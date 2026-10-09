"""Engine registry."""
from .f5 import F5Engine
from .kokoro import KokoroEngine
from .piper import PiperEngine
from .xtts import XTTSEngine

ENGINES = {
    "xtts": XTTSEngine,
    "f5": F5Engine,
    "kokoro": KokoroEngine,
    "piper": PiperEngine,
}
