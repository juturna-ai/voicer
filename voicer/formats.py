"""Output formats: WAV as stored, MP3 and OGG/Opus encoded on demand with PyAV (FFmpeg) and cached next to the WAV."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

import numpy as np

from .audio import read

FORMATS = {
    "wav": {"ext": "wav", "mime": "audio/wav"},
    "mp3": {"ext": "mp3", "mime": "audio/mpeg", "container": "mp3", "codec": "libmp3lame",
            "rate": 44100, "bit_rate": 128_000, "options": {}},
    # WhatsApp voice note: OGG container, Opus codec, mono, 48 kHz
    "ogg_opus": {"ext": "ogg", "mime": "audio/ogg", "container": "ogg", "codec": "libopus",
                 "rate": 48000, "bit_rate": 32_000, "options": {"application": "voip"}},
    # also offered for OpenAI-compatible clients (/v1/audio/speech response_format)
    "flac": {"ext": "flac", "mime": "audio/flac", "container": "flac", "codec": "flac",
             "rate": None, "bit_rate": 0, "options": {}},                    # lossless, engine sample rate
    "aac": {"ext": "aac", "mime": "audio/aac", "container": "adts", "codec": "aac",
            "rate": 44100, "bit_rate": 128_000, "options": {}},
    # raw 16-bit little-endian samples, 24 kHz, no header (the OpenAI "pcm" format)
    "pcm": {"ext": "pcm", "mime": "audio/pcm", "container": "s16le", "codec": "pcm_s16le",
            "rate": 24000, "bit_rate": 0, "options": {}},
}


def check(fmt: str) -> dict:
    if fmt not in FORMATS:
        raise ValueError(f"Unknown format '{fmt}' (use {', '.join(FORMATS)})")
    return FORMATS[fmt]


def encode(wav: Path, fmt: str) -> Path:
    """Path of `wav` in format `fmt`. Encoded files are cached beside the WAV."""
    spec = check(fmt)
    if fmt == "wav":
        return wav
    out = wav.with_suffix("." + spec["ext"])
    if out.exists() and out.stat().st_mtime >= wav.stat().st_mtime:
        return out
    tmp = out.with_name(f".{out.name}.{secrets.token_hex(4)}")
    try:
        _write(read(wav), tmp, spec)
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    return out


def _write(a, path: Path, spec: dict) -> None:
    import av

    rate = spec["rate"] or a.sr
    with av.open(str(path), "w", format=spec["container"]) as c:
        st = c.add_stream(spec["codec"], rate=rate, layout="mono")
        if spec["bit_rate"]:
            st.bit_rate = spec["bit_rate"]
        st.options = spec["options"]
        frame = av.AudioFrame.from_ndarray(np.clip(a.samples, -1, 1).astype(np.float32)[None, :], format="flt", layout="mono")
        frame.sample_rate = a.sr
        rs = av.AudioResampler(format=st.codec_context.format, layout="mono", rate=rate,
                               frame_size=st.codec_context.frame_size or None)
        for f in [*rs.resample(frame), *rs.resample(None)]:
            c.mux(st.encode(f))
        c.mux(st.encode(None))
