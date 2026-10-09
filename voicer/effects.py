"""Post-processing used by style tags: pitch, gain, whisper."""
from __future__ import annotations

import numpy as np

from .engines.base import Audio

# What each style does. `speed` multiplies the request speed (all engines).
# `temperature` only reaches engines with `expressive = True` (XTTS). pitch/gain/whisper are DSP (all engines).
STYLE_EFFECTS = {
    "slow":    {"speed": 0.8},
    "fast":    {"speed": 1.25},
    "whisper": {"whisper": True, "gain_db": -6.0},
    "happy":   {"speed": 1.05, "pitch": 1.0, "temperature": 0.8},
    "excited": {"speed": 1.15, "pitch": 2.0, "gain_db": 2.0, "temperature": 0.85},
    "sad":     {"speed": 0.88, "pitch": -1.5, "gain_db": -3.0, "temperature": 0.6},
}


def pitch_shift(a: Audio, semitones: float) -> Audio:
    if not semitones or not len(a.samples):
        return a
    import librosa

    return Audio(librosa.effects.pitch_shift(a.samples, sr=a.sr, n_steps=semitones).astype(np.float32), a.sr)


def gain(a: Audio, db: float) -> Audio:
    if not db:
        return a
    return Audio(np.clip(a.samples * 10 ** (db / 20), -1, 1).astype(np.float32), a.sr)


def whisper(a: Audio, seed: int = 0) -> Audio:
    """Keep the spectral envelope, randomize phase: removes the voiced pitch, sounds breathy/whispered."""
    if not len(a.samples):
        return a
    import librosa

    S = librosa.stft(a.samples, n_fft=1024, hop_length=256)
    rng = np.random.default_rng(seed)
    phase = np.exp(2j * np.pi * rng.random(S.shape))
    y = librosa.istft(np.abs(S) * phase, hop_length=256, length=len(a.samples))
    peak = np.max(np.abs(y)) or 1.0
    return Audio((y / peak * np.max(np.abs(a.samples))).astype(np.float32), a.sr)


def apply_style(a: Audio, style: str | None) -> Audio:
    fx = STYLE_EFFECTS.get(style or "", {})
    if fx.get("pitch"):
        a = pitch_shift(a, fx["pitch"])
    if fx.get("whisper"):
        a = whisper(a)
    if fx.get("gain_db"):
        a = gain(a, fx["gain_db"])
    return a
