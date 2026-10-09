import os
import sys
import tempfile
from pathlib import Path

import pytest

# Isolate test data from real user data.
os.environ.setdefault("VOICER_DATA", tempfile.mkdtemp(prefix="voicer-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pytest_configure(config):
    config.addinivalue_line("markers", "gpu: needs models / GPU (slow)")
    config.addinivalue_line("markers", "browser: drives headless Chromium (Playwright)")


_whisper = None


def transcribe(path, language=None) -> str:
    global _whisper
    from faster_whisper import WhisperModel

    if _whisper is None:
        _whisper = WhisperModel("small", device="cpu", compute_type="int8")
    segs, _ = _whisper.transcribe(str(path), language=language)
    return " ".join(s.text for s in segs).strip()


def similar(a: str, b: str) -> float:
    import difflib
    import re

    norm = lambda s: re.sub(r"[^\w ]", "", s.lower()).split()
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


@pytest.fixture(scope="session")
def tmp_out():
    return Path(tempfile.mkdtemp(prefix="voicer-out-"))


@pytest.fixture(scope="session")
def live_server():
    """Real uvicorn server on a free port (test data dir). Yields the base URL."""
    import socket
    import threading
    import time

    import uvicorn

    from voicer.server import app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    t.join(5)


@pytest.fixture()
def page(live_server):
    """Headless Chromium page; fails the test on any JS error."""
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
        ctx = browser.new_context(permissions=["microphone"])
        pg = ctx.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
        pg.base = live_server
        pg.errors = errors                      # a test may remove an error it expects
        yield pg
        browser.close()
        assert not errors, errors
