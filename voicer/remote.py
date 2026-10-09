"""Remote access through Tailscale: agents on a VPS reach this PC at https://<pc>.<tailnet>.ts.net, which
`tailscale serve` passes to the server on localhost. Only devices in your tailnet can connect, the link is
encrypted by Tailscale, and every request through it must send the API key (see apikey.allowed)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import apikey, config

# Tailscale for Windows (recommended: it also covers Windows apps) and Tailscale installed inside WSL/Linux.
WINDOWS_CLI = Path("/mnt/c/Program Files/Tailscale/tailscale.exe")
FUNNEL_WARNING = ("Tailscale Funnel is on: the server is open to the whole internet, not just your tailnet. "
                  "Turn it off with: tailscale funnel reset")


def find_cli() -> tuple[str, str] | None:
    """`(path, where)` of the Tailscale command line tool, where = `linux` (this WSL/Linux) or `windows`."""
    linux = shutil.which("tailscale")
    if linux:
        return linux, "linux"
    if WINDOWS_CLI.is_file():
        return str(WINDOWS_CLI), "windows"
    return None


def _json(cli: str, *args: str):
    try:
        out = subprocess.run([cli, *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    try:
        return json.loads(out.stdout) if out.stdout.strip() else None
    except ValueError:
        return None


def _serves_us(target: str) -> bool:
    """True if a `tailscale serve` proxy target points at this server's port on this PC."""
    t = target.removeprefix("http://").removeprefix("https+insecure://").removeprefix("https://").rstrip("/")
    host, _, port = t.rpartition(":")
    return port == str(config.PORT) and host in ("", "localhost", "127.0.0.1", "[::1]")


def status() -> dict:
    """What the API page shows: is Tailscale installed and signed in, and is this server shared on the tailnet."""
    port = config.PORT
    out = {"installed": False, "where": None, "running": False, "dns_name": None, "ips": [], "serving": False,
           "funnel": False, "url": None, "api_key_on": apikey.status()["enabled"], "port": port, "warnings": []}
    found = find_cli()
    if not found:
        return out
    cli, out["where"] = found
    out["installed"] = True
    st = _json(cli, "status", "--json") or {}
    me = st.get("Self") or {}
    out["running"] = st.get("BackendState") == "Running"
    out["dns_name"] = (me.get("DNSName") or "").rstrip(".") or None
    out["ips"] = [ip for ip in me.get("TailscaleIPs") or [] if isinstance(ip, str)]
    if out["running"]:
        serve = _json(cli, "serve", "status", "--json") or {}
        for hostport, web in (serve.get("Web") or {}).items():
            for handler in ((web or {}).get("Handlers") or {}).values():
                if _serves_us(str((handler or {}).get("Proxy") or "")):
                    out["serving"] = True
                    host, _, p = hostport.rpartition(":")
                    plain = bool(((serve.get("TCP") or {}).get(p) or {}).get("HTTP"))   # `serve --http=<port>`
                    scheme, default = ("http", "80") if plain else ("https", "443")
                    out["url"] = f"{scheme}://{host}" + ("" if p == default else f":{p}")
                    out["funnel"] = bool((serve.get("AllowFunnel") or {}).get(hostport))
    if out["funnel"]:
        out["warnings"].append(FUNNEL_WARNING)
    if out["serving"] and not out["api_key_on"]:
        out["warnings"].append("The API key is off, so remote requests are refused. Make a key on this page.")
    return out


def public_base(request) -> str:
    """This server's address as the caller sees it. Behind `tailscale serve` the request arrives as plain HTTP on
    localhost; the proxy's X-Forwarded-Proto / X-Forwarded-Host give the real https://<pc>.ts.net address.
    Only used to build links sent back to the same caller, so trusting these headers is safe."""
    base = str(request.base_url).rstrip("/")
    h = request.headers
    proto = (h.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    host = (h.get("x-forwarded-host") or "").split(",")[0].strip()
    if proto not in ("http", "https") and not host:
        return base
    from urllib.parse import urlsplit

    u = urlsplit(base)
    if host and not all(c.isalnum() or c in ".-:[]" for c in host):
        host = ""                                     # not a host name: ignore
    return f"{proto if proto in ('http', 'https') else u.scheme}://{host or u.netloc}{u.path}".rstrip("/")
