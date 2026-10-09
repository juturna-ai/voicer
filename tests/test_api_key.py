"""Phase 5/7: optional API key (off by default; other devices must send it; this PC needs none)."""
import pytest
from fastapi.testclient import TestClient

from voicer import apikey


@pytest.fixture()
def client():
    from voicer.server import app

    apikey.disable()
    yield TestClient(app)                               # client host "testclient" = another device
    apikey.disable()


def test_off_by_default_everything_open(client):
    assert client.get("/api/api-key").json() == {"enabled": False, "hint": None, "created": None}
    assert client.get("/api/voices").status_code == 200


def test_key_required_from_other_devices(client):
    r = client.post("/api/api-key").json()
    key = r["key"]
    assert key.startswith("vs_") and len(key) > 40 and r["enabled"] and r["hint"] == f"vs_…{key[-4:]}"
    # the key is never readable again, not even its hash
    from voicer import settings

    assert key not in str(settings.load()) and "hash" not in client.get("/api/api-key", headers={"X-API-Key": key}).json()
    r = client.get("/api/voices")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer" and "API key required" in r.json()["detail"]
    r = client.get("/api/voices", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401 and r.json()["detail"] == "Invalid API key"
    assert client.get("/api/voices", headers={"Authorization": f"Bearer {key}"}).status_code == 200
    assert client.get("/api/voices", headers={"X-API-Key": key}).status_code == 200
    assert client.get("/openapi.json").status_code == 401
    # UI files and the health check stay open
    assert client.get("/").status_code == 200 and client.get("/static/app.js").status_code == 200
    assert client.get("/api/health").status_code == 200
    # key management is protected too
    assert client.post("/api/api-key").status_code == 401 and client.delete("/api/api-key").status_code == 401
    # a new key replaces the old one
    new = client.post("/api/api-key", headers={"X-API-Key": key}).json()["key"]
    assert client.get("/api/voices", headers={"X-API-Key": key}).status_code == 401
    assert client.get("/api/voices", headers={"X-API-Key": new}).status_code == 200
    # turn off → open again
    assert client.delete("/api/api-key", headers={"X-API-Key": new}).json()["enabled"] is False
    assert client.get("/api/voices").status_code == 200


@pytest.mark.parametrize("host, headers, local", [
    ("127.0.0.1", {}, True), ("::1", {}, True), ("::ffff:127.0.0.1", {}, True), ("127.0.0.5", {}, True),
    ("192.168.1.20", {}, False), ("100.101.102.103", {}, False), ("testclient", {}, False), (None, {}, False),
    ("127.0.0.1", {"x-forwarded-for": "100.1.2.3"}, False), ("127.0.0.1", {"tailscale-user-login": "a@b"}, False),
    ("127.0.0.1", {"forwarded": "for=1.2.3.4"}, False),
])
def test_this_pc_needs_no_key(host, headers, local):
    assert apikey.is_local(host, headers) is local


def test_this_pc_over_real_http_needs_no_key(live_server):
    """Browser UI on this PC keeps working with a key set (request really comes from 127.0.0.1)."""
    import httpx

    apikey.create()
    try:
        assert httpx.get(live_server + "/api/voices").status_code == 200
        r = httpx.get(live_server + "/api/voices", headers={"X-Forwarded-For": "100.1.2.3"})
        assert r.status_code == 401
    finally:
        apikey.disable()
