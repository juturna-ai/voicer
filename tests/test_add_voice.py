import argparse
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def _args(**kw):
    base = dict(engine="piper", engine_voice="en_US-lessac-medium", name="Tester", id=None, speaker=None,
                language=None, accent="American", gender=None, age=None, license=None, license_url=None,
                source_url=None, description=None, tags="narrator", commercial=None)
    base.update(kw)
    return argparse.Namespace(**base)


def test_build_validates_and_reads_piper_card():
    import add_voice

    v = add_voice.build(_args(commercial="no"))
    assert v["id"] == "piper-en-us-lessac-medium" and v["language"] == "en"
    assert v["license"] and v["source_url"].startswith("http") and v["commercial"] is False
    with pytest.raises(SystemExit):                       # unknown engine
        add_voice.build(_args(engine="nope"))
    with pytest.raises(SystemExit):                       # commercial status must be stated
        add_voice.build(_args(engine="kokoro", engine_voice="af_heart", language="en",
                              license="Apache-2.0", source_url="https://huggingface.co/hexgrad/Kokoro-82M"))
    v = add_voice.build(_args(engine="xtts", engine_voice="Ana Florence", language="es", accent="Neutral",
                              license="CPML", source_url="https://coqui.ai/cpml"))
    assert v["commercial"] is False                        # non-commercial license detected


def test_add_voice_end_to_end(tmp_path, monkeypatch):
    import add_voice
    import fill_metadata  # noqa: F401
    import make_previews  # noqa: F401
    from voicer import library

    cat = json.loads(library.CATALOG.read_text())
    small = {"version": cat["version"], "voices": [v for v in cat["voices"]
                                                   if v["engine"] == "piper" and v["language"] == "en"][:3]}
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(small))
    monkeypatch.setattr(library, "CATALOG", path)
    monkeypatch.setattr(library, "PREVIEWS", tmp_path / "previews")
    monkeypatch.setattr(library, "_cache", None)

    v = add_voice.add(add_voice.build(_args(id="piper-test-lessac", commercial="no")), catalog=path)
    assert v["gender"] and v["age"] and {"narrator"} <= set(v["tags"]) and "estimated" in v
    assert library.preview_path(v) and library.preview_path(v).parent == tmp_path / "previews"
    with pytest.raises(SystemExit):                        # duplicate id refused
        add_voice.add(add_voice.build(_args(id="piper-test-lessac", commercial="no")), catalog=path)
