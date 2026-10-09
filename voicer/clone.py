"""Clone drafts: audio a user uploads or records before it becomes a saved voice.

data/drafts/<id>/draft.json + raw/<NN>_<name> (original files, untouched)."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
import uuid
from pathlib import Path

from . import audio, config

DRAFTS_DIR = config.DATA_DIR / "drafts"
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_FILES = 50


def _dir(draft_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{12}", draft_id or ""):
        raise KeyError(f"Invalid draft id '{draft_id}'")
    return DRAFTS_DIR / draft_id


def _save(d: dict) -> dict:
    p = _dir(d["id"]) / "draft.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False))
    tmp.replace(p)
    return d


def new() -> dict:
    draft_id = uuid.uuid4().hex[:12]
    (_dir(draft_id) / "raw").mkdir(parents=True)
    return _save({"id": draft_id, "created_at": time.time(), "files": []})


def get(draft_id: str) -> dict:
    p = _dir(draft_id) / "draft.json"
    if not p.exists():
        raise KeyError(f"Draft '{draft_id}' not found")
    d = json.loads(p.read_text())
    d["total_seconds"] = round(sum(f["seconds"] for f in d["files"]), 2)
    d["clean_seconds"] = round(sum(c["seconds"] for c in d.get("clips", [])), 2)
    return d


def _safe_name(name: str) -> str:
    stem, dot, ext = Path(name or "audio").name.rpartition(".")
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem if dot else ext)[:60].strip("_") or "audio"
    ext = re.sub(r"[^a-z0-9]", "", ext.lower())[:5] if dot else "bin"
    return f"{stem}.{ext or 'bin'}"


def add_file(draft_id: str, filename: str, data: bytes, source: str = "upload") -> dict:
    """Store one uploaded/recorded file after checking it decodes as audio."""
    d = get(draft_id)
    if len(d["files"]) >= MAX_FILES:
        raise ValueError(f"Too many files (max {MAX_FILES})")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"File too large (max {MAX_FILE_BYTES // 2**20} MB)")
    if not data:
        raise ValueError("Empty file")
    name = f"{len(d['files']):02d}_{_safe_name(filename)}"
    while (_dir(draft_id) / "raw" / name).exists():                   # after deletions
        name = f"{int(name[:2]) + 1:02d}{name[2:]}"
    path = _dir(draft_id) / "raw" / name
    path.write_bytes(data)
    try:
        a = audio.decode(path)
    except ValueError:
        path.unlink()
        raise
    d["files"].append({"name": name, "original": Path(filename or "").name[:120], "source": source,
                       "seconds": round(len(a.samples) / a.sr, 2), "sample_rate": a.sr, "bytes": len(data)})
    d.pop("total_seconds", None)
    d.pop("clean_seconds", None)
    _save(d)
    return get(draft_id)


def remove_file(draft_id: str, name: str) -> dict:
    d = get(draft_id)
    keep = [f for f in d["files"] if f["name"] != name]
    if len(keep) == len(d["files"]):
        raise KeyError(f"File '{name}' not in draft")
    (_dir(draft_id) / "raw" / name).unlink(missing_ok=True)
    d["files"] = keep
    d.pop("total_seconds", None)
    d.pop("clean_seconds", None)
    _save(d)
    return get(draft_id)


def raw_path(draft_id: str, name: str) -> Path:
    get(draft_id)
    p = _dir(draft_id) / "raw" / Path(name).name
    if not p.is_file():
        raise KeyError(f"File '{name}' not in draft")
    return p


def delete(draft_id: str) -> None:
    shutil.rmtree(_dir(draft_id), ignore_errors=True)


def process(draft_id: str) -> dict:
    """Auto-clean every raw file and split it into 6–15 s clips → clips/clip_NN.wav (24 kHz mono PCM16).

    Files are cleaned separately (never joined), so each clip holds one recording."""
    from . import cleanup

    d = get(draft_id)
    out = _dir(draft_id) / "clips"
    if out.exists():
        shutil.rmtree(out)                       # clips are always regenerated from raw/
    out.mkdir()
    clips, errors, measured = [], [], []
    known = {c["hash"]: c for c in d.get("clips", []) if c.get("hash") and "text" in c}
    for f in d["files"]:
        label = f["original"] or f["name"]
        try:
            raw = audio.decode(_dir(draft_id) / "raw" / f["name"])
            m = cleanup.measure(raw)
            a = cleanup.clean(raw)
            measured.append({"name": label, **m})
        except ValueError as e:
            errors.append({"file": label, "error": str(e)})
            continue
        for part in cleanup.split(a):
            name = f"clip_{len(clips):02d}.wav"
            part.samples = cleanup.fade(part.samples, part.sr)
            audio.write_wav(part, out / name)
            clip = {"name": name, "file": f["name"], "seconds": round(len(part.samples) / part.sr, 2),
                    "hash": hashlib.sha1((out / name).read_bytes()).hexdigest()[:16]}
            old = known.get(clip["hash"])                # same audio → keep its transcript (and user edits)
            if old:
                clip.update({k: old[k] for k in ("text", "language", "edited") if k in old})
            clips.append(clip)
    d = get(draft_id)
    d["clips"], d["clean_errors"] = clips, errors
    d["quality"] = cleanup.quality(measured, sum(c["seconds"] for c in clips))
    d["language"] = _main_language(clips)
    d.pop("total_seconds", None)
    d.pop("clean_seconds", None)
    _save(d)
    return get(draft_id)


def clip_path(draft_id: str, name: str) -> Path:
    get(draft_id)
    p = _dir(draft_id) / "clips" / Path(name).name
    if not p.is_file():
        raise KeyError(f"Clip '{name}' not in draft")
    return p


MAX_TEXT = 1000


def _main_language(clips: list[dict]) -> str | None:
    """Language with the most transcribed seconds (None if nothing is transcribed yet)."""
    secs: dict[str, float] = {}
    for c in clips:
        if c.get("language"):
            secs[c["language"]] = secs.get(c["language"], 0) + c["seconds"]
    return max(secs, key=secs.get) if secs else None


def transcribe(draft_id: str, language: str | None = None) -> dict:
    """Transcribe every clean clip that has no transcript yet (faster-whisper, CPU).

    `language` forces en/es; otherwise Whisper detects it per clip. Edited transcripts are never overwritten."""
    from . import asr

    if language not in (None, "", "auto", "en", "es"):
        raise ValueError("language must be auto, en or es")
    language = language if language in ("en", "es") else None
    d = get(draft_id)
    done = {}
    for c in d.get("clips", []):
        if "text" in c:
            continue
        r = asr.transcribe(clip_path(draft_id, c["name"]), language=language)
        done[c["name"]] = {"text": r["text"][:MAX_TEXT], "language": r["language"]}
    d = get(draft_id)                            # re-read: clips may have changed meanwhile
    for c in d.get("clips", []):
        if c["name"] in done and "text" not in c:
            c.update(done[c["name"]])
    d["language"] = _main_language(d.get("clips", []))
    d.pop("total_seconds", None)
    d.pop("clean_seconds", None)
    _save(d)
    return get(draft_id)


def set_clip_text(draft_id: str, name: str, text: str) -> dict:
    """Save a user-corrected transcript for one clip."""
    text = " ".join((text or "").split())
    if len(text) > MAX_TEXT:
        raise ValueError(f"Transcript too long (max {MAX_TEXT} characters)")
    d = get(draft_id)
    for c in d.get("clips", []):
        if c["name"] == name:
            c["text"], c["edited"] = text, True
            break
    else:
        raise KeyError(f"Clip '{name}' not in draft")
    d.pop("total_seconds", None)
    d.pop("clean_seconds", None)
    _save(d)
    return get(draft_id)


# ---- Details, preview and save
PREVIEW_TEXT = {"en": "Hello! This is a preview of my new voice. I hope it sounds just like me.",
                "es": "¡Hola! Esta es una vista previa de mi nueva voz. Espero que suene igual que yo."}
MAX_PREVIEW_CHARS = 300


def _clips_key(d: dict) -> str:
    return hashlib.sha1("|".join(c["hash"] for c in d.get("clips", [])).encode()).hexdigest()[:16]


def _engine(engine: str | None) -> str:
    from . import voices
    from .engines import ENGINES

    engine = engine or voices.DEFAULT_CLONE_ENGINE
    if engine not in ENGINES or not ENGINES[engine].supports_cloning:
        raise ValueError(f"Engine '{engine}' cannot clone voices")
    return engine


def as_voice(draft_id: str, engine: str | None = None) -> dict:
    """The draft's clean clips as a temporary voice (for previews)."""
    d = get(draft_id)
    if not d.get("clips"):
        raise ValueError("No clean clips yet. Add samples first.")
    return {"id": f"draft-{draft_id}", "name": "Preview", "kind": "cloned", "engine": _engine(engine),
            "dir": str(_dir(draft_id)), "language": d.get("language") or "en",
            "samples": [f"clips/{c['name']}" for c in d["clips"]],
            "transcripts": {f"clips/{c['name']}": c["text"] for c in d["clips"] if c.get("text")}}


def preview(draft_id: str, text: str = "", language: str = "", engine: str | None = None) -> Path:
    """Speak a short text with the draft voice → <draft>/preview.wav."""
    from . import tts

    v = as_voice(draft_id, engine)
    language = language or v["language"]
    if language not in ("en", "es"):
        raise ValueError("language must be en or es")
    text = " ".join((text or "").split()) or PREVIEW_TEXT[language]
    if len(text) > MAX_PREVIEW_CHARS:
        raise ValueError(f"Preview text too long (max {MAX_PREVIEW_CHARS} characters)")
    a = tts.speak(text, v, language)
    path = _dir(draft_id) / "preview.wav"
    audio.write_wav(a, path)
    d = get(draft_id)
    d["preview"] = {"clips": _clips_key(d), "engine": v["engine"], "language": language, "text": text}
    d.pop("total_seconds", None)
    d.pop("clean_seconds", None)
    _save(d)
    return path


def preview_path(draft_id: str) -> Path:
    p = _dir(draft_id) / "preview.wav"
    if not p.is_file():
        raise KeyError("No preview yet")
    return p


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


def save(draft_id: str, name: str, language: str, description: str = "", tags=(), consent: bool = False,
         engine: str | None = None) -> dict:
    """Turn the draft into a My Voices entry: clean clips → samples, transcripts, preview (if current)."""
    from . import voices

    if consent is not True:
        raise ValueError("Confirm that this is your voice or that you have permission to clone it")
    name = " ".join((name or "").split())
    if not name or len(name) > 80:
        raise ValueError("Name is required (max 80 characters)")
    if language not in ("en", "es"):
        raise ValueError("language must be en or es")
    description = (description or "").strip()
    if len(description) > 500:
        raise ValueError("Description too long (max 500 characters)")
    tags = _tags(tags)
    v = as_voice(draft_id, engine)
    d = get(draft_id)
    voice = voices.create(name, kind="cloned", sample_files=[_dir(draft_id) / s for s in v["samples"]],
                          engine=v["engine"], language=language, description=description, tags=tags,
                          consent={"confirmed": True, "at": time.time()})
    voice["transcripts"] = {s: c["text"] for s, c in zip(voice["samples"], d["clips"]) if c.get("text")}
    p = _dir(draft_id) / "preview.wav"
    if p.is_file() and d.get("preview", {}).get("clips") == _clips_key(d):
        shutil.copyfile(p, Path(voice["dir"]) / "preview.wav")
        voice["preview"] = "preview.wav"
    voice = voices.save(voice)
    d["saved_voice"] = voice["id"]
    d.pop("total_seconds", None)
    d.pop("clean_seconds", None)
    _save(d)
    return voice
