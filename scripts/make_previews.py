"""Pre-generate a 5–8 s preview clip (MP3) for every library voice → library/previews/<id>.mp3.

Usage: .venv/bin/python scripts/make_previews.py [--force] [--ids id1,id2]
Existing previews are kept unless --force. Sets each voice's `preview` field in the catalog."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import soundfile as sf  # noqa: E402

from voicer import library, tts  # noqa: E402

MIN_S, MAX_S = 5.0, 8.0
# Tried in order until the clip length is within MIN_S..MAX_S (longest first for slow voices → shortest).
TEXTS = {
    "en": ["Hello! This is a preview of my voice. I can read stories, the news, and anything you write.",
           "Hello! This is a preview of my voice. I can read anything you write for me.",
           "Hello! This is a preview of my voice. I can read stories, the news, lessons, and anything else you write for me."],
    "es": ["¡Hola! Esta es una muestra de mi voz. Puedo leer cuentos, noticias y todo lo que escribas.",
           "¡Hola! Esta es una muestra de mi voz. Puedo leer todo lo que escribas.",
           "¡Hola! Esta es una muestra de mi voz. Puedo leer cuentos, noticias, lecciones y todo lo que tú escribas para mí."],
}


def render(v: dict):
    best = None
    for text in TEXTS[v["language"]]:
        a = tts.speak(text, v, language=v["language"])
        dur = len(a.samples) / a.sr
        if MIN_S <= dur <= MAX_S:
            return a, dur
        if best is None or abs(dur - 6.5) < abs(best[1] - 6.5):
            best = (a, dur)
    a, dur = best
    if dur > MAX_S:                                   # still too long: gentle speed-up, then hard cap with fade
        a = tts.speak(TEXTS[v["language"]][1], v, language=v["language"], speed=min(1.25, dur / 7.5))
    n = int(MAX_S * a.sr)
    if len(a.samples) > n:
        a.samples = a.samples[:n].copy()
        f = int(0.2 * a.sr)
        a.samples[-f:] *= __import__("numpy").linspace(1, 0, f)
    return a, len(a.samples) / a.sr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--ids", default="")
    args = ap.parse_args()
    run(set(filter(None, args.ids.split(","))), args.force)


def run(want: set[str] = frozenset(), force: bool = False) -> None:
    """Render previews for `want` ids (all if empty); keep existing ones unless `force`."""
    data = json.loads(library.CATALOG.read_text())
    library.PREVIEWS.mkdir(parents=True, exist_ok=True)
    for v in sorted(data["voices"], key=lambda v: v["engine"]):     # group by engine → fewer model swaps
        if want and v["id"] not in want:
            continue
        out = library.PREVIEWS / f"{v['id']}.mp3"
        if out.exists() and not force:
            v["preview"] = f"previews/{out.name}"
            continue
        a, dur = render(v)
        sf.write(out, a.samples.clip(-1, 1), a.sr, format="MP3")
        v["preview"] = f"previews/{out.name}"
        print(f"{v['id']:45s} {dur:.1f}s", flush=True)
    tmp = library.CATALOG.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    tmp.replace(library.CATALOG)


if __name__ == "__main__":
    main()
