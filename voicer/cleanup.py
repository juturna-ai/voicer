"""Clean voice samples for cloning: mono 24 kHz WAV, high-pass, denoise, trim silence, normalize,
then split into 6–15 s clips at natural pauses."""
from __future__ import annotations

import numpy as np

from .engines.base import Audio

SR = 24000
FRAME = 0.02                      # analysis frame (s)
MIN_CLIP, MAX_CLIP = 6.0, 15.0
KEEP_PAUSE = 0.35                 # long silences inside speech are shortened to this (s)
TARGET_RMS_DB, PEAK_DB = -20.0, -1.0


def _resample(a: Audio, sr: int = SR) -> Audio:
    import librosa

    y = a.samples.astype(np.float32)
    return Audio(y if a.sr == sr else librosa.resample(y, orig_sr=a.sr, target_sr=sr), sr)


def _frames_db(y: np.ndarray, sr: int) -> np.ndarray:
    n = max(1, int(FRAME * sr))
    k = len(y) // n
    if k == 0:
        return np.array([-120.0])
    rms = np.sqrt((y[: k * n].reshape(k, n) ** 2).mean(axis=1) + 1e-12)
    return 20 * np.log10(rms)


def speech_mask(y: np.ndarray, sr: int) -> np.ndarray:
    """Per-frame True where there is speech: louder than max(noise floor + 10 dB, loudest − 40 dB)."""
    db = _frames_db(y, sr)
    floor = np.percentile(db, 10)
    thr = max(floor + 10, db.max() - 40)
    mask = db > thr
    # close short gaps (< 0.15 s) and drop isolated blips (< 0.08 s)
    from scipy.ndimage import binary_closing, binary_opening

    mask = binary_closing(mask, structure=np.ones(int(0.15 / FRAME) or 1))
    return binary_opening(mask, structure=np.ones(int(0.08 / FRAME) or 1))


def highpass(y: np.ndarray, sr: int, hz: float = 70.0) -> np.ndarray:
    from scipy.signal import butter, sosfiltfilt

    return sosfiltfilt(butter(4, hz, "highpass", fs=sr, output="sos"), y).astype(np.float32)


def denoise(y: np.ndarray, sr: int) -> np.ndarray:
    """Stationary spectral gating (noisereduce). Noise profile = the quietest non-speech frames."""
    import noisereduce as nr

    mask = speech_mask(y, sr)
    n = int(FRAME * sr)
    noise = np.concatenate([y[i * n:(i + 1) * n] for i in np.flatnonzero(~mask)] or [y[: n * 10]])
    if len(noise) < sr * 0.25:            # too little silence to learn from: gentle, self-estimated
        return nr.reduce_noise(y=y, sr=sr, stationary=True, prop_decrease=0.6).astype(np.float32)
    return nr.reduce_noise(y=y, sr=sr, y_noise=noise, stationary=True, prop_decrease=0.85).astype(np.float32)


def trim_silence(y: np.ndarray, sr: int) -> np.ndarray:
    """Cut leading/trailing silence (keep 0.1 s) and shorten inner silences longer than KEEP_PAUSE."""
    mask = speech_mask(y, sr)
    if not mask.any():
        return y[:0]
    n = int(FRAME * sr)
    keep = np.zeros(len(mask), bool)
    idx = np.flatnonzero(mask)
    pad, half = int(0.1 / FRAME), int(KEEP_PAUSE / 2 / FRAME)
    keep[max(0, idx[0] - pad): idx[-1] + pad + 1] = True
    # inner gaps: keep `half` frames on each side of speech
    run_start = None
    for i in range(idx[0], idx[-1] + 1):
        if not mask[i] and run_start is None:
            run_start = i
        elif mask[i] and run_start is not None:
            if i - run_start > 2 * half:
                keep[run_start + half: i - half] = False
            run_start = None
    out = [y[i * n:(i + 1) * n] for i in np.flatnonzero(keep)]
    tail = y[len(mask) * n:] if keep[-1] else y[:0]
    return np.concatenate(out + [tail]).astype(np.float32)


def normalize(y: np.ndarray, sr: int) -> np.ndarray:
    """Speech RMS to −20 dBFS, peaks capped at −1 dBFS by a soft limiter."""
    mask = speech_mask(y, sr)
    n = int(FRAME * sr)
    speech = np.concatenate([y[i * n:(i + 1) * n] for i in np.flatnonzero(mask)] or [y])
    rms = np.sqrt((speech ** 2).mean() + 1e-12)
    y = y * (10 ** (TARGET_RMS_DB / 20) / rms)
    peak = 10 ** (PEAK_DB / 20)
    over = np.abs(y) > peak * 0.9                      # soft-knee limiter above −1.9 dBFS
    if over.any():
        knee = peak * 0.9
        y = np.where(over, np.sign(y) * (knee + (peak - knee) * np.tanh((np.abs(y) - knee) / (peak - knee))), y)
    return np.clip(y, -peak, peak).astype(np.float32)


def clean(a: Audio) -> Audio:
    a = _resample(a)
    y = highpass(a.samples, SR)
    y = denoise(y, SR)
    y = trim_silence(y, SR)
    if len(y) < SR * 0.5:
        raise ValueError("No speech found in this file")
    return Audio(normalize(y, SR), SR)


def split(a: Audio, min_s: float = MIN_CLIP, max_s: float = MAX_CLIP) -> list[Audio]:
    """Cut at the quietest point inside each 6–15 s window, preferring cuts that leave a ≥6 s remainder.

    Audio shorter than min_s is returned as a single (short) clip."""
    y, sr = a.samples, a.sr
    total = len(y) / sr
    if total <= max_s:
        return [a]
    db = _frames_db(y, sr)
    # smoothed loudness → quiet points are pauses between words/sentences
    sm = np.convolve(db, np.ones(5) / 5, mode="same")
    cuts, start = [0], 0.0
    while total - start > max_s:
        lo, hi = start + min_s, min(start + max_s, total - min_s)
        if hi < lo:                                    # remainder can't make two ≥6 s clips: split evenly
            hi = lo = start + (total - start) / 2
        i0, i1 = int(lo / FRAME), max(int(lo / FRAME) + 1, int(hi / FRAME))
        win = sm[i0:i1]
        # prefer quiet, then nearer the 10 s middle of the range
        target = (start + 10.0 - lo) / FRAME
        score = win + 0.02 * np.abs(np.arange(len(win)) - target)
        cut = (i0 + int(np.argmin(score))) * FRAME
        cuts.append(int(cut * sr))
        start = cut
    cuts.append(len(y))
    return [Audio(y[s:e].copy(), sr) for s, e in zip(cuts, cuts[1:]) if e > s]


def fade(y: np.ndarray, sr: int, ms: float = 10) -> np.ndarray:
    n = min(len(y) // 2, int(sr * ms / 1000))
    if n:
        y = y.copy()
        y[:n] *= np.linspace(0, 1, n)
        y[-n:] *= np.linspace(1, 0, n)
    return y


# ---- Quality meter
MIN_SECONDS, IDEAL_MIN, IDEAL_MAX = 20.0, 60.0, 180.0
NOISY_SNR_DB, BAD_SNR_DB = 20.0, 12.0


def measure(raw: Audio) -> dict:
    """Input quality of one raw file: speech-to-noise ratio, clipping, speech level."""
    a = _resample(raw)
    y = highpass(a.samples, SR)
    mask = speech_mask(y, SR)
    n = int(FRAME * SR)
    frames = lambda m: np.concatenate([y[i * n:(i + 1) * n] for i in np.flatnonzero(m)] or [np.zeros(n)])  # noqa: E731
    lvl = lambda x: float(20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9))  # noqa: E731
    speech_db = lvl(frames(mask))
    # noise floor = 10th percentile of frame levels (robust to soft speech tails inside pauses)
    noise_db = float(np.percentile(_frames_db(y, SR), 10))
    return {
        "snr_db": round(min(60.0, speech_db - noise_db), 1),          # digital silence → cap
        "speech_db": round(speech_db, 1),
        "clipping": round(float((np.abs(raw.samples) >= 0.99).mean()), 5),
    }


def quality(files: list[dict], clean_seconds: float) -> dict:
    """Overall score 0–100 + plain-language warnings. `files`: [{name, snr_db, speech_db, clipping}]."""
    warnings, issues = [], []          # issues = same warnings as codes, so the UI can translate them
    secs = round(clean_seconds)
    if clean_seconds < MIN_SECONDS:
        warnings.append(f"Only {secs} s of speech. Add more: at least 20 s, ideally 1–3 minutes.")
        issues.append({"code": "short", "seconds": secs})
    elif clean_seconds < IDEAL_MIN:
        warnings.append(f"{secs} s of speech. It works, but 1–3 minutes gives a closer match.")
        issues.append({"code": "below_ideal", "seconds": secs})
    for f in files:
        if f["snr_db"] < NOISY_SNR_DB:
            high = f["snr_db"] < BAD_SNR_DB
            warnings.append(f"{f['name']}: background noise is {'high' if high else 'noticeable'}"
                            f" ({f['snr_db']:.0f} dB SNR). Record in a quieter place if you can.")
            issues.append({"code": "noise_high" if high else "noise", "file": f["name"], "snr_db": round(f["snr_db"])})
        if f["clipping"] > 0.001:
            warnings.append(f"{f['name']}: audio is distorted (clipping). Record a little further from the mic.")
            issues.append({"code": "clipping", "file": f["name"]})
        if f["speech_db"] < -40:
            warnings.append(f"{f['name']}: very quiet recording. Move closer to the mic.")
            issues.append({"code": "quiet", "file": f["name"]})
    snr = min((f["snr_db"] for f in files), default=0.0)
    dur_score = min(1.0, clean_seconds / IDEAL_MIN)
    snr_score = float(np.clip((snr - BAD_SNR_DB) / (35 - BAD_SNR_DB), 0, 1))
    clip_pen = 0.2 if any(f["clipping"] > 0.001 for f in files) else 0.0
    score = round(100 * max(0.0, 0.5 * dur_score + 0.5 * snr_score - clip_pen))
    if clean_seconds < MIN_SECONDS or snr < BAD_SNR_DB:
        score = min(score, 39)
    level = "good" if score >= 75 else "ok" if score >= 40 else "poor"
    return {"score": score, "level": level, "seconds": round(clean_seconds, 1), "snr_db": round(snr, 1),
            "warnings": warnings, "issues": issues}
