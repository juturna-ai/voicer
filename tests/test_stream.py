"""Phase 8: live streaming — audio is sent while the rest of the text is still being spoken (HTTP chunked + WebSocket)."""
import subprocess
import time
import wave

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from conftest import similar, transcribe

VOICE = "piper-en-us-lessac-medium"
TEXT = ("The first train leaves at nine. The second one leaves at ten. Bring a coat, it is cold outside. "
        "We will meet at the station. Do not be late.")


@pytest.fixture(scope="module")
def client():
    from voicer.server import app

    return TestClient(app)


def decoded_seconds(path) -> float:
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", "24000", "-"],
                         capture_output=True, check=True).stdout
    return len(pcm) / 48000


def pcm_to_wav(pcm: bytes, sr: int, path) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)


def test_http_first_bytes_come_before_the_text_is_done(live_server, tmp_path):
    from voicer import history

    httpx.post(f"{live_server}/api/speak", json={"text": "Warm up.", "voice": VOICE}, timeout=120)
    t0, times, data = time.monotonic(), [], b""
    with httpx.stream("POST", f"{live_server}/api/speak", timeout=120,
                      json={"text": TEXT, "voice": VOICE, "format": "pcm", "stream": True}) as r:
        assert r.status_code == 200 and r.headers["transfer-encoding"] == "chunked"
        assert r.headers["content-type"] == "audio/pcm" and r.headers["x-voicer-sample-rate"] == "24000"
        for b in r.iter_raw():
            times.append(time.monotonic() - t0)
            data += b
    assert len(times) >= 4                                      # one piece per sentence, not one blob
    assert times[0] < 0.6 * times[-1], times                    # the first sentence plays before the rest is made
    e = history.get(r.headers["x-voicer-id"])                   # whole clip saved when the stream ends
    assert e["settings"]["stream"] is True and abs(len(data) / 48000 - e["seconds"]) < 0.05
    pcm_to_wav(data, 24000, tmp_path / "s.wav")
    assert similar(transcribe(tmp_path / "s.wav", "en"), TEXT) > 0.85


@pytest.mark.parametrize("fmt, ext, codec", [("mp3", "mp3", "mp3"), ("ogg_opus", "ogg", "opus"),
                                             ("wav", "wav", "pcm_s16le"), ("flac", "flac", "flac"),
                                             ("aac", "aac", "aac")])
def test_http_stream_each_format_plays(client, tmp_path, fmt, ext, codec):
    from voicer import history
    from test_formats import probe

    text = "Your order is ready. Please come to the front desk."
    r = client.post("/speak", json={"text": text, "voice": VOICE, "format": fmt, "stream": True})
    assert r.status_code == 200, r.text
    p = tmp_path / f"s.{ext}"
    p.write_bytes(r.content)
    assert probe(p)[0]["codec_name"] == codec
    assert abs(decoded_seconds(p) - history.get(r.headers["x-voicer-id"])["seconds"]) < 0.15
    assert similar(transcribe(p, "en"), text) > 0.8


def test_openai_stream_is_live(client, tmp_path):
    from voicer import history

    r = client.post("/v1/audio/speech", json={"model": "tts-1", "input": "Short and quick.", "voice": VOICE,
                                              "response_format": "pcm", "stream": True})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/pcm"
    assert abs(len(r.content) / 48000 - history.get(r.headers["x-voicer-id"])["seconds"]) < 0.05


@pytest.mark.parametrize("body, status, detail", [
    ({"text": "Hi", "voice": "nobody"}, 404, "Voice 'nobody' not found"),
    ({"text": " ", "voice": VOICE}, 400, "Text is empty"),
    ({"text": "Hi", "voice": VOICE, "format": "ogg"}, 400, "Unknown format 'ogg'"),
    ({"text": "Hi", "voice": VOICE, "speed": 3}, 400, "Speed must be between"),
])
def test_http_stream_errors_come_before_audio(client, body, status, detail):
    r = client.post("/api/speak", json={**body, "stream": True})
    assert r.status_code == status and detail in r.json()["detail"]


def test_client_leaving_early_stops_and_saves_nothing():
    from voicer import history, stream

    info, it = stream.open_stream(TEXT, VOICE, "en", fmt="pcm")
    assert next(it)
    it.close()
    with pytest.raises(KeyError):
        history.get(info["id"])


def _ws_speak(ws, **msg):
    ws.send_json({"voice": VOICE, **msg})
    start = ws.receive_json()
    if start["type"] == "error":
        return start, b"", None
    data, frames = b"", 0
    while True:
        m = ws.receive()
        if m.get("bytes") is not None:
            data += m["bytes"]
            frames += 1
        else:
            import json

            done = json.loads(m["text"])
            break
    assert frames >= 1
    return start, data, done


@pytest.mark.parametrize("path", ["/api/ws/speak", "/ws/speak"])
def test_websocket_speaks_many_requests_on_one_connection(client, tmp_path, path):
    from voicer import history

    with client.websocket_connect(path) as ws:
        start, data, done = _ws_speak(ws, text=TEXT, language="en")
        assert start == {"type": "start", "id": done["id"], "format": "pcm", "mime": "audio/pcm", "sample_rate": 24000}
        assert done["type"] == "done" and done["url"] == f"/api/history/{done['id']}/audio"
        assert abs(len(data) / 48000 - done["seconds"]) < 0.05 and history.get(done["id"])["seconds"] == done["seconds"]
        pcm_to_wav(data, 24000, tmp_path / "w.wav")
        assert similar(transcribe(tmp_path / "w.wav", "en"), TEXT) > 0.85

        err, _, _ = _ws_speak(ws, text="Hi", voice="nobody")             # an error does not close the socket
        assert err == {"type": "error", "status": 404, "detail": "Voice 'nobody' not found"}
        err, _, _ = _ws_speak(ws, voice=VOICE)
        assert err["type"] == "error" and err["status"] == 422 and "text" in err["detail"]
        ws.send_text("not json")
        assert ws.receive_json() == {"type": "error", "status": 400, "detail": "Send one JSON object per request"}
        ws.send_bytes(b"\x00\x01")
        assert ws.receive_json()["status"] == 400
        start, data, done = _ws_speak(ws, text="[pause 0.5] Hello again.", format="wav")     # leading pause tag
        assert data[:4] == b"RIFF" and abs((len(data) - 44) / 2 / start["sample_rate"] - done["seconds"]) < 0.05

        es = "Hola, buenos días. Nos vemos mañana en la oficina."
        start, data, done = _ws_speak(ws, text=es, voice="Ald (Piper)", language="es", format="ogg_opus")
        assert start["mime"] == "audio/ogg" and data[:4] == b"OggS"
        (tmp_path / "w.ogg").write_bytes(data)
        assert similar(transcribe(tmp_path / "w.ogg", "es"), es) > 0.7


def test_websocket_rejects_other_sites(client):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/api/ws/speak", headers={"origin": "https://evil.example"}) as ws:
            ws.receive_json()
    assert e.value.code == 1008
    with client.websocket_connect("/api/ws/speak", headers={"origin": "http://localhost:8765"}) as ws:
        assert _ws_speak(ws, text="Hello.")[2]["type"] == "done"


def test_websocket_needs_the_api_key_when_on(client):
    from voicer import apikey

    key = apikey.create()
    try:
        with pytest.raises(WebSocketDisconnect) as e:              # the test client is not this PC
            with client.websocket_connect("/api/ws/speak") as ws:
                ws.receive_json()
        assert e.value.code == 1008
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/ws/speak?api_key=vs_wrong") as ws:
                ws.receive_json()
        with client.websocket_connect("/api/ws/speak", headers={"authorization": f"Bearer {key}"}) as ws:
            assert _ws_speak(ws, text="Hello.")[2]["type"] == "done"
        with client.websocket_connect(f"/api/ws/speak?api_key={key}") as ws:      # browsers cannot set headers
            assert _ws_speak(ws, text="Hello.")[2]["type"] == "done"
    finally:
        apikey.disable()



def _first_byte_seconds(text, voice, runs=3):
    from voicer import stream

    out = []
    for _ in range(runs + 1):                                   # the first run loads the model (not counted)
        t0 = time.monotonic()
        info, it = stream.open_stream(text, voice, "en", fmt="pcm")
        next(it)
        out.append(time.monotonic() - t0)
        it.close()
    return sorted(out[1:])[runs // 2]                           # median


@pytest.mark.parametrize("voice", ["piper-en-us-lessac-medium", "kokoro-af-heart"])
def test_first_audio_under_1s_for_short_sentences(voice):
    assert _first_byte_seconds("Hello, how are you today?", voice) < 1.0


@pytest.mark.gpu
def test_xtts_first_audio_under_1s_and_streamed_equals_saved(tmp_path):
    """XTTS sends its first sentence in pieces as the model makes them (engine streaming)."""
    from voicer import history, stream

    assert _first_byte_seconds("Your order is ready.", "xtts-claribel-dervla") < 1.0
    text = "Hello, how are you today? I hope the weather is nice where you are."
    info, it = stream.open_stream(text, "xtts-claribel-dervla", "en", fmt="pcm")
    pieces = list(it)
    data = b"".join(pieces)
    assert len(pieces) >= 3 and abs(len(data) / 48000 - history.get(info["id"])["seconds"]) < 0.02
    pcm_to_wav(data, 24000, tmp_path / "x.wav")
    assert similar(transcribe(tmp_path / "x.wav", "en"), text) > 0.85


def test_trim_start_only_keeps_the_end():
    import numpy as np

    from voicer import tts
    from voicer.engines.base import Audio

    x = np.zeros(24000, np.float32)
    x[8000:12000] = 0.5
    a = tts.trim(Audio(x, 24000), end=False)
    assert len(a.samples) == 24000 - 8000 + int(24000 * 0.05)   # lead silence cut (50 ms margin kept), tail kept
    assert len(tts.trim(Audio(x, 24000)).samples) < len(a.samples)
