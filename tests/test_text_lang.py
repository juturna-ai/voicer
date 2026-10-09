from voicer.text.lang import detect
from voicer.text.split import split_sentences


def test_split_basic():
    s = split_sentences("Hola, ¿cómo estás? Muy bien. Hello there! The Dr. Smith arrived. ¡Qué bueno!")
    assert s == ["Hola, ¿cómo estás?", "Muy bien.", "Hello there!", "The Dr. Smith arrived.", "¡Qué bueno!"]


def test_split_newlines_and_decimals():
    assert split_sentences("Costs 3.5 dollars.\nNext line") == ["Costs 3.5 dollars.", "Next line"]


def test_detect():
    assert detect("Hola, ¿cómo estás?") == "es"
    assert detect("Buenos días a todos los presentes") == "es"
    assert detect("Good morning to all of you.") == "en"
    assert detect("The weather is nice today") == "en"
    assert detect("OK", default="es") == "es"
    assert detect("Mañana") == "es"


def test_plan_auto_and_override():
    from voicer.tts import plan

    text = "Hola, ¿cómo estás? I am fine, thank you. Nos vemos mañana."
    assert [s.lang for s in plan(text)] == ["es", "en", "es"]
    assert [s.lang for s in plan(text, "en")] == ["en", "en", "en"]
    import pytest
    with pytest.raises(ValueError):
        plan(text, "fr")


def test_speak_mixed_calls_engine_per_language(monkeypatch):
    import numpy as np
    from voicer import tts
    from voicer.engines.base import Audio

    calls = []
    monkeypatch.setattr(tts, "synthesize", lambda t, v, lang, **k: calls.append((t, lang)) or Audio(np.ones(100, np.float32), 1000))
    out = tts.speak("Hola amigos. Good morning everyone.", {"id": "x", "engine": "kokoro", "language": "es"})
    assert calls == [("Hola amigos.", "es"), ("Good morning everyone.", "en")]
    assert len(out.samples) == 200 + int(1000 * 0.35)  # pause after a "."
