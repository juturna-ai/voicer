"""Piper TTS (ONNX, CPU): light preset voices from rhasspy/piper-voices."""
from __future__ import annotations

import numpy as np

from .. import config
from .base import Audio, Engine, slider

REPO = "rhasspy/piper-voices"


def voice_files(name: str) -> tuple[str, str]:
    """Download (once) and return (model.onnx, model.onnx.json) for a voice like 'es_MX-ald-medium'."""
    from huggingface_hub import hf_hub_download

    locale, speaker, quality = name.split("-")
    base = f"{locale.split('_')[0]}/{locale}/{speaker}/{quality}/{name}.onnx"
    cache = config.MODELS_DIR / "piper"
    return (hf_hub_download(REPO, base, cache_dir=cache),
            hf_hub_download(REPO, base + ".json", cache_dir=cache))


class PiperEngine(Engine):
    name = "piper"
    large = False  # CPU only, ~60 MB per voice
    languages = ("en", "es")
    max_chars = 400
    controls = ("speed", "stability", "expressiveness")

    def __init__(self):
        self.voices = {}

    @property
    def loaded(self) -> bool:
        return bool(self.voices)

    def load(self) -> None:
        pass  # voices load on demand

    def unload(self) -> None:
        self.voices = {}

    def voice(self, name: str):
        if name not in self.voices:
            from piper import PiperVoice

            model, cfg = voice_files(name)
            self.voices[name] = PiperVoice.load(model, cfg)
        return self.voices[name]

    def synthesize(self, text, voice, language, speed=1.0, **opts) -> Audio:
        from piper import SynthesisConfig

        pv = self.voice(voice["engine_voice"])
        ns, nw = pv.config.noise_scale, pv.config.noise_w_scale
        cfg = SynthesisConfig(speaker_id=(voice.get("settings") or {}).get("speaker_id"),
                              length_scale=1.0 / max(0.25, speed),
                              noise_scale=slider(opts, "stability", ns, min(1.2, 2 * ns), 0.0),     # voice variation
                              noise_w_scale=slider(opts, "expressiveness", nw, 0.0, min(1.6, 2 * nw)))  # timing variation
        chunks = [c.audio_int16_array for c in pv.synthesize(text, syn_config=cfg)]
        wav = (np.concatenate(chunks).astype(np.float32) / 32768.0) if chunks else np.zeros(0, np.float32)
        return Audio(wav, pv.config.sample_rate)
