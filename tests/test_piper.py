import pytest

from conftest import similar, transcribe


@pytest.mark.parametrize("name,lang,text", [
    ("es_MX-ald-medium", "es", "Hola, buenas tardes. ¿En qué te puedo ayudar?"),
    ("es_ES-davefx-medium", "es", "El tren sale de la estación a las ocho."),
    ("en_US-lessac-medium", "en", "The weather today is sunny and warm."),
    ("en_GB-alan-medium", "en", "Please mind the gap between the train and the platform."),
])
def test_piper_presets(tmp_out, name, lang, text):
    from voicer import audio, tts

    out = tts.synthesize(text, {"id": name, "engine": "piper", "engine_voice": name}, lang)
    assert len(out.samples) > out.sr
    p = audio.write_wav(out, tmp_out / f"piper_{name}.wav")
    assert similar(transcribe(p, lang), text) > 0.7
