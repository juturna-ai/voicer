import numpy as np
import pytest

from voicer.engines.base import Audio

STYLE = {"warm", "narrator", "news", "conversational", "energetic", "calm"}


def test_every_library_voice_has_full_metadata():
    from voicer import library

    for v in library.catalog():
        for k in ("name", "language", "accent", "gender", "age", "engine", "license", "source_url"):
            assert v.get(k), (v["id"], k)
        assert isinstance(v["commercial"], bool), v["id"]
        assert v["gender"] in ("female", "male", "neutral"), v["id"]
        assert v["age"] in ("young adult", "adult", "middle-aged", "senior"), v["id"]
        assert set(v["tags"]) & STYLE, v["id"]
        assert set(v.get("estimated", [])) <= {"gender", "age", "tags"}
    assert library.search(gender="female", language="es") and library.search(gender="male", language="es")
    assert library.search(style="narrator") and library.search(commercial=True) and library.search(commercial=False)


def _vowel(f0: float, sr: int = 16000, secs: float = 2.0) -> Audio:
    t = np.arange(int(sr * secs)) / sr
    vib = f0 * (1 + 0.03 * np.sin(2 * np.pi * 5 * t))           # small pitch movement
    phase = 2 * np.pi * np.cumsum(vib) / sr
    y = sum(np.sin(k * phase) / k for k in range(1, 12))
    return Audio((0.3 * y / np.abs(y).max()).astype(np.float32), sr)


def test_features_measure_pitch():
    from voicer import analysis

    lo = analysis.features(_vowel(110), "x" * 30)
    hi = analysis.features(_vowel(220), "x" * 30)
    assert 100 < lo["f0"] < 120 and 200 < hi["f0"] < 240
    assert lo["rate"] > 0 and lo["pitch_var"] > 0


def test_gender_age_and_style_rules():
    from voicer import analysis

    assert analysis.gender({"f0": 110, "f3": 2500}) == "male"
    assert analysis.gender({"f0": 210, "f3": 2800}) == "female"
    assert analysis.gender({"f0": 150, "f3": 2900}) == "female"   # low pitch, short vocal tract
    assert analysis.gender({"f0": 150, "f3": 2450}) == "male"
    assert analysis.age({"f0": 240}, "female") == "young adult"
    peers = [{"rate": r, "pitch_var": p, "brightness": b} for r, p, b in
             [(10, 1, 1000), (12, 2, 1200), (14, 3, 1400), (16, 4, 1600), (18, 5, 1800)]]
    assert "energetic" in analysis.style_tags(peers[-1], peers)
    assert "calm" in analysis.style_tags(peers[0], peers)
    assert "warm" in analysis.style_tags(peers[0], peers)
    for p in peers:
        assert set(analysis.style_tags(p, peers)) <= set(analysis.STYLE_TAGS)


@pytest.mark.gpu
def test_gender_estimate_on_real_voices():
    from voicer import analysis, tts

    text = "Good morning, and welcome. Today we will take a short walk through the old town."
    for vid, want in (("kokoro-af-heart", "female"), ("kokoro-am-michael", "male")):
        f = analysis.features(tts.trim(tts.synthesize(text, vid, "en")), text)
        assert analysis.gender(f) == want, (vid, f)
