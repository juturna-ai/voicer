"""Kokoro-82M (Apache 2.0): fast preset voices, English (US/UK) and Spanish."""
from __future__ import annotations

import gc

import numpy as np

from .. import config
from .base import Audio, Engine

REPO = "hexgrad/Kokoro-82M"


class KokoroEngine(Engine):
    name = "kokoro"
    large = False  # ~0.35 GB VRAM, may stay next to a large model
    languages = ("en", "es")
    max_chars = 400

    def __init__(self):
        self.model = None
        self.pipelines = {}

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        if self.model is not None:
            return
        import torch
        from kokoro import KModel

        device = config.DEVICE if torch.cuda.is_available() else "cpu"
        self.model = KModel(repo_id=REPO).to(device).eval()

    def unload(self) -> None:
        if self.model is None:
            return
        self.model, self.pipelines = None, {}
        gc.collect()
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    @staticmethod
    def lang_code(voice_name: str, language: str) -> str:
        """Kokoro voice prefix: a = US English, b = UK English, e = Spanish."""
        if language == "es":
            return "e"
        return voice_name[0] if voice_name[:1] in ("a", "b") else "a"

    def pipeline(self, code: str):
        from kokoro import KPipeline

        if code not in self.pipelines:
            self.pipelines[code] = KPipeline(lang_code=code, repo_id=REPO, model=self.model)
        return self.pipelines[code]

    def synthesize(self, text, voice, language, speed=1.0, **opts) -> Audio:
        self.load()
        name = voice["engine_voice"]
        chunks = [r.audio.cpu().numpy() for r in self.pipeline(self.lang_code(name, language))(text, voice=name, speed=speed)
                  if r.audio is not None]
        wav = np.concatenate(chunks).astype(np.float32) if chunks else np.zeros(0, np.float32)
        return Audio(wav, 24000)
