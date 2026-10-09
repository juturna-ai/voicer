"""Phase 5: Voice Library API (list + filters, preview clip, add to My Voices)."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from voicer.server import app

    return TestClient(app)


def test_list_all_with_preview_urls(client):
    vs = client.get("/api/library").json()
    assert len(vs) >= 100
    v = vs[0]
    assert {"id", "name", "language", "accent", "gender", "age", "tags", "engine", "license", "license_short",
            "commercial", "source_url", "preview_url", "added"} <= set(v)
    assert "preview" not in v and all("/" not in (x.get("license_short") or "") for x in vs)
    assert all(x["preview_url"] == f"/api/library/{x['id']}/preview" for x in vs)
    assert not any(str(val).startswith("/home") for x in vs for val in x.values())


@pytest.mark.parametrize("params, check", [
    ({"language": "es"}, lambda v: v["language"] == "es"),
    ({"gender": "male", "engine": "piper"}, lambda v: v["gender"] == "male" and v["engine"] == "piper"),
    ({"style": "calm"}, lambda v: "calm" in v["tags"]),
    ({"accent": "british"}, lambda v: v["accent"] == "British"),
    ({"age": "middle-aged"}, lambda v: v["age"] == "middle-aged"),
    ({"license": "Apache-2.0"}, lambda v: "Apache-2.0" in v["license"]),
    ({"commercial": "true"}, lambda v: v["commercial"] is True),
    ({"q": "heart"}, lambda v: "heart" in (v["id"] + v["name"]).lower()),
])
def test_filters(client, params, check):
    vs = client.get("/api/library", params=params).json()
    assert vs and all(check(v) for v in vs)


def test_preview_is_mp3(client):
    r = client.get("/api/library/kokoro-af-heart/preview")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and len(r.content) > 10_000
    assert client.get("/api/library/nope/preview").status_code == 404
    assert client.get("/api/library/..%2F..%2Fetc/preview").status_code == 404


def test_add_to_my_voices(client):
    from voicer import voices

    r = client.post("/api/library/piper-en-us-lessac-medium/add")
    assert r.status_code == 200, r.text
    mine = r.json()
    try:
        assert mine["library_id"] == "piper-en-us-lessac-medium" and mine["kind"] == "preset" and "dir" not in mine
        assert mine["preview"] == "preview.mp3"
        v = next(x for x in client.get("/api/library", params={"q": "lessac"}).json() if x["id"] == "piper-en-us-lessac-medium")
        assert v["added"] is True
        assert any(x["id"] == mine["id"] and x["origin"] == "mine" for x in client.get("/api/voices").json())
    finally:
        voices.delete(mine["id"])
    assert client.post("/api/library/nope/add").status_code == 404
