import time

import pytest

pytestmark = pytest.mark.gpu


def test_xtts_latent_cache(tmp_out):
    from voicer import audio, models, tts, voices
    from voicer.engines.xtts import XTTSEngine

    ref = tts.synthesize("Sample audio for the embedding cache test.",
                         {"id": "s", "engine": "piper", "engine_voice": "en_US-lessac-medium"}, "en")
    v = voices.create("Cache Me", sample_files=[audio.write_wav(ref, tmp_out / "cache.wav")])

    with models.use("xtts") as eng:
        calls = []
        orig = eng.model.get_conditioning_latents
        eng.model.get_conditioning_latents = lambda *a, **k: calls.append(1) or orig(*a, **k)
        try:
            eng.latents(v)
            t = time.time(); eng.latents(v); fast = time.time() - t
            assert len(calls) == 1 and fast < 0.01          # memory hit
            eng._latents.clear()
            eng.latents(v)
            assert len(calls) == 1                           # disk hit, no recompute
            # changing samples invalidates the cache
            sample = __import__("pathlib").Path(v["dir"]) / v["samples"][0]
            sample.write_bytes(sample.read_bytes())
            import os; os.utime(sample, ns=(time.time_ns(), time.time_ns() + 10**9))
            eng.latents(v)
            assert len(calls) == 2
        finally:
            eng.model.get_conditioning_latents = orig


def test_model_load_cached():
    from voicer import models

    a = models.manager.get("kokoro")
    t = time.time()
    b = models.manager.get("kokoro")
    assert a is b and a.loaded and time.time() - t < 0.01


def test_one_large_model_and_idle_unload():
    from voicer import models

    m = models.manager
    m.get("xtts")
    f5 = m.get("f5")
    assert not m.engines["xtts"].loaded            # GPU slot freed for f5
    k = m.get("kokoro")
    m.last_used["kokoro"] = time.time() - m.idle_seconds - 1
    assert "kokoro" in m.unload_idle() and not k.loaded
