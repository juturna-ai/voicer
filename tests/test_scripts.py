"""Phase 12: one install script and one start script."""
import os
import re
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize("script", ["install.sh", "start.sh"])
def test_scripts_are_valid(script):
    path = ROOT / script
    assert os.access(path, os.X_OK)
    assert subprocess.run(["bash", "-n", path]).returncode == 0
    out = subprocess.run([path, "--help"], capture_output=True, text=True)
    assert out.returncode == 0 and f"./{script}" in out.stdout and not out.stdout.startswith("#")
    bad = subprocess.run([path, "--nope"], capture_output=True, text=True)
    assert bad.returncode == 2 and "Unknown option: --nope" in bad.stderr


def test_lock_pins_every_package_without_local_tags():
    lock = (ROOT / "requirements" / "lock.txt").read_text().splitlines()
    pins = {re.split(r"==", line)[0].lower().replace("_", "-") for line in lock if line and not line.startswith("#")}
    assert all("==" in line and "+" not in line and " @ " not in line for line in lock if line and not line.startswith("#"))
    for req in ("base.txt", "dev.txt"):
        for line in (ROOT / "requirements" / req).read_text().splitlines():
            m = re.match(r"([A-Za-z0-9_.-]+)", line)
            if m and not line.startswith("#") and " @ " not in line:
                assert m[1].lower().replace("_", "-") in pins, m[1]


def test_start_needs_the_install(tmp_path):
    shutil.copy(ROOT / "start.sh", tmp_path / "start.sh")
    out = subprocess.run([tmp_path / "start.sh"], capture_output=True, text=True)
    assert out.returncode == 1 and "Run ./install.sh first" in out.stderr


def test_start_runs_the_server_opens_the_ui_and_stops_on_ctrl_c(tmp_path):
    port = _free_port()
    opened = tmp_path / "opened.txt"
    browser = tmp_path / "browser.sh"
    browser.write_text(f'#!/bin/sh\necho "$1" >> {opened}\n')
    browser.chmod(0o755)
    env = {**os.environ, "VOICER_PORT": str(port), "VOICER_DATA": str(tmp_path / "data"), "VOICER_BROWSER": str(browser)}
    proc = subprocess.Popen([ROOT / "start.sh", "--open"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, start_new_session=True)
    try:
        url = f"http://localhost:{port}"
        for _ in range(120):
            if opened.exists():
                break
            time.sleep(0.5)
        assert opened.read_text().split() == [url]                 # opened once the server answers
        assert httpx.get(f"{url}/api/health").json()["status"] == "ok"
        assert httpx.get(url).status_code == 200                   # the UI

        again = subprocess.run([ROOT / "start.sh", "--open"], env=env, capture_output=True, text=True, timeout=30)
        assert again.returncode == 0 and "already running" in again.stdout
        assert opened.read_text().split() == [url, url]            # no second server, just the UI again
    finally:
        os.killpg(proc.pid, signal.SIGINT)                         # Ctrl+C
        out, _ = proc.communicate(timeout=30)
    assert proc.returncode == 0 and "Application shutdown complete" in out
    with pytest.raises(httpx.ConnectError):
        httpx.get(f"http://localhost:{port}/api/health")


@pytest.mark.skipif(not os.environ.get("VOICER_TEST_INSTALL"), reason="slow: set VOICER_TEST_INSTALL=1 (needs network)")
def test_install_in_a_fresh_copy(tmp_path):
    for p in ("voicer", "requirements", "library", "install.sh", "start.sh"):
        (shutil.copytree if (ROOT / p).is_dir() else shutil.copy2)(ROOT / p, tmp_path / p,
                                                                  **({"ignore": shutil.ignore_patterns("__pycache__")} if (ROOT / p).is_dir() else {}))
    out = subprocess.run([tmp_path / "install.sh"], capture_output=True, text=True, timeout=3600)
    assert out.returncode == 0, out.stderr[-2000:]
    assert "Voice Studio is installed" in out.stdout
