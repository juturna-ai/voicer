"""Batch Text to Speech: many texts in one request. Each item is saved to History like a normal generation.
One bad item does not stop the others; its error is reported in its place."""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from xml.etree import ElementTree

from . import formats, history, tts, voices

MAX_ITEMS = 100
MAX_UPLOAD_BYTES = 5 * 2**20                      # a script file, not audio: 5 MB is plenty
CSV_COLUMNS = {"text": "text", "voice": "voice", "language": "language", "filename": "name", "name": "name"}
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def run(items: list[dict], voice: str | None, language: str, fmt: str, base: str) -> dict:
    """Speak each item (`text`, optional `voice`, `language`, `speed`, `engine`, `name`) in order.
    Items without a voice use `voice`, else the default voice. Returns the manifest."""
    formats.check(fmt)
    if not 1 <= len(items) <= MAX_ITEMS:
        raise ValueError(f"Send 1 to {MAX_ITEMS} items (got {len(items)})")
    out = []
    for i, it in enumerate(items):
        row = {"index": i, "name": it.get("name") or None}
        try:
            v = it.get("voice") or voice or voices.default_id()
            if not v:
                raise ValueError("No voice: set 'voice' on the item or the batch, or choose a default voice")
            e = tts.generate(it.get("text", ""), v, it.get("language") or language, it.get("speed", 1.0), it.get("engine"))
            formats.encode(history.audio_path(e["id"]), fmt)
            row.update(status="ok", id=e["id"], voice_id=e["voice_id"], voice=e["voice_name"], seconds=e["seconds"],
                       url=f"{base}/api/history/{e['id']}/audio?format={fmt}",
                       subtitles_url=f"{base}/api/history/{e['id']}/subtitles?format=srt")
        except KeyError as err:
            row.update(status="error", error=str(err.args[0]) if err.args else "Not found")
        except ValueError as err:
            row.update(status="error", error=str(err))
        out.append(row)
    ok = sum(r["status"] == "ok" for r in out)
    return {"format": fmt, "count": len(out), "ok": ok, "failed": len(out) - ok, "items": out}


def _file_name(row: dict, ext: str) -> str:
    """`001.mp3`, or `001-<name>.mp3` with the name made safe for a file name. The number keeps names unique."""
    stem = f"{row['index'] + 1:03d}"
    safe = re.sub(r"[^\w.-]+", "_", str(row.get("name") or "")).strip("._")[:60]
    return f"{stem}-{safe}.{ext}" if safe else f"{stem}.{ext}"


def zip_bytes(manifest: dict) -> bytes:
    """ZIP with one audio file per successful item (`001-name.mp3`, …) and `manifest.json`."""
    ext = formats.FORMATS[manifest["format"]]["ext"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:     # audio is already compressed
        for row in manifest["items"]:
            if row["status"] == "ok":
                row["file"] = _file_name(row, ext)
                z.write(formats.encode(history.audio_path(row["id"]), manifest["format"]), row["file"])
        z.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    return buf.getvalue()


def _lines(text: str) -> list[dict]:
    """One clip per non-empty line."""
    return [{"text": line.strip()} for line in text.splitlines() if line.strip()]


def _docx_text(data: bytes) -> str:
    """Paragraph text of a .docx (one line per paragraph), read with the standard library only."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > 20 * 2**20:                 # a packed "zip bomb" must not fill memory
                raise ValueError("This .docx is too large")
            root = ElementTree.fromstring(z.read(info))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        raise ValueError("This is not a valid .docx file") from None
    paras = []
    for p in root.iter(f"{_W}p"):
        parts = []
        for el in p.iter():
            if el.tag == f"{_W}t":
                parts.append(el.text or "")
            elif el.tag in (f"{_W}tab", f"{_W}br", f"{_W}cr"):
                parts.append(" ")
        paras.append("".join(parts))
    return "\n".join(paras)


def _csv_items(text: str) -> list[dict]:
    """CSV with a header row: `text` (required), `voice`, `language`, `filename` (any order, any case).
    Comma, semicolon or tab separated (Excel in Spanish saves with `;`)."""
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    if not rows:
        return []
    head = [CSV_COLUMNS.get(h.strip().lower()) for h in rows[0]]
    if "text" not in head:
        raise ValueError("The CSV needs a header row with a 'text' column (optional: voice, language, filename)")
    items = []
    for row in rows[1:]:
        it = {k: v.strip() for k, v in zip(head, row) if k and v.strip()}
        if it.get("text"):
            items.append(it)
    return items


def parse(filename: str, data: bytes) -> list[dict]:
    """Batch items from an uploaded .txt (one clip per line), .docx (one clip per paragraph) or .csv file."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("txt", "docx", "csv"):
        raise ValueError("Upload a .txt, .docx or .csv file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"File too large (max {MAX_UPLOAD_BYTES // 2**20} MB)")
    if ext == "docx":
        items = _lines(_docx_text(data))
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252", errors="replace")   # older Windows editors
        items = _csv_items(text) if ext == "csv" else _lines(text)
    if not items:
        raise ValueError("No text found in the file")
    if len(items) > MAX_ITEMS:
        raise ValueError(f"Too many clips ({len(items)}, max {MAX_ITEMS}). Split the file.")
    return items


def manifest_from_history(rows: list[dict], fmt: str, base: str) -> dict:
    """Manifest for clips made one by one (the Batch page): each row is `{id, name}` for a clip in History,
    or `{error, name}` for one that failed. Raises KeyError for an unknown ID."""
    formats.check(fmt)
    if not 1 <= len(rows) <= MAX_ITEMS:
        raise ValueError(f"Send 1 to {MAX_ITEMS} items (got {len(rows)})")
    out = []
    for i, r in enumerate(rows):
        row = {"index": i, "name": r.get("name") or None}
        if r.get("id"):
            e = history.get(r["id"])
            row.update(status="ok", id=e["id"], voice_id=e["voice_id"], voice=e["voice_name"], seconds=e["seconds"],
                       url=f"{base}/api/history/{e['id']}/audio?format={fmt}",
                       subtitles_url=f"{base}/api/history/{e['id']}/subtitles?format=srt")
        else:
            row.update(status="error", error=str(r.get("error") or "Not generated"))
        out.append(row)
    ok = sum(r["status"] == "ok" for r in out)
    return {"format": fmt, "count": len(out), "ok": ok, "failed": len(out) - ok, "items": out}
