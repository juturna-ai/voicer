"""Phase 9: Batch page — upload .txt / .docx / .csv, progress bar, Stop, download all clips as one ZIP."""
import io
import json
import zipfile

import pytest

from conftest import similar, transcribe
from test_batch_files import _docx

pytestmark = pytest.mark.browser
EN = "piper-en-us-lessac-medium"


def _open(page):
    page.goto(page.base + "/#batch")
    page.wait_for_selector("#bat-voice optgroup", state="attached")


def test_batch_page_csv_progress_zip(page, tmp_path):
    from voicer import history

    _open(page)
    assert page.is_disabled("#bat-start")                              # nothing to do yet
    page.select_option("#bat-voice", EN)
    page.select_option("#bat-format", "ogg_opus")
    csv = ("text,filename,voice,language\n"
           "Good morning and welcome.,intro,,\n"
           "Hola a todos.,saludo,piper-es-mx-ald-medium,es\n"
           "This one fails.,bad,nobody,\n")
    page.set_input_files("#bat-input", files=[{"name": "show.csv", "mimeType": "text/csv", "buffer": csv.encode()}])
    page.wait_for_selector("#bat-list li >> nth=2")
    assert "3 clips found in show.csv" in page.inner_text("#bat-msg")
    assert page.inner_text("#bat-start") == "Generate 3 clips"
    assert "piper-es-mx-ald-medium · ES" in page.inner_text("#bat-row-1")   # an ID: another test may add a voice with the same name
    page.click("#bat-start")
    page.wait_for_selector("#bat-zip:not([hidden])", timeout=180000)
    assert page.eval_on_selector("#bat-progress", "p => [p.value, p.max]") == [3, 3]
    assert page.inner_text("#bat-progress-text") == "3 / 3 clips · 1 failed"
    assert "2 of 3 clips made" in page.inner_text("#bat-msg")
    assert "Voice 'nobody' not found" in page.inner_text("#bat-row-2 .bat-status.error")
    assert page.query_selector("#bat-row-0 .bat-status.ok")
    with page.expect_download() as dl:
        page.click("#bat-zip")
    assert dl.value.suggested_filename == "show.zip"
    z = zipfile.ZipFile(dl.value.path())
    assert sorted(z.namelist()) == ["001-intro.ogg", "002-saludo.ogg", "manifest.json"]
    assert z.read("001-intro.ogg")[:4] == b"OggS"
    m = json.loads(z.read("manifest.json"))
    assert m["items"][1]["voice_id"] == "piper-es-mx-ald-medium" and history.get(m["items"][0]["id"])["voice_id"] == EN
    (tmp_path / "a.ogg").write_bytes(z.read("001-intro.ogg"))
    assert similar(transcribe(tmp_path / "a.ogg", "en"), "Good morning and welcome.") > 0.8


def test_batch_page_docx_txt_stop_and_bad_file(page):
    _open(page)
    page.set_input_files("#bat-input", files=[{"name": "s.docx", "mimeType": "application/octet-stream",
                                               "buffer": _docx(["One.", "Two."])}])
    page.wait_for_selector("#bat-row-1")
    assert page.inner_text("#bat-start") == "Generate 2 clips"
    lines = "\n".join(f"Short line number {i}." for i in range(6))
    page.set_input_files("#bat-input", files=[{"name": "n.txt", "mimeType": "text/plain", "buffer": lines.encode()}])
    page.wait_for_selector("#bat-row-5")
    page.click("#bat-start")
    page.wait_for_selector("#bat-stop:not([hidden])")
    page.click("#bat-stop")
    page.wait_for_selector("#bat-zip:not([hidden])", timeout=120000)
    done = page.eval_on_selector("#bat-progress", "p => p.value")
    assert 1 <= done < 6 and page.inner_text("#bat-msg").startswith("Stopped.")
    assert page.is_enabled("#bat-start")
    page.set_input_files("#bat-input", files=[{"name": "x.pdf", "mimeType": "application/pdf", "buffer": b"%PDF"}])
    page.wait_for_selector("#bat-msg.error")
    assert "Upload a .txt, .docx or .csv file" in page.inner_text("#bat-msg")
    assert page.is_disabled("#bat-start") and page.is_hidden("#bat-list")
    page.errors[:] = [e for e in page.errors if "status of 400" not in e]   # the expected 400 reply
