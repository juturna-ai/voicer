"""Final end-to-end test: the app as a user runs it (`./start.sh`, fresh data folder, real browser, real models).

One test per item of the "Final end-to-end test" list in features.md, in the same order. Slow (loads every model).
"""
import os
import signal
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from conftest import similar, transcribe
from test_formats import probe
from test_scripts import ROOT, _free_port

pytestmark = [pytest.mark.gpu, pytest.mark.browser]


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    """`./start.sh` on a free port with an empty data folder. Yields the base URL (http://localhost:PORT)."""
    port = _free_port()
    data = tmp_path_factory.mktemp("e2e-data")
    log = open(data.parent / "server.log", "w")
    env = {**os.environ, "VOICER_PORT": str(port), "VOICER_DATA": str(data)}
    proc = subprocess.Popen([ROOT / "start.sh"], env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    url = f"http://localhost:{port}"
    for _ in range(120):
        try:
            if httpx.get(f"{url}/api/health").json()["status"] == "ok":
                break
        except httpx.HTTPError:
            time.sleep(0.5)
    else:
        pytest.fail("the server did not start")
    yield url, data
    os.killpg(proc.pid, signal.SIGINT)
    assert proc.wait(timeout=60) == 0                     # stops cleanly after the whole run


@pytest.fixture(scope="module")
def browser():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                                    "--autoplay-policy=no-user-gesture-required"])
        yield b
        b.close()


@pytest.fixture()
def page(app, browser):
    ctx = browser.new_context(permissions=["microphone"], accept_downloads=True)
    pg = ctx.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
    pg.base, pg.errors = app[0], errors
    yield pg
    ctx.close()
    assert not errors, errors


def test_01_browse_library_and_play_previews(app, page, tmp_path):
    url = app[0]
    voices = httpx.get(f"{url}/api/library").json()
    assert len(voices) >= 100 and {v["engine"] for v in voices} >= {"kokoro", "piper", "xtts"}
    assert {v["language"] for v in voices} >= {"en", "es"}
    for v in voices:                                      # every voice has a short, real preview clip
        r = httpx.get(url + v["preview_url"])
        assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg", v["id"]
        (tmp_path / "p.mp3").write_bytes(r.content)
        assert 3 <= float(probe(tmp_path / "p.mp3")[1]["duration"]) <= 10, v["id"]

    page.goto(url + "/#library")
    page.wait_for_selector(".voice-card", timeout=15000)
    assert len(page.query_selector_all(".voice-card")) == len(voices)
    for lang, engine in (("es", "piper"), ("es", "kokoro"), ("en", "xtts")):   # browse with filters, then play
        page.click("#lib-clear")
        page.select_option("#lib-language", lang)
        page.select_option("#lib-engine", engine)
        cards = page.query_selector_all(".voice-card")
        assert cards, (lang, engine)
        vid = cards[0].get_attribute("data-id")
        btn = f".voice-card[data-id='{vid}'] .lib-play"
        page.click(btn)
        page.wait_for_function("preview.audio && !preview.audio.paused && preview.audio.currentTime > 0.5", timeout=15000)
        assert page.evaluate("preview.id") == vid and page.get_attribute(btn, "aria-pressed") == "true"
        page.click(btn)                                   # a second click stops it
        assert page.evaluate("preview.audio.paused")
        (tmp_path / "x.mp3").write_bytes(httpx.get(url + f"/api/library/{vid}/preview").content)
        text = transcribe(tmp_path / "x.mp3", lang)
        assert len(text.split()) >= 3, (vid, text)        # it is speech in the right language


def _fetch(page, src, path):
    """Save what an <audio> element plays (blob or URL) to `path`."""
    data = page.evaluate("async (u) => Array.from(new Uint8Array(await (await fetch(u)).arrayBuffer()))", src)
    path.write_bytes(bytes(data))
    return path


def _tts(page, voice_id, lang, text, path):
    page.goto(page.base + "/")
    page.wait_for_selector(f"#tts-voice option[value='{voice_id}']", state="attached", timeout=15000)
    page.select_option("#tts-voice", voice_id)
    page.select_option("#tts-lang", lang)
    page.fill("#tts-text", text)
    page.click("#tts-generate")
    page.wait_for_selector("#tts-msg.ok", timeout=300000)
    return _fetch(page, page.get_attribute("#tts-audio", "src"), path)


SAMPLE = ("Every morning I walk to the small bakery at the corner of my street. The baker always smiles and asks "
          "about my plans for the day. I usually buy fresh bread and a cup of strong coffee. Then I sit by the "
          "window and watch the city wake up slowly. It is the calmest part of my whole day.")


def test_02_clone_a_voice_from_a_sample_and_speak_spanish_and_english(app, page, tmp_path):
    import re

    url = app[0]
    r = httpx.post(f"{url}/api/speak", json={"text": SAMPLE, "voice": "kokoro-bf-emma", "language": "en", "format": "wav"},
                   timeout=300)
    assert r.status_code == 200
    sample = tmp_path / "sample.wav"                      # one synthetic sample (no real person's voice)
    sample.write_bytes(r.content)
    assert float(probe(sample)[1]["duration"]) > 15

    page.goto(url + "/#clone")
    page.set_input_files("#clone-input", str(sample))
    page.wait_for_selector("#clone-clips textarea.transcript:not([disabled])", timeout=120000)
    assert "bakery" in " ".join(page.eval_on_selector_all("#clone-clips textarea", "ts => ts.map(t => t.value)")).lower()
    page.fill("#voice-name", "E2E Clone")
    page.check("#voice-consent")
    page.click("#voice-preview")
    page.wait_for_selector("#voice-msg.ok", timeout=300000)
    page.click("#voice-save")
    page.wait_for_selector("#clone-msg.ok a[href='#voices']", timeout=30000)
    vid = re.search(r"ID ([a-z0-9-]+)\)", page.inner_text("#clone-msg"))[1]
    mine = {v["id"]: v for v in httpx.get(f"{url}/api/my-voices").json()}
    assert mine[vid]["name"] == "E2E Clone" and mine[vid]["kind"] == "cloned"

    for lang, text in (("es", "Buenos días, hoy vamos a probar mi voz clonada en español."),
                       ("en", "Good morning, today we are testing my cloned voice in English.")):
        heard = transcribe(_tts(page, vid, lang, text, tmp_path / f"{lang}.wav"), lang)
        assert similar(heard, text) > 0.7, (lang, heard)


def test_03_blend_two_voices(app, page, tmp_path):
    url = app[0]
    page.goto(url + "/#blend")
    page.wait_for_selector("#blend-a option[value='xtts-daisy-studious']", state="attached", timeout=15000)
    page.select_option("#blend-a", "xtts-daisy-studious")
    page.select_option("#blend-b", "xtts-viktor-eka")
    page.fill("#blend-ratio", "50")
    assert page.inner_text("#blend-ratio-label") == "50% A · 50% B"
    page.fill("#blend-name", "E2E Blend")
    page.click("#blend-preview")
    page.wait_for_selector("#blend-msg.ok", timeout=300000)
    preview = transcribe(_fetch(page, page.get_attribute("#blend-audio", "src"), tmp_path / "p.wav"))
    assert len(preview.split()) >= 4, preview
    page.click("#blend-save")
    page.wait_for_selector("#blend-msg.ok a[href='#voices']", timeout=120000)
    vid = page.inner_text("#blend-msg").split("ID ")[1].split(")")[0]
    v = {v["id"]: v for v in httpx.get(f"{url}/api/my-voices").json()}[vid]
    assert v["name"] == "E2E Blend" and v["blend"]["ratio"] == 0.5
    assert {v["blend"]["a"], v["blend"]["b"]} == {"xtts-daisy-studious", "xtts-viktor-eka"}

    text = "Esta voz es una mezcla de dos voces de la biblioteca."
    heard = transcribe(_tts(page, vid, "es", text, tmp_path / "blend.wav"), "es")
    assert similar(heard, text) > 0.7, heard


def _mcp(server, calls):
    """test_mcp.run in its own thread: in a full run another test file's Playwright keeps an event loop running."""
    from concurrent.futures import ThreadPoolExecutor

    from test_mcp import run

    with ThreadPoolExecutor(1) as ex:
        return ex.submit(run, server, calls).result()


def test_04_call_api_and_mcp_tool(app, tmp_path):
    import sys

    from mcp.client.stdio import StdioServerParameters
    from openai import OpenAI


    url = app[0]
    text = "The weather is clear and the trains are on time."
    r = httpx.post(f"{url}/api/speak", json={"text": text, "voice": "kokoro-af-heart", "format": "mp3"}, timeout=300)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
    (tmp_path / "rest.mp3").write_bytes(r.content)
    assert similar(transcribe(tmp_path / "rest.mp3", "en"), text) > 0.8
    assert httpx.get(f"{url}/api/history/{r.headers['X-Voicer-Id']}").status_code == 200       # saved to History

    OpenAI(base_url=f"{url}/v1", api_key="x").audio.speech.create(
        model="tts-1", voice="piper-es-mx-claude-high", input="Hola, esta es la API compatible.",
        response_format="opus").write_to_file(tmp_path / "openai.ogg")
    assert probe(tmp_path / "openai.ogg")[0]["codec_name"] == "opus"
    assert similar(transcribe(tmp_path / "openai.ogg", "es"), "Hola, esta es la API compatible") > 0.7

    async def calls(c):
        found = (await c.call_tool("search_voices", {"query": "dora"})).structured_content
        said = (await c.call_tool("speak", {"text": "Mensaje de prueba por MCP.", "voice": "kokoro-ef-dora",
                                            "language": "es"})).structured_content
        return found, said
    found, said = _mcp(f"{url}/mcp", calls)                                                      # HTTP transport
    assert "kokoro-ef-dora" in str(found) and said["format"] == "mp3"
    (tmp_path / "mcp.mp3").write_bytes(httpx.get(said["url"]).content)
    assert similar(transcribe(tmp_path / "mcp.mp3", "es"), "Mensaje de prueba por MCP") > 0.7

    stdio = StdioServerParameters(command=sys.executable, args=["-m", "voicer.mcp_server"], cwd=str(ROOT),
                                  env={**os.environ, "VOICER_DATA": str(app[1])})

    async def speak(c):
        return (await c.call_tool("speak", {"text": "Hello from the stdio server.",
                                            "voice": "piper-en-us-lessac-medium"})).structured_content
    out = _mcp(stdio, speak)                                                                     # stdio transport
    assert Path(out["path"]).is_file()
    assert similar(transcribe(out["path"], "en"), "Hello from the stdio server") > 0.7


def _ffprobe_ogg_opus(path, seconds=None):
    """ffprobe: OGG container, one Opus stream, mono, 48 kHz; ffmpeg decodes it with no errors."""
    import json

    j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                                  capture_output=True, text=True, check=True).stdout)
    assert j["format"]["format_name"] == "ogg" and len(j["streams"]) == 1
    st = j["streams"][0]
    assert (st["codec_type"], st["codec_name"], st["channels"], st["sample_rate"]) == ("audio", "opus", 1, "48000")
    if seconds:
        assert abs(float(j["format"]["duration"]) - seconds) < 0.15
    dec = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], capture_output=True, text=True)
    assert dec.returncode == 0 and not dec.stderr.strip(), dec.stderr


def test_05_ogg_opus_confirmed_with_ffprobe(app, tmp_path):

    url = app[0]
    text = "Te mando una nota de voz para confirmar la cita de mañana."
    r = httpx.post(f"{url}/api/speak", json={"text": text, "voice": "kokoro-ef-dora", "language": "es",
                                             "format": "ogg_opus"}, timeout=300)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/ogg"
    p = tmp_path / "speak.ogg"
    p.write_bytes(r.content)
    _ffprobe_ogg_opus(p, float(r.headers["X-Voicer-Seconds"]))
    assert similar(transcribe(p, "es"), text) > 0.7

    h = httpx.get(f"{url}/api/history/{r.headers['X-Voicer-Id']}/audio", params={"format": "ogg_opus", "download": "true"})
    assert h.headers["content-disposition"].endswith('.ogg"')
    (tmp_path / "history.ogg").write_bytes(h.content)
    _ffprobe_ogg_opus(tmp_path / "history.ogg", float(r.headers["X-Voicer-Seconds"]))

    async def calls(c):
        return (await c.call_tool("speak", {"text": "Nota por MCP.", "voice": "kokoro-ef-dora", "language": "es",
                                            "format": "ogg_opus"})).structured_content
    said = _mcp(f"{url}/mcp", calls)
    assert said["mime"] == "audio/ogg"
    (tmp_path / "mcp.ogg").write_bytes(httpx.get(said["url"]).content)
    _ffprobe_ogg_opus(tmp_path / "mcp.ogg", said["seconds"])


def test_06_measure_streaming_latency(app, tmp_path):
    """Time from request to first audio over the network (HTTP chunked and WebSocket), warm model, median of 3."""
    import json
    import statistics

    from websockets.sync.client import connect

    url = app[0]
    text = "Hello, how are you today?"
    long_text = " ".join(["The first train leaves at nine.", "The second one leaves at ten.",
                          "Bring a coat, it is cold outside.", "We will meet at the station."] * 2)

    def http_first(voice, t=text):
        t0 = time.monotonic()
        with httpx.stream("POST", f"{url}/api/speak", timeout=300,
                          json={"text": t, "voice": voice, "language": "en", "format": "pcm", "stream": True}) as r:
            assert r.status_code == 200
            it = r.iter_raw()
            next(it)
            first = time.monotonic() - t0
            for _ in it:
                pass
        return first, time.monotonic() - t0

    def ws_first(voice):
        with connect(url.replace("http", "ws") + "/api/ws/speak") as ws:
            t0 = time.monotonic()
            ws.send(json.dumps({"text": text, "voice": voice, "language": "en"}))
            assert json.loads(ws.recv())["type"] == "start"
            assert isinstance(ws.recv(), bytes)
            first = time.monotonic() - t0
            while not (isinstance(m := ws.recv(), str) and json.loads(m)["type"] == "done"):
                pass
        return first

    results = {}
    for voice in ("piper-en-us-lessac-medium", "kokoro-af-heart", "xtts-claribel-dervla"):
        http_first(voice)                                 # warm up: the first request loads the model
        results[voice] = {"http": statistics.median(http_first(voice)[0] for _ in range(3)),
                          "websocket": statistics.median(ws_first(voice) for _ in range(3))}
    first, total = http_first("kokoro-af-heart", long_text)
    results["long text (kokoro)"] = {"first": first, "total": total}
    print("\nstreaming latency (s):", json.dumps(results, indent=1))
    for voice in ("piper-en-us-lessac-medium", "kokoro-af-heart", "xtts-claribel-dervla"):
        assert results[voice]["http"] < 1.0 and results[voice]["websocket"] < 1.0, results
    assert first < 0.5 * total, results                   # the first sentence plays while the rest is made


def _silences(path, min_s=0.5):
    """Silent stretches (seconds) of at least `min_s`, from ffmpeg silencedetect."""
    import re

    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", f"silencedetect=n=-45dB:d={min_s}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return [float(d) for d in re.findall(r"silence_duration: ([\d.]+)", out)]


def test_07_dictionary_word_and_text_tags(app, page, tmp_path):
    """Add a word on the Dictionary page, then say it in a text with tags: the spoken form is used, the tags are obeyed
    and never read aloud."""
    url = app[0]
    page.goto(url + "/#dictionary")
    page.wait_for_selector("#dict-list > *")
    page.select_option("#dict-lang", "es")
    page.fill("#dict-word", "CDMX")
    page.fill("#dict-spoken", "Ciudad de México")
    page.click("#dict-save")
    page.wait_for_selector("tr[data-word='CDMX']")
    assert httpx.get(f"{url}/api/dictionary").json()["es"] == [{"word": "CDMX", "spoken": "Ciudad de México"}]
    with page.expect_response("**/api/dictionary/listen", timeout=300000) as r:
        page.click("tr[data-word='CDMX'] .dict-listen")
    assert r.value.status == 200
    page.wait_for_function("dic.audio && dic.audio.duration > 0.5")

    voice = "kokoro-ef-dora"
    clip = _tts(page, voice, "es", "Vivo en CDMX. [pause 1s] [slow] Me gusta mucho. [normal] [whatever] Adiós.",
                tmp_path / "tags")
    said = transcribe(clip, "es").lower()
    assert "ciudad de méxico" in said or "ciudad de mexico" in said, said            # the dictionary's spoken form
    assert similar(said, "Vivo en Ciudad de México. Me gusta mucho. Adiós.") >= 0.75, said
    for tag in ("pause", "pausa", "slow", "normal", "whatever", "cdmx", "[", "]"):
        assert tag not in said, (tag, said)                                          # no tag read aloud
    assert any(0.9 <= s <= 1.4 for s in _silences(clip)), _silences(clip)          # the 1 s pause

    def seconds(text):
        r = httpx.post(f"{url}/api/speak", json={"text": text, "voice": voice, "language": "es", "format": "wav"},
                       timeout=300)
        assert r.status_code == 200
        (tmp_path / "s.wav").write_bytes(r.content)
        return float(probe(tmp_path / "s.wav")[1]["duration"])
    assert seconds("[slow] Me gusta mucho.") >= 1.15 * seconds("Me gusta mucho.")    # [slow] = speed ×0.8


def test_08_run_a_5_row_csv_batch(app, page, tmp_path):
    """Batch page: a 5-row CSV (own voices and languages, one row on the side-card defaults) → 5 MP3 clips in one ZIP."""
    import csv
    import io
    import json
    import zipfile

    rows = [("Good morning, and welcome to the show.", "intro", "piper-en-us-lessac-medium", "en"),
            ("Hoy hablamos de viajes y de comida.", "tema", "kokoro-ef-dora", "es"),
            ('The weather today is "sunny, warm" and calm.', "clima", "xtts-claribel-dervla", "en"),
            ("Muchas gracias por escuchar.", "gracias", "piper-es-mx-ald-medium", "es"),
            ("See you next week.", "", "", "")]                     # no voice/language/name: the page settings
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["text", "filename", "voice", "language"])
    w.writerows(rows)
    page.goto(page.base + "/#batch")
    page.wait_for_selector("#bat-voice option[value='kokoro-af-heart']", state="attached", timeout=15000)
    page.select_option("#bat-voice", "kokoro-af-heart")
    page.select_option("#bat-lang", "en")
    page.select_option("#bat-format", "mp3")
    page.set_input_files("#bat-input", files=[{"name": "episode.csv", "mimeType": "text/csv", "buffer": out.getvalue().encode()}])
    page.wait_for_selector("#bat-row-4")
    assert "5 clips found in episode.csv" in page.inner_text("#bat-msg") and page.inner_text("#bat-start") == "Generate 5 clips"
    page.click("#bat-start")
    page.wait_for_selector("#bat-zip:not([hidden])", timeout=600000)
    assert page.eval_on_selector("#bat-progress", "p => [p.value, p.max]") == [5, 5]
    assert page.inner_text("#bat-progress-text") == "5 / 5 clips" and len(page.query_selector_all(".bat-status.ok")) == 5
    with page.expect_download() as dl:
        page.click("#bat-zip")
    assert dl.value.suggested_filename == "episode.zip"
    z = zipfile.ZipFile(dl.value.path())
    clips = sorted(n for n in z.namelist() if n.endswith(".mp3"))
    assert len(clips) == 5 and clips[:4] == ["001-intro.mp3", "002-tema.mp3", "003-clima.mp3", "004-gracias.mp3"], clips
    items = json.loads(z.read("manifest.json"))["items"]
    assert [i["voice_id"] for i in items] == [r[2] or "kokoro-af-heart" for r in rows]
    for name, (text, _, _, lang) in zip(clips, rows):
        (tmp_path / name).write_bytes(z.read(name))
        assert probe(tmp_path / name)[1]["format_name"] == "mp3"
        assert similar(transcribe(tmp_path / name, lang or "en"), text) >= 0.75, name
    hist = httpx.get(f"{app[0]}/api/history", params={"limit": 50}).json()
    assert {i["id"] for i in items} <= {e["id"] for e in hist["items"]}                 # every clip is in History


def test_09_generate_a_2_speaker_dialogue(app, page, tmp_path):
    """Dialogue page: a Spanish script for a woman (Kokoro) and a man (XTTS) → one WAV; each turn has its speaker's
    voice (pitch), its subtitle cue, and Whisper hears the whole script."""
    import re

    import librosa
    import numpy as np

    ana, luis = "kokoro-ef-dora", "xtts-luis-moray-es"
    page.goto(page.base + "/#dialogue")
    page.wait_for_selector("#dlg-cast[data-ready='1']")
    page.fill("#dlg-script", "Ana: Hola Luis, ¿cómo estás hoy?\nLuis: Muy bien, gracias. Acabo de volver del mercado.\n"
                             "Ana: ¡Qué bien! ¿Compraste fruta?\nLuis: Sí, naranjas y manzanas.")
    page.select_option("#dlg-voice-0", ana)
    page.select_option("#dlg-voice-1", luis)
    page.select_option("#dlg-lang", "es")
    page.click("#dlg-generate")
    page.wait_for_selector("#dlg-result .wave-player[data-ready='1']", timeout=600000)
    assert "saved to History" in page.inner_text("#dlg-msg")
    wav = _fetch(page, page.get_attribute("#dlg-result a[data-format='wav']", "href"), tmp_path / "d.wav")
    srt = httpx.get(app[0] + page.get_attribute("#dlg-result a[data-subs='srt']", "href")).text
    said = transcribe(wav, "es")
    assert similar(said, "Hola Luis, ¿cómo estás hoy? Muy bien, gracias. Acabo de volver del mercado. "
                         "¡Qué bien! ¿Compraste fruta? Sí, naranjas y manzanas.") >= 0.75, said

    def sec(ts):
        h, m, s = ts.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    cues = [(sec(a), sec(b), who) for a, b, who in re.findall(r"([\d:,]+) --> ([\d:,]+)\n(Ana|Luis):", srt)]
    assert [c[2] for c in cues][:1] == ["Ana"] and {c[2] for c in cues} == {"Ana", "Luis"}, srt
    y, sr = librosa.load(wav, sr=16000)

    def pitch(who):
        f0 = np.concatenate([librosa.pyin(y[int(a * sr):int(b * sr)], fmin=60, fmax=400, sr=sr)[0] for a, b, w in cues if w == who])
        return float(np.nanmedian(f0))
    assert pitch("Ana") > pitch("Luis") + 40, (pitch("Ana"), pitch("Luis"))           # two different voices


def test_10_run_voice_changer(app, page, tmp_path):
    """Voice Changer page: a Spanish MP3 spoken by a woman (Piper claude) → a man's voice (Kokoro em_alex). Same words
    and length, pitch moves to the target voice's, subtitles from the recording."""
    import librosa
    import numpy as np

    url = app[0]
    text = "Buenos días. Te dejo este mensaje para confirmar la reunión del jueves a las diez."
    r = httpx.post(f"{url}/api/speak", json={"text": text, "voice": "piper-es-mx-claude-high", "language": "es",
                                              "format": "mp3"}, timeout=300)
    assert r.status_code == 200
    src = tmp_path / "nota de voz.mp3"
    src.write_bytes(r.content)

    page.goto(url + "/#changer")
    page.wait_for_selector("#vc-voice option[value='kokoro-em-alex']", state="attached", timeout=15000)
    page.set_input_files("#vc-input", str(src))
    page.wait_for_selector("#vc-source:has-text('nota de voz.mp3')")
    page.select_option("#vc-voice", "kokoro-em-alex")
    page.select_option("#vc-lang", "es")
    page.click("#vc-convert")
    page.wait_for_selector("#vc-result .wave-player[data-ready='1']", timeout=600000)
    assert "saved to History" in page.inner_text("#vc-msg")
    out = _fetch(page, page.get_attribute("#vc-result a[data-format='wav']", "href"), tmp_path / "out.wav")

    a, sr_a = librosa.load(src, sr=16000)
    b, _ = librosa.load(out, sr=16000)
    assert abs(len(a) - len(b)) / 16000 < 0.2                                       # same timing
    said = transcribe(out, "es")
    assert similar(said, text) >= 0.75, said
    f0 = lambda y: float(np.nanmedian(librosa.pyin(y, fmin=60, fmax=400, sr=16000)[0]))
    r = httpx.post(f"{url}/api/speak", json={"text": text, "voice": "kokoro-em-alex", "language": "es", "format": "wav"},
                   timeout=300)
    (tmp_path / "target.wav").write_bytes(r.content)
    target = f0(librosa.load(tmp_path / "target.wav", sr=16000)[0])
    print("\nmedian pitch (Hz): source", f0(a), "converted", f0(b), "target voice", target)
    assert f0(b) < f0(a) - 30 and abs(f0(b) - target) < abs(f0(a) - target) / 2   # a woman's voice → a man's
    srt = httpx.get(url + page.get_attribute("#vc-result a[data-subs='srt']", "href")).text
    assert "-->" in srt and "jueves" in srt.lower()


def test_11_generate_srt_for_an_audio_file(app, page, tmp_path):
    """Your own audio file → SRT (Voice Changer page, "Subtitles only") and VTT (API). Each cue's stretch of audio
    says the cue's text."""
    import re

    import soundfile as sf

    url = app[0]
    lines = ["Hola a todos y bienvenidos al programa.", "Hoy vamos a hablar de la música de los años ochenta.",
             "Después escucharemos tres canciones muy conocidas."]
    r = httpx.post(f"{url}/api/speak", json={"text": " [pause 1s] ".join(lines), "voice": "kokoro-em-alex",
                                              "language": "es", "format": "mp3"}, timeout=300)
    src = tmp_path / "programa 12.mp3"
    src.write_bytes(r.content)

    page.goto(url + "/#changer")
    page.wait_for_selector("#vc-voice option", state="attached", timeout=15000)
    page.set_input_files("#vc-input", str(src))
    page.wait_for_selector("#vc-source:has-text('programa 12.mp3')")
    page.select_option("#vc-lang", "es")
    with page.expect_download(timeout=300000) as dl:
        page.click("#vc-subs")
    assert dl.value.suggested_filename == "programa_12.srt"
    srt = open(dl.value.path(), encoding="utf-8").read()
    page.wait_for_selector("#vc-msg.ok")

    def sec(ts):
        h, m, s = ts.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    cues = [(sec(a), sec(b), t.replace("\n", " ")) for a, b, t in
            re.findall(r"\d+\n([\d:,]+) --> ([\d:,]+)\n(.+?)(?:\n\n|\n?$)", srt, re.S)]
    assert len(cues) >= 3, srt
    assert similar(" ".join(c[2] for c in cues), " ".join(lines)) >= 0.85, srt
    wav = tmp_path / "src.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "16000", str(wav)], check=True)
    y, sr = sf.read(wav)
    for i, (a, b, text) in enumerate(cues):                                          # the timing is right
        sf.write(tmp_path / f"c{i}.wav", y[int(a * sr):int(b * sr) + int(0.2 * sr)], sr)
        assert similar(transcribe(tmp_path / f"c{i}.wav", "es"), text) >= 0.6, (a, b, text)

    r = httpx.post(f"{url}/api/subtitles", files={"file": (src.name, src.read_bytes(), "audio/mpeg")},
                   data={"language": "es", "format": "vtt"}, timeout=300)
    assert r.status_code == 200 and r.text.startswith("WEBVTT") and r.text.count(" --> ") == len(cues)


def test_12_five_parallel_api_requests_use_the_queue(app, tmp_path):
    """5 /api/speak requests at once (3 engines): they wait their turn (one job at a time), all succeed, each clip
    has its own text, and the rest of the API stays fast meanwhile."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    url = app[0]
    jobs = [("The red train leaves at nine.", "piper-en-us-lessac-medium", "en"),
            ("El gato duerme en la ventana.", "kokoro-ef-dora", "es"),
            ("Please close the door quietly.", "xtts-claribel-dervla", "en"),
            ("Mañana vamos a la playa.", "piper-es-mx-claude-high", "es"),
            ("Five apples are on the table.", "kokoro-af-heart", "en")]
    before = httpx.get(f"{url}/api/health").json()["queue"]
    peak = {"running": 0, "waiting": 0, "voices_s": 0.0, "voices_errors": 0}
    stop = threading.Event()

    def watch():
        while not stop.is_set():
            q = httpx.get(f"{url}/api/health").json()["queue"]
            peak["running"] = max(peak["running"], q["running"])
            peak["waiting"] = max(peak["waiting"], q["waiting"])
            t0 = time.monotonic()
            peak["voices_errors"] += httpx.get(f"{url}/api/voices").status_code != 200
            peak["voices_s"] = max(peak["voices_s"], time.monotonic() - t0)
            time.sleep(0.05)

    def speak(job):
        text, voice, lang = job
        r = httpx.post(f"{url}/api/speak", json={"text": text, "voice": voice, "language": lang, "format": "wav"},
                       timeout=600)
        return r.status_code, r.content

    watcher = threading.Thread(target=watch)
    watcher.start()
    try:
        with ThreadPoolExecutor(5) as pool:
            results = list(pool.map(speak, jobs))
    finally:
        stop.set()
        watcher.join()
    print("\nqueue peak:", peak)
    assert [s for s, _ in results] == [200] * 5
    for i, ((text, _, lang), (_, wav)) in enumerate(zip(jobs, results)):
        (tmp_path / f"{i}.wav").write_bytes(wav)
        assert similar(transcribe(tmp_path / f"{i}.wav", lang), text) >= 0.75, text     # no mixed-up replies
    after = httpx.get(f"{url}/api/health").json()["queue"]
    assert peak["running"] == 1 and peak["waiting"] >= 2, peak                           # one at a time, others wait
    assert after["done"] - before["done"] == 5 and after["rejected"] == before["rejected"]
    assert after["running"] == 0 and after["waiting"] == 0
    assert peak["voices_s"] < 2.0 and peak["voices_errors"] == 0, peak                                                 # the UI stays usable


def _tailnet_bin():
    """Folder with `tailscale`, `tailscaled` and `headscale` (env VOICER_TAILNET_BIN, else PATH), or None."""
    import shutil

    d = os.environ.get("VOICER_TAILNET_BIN")
    found = {n: (str(Path(d) / n) if d and (Path(d) / n).is_file() else shutil.which(n))
             for n in ("tailscale", "tailscaled", "headscale")}
    return found if all(found.values()) else None


def test_13_access_from_another_device_via_tailscale(tmp_path_factory):
    """A real, private tailnet on this PC: Headscale (open-source Tailscale control server, BSD-3) and two Tailscale
    nodes in userspace mode, "voicer-pc" and "other-device". The PC shares the server with `tailscale serve` (as the
    API page says); the other device reaches it only through the tailnet: the key is required, speech works over
    REST and the OpenAI API, links point at the tailnet name. No Tailscale account needed."""
    import json

    from conftest import transcribe as _tr

    b = _tailnet_bin()
    if not b:
        pytest.skip("needs tailscale, tailscaled and headscale (set VOICER_TAILNET_BIN to their folder)")
    w = tmp_path_factory.mktemp("ts")                       # short path: unix sockets allow ~100 characters
    hs_port, proxy_port, port = _free_port(), _free_port(), _free_port()
    (w / "hs.yaml").write_text(f"""server_url: http://127.0.0.1:{hs_port}
listen_addr: 127.0.0.1:{hs_port}
metrics_listen_addr: 127.0.0.1:{_free_port()}
grpc_listen_addr: 127.0.0.1:{_free_port()}
noise: {{private_key_path: {w}/noise.key}}
prefixes: {{v4: 100.64.0.0/10, v6: "fd7a:115c:a1e0::/48", allocation: sequential}}
derp: {{server: {{enabled: false}}, urls: ["https://controlplane.tailscale.com/derpmap/default"], paths: [], auto_update_enabled: false}}
disable_check_updates: true
database: {{type: sqlite, sqlite: {{path: {w}/db.sqlite}}}}
dns: {{magic_dns: true, base_domain: tailnet.test, override_local_dns: false, nameservers: {{global: []}}}}
unix_socket: {w}/hs.sock
unix_socket_permission: "0770"
log: {{level: warn}}
policy: {{mode: file, path: ""}}
""")
    procs = []

    def bg(*cmd, env=None, log="x"):
        p = subprocess.Popen([str(c) for c in cmd], stdout=open(w / f"{log}.log", "w"), stderr=subprocess.STDOUT,
                             env=env, start_new_session=True)
        procs.append(p)
        return p

    def run(*cmd, timeout=60):
        out = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout)
        assert out.returncode == 0, (cmd, out.stdout, out.stderr)
        return out.stdout

    hs = [b["headscale"], "-c", w / "hs.yaml"]
    ts = {n: [b["tailscale"], f"--socket={w}/{n}.sock"] for n in ("pc", "dev")}
    wrapper = w / "bin"                                     # what the server runs as `tailscale` on the PC
    wrapper.mkdir()
    (wrapper / "tailscale").write_text(f'#!/bin/sh\nexec "{b["tailscale"]}" --socket="{w}/pc.sock" "$@"\n')
    (wrapper / "tailscale").chmod(0o755)
    try:
        bg(*hs, "serve", log="headscale")
        for _ in range(50):
            if subprocess.run([str(c) for c in hs] + ["users", "create", "me"], capture_output=True).returncode == 0:
                break
            time.sleep(0.2)
        uid = json.loads(run(*hs, "users", "list", "-o", "json"))[0]["id"]
        key = run(*hs, "preauthkeys", "create", "--user", uid, "--expiration", "1h", "--reusable").strip().splitlines()[-1]
        bg(b["tailscaled"], "--tun=userspace-networking", f"--statedir={w}/pc", f"--socket={w}/pc.sock", "--port=0",
           log="pc")
        bg(b["tailscaled"], "--tun=userspace-networking", f"--statedir={w}/dev", f"--socket={w}/dev.sock", "--port=0",
           f"--outbound-http-proxy-listen=127.0.0.1:{proxy_port}", log="dev")
        for n, name in (("pc", "voicer-pc"), ("dev", "other-device")):
            for _ in range(50):
                if (w / f"{n}.sock").exists():
                    break
                time.sleep(0.2)
            run(*ts[n], "up", f"--login-server=http://127.0.0.1:{hs_port}", f"--authkey={key}", f"--hostname={name}")

        data = w / "data"
        env = {**os.environ, "VOICER_PORT": str(port), "VOICER_DATA": str(data), "PATH": f"{wrapper}:{os.environ['PATH']}"}
        bg(ROOT / "start.sh", env=env, log="voicer")
        local = f"http://localhost:{port}"
        for _ in range(120):
            try:
                if httpx.get(f"{local}/api/health").json()["status"] == "ok":
                    break
            except httpx.HTTPError:
                time.sleep(0.5)
        api_key = httpx.post(f"{local}/api/api-key").json()["key"]                    # API & Agents → Make key
        run(wrapper / "tailscale", "serve", "--bg", "--http=80", f"http://127.0.0.1:{port}")
        st = httpx.get(f"{local}/api/remote-access").json()
        assert st["running"] and st["serving"] and st["url"] == "http://voicer-pc.tailnet.test", st
        assert st["ips"][0].startswith("100.") and st["warnings"] == []

        remote = st["url"]
        dev = httpx.Client(proxy=f"http://127.0.0.1:{proxy_port}", timeout=300)      # the other device
        assert dev.get(f"{remote}/api/health").json()["status"] == "ok"
        body = {"text": "Hello from the other device.", "voice": "kokoro-af-heart", "format": "mp3"}
        r = dev.post(f"{remote}/api/speak", json=body)
        assert r.status_code == 401 and "API key" in r.json()["detail"]               # the key is required
        assert dev.post(f"{remote}/api/speak", json=body, headers={"Authorization": "Bearer wrong"}).status_code == 401
        auth = {"Authorization": f"Bearer {api_key}"}
        r = dev.post(f"{remote}/api/speak", json=body, headers=auth)
        assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
        (w / "a.mp3").write_bytes(r.content)
        assert similar(_tr(w / "a.mp3", "en"), body["text"]) >= 0.8
        r = dev.post(f"{remote}/v1/audio/speech", headers=auth,
                     json={"model": "tts-1", "voice": "kokoro-ef-dora", "input": "Hola desde el otro equipo."})
        assert r.status_code == 200
        (w / "b.mp3").write_bytes(r.content)
        assert similar(_tr(w / "b.mp3", "es"), "Hola desde el otro equipo.") >= 0.8
        r = dev.post(f"{remote}/api/batch", headers=auth,
                     json={"items": [{"text": "One.", "voice": "piper-en-us-lessac-medium"}], "format": "mp3"})
        url = r.json()["items"][0]["url"]
        assert url.startswith(f"{remote}/api/history/"), url                          # a link the device can use
        assert dev.get(url, headers=auth).status_code == 200
        assert httpx.get(f"{local}/api/voices").status_code == 200                   # this PC still needs no key
        run(wrapper / "tailscale", "serve", "reset")
        with pytest.raises(httpx.HTTPError):                                          # stop sharing → gone
            dev.get(f"{remote}/api/health", timeout=10).raise_for_status()
    finally:
        for p in reversed(procs):
            try:
                os.killpg(p.pid, signal.SIGINT if p.args[0].endswith("start.sh") else signal.SIGTERM)
                p.wait(timeout=30)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                os.killpg(p.pid, signal.SIGKILL)


def test_14_export_and_re_import_a_voice(app, page, tmp_path):
    """My Voices: Export the cloned voice, delete it, Import backup → the same voice is back and speaks."""
    import hashlib
    import json
    import zipfile

    url, data = app
    clone = [v for v in httpx.get(f"{url}/api/my-voices").json() if v["name"] == "E2E Clone"]
    if not clone:                                         # run alone: make the cloned voice first
        test_02_clone_a_voice_from_a_sample_and_speak_spanish_and_english(app, page, tmp_path)
        clone = [v for v in httpx.get(f"{url}/api/my-voices").json() if v["name"] == "E2E Clone"]
    vid = clone[0]["id"]
    vdir = data / "voices" / vid

    def files():
        return {p.relative_to(vdir).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in vdir.rglob("*") if p.is_file() and not p.name.endswith(".tmp")}

    page.goto(url + "/#voices")
    card = f".voice-card[data-id='{vid}']"
    page.wait_for_selector(card)
    with page.expect_download() as dl:
        page.click(f"{card} .mv-export")
    zpath = tmp_path / dl.value.suggested_filename
    dl.value.save_as(zpath)
    before = files()
    meta = json.loads((vdir / "voice.json").read_text())
    with zipfile.ZipFile(zpath) as z:
        manifest = json.loads(z.read("voicer-backup.json"))
        names = set(z.namelist())
    assert [v["id"] for v in manifest["voices"]] == [vid]
    assert {f"voices/{vid}/{f}" for f in before} <= names                          # samples, settings, embeddings
    assert any(f.startswith("samples/") for f in before) and "voice.json" in before

    page.once("dialog", lambda d: d.accept())                                       # Delete → confirm
    page.click(f"{card} .mv-delete")
    page.wait_for_selector(card, state="detached")
    assert not vdir.exists() and vid not in {v["id"] for v in httpx.get(f"{url}/api/my-voices").json()}

    page.set_input_files("#mv-import-input", str(zpath))                            # Import backup
    page.wait_for_selector("#toast.ok:has-text('Imported 1 voices')", timeout=60000)
    page.wait_for_selector(card)
    assert "E2E Clone" in page.text_content(card)
    got = {v["id"]: v for v in httpx.get(f"{url}/api/my-voices").json()}[vid]      # same ID, name, settings
    assert (got["name"], got["kind"], got["language"]) == (clone[0]["name"], "cloned", clone[0]["language"])
    after = files()
    assert json.loads((vdir / "voice.json").read_text()) == meta                   # settings, consent, license
    assert {k: h for k, h in after.items() if k != "voice.json"} == {k: h for k, h in before.items() if k != "voice.json"}

    for lang, text in (("es", "La voz importada habla otra vez en español."),
                       ("en", "The imported voice speaks again in English.")):
        heard = transcribe(_tts(page, vid, lang, text, tmp_path / f"{lang}.wav"), lang)
        assert similar(heard, text) > 0.7, (lang, heard)
