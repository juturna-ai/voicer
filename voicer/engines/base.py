"""Common engine interface. Every engine returns mono float32 audio and its sample rate."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Audio:
    samples: np.ndarray  # mono float32, range -1..1
    sr: int


class Engine:
    name = "base"
    large = False          # large engines share the single GPU slot
    languages: tuple[str, ...] = ("en", "es")
    supports_cloning = False
    max_chars = 250        # longest text piece sent in one call
    expressive = False     # accepts `temperature` (variation / expressiveness)
    controls: tuple[str, ...] = ("speed",)   # UI/API sliders this engine honours (stability, expressiveness: 0–1)
    streams = False        # synthesize_stream yields pieces while the engine works (live first byte)
    sr: int | None = None  # output rate, when fixed

    def load(self) -> None:
        raise NotImplementedError

    def unload(self) -> None:
        raise NotImplementedError

    @property
    def loaded(self) -> bool:
        raise NotImplementedError

    def synthesize(self, text: str, voice: dict, language: str, speed: float = 1.0, **opts) -> Audio:
        raise NotImplementedError

    def synthesize_stream(self, text: str, voice: dict, language: str, speed: float = 1.0, **opts):
        """Audio pieces of one call, as they are made. Default: the whole result as one piece."""
        yield self.synthesize(text, voice, language, speed=speed, **opts)


def slider(opts: dict, name: str, default: float, at0: float, at1: float) -> float:
    """Map a 0–1 slider (0.5 = engine default) to a native value: 0 → at0, 0.5 → default, 1 → at1."""
    x = opts.get(name)
    if x is None:
        return default
    x = min(1.0, max(0.0, float(x)))
    return default + (at0 - default) * (1 - 2 * x) if x < 0.5 else default + (at1 - default) * (2 * x - 1)
