"""Coqui XTTS-v2 (maintained `coqui-tts` fork). Zero-shot cloning, cross-lingual es/en."""
from __future__ import annotations

import gc
from pathlib import Path

import numpy as np

from .. import config
from .base import Audio, Engine, slider

MODEL_ID = "tts_models/multilingual/multi-dataset/xtts_v2"


def samples_key(paths) -> str:
    """Changes whenever a sample file is added, removed or modified."""
    import hashlib

    h = hashlib.sha1()
    for p in paths:
        st = Path(p).stat()
        h.update(f"{Path(p).name}:{st.st_size}:{st.st_mtime_ns};".encode())
    return h.hexdigest()


def mix_latents(a: tuple, b: tuple, ratio: float) -> tuple:
    """Weighted mix of two (gpt_cond_latent, speaker_embedding) pairs; `ratio` = share of A.

    The speaker embedding is rescaled to the mixed norm so the blend is not "quieter" than its sources."""
    import torch

    ga, sa = (t.detach().float().cpu() for t in a)
    gb, sb = (t.detach().float().cpu() for t in b)
    if ga.shape != gb.shape or sa.shape != sb.shape:
        raise ValueError("Voice latents do not match")
    gpt = ratio * ga + (1 - ratio) * gb
    spk = ratio * sa + (1 - ratio) * sb
    want = ratio * sa.norm() + (1 - ratio) * sb.norm()
    spk = spk * (want / spk.norm().clamp_min(1e-8))
    return gpt, spk


class XTTSEngine(Engine):
    name = "xtts"
    large = True
    supports_cloning = True
    languages = ("en", "es")
    max_chars = 200
    expressive = True
    controls = ("speed", "stability", "expressiveness")
    streams = True
    sr = 24000
    STREAM_TOKENS = 12                       # GPT tokens per streamed piece (~0.5 s of speech; smaller = sooner
    #                                          first byte but more re-decoding — 8 was barely real time on an RTX 2080)

    def __init__(self):
        self.model = None
        self._latents: dict[str, tuple[str, tuple]] = {}  # voice id -> (samples key, latents)

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        if self.model is not None:
            return
        from TTS.api import TTS
        import torch

        device = config.DEVICE if torch.cuda.is_available() else "cpu"
        self.model = TTS(MODEL_ID, progress_bar=False).to(device).synthesizer.tts_model
        self.model.eval()

    def unload(self) -> None:
        if self.model is None:
            return
        self.model, self._latents = None, {}
        gc.collect()
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    @property
    def studio_speakers(self) -> list[str]:
        self.load()
        return list(self.model.speaker_manager.speakers.keys())

    def latents(self, voice: dict):
        """Return (gpt_cond_latent, speaker_embedding) for a voice."""
        self.load()
        if voice.get("blend"):
            return self._blend_latents(voice)
        if voice.get("engine_voice"):  # built-in studio speaker
            spk = self.model.speaker_manager.speakers[voice["engine_voice"]]
            return spk["gpt_cond_latent"], spk["speaker_embedding"]
        samples = [Path(voice["dir"]) / s for s in voice.get("samples", [])]
        if not samples:
            raise ValueError(f"Voice {voice.get('id')} has no reference samples")
        key = samples_key(samples)
        hit = self._latents.get(voice["id"])
        if hit and hit[0] == key:
            return hit[1]
        import torch

        disk = Path(voice["dir"]) / "cache" / "xtts_latents.pt"
        lat = None
        if disk.exists():
            saved = torch.load(disk, map_location="cpu", weights_only=True)
            if saved.get("key") == key:
                lat = (saved["gpt"], saved["spk"])
        if lat is None:
            lat = self.model.get_conditioning_latents(audio_path=[str(s) for s in samples],
                                                      gpt_cond_len=30, max_ref_length=60)
            disk.parent.mkdir(exist_ok=True)
            torch.save({"key": key, "gpt": lat[0].cpu(), "spk": lat[1].cpu()}, disk)
        device = self.model.device
        lat = (lat[0].to(device), lat[1].to(device))
        self._latents[voice["id"]] = (key, lat)
        return lat

    def _blend_latents(self, voice: dict):
        """Saved blend → its stored blend.pt. Unsaved blend (preview) → mix the two source voices now."""
        import json

        import torch

        b = voice["blend"]
        key = json.dumps(b, sort_keys=True)
        hit = self._latents.get(voice["id"])
        if hit and hit[0] == key:
            return hit[1]
        stored = Path(voice["dir"]) / "blend.pt" if voice.get("dir") else None
        if stored and stored.exists():
            saved = torch.load(stored, map_location="cpu", weights_only=True)
            lat = (saved["gpt"], saved["spk"])
        else:
            from .. import voices

            va, vb = voice.get("_sources") or (voices.find(b["a"]), voices.find(b["b"]))
            lat = mix_latents(self.latents(va), self.latents(vb), float(b["ratio"]))
        device = self.model.device
        lat = (lat[0].to(device), lat[1].to(device))
        self._latents[voice["id"]] = (key, lat)
        return lat

    @staticmethod
    def _sampling(opts: dict) -> dict:
        # stability: low = varied delivery (high temperature), high = steady; a style tag's temperature wins
        return {"temperature": float(opts.get("temperature") or slider(opts, "stability", 0.7, 1.0, 0.3)),
                "top_p": slider(opts, "expressiveness", 0.85, 0.6, 1.0)}   # wider sampling = livelier prosody

    def synthesize(self, text, voice, language, speed=1.0, **opts) -> Audio:
        import torch

        gpt, spk = self.latents(voice)
        with torch.inference_mode():
            out = self.model.inference(text, language, gpt, spk, speed=speed, enable_text_splitting=True,
                                       **self._sampling(opts))
        wav = np.asarray(out["wav"], dtype=np.float32).reshape(-1)
        return Audio(wav, 24000)

    def synthesize_stream(self, text, voice, language, speed=1.0, **opts):
        """XTTS streaming decoder: a piece every `STREAM_TOKENS` GPT tokens (pieces are cross-faded by XTTS)."""
        import torch

        gpt, spk = self.latents(voice)
        with torch.inference_mode():
            for chunk in self.model.inference_stream(text, language, gpt, spk, stream_chunk_size=self.STREAM_TOKENS,
                                                     speed=speed, **self._sampling(opts)):
                yield Audio(chunk.detach().float().cpu().numpy().reshape(-1), 24000)
