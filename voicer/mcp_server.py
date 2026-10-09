"""MCP server for AI agents. Tools: list_voices, search_voices, speak.

stdio:  .venv/bin/python -m voicer.mcp_server
HTTP:   http://localhost:8765/mcp (streamable HTTP, served by the main server; same API key rules)
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import TypedDict

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import __version__, apikey, config, formats, history, jobs, library, remote, tts, usage, voices

FIELDS = ("id", "name", "language", "accent", "gender", "age", "tags", "engine", "license", "commercial", "description")

mcp = MCPServer(
    "Voice Studio",
    version=__version__,
    instructions="Local text to speech in English and Spanish. Call list_voices or search_voices to find a "
                 "voice, then speak(text, voice). Use format='ogg_opus' for WhatsApp voice notes.",
)


class SpeakResult(TypedDict, total=False):
    id: str
    voice: str
    voice_id: str
    language: str
    format: str
    mime: str
    seconds: float
    stream: bool
    url: str
    subtitles_url: str
    path: str


def _card(v: dict, origin: str, default: str | None) -> dict:
    return {**{k: v[k] for k in FIELDS if k in v}, "origin": origin, "default": v["id"] == default}


def _all() -> list[dict]:
    default = voices.default_id()
    return [_card(v, "mine", default) for v in voices.all_voices()] + \
           [_card(v, "library", default) for v in library.catalog()]


@contextmanager
def _clear_errors():
    """Bad input (unknown voice, empty text, …) → a tool error with a clear message, no traceback."""
    try:
        yield
    except KeyError as e:
        raise ToolError(str(e.args[0]) if e.args else "Not found") from None
    except ValueError as e:
        raise ToolError(str(e)) from None


def _match(c: dict, language: str, gender: str, tag: str) -> bool:
    return ((not language or c.get("language") == language)
            and (not gender or c.get("gender") == gender)
            and (not tag or tag.lower() in [t.lower() for t in c.get("tags", [])]))


@mcp.tool()
def list_voices(language: str = "", gender: str = "", tag: str = "") -> list[dict]:
    """List all voices (My Voices first, then the free library).

    Filters are optional: language 'en' or 'es'; gender 'female' or 'male'; tag such as 'warm',
    'narrator', 'news', 'conversational', 'energetic', 'calm'. Pass a voice's `id` or `name` to speak."""
    return [c for c in _all() if _match(c, language, gender, tag)]


@mcp.tool()
def search_voices(query: str, language: str = "", gender: str = "", tag: str = "", limit: int = 20) -> list[dict]:
    """Find voices whose name, id, accent, description or tags contain `query` (case-insensitive).

    Same optional filters as list_voices. Returns at most `limit` voices (1–200)."""
    if not 1 <= limit <= 200:
        raise ToolError("limit must be between 1 and 200")
    q = query.strip().lower()
    out = []
    for c in _all():
        hay = " ".join([c["id"], c.get("name", ""), c.get("accent", ""), c.get("description", ""),
                        *c.get("tags", [])]).lower()
        if q in hay and _match(c, language, gender, tag):
            out.append(c)
    return out[:limit]


def _request(ctx: Context | None):
    """The HTTP request behind this call, or None for stdio."""
    try:
        return getattr(ctx.request_context, "request", None) if ctx else None
    except (AttributeError, LookupError, ValueError):
        return None


@mcp.tool()
async def speak(text: str, voice: str, language: str = "auto", format: str = "mp3", stream: bool = False,
                speed: float = 1.0, ctx: Context | None = None) -> SpeakResult:
    """Speak `text` with `voice` (voice id or name). Saves the clip to History.

    language: 'auto' (per sentence), 'en' or 'es'. format: 'mp3', 'wav' or 'ogg_opus'
    (OGG/Opus mono 48 kHz — plays as a native WhatsApp voice note). speed: 0.5–2.0.
    Returns `url` to download the audio and, for local clients, `path` to the file on this PC.
    `stream`: true asks for the URL to play while it downloads (the clip is finished first)."""
    import anyio.to_thread

    req = _request(ctx)
    try:
        info = ctx.session.client_params.client_info if ctx else None
    except (AttributeError, LookupError, ValueError):
        info = None
    agent = (info.name if info else None) or (usage.agent_from(req.headers) if req is not None else "MCP client")
    if req is not None:
        usage.set_caller("mcp", agent, usage.key_label(req.client.host if req.client else None, req.headers))
    else:
        usage.set_caller("mcp-stdio", agent, usage.THIS_PC)
    try:
        async with jobs.slot():                 # waits its turn with the HTTP speech jobs (one GPU)
            return await anyio.to_thread.run_sync(lambda: _speak(text, voice, language, format, stream, speed, ctx))
    except jobs.Busy as e:
        raise ToolError(str(e)) from None


def _speak(text: str, voice: str, language: str, format: str, stream: bool, speed: float,
           ctx: Context | None) -> SpeakResult:
    with _clear_errors():
        spec = formats.check(format)
        entry = tts.generate(text, voice, language, speed)
        path = formats.encode(history.audio_path(entry["id"]), format)
    req = _request(ctx)
    base = remote.public_base(req) if req is not None else f"http://localhost:{config.PORT}"
    out: SpeakResult = {
        "id": entry["id"],
        "voice": entry["voice_name"],
        "voice_id": entry["voice_id"],
        "language": language,
        "format": format,
        "mime": spec["mime"],
        "seconds": entry["seconds"],
        "stream": stream,
        "url": f"{base}/api/history/{entry['id']}/audio?format={format}",
        "subtitles_url": f"{base}/api/history/{entry['id']}/subtitles?format=srt",
    }
    if req is None or apikey.is_local(req.client.host if req.client else None, req.headers):
        out["path"] = str(path)
    return out


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
