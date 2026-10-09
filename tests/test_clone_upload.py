import io
import subprocess

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient


def tone(seconds=2.0, sr=22050, fmt="WAV") -> bytes:
    t = np.arange(int(sr * seconds)) / sr
    buf = io.BytesIO()
    sf.write(buf, 0.3 * np.sin(2 * np.pi * 220 * t), sr, format=fmt)
    return buf.getvalue()


def webm_opus(tmp_path, seconds=1.5) -> bytes:
    src = tmp_path / "t.wav"
    src.write_bytes(tone(seconds, 48000))
    out = tmp_path / "t.webm"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-c:a", "libopus", str(out)], check=True)
    return out.read_bytes()


@pytest.fixture()
def c():
    from voicer.server import app

    with TestClient(app) as client:
        yield client


def test_decode_formats(tmp_path):
    from voicer import audio

    for name, data in (("a.wav", tone()), ("a.mp3", tone(fmt="MP3")), ("a.webm", webm_opus(tmp_path))):
        p = tmp_path / name
        p.write_bytes(data)
        a = audio.decode(p)
        assert a.samples.ndim == 1 and abs(len(a.samples) / a.sr - (1.5 if name.endswith("webm") else 2.0)) < 0.1
    bad = tmp_path / "x.wav"
    bad.write_text("not audio")
    with pytest.raises(ValueError):
        audio.decode(bad)


def test_upload_flow(c, tmp_path):
    d = c.post("/api/clone/drafts").json()
    files = [("files", ("sample one.wav", tone(3.0), "audio/wav")),
             ("files", ("two.mp3", tone(2.0, fmt="MP3"), "audio/mpeg")),
             ("files", ("rec.webm", webm_opus(tmp_path), "audio/webm")),
             ("files", ("notes.txt", b"hello", "text/plain"))]
    r = c.post(f"/api/clone/drafts/{d['id']}/files", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert [f["original"] for f in body["files"]] == ["sample one.wav", "two.mp3", "rec.webm"]
    assert body["errors"] and body["errors"][0]["file"] == "notes.txt"
    assert abs(body["total_seconds"] - 6.5) < 0.2
    name = body["files"][0]["name"]
    assert c.get(f"/api/clone/drafts/{d['id']}/files/{name}").content == tone(3.0)
    r = c.delete(f"/api/clone/drafts/{d['id']}/files/{name}")
    assert len(r.json()["files"]) == 2
    # only-bad upload → 400 with message; unknown draft → 404; path tricks rejected
    assert c.post(f"/api/clone/drafts/{d['id']}/files", files=[("files", ("x.txt", b"x", "text/plain"))]).status_code == 400
    assert c.get("/api/clone/drafts/000000000000").status_code == 404
    assert c.get("/api/clone/drafts/..%2F..").status_code == 404
    assert c.get(f"/api/clone/drafts/{d['id']}/files/..%2Fdraft.json").status_code == 404
