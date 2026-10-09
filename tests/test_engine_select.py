import pytest

from conftest import similar, transcribe


def test_allowed_engines_and_switch(tmp_path):
    from voicer import voices

    ref = tmp_path / "r.wav"
    import numpy as np, soundfile as sf
    sf.write(ref, np.zeros(16000, np.float32), 16000)
    v = voices.create("Switchable", sample_files=[ref])
    assert v["engine"] == "xtts"
    assert set(voices.allowed_engines(v)) == {"xtts", "f5"}
    assert voices.set_engine(v["id"], "f5")["engine"] == "f5"
    assert voices.get(v["id"])["engine"] == "f5"
    with pytest.raises(ValueError):
        voices.set_engine(v["id"], "kokoro")

    p = voices.create("Preset K", kind="preset", engine="kokoro", engine_voice="af_heart")
    assert voices.allowed_engines(p) == ["kokoro"]
    with pytest.raises(ValueError):
        voices.update(p["id"], engine="xtts")


@pytest.mark.gpu
def test_same_clone_two_engines(tmp_out):
    from voicer import audio, tts, voices

    ref = tts.synthesize("A short sample used to clone this voice for testing.",
                         {"id": "s", "engine": "piper", "engine_voice": "en_US-lessac-medium"}, "en")
    v = voices.create("Two Engines", sample_files=[audio.write_wav(ref, tmp_out / "two.wav")])
    text = "Engines can be chosen for every voice."
    for eng in ("xtts", "f5"):
        voices.set_engine(v["id"], eng)
        out = tts.synthesize(text, v["id"], "en")
        assert similar(transcribe(audio.write_wav(out, tmp_out / f"two_{eng}.wav"), "en"), text) > 0.7
    with pytest.raises(ValueError):
        tts.synthesize(text, v["id"], "en", engine="piper")
