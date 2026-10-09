import numpy as np
import pytest

from voicer.engines.base import Audio

LINES = ["The library opens at nine and closes late on Thursdays.",
         "Please return borrowed books before the end of the month.",
         "New readers can sign up at the front desk with a photo card.",
         "Quiet study rooms are on the second floor, next to the stairs."]


@pytest.fixture(scope="module")
def speech():
    """Clean real speech (Piper), 22.05 kHz, with short pauses; repeated to the length asked."""
    from voicer import tts

    cache = {}

    def make(seconds):
        if "base" not in cache:
            parts = []
            for s in LINES:
                parts += [tts.synthesize(s, "piper-en-us-lessac-medium", "en").samples, np.zeros(8000, np.float32)]
            cache["base"] = 0.5 * np.concatenate(parts) / np.abs(np.concatenate(parts)).max()
        b = cache["base"]
        reps = int(np.ceil(seconds * 22050 / len(b)))
        return np.tile(b, reps)[: int(seconds * 22050)].astype(np.float32)

    return make


def run(y):
    from voicer import cleanup

    a = Audio(y, 22050)
    m = cleanup.measure(a)
    clips = cleanup.split(cleanup.clean(a))
    return m, cleanup.quality([{"name": "s.wav", **m}], sum(len(c.samples) / c.sr for c in clips))


def test_good_sample(speech):
    m, q = run(speech(80))
    assert m["snr_db"] > 35 and m["clipping"] == 0
    assert q["level"] == "good" and q["score"] >= 75 and not q["warnings"], q


def test_short_sample_warns(speech):
    _, q = run(speech(12))
    assert q["level"] == "poor" and q["score"] < 40
    assert any("at least 20 s" in w for w in q["warnings"])


def test_noisy_sample_warns(speech):
    y = speech(80)
    y = y + 0.03 * np.random.default_rng(1).standard_normal(len(y)).astype(np.float32)
    m, q = run(y)
    assert m["snr_db"] < 20
    assert any("background noise" in w for w in q["warnings"]) and q["level"] != "good"


def test_clipped_sample_warns(speech):
    y = np.clip(speech(80) * 6, -1, 1)
    _, q = run(y)
    assert any("clipping" in w for w in q["warnings"])


def test_api_returns_quality(speech, tmp_path):
    import soundfile as sf
    from fastapi.testclient import TestClient

    from voicer.server import app

    p = tmp_path / "s.wav"
    sf.write(p, speech(15), 22050)
    with TestClient(app) as c:
        d = c.post("/api/clone/drafts").json()
        c.post(f"/api/clone/drafts/{d['id']}/files", files=[("files", ("s.wav", p.read_bytes(), "audio/wav"))])
        q = c.post(f"/api/clone/drafts/{d['id']}/process").json()["quality"]
        assert q["level"] == "poor" and q["warnings"]
