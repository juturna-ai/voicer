import pytest

from conftest import similar, transcribe

pytestmark = pytest.mark.gpu


def test_f5_clone_en_es(tmp_out):
    from voicer import audio, tts, voices

    studio = {"id": "studio", "engine": "xtts", "engine_voice": "Daisy Studious"}
    ref = tts.synthesize("This is a short reference clip. It is used to clone the voice.", studio, "en")
    ref_path = audio.write_wav(ref, tmp_out / "f5_ref.wav")

    v = voices.create("F5 Clone", kind="cloned", sample_files=[ref_path], engine="f5")
    assert v["engine"] == "f5"
    cases = {
        "en": "The quick brown fox jumps over the lazy dog.",
        "es": "Buenos días, ¿cómo estás? Hoy hace un día muy bonito.",
    }
    for lang, text in cases.items():
        out = tts.synthesize(text, v["id"], lang)
        assert len(out.samples) > out.sr
        p = audio.write_wav(out, tmp_out / f"f5_{lang}.wav")
        heard = transcribe(p, lang)
        assert similar(heard, text) > 0.6, (lang, heard)


def test_f5_does_not_break_python_subprocesses(tmp_out):
    """F5 seeds with a random number up to 2**63 and writes it to PYTHONHASHSEED (valid only up to 2**32 - 1):
    every Python started from this process afterwards (MCP stdio server, scripts) died at start-up."""
    import os
    import subprocess
    import sys

    from voicer import audio, tts, voices

    studio = {"id": "studio", "engine": "xtts", "engine_voice": "Daisy Studious"}
    ref = audio.write_wav(tts.synthesize("A short clip to clone this voice from.", studio, "en"), tmp_out / "f5_seed.wav")
    v = voices.create("F5 Seed", kind="cloned", sample_files=[ref], engine="f5")
    before = os.environ.get("PYTHONHASHSEED")
    tts.synthesize("Hello there.", v["id"], "en")
    after = os.environ.get("PYTHONHASHSEED")
    assert after == before
    subprocess.run([sys.executable, "-c", "pass"], check=True)
