"""Sentence splitting for es/en that never cuts words."""
from __future__ import annotations

import re

ABBREV = {"sr", "sra", "srta", "dr", "dra", "lic", "ing", "prof", "etc", "mr", "mrs", "ms", "st", "vs",
          "no", "núm", "approx", "aprox", "ud", "uds", "av", "col", "jr", "sr", "inc", "ltd", "p.ej", "e.g", "i.e"}
# Sentence end: . ! ? … followed by space/quote and an upper-case letter, ¿, ¡, digit or end.
_END = re.compile(r"([.!?…]+[\"'”»)]*)(\s+)(?=[\"'“«(¿¡]?[A-ZÁÉÍÓÚÑ0-9¿¡])")


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text.strip())
    out = []
    for para in re.split(r"\n\s*\n|\n", text):
        para = para.strip()
        if not para:
            continue
        start = 0
        for m in _END.finditer(para):
            word = para[:m.start(1)].rsplit(" ", 1)[-1].lower().rstrip(".")
            if m.group(1) == "." and (word in ABBREV or (len(word) == 1 and word.isalpha())):
                continue  # "Dr. Pérez", "J. Smith"
            out.append(para[start:m.end(1)].strip())
            start = m.end()
        tail = para[start:].strip()
        if tail:
            out.append(tail)
    return out


# Pause (seconds) after a piece, by how it ends.
PAUSE = {"paragraph": 0.7, "line": 0.5, "?": 0.4, "!": 0.4, ".": 0.35, "…": 0.45,
         ";": 0.25, ":": 0.25, ",": 0.15, "—": 0.2, "word": 0.05, "default": 0.3}


def sentence_pause(sentence: str) -> float:
    end = sentence.rstrip("\"'”») ")[-1:] if sentence.strip() else ""
    return PAUSE.get(end, PAUSE["default"])


def split_paragraphs(text: str) -> list[tuple[str, float]]:
    """Sentences with the pause that follows each one (longer after a line or paragraph break)."""
    out: list[tuple[str, float]] = []
    blocks = re.split(r"(\n\s*\n|\n)", text.strip())
    for i in range(0, len(blocks), 2):
        sents = split_sentences(blocks[i])
        if not sents:
            continue
        brk = blocks[i + 1] if i + 1 < len(blocks) else ""
        for j, s in enumerate(sents):
            pause = sentence_pause(s)
            if j == len(sents) - 1 and brk:
                pause = max(pause, PAUSE["paragraph"] if brk.count("\n") > 1 else PAUSE["line"])
            out.append((s, pause))
    return out


def chunk(sentence: str, max_chars: int) -> list[tuple[str, float]]:
    """Split a long sentence at clause punctuation, else at a space. Never inside a word.
    Returns pieces with the pause that follows each piece (last piece gets 0)."""
    pieces: list[tuple[str, float]] = []
    rest = sentence.strip()
    while len(rest) > max_chars:
        window = rest[: max_chars + 1]
        cut = -1
        for marks in ((";", ":", "—"), (",",)):
            cut = max(window.rfind(m + " ") for m in marks)
            if cut > max_chars // 3:
                cut += 1
                break
            cut = -1
        if cut == -1:
            cut = window.rfind(" ")
            if cut <= 0:  # one giant "word" — cannot split without cutting it
                cut = len(rest.split(" ", 1)[0])
        head, rest = rest[:cut].strip(), rest[cut:].strip()
        end = head[-1:]
        pieces.append((head, PAUSE.get(end, PAUSE["word"])))
        if not rest:
            break
    if rest:
        pieces.append((rest, 0.0))
    return pieces
