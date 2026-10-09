"""Timed subtitles (SRT / WebVTT) from the sentence timings of a generated clip, or from any recording (Whisper)."""
from __future__ import annotations

import re

FORMATS = {"srt": "application/x-subrip", "vtt": "text/vtt"}
MAX_LINE, MAX_LINES = 42, 2          # common subtitle guideline: two lines of up to 42 characters


def check(fmt: str) -> str:
    if fmt not in FORMATS:
        raise ValueError(f"Unknown subtitle format '{fmt}' (use {', '.join(FORMATS)})")
    return FORMATS[fmt]


def _wrap(text: str, width: int = MAX_LINE) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    return lines + [cur] if cur else lines


def cues(timings: list[dict]) -> list[dict]:
    """Readable cues: tags removed, long sentences cut into blocks of at most two 42-character lines.
    A cut sentence shares its time by character count."""
    out = []
    for c in timings:
        text = re.sub(r"\s+", " ", re.sub(r"\[[^\]]*\]", " ", c["text"])).strip()
        if not text:
            continue
        lines = _wrap(text)
        blocks = [lines[i:i + MAX_LINES] for i in range(0, len(lines), MAX_LINES)]
        total = sum(len(" ".join(b)) for b in blocks)
        t = c["start"]
        for b in blocks:
            end = t + (c["end"] - c["start"]) * len(" ".join(b)) / total
            out.append({"start": t, "end": end, "lines": b})
            t = end
    return out


def _ts(sec: float, sep: str) -> str:
    ms = max(0, round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def render(timings: list[dict], fmt: str) -> str:
    check(fmt)
    sep = "," if fmt == "srt" else "."
    blocks = [f"{i}\n{_ts(c['start'], sep)} --> {_ts(c['end'], sep)}\n" + "\n".join(c["lines"])
              for i, c in enumerate(cues(timings), 1)]
    body = "\n\n".join(blocks) + "\n" if blocks else ""
    return ("WEBVTT\n\n" + body) if fmt == "vtt" else body


MAX_AUDIO_SECONDS = 600              # Whisper runs on the CPU: 10 min of audio is about a minute or two of work


def from_audio(path, language: str = "auto") -> list[dict]:
    """Timings `[{start, end, text}]` for a recording (any common audio/video file), from a Whisper transcript."""
    import numpy as np

    from . import asr, audio

    if language not in ("auto", "en", "es"):
        raise ValueError(f"Unsupported language '{language}' (use auto, en or es)")
    a = audio.decode(path)                           # not audio → ValueError
    seconds = len(a.samples) / a.sr
    if seconds < 0.5:
        raise ValueError(f"Recording is too short ({seconds:.1f} s, min 0.5 s)")
    if seconds > MAX_AUDIO_SECONDS:
        raise ValueError(f"Recording is too long ({seconds / 60:.1f} min, max {MAX_AUDIO_SECONDS // 60} min)")
    if float(np.max(np.abs(a.samples))) < 1e-3:
        raise ValueError("Recording is silent")
    segs = asr.transcribe(path, None if language == "auto" else language)["segments"]
    timings = [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in segs if s["text"]]
    if not timings:
        raise ValueError("No speech found in the recording")
    return timings
