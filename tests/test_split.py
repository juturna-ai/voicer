import numpy as np
import pytest

from voicer.engines.base import Audio
from voicer.text.split import PAUSE, chunk, split_paragraphs


def test_pauses_by_punctuation_and_paragraph():
    out = split_paragraphs("Hola. ¿Qué tal?\nBien!\n\nNuevo párrafo, aquí")
    assert out == [("Hola.", PAUSE["."]), ("¿Qué tal?", PAUSE["line"]), ("Bien!", PAUSE["paragraph"]),
                   ("Nuevo párrafo, aquí", PAUSE["default"])]


def test_chunk_never_cuts_words():
    words = ("palabra " * 120).strip()
    pieces = chunk(words, 100)
    assert all(len(p) <= 100 for p, _ in pieces)
    assert " ".join(p for p, _ in pieces) == words           # nothing lost, no word split
    assert pieces[-1][1] == 0.0


def test_chunk_prefers_clause_boundaries():
    s = "Primero vamos al mercado a comprar frutas y verduras, luego pasamos al banco; después comemos en casa."
    pieces = chunk(s, 60)
    assert pieces[0][0].endswith(",") and pieces[0][1] == PAUSE[","]
    assert all(len(p) <= 60 for p, _ in pieces)


def test_chunk_giant_word_kept_whole():
    assert chunk("x" * 50 + " end", 10) == [("x" * 50, PAUSE["word"]), ("end", 0.0)]


def test_plan_long_text_and_join(monkeypatch):
    from voicer import tts

    text = ("Esta es una oración muy larga que sigue y sigue, con muchas palabras para superar el límite, "
            "y todavía continúa un poco más para estar seguros de que se divide bien. Fin.")
    segs = tts.plan(text, "es", max_chars=60)
    assert len(segs) > 2 and all(len(s.text) <= 60 for s in segs)
    calls = []
    from voicer.engines.kokoro import KokoroEngine
    monkeypatch.setattr(KokoroEngine, "max_chars", 60)
    monkeypatch.setattr(tts, "synthesize", lambda t, v, lang, **k: calls.append(t) or Audio(np.ones(1000, np.float32) * 0.5, 1000))
    out = tts.speak(text, {"id": "x", "engine": "kokoro"}, "es")
    assert calls == [s.text for s in segs]
    expected = 1000 * len(segs) + sum(int(1000 * s.pause) for s in segs[:-1])
    assert len(out.samples) == expected


def test_trim_keeps_margin():
    from voicer.tts import trim

    sr = 1000
    x = np.zeros(3000, np.float32); x[1000:2000] = 0.5
    t = trim(Audio(x, sr))
    assert len(t.samples) == 1000 + 2 * 50  # 50 ms margin each side
