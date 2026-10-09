import numpy as np
import pytest
import soundfile as sf

from conftest import similar, transcribe
from voicer.engines.base import Audio

SENTENCES = [
    "The morning train left the station a little after seven.",
    "Most passengers were reading, and a few were already asleep.",
    "Outside, the fields were covered in a thin layer of frost.",
    "A conductor walked slowly through the carriages, checking tickets.",
    "By the time we reached the coast, the sun had finally come out.",
    "We stepped onto the platform and breathed in the cold sea air.",
]


def db(x):
    return 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-12)


@pytest.fixture(scope="module")
def noisy(tmp_path_factory):
    """~40 s of real speech (Piper) with 2.5 s gaps, rumble, hiss, quiet level, 44.1 kHz stereo."""
    from voicer import tts

    parts = []
    for s in SENTENCES * 2:
        a = tts.resample(tts.synthesize(s, "piper-en-us-lessac-medium", "en"), 44100)
        parts += [a.samples, np.zeros(int(44100 * 2.5), np.float32)]
    y = np.concatenate([np.zeros(44100, np.float32)] + parts)
    rng = np.random.default_rng(0)
    t = np.arange(len(y)) / 44100
    y = 0.15 * y / np.abs(y).max() + 0.004 * rng.standard_normal(len(y)) + 0.01 * np.sin(2 * np.pi * 40 * t)
    p = tmp_path_factory.mktemp("noisy") / "noisy.wav"
    sf.write(p, np.stack([y, y * 0.9], axis=1), 44100)
    return p, len(y) / 44100


def test_clean_and_split(noisy, tmp_path):
    from voicer import audio, cleanup

    path, raw_seconds = noisy
    raw = audio.decode(path)
    c = cleanup.clean(raw)
    assert c.sr == 24000 and c.samples.ndim == 1
    # silence trimmed: gaps of 2.5 s shortened → much shorter than the raw file
    assert len(c.samples) / c.sr < raw_seconds - 12
    # normalized: peak ≤ −1 dBFS, speech level near −20 dBFS
    assert np.abs(c.samples).max() <= 10 ** (-1 / 20) + 1e-6
    mask = cleanup.speech_mask(c.samples, c.sr)
    n = int(cleanup.FRAME * c.sr)
    speech = np.concatenate([c.samples[i * n:(i + 1) * n] for i in np.flatnonzero(mask)])
    pauses = np.concatenate([c.samples[i * n:(i + 1) * n] for i in np.flatnonzero(~mask)])
    assert -22.5 < db(speech) < -17.5
    # denoised: signal-to-noise (speech vs pauses) clearly better than the input
    rmask = cleanup.speech_mask(cleanup._resample(raw).samples, 24000)
    r = cleanup._resample(raw).samples
    raw_snr = db(np.concatenate([r[i * n:(i + 1) * n] for i in np.flatnonzero(rmask)])) - \
        db(np.concatenate([r[i * n:(i + 1) * n] for i in np.flatnonzero(~rmask)]))
    assert db(speech) - db(pauses) > raw_snr + 8
    # split: every clip 6–15 s
    clips = cleanup.split(c)
    assert len(clips) >= 2
    assert all(6.0 <= len(k.samples) / k.sr <= 15.0 for k in clips), [len(k.samples) / k.sr for k in clips]
    assert sum(len(k.samples) for k in clips) == len(c.samples)
    # still intelligible
    p = tmp_path / "c0.wav"
    audio.write_wav(clips[0], p)
    assert similar(transcribe(p, "en"), " ".join(SENTENCES[:2])) > 0.5


def test_split_rules():
    from voicer import cleanup

    sr = 24000
    short = Audio(np.ones(sr * 4, np.float32) * 0.1, sr)
    assert len(cleanup.split(short)) == 1
    # 31 s of tone with a pause every 3 s → all clips within 6–15 s
    y = np.concatenate([np.concatenate([0.2 * np.sin(np.arange(int(sr * 2.6)) / 5), np.zeros(int(sr * 0.4))])
                        for _ in range(10)] + [0.2 * np.sin(np.arange(sr) / 5)]).astype(np.float32)
    clips = cleanup.split(Audio(y, sr))
    assert all(6.0 <= len(k.samples) / sr <= 15.0 for k in clips)
    with pytest.raises(ValueError):
        cleanup.clean(Audio(np.zeros(sr * 3, np.float32), sr))


def test_draft_process_api(noisy):
    from fastapi.testclient import TestClient

    from voicer.server import app

    path, _ = noisy
    with TestClient(app) as c:
        d = c.post("/api/clone/drafts").json()
        c.post(f"/api/clone/drafts/{d['id']}/files", files=[("files", ("noisy.wav", path.read_bytes(), "audio/wav"))])
        r = c.post(f"/api/clone/drafts/{d['id']}/process")
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["clips"]) >= 2 and body["clean_seconds"] > 20 and not body["clean_errors"]
        clip = c.get(f"/api/clone/drafts/{d['id']}/clips/{body['clips'][0]['name']}")
        assert clip.status_code == 200 and clip.content[:4] == b"RIFF"
