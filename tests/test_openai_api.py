"""Phase 7: OpenAI-compatible `POST /v1/audio/speech`, tested with the official OpenAI Python SDK."""
import json
import subprocess

import httpx
import numpy as np
import openai
import pytest
import soundfile as sf

from conftest import similar, transcribe

TEXT = "The quick brown fox jumps over the lazy dog."
VOICE = "piper-en-us-lessac-medium"


@pytest.fixture(scope="module")
def client(live_server):
    return openai.OpenAI(base_url=f"{live_server}/v1", api_key="not-needed-on-this-pc")


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,sample_rate,channels:format=format_name",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    return j["streams"][0]["codec_name"], j["format"]["format_name"]


@pytest.mark.parametrize("fmt, codec, container", [
    ("mp3", "mp3", "mp3"), ("opus", "opus", "ogg"), ("aac", "aac", "aac"), ("flac", "flac", "flac"), ("wav", "pcm_s16le", "wav"),
])
def test_sdk_each_format(client, tmp_path, fmt, codec, container):
    r = client.audio.speech.create(model="tts-1", voice=VOICE, input=TEXT, response_format=fmt)
    p = tmp_path / f"out.{fmt}"
    r.write_to_file(p)
    assert probe(p) == (codec, container)
    assert similar(transcribe(p, "en"), TEXT) > 0.8


def test_sdk_pcm_is_raw_24khz(client, tmp_path):
    raw = client.audio.speech.create(model="tts-1", voice=VOICE, input=TEXT, response_format="pcm").content
    assert raw[:4] != b"RIFF" and len(raw) % 2 == 0
    p = tmp_path / "pcm.wav"
    sf.write(p, np.frombuffer(raw, "<i2"), 24000)
    assert similar(transcribe(p, "en"), TEXT) > 0.8


def test_voice_by_name_or_object_speed_and_history(client, live_server):
    from voicer import history

    r = client.audio.speech.with_raw_response.create(model="gpt-4o-mini-tts", voice="Lessac (Piper)", input=TEXT,
                                                     speed=0.25, instructions="Speak calmly.")
    e = history.get(r.headers["x-voicer-id"])
    assert r.headers["content-type"] == "audio/mpeg" and e["voice_id"] == VOICE and e["settings"]["speed"] == 0.5  # clamped
    r = client.audio.speech.with_raw_response.create(model="piper", voice={"id": VOICE}, input="Hello.")
    assert history.get(r.headers["x-voicer-id"])["engine"] == "piper"


def test_stream_is_chunked(live_server, tmp_path):
    with httpx.stream("POST", f"{live_server}/v1/audio/speech",
                      json={"model": "tts-1", "input": TEXT, "voice": VOICE, "stream": True}) as r:
        assert r.status_code == 200 and r.headers["transfer-encoding"] == "chunked"
        data = b"".join(r.iter_bytes())
    (tmp_path / "s.mp3").write_bytes(data)
    assert probe(tmp_path / "s.mp3") == ("mp3", "mp3")


@pytest.mark.parametrize("body, param, text", [
    ({"voice": VOICE}, "input", "input: Field required"),
    ({"input": "Hi"}, "voice", "voice: Field required"),
    ({"input": "Hi", "voice": "alloy"}, "voice", "Voice 'alloy' not found"),
    ({"input": "  ", "voice": VOICE}, "input", "Text is empty"),
    ({"input": "Hi", "voice": VOICE, "response_format": "ogg"}, "response_format", "Unsupported response_format 'ogg'"),
    ({"input": "Hi", "voice": VOICE, "speed": 5}, "speed", "speed must be between 0.25 and 4.0"),
    ({"input": "Hi", "voice": VOICE, "stream_format": "sse"}, "stream_format", "'sse' is not supported"),
    ({"input": "Hi", "voice": VOICE, "model": "kokoro"}, "model", "Engine 'kokoro' not allowed"),
    ({"input": "Hi", "voice": VOICE, "language": "fr"}, "language", "Unsupported language 'fr'"),
])
def test_errors_use_openai_shape(live_server, body, param, text):
    r = httpx.post(f"{live_server}/v1/audio/speech", json={"model": "tts-1", **body})
    assert r.status_code == 400, r.text
    err = r.json()["error"]
    assert err["type"] == "invalid_request_error" and err["param"] == param and text in err["message"]


def test_sdk_raises_on_bad_voice(client):
    with pytest.raises(openai.BadRequestError, match="not found"):
        client.audio.speech.create(model="tts-1", voice="alloy", input="Hi")


def test_other_routes_keep_fastapi_errors(live_server):
    r = httpx.post(f"{live_server}/api/tts", json={})
    assert r.status_code == 422 and "detail" in r.json()


def test_api_key_rule(live_server):
    """With a key on, other devices must send it; the SDK sends `api_key` as the Bearer token."""
    from voicer import apikey

    remote = {"X-Forwarded-For": "100.64.0.9"}       # as if it came through a proxy from another device
    key = apikey.create()
    try:
        r = httpx.post(f"{live_server}/v1/audio/speech", json={"input": "Hi", "voice": VOICE}, headers=remote)
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_api_key"
        bad = openai.OpenAI(base_url=f"{live_server}/v1", api_key="wrong", default_headers=remote)
        with pytest.raises(openai.AuthenticationError, match="Invalid API key"):
            bad.audio.speech.create(model="tts-1", voice=VOICE, input="Hi")
        good = openai.OpenAI(base_url=f"{live_server}/v1", api_key=key, default_headers=remote)
        assert good.audio.speech.create(model="tts-1", voice=VOICE, input="Hi").content[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3")
    finally:
        apikey.disable()
