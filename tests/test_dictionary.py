import pytest


@pytest.fixture(autouse=True)
def clean():
    from voicer import dictionary
    dictionary.import_csv("", replace=True)
    yield
    dictionary.import_csv("", replace=True)


def test_entries_apply_per_language():
    from voicer import dictionary

    dictionary.set_entry("es", "WhatsApp", "guatsap")
    dictionary.set_entry("es", "Fami", "Fah-mee")
    dictionary.set_entry("en", "Fami", "Fah-mee")
    assert dictionary.apply("Escríbeme por whatsapp a Fami.", "es") == "Escríbeme por guatsap a Fah-mee."
    assert dictionary.apply("Use WhatsApp", "en") == "Use WhatsApp"          # es-only entry
    assert dictionary.apply("Famiglia", "es") == "Famiglia"                  # whole words only
    dictionary.delete_entry("es", "Fami")
    assert dictionary.apply("Fami", "es") == "Fami"
    with pytest.raises(ValueError):
        dictionary.set_entry("fr", "a", "b")


def test_csv_roundtrip():
    from voicer import dictionary

    n = dictionary.import_csv("language,word,spoken\nes,WhatsApp,guatsap\nen,SQL,sequel\nes,Dr. Who,doctor Hu\n")
    assert n == 3
    csv = dictionary.export_csv()
    assert "es,WhatsApp,guatsap" in csv and "en,SQL,sequel" in csv
    dictionary.import_csv("", replace=True)
    assert dictionary.load() == {"es": {}, "en": {}}
    dictionary.import_csv(csv)
    assert dictionary.load()["en"] == {"SQL": "sequel"}


def test_plan_uses_dictionary_before_normalize():
    from voicer import dictionary, tts

    dictionary.set_entry("es", "WhatsApp", "guatsap")
    dictionary.set_entry("es", "24/7", "veinticuatro siete")
    segs = tts.plan("Atendemos por WhatsApp 24/7.", "es")
    assert segs[0].text == "Atendemos por guatsap veinticuatro siete."


def test_persisted_to_disk():
    from voicer import config, dictionary
    import json

    dictionary.set_entry("en", "GIF", "jif")
    assert json.loads((config.DATA_DIR / "dictionary.json").read_text())["en"]["GIF"] == "jif"
