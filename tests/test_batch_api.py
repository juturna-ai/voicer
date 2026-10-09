"""Phase 7: `POST /batch` (also `/api/batch`) — many texts in one call."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from conftest import similar, transcribe
from test_formats import probe

EN = "piper-en-us-lessac-medium"
ES = "piper-es-mx-ald-medium"


@pytest.fixture(scope="module")
def client():
    from voicer.server import app

    return TestClient(app)


def test_batch_json_mixed_voices_and_one_bad_item(client, tmp_path):
    from voicer import history

    body = {"voice": EN, "format": "ogg_opus", "items": [
        {"text": "Good morning, this is the first clip."},
        {"text": "Buenos días, este es el segundo.", "voice": "Ald (Piper)", "language": "es", "name": "saludo"},
        {"text": "Broken item.", "voice": "nobody"},
        {"text": "   "},
    ]}
    r = client.post("/batch", json=body)
    assert r.status_code == 200, r.text
    m = r.json()
    assert (m["format"], m["count"], m["ok"], m["failed"]) == ("ogg_opus", 4, 2, 2)
    a, b, bad, empty = m["items"]
    assert a["status"] == "ok" and a["voice_id"] == EN and a["index"] == 0
    assert b["status"] == "ok" and b["voice_id"] == ES and b["name"] == "saludo"
    assert bad == {"index": 2, "name": None, "status": "error", "error": "Voice 'nobody' not found"}
    assert empty["status"] == "error" and "Text is empty" in empty["error"]
    for row, text, lang in ((a, body["items"][0]["text"], "en"), (b, body["items"][1]["text"], "es")):
        assert history.get(row["id"])["text"] == text
        assert row["url"] == f"http://testserver/api/history/{row['id']}/audio?format=ogg_opus"
        audio = client.get(row["url"])
        assert audio.headers["content-type"] == "audio/ogg"
        p = tmp_path / f"{row['id']}.ogg"
        p.write_bytes(audio.content)
        assert probe(p)[0]["codec_name"] == "opus" and similar(transcribe(p, lang), text) > 0.7
        assert "-->" in client.get(row["subtitles_url"]).text


def test_batch_zip(client, tmp_path):
    r = client.post("/api/batch", json={"voice": EN, "zip": True, "items": [
        {"text": "One.", "name": "intro/part 1"}, {"text": "Two."}, {"text": "x", "voice": "nobody"}]})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert r.headers["content-disposition"] == 'attachment; filename="voicer-batch.zip"'
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(z.namelist()) == ["001-intro_part_1.mp3", "002.mp3", "manifest.json"]
    m = json.loads(z.read("manifest.json"))
    assert m["ok"] == 2 and m["items"][0]["file"] == "001-intro_part_1.mp3" and "file" not in m["items"][2]
    (tmp_path / "2.mp3").write_bytes(z.read("002.mp3"))
    assert probe(tmp_path / "2.mp3")[0]["codec_name"] == "mp3"


def test_batch_default_voice_and_errors(client):
    from voicer import voices

    mine = voices.create("Batch Default", kind="preset", engine="piper", engine_voice="en_US-lessac-medium", language="en")
    before = voices.default_id()
    voices.set_default(mine["id"])
    try:
        m = client.post("/batch", json={"items": [{"text": "Uses the default voice."}]}).json()
        assert m["items"][0]["voice_id"] == mine["id"]
    finally:
        voices.set_default(before)
        voices.delete(mine["id"])
    m = client.post("/batch", json={"items": [{"text": "No voice anywhere."}]}).json()
    assert m["failed"] == 1 and "No voice" in m["items"][0]["error"]
    assert client.post("/batch", json={"items": []}).json()["detail"] == "Send 1 to 100 items (got 0)"
    assert client.post("/batch", json={"items": [{"text": "a", "voice": EN}] * 101}).status_code == 400
    r = client.post("/batch", json={"voice": EN, "format": "ogg", "items": [{"text": "Hi"}]})
    assert r.status_code == 400 and "Unknown format 'ogg'" in r.json()["detail"]
    r = client.post("/batch", json={"zip": True, "items": [{"text": "Hi", "voice": "nobody"}]})
    assert r.status_code == 400 and r.json()["detail"] == "No item was spoken: Voice 'nobody' not found"
    assert client.post("/batch", json={"items": [{"voice": EN}]}).status_code == 422


def test_listed_once_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/batch" in paths and "/batch" not in paths
