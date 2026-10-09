"""Phase 9: Batch files — .txt / .docx / .csv → items (`/api/batch/parse`), and a ZIP of clips made one by one
(`/api/batch/zip`) for the Batch page progress bar."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from voicer import batch

EN = "piper-en-us-lessac-medium"


@pytest.fixture(scope="module")
def client():
    from voicer.server import app

    return TestClient(app)


def _docx(paragraphs: list[str]) -> bytes:
    """A minimal valid .docx (what Word or LibreOffice saves, reduced to the text part)."""
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f'<w:p><w:r><w:t xml:space="preserve">{p.split("|")[0]}</w:t></w:r>'
                   + (f'<w:r><w:tab/><w:t>{p.split("|")[1]}</w:t></w:r>' if "|" in p else "") + "</w:p>"
                   for p in paragraphs)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>')
    return buf.getvalue()


def test_parse_txt_lines():
    data = "﻿First line.\r\n\r\n  Segunda línea.  \nThird.\n".encode()
    assert batch.parse("notes.TXT", data) == [{"text": "First line."}, {"text": "Segunda línea."}, {"text": "Third."}]
    assert batch.parse("old.txt", "Canción vieja.".encode("cp1252")) == [{"text": "Canción vieja."}]


def test_parse_docx_paragraphs():
    items = batch.parse("script.docx", _docx(["Hello there.", "", "Tab|after", "Último párrafo."]))
    assert items == [{"text": "Hello there."}, {"text": "Tab after"}, {"text": "Último párrafo."}]
    with pytest.raises(ValueError, match="not a valid .docx"):
        batch.parse("fake.docx", b"plain text")


def test_parse_csv_columns_any_order_and_semicolons():
    data = "Filename,TEXT,voice,language,notes\nintro,Welcome to the show.,Lessac (Piper),en,x\n,\"Hola, amigos.\",,es,\n,,,,\n"
    assert batch.parse("a.csv", data.encode()) == [
        {"name": "intro", "text": "Welcome to the show.", "voice": "Lessac (Piper)", "language": "en"},
        {"text": "Hola, amigos.", "language": "es"}]
    assert batch.parse("b.csv", "text;filename\nUno, dos.;uno\n".encode()) == [{"text": "Uno, dos.", "name": "uno"}]
    with pytest.raises(ValueError, match="'text' column"):
        batch.parse("c.csv", b"words,who\nhi,me\n")


def test_parse_limits():
    with pytest.raises(ValueError, match="Upload a .txt, .docx or .csv"):
        batch.parse("a.pdf", b"x")
    with pytest.raises(ValueError, match="No text found"):
        batch.parse("a.txt", b"\n \n")
    with pytest.raises(ValueError, match=r"Too many clips \(101, max 100\)"):
        batch.parse("a.txt", "\n".join(f"Line {i}." for i in range(101)).encode())


def test_parse_endpoint(client):
    r = client.post("/api/batch/parse", files={"file": ("s.docx", _docx(["One.", "Two."]))})
    assert r.status_code == 200 and r.json() == {"count": 2, "items": [{"text": "One."}, {"text": "Two."}]}
    r = client.post("/api/batch/parse", files={"file": ("s.exe", b"MZ")})
    assert r.status_code == 400 and "Upload a .txt" in r.json()["detail"]
    assert client.post("/api/batch/parse", files={"file": ("e.txt", b"")}).status_code == 400


def test_zip_of_history_clips(client):
    ok = client.post("/api/batch", json={"voice": EN, "items": [{"text": "Clip one."}, {"text": "Clip two."}]}).json()
    ids = [i["id"] for i in ok["items"]]
    rows = [{"id": ids[0], "name": "first"}, {"error": "Voice 'nobody' not found", "name": "bad"}, {"id": ids[1]}]
    r = client.post("/api/batch/zip", json={"format": "wav", "items": rows})
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert sorted(z.namelist()) == ["001-first.wav", "003.wav", "manifest.json"]
    assert z.read("001-first.wav")[:4] == b"RIFF"
    m = json.loads(z.read("manifest.json"))
    assert (m["count"], m["ok"], m["failed"]) == (3, 2, 1) and m["items"][1]["error"] == "Voice 'nobody' not found"
    assert client.post("/api/batch/zip", json={"items": [{"id": "nope"}]}).status_code == 404
    assert client.post("/api/batch/zip", json={"items": [{"error": "x"}]}).status_code == 400
    assert client.post("/api/batch/zip", json={"items": []}).status_code == 400
