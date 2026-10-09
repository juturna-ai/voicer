"""Final test, dictionary: the Dictionary page — words per language, add/change/delete, search, CSV import/export, listen."""
import json

import pytest

from voicer import dictionary

pytestmark = pytest.mark.browser


@pytest.fixture(autouse=True)
def clean():
    dictionary.import_csv("", replace=True)
    yield
    dictionary.import_csv("", replace=True)


def _open(page):
    page.goto(page.base + "/#dictionary")
    page.wait_for_selector("#dict-list > *")


def _rows(page):
    return page.eval_on_selector_all("#dict-table tbody tr", "rs => rs.map(r => [...r.cells].slice(0, 3).map(c => c.textContent))")


def test_add_change_delete_and_search(page):
    _open(page)
    assert page.inner_text("#dict-count") == "0 words" and "No words yet" in page.inner_text("#dict-list")
    page.click("#dict-save")
    assert "Type the word and how to say it." in page.inner_text("#dict-msg.error")
    page.fill("#dict-word", "WhatsApp")
    page.fill("#dict-spoken", "guatsap")
    page.click("#dict-save")
    page.wait_for_selector("#dict-msg.ok")
    page.select_option("#dict-lang", "en")
    page.fill("#dict-word", "SQL")
    page.press("#dict-spoken", "Tab")
    page.fill("#dict-spoken", "sequel")
    page.press("#dict-spoken", "Enter")                                                  # Enter adds too
    page.wait_for_selector("#dict-msg:has-text('Added “SQL”')")
    assert page.inner_text("#dict-count") == "2 words"
    assert _rows(page) == [["ES", "WhatsApp", "guatsap"], ["EN", "SQL", "sequel"]]
    assert dictionary.load() == {"es": {"WhatsApp": "guatsap"}, "en": {"SQL": "sequel"}}

    page.click("tr[data-word='WhatsApp'] .dict-edit")                                   # change → rename
    assert page.inner_text("#dict-save") == "Save change" and page.is_visible("#dict-cancel")
    assert page.input_value("#dict-lang") == "es" and page.input_value("#dict-word") == "WhatsApp"
    page.fill("#dict-word", "Whatsapp")
    page.fill("#dict-spoken", "uatsap")
    page.click("#dict-save")
    page.wait_for_selector("#dict-msg:has-text('Saved “Whatsapp”')")
    assert page.inner_text("#dict-save") == "Add word" and not page.is_visible("#dict-cancel")
    assert dictionary.load()["es"] == {"Whatsapp": "uatsap"}

    page.click("tr[data-word='SQL'] .dict-edit")                                        # move to the other language
    page.select_option("#dict-lang", "es")
    page.click("#dict-save")
    page.wait_for_selector("#dict-msg:has-text('Saved “SQL”')")
    assert dictionary.load() == {"es": {"SQL": "sequel", "Whatsapp": "uatsap"}, "en": {}}

    page.fill("#dict-search", "uats")
    assert _rows(page) == [["ES", "Whatsapp", "uatsap"]] and page.inner_text("#dict-count") == "1 of 2 words"
    page.fill("#dict-search", "zzz")
    assert "No words match." in page.inner_text("#dict-list")
    page.fill("#dict-search", "")

    page.once("dialog", lambda d: d.dismiss())                                          # Cancel keeps it
    page.click("tr[data-word='SQL'] .dict-del")
    assert "SQL" in dictionary.load()["es"]
    page.once("dialog", lambda d: d.accept())
    page.click("tr[data-word='SQL'] .dict-del")
    page.wait_for_selector("tr[data-word='SQL']", state="detached")
    assert dictionary.load()["es"] == {"Whatsapp": "uatsap"} and page.inner_text("#dict-count") == "1 word"

    page.fill("#dict-word", "x" * 150)                                                  # maxlength
    assert len(page.input_value("#dict-word")) == 100
    page.reload()
    page.wait_for_selector("tr[data-word='Whatsapp']")                                   # saved on the server


def test_csv_export_and_import(page, tmp_path):
    dictionary.set_entry("es", "Ñandú", "ñan-du")
    _open(page)
    with page.expect_download() as dl:
        page.click("#dict-export")
    assert dl.value.suggested_filename == "voicer-dictionary.csv"
    data = open(dl.value.path(), "rb").read()
    assert data.startswith(b"\xef\xbb\xbf") and "es,Ñandú,ñan-du" in data.decode("utf-8-sig")

    csv = "language;word;spoken\r\nes;Señal;se-ñal\r\nen;Voicer;voy-ser\r\nes;ñandú;nyandu\r\n".encode("cp1252")
    page.set_input_files("#dict-import-input", files=[{"name": "d.csv", "mimeType": "text/csv", "buffer": csv}])
    page.wait_for_selector("#toast:has-text('Imported 3 words.')")
    page.wait_for_selector("tr[data-word='Voicer']")
    assert dictionary.load() == {"es": {"ñandú": "nyandu", "Señal": "se-ñal"}, "en": {"Voicer": "voy-ser"}}
    assert page.inner_text("#dict-count") == "3 words"

    page.set_input_files("#dict-import-input", files=[{"name": "bad.csv", "mimeType": "text/csv", "buffer": b"fr,a,b\n"}])
    page.wait_for_selector("#toast:has-text('Row 1: Language must be es or en')")
    page.errors.clear()                                                                  # the expected 400 in the console
    assert dictionary.load()["en"] == {"Voicer": "voy-ser"}


@pytest.mark.gpu
def test_listen_to_the_form_and_to_a_word(page):
    dictionary.set_entry("en", "ASAP", "as soon as possible")
    _open(page)
    page.select_option("#dict-lang", "en")
    page.fill("#dict-spoken", "hello there")
    with page.expect_response("**/api/dictionary/listen", timeout=300000) as r:
        page.click("#dict-try")
    assert r.value.status == 200 and r.value.headers["content-type"] == "audio/wav"
    assert json.loads(r.value.request.post_data) == {"language": "en", "text": "hello there"}
    page.wait_for_selector("#dict-try:not([disabled])")
    with page.expect_response("**/api/dictionary/listen", timeout=300000) as r:
        page.click("tr[data-word='ASAP'] .dict-listen")
    assert json.loads(r.value.request.post_data) == {"language": "en", "text": "ASAP"}   # the word: the dictionary applies
    assert r.value.status == 200
    page.wait_for_function("dic.audio && dic.audio.src.startsWith('blob:') && dic.audio.duration > 0.5")  # a real clip
    page.wait_for_selector("tr[data-word='ASAP'] .dict-listen:has-text('▶')")


def test_spanish_labels(page):
    page.goto(page.base + "/#dictionary")
    page.evaluate("localStorage.setItem('ui-lang', 'es')")
    page.reload()
    page.wait_for_selector("#dict-count:has-text('palabras')")
    assert page.inner_text("h1") == "Diccionario" and page.inner_text("#dict-save") == "Añadir palabra"


def test_phone_width_has_no_sideways_scroll(page):
    dictionary.set_entry("es", "Supercalifragilisticoespialidoso" * 3, "una forma hablada muy larga " * 8)
    page.set_viewport_size({"width": 390, "height": 800})
    _open(page)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
