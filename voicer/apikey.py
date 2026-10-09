"""Optional API key. Off by default. When on, requests from other devices must send it
(`Authorization: Bearer <key>` or `X-API-Key: <key>`); this PC (loopback, not via a proxy) needs no key.
Only a SHA-256 hash of the key is stored (data/settings.json); the key itself is shown once, when it is made."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
import time

from . import settings

PREFIX = "vs_"
# Headers a reverse proxy (e.g. `tailscale serve`, nginx) adds: such a request is not from this PC even if it
# reaches us over loopback.
PROXY_HEADERS = ("x-forwarded-for", "x-forwarded-host", "x-forwarded-proto", "x-real-ip", "forwarded", "tailscale-user-login")


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def status() -> dict:
    """`{enabled, hint, created}` — never the key or its hash."""
    s = settings.load().get("api_key") or {}
    return {"enabled": bool(s.get("hash")), "hint": s.get("hint"), "created": s.get("created")}


def create() -> str:
    """Make a new key (replaces any old one). Returns the key; it cannot be read back later."""
    key = PREFIX + secrets.token_urlsafe(32)
    settings.update(api_key={"hash": _hash(key), "hint": f"{PREFIX}…{key[-4:]}",
                             "created": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    return key


def disable() -> None:
    settings.update(api_key=None)


def valid(key: str | None) -> bool:
    h = (settings.load().get("api_key") or {}).get("hash")
    return bool(h and key) and hmac.compare_digest(_hash(key), h)


def from_headers(headers) -> str | None:
    """The key sent with a request, if any (`headers` = case-insensitive mapping)."""
    auth = headers.get("authorization") or ""
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip() or None
    return (headers.get("x-api-key") or "").strip() or None


def proxied(headers) -> bool:
    """True when the request came through a reverse proxy (e.g. `tailscale serve`): another device."""
    return any(h in headers for h in PROXY_HEADERS)


def is_local(client_host: str | None, headers) -> bool:
    """True for a direct request from this PC (loopback address, no proxy headers)."""
    if proxied(headers):
        return False
    try:
        ip = ipaddress.ip_address(client_host or "")
    except ValueError:                                   # e.g. a test client or a unix socket
        return False
    if ip.version == 6 and ip.ipv4_mapped:               # "::ffff:127.0.0.1"
        ip = ip.ipv4_mapped
    return ip.is_loopback


def allowed(client_host: str | None, headers) -> bool:
    """Key off: open, except requests through a proxy (remote access, e.g. Tailscale), which always need the key.
    Key on: this PC, or the right key."""
    if not status()["enabled"]:
        return not proxied(headers)
    return is_local(client_host, headers) or valid(from_headers(headers))
