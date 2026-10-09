import pytest

from conftest import similar, transcribe

pytestmark = pytest.mark.gpu


@pytest.mark.parametrize("name,lang,text", [
    ("af_heart", "en", "Hello there, this is a preset voice speaking English."),
    ("bm_george", "en", "Good evening, and welcome to the news."),
    ("ef_dora", "es", "Hola, buenos días. Esta es una voz en español."),
    ("em_alex", "es", "El clima de hoy es soleado y agradable."),
])
def test_kokoro_presets(tmp_out, name, lang, text):
    from voicer import audio, tts

    v = {"id": name, "engine": "kokoro", "engine_voice": name}
    out = tts.synthesize(text, v, lang)
    assert out.sr == 24000 and len(out.samples) > out.sr
    p = audio.write_wav(out, tmp_out / f"kokoro_{name}.wav")
    assert similar(transcribe(p, lang), text) > 0.7
