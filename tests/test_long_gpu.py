import pytest

from conftest import similar, transcribe

pytestmark = pytest.mark.gpu


def test_long_text_xtts_no_cut_words(tmp_out):
    """A >600-char Spanish text through XTTS (200-char pieces) is fully spoken."""
    from voicer import audio, tts, voices

    text = ("La inteligencia artificial está cambiando la forma en que trabajamos, aprendemos y nos comunicamos. "
            "En muchas empresas, los asistentes de voz responden preguntas de clientes durante todo el día, "
            "sin descanso y con un tono amable; además, pueden atender a varias personas al mismo tiempo. "
            "Sin embargo, es importante revisar la calidad de las respuestas, cuidar la privacidad de los datos "
            "y explicar con claridad cuándo una persona está hablando con una máquina.\n\n"
            "Gracias por escuchar este mensaje.")
    assert len(text) > 450
    ref = tts.synthesize("This is a clean reference sample for the long text test.",
                         {"id": "s", "engine": "kokoro", "engine_voice": "af_heart"}, "en")
    v = voices.create("Long", sample_files=[audio.write_wav(ref, tmp_out / "long_ref.wav")], language="es")
    out = tts.speak(text, v["id"], "es")
    heard = transcribe(audio.write_wav(out, tmp_out / "long.wav"), "es")
    assert similar(heard, text) > 0.75, heard
    assert heard.rstrip(".").split()[-1].lower().startswith("mensaje")  # ending not cut
