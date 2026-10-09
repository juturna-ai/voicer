"""App settings kept in data/settings.json (e.g. the default voice). Missing or broken file → defaults."""
from __future__ import annotations

import json
import os
import secrets
import threading

from . import config

DEFAULTS = {"default_voice": None}
_lock = threading.Lock()


def _path():
    return config.DATA_DIR / "settings.json"


def load() -> dict:
    try:
        data = json.loads(_path().read_text())
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **(data if isinstance(data, dict) else {})}


def update(**values) -> dict:
    with _lock:
        data = {**load(), **values}
        tmp = _path().with_name(f".settings.{secrets.token_hex(4)}.json")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
        os.replace(tmp, _path())
        return data
