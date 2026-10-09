"""Estimate voice metadata (gender, age range, style tags) from a speech clip.

These are heuristic estimates from pitch, pitch movement, speaking rate and brightness.
Fields filled this way are listed in the voice's `estimated` field."""
from __future__ import annotations

import numpy as np

from .engines.base import Audio

STYLE_TAGS = ("warm", "narrator", "news", "conversational", "energetic", "calm")
# Gender score = semitones of median F0 above 155 Hz + semitones of 3rd formant above 2650 Hz
# (shorter vocal tract → higher formants). Tuned on 47 voices of known gender: 45 correct.
F0_REF_HZ, F3_REF_HZ, FEMALE_SCORE = 155.0, 2650.0, -1.05


def features(a: Audio, text: str) -> dict:
    """Median F0 (Hz), pitch movement (semitones std), rate (chars/s), brightness (spectral centroid Hz)."""
    import librosa

    y = a.samples.astype(np.float32)
    if a.sr != 16000:
        y = librosa.resample(y, orig_sr=a.sr, target_sr=16000)
    f0, voiced, _ = librosa.pyin(y, fmin=60, fmax=450, sr=16000, frame_length=1024)
    f0 = f0[voiced & ~np.isnan(f0)]
    if len(f0) < 10:
        raise ValueError("Not enough voiced speech to analyze")
    semis = 12 * np.log2(f0 / np.median(f0))
    rms = librosa.feature.rms(y=y)[0]
    speech = (rms > 0.1 * rms.max()).sum() * 512 / 16000        # seconds of non-silent audio
    centroid = librosa.feature.spectral_centroid(y=y, sr=16000)[0]
    return {
        "f0": float(np.median(f0)),
        "f3": third_formant(y, 16000),
        "pitch_var": float(np.std(semis)),
        "rate": len(text) / max(speech, 0.1),
        "brightness": float(np.median(centroid[rms > 0.1 * rms.max()])),
    }


def third_formant(y: np.ndarray, sr: int) -> float:
    """Median 3rd formant (Hz) of loud frames, from LPC roots at 10 kHz."""
    import librosa

    y = librosa.effects.preemphasis(librosa.resample(y, orig_sr=sr, target_sr=10000))
    frames = librosa.util.frame(y, frame_length=250, hop_length=100).T
    rms = np.sqrt((frames ** 2).mean(axis=1))
    win = np.hamming(250)
    f3 = []
    for fr in frames[rms > 0.2 * rms.max()]:
        try:
            roots = [z for z in np.roots(librosa.lpc(fr * win, order=12)) if np.imag(z) > 0]
        except Exception:      # flat/ill-conditioned frame
            continue
        freqs = sorted(np.angle(z) * 10000 / (2 * np.pi) for z in roots
                       if np.angle(z) * 10000 / (2 * np.pi) > 200 and -10000 / np.pi * np.log(abs(z)) < 800)
        if len(freqs) >= 3:
            f3.append(freqs[2])
    return float(np.median(f3)) if f3 else 0.0


def gender(f: dict) -> str:
    st = lambda x, ref: 12 * np.log2(max(x, 1.0) / ref)  # noqa: E731
    score = st(f["f0"], F0_REF_HZ) + (st(f["f3"], F3_REF_HZ) if f.get("f3") else 0.0)
    return "female" if score >= FEMALE_SCORE else "male"


def age(f: dict, g: str) -> str:
    """Coarse age range from pitch relative to the typical adult range for the gender."""
    hi, lo = (150, 100) if g == "male" else (235, 175)
    if f["f0"] >= hi:
        return "young adult"
    if f["f0"] < lo:
        return "middle-aged"
    return "adult"


def _pct(values: list[float], x: float) -> float:
    return float(np.mean(np.asarray(values) <= x))


def style_tags(f: dict, peers: list[dict]) -> list[str]:
    """Tags from this voice's rank among peers (same language): rate, pitch movement, brightness."""
    rate = _pct([p["rate"] for p in peers], f["rate"])
    var = _pct([p["pitch_var"] for p in peers], f["pitch_var"])
    bright = _pct([p["brightness"] for p in peers], f["brightness"])
    tags = []
    if rate >= 0.65 and var >= 0.5:
        tags.append("energetic")
    if rate < 0.35 or (var < 0.3 and rate < 0.6):
        tags.append("calm")
    if 0.2 <= rate < 0.7 and var >= 0.4:
        tags.append("narrator")
    if rate >= 0.5 and var < 0.5:
        tags.append("news")
    if var >= 0.6 or not tags:
        tags.append("conversational")
    if bright < 0.4:
        tags.append("warm")
    return tags[:3]
