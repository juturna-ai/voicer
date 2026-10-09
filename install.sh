#!/usr/bin/env bash
# Install Voice Studio (Linux, WSL2 or a VPS). Safe to run again: it only adds what is missing.
#   ./install.sh          app + PyTorch for NVIDIA GPUs (CUDA 12.6)
#   ./install.sh --cpu    app + CPU-only PyTorch (a VPS without a GPU; much smaller download)
#   ./install.sh --dev    also the test tools (pytest, Playwright Chromium)
# Models download on first use into data/models. Then start with: ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

CPU=0 DEV=0
for a in "$@"; do
  case "$a" in
    --cpu) CPU=1 ;;
    --dev) DEV=1 ;;
    -h|--help) sed -n '2,6s/^# \{0,1\}//p' "$0"; exit 0 ;;
    *) echo "Unknown option: $a (see ./install.sh --help)" >&2; exit 2 ;;
  esac
done

# uv (https://docs.astral.sh/uv, MIT/Apache-2.0) makes the Python 3.11 environment and installs the packages.
UV=${UV:-$(command -v uv || true)}
for c in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
  [ -z "$UV" ] && [ -x "$c" ] && UV=$c
done
if [ -z "$UV" ]; then
  echo "==> Installing uv (Python package manager) into ~/.local/bin"
  command -v curl >/dev/null || { echo "curl is needed. Install it (e.g. sudo apt install curl) and run again." >&2; exit 1; }
  curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
  UV="$HOME/.local/bin/uv"
fi

if [ ! -x .venv/bin/python ]; then
  echo "==> Making the Python 3.11 environment (.venv)"
  "$UV" venv --python 3.11 .venv
fi

if [ "$CPU" = 1 ]; then TORCH=https://download.pytorch.org/whl/cpu; else TORCH=https://download.pytorch.org/whl/cu126; fi
echo "==> Installing packages (first time: several GB, can take 10+ minutes)"
"$UV" pip install --python .venv/bin/python -c requirements/constraints.txt -c requirements/lock.txt \
  -r requirements/base.txt --extra-index-url "$TORCH" --index-strategy unsafe-best-match

if [ "$DEV" = 1 ]; then
  echo "==> Installing test tools"
  "$UV" pip install --python .venv/bin/python -c requirements/constraints.txt -c requirements/lock.txt -r requirements/dev.txt
  .venv/bin/python -m playwright install chromium
fi

echo "==> Checking"
.venv/bin/python - <<'EOF'
import torch
import voicer.server  # noqa: F401  (the app imports)
gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
print(f"Voice Studio is installed. GPU: {gpu or 'none (CPU mode: slower)'}")
EOF
echo "Start it with: ./start.sh --open"
