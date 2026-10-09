"""Voice changer (speech-to-speech): a recording in, the same words with the same timing and emotion out, in
another voice. Model: OpenVoice v2 tone colour converter (`engines/openvoice.py`).

The target voice's sound comes from its own samples (cloned voices) or, for library / preset / blended voices,
from a reference clip spoken once with that voice and cached in `data/cache/vc_refs/`. The result is saved to
History; its text and subtitles come from a Whisper transcript of the recording (CPU)."""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import numpy as np

from . import audio, config, history, tts
from .engines.base import Audio
from .engines.openvoice import SR

MAX_SECONDS = 300
MIN_SECONDS = 0.5
MAX_REFS = 5
REF_TEXT = {
    "en": "Hello! It is good to hear from you. Today I want to tell you a short story about a quiet town by "
          "the sea, where the mornings are cool and the evenings are long.",
    "es": "¡Hola! Me alegra mucho saber de ti. Hoy quiero contarte una historia corta sobre un pueblo tranquilo "
          "junto al mar, donde las mañanas son frescas y las tardes son largas.",
}
_ref_lock = threading.Lock()


def _to_sr(a: Audio) -> Audio:
    """Band-limited resample to the model rate (plain interpolation would alias when going down from 48 kHz)."""
    import librosa

    if a.sr == SR:
        return a
    return Audio(librosa.resample(a.samples.astype(np.float32), orig_sr=a.sr, target_sr=SR), SR)


def references(voice: dict) -> list[Audio]:
    """Clips that show how `voice` sounds, at the model rate."""
    d = Path(voice["dir"]) if voice.get("dir") else None
    samples = [d / s for s in voice.get("samples", [])] if d else []
    samples = [p for p in samples if p.is_file()][:MAX_REFS]
    if samples:
        return [_to_sr(audio.decode(p)) for p in samples]
    key = hashlib.sha1(json.dumps({k: v for k, v in voice.items() if k not in ("dir", "preview", "created_at")},
                                  sort_keys=True, default=str).encode()).hexdigest()[:12]
    path = config.CACHE_DIR / "vc_refs" / f"{voice.get('id', 'voice')}-{key}.wav"
    with _ref_lock:                                  # made once even when two requests come at once
        if not path.is_file():
            lang = voice.get("language") if voice.get("language") in REF_TEXT else "en"
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp.wav")
            audio.write_wav(tts.speak(REF_TEXT[lang], voice, lang), tmp)
            tmp.replace(path)
    return [_to_sr(audio.read(path))]


def _cues(src_path: Path, language: str) -> tuple[str, list[dict] | None, str]:
    """Transcript text, subtitle cues and language of the recording. No speech → ("", None, language)."""
    from . import asr

    try:
        r = asr.transcribe(src_path, None if language == "auto" else language)
    except Exception:                                # subtitles are a bonus; never fail the conversion
        return "", None, language
    cues = [{"start": round(s["start"], 3), "end": round(s["end"], 3), "text": s["text"]}
            for s in r["segments"] if s["text"]]
    return r["text"], cues or None, (r["language"] if language == "auto" else language)


def convert(src_path: str | Path, voice: str | dict, language: str = "auto", source_name: str = "") -> dict:
    """Speak the recording at `src_path` with `voice` (ID, name or voice dict). Returns the History entry."""
    from . import models

    if language not in ("auto", *tts.LANGS):
        raise ValueError(f"Unsupported language '{language}' (use auto, en or es)")
    v = tts._voice(voice)                            # unknown voice → KeyError before any work
    src = audio.decode(src_path)                     # not audio → ValueError
    seconds = len(src.samples) / src.sr
    if seconds < MIN_SECONDS:
        raise ValueError(f"Recording is too short ({seconds:.1f} s, min {MIN_SECONDS} s)")
    if seconds > MAX_SECONDS:
        raise ValueError(f"Recording is too long ({seconds:.0f} s, max {MAX_SECONDS} s)")
    if float(np.max(np.abs(src.samples))) < 1e-3:
        raise ValueError("Recording is silent")
    refs = references(v)
    with models.use("openvoice") as conv:
        out = conv.convert(_to_sr(src), refs)
    peak = float(np.max(np.abs(out.samples))) or 1.0
    if peak > 0.95:
        out = Audio(out.samples * (0.95 / peak), out.sr)
    text, cues, lang = _cues(Path(src_path), language)
    name = Path(source_name or "").name[:120]
    settings = {"voice_changer": True, "source": name, "source_seconds": round(seconds, 2)}
    return history.add(out, text or f"(voice changer: {name or 'recording'})", v, lang, "openvoice", settings,
                       cues=cues)
