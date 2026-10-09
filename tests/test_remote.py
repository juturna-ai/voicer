"""Phase 10: remote access via Tailscale — agents on a VPS reach the server through `tailscale serve`
(a proxy on this PC). Through it, every request needs the API key; links point at the https tailnet address."""
import json
import os
import stat

import anyio
import httpx
import pytest

from voicer import apikey, config, remote

EN = "piper-en-us-lessac-medium"
TS = "voicer-pc.tail1234.ts.net"
# What `tailscale serve` adds on the way in (it is a reverse proxy on this PC).
VIA_TAILSCALE = {"X-Forwarded-For": "100.101.102.103", "X-Forwarded-Proto": "https", "X-Forwarded-Host": TS,
                 "Tailscale-User-Login": "me@example.com", "Host": TS}


def fake_cli(tmp_path, status, serve):
    """A stand-in `tailscale` program that prints the given JSON for `status --json` / `serve status --json`."""
    (tmp_path / "status.json").write_text(json.dumps(status))
    (tmp_path / "serve.json").write_text(json.dumps(serve))
    p = tmp_path / "tailscale"
    p.write_text(f'#!/bin/sh\nif [ "$1" = serve ]; then cat "{tmp_path}/serve.json"; else cat "{tmp_path}/status.json"; fi\n')
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


@pytest.fixture()
def path_with(monkeypatch, tmp_path):
    def use(status, serve):
        fake_cli(tmp_path, status, serve)
        monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(remote, "WINDOWS_CLI", tmp_path / "missing.exe")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")          # no real tailscale
    return use


def test_status_not_installed(path_with):
    s = remote.status()
    assert (s["installed"], s["running"], s["serving"], s["url"]) == (False, False, False, None)


def test_status_signed_in_and_sharing(path_with):
    me = {"BackendState": "Running", "Self": {"DNSName": TS + ".", "TailscaleIPs": ["100.101.102.103", "fd7a::1"]}}
    path_with(me, {})
    s = remote.status()
    assert s["installed"] and s["where"] == "linux" and s["running"] and s["dns_name"] == TS and not s["serving"]

    serve = {"TCP": {"443": {"HTTPS": True}},
             "Web": {f"{TS}:443": {"Handlers": {"/": {"Proxy": f"http://127.0.0.1:{config.PORT}"}}}}}
    path_with(me, serve)
    s = remote.status()
    assert s["serving"] and s["url"] == f"https://{TS}" and not s["funnel"]
    assert any("API key is off" in w for w in s["warnings"])

    path_with(me, {**serve, "AllowFunnel": {f"{TS}:443": True}})
    assert remote.status()["funnel"] and any("Funnel" in w for w in remote.status()["warnings"])

    for tcp, web, url in ((80, {"HTTP": True}, f"http://{TS}"), (8080, {"HTTP": True}, f"http://{TS}:8080"),
                          (8443, {"HTTPS": True}, f"https://{TS}:8443")):            # `tailscale serve --http=80` etc.
        path_with(me, {"TCP": {str(tcp): web},
                       "Web": {f"{TS}:{tcp}": {"Handlers": {"/": {"Proxy": f"http://127.0.0.1:{config.PORT}"}}}}})
        assert remote.status()["url"] == url

    other = {"Web": {f"{TS}:8443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:3000"}}}}}   # another app
    path_with(me, other)
    assert not remote.status()["serving"]

    path_with({"BackendState": "NeedsLogin", "Self": {}}, {})
    s = remote.status()
    assert s["installed"] and not s["running"] and not s["serving"]


def test_through_tailscale_the_key_is_required_and_links_are_https(live_server):
    apikey.disable()
    r = httpx.get(f"{live_server}/api/voices", headers=VIA_TAILSCALE)
    assert r.status_code == 401 and "Remote access needs the API key" in r.json()["detail"]
    r = httpx.post(f"{live_server}/v1/audio/speech", json={"input": "Hi", "voice": EN}, headers=VIA_TAILSCALE)
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_api_key"
    assert httpx.get(f"{live_server}/api/voices").status_code == 200          # this PC: still open
    assert httpx.get(f"{live_server}/api/remote-access").json()["port"] == config.PORT

    key = apikey.create()
    try:
        auth = {**VIA_TAILSCALE, "Authorization": f"Bearer {key}"}
        assert httpx.get(f"{live_server}/api/remote-access", headers=auth).status_code == 403   # this PC only
        assert httpx.get(f"{live_server}/api/voices", headers={**VIA_TAILSCALE, "Authorization": "Bearer vs_wrong"}).status_code == 401
        r = httpx.post(f"{live_server}/api/batch", json={"items": [{"text": "Remote batch."}], "voice": EN},
                       headers=auth, timeout=120)
        assert r.status_code == 200, r.text
        assert r.json()["items"][0]["url"].startswith(f"https://{TS}/api/history/")   # a link the VPS can open

        r = httpx.post(f"{live_server}/v1/audio/speech", json={"input": "Remote speech.", "voice": EN},
                       headers=auth, timeout=120)
        assert r.status_code == 200 and len(r.content) > 1000

        import httpx2
        from mcp import Client
        from mcp.client.streamable_http import streamable_http_client

        async def main():
            client = httpx2.AsyncClient(headers=auth)
            async with Client(streamable_http_client(f"{live_server}/mcp", http_client=client)) as c:
                return await c.call_tool("speak", {"text": "Remote agent.", "voice": EN})

        out = anyio.run(main).structured_content
        assert out["url"].startswith(f"https://{TS}/api/history/") and "path" not in out
    finally:
        apikey.disable()


def test_websocket_through_tailscale_needs_the_key():
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    from voicer.server import app

    apikey.disable()
    hdrs = {k: v for k, v in VIA_TAILSCALE.items() if k != "Host"}
    with pytest.raises(WebSocketDisconnect):
        with TestClient(app).websocket_connect("/api/ws/speak", headers=hdrs) as ws:
            ws.receive_json()
    key = apikey.create()
    try:
        with TestClient(app).websocket_connect("/api/ws/speak", headers={**hdrs, "Authorization": f"Bearer {key}"}) as ws:
            ws.send_json({"text": "Hi.", "voice": EN})
            assert ws.receive_json()["type"] == "start"
    finally:
        apikey.disable()


def test_public_base():
    from starlette.requests import Request

    def req(headers, host="127.0.0.1:8765"):
        raw = [(b"host", host.encode())] + [(k.lower().encode(), v.encode()) for k, v in headers.items()]
        return Request({"type": "http", "scheme": "http", "server": ("127.0.0.1", 8765), "path": "/", "root_path": "",
                        "headers": raw, "query_string": b""})

    assert remote.public_base(req({})) == "http://127.0.0.1:8765"
    assert remote.public_base(req({"X-Forwarded-Proto": "https", "X-Forwarded-Host": TS})) == f"https://{TS}"
    assert remote.public_base(req({"X-Forwarded-Proto": "https"}, host=TS)) == f"https://{TS}"
    assert remote.public_base(req({"X-Forwarded-Host": "evil.com/x?"})) == "http://127.0.0.1:8765"   # junk ignored
