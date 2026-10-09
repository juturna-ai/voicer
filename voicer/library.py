"""Free voice library: curated open-license preset voices in library/catalog.json."""
from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path

from . import config, voices

CATALOG = config.ROOT / "library" / "catalog.json"
PREVIEWS = config.ROOT / "library" / "previews"
_lock = threading.Lock()
_cache: tuple[float, list[dict]] | None = None


def catalog() -> list[dict]:
    """All library voices (reloaded when the file changes)."""
    global _cache
    with _lock:
        mtime = CATALOG.stat().st_mtime if CATALOG.exists() else 0
        if _cache is None or _cache[0] != mtime:
            data = json.loads(CATALOG.read_text()) if CATALOG.exists() else {"voices": []}
            _cache = (mtime, data["voices"])
        return [dict(v) for v in _cache[1]]


def get(voice_id: str) -> dict:
    for v in catalog():
        if v["id"] == voice_id:
            return v
    raise KeyError(f"Library voice '{voice_id}' not found")


def search(q: str = "", language: str = "", accent: str = "", gender: str = "", age: str = "",
           style: str = "", engine: str = "", license: str = "", commercial: bool | None = None) -> list[dict]:
    """Filter the library. Text filters are case-insensitive; `q` matches name, id, accent, tags, description."""
    out = []
    for v in catalog():
        hay = " ".join([v["id"], v["name"], v.get("accent", ""), v.get("description", ""), *v.get("tags", [])]).lower()
        if q and q.lower() not in hay:
            continue
        if language and v.get("language") != language:
            continue
        if accent and accent.lower() not in v.get("accent", "").lower():
            continue
        if gender and v.get("gender") != gender:
            continue
        if age and v.get("age") != age:
            continue
        if style and style.lower() not in [t.lower() for t in v.get("tags", [])]:
            continue
        if engine and v.get("engine") != engine:
            continue
        if license and license.lower() not in v.get("license", "").lower():
            continue
        if commercial is not None and bool(v.get("commercial")) != commercial:
            continue
        out.append(v)
    return out


def add_to_my_voices(voice_id: str) -> dict:
    """Copy a library voice into My Voices (editable copy, kind = preset)."""
    v = get(voice_id)
    fields = {k: v[k] for k in voices.FIELDS if k in v and k not in ("kind", "samples", "name", "preview")}
    fields["library_id"] = v["id"]
    mine = voices.create(v["name"], kind="preset", **fields)
    src = preview_path(v)
    if src:
        dest = Path(mine["dir"]) / f"preview{src.suffix}"
        shutil.copyfile(src, dest)
        mine["preview"] = dest.name
        mine = voices.save(mine)
    return mine


def preview_path(v: dict) -> Path | None:
    """Absolute path of a library voice's preview clip, if it exists."""
    p = (CATALOG.parent / v["preview"]).resolve() if v.get("preview") else None
    return p if p and p.is_relative_to(PREVIEWS.resolve()) and p.is_file() else None
