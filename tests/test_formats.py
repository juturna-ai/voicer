"""Phase 5/6: download MP3, WAV, OGG/Opus (WhatsApp voice note) for each generated clip."""
import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from conftest import similar, transcribe

TEXT = "Your order is ready for pickup at the front desk."


@pytest.fixture(scope="module")
def client():
    from voicer.server import app

    return TestClient(app)


@pytest.fixture(scope="module")
def entry(client):
    r = client.post("/api/tts", json={"text": TEXT, "voice": "piper-en-us-lessac-medium", "language": "en"})
    assert r.status_code == 200, r.text
    return r.json()


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_name,sample_rate,channels:format=format_name,duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    return j["streams"][0], j["format"]


@pytest.mark.parametrize("fmt, mime, ext, codec, container, rate", [
    ("wav", "audio/wav", "wav", "pcm_s16le", "wav", None),
    ("mp3", "audio/mpeg", "mp3", "mp3", "mp3", 44100),
    ("ogg_opus", "audio/ogg", "ogg", "opus", "ogg", 48000),
])
def test_download_each_format(client, entry, tmp_path, fmt, mime, ext, codec, container, rate):
    r = client.get(f"/api/history/{entry['id']}/audio", params={"format": fmt, "download": "true"})
    assert r.status_code == 200 and r.headers["content-type"] == mime
    assert r.headers["content-disposition"] == f'attachment; filename="voicer-{entry["id"]}.{ext}"'
    p = tmp_path / f"out.{ext}"
    p.write_bytes(r.content)
    st, fm = probe(p)
    assert st["codec_name"] == codec and st["channels"] == 1 and fm["format_name"] == container
    if rate:
        assert int(st["sample_rate"]) == rate
    assert abs(float(fm["duration"]) - entry["seconds"]) < 0.15
    assert similar(transcribe(p, "en"), TEXT) > 0.8


def test_inline_by_default_and_cached(client, entry):
    from voicer import history

    r = client.get(f"/api/history/{entry['id']}/audio", params={"format": "mp3"})
    assert "attachment" not in r.headers.get("content-disposition", "")         # plays in the page
    mp3 = history.audio_path(entry["id"]).with_suffix(".mp3")
    before = mp3.stat().st_mtime_ns
    client.get(f"/api/history/{entry['id']}/audio", params={"format": "mp3"})
    assert mp3.stat().st_mtime_ns == before                                    # encoded once, then reused
    assert not [p for p in mp3.parent.iterdir() if p.name.startswith(".")]     # no temp files left


def test_unknown_format_is_rejected(client, entry):
    r = client.get(f"/api/history/{entry['id']}/audio", params={"format": "aiff"})
    assert r.status_code == 400 and "Unknown format" in r.json()["detail"]


def test_ogg_opus_is_a_clean_whatsapp_voice_note(client, entry, tmp_path):
    """WhatsApp voice note: one Opus stream in OGG, mono, 48 kHz, speech bitrate, decodes with no errors."""
    p = tmp_path / "note.ogg"
    p.write_bytes(client.get(f"/api/history/{entry['id']}/audio", params={"format": "ogg_opus"}).content)
    out = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(p)],
                                    capture_output=True, text=True, check=True).stdout)
    assert len(out["streams"]) == 1
    st = out["streams"][0]
    assert (st["codec_type"], st["codec_name"], st["channels"], st["sample_rate"]) == ("audio", "opus", 1, "48000")
    assert out["format"]["format_name"] == "ogg" and int(out["format"]["bit_rate"]) < 64_000
    dec = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "null", "-"], capture_output=True, text=True)
    assert dec.returncode == 0 and dec.stderr == ""
    assert p.read_bytes()[:4] == b"OggS" and b"OpusHead" in p.read_bytes()[:100]
