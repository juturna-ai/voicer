"""Voice blending: mix two XTTS-compatible voices into a new one (weighted average of XTTS speaker latents).

A saved blend stores its mixed latents in data/voices/<id>/blend.pt, so it keeps working if a source is deleted."""
from __future__ import annotations

import io
from pathlib import Path

from . import audio, voices

ENGINE = "xtts"
MIN_RATIO, MAX_RATIO = 0.05, 0.95
PREVIEW_TEXT = {"en": "Hello! This is a blend of two voices. How does it sound?",
                "es": "¡Hola! Esta es una mezcla de dos voces. ¿Qué te parece?"}


def blendable(v: dict) -> bool:
    """XTTS studio speakers, earlier blends, and any voice with its own samples (cloned)."""
    if v.get("blend"):
        return True
    if v.get("engine_voice"):
        return v.get("engine") == ENGINE
    return v.get("kind") != "preset" and bool(v.get("samples"))


def sources() -> list[dict]:
    """Voices that can be blended: My Voices first, then the library."""
    from . import library

    out = [{"id": v["id"], "name": v["name"], "language": v.get("language"), "origin": "mine"}
           for v in voices.all_voices() if blendable(v)]
    out += [{"id": v["id"], "name": v["name"], "language": v.get("language"), "origin": "library"}
            for v in library.catalog() if blendable(v)]
    return out


def _source(voice_id: str) -> dict:
    v = voices.find(voice_id)
    if not blendable(v):
        raise ValueError(f"Voice '{v['name']}' cannot be blended (use XTTS or cloned voices)")
    return v


def spec(a: str, b: str, ratio: float) -> dict:
    """Unsaved blend voice. `ratio` = share of voice A (0.05–0.95)."""
    if a == b:
        raise ValueError("Pick two different voices")
    try:
        ratio = round(float(ratio), 3)
    except (TypeError, ValueError):
        raise ValueError("ratio must be a number") from None
    if not MIN_RATIO <= ratio <= MAX_RATIO:
        raise ValueError(f"ratio must be between {MIN_RATIO} and {MAX_RATIO}")
    va, vb = _source(a), _source(b)
    return {"id": f"blend-{va['id']}-{vb['id']}-{int(ratio * 1000)}", "name": f"{va['name']} × {vb['name']}",
            "kind": "blended", "engine": ENGINE, "language": va.get("language") or "en",
            "blend": {"a": va["id"], "a_name": va["name"], "b": vb["id"], "b_name": vb["name"], "ratio": ratio},
            "_sources": (va, vb)}


def _wav_bytes(a) -> bytes:
    import numpy as np
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, np.clip(a.samples, -1, 1), a.sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def preview(a: str, b: str, ratio: float, text: str = "", language: str = "") -> bytes:
    from . import tts

    v = spec(a, b, ratio)
    language = language or v["language"]
    if language not in ("en", "es"):
        raise ValueError("language must be en or es")
    text = " ".join((text or "").split()) or PREVIEW_TEXT[language]
    if len(text) > 300:
        raise ValueError("Preview text too long (max 300 characters)")
    return _wav_bytes(tts.speak(text, v, language))


def _license(va: dict, vb: dict) -> dict:
    """Blend keeps the stricter terms: commercial only if both sources allow it."""
    lic = [s["license"] for s in (va, vb) if s.get("license")]
    out = {"license": " + ".join(dict.fromkeys(lic))} if lic else {}
    flags = [s["commercial"] for s in (va, vb) if "commercial" in s]
    if flags:
        out["commercial"] = all(f is True for f in flags)
    return out


def save(a: str, b: str, ratio: float, name: str, language: str = "", description: str = "", tags=()) -> dict:
    import torch

    from . import clone, models, tts

    v = spec(a, b, ratio)
    name = " ".join((name or "").split())
    if not name or len(name) > 80:
        raise ValueError("Name is required (max 80 characters)")
    language = language or v["language"]
    if language not in ("en", "es"):
        raise ValueError("language must be en or es")
    description = (description or "").strip()
    if len(description) > 500:
        raise ValueError("Description too long (max 500 characters)")
    tags = clone._tags(tags)
    with models.use(ENGINE) as eng:
        gpt, spk = eng.latents(v)
    voice = voices.create(name, kind="blended", engine=ENGINE, language=language, description=description,
                          tags=tags, blend=v["blend"], **_license(*v["_sources"]))
    torch.save({"gpt": gpt.cpu(), "spk": spk.cpu(), "blend": v["blend"]}, Path(voice["dir"]) / "blend.pt")
    try:
        audio.write_wav(tts.speak(PREVIEW_TEXT[language], voice, language), Path(voice["dir"]) / "preview.wav")
        voice["preview"] = "preview.wav"
        voice = voices.save(voice)
    except Exception:                                   # the voice is usable even if the preview fails
        pass
    return voice
