"""Central settings. Every value can be overridden with an environment variable."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("VOICER_DATA", ROOT / "data"))
VOICES_DIR = DATA_DIR / "voices"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = DATA_DIR / "outputs"
MODELS_DIR = Path(os.environ.get("VOICER_MODELS", ROOT / "data" / "models"))  # shared by tests

HOST = os.environ.get("VOICER_HOST", "0.0.0.0")
PORT = int(os.environ.get("VOICER_PORT", "8765"))
DEVICE = os.environ.get("VOICER_DEVICE", "cuda")
IDLE_UNLOAD_SECONDS = int(os.environ.get("VOICER_IDLE_UNLOAD", "600"))

# Coqui XTTS-v2 weights are under the Coqui Public Model License (non-commercial).
os.environ.setdefault("COQUI_TOS_AGREED", "1")

for d in (VOICES_DIR, CACHE_DIR, OUTPUT_DIR, MODELS_DIR):
    d.mkdir(parents=True, exist_ok=True)
