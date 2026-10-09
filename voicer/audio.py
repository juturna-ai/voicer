"""Audio helpers: write and read files."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from .engines.base import Audio


def write_wav(audio: Audio, path: str | Path) -> Path:
    path = Path(path)
    sf.write(path, np.clip(audio.samples, -1, 1), audio.sr, subtype="PCM_16")
    return path


def wav_bytes(audio: Audio) -> bytes:
    """16-bit WAV in memory (previews that are not saved)."""
    import io

    buf = io.BytesIO()
    sf.write(buf, np.clip(audio.samples, -1, 1), audio.sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def read(path: str | Path) -> Audio:
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return Audio(data.mean(axis=1), sr)


def decode(path: str | Path) -> Audio:
    """Decode any common audio/video container (wav, mp3, ogg, opus, webm, m4a, flac…) to mono float32.

    Uses PyAV (FFmpeg). Raises ValueError if the file has no decodable audio."""
    import av

    try:
        with av.open(str(path)) as f:
            if not f.streams.audio:
                raise ValueError("No audio track found")
            stream = f.streams.audio[0]
            sr = stream.codec_context.sample_rate or 48000
            rs = av.AudioResampler(format="flt", layout="mono", rate=sr)
            parts = []
            for frame in f.decode(stream):
                for out in rs.resample(frame):
                    parts.append(out.to_ndarray().reshape(-1))
            for out in rs.resample(None):                       # flush
                parts.append(out.to_ndarray().reshape(-1))
    except av.error.FFmpegError as e:
        raise ValueError(f"Not a readable audio file ({e.__class__.__name__})") from None
    if not parts:
        raise ValueError("Audio file is empty")
    return Audio(np.concatenate(parts).astype(np.float32), sr)
