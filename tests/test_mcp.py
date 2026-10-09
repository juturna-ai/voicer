"""Phase 7: MCP server — tools list_voices, search_voices, speak over stdio and streamable HTTP (/mcp)."""
import os
import sys
from pathlib import Path

import anyio
import httpx
import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from conftest import similar, transcribe
from test_formats import probe

ROOT = Path(__file__).resolve().parent.parent
TEXT = "Hello from the voice studio agent tool."


def run(server, calls):
    """Connect an MCP client to `server`, run `calls(client)`, return its result."""
    async def main():
        async with Client(server) as c:
            return await calls(c)
    return anyio.run(main)


def stdio_server():
    return StdioServerParameters(command=sys.executable, args=["-m", "voicer.mcp_server"], cwd=str(ROOT),
                                 env={**os.environ})


def test_stdio_tools_search_and_whatsapp_note():
    async def calls(c):
        tools = {t.name: t for t in (await c.list_tools()).tools}
        found = await c.call_tool("search_voices", {"query": "lessac", "language": "en"})
        spoken = await c.call_tool("speak", {"text": TEXT, "voice": "piper-en-us-lessac-medium", "language": "en",
                                             "format": "ogg_opus"})
        bad = await c.call_tool("speak", {"text": "Hi", "voice": "no-such-voice"})
        empty = await c.call_tool("speak", {"text": "  ", "voice": "piper-en-us-lessac-medium"})
        return tools, found, spoken, bad, empty

    tools, found, spoken, bad, empty = run(stdio_server(), calls)
    assert set(tools) == {"list_voices", "search_voices", "speak"}
    props = tools["speak"].input_schema["properties"]
    assert {"text", "voice", "language", "format", "stream"} <= set(props) and "ctx" not in props
    assert [v["id"] for v in found.structured_content["result"]] == ["piper-en-us-lessac-medium"]

    out = spoken.structured_content
    assert not spoken.is_error and out["format"] == "ogg_opus" and out["mime"] == "audio/ogg"
    assert out["url"].endswith(f"/api/history/{out['id']}/audio?format=ogg_opus")
    path = Path(out["path"])
    assert path.suffix == ".ogg" and path.is_file()
    stream, fmt = probe(path)          # native WhatsApp voice note: OGG, Opus, mono, 48 kHz
    assert (stream["codec_name"], stream["channels"], stream["sample_rate"], fmt["format_name"]) == ("opus", 1, "48000", "ogg")
    assert similar(transcribe(path, "en"), TEXT) > 0.8
    from voicer import history

    assert history.get(out["id"])["text"] == TEXT    # saved to History like the UI
    from voicer import usage

    got = [r for r in usage.rows() if r["id"] == out["id"]]   # usage stats: counted under the MCP client's name
    assert [(r["channel"], r["key"]) for r in got] == [("mcp-stdio", usage.THIS_PC)] and got[0]["agent"]

    assert bad.is_error and "Voice 'no-such-voice' not found" in bad.content[0].text
    assert empty.is_error and "Text is empty" in empty.content[0].text


def test_http_list_filter_and_speak(live_server):
    async def calls(c):
        es_female = await c.call_tool("list_voices", {"language": "es", "gender": "female"})
        calm = await c.call_tool("list_voices", {"tag": "calm"})
        spoken = await c.call_tool("speak", {"text": "Hola, esto es una prueba.", "voice": "piper-es-mx-ald-medium",
                                             "format": "mp3"})
        bad = await c.call_tool("search_voices", {"query": "a", "limit": 0})
        return es_female, calm, spoken, bad

    es_female, calm, spoken, bad = run(f"{live_server}/mcp", calls)
    vs = es_female.structured_content["result"]
    assert vs and all(v["language"] == "es" and v["gender"] == "female" for v in vs)
    assert calm.structured_content["result"] and all("calm" in v["tags"] for v in calm.structured_content["result"])
    assert bad.is_error and "limit must be between 1 and 200" in bad.content[0].text

    out = spoken.structured_content
    assert out["url"] == f"{live_server}/api/history/{out['id']}/audio?format=mp3"   # URL of this server
    assert Path(out["path"]).is_file()                 # this PC → also the file path
    r = httpx.get(out["url"])
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and len(r.content) > 1000


def test_http_guards(live_server):
    """Browser pages from other sites are blocked; other devices need the API key; no file paths for them."""
    from voicer import apikey

    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "t", "version": "1"}}}
    hdrs = {"Accept": "application/json, text/event-stream"}
    url = f"{live_server}/mcp"
    r = httpx.post(url, json=init, headers={**hdrs, "Origin": "http://evil.example"})
    assert r.status_code == 403 and r.json() == {"detail": "Origin not allowed"}
    assert httpx.post(url, json=init, headers={**hdrs, "Origin": "http://localhost:8765"}).status_code == 200

    remote = {**hdrs, "X-Forwarded-For": "100.64.0.9"}    # as if it came through a proxy from another device
    key = apikey.create()
    try:
        assert httpx.post(url, json=init, headers=remote).status_code == 401
        assert httpx.post(url, json=init, headers={**remote, "Authorization": f"Bearer {key}"}).status_code == 200

        import httpx2
        from mcp.client.streamable_http import streamable_http_client

        async def calls(c):
            return await c.call_tool("speak", {"text": "Remote test.", "voice": "piper-en-us-lessac-medium"})

        client = httpx2.AsyncClient(headers={"X-Forwarded-For": "100.64.0.9", "Authorization": f"Bearer {key}"})
        out = run(streamable_http_client(url, http_client=client), calls).structured_content
        assert out["url"].endswith("format=mp3") and "path" not in out
    finally:
        apikey.disable()


def test_config_endpoint_shows_paths_only_to_this_pc(live_server):
    from fastapi.testclient import TestClient

    from voicer.server import app

    local = httpx.get(f"{live_server}/api/mcp-config").json()
    assert local["http_path"] == "/mcp" and local["tools"] == ["list_voices", "search_voices", "speak"]
    assert local["stdio"]["module"] == "voicer.mcp_server" and local["stdio"]["root"] == str(ROOT)
    assert Path(local["stdio"]["python"]).is_file() and (ROOT / local["stdio"]["venv_python"]).is_file()
    remote = {"X-Forwarded-For": "100.64.0.9"}
    assert httpx.get(f"{live_server}/api/mcp-config", headers=remote).status_code == 401    # through a proxy: key needed
    from voicer import apikey

    key = apikey.create()
    try:
        r = httpx.get(f"{live_server}/api/mcp-config", headers={**remote, "Authorization": f"Bearer {key}"})
        assert r.json()["stdio"] is None
    finally:
        apikey.disable()
    assert TestClient(app).get("/api/mcp-config").json()["stdio"] is None      # not from this PC
    from voicer.server import create_app

    assert TestClient(create_app()).post("/mcp", json={}).status_code == 503     # MCP runs only with the server
