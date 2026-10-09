"""Generation history: every Text to Speech result is kept in data/outputs/<id>/ (audio.wav + meta.json,
plus cues.json with sentence timings for subtitles)."""
from __future__ import annotations

import json
import re
import secrets
import shutil
import time
from pathlib import Path

from . import config, usage
from .audio import write_wav
from .engines.base import Audio

_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")


def _dir(entry_id: str) -> Path:
    if not _ID.match(entry_id or ""):
        raise KeyError(f"History entry '{entry_id}' not found")
    return config.OUTPUT_DIR / entry_id


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


def add(audio: Audio, text: str, voice: dict, language: str, engine: str, settings: dict | None = None,
        cues: list[dict] | None = None, entry_id: str | None = None) -> dict:
    """Store one generated clip. Returns the entry (no server paths). `entry_id`: one made earlier with
    `new_id()` (a live stream sends its ID before the clip is done)."""
    entry_id = entry_id or new_id()
    d = _dir(entry_id)
    d.mkdir(parents=True)
    write_wav(audio, d / "audio.wav")
    entry = {
        "id": entry_id,
        "text": text,
        "voice_id": voice.get("id"),
        "voice_name": voice.get("name"),
        "language": language,
        "engine": engine,
        "settings": settings or {},
        "seconds": round(len(audio.samples) / audio.sr, 2),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    if cues is not None:
        (d / "cues.json").write_text(json.dumps(cues, ensure_ascii=False))
    (d / "meta.json").write_text(json.dumps(entry, ensure_ascii=False, indent=1))
    usage.record(entry, settings)
    return entry


def get(entry_id: str) -> dict:
    p = _dir(entry_id) / "meta.json"
    if not p.exists():
        raise KeyError(f"History entry '{entry_id}' not found")
    return json.loads(p.read_text())


def entries() -> list[dict]:
    """All entries, newest first. `has_subtitles` = the entry has sentence timings."""
    out = []
    if not config.OUTPUT_DIR.is_dir():
        return out
    for d in sorted(config.OUTPUT_DIR.iterdir(), reverse=True):
        if _ID.match(d.name) and (d / "meta.json").exists():
            try:
                e = json.loads((d / "meta.json").read_text())
            except (OSError, ValueError):                 # half-written or deleted meanwhile: skip, do not fail the list
                continue
            out.append({**e, "has_subtitles": (d / "cues.json").exists()})
    return out


def search(q: str = "", limit: int = 50, offset: int = 0) -> dict:
    """One page of entries, newest first. `q` matches text, voice name/ID, language or engine (any case)."""
    if not 1 <= limit <= 200:
        raise ValueError("limit must be 1 to 200")
    if offset < 0:
        raise ValueError("offset must be 0 or more")
    items = entries()
    q = q.strip().lower()
    if q:
        items = [e for e in items if q in " ".join(str(e.get(k) or "") for k in
                                                   ("text", "voice_name", "voice_id", "language", "engine")).lower()]
    return {"total": len(items), "items": items[offset:offset + limit]}


def audio_path(entry_id: str) -> Path:
    p = _dir(entry_id) / "audio.wav"
    if not p.exists():
        raise KeyError(f"History entry '{entry_id}' not found")
    return p


def subtitles(entry_id: str, fmt: str) -> str:
    """SRT or WebVTT text for an entry."""
    from . import subtitles as subs

    subs.check(fmt)
    p = _dir(entry_id) / "cues.json"
    if not p.exists():
        get(entry_id)                                   # unknown entry → "not found"
        raise KeyError(f"History entry '{entry_id}' has no subtitles")
    return subs.render(json.loads(p.read_text()), fmt)


def delete(entry_id: str) -> None:
    d = _dir(entry_id)
    if not (d / "meta.json").exists():
        raise KeyError(f"History entry '{entry_id}' not found")
    shutil.rmtree(d)
