"""Phase 5: speed / stability / expressiveness sliders, applied where the engine supports them."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from voicer.engines.base import slider

PIPER = "piper-en-us-lessac-medium"
TEXT = "The weather is nice today, so we will walk to the park."


@pytest.fixture(scope="module")
def client():
    from voicer.server import app

    return TestClient(app)


def test_slider_mapping():
    assert slider({}, "stability", 0.7, 1.0, 0.3) == 0.7                      # not set → engine default
    assert slider({"stability": 0.5}, "stability", 0.7, 1.0, 0.3) == pytest.approx(0.7)
    assert slider({"stability": 0.0}, "stability", 0.7, 1.0, 0.3) == pytest.approx(1.0)
    assert slider({"stability": 1.0}, "stability", 0.7, 1.0, 0.3) == pytest.approx(0.3)
    assert slider({"stability": 0.75}, "stability", 0.7, 1.0, 0.3) == pytest.approx(0.5)
    assert slider({"stability": 7}, "stability", 0.7, 1.0, 0.3) == pytest.approx(0.3)   # clamped


def test_xtts_maps_sliders_to_temperature_and_top_p(monkeypatch):
    import torch

    from voicer.engines.xtts import XTTSEngine

    seen = {}

    class FakeModel:
        def inference(self, text, lang, gpt, spk, **kw):
            seen.update(kw)
            return {"wav": torch.zeros(10)}

    eng = XTTSEngine()
    eng.model = FakeModel()
    monkeypatch.setattr(eng, "latents", lambda v: (None, None))
    eng.synthesize("hi", {}, "en", stability=1.0, expressiveness=0.0)
    assert seen["temperature"] == pytest.approx(0.3) and seen["top_p"] == pytest.approx(0.6)
    eng.synthesize("hi", {}, "en")
    assert seen["temperature"] == pytest.approx(0.7) and seen["top_p"] == pytest.approx(0.85)
    eng.synthesize("hi", {}, "en", stability=0.0, expressiveness=1.0, temperature=0.9)   # a style tag wins
    assert seen["temperature"] == pytest.approx(0.9) and seen["top_p"] == pytest.approx(1.0)


def _audio(client, **body):
    import io

    import soundfile as sf

    e = client.post("/api/tts", json={"text": TEXT, "voice": PIPER, "language": "en", **body})
    assert e.status_code == 200, e.text
    y, _ = sf.read(io.BytesIO(client.get(f"/api/history/{e.json()['id']}/audio").content))
    return e.json(), y


def test_piper_max_stability_is_repeatable_default_varies(client):
    e1, a = _audio(client, stability=1.0, expressiveness=0.0)
    _, b = _audio(client, stability=1.0, expressiveness=0.0)
    assert e1["settings"] == {"speed": 1.0, "stability": 1.0, "expressiveness": 0.0}
    assert len(a) == len(b) and np.abs(a - b).max() < 1e-3                     # no random variation
    _, c = _audio(client)
    _, d = _audio(client)
    assert len(c) != len(d) or np.abs(c - d).max() > 1e-2                      # default keeps natural variation


def test_piper_expressiveness_changes_timing(client):
    lens = {e: [len(_audio(client, expressiveness=e, stability=1.0)[1]) for _ in range(3)] for e in (0.0, 1.0)}
    assert len(set(lens[0.0])) == 1                                            # flat timing: same every time
    assert len(set(lens[1.0])) > 1                                             # lively timing: varies


def test_speed_slider_changes_length(client):
    _, slow = _audio(client, speed=0.6)
    _, fast = _audio(client, speed=1.6)
    assert len(slow) > 1.6 * len(fast)


def test_unsupported_controls_are_not_applied(client):
    vs = {v["id"]: v for v in client.get("/api/voices").json()}
    assert vs[PIPER]["controls"] == ["speed", "stability", "expressiveness"]
    assert vs["kokoro-af-heart"]["controls"] == ["speed"]
    e = client.post("/api/tts", json={"text": "Hello there.", "voice": "kokoro-af-heart", "stability": 0.9,
                                      "expressiveness": 0.1}).json()
    assert e["settings"] == {"speed": 1.0}


@pytest.mark.parametrize("field", ["stability", "expressiveness"])
def test_out_of_range_is_rejected(client, field):
    r = client.post("/api/tts", json={"text": "Hi.", "voice": PIPER, field: 1.5})
    assert r.status_code == 400 and "between 0 and 1" in r.json()["detail"]


@pytest.mark.gpu
def test_xtts_extremes_still_speak_clearly(client, tmp_path):
    from conftest import similar, transcribe

    for s, x in ((0.0, 1.0), (1.0, 0.0)):
        e = client.post("/api/tts", json={"text": TEXT, "voice": "xtts-daisy-studious", "language": "en",
                                          "stability": s, "expressiveness": x}).json()
        assert e["settings"]["stability"] == s, e
        p = tmp_path / f"x{s}.wav"
        p.write_bytes(client.get(f"/api/history/{e['id']}/audio").content)
        assert similar(transcribe(p, "en"), TEXT) > 0.75, (s, x)
