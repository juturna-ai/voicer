"""Final test, dictionary: the pronunciation dictionary API (list, add/change, delete, CSV import/export)."""
import httpx
import pytest

from voicer import dictionary


@pytest.fixture(autouse=True)
def clean():
    dictionary.import_csv("", replace=True)
    yield
    dictionary.import_csv("", replace=True)


def _csv(url, data: bytes, replace=False):
    return httpx.post(f"{url}/api/dictionary/import", files={"file": ("d.csv", data, "text/csv")},
                      data={"replace": str(replace).lower()})


def test_add_change_rename_delete(live_server):
    url = f"{live_server}/api/dictionary"
    assert httpx.get(url).json() == {"es": [], "en": [], "count": 0}
    r = httpx.put(url, json={"language": "es", "word": "WhatsApp", "spoken": "guatsap"})
    assert r.status_code == 200 and r.json()["es"] == [{"word": "WhatsApp", "spoken": "guatsap"}]
    httpx.put(url, json={"language": "es", "word": "fami", "spoken": "Fah-mee"})
    httpx.put(url, json={"language": "en", "word": "SQL", "spoken": "sequel"})
    r = httpx.put(url, json={"language": "es", "word": "whatsapp", "spoken": "uatsap"})     # same word, any case
    assert r.json()["es"] == [{"word": "fami", "spoken": "Fah-mee"}, {"word": "whatsapp", "spoken": "uatsap"}]
    assert r.json()["count"] == 3
    r = httpx.put(url, json={"language": "es", "word": "Fami", "spoken": "Fami", "old_word": "fami"})  # case fix only
    assert {"word": "Fami", "spoken": "Fami"} in r.json()["es"] and len(r.json()["es"]) == 2
    r = httpx.put(url, json={"language": "es", "word": "Famy", "spoken": "Fah-mee", "old_word": "Fami"})  # rename
    assert [e["word"] for e in r.json()["es"]] == ["Famy", "whatsapp"]
    assert dictionary.apply("Hola Famy por WhatsApp", "es") == "Hola Fah-mee por uatsap"
    r = httpx.delete(url, params={"language": "es", "word": "WHATSAPP"})
    assert r.status_code == 404                                                          # delete needs the exact word
    r = httpx.delete(url, params={"language": "es", "word": "whatsapp"})
    assert r.status_code == 200 and [e["word"] for e in r.json()["es"]] == ["Famy"]


@pytest.mark.parametrize("body, status, detail", [
    ({"language": "fr", "word": "a", "spoken": "b"}, 400, "Language must be es or en"),
    ({"language": "es", "word": " ", "spoken": "b"}, 400, "must not be empty"),
    ({"language": "es", "word": "a", "spoken": ""}, 400, "must not be empty"),
    ({"language": "es", "word": "a" * 101, "spoken": "b"}, 400, "up to 100 characters"),
    ({"language": "es", "word": "a", "spoken": "b" * 301}, 400, "up to 300"),
    ({"language": "es", "word": "a", "spoken": "b", "old_word": "nope"}, 404, "not in es dictionary"),
    ({"language": "es", "word": 5, "spoken": "b"}, 400, "must not be empty"),
])
def test_bad_input(live_server, body, status, detail):
    r = httpx.put(f"{live_server}/api/dictionary", json=body)
    assert r.status_code == status and detail in r.json()["detail"], r.text
    assert httpx.get(f"{live_server}/api/dictionary").json()["count"] == 0


def test_csv_export_import(live_server):
    url = f"{live_server}/api/dictionary"
    httpx.put(url, json={"language": "es", "word": "Ñandú", "spoken": "ñan-du"})
    r = httpx.get(f"{url}/export")
    assert r.headers["content-type"].startswith("text/csv") and "voicer-dictionary.csv" in r.headers["content-disposition"]
    assert r.content.startswith(b"\xef\xbb\xbf") and "es,Ñandú,ñan-du" in r.text            # BOM: Excel shows the accent
    exported = r.content

    dictionary.import_csv("", replace=True)
    r = _csv(live_server, exported)
    assert r.status_code == 200 and r.json()["imported"] == 1 and r.json()["es"][0]["word"] == "Ñandú"

    excel = "language;word;spoken\r\nes;Señal;se-ñal\r\nEN;Voicer;voy-ser\r\n".encode("cp1252")   # Spanish Excel
    r = _csv(live_server, excel)
    assert r.status_code == 200 and r.json()["imported"] == 2 and r.json()["count"] == 3
    assert {"word": "Señal", "spoken": "se-ñal"} in r.json()["es"] and r.json()["en"][0]["word"] == "Voicer"

    r = _csv(live_server, b"es,Nuevo,nuevo\n", replace=True)
    assert r.json()["count"] == 1 and r.json()["es"][0]["word"] == "Nuevo"


@pytest.mark.parametrize("data, detail", [
    (b"es,ok,ok\nfr,bad,row\n", "Row 2: Language must be es or en"),
    (b"es,only-two\n", "Row 1: needs 3 columns"),
    (b"language,word,spoken\n", "No words found"),
    (b"", "No words found"),
    (b"es,a,b\n" * 200_000, "too big"),
])
def test_bad_csv_changes_nothing(live_server, data, detail):
    httpx.put(f"{live_server}/api/dictionary", json={"language": "es", "word": "keep", "spoken": "me"})
    for replace in (False, True):
        r = _csv(live_server, data, replace)
        assert r.status_code == 400 and detail in r.json()["detail"], r.text
    assert dictionary.load() == {"es": {"keep": "me"}, "en": {}}


@pytest.mark.gpu
def test_listen_speaks_the_word_through_the_dictionary(live_server, tmp_path):
    from conftest import similar, transcribe
    from voicer import history

    url = f"{live_server}/api/dictionary"
    httpx.put(url, json={"language": "en", "word": "ASAP", "spoken": "as soon as possible"})
    before = len(history.entries())
    r = httpx.post(f"{url}/listen", json={"language": "en", "text": "ASAP"}, timeout=300)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and r.content[:4] == b"RIFF"
    (tmp_path / "w.wav").write_bytes(r.content)
    assert similar(transcribe(tmp_path / "w.wav", "en"), "As soon as possible.") >= 0.8
    assert len(history.entries()) == before                                   # not saved to History
    r = httpx.post(f"{url}/listen", json={"language": "en", "text": "ASAP", "voice": "piper-en-us-lessac-medium"}, timeout=300)
    assert r.status_code == 200 and r.content[:4] == b"RIFF"


@pytest.mark.parametrize("body, status, detail", [
    ({"language": "fr", "text": "a"}, 400, "Language must be es or en"),
    ({"language": "es", "text": " "}, 400, "Text must have 1 to 300"),
    ({"language": "es", "text": "a" * 301}, 400, "Text must have 1 to 300"),
    ({"language": "es", "text": "hola", "voice": "nobody"}, 404, "nobody"),
])
def test_listen_bad_input(live_server, body, status, detail):
    r = httpx.post(f"{live_server}/api/dictionary/listen", json=body)
    assert r.status_code == status and detail in r.json()["detail"], r.text
