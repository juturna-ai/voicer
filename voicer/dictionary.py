"""Pronunciation dictionary: word -> spoken form, per language. Stored in data/dictionary.json."""
from __future__ import annotations

import csv
import io
import json
import re
import threading

from . import config

LANGS = ("es", "en")
MAX_WORD = 100                   # characters
MAX_SPOKEN = 300
MAX_ENTRIES = 5000               # per language
LISTEN_VOICE = {"es": "kokoro-ef-dora", "en": "kokoro-af-heart"}   # when no default voice is set (fast, small)
_lock = threading.Lock()
_cache: dict | None = None


def _file():
    return config.DATA_DIR / "dictionary.json"


def load() -> dict[str, dict[str, str]]:
    global _cache
    with _lock:
        if _cache is None:
            f = _file()
            data = json.loads(f.read_text()) if f.exists() else {}
            _cache = {lang: dict(data.get(lang, {})) for lang in LANGS}
        return {lang: dict(v) for lang, v in _cache.items()}


def _save(data: dict) -> None:
    global _cache
    with _lock:
        tmp = _file().with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True))
        tmp.replace(_file())
        _cache = data


def _check(lang: str, word: str, spoken: str | None = "x") -> None:
    if lang not in LANGS:
        raise ValueError("Language must be es or en")
    if not word.strip() or (spoken is not None and not spoken.strip()):
        raise ValueError("Word and spoken form must not be empty")
    if len(word.strip()) > MAX_WORD or (spoken is not None and len(spoken.strip()) > MAX_SPOKEN):
        raise ValueError(f"Too long: a word can have up to {MAX_WORD} characters, a spoken form up to {MAX_SPOKEN}")


def _put(entries: dict, word: str, spoken: str) -> None:
    """Add or change a word. Words match without case, so "whatsapp" replaces "WhatsApp" (no duplicates)."""
    for w in [w for w in entries if w.lower() == word.lower()]:
        del entries[w]
    if len(entries) >= MAX_ENTRIES:
        raise ValueError(f"The dictionary is full ({MAX_ENTRIES} words per language)")
    entries[word] = spoken


def set_entry(lang: str, word: str, spoken: str, old: str | None = None) -> None:
    """Add or change a word. `old`: the word it replaces (the word itself was edited)."""
    _check(lang, word, spoken)
    data = load()
    if old and old.strip().lower() != word.strip().lower():
        if not any(w.lower() == old.strip().lower() for w in data[lang]):
            raise KeyError(f"'{old}' not in {lang} dictionary")
        for w in [w for w in data[lang] if w.lower() == old.strip().lower()]:
            del data[lang][w]
    _put(data[lang], word.strip(), spoken.strip())
    _save(data)


def delete_entry(lang: str, word: str) -> None:
    _check(lang, word, None)
    data = load()
    if data[lang].pop(word.strip(), None) is None:
        raise KeyError(f"'{word}' not in {lang} dictionary")
    _save(data)


def apply(text: str, lang: str) -> str:
    """Replace whole words (case-insensitive), longest entries first."""
    entries = load().get(lang, {})
    if not entries:
        return text
    words = sorted(entries, key=len, reverse=True)
    lookup = {w.lower(): entries[w] for w in words}
    pattern = re.compile(r"(?<!\w)(" + "|".join(re.escape(w) for w in words) + r")(?!\w)", re.I)
    return pattern.sub(lambda m: lookup[m.group(1).lower()], text)


def export_csv() -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["language", "word", "spoken"])
    for lang, entries in load().items():
        for word, spoken in sorted(entries.items()):
            w.writerow([lang, word, spoken])
    return buf.getvalue()


def import_csv(text: str, replace: bool = False, allow_empty: bool = True) -> int:
    """Rows: language,word,spoken (header optional; `,` `;` or tab). All or nothing: a bad row → ValueError naming
    the row, and nothing changes. Returns number of entries imported."""
    text = text.lstrip("﻿")
    first = next((line for line in text.splitlines() if line.strip()), "")
    sep = max(",;\t", key=first.count)                  # Spanish Excel saves CSV with ";"
    data = {lang: {} for lang in LANGS} if replace else load()
    n = 0
    for i, row in enumerate(csv.reader(io.StringIO(text), delimiter=sep), 1):
        if not any(c.strip() for c in row) or (row and row[0].strip().lower() == "language"):
            continue
        if len(row) < 3:
            raise ValueError(f"Row {i}: needs 3 columns: language, word, spoken form")
        lang, word, spoken = (c.strip() for c in row[:3])
        try:
            _check(lang.lower(), word, spoken)
            _put(data[lang.lower()], word, spoken)
        except ValueError as e:
            raise ValueError(f"Row {i}: {e}") from None
        n += 1
    if not n and not allow_empty:
        raise ValueError("No words found. Each row needs: language, word, spoken form")
    _save(data)
    return n
