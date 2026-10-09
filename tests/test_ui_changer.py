"""Phase 9: Voice Changer page — record or upload speech, pick a voice, convert, play and download."""
import urllib.request

import pytest

from conftest import similar, transcribe

pytestmark = pytest.mark.browser

SRC_VOICE = "piper-en-us-lessac-medium"
TARGET = "kokoro-am-michael"
TEXT = "Good morning everyone. The meeting starts in ten minutes, so please take your seats."


def test_changer_record_from_mic_shows_the_recording(page):
    page.goto(page.base + "/#changer")
    page.wait_for_selector("#vc-voice option[value='kokoro-af-heart']")
    assert page.is_disabled("#vc-convert")                         # nothing to convert yet
    page.click("#vc-rec-start")
    page.wait_for_selector("#vc-rec-stop")
    page.wait_for_timeout(1500)
    page.click("#vc-rec-stop")
    page.wait_for_selector("#vc-source:has-text('Recording 1')", timeout=10000)
    assert page.query_selector("#vc-source audio") and page.query_selector("#vc-rec-start")
    assert page.is_enabled("#vc-convert")
    page.click("#vc-clear")
    page.wait_for_selector("#vc-source", state="hidden")
    assert page.is_disabled("#vc-convert")


def test_changer_rejects_a_file_that_is_not_audio(page, tmp_path):
    (tmp_path / "notes.txt").write_text("hello")
    page.goto(page.base + "/#changer")
    page.wait_for_selector("#vc-voice option[value='kokoro-af-heart']")
    page.set_input_files("#vc-input", str(tmp_path / "notes.txt"))
    page.wait_for_selector("#vc-msg.error")
    assert "audio" in page.inner_text("#vc-msg").lower() and page.is_disabled("#vc-convert")


@pytest.mark.gpu
def test_changer_upload_convert_play_download(page, tmp_path):
    from voicer import audio, history, tts

    src = tmp_path / "me.wav"
    audio.write_wav(tts.speak(TEXT, SRC_VOICE, "en"), src)
    page.goto(page.base + "/#changer")
    page.wait_for_selector(f"#vc-voice option[value='{TARGET}']")
    page.set_input_files("#vc-input", str(src))
    page.wait_for_selector("#vc-source:has-text('me.wav')")
    page.fill("#vc-search", "michael")                              # the search narrows the list
    assert page.eval_on_selector_all("#vc-voice option", "o => o.map(x => x.value)") == [TARGET]
    page.select_option("#vc-voice", TARGET)
    page.click("#vc-convert")
    page.wait_for_selector("#vc-result .wave-player[data-ready='1']", timeout=300000)
    assert "saved to History" in page.inner_text("#vc-msg")
    href = page.get_attribute("#vc-result a[data-format='ogg_opus']", "href")
    entry_id = href.split("/")[3]
    e = history.get(entry_id)
    assert e["voice_id"] == TARGET and e["engine"] == "openvoice" and e["settings"]["source"] == "me.wav"
    assert "&download=true" in href and page.query_selector("#vc-result a[data-subs='srt']")
    out = tmp_path / "out.ogg"
    out.write_bytes(urllib.request.urlopen(page.base + href).read())
    assert out.read_bytes()[:4] == b"OggS"
    assert similar(transcribe(out, "en"), TEXT) > 0.8
    page.click("#vc-result .wave-play")
    page.wait_for_function("document.querySelector('#vc-audio').currentTime > 0.2", timeout=10000)


@pytest.mark.gpu
def test_changer_subtitles_only_downloads_an_srt(page, tmp_path):
    from voicer import audio, history, tts

    src = tmp_path / "talk.wav"
    audio.write_wav(tts.speak(TEXT, SRC_VOICE, "en"), src)
    before = len(history.entries())
    page.goto(page.base + "/#changer")
    page.wait_for_selector("#vc-voice option", state="attached")
    assert page.is_disabled("#vc-subs")                              # nothing to transcribe yet
    page.set_input_files("#vc-input", str(src))
    page.wait_for_selector("#vc-source:has-text('talk.wav')")
    page.select_option("#vc-lang", "en")
    with page.expect_download(timeout=300000) as dl:
        page.click("#vc-subs")
    assert dl.value.suggested_filename == "talk.srt"
    srt = open(dl.value.path(), encoding="utf-8").read()
    assert srt.startswith("1\n00:00:0") and " --> " in srt
    assert similar(" ".join(l for l in srt.splitlines() if l and "-->" not in l and not l.isdigit()), TEXT) > 0.85
    page.wait_for_selector("#vc-msg.ok:has-text('talk.srt')")
    assert page.is_enabled("#vc-subs") and page.inner_text("#vc-subs") == "Subtitles only (SRT)"
    assert len(history.entries()) == before                           # nothing saved
