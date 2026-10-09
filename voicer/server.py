"""HTTP server: web UI (static files in voicer/web/) and JSON API under /api."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.routing import Route
from pydantic import BaseModel

from . import __version__, apikey, audio, autobackup, backup, batch, blend, clone, config, dialogue, dictionary, formats, history, jobs, library, openai_api, remote, subtitles, tts, usage, voice_changer, voices
from .models import manager
from .stream import open_stream

WEB = config.ROOT / "voicer" / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .mcp_server import mcp

    manager.start_reaper()          # unload idle models (10 min)
    autobackup.start()              # optional daily backup (off unless turned on in Settings)
    # MCP over HTTP at /mcp. A session manager runs only once, so each server start gets a new one.
    # No Host check here: the API key and the Origin check (require_api_key) guard /mcp.
    http = mcp.streamable_http_app(host=config.HOST).routes[0].app
    if not hasattr(app.state, "mcp_http"):
        app.state.mcp_http = []     # one per running server (tests start several)
    running = app.state.mcp_http
    running.append(http)
    try:
        async with http.session_manager.run():
            yield
    finally:
        running.remove(http)
    manager.stop()
    autobackup.stop()


def _call(fn, *args, **kw):
    """Run a store function; map KeyError → 404 and ValueError → 400 with a clear message."""
    try:
        return fn(*args, **kw)
    except KeyError as e:
        raise HTTPException(404, str(e.args[0]) if e.args else "Not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


def live_reply(text: str, voice: str, language: str, speed: float, engine: str | None, fmt: str,
               download: bool = False) -> StreamingResponse:
    """Live stream (stream.py): the first sentence is spoken before we answer, so errors are still 4xx."""
    info, it = _call(open_stream, text, voice, language, speed, engine, fmt)
    headers = {"X-Voicer-Id": info["id"], "X-Voicer-Sample-Rate": str(info["sample_rate"])}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="voicer-{info["id"]}.{formats.FORMATS[fmt]["ext"]}"'
    return StreamingResponse(it, media_type=info["mime"], headers=headers)


class WsSpeakIn(BaseModel):
    text: str
    voice: str
    language: str = "auto"
    speed: float = 1.0
    engine: str | None = None
    format: str = "pcm"


class PreviewIn(BaseModel):
    text: str = ""
    language: str = ""
    engine: str | None = None


class SaveIn(BaseModel):
    name: str
    language: str
    description: str = ""
    tags: list[str] | str = []
    consent: bool = False
    engine: str | None = None


class BlendIn(BaseModel):
    a: str
    b: str
    ratio: float = 0.5
    text: str = ""
    language: str = ""
    name: str = ""
    description: str = ""
    tags: list[str] | str = []


class TtsIn(BaseModel):
    text: str
    voice: str
    language: str = "auto"
    speed: float = 1.0
    engine: str | None = None
    stability: float | None = None
    expressiveness: float | None = None


class SpeakIn(BaseModel):
    text: str
    voice: str
    language: str = "auto"
    format: str = "mp3"
    stream: bool = False
    speed: float = 1.0
    engine: str | None = None
    download: bool = False


class DialogueIn(BaseModel):
    script: str
    voices: dict[str, str]
    language: str = "auto"
    speed: float = 1.0
    gap: float = 0.4
    format: str = "mp3"
    stream: bool = False
    download: bool = False


class BatchItem(BaseModel):
    text: str
    voice: str | None = None
    language: str | None = None
    speed: float = 1.0
    engine: str | None = None
    name: str | None = None


class BatchIn(BaseModel):
    items: list[BatchItem]
    voice: str | None = None
    language: str = "auto"
    format: str = "mp3"
    zip: bool = False


class BatchZipRow(BaseModel):
    id: str | None = None
    name: str | None = None
    error: str | None = None


class BatchZipIn(BaseModel):
    items: list[BatchZipRow]
    format: str = "mp3"


CARD_FIELDS = ("id", "name", "language", "accent", "gender", "age", "tags", "engine", "kind", "license", "commercial")


def _card(v: dict, origin: str) -> dict:
    """Short voice summary for pickers."""
    from .engines import ENGINES

    eng = ENGINES.get(v.get("engine") or voices.DEFAULT_CLONE_ENGINE)
    return {**{k: v[k] for k in CARD_FIELDS if k in v}, "origin": origin, "controls": list(eng.controls if eng else ())}


def _library_card(v: dict, mine: set) -> dict:
    """Library entry for the Voice Library page: catalog record + preview URL, no file paths."""
    out = {k: x for k, x in v.items() if k not in ("preview", "settings")}
    out["license_short"] = v.get("license", "").split(";")[0].strip()
    out["preview_url"] = f"/api/library/{v['id']}/preview" if library.preview_path(v) else None
    out["added"] = v["id"] in mine
    return out


def _my_card(v: dict, default: str | None) -> dict:
    """My Voices entry: the full record without server paths, plus preview URL, default flag and allowed engines."""
    out = _public(v)
    out["preview_url"] = f"/api/my-voices/{v['id']}/preview"
    out["has_preview"] = bool(v.get("preview")) and (Path(v["dir"]) / v["preview"]).is_file()
    out["default"] = v["id"] == default
    out["allowed_engines"] = voices.allowed_engines(v)
    return out


def _public(voice: dict) -> dict:
    """Voice as sent to clients: no absolute server paths."""
    return {k: v for k, v in voice.items() if k != "dir"}


class _McpEndpoint:
    """ASGI app for /mcp: hands the request to the MCP session manager of the running server."""

    def __init__(self, app: FastAPI):
        self.app = app

    async def __call__(self, scope, receive, send):
        running = getattr(self.app.state, "mcp_http", None)
        if not running:             # app used without its lifespan (e.g. a plain TestClient)
            return await JSONResponse({"detail": "MCP is not running"}, status_code=503)(scope, receive, send)
        await running[-1](scope, receive, send)


LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}


def _mcp_origin_ok(request: Request | WebSocket) -> bool:
    """Block browser pages on other sites from using /mcp (DNS rebinding). Agents send no Origin header;
    a request with a valid API key is allowed from any origin."""
    origin = request.headers.get("origin")
    if not origin:
        return True
    from urllib.parse import urlsplit

    host = urlsplit(origin).hostname or ""
    return (f"[{host}]" if ":" in host else host) in LOCAL_HOSTS or apikey.valid(apikey.from_headers(request.headers))


def create_app() -> FastAPI:
    app = FastAPI(title="Voice Studio", version=__version__, lifespan=lifespan)
    app.add_middleware(jobs.QueueMiddleware)         # added first = runs after the API key check

    @app.middleware("http")
    async def require_api_key(request: Request, call_next):
        """With an API key set, everything except the UI files and health check needs it — unless the
        request comes straight from this PC."""
        path = request.url.path
        if path.startswith("/mcp") and not _mcp_origin_ok(request):
            return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
        open_path = path == "/" or path.startswith("/static/") or path == "/api/health"
        if not open_path and not apikey.allowed(request.client.host if request.client else None, request.headers):
            sent = apikey.from_headers(request.headers)
            msg = "Invalid API key" if sent else "API key required. Send it as 'Authorization: Bearer <key>'."
            if not apikey.status()["enabled"]:     # through a proxy (remote access) with the key off
                msg = "Remote access needs the API key. Make one on the API & Agents page of Voice Studio."
            if path.startswith("/v1/"):       # OpenAI-compatible routes answer in the OpenAI error shape
                r = openai_api.error(401, msg, code="invalid_api_key")
                r.headers["WWW-Authenticate"] = "Bearer"
                return r
            return JSONResponse({"detail": msg}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
        if jobs.JOB_ROUTES.match(path):     # usage stats: who asked (MCP and WebSocket set this themselves)
            usage.set_caller("openai" if path.startswith("/v1/") else "rest", usage.agent_from(request.headers),
                             usage.key_label(request.client.host if request.client else None, request.headers))
        return await call_next(request)

    @app.get("/api/usage")
    def usage_stats(days: int = 30) -> dict:
        """Usage for the last `days` days (0 = all time): `totals` and `by_voice`, `by_agent`, `by_key`,
        `by_channel`, `by_day` — each `{name, requests, characters, seconds, minutes}`. A request = one clip."""
        return _call(usage.summary, days)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "models": manager.status(), "queue": jobs.status()}

    # ---- Clone drafts (uploads/recordings before a voice is saved)
    @app.post("/api/clone/drafts")
    def draft_new() -> dict:
        return clone.new()

    @app.get("/api/clone/drafts/{draft_id}")
    def draft_get(draft_id: str) -> dict:
        return _call(clone.get, draft_id)

    @app.post("/api/clone/drafts/{draft_id}/files")
    async def draft_add(draft_id: str, files: list[UploadFile] = File(...), source: str = "upload") -> dict:
        if source not in ("upload", "mic"):
            raise HTTPException(400, "source must be 'upload' or 'mic'")
        d = _call(clone.get, draft_id)
        errors = []
        for f in files:
            data = await f.read(clone.MAX_FILE_BYTES + 1)
            try:
                d = clone.add_file(draft_id, f.filename or "audio", data, source=source)
            except ValueError as e:
                errors.append({"file": f.filename, "error": str(e)})
        if errors and len(errors) == len(files):
            raise HTTPException(400, "; ".join(f"{e['file']}: {e['error']}" for e in errors))
        return {**d, "errors": errors}

    @app.delete("/api/clone/drafts/{draft_id}/files/{name}")
    def draft_remove(draft_id: str, name: str) -> dict:
        return _call(clone.remove_file, draft_id, name)

    @app.get("/api/clone/drafts/{draft_id}/files/{name}")
    def draft_file(draft_id: str, name: str) -> FileResponse:
        return FileResponse(_call(clone.raw_path, draft_id, name))

    @app.post("/api/clone/drafts/{draft_id}/process")
    def draft_process(draft_id: str) -> dict:
        return _call(clone.process, draft_id)

    @app.post("/api/clone/drafts/{draft_id}/transcribe")
    def draft_transcribe(draft_id: str, language: str = "auto") -> dict:
        return _call(clone.transcribe, draft_id, language)

    @app.put("/api/clone/drafts/{draft_id}/clips/{name}/text")
    def draft_clip_text(draft_id: str, name: str, text: str = Body(..., embed=True)) -> dict:
        return _call(clone.set_clip_text, draft_id, name, text)

    @app.post("/api/clone/drafts/{draft_id}/preview")
    def draft_preview(draft_id: str, body: PreviewIn = PreviewIn()) -> FileResponse:
        path = _call(clone.preview, draft_id, body.text, body.language, body.engine)
        return FileResponse(path, media_type="audio/wav", headers={"Cache-Control": "no-store"})

    @app.post("/api/clone/drafts/{draft_id}/save")
    def draft_save(draft_id: str, body: SaveIn) -> dict:
        v = _call(clone.save, draft_id, body.name, body.language, body.description, body.tags,
                  body.consent, body.engine)
        return _public(v)

    @app.get("/api/clone/drafts/{draft_id}/clips/{name}")
    def draft_clip(draft_id: str, name: str) -> FileResponse:
        return FileResponse(_call(clone.clip_path, draft_id, name), media_type="audio/wav")

    # ---- Voice blending (XTTS latents)
    @app.get("/api/blend/sources")
    def blend_sources() -> list[dict]:
        return blend.sources()

    @app.post("/api/blend/preview")
    def blend_preview(body: BlendIn) -> Response:
        data = _call(blend.preview, body.a, body.b, body.ratio, body.text, body.language)
        return Response(data, media_type="audio/wav", headers={"Cache-Control": "no-store"})

    @app.post("/api/blend")
    def blend_save(body: BlendIn) -> dict:
        return _public(_call(blend.save, body.a, body.b, body.ratio, body.name, body.language,
                             body.description, body.tags))

    # ---- Voice Library
    @app.get("/api/library")
    def library_list(q: str = "", language: str = "", accent: str = "", gender: str = "", age: str = "",
                     style: str = "", engine: str = "", license: str = "", commercial: bool | None = None) -> list[dict]:
        """Library voices matching every given filter. `added` = a copy is already in My Voices."""
        mine = {v.get("library_id") for v in voices.all_voices()}
        return [_library_card(v, mine) for v in library.search(q, language, accent, gender, age, style, engine,
                                                                license, commercial)]

    @app.get("/api/library/{voice_id}/preview")
    def library_preview(voice_id: str) -> FileResponse:
        p = library.preview_path(_call(library.get, voice_id))
        if not p:
            raise HTTPException(404, f"Library voice '{voice_id}' has no preview")
        return FileResponse(p, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})

    @app.post("/api/library/{voice_id}/add")
    def library_add(voice_id: str) -> dict:
        return _public(_call(library.add_to_my_voices, voice_id))

    # ---- My Voices
    @app.get("/api/my-voices")
    def my_voices() -> list[dict]:
        default = voices.default_id()
        return [_my_card(v, default) for v in voices.all_voices()]

    @app.patch("/api/my-voices/{voice_id}")
    def my_voice_edit(voice_id: str, body: dict = Body(...)) -> dict:
        return _my_card(_call(voices.edit, voice_id, **body), voices.default_id())

    @app.delete("/api/my-voices/{voice_id}")
    def my_voice_delete(voice_id: str) -> dict:
        was_default = voices.default_id() == voice_id
        _call(voices.delete, voice_id)
        if was_default:
            voices.set_default(None)
        return {"deleted": voice_id}

    @app.post("/api/my-voices/{voice_id}/duplicate")
    def my_voice_duplicate(voice_id: str, body: dict = Body(default={})) -> dict:
        return _my_card(_call(voices.duplicate, voice_id, (body or {}).get("name")), voices.default_id())

    def _dict_list() -> dict:
        d = dictionary.load()
        out = {lang: [{"word": w, "spoken": d[lang][w]} for w in sorted(d[lang], key=str.lower)] for lang in d}
        return {**out, "count": sum(len(v) for v in d.values())}

    @app.get("/api/dictionary")
    def dictionary_list() -> dict:
        """Pronunciation dictionary: `{es: [{word, spoken}], en: [...], count}`, A–Z. Applied before speech."""
        return _dict_list()

    @app.put("/api/dictionary")
    def dictionary_put(body: dict = Body(...)) -> dict:
        """Add or change a word: `{language: es|en, word, spoken, old_word?}` (`old_word`: the word was renamed).
        Words match without case: "whatsapp" replaces "WhatsApp"."""
        get = lambda k: body.get(k) if isinstance(body.get(k), str) else ""
        _call(dictionary.set_entry, get("language"), get("word"), get("spoken"), get("old_word") or None)
        return _dict_list()

    @app.delete("/api/dictionary")
    def dictionary_delete(language: str, word: str) -> dict:
        _call(dictionary.delete_entry, language, word)
        return _dict_list()

    @app.post("/api/dictionary/listen")
    def dictionary_listen(body: dict = Body(...)) -> Response:
        """Hear a word: `{language: es|en, text, voice?}` → WAV of `text` spoken with the dictionary applied (not
        saved to History). Voice: `voice`, else the default voice, else a small Kokoro voice for that language."""
        lang, text = body.get("language"), body.get("text")
        if lang not in dictionary.LANGS:
            raise HTTPException(400, "Language must be es or en")
        if not isinstance(text, str) or not text.strip() or len(text) > dictionary.MAX_SPOKEN:
            raise HTTPException(400, f"Text must have 1 to {dictionary.MAX_SPOKEN} characters")
        voice = body.get("voice") if isinstance(body.get("voice"), str) and body.get("voice") else None
        if voice:
            v = _call(voices.find, voice)
        else:                                       # the default voice if it speaks this language, else a small one
            v = voices.find(voices.default_id()) if voices.default_id() else None
            if not v or v.get("language") != lang:
                v = voices.find(dictionary.LISTEN_VOICE[lang])
        a = _call(tts.speak, text, v, lang)
        return Response(audio.wav_bytes(a), media_type="audio/wav", headers={"Cache-Control": "no-store"})

    @app.get("/api/dictionary/export")
    def dictionary_export() -> Response:
        """CSV `language,word,spoken` (UTF-8 with BOM, so Excel shows accents)."""
        return Response("\ufeff" + dictionary.export_csv(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="voicer-dictionary.csv"'})

    @app.post("/api/dictionary/import")
    def dictionary_import(file: UploadFile = File(...), replace: bool = Form(False)) -> dict:
        """CSV `language,word,spoken` (header optional; `,` `;` or tab; UTF-8 or Windows-1252). `replace=true`
        empties the dictionary first. A bad row → 400 naming the row, nothing changes."""
        raw = file.file.read(1_000_001)
        if len(raw) > 1_000_000:
            raise HTTPException(400, "The file is too big (max 1 MB).")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")      # CSV saved by Excel on Windows
        n = _call(dictionary.import_csv, text, replace, allow_empty=False)
        return {"imported": n, **_dict_list()}

    @app.get("/api/export")
    def export_backup(voice: list[str] | None = Query(default=None), dictionary: bool = True) -> FileResponse:
        """Backup zip of My Voices (samples, model caches, settings, preview) + the pronunciation dictionary.
        `voice` (repeatable): only these voice IDs; none = all voices. `dictionary=false` leaves it out.
        Import it on another PC or VPS. The API key is never in it."""
        from starlette.background import BackgroundTask

        path = _call(backup.export, voice, dictionary)
        try:
            name = _call(backup.file_name, voice)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return FileResponse(path, media_type="application/zip", filename=name,
                            background=BackgroundTask(path.unlink, missing_ok=True))

    @app.post("/api/import")
    def import_backup(file: UploadFile = File(...)) -> dict:
        """Import a backup zip from /api/export. Adds voices (never overwrites; an ID already here → new ID,
        "<name> (imported)") and dictionary words (your words win). A bad zip changes nothing → 400."""
        return _call(backup.import_zip, file.file)

    def _this_pc(request: Request) -> None:
        if not apikey.is_local(request.client.host if request.client else None, request.headers):
            raise HTTPException(403, "Only on the PC that runs Voice Studio")

    @app.get("/api/auto-backup")
    def auto_backup_get(request: Request) -> dict:
        """Daily auto-backup settings and state (this PC only: it shows folder paths)."""
        _this_pc(request)
        return autobackup.status()

    @app.put("/api/auto-backup")
    def auto_backup_put(request: Request, body: dict = Body(...)) -> dict:
        """`{enabled, folder, keep}`. Folder empty = data/backups; `C:\\…` works under WSL. This PC only."""
        _this_pc(request)
        return _call(autobackup.configure, body.get("enabled"), body.get("folder") or "", body.get("keep", 7))

    @app.post("/api/auto-backup/run")
    def auto_backup_run(request: Request) -> dict:
        """Make one auto-backup now. This PC only."""
        _this_pc(request)
        return _call(autobackup.run_now)

    @app.get("/api/my-voices/{voice_id}/preview")
    def my_voice_preview(voice_id: str) -> FileResponse:
        p = _call(voices.preview_file, voice_id)
        return FileResponse(p, media_type="audio/mpeg" if p.suffix == ".mp3" else "audio/wav",
                            headers={"Cache-Control": "no-cache"})

    @app.get("/api/default-voice")
    def default_voice_get() -> dict:
        return {"voice": voices.default_id()}

    @app.put("/api/default-voice")
    def default_voice_set(body: dict = Body(...)) -> dict:
        return {"voice": _call(voices.set_default, body.get("voice"))}

    @app.get("/api/mcp-config")
    def mcp_config(request: Request) -> dict:
        """What the MCP config snippets need. `stdio` (paths on this PC) only for requests from this PC."""
        import os
        import sys

        local = apikey.is_local(request.client.host if request.client else None, request.headers)
        python = Path(sys.executable)
        rel = python.relative_to(config.ROOT) if python.is_relative_to(config.ROOT) else python   # .venv/bin/python
        stdio = {"python": str(python), "venv_python": rel.as_posix(), "root": str(config.ROOT), "module": "voicer.mcp_server",
                 "wsl_distro": os.environ.get("WSL_DISTRO_NAME") or None} if local else None
        return {"http_path": "/mcp", "tools": ["list_voices", "search_voices", "speak"], "stdio": stdio}

    @app.get("/api/remote-access")
    def remote_access(request: Request) -> dict:
        """Tailscale remote access status (this PC only): `{installed, where, running, dns_name, ips, serving,
        funnel, url, api_key_on, port, warnings}`."""
        if not apikey.is_local(request.client.host if request.client else None, request.headers):
            raise HTTPException(403, "Shown only on the PC that runs Voice Studio")
        return remote.status()

    # ---- API key (optional; see apikey.py)
    @app.get("/api/api-key")
    def api_key_status() -> dict:
        return apikey.status()

    @app.post("/api/api-key")
    def api_key_create() -> dict:
        """New key (replaces the old one). The key is in this response only."""
        return {"key": apikey.create(), **apikey.status()}

    @app.delete("/api/api-key")
    def api_key_disable() -> dict:
        apikey.disable()
        return apikey.status()

    # ---- Text to Speech + history
    def voice_list(language: str = "", gender: str = "", tags: str = "") -> list[dict]:
        """All voices for pickers: My Voices first, then the library. Optional filters: `language` (en, es),
        `gender` (female, male), `tags` (comma-separated; a voice must have all of them)."""
        default = voices.default_id()
        want = {t.strip().lower() for t in tags.split(",") if t.strip()}
        out = [_card(v, "mine") for v in voices.all_voices()] + [_card(v, "library") for v in library.catalog()]
        out = [c for c in out if (not language or c.get("language") == language.lower())
               and (not gender or c.get("gender") == gender.lower())
               and want <= {t.lower() for t in c.get("tags", [])}]
        for c in out:
            c["default"] = c["id"] == default
        return out

    app.get("/api/voices")(voice_list)
    app.get("/voices", include_in_schema=False)(voice_list)    # short alias (features.md)

    @app.post("/api/tts")
    def tts_generate(body: TtsIn) -> dict:
        return _call(tts.generate, body.text, body.voice, body.language, body.speed, body.engine,
                     body.stability, body.expressiveness)

    def _audio_reply(entry: dict, fmt: str, stream: bool, download: bool) -> Response:
        """A History entry's audio as the response body, with `X-Voicer-Id` / `X-Voicer-Seconds` headers."""
        spec = formats.FORMATS[fmt]
        path = _call(formats.encode, history.audio_path(entry["id"]), fmt)
        headers = {"X-Voicer-Id": entry["id"], "X-Voicer-Seconds": str(entry["seconds"])}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="voicer-{entry["id"]}.{spec["ext"]}"'
        if stream:
            return StreamingResponse(openai_api.chunks(path), media_type=spec["mime"], headers=headers)
        return FileResponse(path, media_type=spec["mime"], headers=headers)

    def speak(body: SpeakIn) -> Response:
        """Text → audio bytes in one call (saved to History). `format` mp3 (default), wav, ogg_opus, flac, aac,
        pcm; `stream=true` sends each sentence as soon as it is spoken (live, chunked; no `X-Voicer-Seconds`, adds
        `X-Voicer-Sample-Rate`). Headers: `X-Voicer-Id` (History ID), `X-Voicer-Seconds`."""
        _call(formats.check, body.format)
        if body.stream:
            return live_reply(body.text, body.voice, body.language, body.speed, body.engine, body.format, body.download)
        entry = _call(tts.generate, body.text, body.voice, body.language, body.speed, body.engine)
        return _audio_reply(entry, body.format, body.stream, body.download)

    def dialogue_speak(body: DialogueIn) -> Response:
        """Multi-speaker dialogue → one audio file (saved to History). `script`: lines `Name: text`;
        `voices`: `{"Name": voice ID or name}`. Same `format` / `stream` / `download` and headers as /api/speak."""
        _call(formats.check, body.format)
        entry = _call(dialogue.generate, body.script, body.voices, body.language, body.speed, body.gap)
        return _audio_reply(entry, body.format, body.stream, body.download)

    async def voice_change(file: UploadFile = File(...), voice: str = Form(...), language: str = Form("auto"),
                           format: str = Form("mp3"), stream: bool = Form(False), download: bool = Form(False)) -> Response:
        """Voice changer (speech-to-speech): upload a recording (any common audio/video file, 0.5 s–5 min) →
        the same words, timing and emotion in `voice`. Saved to History with subtitles from the recording.
        Multipart form; same `format` / `stream` / `download` and headers as /api/speak."""
        import tempfile

        from starlette.concurrency import run_in_threadpool

        _call(formats.check, format)
        data = await file.read(clone.MAX_FILE_BYTES + 1)
        if not data:
            raise HTTPException(400, "Empty file")
        if len(data) > clone.MAX_FILE_BYTES:
            raise HTTPException(400, f"File too large (max {clone.MAX_FILE_BYTES // 2**20} MB)")
        with tempfile.TemporaryDirectory(dir=config.CACHE_DIR) as tmp:
            src = Path(tmp) / "source"
            src.write_bytes(data)
            entry = await run_in_threadpool(_call, voice_changer.convert, src, voice, language, file.filename or "")
        return _audio_reply(entry, format, stream, download)

    @app.post("/api/subtitles")
    async def subtitles_from_audio(file: UploadFile = File(...), language: str = Form("auto"),
                                   format: str = Form("srt")) -> Response:
        """Subtitles for your own recording: upload audio or video (0.5 s–10 min) → SRT or VTT file timed from a
        Whisper transcript (`language` auto/en/es). Nothing is saved."""
        import re
        import tempfile

        from starlette.concurrency import run_in_threadpool

        media = _call(subtitles.check, format)
        data = await file.read(clone.MAX_FILE_BYTES + 1)
        if not data:
            raise HTTPException(400, "Empty file")
        if len(data) > clone.MAX_FILE_BYTES:
            raise HTTPException(400, f"File too large (max {clone.MAX_FILE_BYTES // 2**20} MB)")
        with tempfile.TemporaryDirectory(dir=config.CACHE_DIR) as tmp:
            src = Path(tmp) / "source"
            src.write_bytes(data)
            timings = await run_in_threadpool(_call, subtitles.from_audio, src, language)
        stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(file.filename or "").stem).strip("._")[:80] or "subtitles"
        return Response(subtitles.render(timings, format), media_type=f"{media}; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{stem}.{format}"'})

    app.post("/api/voice-changer", response_model=None)(voice_change)
    app.post("/voice-changer", response_model=None, include_in_schema=False)(voice_change)    # short alias (features.md)

    app.post("/api/dialogue", response_model=None)(dialogue_speak)
    app.post("/dialogue", response_model=None, include_in_schema=False)(dialogue_speak)    # short alias (features.md)

    app.post("/api/speak", response_model=None)(speak)
    app.post("/speak", response_model=None, include_in_schema=False)(speak)    # short alias (features.md)

    async def ws_one(ws: WebSocket, body: WsSpeakIn) -> None:
        """One WebSocket speech request: start message, audio frames, done (or an error message)."""
        from starlette.concurrency import run_in_threadpool

        try:
            info, it = await run_in_threadpool(_call, open_stream, body.text, body.voice, body.language,
                                               body.speed, body.engine, body.format)
        except HTTPException as e:
            await ws.send_json({"type": "error", "status": e.status_code, "detail": e.detail})
            return
        await ws.send_json({"type": "start", **info})
        try:
            while (b := await run_in_threadpool(next, it, None)) is not None:
                await ws.send_bytes(b)
        except BaseException:
            await run_in_threadpool(it.close)       # client left: stop speaking, save nothing
            raise
        try:
            seconds = history.get(info["id"])["seconds"]
        except KeyError:                            # the engine failed part way
            await ws.send_json({"type": "error", "status": 500, "detail": "Speech stopped early"})
            return
        await ws.send_json({"type": "done", "id": info["id"], "seconds": seconds,
                            "url": f"/api/history/{info['id']}/audio"})

    async def ws_speak(ws: WebSocket) -> None:
        """Live speech over a WebSocket. Send JSON `{text, voice, language?, speed?, engine?, format?}` (format
        default `pcm` = 16-bit 24 kHz mono); get `{"type":"start", id, format, mime, sample_rate}`, then binary
        audio frames (one per sentence), then `{"type":"done", id, seconds, url}`. Errors: `{"type":"error",
        status, detail}`; the socket stays open for the next request. API key: header or `?api_key=`."""
        from pydantic import ValidationError

        key = apikey.from_headers(ws.headers) or ws.query_params.get("api_key")
        host = ws.client.host if ws.client else None
        if not _mcp_origin_ok(ws) or not (apikey.allowed(host, ws.headers) or apikey.valid(key)):
            await ws.close(code=1008)                       # policy violation: other site, or no / wrong key
            return
        await ws.accept()
        usage.set_caller("websocket", usage.agent_from(ws.headers), usage.key_label(host, ws.headers, key))
        try:
            while True:
                try:
                    body = WsSpeakIn.model_validate(await ws.receive_json())
                except ValidationError as e:
                    await ws.send_json({"type": "error", "status": 422, "detail": "; ".join(
                        f"{'.'.join(map(str, x['loc'])) or 'body'}: {x['msg']}" for x in e.errors())})
                    continue
                except (ValueError, KeyError):              # not JSON, or a binary frame
                    await ws.send_json({"type": "error", "status": 400, "detail": "Send one JSON object per request"})
                    continue
                try:
                    await jobs.enter()                      # one speech job at a time, like the HTTP routes
                except jobs.Busy as e:
                    await ws.send_json({"type": "error", "status": 503, "detail": str(e), "retry_after": e.retry_after})
                    continue
                try:
                    await ws_one(ws, body)
                finally:
                    jobs.leave()
        except WebSocketDisconnect:
            pass

    app.websocket("/api/ws/speak")(ws_speak)
    app.websocket("/ws/speak")(ws_speak)                     # short alias, like /speak

    def batch_speak(body: BatchIn, request: Request) -> Response:
        """Many texts in one call (max 100), each saved to History. Items without `voice` use the batch
        `voice`, else the default voice. Returns `{format, count, ok, failed, items}` (each item `status` ok with
        `id`, `url`, … or error with `error`); `zip=true` → a ZIP of the audio files + manifest.json."""
        base = remote.public_base(request)
        items = [i.model_dump() for i in body.items]
        manifest = _call(batch.run, items, body.voice, body.language, body.format, base)
        if not body.zip:
            return JSONResponse(manifest)
        if not manifest["ok"]:
            raise HTTPException(400, f"No item was spoken: {manifest['items'][0]['error']}")
        return Response(batch.zip_bytes(manifest), media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="voicer-batch.zip"'})

    app.post("/api/batch", response_model=None)(batch_speak)
    app.post("/batch", response_model=None, include_in_schema=False)(batch_speak)    # short alias (features.md)

    @app.post("/api/batch/parse")
    async def batch_parse(file: UploadFile = File(...)) -> dict:
        """Read a .txt (one clip per line), .docx (one clip per paragraph) or .csv (header row: `text`, optional
        `voice`, `language`, `filename`) file → `{count, items: [{text, voice?, language?, name?}]}` (max 100).
        Nothing is spoken; send the items to /api/batch."""
        data = await file.read(batch.MAX_UPLOAD_BYTES + 1)
        if not data:
            raise HTTPException(400, "Empty file")
        items = _call(batch.parse, file.filename or "", data)
        return {"count": len(items), "items": items}

    @app.post("/api/batch/zip", response_model=None)
    def batch_zip(body: BatchZipIn, request: Request) -> Response:
        """ZIP of clips already in History (the Batch page makes them one by one to show progress):
        `{format?=mp3, items: [{id, name?} | {error, name?}]}` → `voicer-batch.zip` (same layout as /api/batch
        `zip=true`). 404 unknown ID, 400 if no item has an ID."""
        base = remote.public_base(request)
        manifest = _call(batch.manifest_from_history, [r.model_dump() for r in body.items], body.format, base)
        if not manifest["ok"]:
            raise HTTPException(400, "No clip to put in the ZIP")
        return Response(batch.zip_bytes(manifest), media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="voicer-batch.zip"'})

    @app.get("/api/history")
    def history_list(q: str = "", limit: int = 50, offset: int = 0) -> dict:
        """Generated clips, newest first: `{total, items}`. `q` searches text, voice, language, engine."""
        return _call(history.search, q, limit, offset)

    @app.delete("/api/history/{entry_id}")
    def history_delete(entry_id: str) -> dict:
        """Delete a clip with its encoded copies and subtitles."""
        _call(history.delete, entry_id)
        return {"deleted": entry_id}

    @app.get("/api/history/{entry_id}")
    def history_get(entry_id: str) -> dict:
        return _call(history.get, entry_id)

    @app.get("/api/history/{entry_id}/audio")
    def history_audio(entry_id: str, format: str = "wav", download: bool = False) -> FileResponse:
        """The clip as WAV, MP3 or OGG/Opus (WhatsApp voice note). `download=true` saves it as a file."""
        spec = _call(formats.check, format)
        path = _call(formats.encode, _call(history.audio_path, entry_id), format)
        name = f"voicer-{entry_id}.{spec['ext']}" if download else None
        return FileResponse(path, media_type=spec["mime"], filename=name)   # filename → attachment

    @app.get("/api/history/{entry_id}/subtitles")
    def history_subtitles(entry_id: str, format: str = "srt", download: bool = False) -> Response:
        """Timed subtitles (one cue per sentence) as SRT or WebVTT."""
        mime = _call(subtitles.check, format)
        text = _call(history.subtitles, entry_id, format)
        headers = {"Content-Disposition": f'attachment; filename="voicer-{entry_id}.{format}"'} if download else {}
        return Response(text, media_type=f"{mime}; charset=utf-8", headers=headers)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})

    # ---- OpenAI-compatible API (/v1/audio/speech). Its request errors use the OpenAI error shape.
    app.include_router(openai_api.router)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/v1/"):
            e = exc.errors()[0] if exc.errors() else {}
            loc = [str(x) for x in e.get("loc", ()) if x != "body"]
            return openai_api.error(400, f"{'.'.join(loc) or 'body'}: {e.get('msg', 'invalid request')}",
                                    loc[0] if loc else None)
        return await request_validation_exception_handler(request, exc)

    # ---- MCP for agents (streamable HTTP). Tools live in mcp_server.py; stdio: python -m voicer.mcp_server
    app.router.routes.append(Route("/mcp", endpoint=_McpEndpoint(app), include_in_schema=False))

    app.mount("/static", StaticFiles(directory=WEB), name="static")
    return app


app = create_app()
