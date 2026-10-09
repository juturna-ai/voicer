"""Phase 4: name, language, description, tags; preview (real XTTS) before save."""
import json

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from conftest import similar, transcribe
from test_transcribe import EN, speech


@pytest.fixture()
def c():
    from voicer.server import app

    with TestClient(app) as client:
        yield client


def ready_draft(c, tmp_path, sentences=EN * 2):
    p = speech(tmp_path / "me.wav", sentences, "piper-en-us-lessac-medium", "en")
    d = c.post("/api/clone/drafts").json()
    c.post(f"/api/clone/drafts/{d['id']}/files", files=[("files", ("me.wav", p.read_bytes(), "audio/wav"))])
    c.post(f"/api/clone/drafts/{d['id']}/process")
    return c.post(f"/api/clone/drafts/{d['id']}/transcribe").json()


def test_save_validation(c, tmp_path):
    from voicer import clone

    empty = c.post("/api/clone/drafts").json()
    r = c.post(f"/api/clone/drafts/{empty['id']}/save", json={"name": "X", "language": "en", "consent": True})
    assert r.status_code == 400 and "samples" in r.json()["detail"]
    d = ready_draft(c, tmp_path, EN)
    u = f"/api/clone/drafts/{d['id']}/save"
    assert "permission" in c.post(u, json={"name": "X", "language": "en"}).json()["detail"]
    assert c.post(u, json={"name": "  ", "language": "en", "consent": True}).status_code == 400
    assert c.post(u, json={"name": "X", "language": "fr", "consent": True}).status_code == 400
    assert c.post(u, json={"name": "X", "language": "en", "consent": True, "engine": "piper"}).status_code == 400
    assert c.post(u, json={"name": "X", "language": "en", "consent": True, "description": "d" * 501}).status_code == 400
    assert c.post(f"/api/clone/drafts/{d['id']}/preview", json={"text": "a" * 301}).status_code == 400
    assert c.get(f"/api/clone/drafts/{d['id']}/preview").status_code in (404, 405)
    clone.delete(d["id"]); clone.delete(empty["id"])


def test_preview_then_save(c, tmp_path):
    """Real XTTS preview from the draft clips, then save with all details into My Voices."""
    from voicer import clone, tts, voices

    d = ready_draft(c, tmp_path)
    r = c.post(f"/api/clone/drafts/{d['id']}/preview", json={"text": "Testing my new cloned voice today.", "language": "en"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    wav = tmp_path / "prev.wav"
    wav.write_bytes(r.content)
    a, sr = sf.read(wav)
    assert 1.0 < len(a) / sr < 8 and np.abs(a).max() > 0.05
    assert similar(transcribe(wav, "en"), "Testing my new cloned voice today.") > 0.7
    r = c.post(f"/api/clone/drafts/{d['id']}/save", json={
        "name": "  My   Test Voice ", "language": "en", "description": "Made by the test suite.",
        "tags": "Warm, narrator, warm, ", "consent": True})
    assert r.status_code == 200, r.text
    v = r.json()
    assert "dir" not in v                                              # no server paths sent to clients
    assert v["name"] == "My Test Voice" and v["kind"] == "cloned" and v["engine"] == "xtts"
    assert v["language"] == "en" and v["description"] == "Made by the test suite."
    assert v["tags"] == ["warm", "narrator"] and v["consent"]["confirmed"] is True
    assert len(v["samples"]) == len(d["clips"]) and v["preview"] == "preview.wav"
    assert [v["transcripts"][s] for s in v["samples"]] == [c_["text"] for c_ in d["clips"]]
    mine = voices.get(v["id"])
    assert all((__import__("pathlib").Path(mine["dir"]) / s).is_file() for s in mine["samples"] + ["preview.wav"])
    out = tts.speak("The saved voice works.", v["id"], "en")            # usable right away
    assert len(out.samples) / out.sr > 0.8
    assert clone.get(d["id"])["saved_voice"] == v["id"]
    voices.delete(v["id"]); clone.delete(d["id"])


def test_stale_preview_not_copied(c, tmp_path):
    """A preview made before the samples changed is not stored with the voice."""
    from voicer import clone, voices

    d = ready_draft(c, tmp_path, EN)
    (clone._dir(d["id"]) / "preview.wav").write_bytes(b"old")
    dd = clone.get(d["id"]); dd["preview"] = {"clips": "stale"}; clone._save(dd)
    v = c.post(f"/api/clone/drafts/{d['id']}/save", json={"name": "Stale", "language": "en", "consent": True}).json()
    assert "preview" not in v
    voices.delete(v["id"]); clone.delete(d["id"])


def test_f5_uses_saved_transcript(tmp_path, monkeypatch):
    """F5 reference text comes from the (edited) clip transcript, not a new Whisper run."""
    from voicer import asr, voices
    from voicer.engines.f5 import F5Engine

    p = speech(tmp_path / "s.wav", EN[:1], "piper-en-us-lessac-medium", "en")
    v = voices.create("F5 ref test", sample_files=[p])
    v["transcripts"] = {v["samples"][0]: "Edited reference text."}
    v = voices.save(v)
    monkeypatch.setattr(asr, "transcribe", lambda *a, **k: pytest.fail("whisper should not run"))
    assert F5Engine().reference(v)[1] == "Edited reference text."
    voices.delete(v["id"])
