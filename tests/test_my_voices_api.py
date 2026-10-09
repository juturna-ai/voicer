"""Phase 5: My Voices API (list, edit, delete, duplicate, default voice, preview)."""
import io

import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from voicer import voices


@pytest.fixture(scope="module")
def client():
    from voicer.server import app

    return TestClient(app)


@pytest.fixture()
def voice():
    v = voices.create("Desk Voice", kind="preset", engine="piper", engine_voice="en_US-lessac-medium", language="en",
                      gender="female", estimated=["gender", "age"])
    yield v
    try:
        voices.delete(v["id"])
    except KeyError:
        pass


def test_list(client, voice):
    vs = client.get("/api/my-voices").json()
    v = next(x for x in vs if x["id"] == voice["id"])
    assert v["name"] == "Desk Voice" and v["preview_url"] == f"/api/my-voices/{voice['id']}/preview"
    assert v["has_preview"] is False and v["default"] is False and v["allowed_engines"] == ["piper"]
    assert "dir" not in v and not any(str(x).startswith("/") for x in v.values() if isinstance(x, str) and x != v["preview_url"])


def test_edit_and_rename(client, voice):
    r = client.patch(f"/api/my-voices/{voice['id']}", json={
        "name": "  Morning   Voice ", "description": "For the news", "tags": "Calm, news, calm", "language": "es",
        "accent": "Mexican", "gender": "male", "age": "senior"})
    assert r.status_code == 200, r.text
    v = r.json()
    assert (v["name"], v["description"], v["tags"], v["language"], v["accent"], v["gender"], v["age"]) == \
        ("Morning Voice", "For the news", ["calm", "news"], "es", "Mexican", "male", "senior")
    assert v["estimated"] == [] and v["id"] == voice["id"]           # user values are not estimates; ID unchanged
    assert voices.get(voice["id"])["name"] == "Morning Voice"


@pytest.mark.parametrize("body, words", [
    ({"name": " "}, "Name is required"),
    ({"name": "x" * 81}, "max 80"),
    ({"language": "fr"}, "en or es"),
    ({"gender": "robot"}, "gender must be"),
    ({"age": "teen"}, "age must be"),
    ({"description": "x" * 501}, "max 500"),
    ({"engine": "xtts"}, "not allowed"),
    ({"samples": []}, "Cannot edit: samples"),
    ({"voice_id": "other"}, "Cannot edit: voice_id"),
    ({"tags": [str(i) for i in range(21)]}, "max 20"),
])
def test_edit_rejects_bad_values(client, voice, body, words):
    r = client.patch(f"/api/my-voices/{voice['id']}", json=body)
    assert r.status_code == 400 and words in r.json()["detail"], r.text
    assert voices.get(voice["id"])["name"] == "Desk Voice"


def test_duplicate(client, voice):
    r = client.post(f"/api/my-voices/{voice['id']}/duplicate")
    assert r.status_code == 200, r.text
    d = r.json()
    try:
        assert d["id"] != voice["id"] and d["name"] == "Desk Voice (copy)" and d["engine_voice"] == "en_US-lessac-medium"
        assert d["duplicated_from"] == voice["id"]
        named = client.post(f"/api/my-voices/{voice['id']}/duplicate", json={"name": "Second"}).json()
        assert named["name"] == "Second"
        voices.delete(named["id"])
        client.patch(f"/api/my-voices/{d['id']}", json={"name": "Changed copy"})
        assert voices.get(voice["id"])["name"] == "Desk Voice"           # copies are independent
    finally:
        voices.delete(d["id"])


def test_duplicate_cloned_copies_samples(client, tmp_path):
    import numpy as np

    sf.write(tmp_path / "s.wav", np.zeros(24000, np.float32), 24000)
    v = voices.create("Cloned One", sample_files=[tmp_path / "s.wav"])
    d = client.post(f"/api/my-voices/{v['id']}/duplicate").json()
    try:
        assert d["samples"] == v["samples"] and d["kind"] == "cloned"
        from pathlib import Path
        assert (Path(voices.get(d["id"])["dir"]) / d["samples"][0]).is_file()
    finally:
        voices.delete(v["id"])
        voices.delete(d["id"])


def test_default_voice(client, voice):
    assert client.put("/api/default-voice", json={"voice": voice["id"]}).json() == {"voice": voice["id"]}
    assert client.get("/api/default-voice").json() == {"voice": voice["id"]}
    assert next(x for x in client.get("/api/my-voices").json() if x["id"] == voice["id"])["default"] is True
    cards = client.get("/api/voices").json()
    assert [c["id"] for c in cards if c["default"]] == [voice["id"]]
    assert client.put("/api/default-voice", json={"voice": "nope-123"}).status_code == 404
    assert client.get("/api/default-voice").json() == {"voice": voice["id"]}
    # deleting the default voice clears the default
    assert client.delete(f"/api/my-voices/{voice['id']}").json() == {"deleted": voice["id"]}
    assert client.get("/api/default-voice").json() == {"voice": None}
    assert client.put("/api/default-voice", json={"voice": None}).json() == {"voice": None}


def test_delete(client, voice):
    assert client.delete(f"/api/my-voices/{voice['id']}").status_code == 200
    with pytest.raises(KeyError):
        voices.get(voice["id"])
    assert client.delete(f"/api/my-voices/{voice['id']}").status_code == 404
    assert client.delete("/api/my-voices/..%2Fx").status_code == 404


def test_preview_made_on_demand_then_kept(client, voice):
    from conftest import similar, transcribe

    r = client.get(f"/api/my-voices/{voice['id']}/preview")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    y, sr = sf.read(io.BytesIO(r.content))
    assert 3 < len(y) / sr < 12
    assert voices.get(voice["id"])["preview"] == "preview.wav"
    assert next(x for x in client.get("/api/my-voices").json() if x["id"] == voice["id"])["has_preview"] is True
    from pathlib import Path
    p = Path(voices.get(voice["id"])["dir"]) / "preview.wav"
    assert similar(transcribe(p, "en"), voices.PREVIEW_TEXT["en"]) > 0.75
    mtime = p.stat().st_mtime
    client.get(f"/api/my-voices/{voice['id']}/preview")
    assert p.stat().st_mtime == mtime                                   # not made again


def test_library_copy_keeps_its_preview(client):
    v = client.post("/api/library/kokoro-af-heart/add").json()
    try:
        r = client.get(f"/api/my-voices/{v['id']}/preview")
        assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
    finally:
        voices.delete(v["id"])
