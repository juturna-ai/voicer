"""Multi-speaker dialogue: a script of `Speaker: text` lines, one voice per speaker, one audio file.

    Ann: Hi Ben, are you ready?
    Ben: Almost. Give me a minute.

A line without `Name:` continues the previous speaker's turn. Each turn is spoken with the full Text to
Speech pipeline (tags, language per sentence, dictionary), turns are levelled to the same loudness and
joined with a short gap. The result is saved to History with one subtitle cue per sentence (`Name: text`)."""
from __future__ import annotations

import re

import numpy as np

from . import history, tts, voices
from .engines.base import Audio

SPEAKER = re.compile(r"^\s*([^:\[\]]{1,40}?)\s*:\s*(.*)$")
MAX_SPEAKERS = 10
GAP = 0.4                    # seconds of silence between turns (default)
TARGET_RMS = 10 ** (-20 / 20)  # each turn levelled to −20 dBFS RMS, peak kept under −1 dBFS


def parse(script: str) -> list[tuple[str, str]]:
    """`[(speaker, text), …]`, one per turn. Raises ValueError with the line number on a bad script."""
    turns: list[list[str]] = []
    seen: dict[str, str] = {}                    # "ann" → "Ann": a name is the same speaker in any case
    for n, line in enumerate((script or "").splitlines(), 1):
        if not line.strip():
            continue
        m = SPEAKER.match(line)
        if m and m.group(1).strip():
            name = seen.setdefault(m.group(1).strip().lower(), m.group(1).strip())
            turns.append([name, m.group(2).strip()])
        elif turns:
            turns[-1][1] = f"{turns[-1][1]} {line.strip()}".strip()
        else:
            raise ValueError(f"Line {n} has no speaker. Start each turn with 'Name: text'")
    turns = [t for t in turns if t[1]]
    if not turns:
        raise ValueError("Script is empty. Write lines like 'Ann: Hello.'")
    return [(s, t) for s, t in turns]


def speakers(script: str) -> list[str]:
    """Speaker names in order of first appearance."""
    return list(dict.fromkeys(s for s, _ in parse(script)))


def _voice_for(name: str, cast: dict[str, str]) -> str:
    if name in cast:
        return cast[name]
    low = {k.strip().lower(): v for k, v in cast.items()}
    if name.lower() in low:
        return low[name.lower()]
    raise ValueError(f"No voice for speaker '{name}'")


def _level(a: Audio) -> Audio:
    x = a.samples
    rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
    if rms < 1e-5:
        return a
    gain = min(TARGET_RMS / rms, 0.89 / (float(np.max(np.abs(x))) or 1.0))
    return Audio((x * gain).astype(np.float32), a.sr)


def generate(script: str, cast: dict[str, str], language: str = "auto", speed: float = 1.0,
             gap: float = GAP) -> dict:
    """Speak `script` with `cast` (speaker → voice ID or name). Returns the History entry."""
    script = (script or "").strip()
    if len(script) > tts.MAX_TEXT:
        raise ValueError(f"Script is too long ({len(script)} characters, max {tts.MAX_TEXT})")
    if not 0.5 <= speed <= 2.0:
        raise ValueError("Speed must be between 0.5 and 2.0")
    if not 0.0 <= gap <= 3.0:
        raise ValueError("Gap must be between 0 and 3 seconds")
    turns = parse(script)
    names = list(dict.fromkeys(s for s, _ in turns))
    if len(names) > MAX_SPEAKERS:
        raise ValueError(f"Too many speakers ({len(names)}, max {MAX_SPEAKERS})")
    voice = {n: tts._voice(_voice_for(n, cast)) for n in names}      # unknown voice → KeyError before any work

    parts, cues, sr, pos = [], [], None, 0
    for i, (name, text) in enumerate(turns):
        a, turn_cues = tts.speak_timed(text, voice[name], language, speed)
        sr = sr or a.sr
        a = _level(tts.resample(a, sr))
        for c in turn_cues:
            cues.append({"start": round(pos / sr + c["start"], 3), "end": round(pos / sr + c["end"], 3),
                         "text": f"{name}: {c['text']}"})
        parts.append(a)
        pos += len(a.samples) + (int(sr * gap) if i < len(turns) - 1 else 0)
    audio = tts.concat(parts, gap)

    first = voice[names[0]]
    label = {"id": first.get("id"), "name": "Dialogue: " + ", ".join(f"{n} ({voice[n].get('name')})" for n in names)}
    engines = sorted({v.get("engine") or voices.DEFAULT_CLONE_ENGINE for v in voice.values()})
    settings = {"speed": speed, "gap": gap, "dialogue": {n: voice[n].get("id") for n in names}}
    return history.add(audio, script, label, language, "+".join(engines), settings, cues=cues)
