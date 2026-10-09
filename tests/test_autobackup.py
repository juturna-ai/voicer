"""Phase 11: optional daily auto-backup to a folder (off by default; Settings page)."""
import json
import time
import zipfile
from pathlib import Path

import httpx
import pytest

from test_backup import two_voices  # noqa: F401  (fixture)
from voicer import apikey, autobackup, config, settings


@pytest.fixture(autouse=True)
def keep_settings():
    old = {k: settings.load().get(k) for k in ("auto_backup", "auto_backup_state")}
    yield
    settings.update(**old)


def test_off_by_default_and_folder_rules(tmp_path):
    settings.update(auto_backup=None, auto_backup_state=None)
    s = autobackup.status()
    assert (s["enabled"], s["folder"], s["keep"], s["last"], s["next"]) == (False, "", 7, None, None)
    assert s["path"] == str(config.DATA_DIR / "backups") and not autobackup.due()

    assert autobackup.to_path("") == config.DATA_DIR / "backups"
    assert autobackup.to_path(f"  {tmp_path}/a/../b ") == tmp_path / "b"
    if Path("/mnt/c").is_dir():                                    # WSL: a Windows folder works
        assert autobackup.to_path(r"C:\Backups\Voices") == Path("/mnt/c/Backups/Voices")
    for bad in ("relative/folder", str(config.VOICES_DIR / "x")):
        with pytest.raises(ValueError):
            autobackup.to_path(bad)
    for bad in ({"enabled": "yes"}, {"enabled": True, "keep": 0}, {"enabled": True, "keep": 366},
                {"enabled": True, "keep": "7"}, {"enabled": True, "keep": True}):
        with pytest.raises(ValueError):
            autobackup.configure(**{"folder": str(tmp_path), **bad})
    (tmp_path / "file").write_text("x")
    with pytest.raises(ValueError, match="cannot write"):
        autobackup.configure(True, str(tmp_path / "file" / "sub"))
    assert autobackup.options()["enabled"] is False                # nothing saved on an error


def test_backup_now_keeps_the_newest_and_never_touches_other_files(tmp_path, two_voices):
    a, _ = two_voices
    folder = tmp_path / "made" / "here"
    autobackup.configure(True, str(folder), keep=2)
    assert folder.is_dir()
    for old in ("voicer-auto-20200101-000000.zip", "voicer-auto-20200102-000000.zip"):
        (folder / old).write_bytes(b"old")
    others = {"notes.txt": b"mine", "voicer-auto-old.zip": b"mine", "voicer-backup-20200101-0000.zip": b"mine"}
    for name, data in others.items():
        (folder / name).write_bytes(data)

    s = autobackup.run_now()
    made = sorted(p.name for p in folder.glob("voicer-auto-*-*.zip"))
    assert len(made) == 2 and made[0] == "voicer-auto-20200102-000000.zip" and made[1] == s["last_file"]
    assert all((folder / n).read_bytes() == d for n, d in others.items())
    assert not list(folder.glob(".*"))                             # no half-written file
    z = zipfile.ZipFile(folder / s["last_file"])
    assert f"voices/{a['id']}/voice.json" in z.namelist() and "dictionary.json" in z.namelist()
    assert json.loads(z.read("voicer-backup.json"))["format"] == "voicer-backup"
    assert (s["last_error"], s["count"]) == (None, 2) and time.time() - s["last"] < 60
    assert s["next"] >= s["last"] + autobackup.EVERY - 1


def test_timer_runs_once_a_day_and_waits_after_an_error(tmp_path):
    autobackup.configure(True, str(tmp_path), keep=3)
    now = time.time()
    assert autobackup.due(now)                                     # never backed up
    settings.update(auto_backup_state={"last_ok": now - 3600, "last_try": now - 3600})
    assert not autobackup.due(now)
    settings.update(auto_backup_state={"last_ok": now - 25 * 3600, "last_try": now - 25 * 3600})
    assert autobackup.due(now)
    autobackup.tick()
    assert len(autobackup.backups(tmp_path)) == 1 and not autobackup.due()

    blocker = tmp_path / "blocked"
    blocker.write_text("a file, not a folder")
    settings.update(auto_backup={"enabled": True, "folder": str(blocker), "keep": 3}, auto_backup_state=None)
    autobackup.tick()                                              # fails, does not raise
    s = autobackup.status()
    assert "Could not write" in s["last_error"] and s["last"] is None
    assert not autobackup.due()                                    # retry after an hour, not every 10 minutes
    assert autobackup.due(time.time() + autobackup.RETRY + 1)
    settings.update(auto_backup={"enabled": False, "folder": str(blocker), "keep": 3})
    assert not autobackup.due(time.time() + 10 * autobackup.EVERY)


def test_api_this_pc_only(live_server, tmp_path):
    r = httpx.put(f"{live_server}/api/auto-backup", json={"enabled": True, "folder": str(tmp_path), "keep": 5})
    assert r.status_code == 200 and (r.json()["enabled"], r.json()["keep"]) == (True, 5)
    assert httpx.get(f"{live_server}/api/auto-backup").json()["path"] == str(tmp_path)
    r = httpx.post(f"{live_server}/api/auto-backup/run", timeout=60)
    assert r.status_code == 200 and (tmp_path / r.json()["last_file"]).is_file()
    r = httpx.put(f"{live_server}/api/auto-backup", json={"enabled": True, "folder": "rel", "keep": 5})
    assert r.status_code == 400 and "full folder path" in r.json()["detail"]

    key = apikey.create()
    try:
        remote = {"X-Forwarded-For": "100.64.0.9", "Authorization": f"Bearer {key}"}
        for method, path in (("GET", ""), ("PUT", ""), ("POST", "/run")):
            r = httpx.request(method, f"{live_server}/api/auto-backup{path}", headers=remote,
                              json={"enabled": False} if method == "PUT" else None)
            assert r.status_code == 403 and str(tmp_path) not in r.text, (method, r.text)
    finally:
        apikey.disable()


@pytest.mark.browser
def test_settings_page_daily_backup(page, tmp_path):
    settings.update(auto_backup=None, auto_backup_state=None)
    page.goto(page.base + "/#settings")
    page.wait_for_selector("#ab-enabled")
    assert not page.is_checked("#ab-enabled") and page.text_content("#ab-status") == "No automatic backup yet."
    assert page.get_attribute("#ab-folder", "placeholder") == str(config.DATA_DIR / "backups")
    page.check("#ab-enabled")
    page.fill("#ab-folder", str(tmp_path))
    page.fill("#ab-keep", "3")
    page.click("#ab-save")
    page.wait_for_selector("#toast.ok:has-text('Backup settings saved.')")
    assert autobackup.options() == {"enabled": True, "folder": str(tmp_path), "keep": 3}
    page.wait_for_selector("#ab-next")
    page.click("#ab-run")
    page.wait_for_selector("#ab-status.ok:has-text('Last backup')", timeout=60000)
    assert len(autobackup.backups(tmp_path)) == 1 and "1 kept" in page.text_content("#ab-status")

    page.fill("#ab-folder", "not/absolute")
    page.click("#ab-save")
    page.wait_for_selector("#toast.error:has-text('full folder path')")
    page.errors[:] = [e for e in page.errors if "400" not in e]
    assert autobackup.options()["folder"] == str(tmp_path)          # unchanged
