"""OpenAI-compatible text to speech: `POST /v1/audio/speech`. Works with the OpenAI SDKs (set `base_url` to
`http://localhost:8765/v1`). Errors use the OpenAI shape: `{"error": {"message", "type", "param", "code"}}`."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import formats, history, stream, tts

router = APIRouter(prefix="/v1", tags=["OpenAI-compatible"])

# OpenAI response_format → our format. "opus" is Ogg/Opus in the OpenAI API too.
RESPONSE_FORMATS = {"mp3": "mp3", "opus": "ogg_opus", "ogg_opus": "ogg_opus", "aac": "aac", "flac": "flac",
                    "wav": "wav", "pcm": "pcm"}
ENGINE_MODELS = ("xtts", "f5", "kokoro", "piper")      # `model` naming one of these picks that engine
CHUNK = 16 * 1024


class VoiceRef(BaseModel):
    id: str


class SpeechIn(BaseModel):
    model: str = "tts-1"
    input: str
    voice: str | VoiceRef
    response_format: str = "mp3"
    speed: float = 1.0
    stream: bool = False
    stream_format: str | None = None     # OpenAI: "audio" (raw bytes) or "sse"
    instructions: str | None = None      # accepted for compatibility; not used
    language: str = "auto"               # extension: auto / en / es


def error(status: int, message: str, param: str | None = None, code: str | None = None) -> JSONResponse:
    return JSONResponse({"error": {"message": message, "type": "invalid_request_error", "param": param,
                                   "code": code}}, status_code=status)


def chunks(path):
    """File bytes in 16 KB pieces (for chunked responses)."""
    with open(path, "rb") as f:
        while b := f.read(CHUNK):
            yield b


@router.post("/audio/speech", response_model=None)
def speech(body: SpeechIn) -> FileResponse | StreamingResponse | JSONResponse:
    """Text → audio bytes (OpenAI `audio.speech`). `voice` = voice ID or name; `model` is ignored unless it
    names an engine (xtts, f5, kokoro, piper); `response_format` mp3, opus, aac, flac, wav, pcm (24 kHz s16le);
    `speed` 0.25–4 (clamped to 0.5–2); `stream` sends each sentence as soon as it is spoken (chunked). Saved to History (`X-Voicer-Id`)."""
    fmt = RESPONSE_FORMATS.get(body.response_format)
    if not fmt:
        return error(400, f"Unsupported response_format '{body.response_format}' "
                          f"(use {', '.join(k for k in RESPONSE_FORMATS if k != 'ogg_opus')})", "response_format")
    if body.stream_format not in (None, "audio"):
        return error(400, "stream_format 'sse' is not supported; use 'audio' or stream=true", "stream_format")
    if not 0.25 <= body.speed <= 4.0:
        return error(400, "speed must be between 0.25 and 4.0", "speed")
    voice = body.voice.id if isinstance(body.voice, VoiceRef) else body.voice
    engine = body.model if body.model in ENGINE_MODELS else None
    try:
        if body.stream or body.stream_format == "audio":    # live: each sentence is sent as soon as it is spoken
            info, it = stream.open_stream(body.input, voice, body.language, min(max(body.speed, 0.5), 2.0),
                                          engine, fmt)
            return StreamingResponse(it, media_type=info["mime"], headers={"X-Voicer-Id": info["id"]})
        entry = tts.generate(body.input, voice, body.language, min(max(body.speed, 0.5), 2.0), engine)
        path = formats.encode(history.audio_path(entry["id"]), fmt)
    except KeyError as e:
        return error(400, str(e.args[0]) if e.args else "Not found", "voice", "voice_not_found")
    except ValueError as e:
        msg = str(e)
        param = ("model" if msg.startswith("Engine") else "language" if "language" in msg
                 else "input" if msg.startswith("Text") else None)
        return error(400, msg, param)
    spec = formats.FORMATS[fmt]
    headers = {"X-Voicer-Id": entry["id"]}
    return FileResponse(path, media_type=spec["mime"], headers=headers)
