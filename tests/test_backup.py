"""Phase 11: backup — export one voice or all voices (samples, caches/embeddings, settings, dictionary) as a zip."""
import io
import json
import tempfile
import zipfile
from pathlib import Path

import httpx
import numpy as np
import pytest
import soundfile as sf

from voicer import apikey, dictionary, settings, voices


@pytest.fixture()
def two_voices(tmp_path):
    wav = tmp_path / "s.wav"
    sf.write(wav, (0.2 * np.sin(np.arange(22050 * 3) / 22050 * 2 * np.pi * 220)).astype(np.float32), 22050)
    a = voices.create("Backup Alpha", sample_files=[wav], language="es", settings={"stability": 0.7},
                      consent={"confirmed": True})
    b = voices.create("Backup Beta", sample_files=[wav, wav])
    d = Path(a["dir"])
    (d / "xtts_latents.pt").write_bytes(b"\x80latents")            # model cache = the voice embedding
    (d / "f5").mkdir()
    (d / "f5" / "ref.npz").write_bytes(b"npz")
    (d / "voice.json.tmp").write_text("half")                       # never exported
    dictionary.set_entry("es", "Zyxq", "sicsq")
    old_default = settings.load().get("default_voice")
    voices.set_default(a["id"])
    yield a, b
    settings.update(default_voice=old_default)
    dictionary.delete_entry("es", "Zyxq")
    for v in (a, b):
        voices.delete(v["id"])


def _zip(r):
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    return zipfile.ZipFile(io.BytesIO(r.content))


def test_export_one_voice(live_server, two_voices):
    a, b = two_voices
    before = set(Path(tempfile.gettempdir()).glob("voicer-export-*.zip"))
    apikey.create()                                                # the key must never be in a backup
    try:
        r = httpx.get(f"{live_server}/api/export", params={"voice": a["id"]})
    finally:
        apikey.disable()
    z = _zip(r)
    assert r.headers["content-disposition"] == f'attachment; filename="{a["id"]}.voicer.zip"'
    names = set(z.namelist())
    p = f"voices/{a['id']}/"
    assert {p + "voice.json", p + "samples/sample_00.wav", p + "xtts_latents.pt", p + "f5/ref.npz",
            "dictionary.json", "voicer-backup.json"} == names
    m = json.loads(z.read("voicer-backup.json"))
    assert (m["format"], m["version"], m["default_voice"], m["dictionary"]) == ("voicer-backup", 1, a["id"], True)
    assert m["voices"] == [{"id": a["id"], "name": "Backup Alpha", "kind": "cloned", "engine": "xtts", "files": 4}]
    v = json.loads(z.read(p + "voice.json"))
    assert v["settings"] == {"stability": 0.7} and v["consent"] == {"confirmed": True} and "dir" not in v
    assert z.read(p + "xtts_latents.pt") == b"\x80latents"
    assert json.loads(z.read("dictionary.json"))["es"]["Zyxq"] == "sicsq"
    assert "api_key" not in r.content.decode("latin-1") and "hash" not in m
    assert set(Path(tempfile.gettempdir()).glob("voicer-export-*.zip")) == before    # temp file removed


def test_export_all_and_options(live_server, two_voices):
    a, b = two_voices
    z = _zip(httpx.get(f"{live_server}/api/export"))
    ids = {v["id"] for v in json.loads(z.read("voicer-backup.json"))["voices"]}
    assert {a["id"], b["id"]} <= ids == {v["id"] for v in voices.all_voices()}
    assert f"voices/{b['id']}/samples/sample_01.wav" in z.namelist()

    r = httpx.get(f"{live_server}/api/export", params=[("voice", b["id"]), ("voice", a["id"]), ("dictionary", "false")])
    z = _zip(r)
    m = json.loads(z.read("voicer-backup.json"))
    assert [v["id"] for v in m["voices"]] == [b["id"], a["id"]] and not m["dictionary"]
    assert "dictionary.json" not in z.namelist() and "voicer-backup-" in r.headers["content-disposition"]

    r = httpx.get(f"{live_server}/api/export", params={"voice": "no-such-voice"})
    assert r.status_code == 404 and "not found" in r.json()["detail"]
    r = httpx.get(f"{live_server}/api/export", params={"voice": "piper-en-us-lessac-medium"})   # library voice
    assert r.status_code == 404


@pytest.mark.browser
def test_my_voices_export_buttons(page, two_voices):
    a, _ = two_voices
    page.goto(page.base + "/#voices")
    page.wait_for_selector(f".voice-card[data-id='{a['id']}'] .mv-export")
    with page.expect_download() as dl:
        page.click(f".voice-card[data-id='{a['id']}'] .mv-export")
    assert dl.value.suggested_filename == f"{a['id']}.voicer.zip"
    with page.expect_download() as dl:
        page.click("#mv-export-all")
    assert dl.value.suggested_filename.startswith("voicer-backup-")
    z = zipfile.ZipFile(dl.value.path())
    assert f"voices/{a['id']}/voice.json" in z.namelist()
