"""Optional daily auto-backup (off by default): once a day a backup zip of all My Voices + the dictionary
(`backup.export`) is written to a folder, and only the newest `keep` auto-backups are kept. Only files named
`voicer-auto-YYYYmmdd-HHMMSS.zip` are ever deleted. Settings live in settings.json: `auto_backup` (what you chose)
and `auto_backup_state` (last try, last success, last error)."""
from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path

from . import backup, config, settings

DEFAULT = {"enabled": False, "folder": "", "keep": 7}
EVERY = 24 * 3600                  # one backup a day
RETRY = 3600                       # after a failed try, wait an hour
CHECK = 600                        # the timer looks every 10 minutes
FIRST_CHECK = 60                   # first look one minute after start (never slows the start)
NAME = re.compile(r"voicer-auto-\d{8}-\d{6}\.zip")
_lock = threading.Lock()
_stop = threading.Event()
_thread: threading.Thread | None = None


def default_folder() -> Path:
    return config.DATA_DIR / "backups"


def to_path(folder: str) -> Path:
    """The folder you typed → a path on this machine. Empty = default. `C:\\Backups` works under WSL."""
    folder = (folder or "").strip().strip('"')
    if not folder:
        return default_folder()
    m = re.fullmatch(r"([A-Za-z]):[\\/](.*)", folder)
    if m:
        drive = Path("/mnt") / m[1].lower()
        if os.name == "nt" or not drive.is_dir():
            raise ValueError("Windows folders (C:\\…) work only when Voice Studio runs in WSL. Use a Linux path.")
        p = drive / m[2].replace("\\", "/")
    else:
        p = Path(folder).expanduser()
    if not p.is_absolute():
        raise ValueError("Use a full folder path, for example /home/me/voice-backups or C:\\Backups\\Voices.")
    p = Path(os.path.normpath(p))
    if p.resolve().is_relative_to(config.VOICES_DIR.resolve()):
        raise ValueError("The backup folder must not be inside the voices folder.")
    return p


def options() -> dict:
    saved = settings.load().get("auto_backup")
    out = dict(DEFAULT)
    if isinstance(saved, dict):
        out.update({k: saved[k] for k in DEFAULT if k in saved})
    return out


def _state() -> dict:
    s = settings.load().get("auto_backup_state")
    return s if isinstance(s, dict) else {}


def backups(folder: Path) -> list[Path]:
    """This app's auto-backups in the folder, oldest first."""
    try:
        return sorted(p for p in folder.iterdir() if NAME.fullmatch(p.name) and p.is_file())
    except OSError:
        return []


def status() -> dict:
    o, s = options(), _state()
    out = {**o, "path": None, "last": s.get("last_ok"), "last_file": s.get("last_file"), "last_error": s.get("last_error"),
           "last_try": s.get("last_try"), "next": None, "count": 0, "default_folder": str(default_folder())}
    try:
        p = to_path(o["folder"])
        out["path"] = str(p)
        out["count"] = len(backups(p))
    except ValueError as e:
        out["last_error"] = out["last_error"] or str(e)
    if o["enabled"]:
        out["next"] = max(time.time(), (s.get("last_ok") or 0) + EVERY, (s.get("last_try") or 0) + RETRY
                          if s.get("last_error") else 0)
    return out


def configure(enabled: bool, folder: str = "", keep: int = 7) -> dict:
    """Save your choice. When turned on, the folder is made if needed and must be writable."""
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be true or false")
    if isinstance(keep, bool) or not isinstance(keep, int) or not 1 <= keep <= 365:
        raise ValueError("Keep must be a whole number from 1 to 365")
    folder = (folder or "").strip()[:500]
    p = to_path(folder)
    if enabled:
        try:
            p.mkdir(parents=True, exist_ok=True)
            probe = p / f".voicer-write-test-{os.getpid()}"
            probe.write_bytes(b"")
            probe.unlink()
        except OSError:
            raise ValueError("Voice Studio cannot write to this folder. Choose another folder.") from None
    settings.update(auto_backup={"enabled": enabled, "folder": folder, "keep": keep})
    return status()


def run_now() -> dict:
    """Make one auto-backup now (also when turned off), then delete the oldest ones above `keep`."""
    with _lock:
        o = options()
        now = time.time()
        state = {**_state(), "last_try": now}
        try:
            folder = to_path(o["folder"])
            folder.mkdir(parents=True, exist_ok=True)
            name = f"voicer-auto-{time.strftime('%Y%m%d-%H%M%S', time.localtime(now))}.zip"
            part = folder / f".{name}.part"
            backup.export(dest=part)
            os.replace(part, folder / name)
            for old in backups(folder)[:-o["keep"]]:
                old.unlink(missing_ok=True)
        except (OSError, ValueError, KeyError) as e:
            msg = str(e) if isinstance(e, ValueError) else "Could not write the backup to the folder (disk full or no access)."
            settings.update(auto_backup_state={**state, "last_error": msg})
            raise ValueError(msg) from None
        settings.update(auto_backup_state={**state, "last_ok": now, "last_file": name, "last_error": None})
    return status()


def due(now: float | None = None) -> bool:
    o, s = options(), _state()
    now = now or time.time()
    if not o["enabled"] or now - (s.get("last_ok") or 0) < EVERY:
        return False
    return not s.get("last_error") or now - (s.get("last_try") or 0) >= RETRY


def tick() -> None:
    """One look of the timer: back up if a day has passed. Errors are kept for the Settings page."""
    if due():
        try:
            run_now()
        except ValueError:
            pass


def start() -> None:
    """Start the daily timer (one per process; the server's lifespan calls it)."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()

    def loop():
        wait = FIRST_CHECK
        while not _stop.wait(wait):
            tick()
            wait = CHECK

    _thread = threading.Thread(target=loop, daemon=True, name="auto-backup")
    _thread.start()


def stop() -> None:
    _stop.set()
