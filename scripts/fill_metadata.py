"""Fill missing gender / age / style tags in library/catalog.json from a short synthesized clip.

Usage: .venv/bin/python scripts/fill_metadata.py [--force] [--ids id1,id2]
Only empty fields are filled (unless --force). Filled fields are recorded in `estimated`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voicer import analysis, audio, config, library, tts  # noqa: E402

CLIPS = config.CACHE_DIR / "analysis"

TEXT = {
    "en": "Good morning, and welcome. Today we will take a short walk through the old town and its quiet gardens.",
    "es": "Buenos días y bienvenidos. Hoy daremos un paseo corto por el centro histórico y sus jardines tranquilos.",
}

# Values stated by the voice's own source (model card / dataset). These win over estimates.
DOCUMENTED = {
    "piper-en-us-sam-medium": {"gender": "neutral"},   # dataset: "Sam" non-binary voice project
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-estimate fields that are already set")
    ap.add_argument("--resynth", action="store_true", help="synthesize analysis clips again")
    ap.add_argument("--ids", default="", help="comma-separated voice ids (default: all)")
    args = ap.parse_args()
    run(set(filter(None, args.ids.split(","))), args.force, args.resynth)


def run(want: set[str] = frozenset(), force: bool = False, resynth: bool = False) -> None:
    """Fill metadata for `want` ids (all if empty). Peers for style ranks are always all voices."""
    args = argparse.Namespace(force=force, resynth=resynth)
    data = json.loads(library.CATALOG.read_text())
    feats: dict[str, dict] = {}
    by_base: dict[tuple, dict] = {}        # (engine, engine_voice, settings) → features: one clip per real voice
    for v in sorted(data["voices"], key=lambda v: v["engine"]):
        key = (v["engine"], v["engine_voice"], json.dumps(v.get("settings", {}), sort_keys=True))
        if key not in by_base:
            lang = v["language"] if v["engine"] != "xtts" else "en"
            text = TEXT[lang]
            clip = CLIPS / f"{v['id']}.wav"
            if clip.exists() and not args.resynth:
                a = audio.read(clip)
            else:
                a = tts.synthesize(text, v, lang)
                CLIPS.mkdir(parents=True, exist_ok=True)
                audio.write_wav(a, clip)
            by_base[key] = analysis.features(tts.trim(a), text)
            print(f"{v['id']:45s} f0={by_base[key]['f0']:.0f}", flush=True)
        feats[v["id"]] = by_base[key]

    for v in data["voices"]:
        if want and v["id"] not in want:
            continue
        f = feats[v["id"]]
        peers = [feats[p["id"]] for p in data["voices"] if p["language"] == v["language"]]
        est = set(v.get("estimated", []))
        for k, val in DOCUMENTED.get(v["id"], {}).items():
            v[k] = val
            est.discard(k)
        if args.force or not v.get("gender"):
            v["gender"] = analysis.gender(f)
            est.add("gender")
        if args.force or not v.get("age"):
            v["age"] = analysis.age(f, v["gender"])
            est.add("age")
        if args.force or not set(v.get("tags", [])) & set(analysis.STYLE_TAGS):
            keep = [t for t in v.get("tags", []) if t not in analysis.STYLE_TAGS]
            v["tags"] = keep + analysis.style_tags(f, peers)
            est.add("tags")
        v["estimated"] = sorted(est)
    tmp = library.CATALOG.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    tmp.replace(library.CATALOG)
    print("updated", len(data["voices"]), "voices")


if __name__ == "__main__":
    main()
