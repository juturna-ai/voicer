"""Phase 5: History API (`GET /api/history` list + search + paging, `DELETE /api/history/{id}`)."""
import time
import uuid

import numpy as np
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from voicer.server import app

    return TestClient(app)


def _add(text, cues=True):
    from voicer import history
    from voicer.engines.base import Audio

    a = Audio(np.zeros(24000, dtype=np.float32), 24000)
    return history.add(a, text, {"id": "hist-voice", "name": "Hist Voice"}, "en", "piper",
                       cues=[{"start": 0.0, "end": 1.0, "text": text}] if cues else None)


def test_list_newest_first_search_and_paging(client):
    tag = uuid.uuid4().hex[:8]
    old = _add(f"first {tag}")
    time.sleep(1.1)                                       # IDs start with the time to the second
    new = _add(f"second {tag}", cues=False)
    r = client.get("/api/history", params={"q": tag.upper()}).json()
    assert r["total"] == 2 and [e["id"] for e in r["items"]] == [new["id"], old["id"]]
    assert [e["has_subtitles"] for e in r["items"]] == [False, True]
    assert r["items"][1]["voice_name"] == "Hist Voice" and r["items"][1]["seconds"] == 1.0
    page = client.get("/api/history", params={"q": tag, "limit": 1, "offset": 1}).json()
    assert page["total"] == 2 and [e["id"] for e in page["items"]] == [old["id"]]
    assert client.get("/api/history", params={"q": "hist voice"}).json()["total"] >= 2   # voice name matches too
    all_ = client.get("/api/history").json()
    assert {old["id"], new["id"]} <= {e["id"] for e in all_["items"]}
    assert all("dir" not in e and "/" not in e["id"] for e in all_["items"])


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
def test_bad_paging_is_400(client, params):
    r = client.get("/api/history", params=params)
    assert r.status_code == 400 and r.json()["detail"]


def test_delete_removes_entry_files_and_encodings(client):
    from voicer import config

    e = _add(f"delete me {uuid.uuid4().hex[:6]}")
    assert client.get(f"/api/history/{e['id']}/audio", params={"format": "mp3"}).status_code == 200
    d = config.OUTPUT_DIR / e["id"]
    assert (d / "audio.mp3").exists()
    r = client.delete(f"/api/history/{e['id']}")
    assert r.status_code == 200 and r.json() == {"deleted": e["id"]}
    assert not d.exists()
    assert client.get(f"/api/history/{e['id']}").status_code == 404
    assert client.delete(f"/api/history/{e['id']}").status_code == 404
    assert e["id"] not in {x["id"] for x in client.get("/api/history").json()["items"]}


@pytest.mark.parametrize("eid", ["nope", "..", "20260101-000000-zzzzzz", "20260101-000000-abcdef"])
def test_delete_unknown_or_unsafe_id_is_404(client, eid):
    assert client.delete(f"/api/history/{eid}").status_code == 404


def test_broken_entry_is_skipped(client):
    from voicer import config

    d = config.OUTPUT_DIR / "20200101-000000-abcabc"
    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text("{not json")
    try:
        assert client.get("/api/history").status_code == 200
    finally:
        (d / "meta.json").unlink()
        d.rmdir()
