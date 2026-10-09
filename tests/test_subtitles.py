"""Subtitles: SRT / WebVTT with one cue per sentence, timed from the generated audio."""
import io
import re

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from conftest import similar, transcribe
from voicer import subtitles


def test_render_srt_and_vtt():
    t = [{"start": 0.0, "end": 1.5, "text": "Hello there."}, {"start": 3661.25, "end": 3662.0, "text": "[happy] Bye. "}]
    assert subtitles.render(t, "srt") == ("1\n00:00:00,000 --> 00:00:01,500\nHello there.\n\n"
                                          "2\n01:01:01,250 --> 01:01:02,000\nBye.\n")
    assert subtitles.render(t, "vtt") == ("WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.500\nHello there.\n\n"
                                          "2\n01:01:01.250 --> 01:01:02.000\nBye.\n")
    assert subtitles.render([], "vtt") == "WEBVTT\n\n"
    with pytest.raises(ValueError):
        subtitles.render(t, "ass")


def test_long_sentence_split_into_readable_blocks():
    text = " ".join(["word"] * 40)                       # 199 characters
    cs = subtitles.cues([{"start": 2.0, "end": 12.0, "text": text}])
    assert len(cs) == 3 and all(len(c["lines"]) <= 2 and all(len(l) <= 42 for l in c["lines"]) for c in cs)
    assert cs[0]["start"] == 2.0 and abs(cs[-1]["end"] - 12.0) < 1e-9
    assert all(a["end"] == b["start"] for a, b in zip(cs, cs[1:]))
    assert " ".join(" ".join(c["lines"]) for c in cs) == text


@pytest.fixture(scope="module")
def client():
    from voicer.server import app

    return TestClient(app)


def _cues(vtt: str):
    out = []
    for block in vtt.strip().split("\n\n")[1:]:
        _, times, *lines = block.split("\n")
        a, b = [sum(float(x) * m for x, m in zip(re.split("[:]", s), (3600, 60, 1))) for s in times.split(" --> ")]
        out.append((a, b, " ".join(lines)))
    return out


def test_timings_match_the_audio(client, tmp_path):
    """Each cue's slice of audio, run through speech recognition, says that cue's sentence; tags never show."""
    text = ("The train leaves at noon. [pause 1s] Please take your ticket and your bag. "
            "We will arrive in the evening.")
    e = client.post("/api/tts", json={"text": text, "voice": "piper-en-us-lessac-medium", "language": "en"}).json()
    r = client.get(f"/api/history/{e['id']}/subtitles", params={"format": "vtt"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/vtt")
    assert "content-disposition" not in r.headers
    cues = _cues(r.text)
    assert [c[2] for c in cues] == ["The train leaves at noon.", "Please take your ticket and your bag.",
                                    "We will arrive in the evening."]
    assert all(a < b for a, b, _ in cues) and all(x[1] <= y[0] for x, y in zip(cues, cues[1:]))
    assert cues[1][0] - cues[0][1] >= 0.95                      # the [pause 1s] gap
    y, sr = sf.read(io.BytesIO(client.get(f"/api/history/{e['id']}/audio").content))
    assert abs(cues[-1][1] - len(y) / sr) < 0.02                 # last cue ends with the audio
    for i, (a, b, said) in enumerate(cues):
        p = tmp_path / f"cue{i}.wav"
        sf.write(p, np.asarray(y[int(a * sr):int(b * sr)]), sr)
        assert similar(transcribe(p, "en"), said) > 0.75, (said, transcribe(p, "en"))
    srt = client.get(f"/api/history/{e['id']}/subtitles", params={"format": "srt", "download": "true"})
    assert srt.headers["content-disposition"] == f'attachment; filename="voicer-{e["id"]}.srt"'
    assert srt.text.startswith("1\n00:00:00,") and srt.text.count(" --> ") == 3


def test_numbers_show_as_written(client):
    e = client.post("/api/tts", json={"text": "Cuesta 25 pesos.", "voice": "piper-es-mx-ald-medium"}).json()
    assert "Cuesta 25 pesos." in client.get(f"/api/history/{e['id']}/subtitles?format=srt").text


@pytest.mark.parametrize("path, code", [
    ("/api/history/20260101-000000-abcdef/subtitles", 404),
    ("/api/history/../../etc/subtitles", 404),
])
def test_subtitle_errors(client, path, code):
    assert client.get(path).status_code == code


def test_bad_subtitle_format(client):
    e = client.post("/api/tts", json={"text": "Hi.", "voice": "piper-en-us-lessac-medium"}).json()
    r = client.get(f"/api/history/{e['id']}/subtitles?format=ass")
    assert r.status_code == 400 and "srt" in r.json()["detail"]
