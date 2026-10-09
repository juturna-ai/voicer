import pytest


def test_catalog_sources_and_licenses():
    from voicer import library

    cat = library.catalog()
    assert {v["engine"] for v in cat} == {"kokoro", "piper", "xtts"}
    for v in cat:
        assert v["license"] and v["source_url"].startswith("http") and v["engine_voice"], v["id"]
        assert v["engine"] in ("kokoro", "piper", "xtts")
    ids = [v["id"] for v in cat]
    assert len(ids) == len(set(ids))
    banned = {"af_sky", "af_alloy", "af_nova", "am_echo", "am_onyx", "bm_fable"}
    assert not banned & {v["engine_voice"] for v in cat}


def test_find_by_library_id_and_name():
    from voicer import voices

    assert voices.find("kokoro-af-heart")["engine_voice"] == "af_heart"
    assert voices.find("Heart")["id"] == "kokoro-af-heart"
    assert voices.find("ald (piper)")["engine_voice"] == "es_MX-ald-medium"


def test_add_to_my_voices():
    from voicer import library, voices

    v = library.add_to_my_voices("piper-es-mx-ald-medium")
    assert v["kind"] == "preset" and v["library_id"] == "piper-es-mx-ald-medium"
    assert voices.get(v["id"])["engine_voice"] == "es_MX-ald-medium"


@pytest.mark.gpu
@pytest.mark.parametrize("vid", ["kokoro-ef-dora", "piper-es-es-sharvard-medium-1", "xtts-ana-florence"])
def test_one_voice_per_engine_speaks(vid):
    from voicer import tts

    out = tts.speak("Hola, esta es una prueba.", vid, "es")
    assert len(out.samples) > out.sr * 0.8


def test_library_size_and_language_mix():
    from voicer import library

    cat = library.catalog()
    es = [v for v in cat if v["language"] == "es"]
    en = [v for v in cat if v["language"] == "en"]
    assert len(cat) >= 30 and len(es) >= 10 and len(en) >= 10
    assert {v["accent"] for v in es} >= {"Mexican", "Argentine"}  # Latin American voices present
    assert library.search(language="es", accent="mexican")
