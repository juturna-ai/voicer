import pytest

pytestmark = pytest.mark.browser


def test_shell_loads_and_navigates(page):
    page.goto(page.base + "/")
    page.wait_for_selector(".status.ok", timeout=10000)
    labels = [a.inner_text() for a in page.query_selector_all("#nav a")]
    assert labels == ["Text to Speech", "Voice Library", "My Voices", "Clone Voice", "Voice Changer", "Dialogue",
                      "Batch", "Dictionary", "History", "API & Agents", "Usage", "Settings"]
    for label in labels:                                # every entry opens its own section
        page.click(f"#nav >> text={label}")
        page.wait_for_selector(f"main h1:text-is(\"{label}\")")
        assert page.get_attribute(f"#nav >> text={label}", "aria-current") == "page"
    page.click("#nav >> text=Voice Library")
    page.wait_for_selector("h1:text-is(\"Voice Library\")")
    assert page.url.endswith("#library")


def _wav(path, seconds=2.0):
    import numpy as np
    import soundfile as sf

    t = np.arange(int(22050 * seconds)) / 22050
    sf.write(path, 0.3 * np.sin(2 * np.pi * 220 * t), 22050)
    return path


def test_clone_upload_by_browse_and_drop(page, tmp_path):
    page.goto(page.base + "/#clone")
    page.wait_for_selector("#dropzone")
    page.set_input_files("#clone-input", str(_wav(tmp_path / "first.wav", 2.0)))
    page.wait_for_selector("#clone-files li:has-text('first.wav')")
    # drag-and-drop: build a real File in the page and dispatch drop events on the zone
    page.evaluate("""() => {
      const sr = 8000, n = sr * 3, buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
      const w = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
      w(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); w(8, "WAVEfmt "); v.setUint32(16, 16, true);
      v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true);
      v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, "data"); v.setUint32(40, n * 2, true);
      for (let i = 0; i < n; i++) v.setInt16(44 + i * 2, Math.sin(i / 10) * 8000, true);
      const dt = new DataTransfer();
      dt.items.add(new File([buf], "dropped.wav", { type: "audio/wav" }));
      const zone = document.querySelector("#dropzone");
      zone.dispatchEvent(new DragEvent("dragover", { dataTransfer: dt, bubbles: true, cancelable: true }));
      zone.dispatchEvent(new DragEvent("drop", { dataTransfer: dt, bubbles: true, cancelable: true }));
    }""")
    page.wait_for_selector("#clone-files li:has-text('dropped.wav')")
    assert "0:05 total" in page.inner_text("#clone-total")
    page.click("button[aria-label='Remove first.wav']")
    page.wait_for_selector("#clone-files li:has-text('first.wav')", state="detached")
    assert "1 file(s)" in page.inner_text("#clone-total")


def test_clone_draft_survives_reload(page, tmp_path):
    page.goto(page.base + "/#clone")
    page.set_input_files("#clone-input", str(_wav(tmp_path / "keep.wav", 1.0)))
    page.wait_for_selector("#clone-files li:has-text('keep.wav')")
    page.reload()
    page.wait_for_selector("#clone-files li:has-text('keep.wav')")


def test_clone_record_from_mic(page):
    """Chromium's fake microphone (a beep) is recorded, uploaded as source=mic, and decodes server-side."""
    import json
    import urllib.request

    page.goto(page.base + "/#clone")
    page.click("#rec-start")
    page.wait_for_selector("#rec-stop")
    page.wait_for_timeout(2500)
    page.click("#rec-stop")
    page.wait_for_selector("#clone-files li:has-text('Recording 1')", timeout=10000)
    draft_id = page.evaluate("localStorage.getItem('clone-draft')")
    d = json.load(urllib.request.urlopen(f"{page.base}/api/clone/drafts/{draft_id}"))
    f = d["files"][-1]
    assert f["source"] == "mic" and 2.0 < f["seconds"] < 3.5, f
    from voicer import audio, clone

    a = audio.decode(clone.raw_path(draft_id, f["name"]))
    assert float((a.samples ** 2).mean() ** 0.5) > 0.01            # not silence
    assert page.query_selector("#rec-start")                      # back to idle


def test_clone_mic_blocked_shows_clear_error(live_server):
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context(permissions=[]).new_page()
        pg.goto(live_server + "/#clone")
        pg.click("#rec-start")
        pg.wait_for_selector("#clone-msg.error", timeout=10000)
        assert "icrophone" in pg.inner_text("#clone-msg")
        b.close()


def test_clone_auto_clean_shows_clips(page, tmp_path):
    import numpy as np
    import soundfile as sf

    from voicer import tts

    parts = []
    for s in ("The quick brown fox jumps over the lazy dog near the river bank.",
              "A gentle breeze moved through the tall grass on the quiet hill.") * 3:
        parts += [tts.synthesize(s, "piper-en-us-lessac-medium", "en").samples, np.zeros(22050, np.float32)]
    p = tmp_path / "speech.wav"
    sf.write(p, np.concatenate(parts), 22050)
    page.goto(page.base + "/#clone")
    page.set_input_files("#clone-input", str(p))
    page.wait_for_selector("#clone-clips li", timeout=30000)
    assert "clean speech" in page.inner_text("#clone-clips-msg")
    secs = page.eval_on_selector_all("#clone-clips li .muted", "els => els.map(e => e.textContent)")
    assert all("0:06" <= s <= "0:15" for s in secs), secs


def test_clone_quality_meter_warns_short(page, tmp_path):
    import numpy as np
    import soundfile as sf

    from voicer import tts

    a = tts.synthesize("This is a short sample of my voice for the test.", "piper-en-us-lessac-medium", "en")
    p = tmp_path / "short.wav"
    sf.write(p, a.samples, a.sr)
    page.goto(page.base + "/#clone")
    page.set_input_files("#clone-input", str(p))
    page.wait_for_selector(".qmeter.poor", timeout=30000)
    assert "at least 20 s" in page.inner_text("#clone-quality")
    assert "Poor" in page.inner_text(".qlabel")


def test_clone_auto_transcribe_and_edit(page, tmp_path):
    import numpy as np
    import soundfile as sf

    from voicer import tts

    a = tts.synthesize("The quick brown fox jumps over the lazy dog near the river bank.", "piper-en-us-lessac-medium", "en")
    p = tmp_path / "fox.wav"
    sf.write(p, np.concatenate([a.samples, np.zeros(a.sr, np.float32), a.samples]), a.sr)
    page.goto(page.base + "/#clone")
    page.set_input_files("#clone-input", str(p))
    page.wait_for_selector("#clone-clips textarea.transcript:not([disabled])", timeout=60000)
    assert "fox" in page.input_value("#clone-clips textarea").lower()
    page.fill("#clone-clips textarea", "Edited by hand.")
    page.dispatch_event("#clone-clips textarea", "change")
    page.wait_for_selector("#clone-clips textarea.saved")
    page.reload()
    page.wait_for_selector("#clone-clips textarea:not([disabled])")
    assert page.input_value("#clone-clips textarea") == "Edited by hand."


def test_clone_details_preview_then_save(page, tmp_path):
    import re

    from test_transcribe import EN, speech
    from voicer import voices

    p = speech(tmp_path / "me.wav", EN * 2, "piper-en-us-lessac-medium", "en")
    page.goto(page.base + "/#clone")
    assert page.is_disabled("#voice-preview") and page.is_disabled("#voice-save")
    page.set_input_files("#clone-input", str(p))
    page.wait_for_selector("#clone-clips textarea.transcript:not([disabled])", timeout=60000)
    page.fill("#voice-name", "Browser Voice")
    page.check("#voice-consent")
    assert page.is_disabled("#voice-save") and "preview" in page.inner_text("#voice-hint")
    page.fill("#voice-tags", "calm, test")
    page.fill("#voice-desc", "Saved from the browser test.")
    page.click("#voice-preview")
    page.wait_for_selector("#voice-msg.ok", timeout=180000)
    assert page.is_visible("#voice-audio")
    assert page.evaluate("document.querySelector('#voice-audio').duration") > 1
    assert page.is_enabled("#voice-save")
    page.click("#voice-save")
    page.wait_for_selector("#clone-msg.ok a[href='#voices']")
    vid = re.search(r"ID ([a-z0-9-]+)\)", page.inner_text("#clone-msg"))[1]
    v = voices.get(vid)
    assert v["name"] == "Browser Voice" and v["tags"] == ["calm", "test"] and v["preview"] == "preview.wav"
    assert page.evaluate("localStorage.getItem('clone-draft')") is None
    assert page.inner_text("#clone-files") == ""                  # fresh draft
    voices.delete(vid)


def test_blend_slider_preview_save(page):
    from voicer import voices

    page.goto(page.base + "/#blend")
    page.wait_for_selector("#blend-a option[value='xtts-daisy-studious']", state="attached")
    assert page.get_attribute("a[data-route='clone']", "class") == "active"
    assert page.is_disabled("#blend-preview") and page.is_disabled("#blend-save")
    page.select_option("#blend-a", "xtts-daisy-studious")
    page.select_option("#blend-b", "xtts-viktor-eka")
    page.fill("#blend-ratio", "60")
    assert page.inner_text("#blend-ratio-label") == "60% A · 40% B"
    page.fill("#blend-name", "UI Blend")
    assert page.is_disabled("#blend-save")                     # preview first
    page.click("#blend-preview")
    page.wait_for_selector("#blend-msg.ok", timeout=180000)
    assert page.evaluate("document.querySelector('#blend-audio').duration") > 1
    page.fill("#blend-ratio", "65")
    assert page.is_disabled("#blend-save")                     # ratio changed → preview again
    page.fill("#blend-ratio", "60")
    page.click("#blend-save")
    page.wait_for_selector("#blend-msg.ok a[href='#voices']", timeout=120000)
    vid = page.inner_text("#blend-msg").split("ID ")[1].split(")")[0]
    v = voices.get(vid)
    assert v["blend"]["ratio"] == 0.6 and v["name"] == "UI Blend"
    voices.delete(vid)


def test_tts_page_generate_and_play(page, tmp_path):
    from conftest import similar, transcribe

    page.goto(page.base + "/")                                  # Text to Speech is the start page
    page.wait_for_selector("h1:text-is('Text to Speech')")
    page.wait_for_selector("#tts-voice option[value='piper-en-us-lessac-medium']", state="attached")
    assert page.inner_text("#tts-count").startswith("0 / 5,000")
    assert page.is_disabled("#tts-generate")
    # searchable picker
    page.fill("#tts-search", "lessac")
    opts = page.eval_on_selector_all("#tts-voice option", "os => os.map(o => o.value)")
    assert opts == ["piper-en-us-lessac-medium"]
    page.select_option("#tts-voice", "piper-en-us-lessac-medium")
    assert "Lessac" in page.inner_text("#tts-voice-info")
    page.fill("#tts-search", "zzzz-nothing")
    assert "No voices match" in page.inner_text("#tts-voice")
    page.fill("#tts-search", "")
    text = "The library opens at nine in the morning."
    page.fill("#tts-text", text)
    assert page.inner_text("#tts-count").startswith(f"{len(text)} / 5,000")
    page.select_option("#tts-lang", "en")
    page.press("#tts-text", "Control+Enter")                    # keyboard shortcut generates
    page.wait_for_selector("#tts-msg.ok", timeout=60000)
    assert "saved to History" in page.inner_text("#tts-msg")
    src = page.get_attribute("#tts-audio", "src")
    wav = page.evaluate("async (u) => Array.from(new Uint8Array(await (await fetch(u)).arrayBuffer()))", src)
    (tmp_path / "tts.wav").write_bytes(bytes(wav))
    heard = transcribe(tmp_path / "tts.wav", "en")
    assert similar(heard, text) > 0.7, heard
    # text survives a section change; the voice choice survives a reload
    page.click("#nav >> text=History")
    page.click("#nav >> text=Text to Speech")
    assert page.input_value("#tts-text") == text
    page.reload()
    page.wait_for_selector("#tts-voice option[value='piper-en-us-lessac-medium']", state="attached")
    assert page.input_value("#tts-voice") == "piper-en-us-lessac-medium"



def test_tts_sliders_follow_engine_and_reach_api(page):
    page.goto(page.base + "/#tts")
    page.wait_for_selector("#tts-voice option[value='kokoro-af-heart']", state="attached")
    page.select_option("#tts-voice", "kokoro-af-heart")
    assert not page.is_disabled("#tts-speed")
    assert page.is_disabled("#tts-stability") and page.is_disabled("#tts-expressiveness")
    assert "speed only" in page.inner_text("#tts-controls-note")
    page.select_option("#tts-voice", "piper-en-us-lessac-medium")
    assert not page.is_disabled("#tts-stability") and not page.is_disabled("#tts-expressiveness")
    assert page.inner_text("#tts-controls-note") == ""
    page.fill("#tts-speed", "1.25")
    page.fill("#tts-stability", "80")
    page.fill("#tts-expressiveness", "20")
    assert page.inner_text("#tts-speed-val") == "1.25×" and page.inner_text("#tts-stability-val") == "80%"
    page.fill("#tts-text", "Good morning.")
    with page.expect_request("**/api/tts") as req:
        page.click("#tts-generate")
    assert req.value.post_data_json == {"text": "Good morning.", "voice": "piper-en-us-lessac-medium",
                                        "language": "auto", "speed": 1.25, "stability": 0.8, "expressiveness": 0.2}
    page.wait_for_selector("#tts-msg.ok", timeout=60000)
    # unsupported sliders are not sent; reset restores defaults
    page.select_option("#tts-voice", "kokoro-af-heart")
    with page.expect_request("**/api/tts") as req:
        page.click("#tts-generate")
    assert set(req.value.post_data_json) == {"text", "voice", "language", "speed"}
    page.wait_for_selector("#tts-msg.ok", timeout=60000)
    page.click("#tts-reset")
    assert page.input_value("#tts-speed") == "1" and page.input_value("#tts-stability") == "50"


def test_tts_tag_buttons_insert_and_are_not_spoken(page, tmp_path):
    from conftest import transcribe

    page.goto(page.base + "/#tts")
    page.wait_for_selector("#tts-voice option[value='piper-en-us-lessac-medium']", state="attached")
    page.select_option("#tts-voice", "piper-en-us-lessac-medium")
    assert len(page.query_selector_all(".tts-tags button")) == 9
    page.fill("#tts-text", "Hello there my friend.")
    page.eval_on_selector("#tts-text", "ta => ta.setSelectionRange(5, 5)")         # cursor after "Hello"
    page.click("button[data-tag='[pause 1s]']")
    assert page.input_value("#tts-text") == "Hello [pause 1s] there my friend."
    v = page.input_value("#tts-text")
    i = v.index("my friend")
    page.eval_on_selector("#tts-text", f"ta => ta.setSelectionRange({i}, {i + 9})")  # select "my friend"
    page.click("button[data-tag='[happy]']")
    v = page.input_value("#tts-text")
    assert "[happy] my friend [normal]" in v and page.evaluate("document.activeElement.id") == "tts-text"
    assert page.inner_text("#tts-count").startswith(f"{len(v)} / ")
    page.select_option("#tts-lang", "en")
    page.click("#tts-generate")
    page.wait_for_selector("#tts-msg.ok", timeout=60000)
    src = page.get_attribute("#tts-audio", "src")
    wav = page.evaluate("async (u) => Array.from(new Uint8Array(await (await fetch(u)).arrayBuffer()))", src)
    (tmp_path / "tags.wav").write_bytes(bytes(wav))
    heard = transcribe(tmp_path / "tags.wav", "en").lower()
    assert "hello" in heard and "friend" in heard
    assert not any(w in heard for w in ("pause", "happy", "normal", "bracket")), heard
    # full text: the tag is refused with a clear message, text unchanged
    page.fill("#tts-text", "a" * 5000)
    page.click("button[data-tag='[slow]']")
    assert page.input_value("#tts-text") == "a" * 5000
    assert "character limit" in page.inner_text("#tts-msg")


def test_tts_waveform_player(page):
    page.goto(page.base + "/#tts")
    page.wait_for_selector("#tts-voice option[value='piper-en-us-lessac-medium']", state="attached")
    page.select_option("#tts-voice", "piper-en-us-lessac-medium")
    page.fill("#tts-text", "One. [pause 1s] Two, three, four, five, six.")
    page.click("#tts-generate")
    page.wait_for_selector(".wave-player[data-ready='1']", timeout=60000)
    page.wait_for_function("document.querySelector('#tts-audio').duration > 1")
    dur = page.evaluate("document.querySelector('#tts-audio').duration")
    assert page.inner_text(".wave-time").endswith(f"0:0{int(dur)}")
    # the picture shows the audio: a quiet gap (the 1 s pause) between loud parts
    heights = page.evaluate("""() => {
      const c = document.querySelector('.wave'), ctx = c.getContext('2d'), out = [];
      const img = ctx.getImageData(0, 0, c.width, c.height).data;
      for (let x = 0; x < c.width; x += 3) { let n = 0;
        for (let y = 0; y < c.height; y++) if (img[(y * c.width + x) * 4 + 3] > 0) n++;
        out.push(n); }
      return out; }""")
    assert max(heights) > 0.6 * page.evaluate("document.querySelector('.wave').height")
    assert min(heights[len(heights) // 10: -len(heights) // 10]) < 0.1 * max(heights)
    # click in the middle seeks there; keys seek; play/pause button toggles
    page.click(".wave", position={"x": page.evaluate("document.querySelector('.wave').clientWidth") / 2, "y": 20})
    assert abs(page.evaluate("document.querySelector('#tts-audio').currentTime") - dur / 2) < 0.3
    page.focus(".wave")
    page.keyboard.press("Home")
    assert page.evaluate("document.querySelector('#tts-audio').currentTime") == 0
    page.keyboard.press("ArrowRight")
    assert abs(page.evaluate("document.querySelector('#tts-audio').currentTime") - 1) < 0.05
    assert page.get_attribute(".wave", "aria-valuenow") == "1"
    page.evaluate("document.querySelector('#tts-audio').pause()")
    page.click(".wave-play")
    page.wait_for_selector(".wave-play[aria-label='Pause']")
    page.click(".wave-play")
    page.wait_for_selector(".wave-play[aria-label='Play']")
    assert page.evaluate("document.querySelector('#tts-audio').paused")


def test_tts_download_buttons(page, tmp_path):
    import subprocess

    page.goto(page.base + "/#tts")
    page.wait_for_selector("#tts-voice option[value='piper-en-us-lessac-medium']", state="attached")
    page.select_option("#tts-voice", "piper-en-us-lessac-medium")
    page.fill("#tts-text", "Download me in three formats.")
    page.click("#tts-generate")
    page.wait_for_selector(".downloads a[data-format='ogg_opus']", timeout=60000)
    assert [a.inner_text() for a in page.query_selector_all(".downloads a[data-format]")] == ["MP3", "WAV", "OGG (WhatsApp voice note)"]
    for fmt, ext, codec in (("mp3", "mp3", "mp3"), ("wav", "wav", "pcm_s16le"), ("ogg_opus", "ogg", "opus")):
        with page.expect_download() as dl:
            page.click(f".downloads a[data-format='{fmt}']")
        d = dl.value
        assert d.suggested_filename.endswith(f".{ext}") and d.suggested_filename.startswith("voicer-")
        p = tmp_path / d.suggested_filename
        d.save_as(p)
        got = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(p)],
                             capture_output=True, text=True).stdout.strip()
        assert got == codec, (fmt, got)


def test_tts_subtitle_links(page, tmp_path):
    page.goto(page.base + "/#tts")
    page.wait_for_selector("#tts-voice option[value='piper-en-us-lessac-medium']", state="attached")
    page.select_option("#tts-voice", "piper-en-us-lessac-medium")
    page.fill("#tts-text", "First line of the subtitles. [pause 1s] Second line comes after a pause.")
    page.click("#tts-generate")
    page.wait_for_selector(".downloads a[data-subs='vtt']", timeout=60000)
    assert [a.inner_text() for a in page.query_selector_all(".downloads a[data-subs]")] == ["SRT", "VTT"]
    for fmt in ("srt", "vtt"):
        with page.expect_download() as dl:
            page.click(f".downloads a[data-subs='{fmt}']")
        d = dl.value
        assert d.suggested_filename.startswith("voicer-") and d.suggested_filename.endswith("." + fmt)
        p = tmp_path / d.suggested_filename
        d.save_as(p)
        body = p.read_text(encoding="utf-8")
        assert body.startswith("WEBVTT" if fmt == "vtt" else "1\n")
        assert "First line of the subtitles." in body and "Second line comes after a pause." in body
        assert "[pause" not in body


def test_voice_library_page(page):
    from voicer import voices

    page.goto(page.base + "/#library")
    page.wait_for_selector(".voice-card", timeout=10000)
    total = len(page.query_selector_all(".voice-card"))
    assert total >= 100
    assert page.inner_text("#lib-count") == f"{total} of {total} voices"
    card = page.query_selector(".voice-card[data-id='kokoro-af-heart']")
    assert "Heart (Kokoro)" in card.inner_text() and "Commercial use OK" in card.inner_text()
    assert card.query_selector("a").get_attribute("href").startswith("https://")
    # every filter narrows the grid to matching voices
    page.select_option("#lib-language", "es")
    es = len(page.query_selector_all(".voice-card"))
    assert 0 < es < total and all("Español" in c.inner_text() for c in page.query_selector_all(".voice-card"))
    page.select_option("#lib-gender", "male")
    page.select_option("#lib-engine", "piper")
    names = [c.get_attribute("data-id") for c in page.query_selector_all(".voice-card")]
    assert names and all(n.startswith("piper-es") for n in names)
    page.click("#lib-clear")
    page.wait_for_selector(f"#lib-count:text-is('{total} of {total} voices')")
    for sel, value, word in (("#lib-accent", "British", "British"), ("#lib-age", "middle-aged", "Middle-aged"),
                             ("#lib-style", "calm", "calm"), ("#lib-license", "Apache-2.0", "Apache-2.0")):
        page.select_option(sel, value)
        cards = page.query_selector_all(".voice-card")
        assert cards and all(word in c.inner_text() for c in cards), sel
        page.select_option(sel, "")
    page.check("#lib-commercial")
    assert all("Commercial use OK" in c.inner_text() for c in page.query_selector_all(".voice-card"))
    page.uncheck("#lib-commercial")
    page.fill("#lib-search", "zzzz-nothing")
    assert page.inner_text("#lib-grid") == "No voices match these filters."
    page.fill("#lib-search", "lessac")
    assert [c.get_attribute("data-id") for c in page.query_selector_all(".voice-card")] == ["piper-en-us-lessac-medium"]
    # preview plays, a second click stops it
    btn = ".voice-card[data-id='piper-en-us-lessac-medium'] .lib-play"
    page.click(btn)
    page.wait_for_function("preview.audio && preview.audio.currentTime > 0.3", timeout=10000)
    assert page.get_attribute(btn, "aria-pressed") == "true" and page.inner_text(btn) == "■ Stop"
    page.click(btn)
    assert page.evaluate("preview.audio.paused") and page.inner_text(btn) == "▶ Preview"
    # add to My Voices → button changes, voice is in the TTS picker
    page.click(".voice-card[data-id='piper-en-us-lessac-medium'] .lib-add")
    page.wait_for_selector(".voice-card[data-id='piper-en-us-lessac-medium'] .lib-add:text-is('✓ In My Voices')")
    assert page.is_disabled(".voice-card[data-id='piper-en-us-lessac-medium'] .lib-add")
    page.wait_for_selector("#toast.ok")
    mine = [v for v in voices.all_voices() if v.get("library_id") == "piper-en-us-lessac-medium"]
    try:
        assert len(mine) == 1
        page.goto(page.base + "/#tts")
        page.wait_for_selector(f"#tts-voice optgroup[label='My Voices'] option[value='{mine[0]['id']}']", state="attached")
    finally:
        for v in mine:
            voices.delete(v["id"])


def test_voice_library_phone_layout(page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(page.base + "/#library")
    page.wait_for_selector(".voice-card")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_my_voices_page(page):
    from voicer import library, voices

    v = library.add_to_my_voices("piper-en-us-lessac-medium")
    vid, made = v["id"], [v["id"]]
    try:
        page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=page.base)
        page.goto(page.base + "/#voices")
        card = f".voice-card[data-id='{vid}']"
        page.wait_for_selector(card)
        n = len(voices.all_voices())
        assert page.inner_text("#mv-count") == f"{n} of {n} voices"
        # preview plays, a second click stops it
        page.click(f"{card} .mv-play")
        page.wait_for_function("preview.audio && preview.audio.currentTime > 0.3", timeout=10000)
        assert page.get_attribute(f"{card} .mv-play", "aria-pressed") == "true"
        page.click(f"{card} .mv-play")
        assert page.evaluate("preview.audio.paused") and page.inner_text(f"{card} .mv-play") == "▶ Preview"
        # copy ID
        page.click(f"{card} .mv-copy")
        page.wait_for_selector(f"#toast.ok:text-is('Copied {vid}')")
        assert page.evaluate("navigator.clipboard.readText()") == vid
        # rename: the name field opens focused
        page.click(f"{card} .mv-rename")
        assert page.evaluate("document.activeElement.id") == "mv-name"
        page.fill("#mv-name", "Lessac Renamed")
        page.click(f"{card} button[type=submit]")
        page.wait_for_selector(f"{card} h3:text-is('Lessac Renamed')")
        # edit: tags, gender, description
        page.click(f"{card} .mv-edit-btn")
        page.fill("#mv-tags", "calm, narrator")
        page.fill("#mv-desc", "Test voice")
        page.select_option("#mv-gender", "female")
        page.click(f"{card} button[type=submit]")
        page.wait_for_selector(f"{card} .chip:text-is('narrator')")
        saved = voices.get(vid)
        assert saved["tags"] == ["calm", "narrator"] and saved["gender"] == "female"
        assert saved["description"] == "Test voice" and "Female" in page.inner_text(card)
        # cancel closes the form without saving
        page.click(f"{card} .mv-edit-btn")
        page.fill("#mv-name", "Not saved")
        page.click(f"{card} .mv-edit button.ghost")
        page.wait_for_selector(f"{card} h3:text-is('Lessac Renamed')")
        # duplicate
        page.click(f"{card} .mv-dup")
        page.wait_for_selector(".voice-card h3:text-is('Lessac Renamed (copy)')")
        dup = page.get_attribute(".voice-card:has(h3:text-is('Lessac Renamed (copy)'))", "data-id")
        made.append(dup)
        assert dup != vid and voices.get(dup)["duplicated_from"] == vid
        # set as default → badge, disabled button, TTS page starts with it
        page.click(f"{card} .mv-default")
        page.wait_for_selector(f"{card} .badge:text-is('★ Default')")
        assert page.is_disabled(f"{card} .mv-default") and voices.default_id() == vid
        page.goto(page.base + "/#tts")
        page.wait_for_function(f"document.querySelector('#tts-voice').value === '{vid}'")
        # delete: cancel keeps it, accept removes it
        page.goto(page.base + "/#voices")
        dcard = f".voice-card[data-id='{dup}']"
        page.wait_for_selector(dcard)
        page.once("dialog", lambda d: d.dismiss())
        page.click(f"{dcard} .mv-delete")
        page.wait_for_timeout(300)
        assert page.query_selector(dcard)
        page.once("dialog", lambda d: d.accept())
        page.click(f"{dcard} .mv-delete")
        page.wait_for_selector(dcard, state="detached")
        with pytest.raises(KeyError):
            voices.get(dup)
        # deleting the default clears it
        page.once("dialog", lambda d: d.accept())
        page.click(f"{card} .mv-delete")
        page.wait_for_selector(card, state="detached")
        assert voices.default_id() is None
        # search
        page.fill("#mv-search", "zzzz-nothing")
        assert "No voices" in page.inner_text("#mv-grid")
    finally:
        for x in made:
            try:
                voices.delete(x)
            except KeyError:
                pass
        voices.set_default(None)


def test_my_voices_phone_layout(page):
    from voicer import library, voices

    v = library.add_to_my_voices("piper-en-us-lessac-medium")
    try:
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(page.base + "/#voices")
        page.wait_for_selector(f".voice-card[data-id='{v['id']}']")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.click(f".voice-card[data-id='{v['id']}'] .mv-edit-btn")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    finally:
        voices.delete(v["id"])


def _hist(text, voice=("piper-en-us-lessac-medium", "Lessac (Piper)"), cues=True):
    import numpy as np

    from voicer import history
    from voicer.engines.base import Audio

    return history.add(Audio(np.zeros(24000, dtype=np.float32), 24000), text, {"id": voice[0], "name": voice[1]},
                       "en", "piper", cues=[{"start": 0.0, "end": 1.0, "text": text}] if cues else None)


def test_history_page(page):
    import time
    import uuid

    from voicer import history

    tag = uuid.uuid4().hex[:8]
    long_text = f"Old clip {tag}. " + "This sentence makes the text long. " * 10
    old = _hist(long_text)
    time.sleep(1.1)
    new = _hist(f"New clip {tag}.", cues=False)
    try:
        page.goto(page.base + "/#history")
        page.wait_for_selector("#hist-count:not(:text-is('Loading…'))")
        page.fill("#hist-search", tag)
        page.wait_for_selector("#hist-count:text-is('2 clips')")
        ids = [x.get_attribute("data-id") for x in page.query_selector_all(".hist-item")]
        assert ids == [new["id"], old["id"]]                               # newest first
        assert "null" not in page.inner_text("#hist-list")
        o, n = f".hist-item[data-id='{old['id']}']", f".hist-item[data-id='{new['id']}']"
        meta = page.inner_text(f"{o} .hist-meta")
        assert "Lessac (Piper)" in meta and "English" in meta and "Piper" in meta and "1.0 s" in meta
        assert page.get_attribute(f"{o} time", "datetime") == old["created"]
        # subtitles only where the clip has timings
        assert page.query_selector(f"{o} a[data-subs=srt]") and not page.query_selector(f"{n} a[data-subs]")
        # long text is cut to 3 lines until "Show more"
        assert "clamp" in page.get_attribute(f"{o} .hist-text", "class")
        page.click(f"{o} .hist-more")
        assert "clamp" not in page.get_attribute(f"{o} .hist-text", "class") and page.inner_text(f"{o} .hist-more") == "Show less"
        # download
        with page.expect_download() as dl:
            page.click(f"{n} a[data-format=mp3]")
        assert dl.value.suggested_filename == f"voicer-{new['id']}.mp3"
        # replay, second click stops
        page.click(f"{n} .hist-play")
        page.wait_for_function("preview.audio && preview.audio.currentTime > 0.3", timeout=10000)
        assert page.inner_text(f"{n} .hist-play") == "■ Stop"
        page.click(f"{n} .hist-play")
        assert page.evaluate("preview.audio.paused") and page.inner_text(f"{n} .hist-play") == "▶ Play"
        # delete: cancel keeps it, accept removes it
        page.once("dialog", lambda d: d.dismiss())
        page.click(f"{n} .hist-delete")
        page.wait_for_timeout(300)
        assert page.query_selector(n)
        page.once("dialog", lambda d: d.accept())
        page.click(f"{n} .hist-delete")
        page.wait_for_selector(n, state="detached")
        page.wait_for_selector("#hist-count:text-is('1 clip')")
        with pytest.raises(KeyError):
            history.get(new["id"])
        # use again → TTS page with the text and voice
        page.click(f"{o} .hist-use")
        page.wait_for_selector("#tts-text")
        assert page.input_value("#tts-text") == long_text
        page.wait_for_function("document.querySelector('#tts-voice').value === 'piper-en-us-lessac-medium'")
    finally:
        for e in (old, new):
            try:
                history.delete(e["id"])
            except KeyError:
                pass


def test_history_paging_and_empty_search(page):
    import uuid

    from voicer import history

    tag = uuid.uuid4().hex[:8]
    made = [_hist(f"Paging {tag} {i}", cues=False) for i in range(32)]
    try:
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(page.base + "/#history")
        page.fill("#hist-search", tag)
        page.wait_for_selector("#hist-count:text-is('32 clips')")
        assert len(page.query_selector_all(".hist-item")) == 30
        assert page.inner_text("#hist-more") == "Load more (2 left)"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")   # phone: no sideways scroll
        page.click("#hist-more")
        page.wait_for_function("document.querySelectorAll('.hist-item').length === 32")
        assert not page.query_selector("#hist-more")
        assert len({x.get_attribute("data-id") for x in page.query_selector_all(".hist-item")}) == 32
        page.fill("#hist-search", "zzzz-" + tag)
        page.wait_for_selector("#hist-list p:text-is('No clips match your search.')")
    finally:
        for e in made:
            history.delete(e["id"])


def test_api_page_key_and_examples_run(page, tmp_path):
    import os
    import subprocess
    import sys

    from voicer import apikey

    apikey.disable()
    try:
        page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=page.base)
        page.goto(page.base + "/#api")
        page.wait_for_selector("table.endpoints")
        assert page.inner_text("#api-base") == page.base
        paths = page.eval_on_selector_all("table.endpoints td:nth-child(2)", "els => els.map(e => e.textContent)")
        assert {"/api/tts", "/api/voices", "/api/api-key", "/api/history/{entry_id}/audio"} <= set(paths)
        page.wait_for_selector("#api-key-status:has-text('Off')")
        assert "Authorization" not in page.inner_text("#api-examples")
        # the examples use the voice named in the note (default voice, else first My Voice, else Lessac)
        import re

        vid = re.search(r"\(ID ([^)]+)\)", page.inner_text("#api-voice-note")).group(1)
        assert f'"voice": "{vid}"' in page.inner_text("#api-ex-1")
        # create a key: shown once, copyable, works, examples now send it
        page.click("#api-key-create")
        page.wait_for_selector("#api-key-value")
        key = page.inner_text("#api-key-value")
        assert key.startswith("vs_") and apikey.valid(key)
        page.click("#api-key-box .code-copy")
        page.wait_for_selector("#toast.ok:text-is('Copied.')")
        assert page.evaluate("navigator.clipboard.readText()") == key
        assert f"vs_…{key[-4:]}" in page.inner_text("#api-key-status")
        assert "null" not in page.inner_text("#api-key-box")
        assert 'Authorization: Bearer $VOICER_API_KEY' in page.inner_text("#api-examples")
        # the copy-ready examples really work (curl, then Python), with the key in the environment
        env = {**os.environ, "VOICER_API_KEY": key}
        curl = page.inner_text("#api-ex-1") + "\n" + page.inner_text("#api-ex-2") + "\n" + page.inner_text("#api-ex-3")
        subprocess.run(["bash", "-euc", curl], cwd=tmp_path, env=env, check=True, timeout=300, capture_output=True)
        assert (tmp_path / "speech.mp3").read_bytes()[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3")
        assert (tmp_path / "note.ogg").read_bytes()[:4] == b"OggS"
        assert "-->" in (tmp_path / "speech.srt").read_text()
        page.click(".api-tabs button[data-lang=python]")
        assert page.get_attribute(".api-tabs button[data-lang=python]", "aria-selected") == "true"
        py = tmp_path / "py"
        py.mkdir()
        (py / "ex.py").write_text(page.inner_text("#api-ex-0"))
        out = subprocess.run(["python3", "ex.py"], cwd=py, env=env, check=True, timeout=300, capture_output=True, text=True)
        assert out.stdout.startswith("Saved") and (py / "note.ogg").read_bytes()[:4] == b"OggS"
        # OpenAI SDK tab: the SDK snippet and the /v1 curl call work too
        page.click(".api-tabs button[data-lang=openai]")
        assert page.get_attribute(".api-tabs button[data-lang=openai]", "aria-selected") == "true"
        oa = tmp_path / "oa"
        oa.mkdir()
        (oa / "ex.py").write_text(page.inner_text("#api-ex-0"))
        subprocess.run([sys.executable, "ex.py"], cwd=oa, env=env, check=True, timeout=300, capture_output=True)
        assert (oa / "speech.mp3").read_bytes()[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3")
        subprocess.run(["bash", "-euc", page.inner_text("#api-ex-1")], cwd=oa, env=env, check=True, timeout=300,
                       capture_output=True)
        assert (oa / "note.ogg").read_bytes()[:4] == b"OggS"
        # after a reload the key is not shown again
        page.reload()
        page.wait_for_selector("#api-key-status:has-text('On')")
        assert not page.query_selector("#api-key-value") and key not in page.content()
        # replace (confirm) → new key, old one stops working
        page.once("dialog", lambda d: d.accept())
        page.click("#api-key-replace")
        page.wait_for_function(f"(document.querySelector('#api-key-value')?.textContent || '{key}') !== '{key}'")
        assert not apikey.valid(key) and apikey.valid(page.inner_text("#api-key-value"))
        # turn off (confirm)
        page.once("dialog", lambda d: d.accept())
        page.click("#api-key-off")
        page.wait_for_selector("#api-key-status:has-text('Off')")
        assert not apikey.status()["enabled"] and "Authorization" not in page.inner_text("#api-examples")
    finally:
        apikey.disable()


def test_api_page_phone_layout(page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(page.base + "/#api")
    page.wait_for_selector("table.endpoints")
    page.wait_for_selector("#mcp-ex-0")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert page.evaluate("document.querySelector('.table-wrap').scrollWidth <= document.querySelector('.table-wrap').clientWidth")


def test_api_page_mcp_snippets_work(page):
    """The MCP config snippets on the API page connect: HTTP, stdio and (in WSL) the Windows wsl.exe launcher."""
    import json
    import os
    import shutil
    import threading

    import anyio
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    from voicer import apikey

    def tools(server):
        out = {}

        def go():          # own thread: no event loop there, whatever Playwright does
            async def main():
                async with Client(server) as c:
                    out["tools"] = sorted(t.name for t in (await c.list_tools()).tools)
                    out["found"] = (await c.call_tool("search_voices", {"query": "lessac"})).structured_content["result"]
            anyio.run(main)
        th = threading.Thread(target=go)
        th.start()
        th.join(120)
        return out

    apikey.disable()
    page.goto(page.base + "/#api")
    page.wait_for_selector("#mcp-box #mcp-ex-0")
    assert "list_voices, search_voices, speak" in page.inner_text("#mcp-box") and "null" not in page.inner_text("#mcp-box")
    # HTTP (default tab): config file + Claude Code command
    cfg = json.loads(page.inner_text("#mcp-ex-0"))["mcpServers"]["voice-studio"]
    assert cfg == {"type": "http", "url": page.base + "/mcp"}
    assert page.inner_text("#mcp-ex-1") == f"claude mcp add --transport http voice-studio {page.base}/mcp"
    r = tools(cfg["url"])
    assert r["tools"] == ["list_voices", "search_voices", "speak"] and r["found"][0]["id"] == "piper-en-us-lessac-medium"
    # stdio: start the server exactly as the snippet says
    page.click(".mcp-tabs button[data-mcp=stdio]")
    assert page.get_attribute(".mcp-tabs button[data-mcp=stdio]", "aria-selected") == "true"
    assert page.get_attribute(".api-tabs button[data-lang=curl]", "aria-selected") == "true"   # other tabs untouched
    cfg = json.loads(page.inner_text("#mcp-ex-0"))["mcpServers"]["voice-studio"]
    r = tools(StdioServerParameters(command=cfg["command"], args=cfg["args"], env={**os.environ, **cfg["env"]}, cwd="/"))
    assert r["tools"] == ["list_voices", "search_voices", "speak"]
    # Windows apps: wsl.exe starts the stdio server inside this WSL distro
    if os.environ.get("WSL_DISTRO_NAME"):
        page.click(".mcp-tabs button[data-mcp=windows]")
        cfg = json.loads(page.inner_text("#mcp-ex-0"))["mcpServers"]["voice-studio"]
        assert cfg["command"] == "wsl.exe" and cfg["args"][:2] == ["-d", os.environ["WSL_DISTRO_NAME"]]
        if shutil.which("wsl.exe"):
            assert tools(StdioServerParameters(command="wsl.exe", args=cfg["args"]))["tools"] == ["list_voices", "search_voices", "speak"]
    # with the API key on, the HTTP snippets carry the header
    page.click(".mcp-tabs button[data-mcp=http]")
    try:
        page.click("#api-key-create")
        page.wait_for_selector("#api-key-value")
        cfg = json.loads(page.inner_text("#mcp-ex-0"))["mcpServers"]["voice-studio"]
        assert cfg["headers"] == {"Authorization": "Bearer YOUR_API_KEY"}
        assert '--header "Authorization: Bearer $VOICER_API_KEY"' in page.inner_text("#mcp-ex-1")
        assert "Replace YOUR_API_KEY" in page.inner_text("#mcp-box") and "null" not in page.inner_text("#mcp-box")
    finally:
        apikey.disable()
