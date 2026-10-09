"""Phase 11: import a backup zip on another PC or VPS — safe, all or nothing, never overwrites."""
import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from test_backup import two_voices  # noqa: F401  (fixture)
from voicer import backup, config, dictionary, settings, voices


def _post(url, data: bytes, name="b.zip"):
    return httpx.post(f"{url}/api/import", files={"file": (name, data, "application/zip")}, timeout=60)


def _make(entries: dict, manifest: dict | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("voicer-backup.json", json.dumps(manifest or {"format": "voicer-backup", "version": 1, "voices": []}))
        for name, data in entries.items():
            if isinstance(data, zipfile.ZipInfo):
                z.writestr(data, b"/etc/passwd")
            else:
                z.writestr(name, data)
    return buf.getvalue()


def _state():
    return sorted(p.name for p in config.VOICES_DIR.iterdir()), dictionary.load()


def test_round_trip_to_a_new_pc(live_server, two_voices):
    a, b = two_voices
    data = httpx.get(f"{live_server}/api/export", params=[("voice", a["id"]), ("voice", b["id"])]).content
    files_a = sorted(p.relative_to(a["dir"]).as_posix() for p in Path(a["dir"]).rglob("*") if p.is_file()
                     and not p.name.endswith(".tmp"))
    for v in (a, b):                                              # "another PC": nothing of it here
        voices.delete(v["id"])
    dictionary.delete_entry("es", "Zyxq")
    settings.update(default_voice=None)

    r = _post(live_server, data)
    assert r.status_code == 200, r.text
    out = r.json()
    assert [(v["id"], v["renamed"]) for v in out["voices"]] == [(a["id"], False), (b["id"], False)]
    assert out["dictionary_added"] >= 1 and out["default_voice"] == a["id"]
    got = voices.get(a["id"])
    assert (got["name"], got["settings"], got["consent"], got["language"]) == (
        "Backup Alpha", {"stability": 0.7}, {"confirmed": True}, "es")
    assert sorted(p.relative_to(got["dir"]).as_posix() for p in Path(got["dir"]).rglob("*") if p.is_file()) == files_a
    assert (Path(got["dir"]) / "xtts_latents.pt").read_bytes() == b"\x80latents"
    assert dictionary.load()["es"]["Zyxq"] == "sicsq"
    assert voices.default_id() == a["id"]
    assert not list(config.VOICES_DIR.glob(".import-*"))            # staging folder removed


def test_import_twice_adds_copies_and_keeps_your_words(live_server, two_voices):
    a, b = two_voices
    data = httpx.get(f"{live_server}/api/export", params={"voice": a["id"]}).content
    dictionary.set_entry("es", "Zyxq", "mine")                     # changed here after the backup
    voices.set_default(b["id"])
    r = _post(live_server, data)
    assert r.status_code == 200, r.text
    (new,) = r.json()["voices"]
    try:
        assert new["renamed"] and new["id"] != a["id"] and new["name"] == "Backup Alpha (imported)"
        assert (r.json()["dictionary_added"], r.json()["dictionary_kept"]) == (0, 1)
        assert dictionary.load()["es"]["Zyxq"] == "mine"            # your word wins
        assert voices.default_id() == b["id"]                       # your default stays
        copy = voices.get(new["id"])
        assert copy["imported_from"] == a["id"] and copy["samples"] == ["samples/sample_00.wav"]
        assert (Path(copy["dir"]) / "samples" / "sample_00.wav").is_file()
        assert voices.get(a["id"])["name"] == "Backup Alpha"        # the original is untouched
        names = [c["name"] for c in httpx.get(f"{live_server}/api/my-voices").json()]
        assert "Backup Alpha (imported)" in names
    finally:
        voices.delete(new["id"])


def test_bad_zips_change_nothing(live_server):
    before = _state()
    link = zipfile.ZipInfo("voices/evil-1/link")
    link.external_attr = 0o120777 << 16                             # a symbolic link
    ok_json = json.dumps({"name": "Ok", "kind": "cloned"})
    cases = {
        "not a zip file": b"hello",
        "voicer-backup.json file is missing": (lambda: (b := io.BytesIO(), zipfile.ZipFile(b, "w").close(), b.getvalue())[2])(),
        "wrong format": _make({}, {"format": "other", "version": 1}),
        "newer Voice Studio": _make({}, {"format": "voicer-backup", "version": 99}),
        "unsafe file path": _make({"voices/ok-1/voice.json": ok_json, "voices/ok-1/../../../evil.txt": "x"}),
        "unsafe file path 'voices/ok-1//etc": _make({"voices/ok-1/voice.json": ok_json, "voices/ok-1//etc/x": "x"}),
        "unexpected file '/etc": _make({"/etc/evil.txt": "x"}),
        "unsafe file path 'voices/ok-1/C:": _make({"voices/ok-1/voice.json": ok_json, "voices/ok-1/C:/x": "x"}),
        "unexpected file": _make({"../evil.txt": "x"}),
        "unexpected file 'voices/evil-1/link'": _make({"voices/evil-1/voice.json": ok_json, "link": link}),
        "has no voice.json": _make({"voices/ok-1/samples/a.wav": "x"}),
        "damaged voice.json": _make({"voices/ok-1/voice.json": "{nope"}),
        "unsafe file path 'voices/BAD": _make({"voices/BAD_ID/voice.json": ok_json}),
        "dictionary.json is damaged": _make({"voices/ok-1/voice.json": ok_json, "dictionary.json": "[1"}),
    }
    for expect, data in cases.items():
        r = _post(live_server, data)
        assert r.status_code == 400 and expect in r.json()["detail"], (expect, r.text)
        assert _state() == before, expect                           # all or nothing
    assert not (config.DATA_DIR.parent / "evil.txt").exists() and not (config.DATA_DIR / "evil.txt").exists()

    bomb = io.BytesIO()                                             # 50 MB of zeros packs to ~50 KB
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("voicer-backup.json", json.dumps({"format": "voicer-backup", "version": 1}))
        z.writestr("voices/ok-1/voice.json", ok_json)
        z.writestr("voices/ok-1/big.bin", b"\0" * 50 * 1024**2)
    r = _post(live_server, bomb.getvalue())
    assert r.status_code == 400 and "unsafe size" in r.json()["detail"]
    assert _state() == before


def test_voice_json_from_a_backup_is_cleaned():
    meta = {"name": "  Odd \n name ", "kind": "cloned", "dir": "/etc", "samples": ["samples/a.wav", "../../etc/passwd"],
            "preview": "/etc/shadow", "settings": "x", "tags": "y", "evil": 1}
    data = _make({"voices/clean-1/voice.json": json.dumps(meta), "voices/clean-1/samples/a.wav": "RIFF"})
    out = backup.import_zip(io.BytesIO(data))
    try:
        assert out["voices"] == [{"id": "clean-1", "name": "Odd name", "from_id": "clean-1", "renamed": False}]
        v = json.loads((config.VOICES_DIR / "clean-1" / "voice.json").read_text())
        assert v["samples"] == ["samples/a.wav"] and "preview" not in v and "evil" not in v
        assert (v["settings"], v["tags"], v["id"]) == ({}, [], "clean-1")
        assert voices.get("clean-1")["dir"] == str(config.VOICES_DIR / "clean-1")
    finally:
        voices.delete("clean-1")


@pytest.mark.browser
def test_my_voices_import_button(page, two_voices):
    a, _ = two_voices
    data = httpx.get(f"{page.base}/api/export", params={"voice": a["id"]}).content
    page.goto(page.base + "/#voices")
    page.wait_for_selector(f".voice-card[data-id='{a['id']}']")
    n = page.locator(".voice-card").count()
    page.set_input_files("#mv-import-input", files=[{"name": "a.voicer.zip", "mimeType": "application/zip", "buffer": data}])
    page.wait_for_selector("#toast.ok:has-text('Imported 1 voices')")
    assert "added as copies" in page.text_content("#toast")
    page.wait_for_function(f"document.querySelectorAll('.voice-card').length === {n + 1}")
    assert page.locator(".voice-card", has_text="Backup Alpha (imported)").count() == 1
    assert page.text_content("#mv-import") == "Import backup" and not page.is_disabled("#mv-import")

    page.set_input_files("#mv-import-input", files=[{"name": "x.zip", "mimeType": "application/zip", "buffer": b"no"}])
    page.wait_for_selector("#toast.error:has-text('Could not import the backup')")
    page.errors[:] = [e for e in page.errors if "400" not in e]
    for v in voices.all_voices():
        if v.get("imported_from") == a["id"]:
            voices.delete(v["id"])
