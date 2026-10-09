"""Synthesis service: text + voice -> audio."""
from __future__ import annotations

from typing import Iterator, NamedTuple

import numpy as np

from . import dictionary, models, voices
from .engines.base import Audio
from .text.lang import detect
from .text.normalize import normalize
from .text.split import chunk, split_paragraphs

LANGS = ("en", "es")
SENTENCE_PAUSE = 0.25  # default seconds of silence between parts


class Segment(NamedTuple):
    text: str
    lang: str
    pause: float = SENTENCE_PAUSE  # silence after this segment
    src: str = ""                  # the original sentence (before dictionary/normalize), for subtitles
    sent: int = 0                  # sentence number; the pieces of one long sentence share it


def _voice(voice: str | dict) -> dict:
    return voices.find(voice) if isinstance(voice, str) else voice


def synthesize(text: str, voice: str | dict, language: str = "en", speed: float = 1.0,
               engine: str | None = None, **opts) -> Audio:
    """One engine call, one language. `engine` overrides the voice's engine (validated)."""
    v = _voice(voice)
    if engine and engine != v.get("engine"):
        if engine not in voices.allowed_engines(v):
            raise ValueError(f"Engine '{engine}' not allowed for voice '{v.get('id')}'")
    engine = engine or v.get("engine") or voices.DEFAULT_CLONE_ENGINE
    with models.use(engine) as eng:
        if language not in eng.languages:
            raise ValueError(f"Engine '{engine}' does not support language '{language}'")
        return eng.synthesize(text, v, language, speed=speed, **opts)


def synthesize_stream(text: str, voice: str | dict, language: str = "en", speed: float = 1.0,
                      engine: str | None = None, **opts) -> Iterator[Audio]:
    """`synthesize`, but yields audio pieces while the engine works (XTTS; other engines: one piece).
    The engine runs in its own thread, which holds the model for the whole sentence (the model lock is
    per thread); pieces are passed on through a queue."""
    import queue
    import threading

    v = _voice(voice)
    if engine and engine != v.get("engine"):
        if engine not in voices.allowed_engines(v):
            raise ValueError(f"Engine '{engine}' not allowed for voice '{v.get('id')}'")
    engine = engine or v.get("engine") or voices.DEFAULT_CLONE_ENGINE
    q: queue.Queue = queue.Queue()
    stop = threading.Event()

    def work() -> None:
        try:
            with models.use(engine) as eng:
                if language not in eng.languages:
                    raise ValueError(f"Engine '{engine}' does not support language '{language}'")
                for a in eng.synthesize_stream(text, v, language, speed=speed, **opts):
                    if stop.is_set():
                        break
                    q.put(a)
            q.put(None)
        except BaseException as e:                    # passed to the reader, raised there
            q.put(e)

    threading.Thread(target=work, daemon=True, name="voicer-stream").start()
    try:
        while (x := q.get()) is not None:
            if isinstance(x, BaseException):
                raise x
            yield x
    finally:
        stop.set()


def plan(text: str, language: str = "auto", default: str = "en", normalize_text: bool = True,
         max_chars: int = 250) -> list[Segment]:
    """Split text into sentences, tag each with a language (a fixed language overrides detection),
    apply the pronunciation dictionary, spell out numbers/dates/money for that language, then cut over-long sentences at clause
    boundaries (never inside a word). Each segment carries the pause that should follow it."""
    if language not in ("auto", *LANGS):
        raise ValueError(f"Unsupported language '{language}' (use auto, en or es)")
    out: list[Segment] = []
    prev = default
    for n, (s, pause) in enumerate(split_paragraphs(text)):
        src = s
        lang = language if language != "auto" else detect(s, default=prev)
        prev = lang
        s = dictionary.apply(s, lang)
        if normalize_text:
            s = normalize(s, lang)
        pieces = chunk(s, max_chars)
        for i, (piece, p) in enumerate(pieces):
            out.append(Segment(piece, lang, pause if i == len(pieces) - 1 else p, src, n))
    return out


def resample(a: Audio, sr: int) -> Audio:
    if a.sr == sr or not len(a.samples):
        return Audio(a.samples, sr)
    n = int(round(len(a.samples) * sr / a.sr))
    x = np.linspace(0, len(a.samples) - 1, n)
    return Audio(np.interp(x, np.arange(len(a.samples)), a.samples).astype(np.float32), sr)


def trim(a: Audio, margin: float = 0.05, floor_db: float = -40.0, end: bool = True) -> Audio:
    """Drop leading/trailing near-silence (relative to the clip's peak), keeping a safety margin
    so word onsets and endings are never cut. 5 ms fades avoid clicks at the joins.
    `end=False`: only the start (the first piece of a live-streamed sentence; more audio follows)."""
    x = a.samples
    if not len(x):
        return a
    peak = float(np.max(np.abs(x))) or 1.0
    loud = np.flatnonzero(np.abs(x) > peak * 10 ** (floor_db / 20))
    if not len(loud):
        return a
    m = int(a.sr * margin)
    x = x[max(0, loud[0] - m): (loud[-1] + m + 1 if end else len(x))].copy()
    f = min(len(x) // 2, int(a.sr * 0.005))
    if f:
        ramp = np.linspace(0, 1, f, dtype=np.float32)
        x[:f] *= ramp
        if end:
            x[-f:] *= ramp[::-1]
    return Audio(x, a.sr)


def concat(parts: list[Audio], pauses: list[float] | float = SENTENCE_PAUSE) -> Audio:
    """Join parts with silence. `pauses[i]` follows part i (a single float = same gap everywhere)."""
    if not parts:
        return Audio(np.zeros(0, np.float32), 24000)
    sr = parts[0].sr
    if isinstance(pauses, (int, float)):
        pauses = [pauses] * len(parts)
    chunks = []
    for i, p in enumerate(parts):
        chunks.append(resample(p, sr).samples)
        if i < len(parts) - 1:
            chunks.append(np.zeros(int(sr * pauses[i]), np.float32))
    return Audio(np.concatenate(chunks), sr)


def speak(text: str, voice: str | dict, language: str = "auto", speed: float = 1.0,
          engine: str | None = None, **opts) -> Audio:
    """Full pipeline: tags → split → per-sentence language → dictionary → normalize → chunk →
    synthesize (+ style) → trim → join with natural or tagged pauses."""
    return speak_timed(text, voice, language, speed, engine, **opts)[0]


class Part(NamedTuple):
    audio: Audio               # one spoken segment (trimmed, style applied)
    pause: float               # silence after it
    text: str                  # the original sentence
    key: tuple[int, int]       # (text item, sentence): parts of one long sentence share it → one subtitle cue
    last: bool                 # no pause after the last part


def speak_parts(text: str, voice: str | dict, language: str = "auto", speed: float = 1.0,
                engine: str | None = None, stream_first: bool = False, **opts) -> tuple[float, Iterator[Part]]:
    """The `speak` pipeline one segment at a time (for live streaming). Planning is done at once, so a bad
    request raises here. Returns `(leading pause in seconds, parts)`; each part is spoken when it is asked for.

    `stream_first`: the first segment (if it has no style tag and the engine can stream) comes in pieces as the
    engine makes them — pieces with no pause, then an empty part that carries the pause — for a faster first
    byte. Its end is not trimmed (already sent). Later segments are made while the first one plays."""
    from . import effects
    from .engines import ENGINES
    from .text import tags

    v = _voice(voice)
    eng_name = engine or v.get("engine") or voices.DEFAULT_CLONE_ENGINE
    eng_cls = ENGINES[eng_name]
    prev = v.get("language") if v.get("language") in LANGS else "en"
    lead = 0.0                               # pause tags before any speech
    segs: list[tuple[Segment, str | None]] = []
    keys: list[tuple[int, int]] = []         # (text item, sentence) of each segment, to group the timings
    tagged: set[int] = set()                 # segments whose pause was set by a [pause] tag
    for k, item in enumerate(tags.parse(text)):
        if item.kind == "pause":
            if not segs:
                lead += item.seconds
                continue
            i = len(segs) - 1
            seg, style = segs[i]
            # a tag right after text sets the gap exactly; consecutive tags add up
            segs[i] = (seg._replace(pause=(seg.pause if i in tagged else 0.0) + item.seconds), style)
            tagged.add(i)
            continue
        for seg in plan(item.text, language, prev, max_chars=eng_cls.max_chars):
            segs.append((seg, item.style))
            keys.append((k, seg.sent))
            prev = seg.lang
    if not segs:
        raise ValueError("Text is empty")

    def run() -> Iterator[Part]:
        for i, (seg, style) in enumerate(segs):
            last = i == len(segs) - 1
            if i == 0 and stream_first and not style and eng_cls.streams:
                for n, a in enumerate(synthesize_stream(seg.text, v, seg.lang, speed=speed, engine=engine, **opts)):
                    yield Part(trim(a, end=False) if n == 0 else a, 0.0, seg.src.strip(), keys[i], False)
                yield Part(Audio(np.zeros(0, np.float32), eng_cls.sr or 24000), seg.pause, seg.src.strip(), keys[i],
                           last)
                continue
            fx = effects.STYLE_EFFECTS.get(style or "", {})
            o = dict(opts)
            if "temperature" in fx and eng_cls.expressive:
                o["temperature"] = fx["temperature"]
            a = synthesize(seg.text, v, seg.lang, speed=speed * fx.get("speed", 1.0), engine=engine, **o)
            yield Part(effects.apply_style(trim(a), style), seg.pause, seg.src.strip(), keys[i], last)

    return lead, run()


def join_parts(parts: list[Part], lead: float = 0.0) -> tuple[Audio, list[dict]]:
    """One clip from spoken parts, plus one timing per original sentence: [{"start", "end", "text"}] in seconds."""
    out = concat([p.audio for p in parts], [p.pause for p in parts])
    if lead:
        out = Audio(np.concatenate([np.zeros(int(out.sr * lead), np.float32), out.samples]), out.sr)
    # timings: same sample counts as concat (parts resampled to the first part's rate)
    sr, pos, cues = out.sr, int(out.sr * lead), []
    for i, p in enumerate(parts):
        n = len(resample(p.audio, sr).samples)
        if i and p.key == parts[i - 1].key:
            cues[-1]["end"] = (pos + n) / sr
        else:
            cues.append({"start": pos / sr, "end": (pos + n) / sr, "text": p.text})
        pos += n + (int(sr * p.pause) if i < len(parts) - 1 else 0)
    return out, cues


def speak_timed(text: str, voice: str | dict, language: str = "auto", speed: float = 1.0,
                engine: str | None = None, **opts) -> tuple[Audio, list[dict]]:
    """`speak`, plus one timing per original sentence: [{"start", "end", "text"}] in seconds."""
    lead, parts = speak_parts(text, voice, language, speed, engine, **opts)
    return join_parts(list(parts), lead)


MAX_TEXT = 5000                              # characters per Text to Speech request


def generate(text: str, voice: str | dict, language: str = "auto", speed: float = 1.0,
             engine: str | None = None, stability: float | None = None, expressiveness: float | None = None,
             **opts) -> dict:
    """Speak `text` and keep the result in history. Returns the history entry.

    `stability` / `expressiveness` are 0–1 sliders (0.5 = engine default). They are applied only when the
    engine supports them (see `Engine.controls`); `settings` in the entry lists what was applied."""
    from . import history
    from .engines import ENGINES

    text = (text or "").strip()
    if not text:
        raise ValueError("Text is empty")
    if len(text) > MAX_TEXT:
        raise ValueError(f"Text is too long ({len(text)} characters, max {MAX_TEXT})")
    if not 0.5 <= speed <= 2.0:
        raise ValueError("Speed must be between 0.5 and 2.0")
    v = _voice(voice)
    if engine and engine != v.get("engine") and engine not in voices.allowed_engines(v):
        raise ValueError(f"Engine '{engine}' not allowed for voice '{v.get('id')}'")
    used = engine or v.get("engine") or voices.DEFAULT_CLONE_ENGINE
    for name, x in (("stability", stability), ("expressiveness", expressiveness)):
        if x is None:
            continue
        if not 0.0 <= x <= 1.0:
            raise ValueError(f"{name.capitalize()} must be between 0 and 1")
        if name in ENGINES[used].controls:
            opts[name] = x
    audio, cues = speak_timed(text, v, language, speed=speed, engine=engine, **opts)
    return history.add(audio, text, v, language, used, {"speed": speed, **opts}, cues=cues)
