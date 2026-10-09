"""Inline text tags: [pause 0.5s] [pause 1s] [slow] [fast] [whisper] [happy] [sad] [excited] [normal].

Style tags apply to the text after them until the next style tag or [normal].
Unknown tags are removed, never spoken."""
from __future__ import annotations

import re
from dataclasses import dataclass

STYLES = ("slow", "fast", "whisper", "happy", "sad", "excited")
TAG = re.compile(r"\[\s*([a-zA-Z]+)(?:\s+([0-9]*\.?[0-9]+)\s*(ms|s)?)?\s*\]")
MAX_PAUSE = 10.0


@dataclass
class Item:
    kind: str           # "text" | "pause"
    text: str = ""
    style: str | None = None
    seconds: float = 0.0


def parse(text: str) -> list[Item]:
    items: list[Item] = []
    style = None
    pos = 0

    def add_text(t: str):
        t = re.sub(r"\[[^\]]*\]", " ", t)  # any leftover bracket tag is dropped, never spoken
        if t.strip():
            items.append(Item("text", t, style))

    for m in TAG.finditer(text):
        add_text(text[pos:m.start()])
        pos = m.end()
        name, num, unit = m.group(1).lower(), m.group(2), (m.group(3) or "s").lower()
        if name in ("pause", "break") and num:
            secs = float(num) / (1000 if unit == "ms" else 1)
            items.append(Item("pause", seconds=min(secs, MAX_PAUSE)))
        elif name in STYLES:
            style = name
        elif name == "normal":
            style = None
        # anything else: ignored
    add_text(text[pos:])
    return items


def strip(text: str) -> str:
    """Text with every tag removed (for subtitles, character counts, etc.)."""
    return re.sub(r"\s{2,}", " ", re.sub(r"\[[^\]]*\]", " ", text)).strip()
