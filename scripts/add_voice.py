"""Add a preset voice to the Voice Library (library/catalog.json), then fill metadata and render its preview.

Examples:
  # Piper: license and source are read from the voice's MODEL_CARD
  .venv/bin/python scripts/add_voice.py --engine piper --engine-voice es_MX-ald-medium --name "Ald" --accent Mexican \\
      --confirm-not-real-person
  # Kokoro / XTTS studio speaker: give license info yourself
  .venv/bin/python scripts/add_voice.py --engine kokoro --engine-voice ef_dora --name Dora --language es --accent Spain \\
      --license Apache-2.0 --license-url https://www.apache.org/licenses/LICENSE-2.0 \\
      --source-url https://huggingface.co/hexgrad/Kokoro-82M --commercial yes --confirm-not-real-person

Rules (features.md): open-license voices only; record license + source; no voices that imitate real or famous people."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voicer import library, tts  # noqa: E402
from voicer.engines import ENGINES  # noqa: E402

PIPER_HF = "https://huggingface.co/rhasspy/piper-voices"
NON_COMMERCIAL = re.compile(r"\bnc\b|non-?commercial|cpml|coqui public", re.I)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def piper_card(engine_voice: str) -> dict:
    """Language, accent-region, license and dataset URL from a Piper voice's MODEL_CARD."""
    import urllib.request

    lang, name, quality = engine_voice.split("-", 2)
    path = f"{lang.split('_')[0]}/{lang}/{name}/{quality}"
    with urllib.request.urlopen(f"{PIPER_HF}/raw/main/{path}/MODEL_CARD", timeout=20) as r:
        card = r.read().decode()
    get = lambda key: (re.search(rf"\* {key}: (.+)", card) or [None, ""])[1].strip()  # noqa: E731
    return {"language": lang.split("_")[0], "source_url": get("URL"), "license": get("License"),
            "model_url": f"{PIPER_HF}/tree/main/{path}"}


def build(a: argparse.Namespace) -> dict:
    if a.engine not in ENGINES:
        raise SystemExit(f"Unknown engine '{a.engine}'. Choose: {', '.join(ENGINES)}")
    v = {"engine": a.engine, "engine_voice": a.engine_voice, "kind": "preset", "settings": {}}
    if a.engine == "piper":
        v.update(piper_card(a.engine_voice))
        if a.speaker is not None:
            v["settings"]["speaker_id"] = a.speaker
    for k in ("language", "accent", "gender", "age", "license", "license_url", "source_url", "description"):
        if getattr(a, k):
            v[k] = getattr(a, k)
    v["name"] = f"{a.name} ({a.engine.upper() if a.engine == 'xtts' else a.engine.capitalize()})"
    v["tags"] = [t.strip() for t in (a.tags or "").split(",") if t.strip()]
    v["id"] = a.id or "-".join(filter(None, [a.engine, slug(a.engine_voice),
                                              None if a.speaker is None else str(a.speaker)]))
    lic = v.get("license", "")
    if a.commercial is None:                         # infer only "no"; never assume commercial use is OK
        if not NON_COMMERCIAL.search(lic):
            raise SystemExit("Give --commercial yes|no (could not tell from the license).")
        v["commercial"] = False
    else:
        v["commercial"] = a.commercial == "yes"
    for k in ("language", "accent", "license", "source_url"):
        if not v.get(k):
            raise SystemExit(f"Missing --{k.replace('_', '-')}")
    if not v["source_url"].startswith("http"):
        raise SystemExit("--source-url must be a URL")
    if v["language"] not in tts.LANGS:
        raise SystemExit(f"Language must be one of {tts.LANGS}")
    if "See URL" in lic:
        raise SystemExit("License not stated in the model card. Check it by hand and pass --license.")
    v["description"] = v.get("description", "")
    v["age"] = v.get("age", "")
    v["gender"] = v.get("gender", "")
    return v


def add(v: dict, catalog: Path | None = None, previews: bool = True) -> dict:
    catalog = catalog or library.CATALOG
    data = json.loads(catalog.read_text())
    if any(x["id"] == v["id"] for x in data["voices"]):
        raise SystemExit(f"Voice id '{v['id']}' already in the library")
    tts.synthesize("Test." if v["language"] == "en" else "Prueba.", v, v["language"])   # fails early if unusable
    data["voices"].append(v)
    tmp = catalog.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    tmp.replace(catalog)
    if previews:
        import fill_metadata
        import make_previews

        fill_metadata.run({v["id"]})
        make_previews.run({v["id"]})
    return library.get(v["id"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", required=True)
    ap.add_argument("--engine-voice", required=True, help="Kokoro voice, Piper voice key, or XTTS speaker name")
    ap.add_argument("--name", required=True, help="display name (not a real person's name)")
    ap.add_argument("--id")
    ap.add_argument("--speaker", type=int, help="Piper multi-speaker id")
    for k in ("language", "accent", "gender", "age", "license", "license-url", "source-url", "description", "tags"):
        ap.add_argument(f"--{k}")
    ap.add_argument("--commercial", choices=["yes", "no"])
    ap.add_argument("--confirm-not-real-person", action="store_true", required=True,
                    help="you confirm the voice does not imitate a real or famous person")
    a = ap.parse_args()
    v = add(build(a))
    import make_licenses

    make_licenses.OUT.write_text(make_licenses.render())
    print(json.dumps(v, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
