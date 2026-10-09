"""Job queue: speech jobs (REST, OpenAI, WebSocket, MCP) wait here for their turn and run one at a time,
because there is one GPU. A waiting job holds no server thread, so pages and voice lists stay fast under load.
When too many jobs wait, a new one is refused at once (503 + Retry-After) instead of piling up until it times out."""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import time
import weakref
from collections import deque
from contextlib import asynccontextmanager

MAX_WAITING = int(os.environ.get("VOICER_MAX_QUEUE", "64"))
MAX_WAIT_SECONDS = float(os.environ.get("VOICER_QUEUE_TIMEOUT", "900"))

# Requests that make audio or run a model. Previews are left out: they are made once and then read from disk.
JOB_ROUTES = re.compile(r"^/(?:(?:api/)?(?:speak|batch|dialogue|voice-changer)|api/tts|v1/audio/speech|api/blend(?:/preview)?"
                        r"|api/clone/drafts/[^/]+/(?:process|transcribe|preview|save)|api/dictionary/listen|api/subtitles)/?$")

stats = {"running": 0, "waiting": 0, "done": 0, "rejected": 0}
_avg = [5.0]                       # running mean of job seconds, for Retry-After
_start: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()   # task → start time of its job


class Busy(Exception):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


class _Gate:
    """FIFO lock for one event loop. A waiter that is cancelled after it was handed the slot passes it on,
    so the slot can never be lost."""

    def __init__(self) -> None:
        self.busy = False
        self.queue: deque[asyncio.Future] = deque()

    async def acquire(self) -> None:
        if not self.busy and not self.queue:
            self.busy = True
            return
        fut = asyncio.get_running_loop().create_future()
        self.queue.append(fut)
        try:
            async with asyncio.timeout(MAX_WAIT_SECONDS):
                await fut
        except BaseException:
            if fut.done() and not fut.cancelled():
                self.release()                       # we got the slot as we were cancelled: hand it on
            else:
                fut.cancel()
                try:
                    self.queue.remove(fut)
                except ValueError:
                    pass
            raise

    def release(self) -> None:
        while self.queue:
            fut = self.queue.popleft()
            if not fut.done():
                fut.set_result(None)                 # the slot goes straight to the next job
                return
        self.busy = False


_gates: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()   # one per event loop (tests run several)


def _gate() -> _Gate:
    loop = asyncio.get_running_loop()
    if loop not in _gates:
        _gates[loop] = _Gate()
    return _gates[loop]


def retry_after() -> int:
    return max(1, min(300, math.ceil(_avg[0] * (stats["waiting"] + stats["running"]))))


async def enter() -> None:
    """Wait for this job's turn. Raises Busy when the queue is full or the wait is too long."""
    if stats["waiting"] >= MAX_WAITING:
        stats["rejected"] += 1
        raise Busy(f"Server busy: {stats['waiting']} jobs are waiting. Try again in a few seconds.", retry_after())
    stats["waiting"] += 1
    try:
        await _gate().acquire()
    except TimeoutError:
        stats["rejected"] += 1
        raise Busy(f"Server busy: waited {MAX_WAIT_SECONDS:.0f} s for a turn. Try again later.", retry_after()) from None
    finally:
        stats["waiting"] -= 1
    stats["running"] += 1
    _start[asyncio.current_task()] = time.monotonic()


def leave() -> None:
    t0 = _start.pop(asyncio.current_task(), None)
    if t0 is not None:
        _avg[0] = 0.8 * _avg[0] + 0.2 * (time.monotonic() - t0)
    stats["running"] -= 1
    stats["done"] += 1
    _gate().release()


@asynccontextmanager
async def slot():
    await enter()
    try:
        yield
    finally:
        leave()


def status() -> dict:
    return {**stats, "max_waiting": MAX_WAITING}


class QueueMiddleware:
    """ASGI middleware: job routes (see JOB_ROUTES) take a turn in the queue; a full queue answers 503."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT") or not JOB_ROUTES.match(scope["path"]):
            return await self.app(scope, receive, send)
        try:
            await enter()
        except Busy as e:
            msg = str(e)
            body = ({"error": {"message": msg, "type": "server_error", "param": None, "code": "server_busy"}}
                    if scope["path"].startswith("/v1/") else {"detail": msg})
            data = json.dumps(body).encode()
            await send({"type": "http.response.start", "status": 503, "headers": [
                (b"content-type", b"application/json"), (b"content-length", str(len(data)).encode()),
                (b"retry-after", str(e.retry_after).encode())]})
            await send({"type": "http.response.body", "body": data})
            return
        try:
            await self.app(scope, receive, send)          # streaming replies keep the turn until the last byte
        finally:
            leave()
