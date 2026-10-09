"""Phase 4: blend two voices into a new one with a ratio (XTTS speaker latents)."""
import io
import tempfile
from pathlib import Path

import pytest
import torch
from fastapi.testclient import TestClient

from conftest import similar, transcribe

A, B = "xtts-daisy-studious", "xtts-viktor-eka"           # clearly different library voices
T = "The morning train left the station quietly and slowly rolled toward the distant hills."


@pytest.fixture(scope="module")
def c():
    from voicer.server import app

    with TestClient(app) as client:
        yield client


def test_mix_math():
    from voicer.engines.xtts import mix_latents

    a = (torch.ones(1, 4, 8), torch.tensor([3.0, 0, 0]).view(1, 3, 1))
    b = (torch.zeros(1, 4, 8), torch.tensor([0, 4.0, 0]).view(1, 3, 1))
    g, s = mix_latents(a, b, 0.7)
    assert torch.allclose(g, torch.full((1, 4, 8), 0.7))
    assert abs(float(s.norm()) - (0.7 * 3 + 0.3 * 4)) < 1e-5            # norm kept between sources
    assert float(s[0, 0, 0]) / float(s[0, 1, 0]) == pytest.approx(0.7 * 3 / (0.3 * 4))
    with pytest.raises(ValueError):
        mix_latents(a, (torch.zeros(1, 5, 8), b[1]), 0.5)


def test_validation_and_sources(c):
    from voicer import blend, voices

    src = c.get("/api/blend/sources").json()
    ids = {v["id"] for v in src}
    assert A in ids and B in ids and not any(i.startswith(("piper-", "kokoro-")) for i in ids)
    for body, code in (({"a": A, "b": A}, 400), ({"a": A, "b": B, "ratio": 1.0}, 400),
                       ({"a": A, "b": B, "ratio": 0.0}, 400), ({"a": A, "b": "piper-en-us-lessac-medium"}, 400),
                       ({"a": A, "b": "nope"}, 404), ({"a": A, "b": B, "language": "fr"}, 400)):
        assert c.post("/api/blend/preview", json=body).status_code == code, body
    assert c.post("/api/blend", json={"a": A, "b": B, "ratio": 0.5, "name": " "}).status_code == 400
    assert voices.allowed_engines({"kind": "blended", "blend": {}}) == ["xtts"]
    assert blend._license({"license": "CPML", "commercial": False}, {"kind": "cloned"}) == {"license": "CPML", "commercial": False}
    assert blend._license({"license": "MIT", "commercial": True}, {"license": "MIT", "commercial": True})["commercial"] is True


def _emb(wav_bytes):
    from voicer import models

    f = Path(tempfile.mkdtemp()) / "x.wav"
    f.write_bytes(wav_bytes)
    with models.use("xtts") as e:
        return e.model.get_conditioning_latents(audio_path=[str(f)])[1].flatten().float().cpu(), f


def test_ratio_moves_voice_between_sources(c):
    """Speaker similarity of the blended speech follows the slider: 80/20 sounds like A, 20/80 like B."""
    from voicer import library, models

    with models.use("xtts") as e:
        sa = e.latents(library.get(A))[1].flatten().float().cpu()
        sb = e.latents(library.get(B))[1].flatten().float().cpu()
    cos = lambda x, y: float(torch.nn.functional.cosine_similarity(x, y, 0))
    sims = {}
    for r in (0.8, 0.5, 0.2):
        resp = c.post("/api/blend/preview", json={"a": A, "b": B, "ratio": r, "text": T, "language": "en"})
        assert resp.status_code == 200 and resp.headers["content-type"] == "audio/wav"
        x, wav = _emb(resp.content)
        sims[r] = (cos(x, sa), cos(x, sb))
        if r == 0.5:
            assert similar(transcribe(wav, "en"), T) > 0.8
    assert sims[0.8][0] > sims[0.8][1] + 0.2, sims
    assert sims[0.2][1] > sims[0.2][0] + 0.2, sims
    assert sims[0.8][0] > sims[0.5][0] > sims[0.2][0], sims


def test_save_blend_is_self_contained(c, tmp_path):
    """Saved blend stores its latents; it still speaks after a source voice is deleted."""
    from test_transcribe import EN, speech

    from voicer import library, tts, voices

    mine = voices.create("Blend source", sample_files=[speech(tmp_path / "s.wav", EN, "piper-en-us-lessac-medium", "en")])
    r = c.post("/api/blend", json={"a": mine["id"], "b": A, "ratio": 0.7, "name": "Test Blend", "language": "es",
                                   "tags": "mix, test", "description": "70/30"})
    assert r.status_code == 200, r.text
    v = r.json()
    assert "dir" not in v and v["kind"] == "blended" and v["engine"] == "xtts" and v["language"] == "es"
    assert v["blend"] == {"a": mine["id"], "a_name": "Blend source", "b": A, "b_name": library.get(A)["name"], "ratio": 0.7}
    assert v["license"] == library.get(A)["license"] and v["commercial"] is False   # stricter terms kept
    assert v["tags"] == ["mix", "test"] and v["preview"] == "preview.wav"
    d = Path(voices.get(v["id"])["dir"])
    assert (d / "blend.pt").is_file() and (d / "preview.wav").stat().st_size > 10000
    voices.delete(mine["id"])
    from voicer import models

    with models.use("xtts") as e:
        e._latents.clear()
    out = tts.speak("La mezcla funciona bien.", v["id"], "es")
    assert len(out.samples) / out.sr > 0.8
    assert v["id"] in {x["id"] for x in c.get("/api/blend/sources").json()}       # blends can be blended again
    voices.delete(v["id"])
