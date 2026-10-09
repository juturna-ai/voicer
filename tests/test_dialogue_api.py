"""Phase 7 / 9: multi-speaker dialogue (`voicer/dialogue.py`) and `POST /dialogue` (also `/api/dialogue`)."""
import httpx
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from conftest import similar, transcribe
from test_formats import probe

EN_F = "piper-en-us-lessac-medium"
SCRIPT = """Ann: Good morning, Ben. Did you bring the report?
Ben: Yes, I printed it last night.
It is on your desk.
ann: Thank you, that is very helpful."""


@pytest.fixture(scope="module")
def client():
    from voicer.server import app

    return TestClient(app)


def test_parse():
    from voicer import dialogue

    assert dialogue.parse(SCRIPT) == [("Ann", "Good morning, Ben. Did you bring the report?"),
                                      ("Ben", "Yes, I printed it last night. It is on your desk."),
                                      ("Ann", "Thank you, that is very helpful.")]
    assert dialogue.speakers(SCRIPT) == ["Ann", "Ben"]
    assert dialogue.parse("Ann:\n  Hello there.\nBen: Note: this colon stays.") == [
        ("Ann", "Hello there."), ("Ben", "Note: this colon stays.")]
    for bad, msg in (("Hello.\nAnn: hi", "Line 1 has no speaker"), ("", "Script is empty"), ("Ann:  ", "Script is empty")):
        with pytest.raises(ValueError, match=msg):
            dialogue.parse(bad)


def _second_voice():
    """A different-sounding English voice on another engine if installed, else a second Piper voice."""
    from voicer import library

    ids = {v["id"] for v in library.catalog()}
    for vid in ("kokoro-am-michael", "piper-en-us-ryan-medium", "piper-en-gb-alan-medium"):
        if vid in ids:
            return vid
    return next(v["id"] for v in library.catalog() if v["language"] == "en" and v["id"] != EN_F)


def test_dialogue_one_file_two_voices(client, tmp_path):
    from voicer import history

    ben = _second_voice()
    r = client.post("/dialogue", json={"script": SCRIPT, "voices": {"Ann": EN_F, "ben": ben}, "format": "wav"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "audio/wav"
    p = tmp_path / "d.wav"
    p.write_bytes(r.content)
    x, sr = sf.read(p)
    assert x.ndim == 1 and len(x) / sr > 5
    heard = transcribe(p, "en")
    assert similar(heard, "Good morning, Ben. Did you bring the report? Yes, I printed it last night. It is on your "
                          "desk. Thank you, that is very helpful.") > 0.8, heard

    e = history.get(r.headers["x-voicer-id"])
    assert e["text"] == SCRIPT and e["settings"]["dialogue"] == {"Ann": EN_F, "Ben": ben}
    assert e["voice_name"].startswith("Dialogue: Ann (") and e["voice_id"] == EN_F
    srt = client.get(f"/api/history/{e['id']}/subtitles?format=srt").text
    lines = [l for l in srt.splitlines() if l.startswith(("Ann:", "Ben:"))]
    assert [l.split(":")[0] for l in lines] == ["Ann", "Ann", "Ben", "Ben", "Ann"]     # one cue per sentence

    # turns are levelled: each speaker's part has about the same loudness
    import json
    cues = json.loads((history.audio_path(e["id"]).parent / "cues.json").read_text())
    rms = []
    for c in cues:
        seg = x[int(c["start"] * sr): int(c["end"] * sr)]
        rms.append(20 * np.log10(np.sqrt(np.mean(seg ** 2))))
    assert max(rms) - min(rms) < 6, rms
    assert all(b["start"] >= a["end"] for a, b in zip(cues, cues[1:]))


def test_dialogue_formats_stream_and_alias(live_server, tmp_path):
    body = {"script": "A: Hello.\nB: Hola, ¿qué tal?", "voices": {"A": EN_F, "B": "Ald (Piper)"},
            "format": "ogg_opus", "stream": True}
    with httpx.stream("POST", f"{live_server}/api/dialogue", json=body) as r:
        assert r.status_code == 200 and r.headers["transfer-encoding"] == "chunked"
        data = b"".join(r.iter_bytes())
    (tmp_path / "d.ogg").write_bytes(data)
    assert probe(tmp_path / "d.ogg")[0]["codec_name"] == "opus"


@pytest.mark.parametrize("body, status, detail", [
    ({"script": "Ann: Hi.\nBen: Hi.", "voices": {"Ann": EN_F}}, 400, "No voice for speaker 'Ben'"),
    ({"script": "Ann: Hi.", "voices": {"Ann": "nobody"}}, 404, "Voice 'nobody' not found"),
    ({"script": "Hi.", "voices": {"Ann": EN_F}}, 400, "Line 1 has no speaker"),
    ({"script": "Ann: Hi.", "voices": {"Ann": EN_F}, "gap": 5}, 400, "Gap must be between 0 and 3"),
    ({"script": "Ann: Hi.", "voices": {"Ann": EN_F}, "format": "ogg"}, 400, "Unknown format 'ogg'"),
    ({"script": "Ann: " + "a" * 5000, "voices": {"Ann": EN_F}}, 400, "Script is too long"),
    ({"script": "\n".join(f"S{i}: Hi." for i in range(11)), "voices": {f"S{i}": EN_F for i in range(11)}}, 400,
     "Too many speakers"),
])
def test_dialogue_errors(client, body, status, detail):
    r = client.post("/dialogue", json=body)
    assert r.status_code == status and detail in r.json()["detail"], r.text


def test_listed_once_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/dialogue" in paths and "/dialogue" not in paths
