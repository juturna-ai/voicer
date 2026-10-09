"""Phase 5: Text to Speech API (`POST /api/tts`, history entries, `GET /api/voices`)."""
import io

import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from conftest import similar, transcribe


@pytest.fixture(scope="module")
def client():
    from voicer.server import app

    return TestClient(app)


def test_voice_list_has_library_and_my_voices(client):
    from voicer import voices

    mine = voices.create("Picker Test", kind="preset", engine="piper", engine_voice="en_US-lessac-medium", language="en")
    try:
        vs = client.get("/api/voices").json()
        lib = [v for v in vs if v["origin"] == "library"]
        assert len(lib) >= 30 and {v["language"] for v in lib} >= {"en", "es"}
        m = next(v for v in vs if v["id"] == mine["id"])
        assert m["origin"] == "mine" and m["name"] == "Picker Test"
        assert all("dir" not in v and "samples" not in v for v in vs)
    finally:
        voices.delete(mine["id"])


def test_generate_saves_history_and_audio(client, tmp_path):
    text = "The library opens at nine in the morning."
    r = client.post("/api/tts", json={"text": text, "voice": "piper-en-us-lessac-medium", "language": "en"})
    assert r.status_code == 200, r.text
    e = r.json()
    assert e["text"] == text and e["voice_id"] == "piper-en-us-lessac-medium" and e["engine"] == "piper"
    assert e["seconds"] > 1.0 and e["settings"]["speed"] == 1.0
    assert client.get(f"/api/history/{e['id']}").json() == e
    a = client.get(f"/api/history/{e['id']}/audio")
    assert a.status_code == 200 and a.headers["content-type"] == "audio/wav"
    y, sr = sf.read(io.BytesIO(a.content))
    assert abs(len(y) / sr - e["seconds"]) < 0.05
    (tmp_path / "out.wav").write_bytes(a.content)
    assert similar(transcribe(tmp_path / "out.wav", "en"), text) > 0.8


def test_generate_auto_language_and_speed(client, tmp_path):
    slow = client.post("/api/tts", json={"text": "Hola, buenos días a todos.", "voice": "piper-es-mx-ald-medium",
                                         "speed": 0.7}).json()
    fast = client.post("/api/tts", json={"text": "Hola, buenos días a todos.", "voice": "piper-es-mx-ald-medium",
                                         "speed": 1.4}).json()
    assert slow["language"] == "auto" and slow["seconds"] > fast["seconds"] * 1.5
    (tmp_path / "es.wav").write_bytes(client.get(f"/api/history/{fast['id']}/audio").content)
    assert similar(transcribe(tmp_path / "es.wav", "es"), "Hola, buenos días a todos.") > 0.7


@pytest.mark.parametrize("body, code, words", [
    ({"text": "  ", "voice": "piper-en-us-lessac-medium"}, 400, "empty"),
    ({"text": "x" * 5001, "voice": "piper-en-us-lessac-medium"}, 400, "too long"),
    ({"text": "Hi.", "voice": "no-such-voice"}, 404, "not found"),
    ({"text": "Hi.", "voice": "piper-en-us-lessac-medium", "language": "fr"}, 400, "language"),
    ({"text": "Hi.", "voice": "piper-en-us-lessac-medium", "speed": 5}, 400, "speed"),
    ({"text": "Hi.", "voice": "piper-en-us-lessac-medium", "engine": "xtts"}, 400, "not allowed"),
])
def test_generate_rejects_bad_input(client, body, code, words):
    r = client.post("/api/tts", json=body)
    assert r.status_code == code and words in r.json()["detail"].lower(), r.text


@pytest.mark.parametrize("eid", ["nope", "..%2F..%2Fetc", "20990101-000000-abcdef"])
def test_history_unknown_or_unsafe_id_is_404(client, eid):
    assert client.get(f"/api/history/{eid}").status_code == 404
    assert client.get(f"/api/history/{eid}/audio").status_code == 404
