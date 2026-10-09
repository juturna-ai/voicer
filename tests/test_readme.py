"""Phase 12: README.md is short and its examples work as written (against a test server)."""
import json
import re
import subprocess
from pathlib import Path

import pytest

from conftest import similar, transcribe
from test_formats import probe
from test_mcp import run

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text()
BLOCKS = re.findall(r"```(\w+)\n(.*?)```", README, re.S)


def test_short_and_covers_the_topics():
    assert len(README.splitlines()) < 50
    for topic in ("## Start", "## Browse the library", "## Clone a voice", "## API", "## MCP"):
        assert topic in README
    for script in re.findall(r"\./(\w+\.sh)", README):
        assert (ROOT / script).is_file(), script


@pytest.mark.gpu
def test_examples_run(live_server, tmp_path):
    host = live_server.removeprefix("http://")
    bash = next(code for lang, code in BLOCKS if lang == "bash" and "curl" in code).replace("localhost:8765", host)
    out = subprocess.run(["bash", "-euo", "pipefail", "-c", bash], cwd=tmp_path, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr
    assert probe(tmp_path / "hola.mp3")[1]["format_name"] == "mp3"
    assert similar(transcribe(tmp_path / "hola.mp3", "es"), "Hola, qué tal") >= 0.6
    assert all(v["language"] == "es" for v in json.loads(out.stdout))

    sdk = re.search(r"OpenAI SDK: `(.*?)`\.", README)[1].replace("http://localhost:8765", live_server)
    py = f"from openai import OpenAI\n{sdk}.write_to_file('hi.mp3')"
    out = subprocess.run([ROOT / ".venv/bin/python", "-c", py], cwd=tmp_path, capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr
    assert similar(transcribe(tmp_path / "hi.mp3", "en"), "Hi") >= 0.5

    config = json.loads(next(code for lang, code in BLOCKS if lang == "json"))
    url = config["mcpServers"]["voice-studio"]["url"].replace("http://localhost:8765", live_server)

    async def calls(c):
        return [t.name for t in (await c.list_tools()).tools]
    assert {"list_voices", "search_voices", "speak"} <= set(run(url, calls))
