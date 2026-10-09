import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def test_licenses_md_lists_every_voice_and_model_and_is_current():
    import make_licenses
    from voicer import library

    text = make_licenses.OUT.read_text()
    assert text == make_licenses.render(), "LICENSES.md is out of date: run scripts/make_licenses.py"
    for v in library.catalog():
        assert f"`{v['id']}`" in text
    for engine_model in ("XTTS-v2", "F5-TTS", "F5-Spanish", "Kokoro-82M", "Piper", "faster-whisper", "Vocos"):
        assert engine_model in text
    for m in make_licenses.MODELS:
        assert m[2] and m[4].startswith("https://")
