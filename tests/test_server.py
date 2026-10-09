from fastapi.testclient import TestClient


def client():
    from voicer.server import app

    return TestClient(app)


def test_health_and_index():
    with client() as c:
        r = c.get("/api/health")
        assert r.status_code == 200 and r.json()["status"] == "ok"
        r = c.get("/")
        assert r.status_code == 200 and "Voice Studio" in r.text
        assert c.get("/static/app.js").status_code == 200
        assert c.get("/static/app.css").status_code == 200
