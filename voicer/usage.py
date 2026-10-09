"""Usage stats: one line per clip saved to History in data/usage.jsonl (kept when History is cleared), with who
asked for it. `summary()` adds them up: clips (requests), characters and audio minutes per voice, per agent and
per API key / device, and per day."""
from __future__ import annotations

import contextvars
import json
import re
import threading
import time
from collections import defaultdict

from . import apikey, config

THIS_PC = "This PC"
NO_KEY = "No key (key off)"
_caller: contextvars.ContextVar[dict] = contextvars.ContextVar("voicer_caller", default={})
_lock = threading.Lock()


def _path():
    return config.DATA_DIR / "usage.jsonl"


def _clean(s: str | None) -> str:
    """Printable, short: header values come from the client."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", s or "").strip()[:60]


def agent_from(headers) -> str:
    """The calling app: `X-Voicer-Agent` header if sent, else the first word of User-Agent
    (`curl/8.5` → `curl`; any browser → `Web browser`)."""
    name = _clean(headers.get("x-voicer-agent"))
    if name:
        return name
    ua = (headers.get("user-agent") or "").strip()
    if ua.startswith("Mozilla/"):
        return "Web browser"
    return _clean(ua.split()[0].split("/")[0]) if ua else "Unknown"


def key_label(client_host: str | None, headers, sent: str | None = None) -> str:
    """Which key or device a request counts under: the key hint (`vs_…abcd`), this PC, or no key."""
    sent = sent or apikey.from_headers(headers)
    if sent and apikey.valid(sent):
        return apikey.status()["hint"] or "API key"
    return THIS_PC if apikey.is_local(client_host, headers) else NO_KEY


def set_caller(channel: str, agent: str, key: str) -> contextvars.Token:
    """Remember who is asking for the rest of this request (threads started from it inherit it)."""
    return _caller.set({"channel": channel, "agent": _clean(agent) or "Unknown", "key": key})


def caller() -> dict:
    return _caller.get()


def record(entry: dict, settings: dict | None = None) -> None:
    """Log one clip. Never fails the generation: a full disk loses a stats line, not the clip."""
    who = caller()
    settings = settings or {}
    kind = "dialogue" if "dialogue" in settings else "voice-changer" if entry.get("engine") == "openvoice" else "tts"
    row = {
        "t": round(time.time(), 3),
        "id": entry["id"],
        "kind": kind,
        "voice_id": "dialogue" if kind == "dialogue" else entry.get("voice_id"),
        "voice": "Dialogue (several voices)" if kind == "dialogue" else entry.get("voice_name"),
        "chars": 0 if kind == "voice-changer" else len(entry.get("text") or ""),
        "seconds": entry.get("seconds") or 0,
        "channel": who.get("channel", "internal"),
        "agent": who.get("agent", "Voice Studio"),
        "key": who.get("key", THIS_PC),
    }
    try:
        with _lock, open(_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def rows(since: float = 0) -> list[dict]:
    try:
        lines = _path().read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    out = []
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:                               # a half-written last line after a crash
            continue
        if r.get("t", 0) >= since:
            out.append(r)
    return out


def _group(rs: list[dict], key) -> list[dict]:
    acc: dict = defaultdict(lambda: {"requests": 0, "characters": 0, "seconds": 0.0})
    for r in rs:
        a = acc[key(r)]
        a["requests"] += 1
        a["characters"] += r.get("chars", 0)
        a["seconds"] += r.get("seconds", 0)
    return [{"name": k, **v, "seconds": round(v["seconds"], 2), "minutes": round(v["seconds"] / 60, 2)}
            for k, v in sorted(acc.items(), key=lambda kv: (-kv[1]["requests"], str(kv[0])))]


def summary(days: int | None = 30) -> dict:
    """Totals and breakdowns for the last `days` days (None or 0 = all time)."""
    if days is not None and days < 0:
        raise ValueError("days must be 0 (all time) or more")
    since = time.time() - days * 86400 if days else 0
    rs = rows(since)
    total = _group(rs, lambda r: "all")
    total = total[0] if total else {"requests": 0, "characters": 0, "seconds": 0.0, "minutes": 0.0}
    total.pop("name", None)
    by_voice = _group(rs, lambda r: (r.get("voice_id"), r.get("voice")))
    for v in by_voice:
        v["voice_id"], v["name"] = v["name"]
    return {
        "days": days or None,
        "since": time.strftime("%Y-%m-%d", time.localtime(since)) if since else None,
        "totals": total,
        "by_voice": by_voice,
        "by_agent": _group(rs, lambda r: r.get("agent") or "Unknown"),
        "by_key": _group(rs, lambda r: r.get("key") or THIS_PC),
        "by_channel": _group(rs, lambda r: r.get("channel") or "internal"),
        "by_day": sorted(_group(rs, lambda r: time.strftime("%Y-%m-%d", time.localtime(r["t"]))), key=lambda d: d["name"]),
    }
