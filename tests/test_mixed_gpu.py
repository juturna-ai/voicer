import pytest

from conftest import similar, transcribe

pytestmark = pytest.mark.gpu


def test_mixed_language_clone(tmp_out):
    """A cloned XTTS voice speaks a Spanish and an English sentence in one request."""
    from voicer import audio, tts, voices

    ref = tts.synthesize("This is the reference sample for the mixed language test, spoken clearly.",
                         {"id": "s", "engine": "xtts", "engine_voice": "Gracie Wise"}, "en")
    v = voices.create("Mixed", sample_files=[audio.write_wav(ref, tmp_out / "mixed_ref.wav")])
    es, en = "Hola, ¿cómo estás? Hoy vamos a la playa.", "The meeting starts at noon."
    a_es = tts.speak(es, v["id"])
    a_en = tts.speak(en, v["id"])
    a_mix = tts.speak(f"{es} {en}", v["id"])
    assert len(a_mix.samples) > len(a_es.samples) + len(a_en.samples) - a_mix.sr  # both parts present
    # second half of the mixed clip should be English
    tail = type(a_mix)(a_mix.samples[len(a_es.samples):], a_mix.sr)
    assert similar(transcribe(audio.write_wav(tail, tmp_out / "mix_tail.wav"), "en"), en) > 0.6
    head = type(a_mix)(a_mix.samples[:len(a_es.samples)], a_mix.sr)
    assert similar(transcribe(audio.write_wav(head, tmp_out / "mix_head.wav"), "es"), es) > 0.6
