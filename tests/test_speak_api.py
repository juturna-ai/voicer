"""Phase 7: `POST /speak` (also `/api/speak`) — text in, audio bytes out."""
import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import similar, transcribe
from test_formats import probe

VOICE = "piper-en-us-lessac-medium"


@pytest.fixture(scope="module")
def client():
    from voicer.server import app

    return TestClient(app)


def test_speak_returns_mp3_saved_to_history(client, tmp_path):
    from voicer import history

    text = "The train leaves from platform four."
    r = client.post("/speak", json={"text": text, "voice": VOICE})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "audio/mpeg" and float(r.headers["x-voicer-seconds"]) > 1
    p = tmp_path / "a.mp3"
    p.write_bytes(r.content)
    stream, fmt = probe(p)
    assert (stream["codec_name"], fmt["format_name"]) == ("mp3", "mp3")
    assert similar(transcribe(p, "en"), text) > 0.8
    e = history.get(r.headers["x-voicer-id"])
    assert e["text"] == text and e["voice_id"] == VOICE


@pytest.mark.parametrize("path", ["/speak", "/api/speak"])
def test_speak_spanish_whatsapp_note_by_name(client, tmp_path, path):
    text = "Hola, nos vemos mañana en la oficina."
    r = client.post(path, json={"text": text, "voice": "Ald (Piper)", "language": "es", "format": "ogg_opus"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "audio/ogg"
    p = tmp_path / "n.ogg"
    p.write_bytes(r.content)
    stream, fmt = probe(p)
    assert (stream["codec_name"], stream["channels"], stream["sample_rate"], fmt["format_name"]) == ("opus", 1, "48000", "ogg")
    assert similar(transcribe(p, "es"), text) > 0.7


def test_speak_wav_and_download_name(client):
    r = client.post("/speak", json={"text": "Hello.", "voice": VOICE, "format": "wav", "download": True})
    assert r.headers["content-type"] == "audio/wav" and r.content[:4] == b"RIFF"
    assert r.headers["content-disposition"] == f'attachment; filename="voicer-{r.headers["x-voicer-id"]}.wav"'


def test_speak_stream_is_chunked(live_server, tmp_path):
    with httpx.stream("POST", f"{live_server}/speak", json={"text": "Streaming test.", "voice": VOICE, "stream": True}) as r:
        assert r.status_code == 200 and r.headers["transfer-encoding"] == "chunked"
        assert r.headers["x-voicer-id"]
        data = b"".join(r.iter_bytes())
    (tmp_path / "s.mp3").write_bytes(data)
    assert probe(tmp_path / "s.mp3")[0]["codec_name"] == "mp3"


@pytest.mark.parametrize("body, status, detail", [
    ({"text": "Hi", "voice": "nobody"}, 404, "Voice 'nobody' not found"),
    ({"text": " ", "voice": VOICE}, 400, "Text is empty"),
    ({"text": "Hi", "voice": VOICE, "format": "ogg"}, 400, "Unknown format 'ogg'"),
    ({"text": "Hi", "voice": VOICE, "language": "fr"}, 400, "Unsupported language 'fr'"),
])
def test_speak_errors(client, body, status, detail):
    r = client.post("/speak", json=body)
    assert r.status_code == status and detail in r.json()["detail"]
    assert client.post("/speak", json={"voice": VOICE}).status_code == 422


def test_speak_listed_once_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/speak" in paths and "/speak" not in paths
