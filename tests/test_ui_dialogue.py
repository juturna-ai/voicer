"""Phase 9: Dialogue page — `Name: text` script, a voice per speaker, one output file."""
import urllib.request

import pytest

from conftest import similar, transcribe

pytestmark = pytest.mark.browser

ANN, BEN = "piper-en-us-lessac-medium", "piper-en-us-ryan-high"
SCRIPT = "Ann: Good morning, Ben. Did you sleep well?\nben: Yes, thank you.\nI feel great today.\nAnn: Then let us go."
SPOKEN = "Good morning, Ben. Did you sleep well? Yes, thank you. I feel great today. Then let us go."


def _open(page):
    page.goto(page.base + "/#dialogue")
    page.wait_for_selector("#dlg-cast[data-ready='1']")


def test_dialogue_page_cast_generate_play_download(page, tmp_path):
    from voicer import history

    _open(page)
    assert page.is_disabled("#dlg-generate")                      # no script yet
    page.fill("#dlg-script", SCRIPT)
    assert page.eval_on_selector_all("#dlg-cast select", "s => s.map(x => x.dataset.speaker)") == ["Ann", "ben"]
    first = page.eval_on_selector_all("#dlg-cast select", "s => s.map(x => x.value)")
    assert all(first) and first[0] != first[1]                    # each speaker starts with its own voice
    page.select_option("#dlg-voice-0", ANN)
    page.select_option("#dlg-voice-1", BEN)
    page.eval_on_selector("#dlg-gap", "e => { e.value = 0.8; e.dispatchEvent(new Event('input')); }")
    assert page.inner_text("#dlg-gap-val") == "0.8 s"
    page.click("#dlg-generate")
    page.wait_for_selector("#dlg-result .wave-player[data-ready='1']", timeout=180000)
    assert "saved to History" in page.inner_text("#dlg-msg")
    href = page.get_attribute("#dlg-result a[data-format='wav']", "href")
    e = history.get(href.split("/")[3])
    assert e["settings"]["dialogue"] == {"Ann": ANN, "ben": BEN} and e["settings"]["gap"] == 0.8
    assert e["voice_name"].startswith("Dialogue: Ann")
    out = tmp_path / "d.wav"
    out.write_bytes(urllib.request.urlopen(page.base + href).read())
    assert similar(transcribe(out, "en"), SPOKEN) > 0.8
    assert page.query_selector("#dlg-result a[data-subs='srt']")

    page.reload()                                                 # the cast is remembered per speaker name
    page.wait_for_selector("#dlg-cast[data-ready='1']")
    page.fill("#dlg-script", "ANN: Hello.\nBen: Hi.")
    assert page.eval_on_selector_all("#dlg-cast select", "s => s.map(x => x.value)") == [ANN, BEN]


def test_dialogue_page_errors(page):
    _open(page)
    page.fill("#dlg-script", "\n".join(f"P{i}: Hello." for i in range(11)))
    assert "Too many speakers (11, max 10)" in page.inner_text("#dlg-cast-msg") and page.is_disabled("#dlg-generate")
    page.fill("#dlg-script", "Hello there.\nAnn: Hi.")            # text before the first speaker: the server says where
    assert page.is_enabled("#dlg-generate")
    page.click("#dlg-generate")
    page.wait_for_selector("#dlg-msg.error")
    assert "Line 1 has no speaker" in page.inner_text("#dlg-msg")
    page.errors[:] = [e for e in page.errors if "status of 400" not in e]   # the expected 400 reply
