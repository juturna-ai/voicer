"""Model manager: lazy load, one large model in VRAM at a time, unload after idle time."""
from __future__ import annotations

import threading
import time

from . import config
from .engines import ENGINES
from .engines.base import Engine
from .engines.openvoice import OpenVoiceConverter

MODELS = {**ENGINES, "openvoice": OpenVoiceConverter}    # TTS engines + the voice changer model


class ModelManager:
    def __init__(self, idle_seconds: int = config.IDLE_UNLOAD_SECONDS):
        self.idle_seconds = idle_seconds
        self.engines: dict[str, Engine] = {}
        self.last_used: dict[str, float] = {}
        self.lock = threading.RLock()
        self._stop = threading.Event()
        self._reaper = None

    def get(self, name: str) -> Engine:
        if name not in MODELS:
            raise KeyError(f"Unknown engine '{name}'")
        with self.lock:
            eng = self.engines.get(name) or MODELS[name]()
            self.engines[name] = eng
            if eng.large and not eng.loaded:
                for other_name, other in self.engines.items():  # free the GPU slot
                    if other_name != name and other.large and other.loaded:
                        other.unload()
            eng.load()
            self.last_used[name] = time.time()
            return eng

    def touch(self, name: str) -> None:
        self.last_used[name] = time.time()

    def unload_idle(self) -> list[str]:
        now, unloaded = time.time(), []
        with self.lock:
            for name, eng in self.engines.items():
                if eng.loaded and now - self.last_used.get(name, 0) > self.idle_seconds:
                    eng.unload()
                    unloaded.append(name)
        return unloaded

    def status(self) -> dict:
        return {n: {"loaded": e.loaded, "last_used": self.last_used.get(n)} for n, e in self.engines.items()}

    def start_reaper(self, interval: int = 30) -> None:
        if self._reaper:
            return

        def loop():
            while not self._stop.wait(interval):
                self.unload_idle()

        self._reaper = threading.Thread(target=loop, daemon=True, name="model-reaper")
        self._reaper.start()

    def stop(self) -> None:
        self._stop.set()


manager = ModelManager()


from contextlib import contextmanager  # noqa: E402


@contextmanager
def use(name: str):
    """Hold an engine for one job. Blocks idle-unload and model swaps until done."""
    with manager.lock:
        eng = manager.get(name)
        try:
            yield eng
        finally:
            manager.touch(name)
