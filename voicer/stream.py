"""Live streaming: send audio while the rest of the text is still being spoken.

`open_stream()` checks the request, speaks the first sentence and returns the stream info plus an iterator of
encoded bytes: the first sentence at once, then each next sentence as soon as it is ready. When the iterator
ends, the whole clip is saved to History under `info["id"]` (same entry as a normal generate). If the client
goes away early, generation stops and nothing is saved. An engine error after the first bytes ends the stream
early (the status code is already sent)."""
from __future__ import annotations

import logging
import struct
from typing import Iterator

import numpy as np

from . import formats, history, tts, voices
from .engines import ENGINES
from .engines.base import Audio

log = logging.getLogger(__name__)
UNKNOWN = 0xFFFFFFFF                     # WAV sizes when the length is not known yet (standard for live WAV)


class _Sink:
    """File-like target for PyAV: collects bytes until they are taken."""

    def __init__(self) -> None:
        self.buf = bytearray()

    def write(self, b) -> int:
        self.buf += b
        return len(b)

    def take(self) -> bytes:
        b = bytes(self.buf)
        self.buf.clear()
        return b


class Encoder:
    """Float audio pieces (all at rate `sr`) → bytes of `fmt`, piece by piece. Same formats as `formats.FORMATS`."""

    def __init__(self, fmt: str, sr: int) -> None:
        self.spec, self.fmt, self.sr = formats.check(fmt), fmt, sr
        self.header = b""
        if fmt == "wav":
            self.out_sr = sr
            self.header = struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", UNKNOWN, b"WAVE", b"fmt ", 16, 1, 1, sr,
                                      sr * 2, 2, 16, b"data", UNKNOWN)
            return
        import av

        self.out_sr = self.spec["rate"] or sr
        self.sink = _Sink()
        container = self.spec["container"]
        # write each packet out at once (no 32 KB buffering); OGG pages every 0.1 s instead of every 1 s
        opts = {"flush_packets": "1", **({"page_duration": "100000"} if container == "ogg" else {})}
        self.c = av.open(self.sink, "w", format=container, buffer_size=4096, options=opts)
        self.st = self.c.add_stream(self.spec["codec"], rate=self.out_sr, layout="mono")
        if self.spec["bit_rate"]:
            self.st.bit_rate = self.spec["bit_rate"]
        self.st.options = self.spec["options"]
        self.rs = av.AudioResampler(format=self.st.codec_context.format, layout="mono", rate=self.out_sr,
                                    frame_size=self.st.codec_context.frame_size or None)

    @property
    def mime(self) -> str:
        return self.spec["mime"]

    def feed(self, a: Audio) -> bytes:
        x = np.clip(tts.resample(a, self.sr).samples, -1, 1).astype(np.float32)
        head, self.header = self.header, b""
        if not len(x):
            return head
        if self.fmt == "wav":
            return head + (x * 32767).astype("<i2").tobytes()
        import av

        frame = av.AudioFrame.from_ndarray(x[None, :], format="flt", layout="mono")
        frame.sample_rate = self.sr
        for f in self.rs.resample(frame):
            self.c.mux(self.st.encode(f))
        return self.sink.take()

    def close(self) -> bytes:
        """The last bytes (encoder tail). Call once, at the end."""
        if self.fmt == "wav":
            return b""
        for f in self.rs.resample(None):
            self.c.mux(self.st.encode(f))
        self.c.mux(self.st.encode(None))
        self.c.close()
        return self.sink.take()


def open_stream(text: str, voice: str | dict, language: str = "auto", speed: float = 1.0,
                engine: str | None = None, fmt: str = "mp3", **opts) -> tuple[dict, Iterator[bytes]]:
    """Check the request and speak the first sentence (errors are raised here, before any byte is sent).
    Returns `({id, format, mime, sample_rate}, bytes iterator)`. `sample_rate` is the rate of the sent audio."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Text is empty")
    if len(text) > tts.MAX_TEXT:
        raise ValueError(f"Text is too long ({len(text)} characters, max {tts.MAX_TEXT})")
    if not 0.5 <= speed <= 2.0:
        raise ValueError("Speed must be between 0.5 and 2.0")
    formats.check(fmt)
    v = tts._voice(voice)                                    # unknown voice → KeyError
    if engine and engine != v.get("engine") and engine not in voices.allowed_engines(v):
        raise ValueError(f"Engine '{engine}' not allowed for voice '{v.get('id')}'")
    used = engine or v.get("engine") or voices.DEFAULT_CLONE_ENGINE
    if used not in ENGINES:
        raise ValueError(f"Unknown engine '{used}'")
    lead, parts = tts.speak_parts(text, v, language, speed, engine, stream_first=True, **opts)
    first = next(parts)                                      # the slow part of the first byte: done before we answer
    sr = first.audio.sr
    enc = Encoder(fmt, sr)
    entry_id = history.new_id()
    info = {"id": entry_id, "format": fmt, "mime": enc.mime, "sample_rate": enc.out_sr}

    def run() -> Iterator[bytes]:
        done, cur = [], first
        try:
            if lead and (b := enc.feed(Audio(np.zeros(int(sr * lead), np.float32), sr))):
                yield b
            while cur is not None:
                done.append(cur)
                a = tts.resample(cur.audio, sr)
                if not cur.last:                             # the pause goes out with the sentence: no stall
                    a = Audio(np.concatenate([a.samples, np.zeros(int(sr * cur.pause), np.float32)]), sr)
                if b := enc.feed(a):
                    yield b
                cur = next(parts, None)
            if b := enc.close():
                yield b
        except GeneratorExit:                                # client went away: stop, save nothing
            parts.close()
            raise
        except Exception:                                    # headers are sent; end the stream short
            log.exception("Live stream failed")
            parts.close()
            return
        audio, cues = tts.join_parts(done, lead)
        history.add(audio, text, v, language, used, {"speed": speed, **opts, "stream": True}, cues=cues,
                    entry_id=entry_id)

    return info, run()
