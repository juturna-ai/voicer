"""F5-TTS: optional cloning engine. English = official F5TTS_v1_Base, Spanish = jpgallegoar/F5-Spanish."""
from __future__ import annotations

import gc
import os
from pathlib import Path

import numpy as np

from .. import config
from .base import Audio, Engine

CHECKPOINTS = {
    "en": {"model": "F5TTS_v1_Base", "repo": "SWivid/F5-TTS",
           "ckpt": "F5TTS_v1_Base/model_1250000.safetensors", "vocab": "F5TTS_v1_Base/vocab.txt"},
    "es": {"model": "F5TTS_Base", "repo": "jpgallegoar/F5-Spanish",
           "ckpt": "model_1250000.safetensors", "vocab": "vocab.txt"},
}
REF_MAX_SECONDS = 11.0


def hash_text(text: str) -> str:
    import hashlib

    return hashlib.sha1(text.encode()).hexdigest()[:12]


class F5Engine(Engine):
    name = "f5"
    large = True
    supports_cloning = True
    languages = ("en", "es")
    max_chars = 300

    def __init__(self):
        self.model = None
        self.variant = None

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def load(self, language: str | None = None) -> None:
        """Checkpoint depends on language, so the real load happens at first synthesis."""
        if language is None or (self.model is not None and self.variant == language):
            return
        self.unload()
        from huggingface_hub import hf_hub_download
        from f5_tts.api import F5TTS
        import torch

        c = CHECKPOINTS[language]
        ckpt = hf_hub_download(c["repo"], c["ckpt"])
        vocab = hf_hub_download(c["repo"], c["vocab"])
        device = config.DEVICE if torch.cuda.is_available() else "cpu"
        self.model = F5TTS(model=c["model"], ckpt_file=ckpt, vocab_file=vocab, device=device)
        self.variant = language

    def unload(self) -> None:
        if self.model is None:
            return
        self.model, self.variant = None, None
        gc.collect()
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def reference(self, voice: dict) -> tuple[str, str]:
        """A short (<= 11 s) reference clip and its transcript, cached in the voice folder."""
        from .. import asr, audio

        from .xtts import samples_key

        d = Path(voice["dir"])
        if not voice.get("samples"):
            raise ValueError(f"Voice {voice.get('id')} has no reference samples")
        ref_wav, ref_txt, ref_key = (d / "cache" / n for n in ("f5_ref.wav", "f5_ref.txt", "f5_ref.key"))
        known = (voice.get("transcripts") or {}).get(voice["samples"][0])   # saved/edited clip transcript
        key = samples_key([d / s for s in voice["samples"]]) + (f":{hash_text(known)}" if known else "")
        if ref_wav.exists() and ref_txt.exists() and ref_key.exists() and ref_key.read_text() == key:
            return str(ref_wav), ref_txt.read_text()
        a = audio.read(d / voice["samples"][0])
        whole = len(a.samples) <= a.sr * REF_MAX_SECONDS
        a.samples = a.samples[: int(a.sr * REF_MAX_SECONDS)]
        ref_wav.parent.mkdir(exist_ok=True)
        audio.write_wav(a, ref_wav)
        text = known if known and whole else asr.transcribe(ref_wav)["text"]
        ref_txt.write_text(text)
        ref_key.write_text(key)
        return str(ref_wav), text

    def synthesize(self, text, voice, language, speed=1.0, **opts) -> Audio:
        ref_wav, ref_text = self.reference(voice)
        self.load(language)
        hash_seed = os.environ.get("PYTHONHASHSEED")
        try:
            wav, sr, _ = self.model.infer(ref_wav, ref_text, text, speed=speed, show_info=lambda *a: None,
                                          nfe_step=int(opts.get("nfe_step", 32)), seed=opts.get("seed"))
        finally:   # F5 writes its random seed (up to 2**63) there; Python child processes then fail to start
            if hash_seed is None:
                os.environ.pop("PYTHONHASHSEED", None)
            else:
                os.environ["PYTHONHASHSEED"] = hash_seed
        return Audio(np.asarray(wav, dtype=np.float32).reshape(-1), sr)
