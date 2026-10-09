"""Phase 12: Windows desktop shortcut (WSL only): starts the server and opens the UI."""
import os
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path

import httpx
import pytest

from test_scripts import ROOT, _free_port

WSL = "microsoft" in Path("/proc/version").read_text().lower() and shutil.which("powershell.exe")
pytestmark = pytest.mark.skipif(not WSL, reason="needs WSL on Windows")


def ps(cmd: str) -> str:
    return subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd], cwd="/mnt/c",
                          capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL).stdout.replace("\r", "").strip()


@pytest.fixture()
def win_folder():
    """An empty folder on the Windows drive (like the Desktop; a \\\\wsl$ path would add a security prompt)."""
    win = ps("[IO.Path]::GetTempPath()").rstrip("\\") + f"\\voicer-test-{uuid.uuid4().hex[:8]}"
    linux = Path(subprocess.run(["wslpath", "-u", win], capture_output=True, text=True).stdout.strip())
    linux.mkdir()
    yield win, linux
    for p in linux.glob("*.lnk"):
        p.unlink()
    linux.rmdir()


def _server_pid(port: int) -> int | None:
    for p in Path("/proc").iterdir():
        try:
            if p.name.isdigit() and f"VOICER_PORT={port}".encode() in (p / "environ").read_bytes().split(b"\0") \
                    and b"voicer" in (p / "cmdline").read_bytes():
                return int(p.name)
        except OSError:
            continue
    return None


def test_desktop_shortcut_starts_the_server_and_opens_the_ui(tmp_path, win_folder):
    win, linux = win_folder
    port = _free_port()
    opened = tmp_path / "opened.txt"
    browser = tmp_path / "browser.sh"
    browser.write_text(f'#!/bin/sh\necho "$1" >> {opened}\n')
    browser.chmod(0o755)
    data = tmp_path / "data with space"
    env = {**os.environ, "VOICER_DESKTOP": win, "VOICER_PORT": str(port), "VOICER_DATA": str(data),
           "VOICER_BROWSER": str(browser)}
    out = subprocess.run([ROOT / "windows.sh", "shortcut"], env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and "Desktop shortcut made" in out.stdout, out.stderr
    lnk = f"{win}\\Voice Studio.lnk"
    assert (linux / "Voice Studio.lnk").is_file()
    target, args, style = ps(f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}'); "
                             "$s.TargetPath; $s.Arguments; $s.WindowStyle").splitlines()
    assert target.lower().endswith("\\system32\\wsl.exe") and style == "7"          # minimized window
    assert f'--cd "{ROOT}"' in args and args.endswith("./start.sh --open") and f"VOICER_PORT='{port}'" in args

    ps(f"Start-Process -FilePath '{lnk}'")                                            # = double-click
    pid = None
    try:
        for _ in range(120):
            if opened.exists():
                break
            time.sleep(0.5)
        assert opened.read_text().split() == [f"http://localhost:{port}"]
        win_health = subprocess.run(["cmd.exe", "/c", "curl.exe", "-s", f"http://localhost:{port}/api/health"],
                                    cwd="/mnt/c", capture_output=True, text=True, timeout=30).stdout
        assert '"status":"ok"' in win_health                                         # reached from Windows
        assert (data / "voices").is_dir()                                             # the folder with a space
        pid = _server_pid(port)
        assert pid
    finally:
        pid = pid or _server_pid(port)
        if pid:
            os.kill(pid, signal.SIGINT)
    for _ in range(40):
        if not _server_pid(port):
            break
        time.sleep(0.5)
    assert not _server_pid(port)

    out = subprocess.run([ROOT / "windows.sh", "remove-shortcut"], env=env, capture_output=True, text=True, timeout=60)
    assert "removed" in out.stdout and not (linux / "Voice Studio.lnk").exists()
    out = subprocess.run([ROOT / "windows.sh", "remove-shortcut"], env=env, capture_output=True, text=True, timeout=60)
    assert "no desktop shortcut" in out.stdout


def test_help_and_bad_command():
    out = subprocess.run([ROOT / "windows.sh", "--help"], capture_output=True, text=True)
    assert out.returncode == 0 and "./windows.sh shortcut" in out.stdout
    bad = subprocess.run([ROOT / "windows.sh", "nope"], capture_output=True, text=True)
    assert bad.returncode == 2 and "Unknown command: nope" in bad.stderr


def test_autostart_starts_the_server_at_sign_in_without_a_browser(tmp_path, win_folder):
    win, linux = win_folder
    port = _free_port()
    opened = tmp_path / "opened.txt"
    browser = tmp_path / "browser.sh"
    browser.write_text(f'#!/bin/sh\necho "$1" >> {opened}\n')
    browser.chmod(0o755)
    env = {**os.environ, "VOICER_STARTUP": win, "VOICER_PORT": str(port), "VOICER_DATA": str(tmp_path / "data"),
           "VOICER_BROWSER": str(browser)}
    out = subprocess.run([ROOT / "windows.sh", "autostart", "on"], env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and "Auto-start is on" in out.stdout, out.stderr
    lnk = f"{win}\\Voice Studio.lnk"
    target, args, style = ps(f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}'); "
                             "$s.TargetPath; $s.Arguments; $s.WindowStyle").splitlines()
    assert target.lower().endswith("\\system32\\wsl.exe") and style == "7" and args.endswith(" ./start.sh")

    ps(f"Start-Process -FilePath '{lnk}'")                                            # = Windows sign-in
    try:
        for _ in range(120):
            if _server_pid(port):
                try:
                    if httpx.get(f"http://localhost:{port}/api/health").json()["status"] == "ok":
                        break
                except httpx.HTTPError:
                    pass
            time.sleep(0.5)
        else:
            pytest.fail("the server did not start")
        time.sleep(2)
        assert not opened.exists()                                                    # no browser at sign-in
    finally:
        pid = _server_pid(port)
        if pid:
            os.kill(pid, signal.SIGINT)
    for _ in range(40):
        if not _server_pid(port):
            break
        time.sleep(0.5)
    assert not _server_pid(port)

    out = subprocess.run([ROOT / "windows.sh", "autostart", "off"], env=env, capture_output=True, text=True, timeout=60)
    assert "Auto-start is off." in out.stdout and not (linux / "Voice Studio.lnk").exists()
    out = subprocess.run([ROOT / "windows.sh", "autostart", "off"], env=env, capture_output=True, text=True, timeout=60)
    assert "already off" in out.stdout
    bad = subprocess.run([ROOT / "windows.sh", "autostart"], capture_output=True, text=True)
    assert bad.returncode == 2 and "autostart on|off" in bad.stderr


def test_the_real_startup_folder_is_found():
    assert ps("[Environment]::GetFolderPath('Startup')").endswith("\\Start Menu\\Programs\\Startup")
