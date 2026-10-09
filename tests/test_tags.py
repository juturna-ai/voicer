import numpy as np
import pytest

from voicer.engines.base import Audio
from voicer.text.tags import parse, strip


def test_parse():
    items = parse("Hola [pause 0.5s] amigo. [slow] Despacio [pause 500ms][pause 1s] [normal] fin [foo] [whisper]shh")
    kinds = [(i.kind, i.text.strip(), i.style, i.seconds) for i in items]
    assert kinds == [
        ("text", "Hola", None, 0.0), ("pause", "", None, 0.5), ("text", "amigo.", None, 0.0),
        ("text", "Despacio", "slow", 0.0), ("pause", "", None, 0.5), ("pause", "", None, 1.0),
        ("text", "fin", None, 0.0), ("text", "shh", "whisper", 0.0),
    ]


def test_unknown_and_broken_tags_never_spoken():
    assert all("[" not in i.text for i in parse("Hi [laugh] there [pause] ok [ x ]"))
    assert strip("Hola [pause 1s] [happy]amigo") == "Hola amigo"


def _fake(monkeypatch, sr=1000):
    from voicer import tts
    calls = []

    def fake(t, v, lang, speed=1.0, engine=None, **o):
        calls.append((t, lang, round(speed, 3), o.get("temperature")))
        return Audio(np.full(sr, 0.5, np.float32), sr)
    monkeypatch.setattr(tts, "synthesize", fake)
    return calls


def test_pause_tags_exact_gaps(monkeypatch):
    from voicer import tts

    _fake(monkeypatch)
    out = tts.speak("[pause 1s] Uno. [pause 0.5s] Dos. [pause 0.5s][pause 1s] Tres.", {"id": "x", "engine": "piper"}, "es")
    # lead 1 s + 3 parts + 0.5 s gap + 1.5 s gap
    assert len(out.samples) == 1000 + 3000 + 500 + 1500
    assert np.all(out.samples[:1000] == 0)


def test_styles_map_to_engine_support(monkeypatch):
    from voicer import tts

    calls = _fake(monkeypatch)
    tts.speak("[slow] Uno. [fast] Dos. [sad] Tres. [normal] Cuatro.", {"id": "x", "engine": "piper"}, "es", speed=1.0)
    assert [c[2] for c in calls] == [0.8, 1.25, 0.88, 1.0]
    assert all(c[3] is None for c in calls)                 # piper has no temperature
    calls.clear()
    tts.speak("[excited] ¡Vamos!", {"id": "x", "engine": "xtts", "samples": ["a"]}, "es")
    assert calls[0][3] == 0.85                              # xtts gets expressiveness


def test_whisper_effect_removes_pitch():
    from voicer import effects

    sr = 16000
    t = np.arange(sr) / sr
    tone = Audio((0.5 * np.sin(2 * np.pi * 200 * t)).astype(np.float32), sr)
    w = effects.whisper(tone)
    spec = lambda x: np.abs(np.fft.rfft(x))
    # energy concentrated at 200 Hz for the tone, spread out for the whisper
    ratio = lambda x: spec(x)[195:206].sum() / spec(x).sum()
    assert ratio(tone.samples) > 0.5 and ratio(w.samples) < 0.2


@pytest.mark.gpu
def test_tags_real_audio(tmp_out):
    from conftest import similar, transcribe
    from voicer import audio, tts

    v = {"id": "k", "engine": "kokoro", "engine_voice": "af_heart", "language": "en"}
    plain = tts.speak("Hello there. How are you?", v, "en")
    tagged = tts.speak("Hello there. [pause 1s] [whisper] How are you? [excited] Great!", v, "en")
    assert len(tagged.samples) > len(plain.samples) + 0.6 * tagged.sr
    heard = transcribe(audio.write_wav(tagged, tmp_out / "tags.wav"), "en")
    assert "pause" not in heard.lower() and "whisper" not in heard.lower() and "excited" not in heard.lower()
    assert similar(heard, "Hello there. How are you? Great!") > 0.5, heard
