import pytest

from conftest import similar, transcribe

pytestmark = pytest.mark.gpu


def test_xtts_clone_cross_lingual(tmp_out):
    from voicer import audio, tts, voices

    # Reference: a synthetic XTTS studio speaker (not a real person).
    studio = {"id": "studio", "engine": "xtts", "engine_voice": "Claribel Dervla"}
    ref = tts.synthesize("This is a reference recording for the voice studio. "
                         "It has a few sentences so that cloning works well.", studio, "en")
    ref_path = audio.write_wav(ref, tmp_out / "ref.wav")

    v = voices.create("Test Clone", kind="cloned", sample_files=[ref_path], language="en")
    assert v["engine"] == "xtts"  # default engine for cloned voices

    cases = {
        "es": "Hola, esta es una prueba de clonación de voz en español.",
        "en": "And this is the same cloned voice speaking English.",
    }
    for lang, text in cases.items():
        out = tts.synthesize(text, v["id"], lang)
        assert out.sr == 24000 and len(out.samples) > out.sr  # > 1 s of audio
        p = audio.write_wav(out, tmp_out / f"clone_{lang}.wav")
        heard = transcribe(p, lang)
        assert similar(heard, text) > 0.7, (lang, heard)
