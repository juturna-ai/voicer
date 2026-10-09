"""Speech-to-text with faster-whisper (CPU int8 to keep VRAM free for TTS)."""
from __future__ import annotations

import os
import threading

_model = None
_lock = threading.Lock()
MODEL_SIZE = os.environ.get("VOICER_WHISPER", "small")


def _get():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def transcribe(path, language: str | None = None) -> dict:
    """Return {'text', 'language', 'segments': [{'start','end','text'}]}."""
    with _lock:
        segs, info = _get().transcribe(str(path), language=language, vad_filter=True)
        segments = [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segs]
    return {"text": " ".join(s["text"] for s in segments).strip(), "language": info.language,
            "segments": segments}
