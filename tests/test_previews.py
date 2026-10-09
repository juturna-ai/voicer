from conftest import similar, transcribe
import soundfile as sf


def test_every_library_voice_has_5_to_8s_preview():
    from voicer import library

    for v in library.catalog():
        p = library.preview_path(v)
        assert p, v["id"]
        info = sf.info(str(p))
        assert 5.0 <= info.duration <= 8.2, (v["id"], info.duration)   # MP3 frames pad a few ms


def test_preview_copied_to_my_voices():
    from pathlib import Path

    from voicer import library

    mine = library.add_to_my_voices("kokoro-af-heart")
    assert mine["preview"] == "preview.mp3" and (Path(mine["dir"]) / "preview.mp3").is_file()


def test_previews_are_intelligible():
    from voicer import library

    for vid in ("kokoro-af-heart", "piper-es-mx-ald-medium", "xtts-ana-florence-es", "piper-en-gb-alba-medium"):
        v = library.get(vid)
        text = transcribe(str(library.preview_path(v)), v["language"])
        expect = "esta es una muestra de mi voz" if v["language"] == "es" else "this is a preview of my voice"
        assert similar(text, expect) > 0.3 and expect.split()[-1] in text.lower(), (vid, text)
