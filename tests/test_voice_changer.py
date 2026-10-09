"""Phase 7 / 9: voice changer (speech-to-speech, OpenVoice v2) and `POST /voice-changer` (also `/api/voice-changer`)."""
import io

import librosa
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from conftest import similar, transcribe
from test_formats import probe

SRC_VOICE = "piper-en-us-lessac-medium"        # female, US
TARGET = "kokoro-am-michael"                    # male, US
TEXT = "I can't believe we finally made it! This is the best day of my whole life."


@pytest.fixture(scope="module")
def client():
    from voicer.server import app

    return TestClient(app)


def f0(path) -> float:
    y, sr = librosa.load(str(path), sr=16000)
    f, _, _ = librosa.pyin(y, fmin=60, fmax=400, sr=sr)
    return float(np.nanmedian(f))


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    from voicer import audio, tts

    p = tmp_path_factory.mktemp("vc") / "me.wav"
    audio.write_wav(tts.speak(TEXT, SRC_VOICE, "en"), p)
    return p


@pytest.mark.gpu
def test_convert_keeps_words_and_timing_changes_voice(client, source, tmp_path):
    from voicer import history, tts, voice_changer

    with open(source, "rb") as f:
        r = client.post("/voice-changer", files={"file": ("me.wav", f, "audio/wav")}, data={"voice": TARGET, "format": "wav"})
    assert r.status_code == 200, r.text
    out = tmp_path / "out.wav"
    out.write_bytes(r.content)
    src_len, out_len = sf.info(source).duration, sf.info(out).duration
    assert abs(out_len - src_len) < 0.1                                      # same timing
    assert similar(transcribe(out, "en"), TEXT) > 0.8                        # same words
    ref = tmp_path / "ref.wav"
    sf.write(ref, voice_changer.references(tts._voice(TARGET))[0].samples, voice_changer.SR)
    src_f0, out_f0, ref_f0 = f0(source), f0(out), f0(ref)
    assert abs(out_f0 - ref_f0) < abs(src_f0 - ref_f0) / 3, (src_f0, out_f0, ref_f0)   # sounds like the target

    e = history.get(r.headers["x-voicer-id"])
    assert e["engine"] == "openvoice" and e["voice_id"] == TARGET and e["language"] == "en"
    assert similar(e["text"], TEXT) > 0.8 and e["settings"]["source"] == "me.wav" and e["settings"]["voice_changer"]
    assert "-->" in client.get(f"/api/history/{e['id']}/subtitles?format=srt").text


@pytest.mark.gpu
def test_convert_compressed_upload_to_cloned_voice(client, tmp_path):
    """OGG/Opus upload (a WhatsApp note) → a cloned voice, whose own samples are the reference."""
    from voicer import audio, tts, voices

    sample = tmp_path / "sample.wav"
    audio.write_wav(tts.speak("This is my own voice sample for cloning. I speak slowly and clearly.", TARGET, "en"), sample)
    mine = voices.create("VC Clone Test", kind="cloned", sample_files=[sample], language="en")
    # A longer sentence: one misheard short word ("Hola" → "Vuelve") no longer decides the result.
    said = "Hola, ¿cómo estás? Te llamo mañana por la tarde para hablar del viaje a la playa."
    try:
        note = client.post("/speak", json={"text": said, "voice": "Ald (Piper)",
                                           "language": "es", "format": "ogg_opus"}).content
        r = client.post("/api/voice-changer", files={"file": ("note.ogg", note, "audio/ogg")},
                        data={"voice": "VC Clone Test", "language": "es", "format": "ogg_opus"})
        assert r.status_code == 200, r.text
        p = tmp_path / "o.ogg"
        p.write_bytes(r.content)
        assert probe(p)[0]["codec_name"] == "opus"
        assert similar(transcribe(p, "es"), said) > 0.7
    finally:
        voices.delete(mine["id"])


def _wav(seconds, amp=0.3):
    buf = io.BytesIO()
    t = np.arange(int(22050 * seconds)) / 22050
    sf.write(buf, (amp * np.sin(2 * np.pi * 220 * t)).astype(np.float32), 22050, format="WAV")
    return buf.getvalue()


@pytest.mark.parametrize("files, data, status, detail", [
    ({"file": ("a.wav", _wav(1), "audio/wav")}, {"voice": "nobody"}, 404, "Voice 'nobody' not found"),
    ({"file": ("a.wav", _wav(0.2), "audio/wav")}, {"voice": TARGET}, 400, "Recording is too short"),
    ({"file": ("a.wav", _wav(1, 0), "audio/wav")}, {"voice": TARGET}, 400, "Recording is silent"),
    ({"file": ("a.txt", b"hello world", "text/plain")}, {"voice": TARGET}, 400, "Not a readable audio file"),
    ({"file": ("a.wav", b"", "audio/wav")}, {"voice": TARGET}, 400, "Empty file"),
    ({"file": ("a.wav", _wav(1), "audio/wav")}, {"voice": TARGET, "format": "ogg"}, 400, "Unknown format 'ogg'"),
    ({"file": ("a.wav", _wav(1), "audio/wav")}, {"voice": TARGET, "language": "fr"}, 400, "Unsupported language 'fr'"),
])
def test_errors(client, files, data, status, detail):
    r = client.post("/voice-changer", files=files, data=data)
    assert r.status_code == status and detail in r.json()["detail"], r.text


def test_too_long_and_missing_fields(client, monkeypatch):
    from voicer import voice_changer

    monkeypatch.setattr(voice_changer, "MAX_SECONDS", 2)
    r = client.post("/voice-changer", files={"file": ("a.wav", _wav(3), "audio/wav")}, data={"voice": TARGET})
    assert r.status_code == 400 and "Recording is too long" in r.json()["detail"]
    assert client.post("/voice-changer", data={"voice": TARGET}).status_code == 422
    assert client.post("/voice-changer", files={"file": ("a.wav", _wav(1), "audio/wav")}).status_code == 422


def test_listed_once_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/voice-changer" in paths and "/voice-changer" not in paths
