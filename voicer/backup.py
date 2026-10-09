"""Backup: export My Voices (samples, model caches/embeddings, voice settings, preview) and the pronunciation
dictionary as one zip, to move them to another PC or VPS.

Zip layout: `voicer-backup.json` (manifest), `voices/<id>/...` (the whole voice folder), `dictionary.json`.
The API key and other app settings are never exported."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

from . import __version__, config, dictionary, settings, voices

FORMAT = "voicer-backup"
VERSION = 1
MANIFEST = "voicer-backup.json"
# Already compressed: store as is (faster, same size).
_STORED = {".mp3", ".ogg", ".opus", ".m4a", ".aac", ".flac", ".zip", ".npz", ".gz"}


def _voice_files(d: Path) -> list[Path]:
    """Regular files of a voice folder (no links, no half-written temp files)."""
    return sorted(p for p in d.rglob("*")
                  if p.is_file() and not p.is_symlink() and not p.name.endswith(".tmp") and not p.name.startswith("."))


def export(voice_ids: list[str] | None = None, include_dictionary: bool = True, dest: Path | None = None) -> Path:
    """Write the backup zip and return its path. `voice_ids` (My Voices IDs) None = all voices. Unknown ID → KeyError.
    The caller deletes the file when done (it is a temp file unless `dest` is given)."""
    picked = [voices.get(v) for v in dict.fromkeys(voice_ids)] if voice_ids else (
        voices.all_voices() if config.VOICES_DIR.is_dir() else [])
    if dest is None:
        fd, name = tempfile.mkstemp(prefix="voicer-export-", suffix=".zip")
        os.close(fd)
        dest = Path(name)
    default = settings.load().get("default_voice")
    manifest = {"format": FORMAT, "version": VERSION, "app_version": __version__,
                "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "voices": [], "dictionary": False,
                "default_voice": default if any(v["id"] == default for v in picked) else None}
    try:
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for v in picked:
                d = Path(v["dir"])
                files = _voice_files(d)
                for p in files:
                    rel = p.relative_to(d).as_posix()
                    z.write(p, f"voices/{v['id']}/{rel}",
                            zipfile.ZIP_STORED if p.suffix.lower() in _STORED else zipfile.ZIP_DEFLATED)
                manifest["voices"].append({"id": v["id"], "name": v.get("name"), "kind": v.get("kind"),
                                           "engine": v.get("engine"), "files": len(files)})
            if include_dictionary:
                words = dictionary.load()
                z.writestr("dictionary.json", json.dumps(words, indent=2, ensure_ascii=False, sort_keys=True))
                manifest["dictionary"] = True
                manifest["dictionary_entries"] = sum(len(w) for w in words.values())
            z.writestr(MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False))
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return dest


def file_name(voice_ids: list[str] | None) -> str:
    """Download name: `<voice-id>.voicer.zip` for one voice, else `voicer-backup-<date>.zip`."""
    if voice_ids and len(set(voice_ids)) == 1:
        return f"{voices.get(voice_ids[0])['id']}.voicer.zip"
    return f"voicer-backup-{time.strftime('%Y%m%d-%H%M')}.zip"


# ---- Import

MAX_FILES = 20_000
MAX_TOTAL_BYTES = 20 * 1024**3               # 20 GB unpacked: far above any real backup, stops a "zip bomb"
MAX_RATIO = 500                              # a big file (>10 MB) may not unpack to more than 500× its packed size
_SAFE_PART = re.compile(r"[A-Za-z0-9._ ()+-][A-Za-z0-9._ ()+-]{0,199}")


def _safe_rel(rel: str) -> bool:
    """A plain relative path inside the voice folder: no `..`, no absolute path, no drive, no backslash."""
    parts = rel.split("/")
    return bool(parts) and all(_SAFE_PART.fullmatch(p) and p not in (".", "..") for p in parts)


def _bad(msg: str) -> ValueError:
    return ValueError(f"This is not a valid Voice Studio backup: {msg}")


def _read_manifest(z: zipfile.ZipFile) -> dict:
    try:
        m = json.loads(z.read(MANIFEST))
    except KeyError:
        raise _bad("the voicer-backup.json file is missing") from None
    except ValueError:
        raise _bad("voicer-backup.json is damaged") from None
    if not isinstance(m, dict) or m.get("format") != FORMAT:
        raise _bad("wrong format")
    if not isinstance(m.get("version"), int) or m["version"] > VERSION:
        raise ValueError("This backup was made by a newer Voice Studio. Update Voice Studio, then import it again.")
    return m


def _plan(z: zipfile.ZipFile) -> dict[str, list[tuple[zipfile.ZipInfo, str]]]:
    """Check every entry before anything is written. Returns {zip voice id: [(entry, path in voice folder)]}."""
    infos = z.infolist()
    if len(infos) > MAX_FILES:
        raise _bad("too many files")
    total = 0
    plan: dict[str, list] = {}
    for i in infos:
        if i.is_dir() or i.filename in (MANIFEST, "dictionary.json"):
            continue
        name = i.filename
        if not name.startswith("voices/") or "\\" in name or (i.external_attr >> 16) & 0o170000 == 0o120000:
            raise _bad(f"unexpected file '{name[:80]}'")
        _, vid, *rest = name.split("/", 2) + [""]
        rel = rest[0]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", vid) or not _safe_rel(rel):
            raise _bad(f"unsafe file path '{name[:80]}'")
        if i.file_size > MAX_RATIO * max(i.compress_size, 1) and i.file_size > 10 * 1024**2:
            raise _bad(f"'{name[:80]}' unpacks to an unsafe size")
        total += i.file_size
        plan.setdefault(vid, []).append((i, rel))
    if total > MAX_TOTAL_BYTES:
        raise _bad("it unpacks to more than 20 GB")
    free = shutil.disk_usage(config.VOICES_DIR).free
    if total + 200 * 1024**2 > free:
        raise ValueError(f"Not enough free disk space: the backup needs {total / 1024**3:.1f} GB.")
    return plan


def _copy(z: zipfile.ZipFile, info: zipfile.ZipInfo, dest: Path) -> None:
    """Unpack one entry; never write more bytes than the entry says (the CRC check catches a lying header)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    left = info.file_size
    with z.open(info) as src, open(dest, "wb") as out:
        while chunk := src.read(1024 * 1024):
            left -= len(chunk)
            if left < 0:
                raise _bad(f"'{info.filename[:80]}' is larger than it says")
            out.write(chunk)


def _clean_voice(meta: dict, new_id: str, files: set[str]) -> dict:
    """voice.json from the backup → safe to save here: known fields only, file references inside the folder."""
    v = {k: meta[k] for k in voices.FIELDS if k in meta}
    v.update(id=new_id, created_at=meta.get("created_at") if isinstance(meta.get("created_at"), (int, float)) else time.time())
    if not isinstance(v.get("name"), str) or not v["name"].strip():
        v["name"] = new_id
    v["name"] = " ".join(v["name"].split())[:80]
    v["samples"] = [s for s in v.get("samples") or [] if isinstance(s, str) and s in files]
    for key in ("preview",):
        if v.get(key) is not None and not (isinstance(v[key], str) and v[key] in files):
            v.pop(key)
    if not isinstance(v.get("tags"), list):
        v["tags"] = []
    if not isinstance(v.get("settings"), dict):
        v["settings"] = {}
    return v


def _merge_dictionary(z: zipfile.ZipFile) -> tuple[int, int]:
    """Add the backup's words. A word you already have keeps your spoken form. Returns (added, kept)."""
    try:
        data = json.loads(z.read("dictionary.json"))
    except KeyError:
        return 0, 0
    except ValueError:
        raise _bad("dictionary.json is damaged") from None
    if not isinstance(data, dict):
        raise _bad("dictionary.json is damaged")
    have = dictionary.load()
    added = kept = 0
    for lang in dictionary.LANGS:
        known = {w.lower() for w in have[lang]}
        for word, spoken in (data.get(lang) or {}).items() if isinstance(data.get(lang), dict) else ():
            if not (isinstance(word, str) and isinstance(spoken, str) and word.strip() and spoken.strip()):
                continue
            word, spoken = word.strip(), spoken.strip()
            if len(word) > dictionary.MAX_WORD or len(spoken) > dictionary.MAX_SPOKEN:
                continue                                      # too long to be a real entry (never cut: it would change it)
            if word.lower() in known:
                kept += 1
            else:
                have[lang][word] = spoken
                known.add(word.lower())
                added += 1
    if added:
        dictionary._save(have)
    return added, kept


def import_zip(src) -> dict:
    """Import a backup zip (path or open binary file). Never overwrites: a voice whose ID is already here is added
    as a new voice "<name> (imported)". Dictionary words are added; your own words win. The default voice is set
    only if you have none. Everything is checked first; a bad zip changes nothing."""
    try:
        z = zipfile.ZipFile(src)
    except (zipfile.BadZipFile, OSError):
        raise _bad("not a zip file") from None
    with z:
        manifest = _read_manifest(z)
        plan = _plan(z)
        for vid, entries in plan.items():
            if "voice.json" not in {rel for _, rel in entries}:
                raise _bad(f"voice '{vid}' has no voice.json")
        metas = {}
        for vid in plan:
            try:
                metas[vid] = json.loads(z.read(f"voices/{vid}/voice.json"))
            except ValueError:
                raise _bad(f"voice '{vid}' has a damaged voice.json") from None
            if not isinstance(metas[vid], dict):
                raise _bad(f"voice '{vid}' has a damaged voice.json")

        stage = Path(tempfile.mkdtemp(prefix=".import-", dir=config.VOICES_DIR))   # same disk: the final move is a rename
        done: list[Path] = []
        result = {"voices": [], "dictionary_added": 0, "dictionary_kept": 0, "default_voice": None}
        try:
            for vid, entries in plan.items():
                tmp = stage / vid
                for info, rel in entries:
                    if rel != "voice.json":
                        _copy(z, info, tmp / rel)
                files = {rel for _, rel in entries}
                meta = metas[vid]
                new_id, name = vid, meta.get("name")
                if (config.VOICES_DIR / vid).exists():
                    v0 = _clean_voice(meta, vid, files)
                    name = f"{v0['name']} (imported)"[:80]
                    new_id = f"{voices._slug(name)}-{uuid.uuid4().hex[:6]}"
                v = _clean_voice({**meta, **({"name": name} if new_id != vid else {})}, new_id, files)
                if new_id != vid:
                    v["imported_from"] = vid
                tmp.mkdir(parents=True, exist_ok=True)
                (tmp / "voice.json").write_text(json.dumps(v, indent=2, ensure_ascii=False))
                dest = voices._path(new_id)
                tmp.rename(dest)
                done.append(dest)
                result["voices"].append({"id": new_id, "name": v["name"], "from_id": vid, "renamed": new_id != vid})
            result["dictionary_added"], result["dictionary_kept"] = _merge_dictionary(z)
        except BaseException:
            for d in done:                                    # all or nothing: remove the voices this import added
                shutil.rmtree(d, ignore_errors=True)
            raise
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    ids = {x["from_id"]: x["id"] for x in result["voices"]}
    if manifest.get("default_voice") in ids and voices.default_id() is None:
        result["default_voice"] = voices.set_default(ids[manifest["default_voice"]])
    return result
