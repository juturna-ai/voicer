"""Final test, SRT for an audio file: `POST /api/subtitles` makes SRT/VTT for your own recording (Whisper timings)."""
import re

import httpx
import numpy as np
import pytest

from conftest import similar
from voicer import audio, tts
from voicer.engines.base import Audio

TEXT = ["Good morning, everyone.", "Today we talk about the weather.", "Tomorrow will be sunny and warm."]


def _srt_cues(srt):
    def sec(ts):
        h, m, s = ts.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    return [(sec(a), sec(b), t.replace("\n", " ")) for a, b, t in
            re.findall(r"\d+\n([\d:,]+) --> ([\d:,]+)\n(.+?)(?:\n\n|\n?$)", srt, re.S)]


@pytest.mark.gpu
def test_srt_and_vtt_for_a_recording(live_server, tmp_path):
    a = tts.speak(" [pause 1.5s] ".join(TEXT), "piper-en-us-lessac-medium", "en")   # clear gaps between sentences
    path = tmp_path / "my talk (final).mp3"
    audio.write_wav(a, tmp_path / "t.wav")
    import subprocess
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp_path / "t.wav", path], check=True)
    seconds = len(a.samples) / a.sr

    r = httpx.post(f"{live_server}/api/subtitles", files={"file": (path.name, path.read_bytes(), "audio/mpeg")},
                   data={"language": "en"}, timeout=300)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/x-subrip")
    assert 'filename="my_talk_final.srt"' in r.headers["content-disposition"]
    cues = _srt_cues(r.text)
    assert len(cues) >= 3, r.text
    assert similar(" ".join(c[2] for c in cues), " ".join(TEXT)) >= 0.85
    assert all(0 <= s < e <= seconds + 0.3 for s, e, _ in cues)
    assert all(cues[i][1] <= cues[i + 1][0] + 0.05 for i in range(len(cues) - 1))       # in order, no overlap
    first_word_end = next(e for s, e, t in cues if "morning" in t.lower())
    assert first_word_end < seconds / 2                                                  # the timing follows the audio

    r = httpx.post(f"{live_server}/api/subtitles", files={"file": ("x.wav", (tmp_path / "t.wav").read_bytes())},
                   data={"format": "vtt"}, timeout=300)                                  # auto language
    assert r.status_code == 200 and r.text.startswith("WEBVTT\n\n") and " --> " in r.text
    assert r.headers["content-type"].startswith("text/vtt")


def _wav(tmp_path, samples, sr=16000):
    p = tmp_path / "x.wav"
    audio.write_wav(Audio(np.asarray(samples, dtype=np.float32), sr), p)
    return p.read_bytes()


@pytest.mark.parametrize("make, form, detail", [
    (lambda p: b"", {}, "Empty file"),
    (lambda p: b"not audio at all", {}, "audio"),
    (lambda p: _wav(p, np.zeros(16000 * 2)), {}, "silent"),
    (lambda p: _wav(p, 0.3 * np.sin(np.arange(4000) / 5)), {}, "too short"),
    (lambda p: _wav(p, 0.3 * np.sin(np.arange(16000 * 601) / 5)), {}, "too long"),
    (lambda p: _wav(p, 0.3 * np.sin(np.arange(16000 * 2) / 5)), {"language": "fr"}, "Unsupported language"),
    (lambda p: _wav(p, 0.3 * np.sin(np.arange(16000 * 2) / 5)), {"format": "txt"}, "Unknown subtitle format"),
    (lambda p: _wav(p, 0.3 * np.sin(np.arange(16000 * 2) / 5)), {}, "No speech found"),
])
def test_bad_input(live_server, tmp_path, make, form, detail):
    r = httpx.post(f"{live_server}/api/subtitles", files={"file": ("a.wav", make(tmp_path))}, data=form, timeout=120)
    assert r.status_code == 400 and detail in r.json()["detail"], r.text
