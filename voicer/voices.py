"""Voice store. Each voice lives in data/voices/<id>/voice.json with its samples."""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from . import config

DEFAULT_CLONE_ENGINE = "xtts"
FIELDS = ("name", "language", "accent", "gender", "age", "tags", "engine", "engine_voice",
          "license", "license_url", "source_url", "commercial", "description", "kind", "samples", "preview",
          "settings", "library_id", "estimated", "transcripts", "consent", "blend")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "voice"


def _path(voice_id: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", voice_id or ""):
        raise KeyError(f"Invalid voice id '{voice_id}'")
    return config.VOICES_DIR / voice_id


def _load(d: Path) -> dict:
    v = json.loads((d / "voice.json").read_text())
    v["dir"] = str(d)
    return v


def save(voice: dict) -> dict:
    d = _path(voice["id"])
    d.mkdir(parents=True, exist_ok=True)
    data = {k: v for k, v in voice.items() if k != "dir"}
    tmp = d / "voice.json.tmp"
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(d / "voice.json")
    data["dir"] = str(d)
    return data


def create(name: str, kind: str = "cloned", sample_files: list[str | Path] = (), **fields) -> dict:
    voice_id = f"{_slug(name)}-{uuid.uuid4().hex[:6]}"
    voice = {
        "id": voice_id, "name": name, "kind": kind,
        "engine": fields.pop("engine", None) or (DEFAULT_CLONE_ENGINE if kind != "preset" else None),
        "language": "en", "tags": [], "samples": [], "settings": {},
        "created_at": time.time(),
    }
    voice.update({k: v for k, v in fields.items() if k in FIELDS})
    d = _path(voice_id)
    (d / "samples").mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(sample_files):
        dest = d / "samples" / f"sample_{i:02d}{Path(f).suffix or '.wav'}"
        shutil.copyfile(f, dest)
        voice["samples"].append(str(dest.relative_to(d)))
    return save(voice)


def get(voice_id: str) -> dict:
    d = _path(voice_id)
    if not (d / "voice.json").exists():
        raise KeyError(f"Voice '{voice_id}' not found")
    return _load(d)


def all_voices() -> list[dict]:
    out = []
    for d in sorted(config.VOICES_DIR.iterdir()):
        if (d / "voice.json").exists():
            out.append(_load(d))
    return out


def find(name_or_id: str) -> dict:
    """Look up a voice by id, then by case-insensitive name. My Voices first, then the library."""
    from . import library

    try:
        return get(name_or_id)
    except KeyError:
        pass
    try:
        return library.get(name_or_id)
    except KeyError:
        pass
    key = (name_or_id or "").strip().lower()
    for v in all_voices() + library.catalog():
        if v["name"].lower() == key or v["name"].lower().split(" (")[0] == key:
            return v
    raise KeyError(f"Voice '{name_or_id}' not found")


def allowed_engines(voice: dict) -> list[str]:
    """Cloned voices can use any cloning engine; blends only XTTS; presets only their own engine."""
    from .engines import ENGINES

    if voice.get("kind") == "preset":
        return [voice["engine"]]
    if voice.get("kind") == "blended" or voice.get("blend"):   # mixed XTTS latents: XTTS only
        return ["xtts"]
    return [n for n, cls in ENGINES.items() if cls.supports_cloning]


def set_engine(voice_id: str, engine: str) -> dict:
    voice = get(voice_id)
    if engine not in allowed_engines(voice):
        raise ValueError(f"Engine '{engine}' not allowed for voice '{voice_id}' "
                         f"(allowed: {', '.join(allowed_engines(voice))})")
    voice["engine"] = engine
    return save(voice)


def update(voice_id: str, **fields) -> dict:
    voice = get(voice_id)
    if "engine" in fields and fields["engine"] != voice.get("engine"):
        set_engine(voice_id, fields["engine"])
        voice = get(voice_id)
    voice.update({k: v for k, v in fields.items() if k in FIELDS and k not in ("engine", "samples")})
    return save(voice)


def delete(voice_id: str) -> None:
    d = _path(voice_id)
    if not (d / "voice.json").exists():
        raise KeyError(f"Voice '{voice_id}' not found")
    shutil.rmtree(d)


# ---- My Voices management (edit, duplicate, default, preview)
EDITABLE = ("name", "description", "tags", "language", "accent", "gender", "age", "engine")
GENDERS = ("female", "male", "neutral", "")
AGES = ("young adult", "adult", "middle-aged", "senior", "")
_preview_lock = threading.Lock()
PREVIEW_TEXT = {"en": "Hello! This is a short preview of this voice. I hope you like how it sounds.",
                "es": "¡Hola! Esta es una breve muestra de esta voz. Espero que te guste cómo suena."}


def _tags(tags) -> list[str]:
    if isinstance(tags, str):
        tags = tags.split(",")
    out = []
    for t in tags or []:
        t = " ".join(str(t).split()).lower()[:30]
        if t and t not in out:
            out.append(t)
    if len(out) > 20:
        raise ValueError("Too many tags (max 20)")
    return out


def edit(voice_id: str, /, **fields) -> dict:
    """Validated edit of the user-facing fields (`EDITABLE`). Other keys are refused."""
    bad = sorted(set(fields) - set(EDITABLE))
    if bad:
        raise ValueError(f"Cannot edit: {', '.join(bad)}")
    out = {}
    if "name" in fields:
        out["name"] = " ".join(str(fields["name"] or "").split())
        if not out["name"] or len(out["name"]) > 80:
            raise ValueError("Name is required (max 80 characters)")
    if "description" in fields:
        out["description"] = str(fields["description"] or "").strip()
        if len(out["description"]) > 500:
            raise ValueError("Description too long (max 500 characters)")
    if "tags" in fields:
        out["tags"] = _tags(fields["tags"])
    if "language" in fields:
        if fields["language"] not in ("en", "es"):
            raise ValueError("language must be en or es")
        out["language"] = fields["language"]
    if "accent" in fields:
        out["accent"] = " ".join(str(fields["accent"] or "").split())[:40]
    for key, allowed in (("gender", GENDERS), ("age", AGES)):
        if key in fields:
            if (fields[key] or "") not in allowed:
                raise ValueError(f"{key} must be one of: {', '.join(a for a in allowed if a)}")
            out[key] = fields[key] or ""
    v = get(voice_id)
    if out.keys() & {"gender", "age", "tags"} and v.get("estimated"):          # the user's value is not an estimate
        out["estimated"] = [f for f in v["estimated"] if f not in out]
    if "engine" in fields:
        out["engine"] = fields["engine"]
    return update(voice_id, **out)


def duplicate(voice_id: str, name: str | None = None) -> dict:
    """Copy a voice (samples, caches, preview) under a new ID. Default name: "<name> (copy)"."""
    src = get(voice_id)
    name = " ".join((name or f"{src['name']} (copy)").split())[:80]
    new_id = f"{_slug(name)}-{uuid.uuid4().hex[:6]}"
    shutil.copytree(src["dir"], _path(new_id))
    v = {k: x for k, x in src.items() if k != "dir"}
    v.update(id=new_id, name=name, created_at=time.time(), duplicated_from=voice_id)
    return save(v)


def default_id() -> str | None:
    """The default voice's ID, or None if unset or the voice no longer exists."""
    from . import settings

    vid = settings.load().get("default_voice")
    if not vid:
        return None
    try:
        find(vid)
        return vid
    except KeyError:
        return None


def set_default(voice_id: str | None) -> str | None:
    from . import settings

    if voice_id:
        find(voice_id)                                # unknown → KeyError
    settings.update(default_voice=voice_id or None)
    return voice_id or None


def preview_file(voice_id: str) -> Path:
    """The voice's preview clip. Made once on first request (standard sentence) if the voice has none."""
    from . import audio, tts

    with _preview_lock:                              # two requests at once → made once, never read half-written
        v = get(voice_id)
        d = Path(v["dir"])
        if v.get("preview") and (d / v["preview"]).is_file() and (d / v["preview"]).resolve().is_relative_to(d.resolve()):
            return d / v["preview"]
        lang = v.get("language") if v.get("language") in PREVIEW_TEXT else "en"
        audio.write_wav(tts.speak(PREVIEW_TEXT[lang], v, lang), d / "preview.wav")
        update(voice_id, preview="preview.wav")
        return d / "preview.wav"

