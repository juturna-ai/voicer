"""Phase 4: auto-transcribe clean clips with faster-whisper; edits are kept."""
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from conftest import similar

EN = ("The quick brown fox jumps over the lazy dog near the river bank.",
      "A gentle breeze moved through the tall grass on the quiet hill.")
ES = ("El perro corre por el parque cada mañana con su dueño.",
      "La biblioteca de la ciudad abre a las nueve de la mañana.")


def speech(path, sentences, voice, lang):
    from voicer import tts

    parts = []
    for s in sentences:
        a = tts.synthesize(s, voice, lang)
        parts += [a.samples, np.zeros(a.sr // 2, np.float32)]
    sf.write(path, np.concatenate(parts), a.sr)
    return path


def draft_with(*paths):
    from voicer import clone

    d = clone.new()
    for p in paths:
        clone.add_file(d["id"], p.name, p.read_bytes())
    return clone.process(d["id"])


def test_transcribe_english_clips(tmp_path):
    from voicer import clone

    d = draft_with(speech(tmp_path / "en.wav", EN, "piper-en-us-lessac-medium", "en"))
    assert d["clips"] and all("text" not in c for c in d["clips"]) and d["language"] is None
    d = clone.transcribe(d["id"])
    text = " ".join(c["text"] for c in d["clips"])
    assert similar(text, " ".join(EN)) > 0.8, text
    assert d["language"] == "en" and all(c["language"] == "en" for c in d["clips"])
    clone.delete(d["id"])


def test_transcribe_spanish_detected(tmp_path):
    from voicer import clone

    d = draft_with(speech(tmp_path / "es.wav", ES, "piper-es-mx-ald-medium", "es"))
    d = clone.transcribe(d["id"])
    assert d["language"] == "es"
    assert similar(" ".join(c["text"] for c in d["clips"]), " ".join(ES)) > 0.7
    clone.delete(d["id"])


def test_edits_kept_and_clips_not_retranscribed(tmp_path, monkeypatch):
    from voicer import asr, clone

    d = draft_with(speech(tmp_path / "en.wav", EN, "piper-en-us-lessac-medium", "en"))
    d = clone.transcribe(d["id"])
    first = d["clips"][0]["name"]
    d = clone.set_clip_text(d["id"], first, "  My   corrected\ntext. ")
    assert d["clips"][0]["text"] == "My corrected text." and d["clips"][0]["edited"]
    calls = []
    real = asr.transcribe
    monkeypatch.setattr(asr, "transcribe", lambda p, language=None: calls.append(p) or real(p, language))
    clone.add_file(d["id"], "es.wav", speech(tmp_path / "es.wav", ES[:1], "piper-es-mx-ald-medium", "es").read_bytes())
    d = clone.process(d["id"])                                 # re-clean everything after a new file
    assert d["clips"][0]["text"] == "My corrected text."      # unchanged audio keeps its (edited) text
    assert sum("text" not in c for c in d["clips"]) == 1
    d = clone.transcribe(d["id"])
    assert len(calls) == 1 and all("text" in c for c in d["clips"])
    assert d["language"] == "en"                               # most seconds are English
    clone.delete(d["id"])


def test_api_transcribe_and_edit(tmp_path):
    from voicer.server import app

    p = speech(tmp_path / "en.wav", EN[:1], "piper-en-us-lessac-medium", "en")
    with TestClient(app) as c:
        d = c.post("/api/clone/drafts").json()
        c.post(f"/api/clone/drafts/{d['id']}/files", files=[("files", ("en.wav", p.read_bytes(), "audio/wav"))])
        c.post(f"/api/clone/drafts/{d['id']}/process")
        r = c.post(f"/api/clone/drafts/{d['id']}/transcribe?language=en")
        assert r.status_code == 200 and similar(r.json()["clips"][0]["text"], EN[0]) > 0.8
        name = r.json()["clips"][0]["name"]
        u = f"/api/clone/drafts/{d['id']}/clips/{name}/text"
        assert c.put(u, json={"text": "Fixed."}).json()["clips"][0]["text"] == "Fixed."
        assert c.put(u, json={"text": "x" * 1001}).status_code == 400
        assert c.put(f"/api/clone/drafts/{d['id']}/clips/nope.wav/text", json={"text": "a"}).status_code == 404
        assert c.post(f"/api/clone/drafts/{d['id']}/transcribe?language=fr").status_code == 400
        assert c.post("/api/clone/drafts/000000000000/transcribe").status_code == 404
        from voicer import clone

        clone.delete(d["id"])
