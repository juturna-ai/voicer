"""Phase 10: job queue — many requests at once, speech jobs one at a time, full queue → 503, pages stay fast."""
import asyncio
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from voicer import jobs

EN = "piper-en-us-lessac-medium"


def test_gate_runs_one_at_a_time_in_order_and_survives_cancel():
    async def main():
        order, active, peak = [], [0], [0]

        async def job(i, secs=0.01):
            async with jobs.slot():
                active[0] += 1
                peak[0] = max(peak[0], active[0])
                order.append(i)
                await asyncio.sleep(secs)
                active[0] -= 1

        first = asyncio.create_task(job(0, 0.05))
        await asyncio.sleep(0)
        waiting = [asyncio.create_task(job(i)) for i in range(1, 6)]
        await asyncio.sleep(0)
        waiting[1].cancel()                               # a client that leaves while it waits
        await asyncio.gather(first, *waiting, return_exceptions=True)
        assert peak[0] == 1 and order == [0, 1, 3, 4, 5]
        async with asyncio.timeout(1):                    # the slot was not lost
            async with jobs.slot():
                pass

    before = dict(jobs.stats)
    asyncio.run(main())
    assert jobs.stats["running"] == before["running"] and jobs.stats["waiting"] == before["waiting"]


def test_full_queue_is_refused_with_retry_after(monkeypatch):
    monkeypatch.setattr(jobs, "MAX_WAITING", 2)

    async def main():
        hold = asyncio.Event()

        async def job():
            async with jobs.slot():
                await hold.wait()

        tasks = [asyncio.create_task(job()) for _ in range(3)]  # 1 running + 2 waiting
        await asyncio.sleep(0.01)
        with pytest.raises(jobs.Busy, match="Server busy: 2 jobs are waiting") as e:
            await jobs.enter()
        assert e.value.retry_after >= 1
        hold.set()
        await asyncio.gather(*tasks)

    asyncio.run(main())


def test_routes():
    for p in ("/api/speak", "/speak", "/api/batch", "/batch", "/api/dialogue", "/voice-changer", "/v1/audio/speech",
              "/api/tts", "/api/blend", "/api/blend/preview", "/api/clone/drafts/abc/save", "/api/dictionary/listen",
              "/api/subtitles"):
        assert jobs.JOB_ROUTES.match(p), p
    for p in ("/api/voices", "/api/batch/parse", "/api/batch/zip", "/api/history", "/api/health", "/mcp",
              "/api/dictionary", "/api/history/abc/subtitles"):
        assert not jobs.JOB_ROUTES.match(p), p


def _post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            r.read()
            return r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, {**dict(e.headers), "body": e.read().decode()}


def test_many_requests_at_once(live_server, monkeypatch):
    """60 speech requests at once: no crash, the queue limit turns the extra ones into 503 + Retry-After,
    and the voice list still answers fast while they wait."""
    monkeypatch.setattr(jobs, "MAX_WAITING", 40)
    results, lat, stop = [], [], threading.Event()

    def speak(i):
        results.append(_post(live_server + "/api/speak", {"text": f"Queue test {i}, {time.time()}.", "voice": EN, "format": "wav"}))

    def probe():
        while not stop.is_set():
            t = time.monotonic()
            urllib.request.urlopen(live_server + "/api/voices", timeout=60).read()
            lat.append(time.monotonic() - t)
            time.sleep(0.2)

    threads = [threading.Thread(target=speak, args=(i,)) for i in range(60)]
    p = threading.Thread(target=probe)
    p.start()
    for t in threads:
        t.start()
    time.sleep(1.5)
    q = json.loads(urllib.request.urlopen(live_server + "/api/health", timeout=30).read())["queue"]
    assert q["running"] == 1 and q["waiting"] >= 1 and q["max_waiting"] == 40
    for t in threads:
        t.join()
    stop.set()
    p.join()
    codes = [c for c, _ in results]
    assert set(codes) <= {200, 503} and codes.count(200) >= 41
    busy = [h for c, h in results if c == 503]
    assert all(int(h["retry-after"]) >= 1 and "Server busy" in h["body"] for h in busy)
    assert max(lat) < 2, max(lat)
    r = _post(live_server + "/v1/audio/speech", {"model": "tts-1", "input": "After the rush.", "voice": EN})
    assert r[0] == 200                                   # the queue is free again
