"""OpenVoice v2 tone colour converter (MyShell, MIT), loaded through `coqui-tts`. Speech-to-speech: keeps the
words, timing and emotion of the source and swaps the voice. Not a Text to Speech engine (not in ENGINES)."""
from __future__ import annotations

import gc

import numpy as np

from .. import config
from .base import Audio

MODEL_ID = "voice_conversion_models/multilingual/multi-dataset/openvoice_v2"
SR = 22050                    # model input and output rate


class OpenVoiceConverter:
    name = "openvoice"
    large = False             # ~33 M parameters, ~130 MB VRAM: may stay next to one large TTS model

    def __init__(self):
        self.model = None

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def load(self) -> None:
        if self.model is not None:
            return
        import torch
        from TTS.api import TTS

        device = config.DEVICE if torch.cuda.is_available() else "cpu"
        self.model = TTS(MODEL_ID, progress_bar=False).to(device).voice_converter.vc_model
        self.model.eval()

    def unload(self) -> None:
        if self.model is None:
            return
        self.model = None
        gc.collect()
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def convert(self, source: Audio, references: list[Audio]) -> Audio:
        """`source` spoken in the voice of `references` (all must be at `SR`)."""
        import torch

        self.load()
        refs = [torch.from_numpy(np.ascontiguousarray(r.samples, dtype=np.float32)) for r in references]
        out = self.model.voice_conversion(torch.from_numpy(np.ascontiguousarray(source.samples, dtype=np.float32)), refs)
        return Audio(np.asarray(out, dtype=np.float32), SR)
