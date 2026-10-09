"""Phase 10: usage stats — requests, characters and audio minutes per voice and per agent / API key."""
import json
import time

import anyio
import httpx
import pytest
from fastapi.testclient import TestClient

from voicer import apikey, usage

EN = "piper-en-us-lessac-medium"


def row(clip_id: str) -> dict:
    found = [r for r in usage.rows() if r["id"] == clip_id]
    assert len(found) == 1, found
    return found[0]


def test_agent_names_from_headers():
    assert usage.agent_from({"x-voicer-agent": "n8n flow\n7", "user-agent": "curl/8.5"}) == "n8n flow 7"
    assert usage.agent_from({"user-agent": "curl/8.5.0"}) == "curl"
    assert usage.agent_from({"user-agent": "Mozilla/5.0 (Windows NT 10.0)"}) == "Web browser"
    assert usage.agent_from({}) == "Unknown"
    assert len(usage.agent_from({"x-voicer-agent": "x" * 500})) == 60


def test_summary_adds_up_per_voice_agent_key_and_day(tmp_path, monkeypatch):
    monkeypatch.setattr(usage, "_path", lambda: tmp_path / "usage.jsonl")
    assert usage.summary()["totals"] == {"requests": 0, "characters": 0, "seconds": 0.0, "minutes": 0.0}

    def add(text, voice, secs, agent, key, settings=None, engine="piper"):
        usage.set_caller("rest", agent, key)
        usage.record({"id": text, "text": text, "voice_id": voice, "voice_name": voice.upper(), "seconds": secs,
                      "engine": engine}, settings)

    add("hello", "a", 60, "Bot", usage.THIS_PC)
    add("hi", "a", 30, "Bot", "vs_…abcd")
    add("four", "b", 30, "curl", "vs_…abcd")
    add("line one line two", "x", 12, "Bot", usage.THIS_PC, {"dialogue": [{}, {}]})
    add("(voice changer)", "b", 6, "Web browser", usage.THIS_PC, {}, engine="openvoice")
    with open(tmp_path / "usage.jsonl", "a") as f:
        f.write('{"t": 1, "id": "old", "chars": 5, "seconds": 9}\n{"half-writ')   # very old + a broken last line

    s = usage.summary(30)
    assert s["totals"] == {"requests": 5, "characters": 5 + 2 + 4 + 17, "seconds": 138.0, "minutes": 2.3}
    by_voice = {v["voice_id"]: v for v in s["by_voice"]}
    assert by_voice["a"] == {"name": "A", "voice_id": "a", "requests": 2, "characters": 7, "seconds": 90.0, "minutes": 1.5}
    assert by_voice["dialogue"]["name"] == "Dialogue (several voices)"
    assert by_voice["b"]["characters"] == 4                       # the voice changer reads no text
    assert [(a["name"], a["requests"]) for a in s["by_agent"]] == [("Bot", 3), ("Web browser", 1), ("curl", 1)]
    assert {k["name"]: k["requests"] for k in s["by_key"]} == {usage.THIS_PC: 3, "vs_…abcd": 2}
    assert [d["name"] for d in s["by_day"]] == [time.strftime("%Y-%m-%d")]
    assert usage.summary(0)["totals"]["requests"] == 6            # all time includes the old line
    with pytest.raises(ValueError):
        usage.summary(-1)


def test_rest_and_openai_calls_are_counted_with_agent_and_key(live_server):
    r = httpx.post(f"{live_server}/api/speak", json={"text": "Count me.", "voice": EN},
                   headers={"X-Voicer-Agent": "Morning briefing bot"}, timeout=120)
    assert r.status_code == 200, r.text
    got = row(r.headers["x-voicer-id"])
    assert {k: got[k] for k in ("kind", "voice_id", "chars", "channel", "agent", "key")} == {
        "kind": "tts", "voice_id": EN, "chars": 9, "channel": "rest", "agent": "Morning briefing bot", "key": usage.THIS_PC}
    assert got["seconds"] > 0.3

    for stream in (False, True):                        # a live stream is counted too, when it is saved
        r = httpx.post(f"{live_server}/v1/audio/speech", json={"model": "tts-1", "input": "Open AI style.",
                       "voice": EN, "stream": stream}, headers={"User-Agent": "OpenAI/Python 1.40"}, timeout=120)
        assert r.status_code == 200, r.text
        got = row(r.headers["x-voicer-id"])
        assert (got["channel"], got["agent"], got["key"]) == ("openai", "OpenAI", usage.THIS_PC)

    key = apikey.create()
    try:
        remote = {"X-Forwarded-For": "100.64.0.9", "Authorization": f"Bearer {key}", "User-Agent": "curl/8.5.0"}
        r = httpx.post(f"{live_server}/api/speak", json={"text": "From the phone.", "voice": EN}, headers=remote,
                       timeout=120)
        assert r.status_code == 200, r.text
        assert (row(r.headers["x-voicer-id"])["key"], row(r.headers["x-voicer-id"])["agent"]) == (f"vs_…{key[-4:]}", "curl")
    finally:
        apikey.disable()

    s = httpx.get(f"{live_server}/api/usage", params={"days": 1}).json()
    assert s["days"] == 1 and s["totals"]["requests"] >= 4
    assert any(a["name"] == "Morning briefing bot" for a in s["by_agent"])
    assert any(v["voice_id"] == EN and v["minutes"] > 0 for v in s["by_voice"])
    assert {"rest", "openai"} <= {c["name"] for c in s["by_channel"]}
    assert httpx.get(f"{live_server}/api/usage", params={"days": -1}).status_code == 400


def test_websocket_calls_are_counted():
    from voicer.server import app

    with TestClient(app).websocket_connect("/api/ws/speak", headers={"X-Voicer-Agent": "Live reader"}) as ws:
        ws.send_json({"text": "Socket words.", "voice": EN})
        while (m := ws.receive()).get("text") is None or json.loads(m["text"])["type"] != "done":
            pass
        clip = json.loads(m["text"])["id"]
    got = row(clip)
    assert (got["channel"], got["agent"], got["key"]) == ("websocket", "Live reader", usage.NO_KEY)   # testclient = not this PC


def test_mcp_calls_are_counted_with_the_client_name(live_server):
    from mcp import Client
    from mcp.types import Implementation

    async def main():
        async with Client(f"{live_server}/mcp", client_info=Implementation(name="Claude Desktop", version="1")) as c:
            return await c.call_tool("speak", {"text": "Agent speaking.", "voice": EN, "format": "wav"})

    out = anyio.run(main).structured_content
    got = row(out["id"])
    assert (got["channel"], got["agent"], got["key"], got["chars"]) == ("mcp", "Claude Desktop", usage.THIS_PC, 15)
