"""Phase 7: `GET /voices` (also `/api/voices`) with filters language, gender, tags."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from voicer.server import app

    return TestClient(app)


@pytest.mark.parametrize("path", ["/voices", "/api/voices"])
def test_filters(client, path):
    every = client.get(path).json()
    es_f = client.get(path, params={"language": "es", "gender": "female"}).json()
    assert es_f and all(v["language"] == "es" and v["gender"] == "female" for v in es_f)
    assert len(es_f) == sum(v["language"] == "es" and v.get("gender") == "female" for v in every)      # a clone may have no gender
    two = client.get(path, params={"tags": "Calm, narrator"}).json()          # all tags, any case, spaces ok
    assert two and all({"calm", "narrator"} <= {t.lower() for t in v["tags"]} for v in two)
    assert len(two) < len(client.get(path, params={"tags": "calm"}).json())
    assert client.get(path, params={"language": "EN"}).json() == client.get(path, params={"language": "en"}).json()
    assert client.get(path, params={"language": "fr"}).json() == []
    assert client.get(path, params={"tags": ","}).json() == every


def test_my_voices_are_filtered_too(client):
    from voicer import voices

    mine = voices.create("Filter Test", kind="preset", engine="piper", engine_voice="en_US-lessac-medium", language="en",
                         gender="male", tags=["podcast", "calm"])
    try:
        got = client.get("/voices", params={"language": "en", "gender": "male", "tags": "podcast"}).json()
        assert [v["id"] for v in got] == [mine["id"]] and got[0]["origin"] == "mine"
        assert mine["id"] not in [v["id"] for v in client.get("/voices", params={"gender": "female"}).json()]
    finally:
        voices.delete(mine["id"])


def test_listed_once_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    params = {p["name"] for p in paths["/api/voices"]["get"]["parameters"]}
    assert params == {"language", "gender", "tags"} and "/voices" not in paths
