#!/usr/bin/env bash
# One-file Linux binary (ELF) with Tk GUI, bundled_configs, and CLI — no sudo required.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -U pip pyinstaller intelhex

rm -f converter-linux.spec 2>/dev/null || true
.venv/bin/pyinstaller --clean --noconfirm --onefile --name converter-linux \
  --hidden-import gui \
  --hidden-import config_manager \
  --hidden-import api_client \
  --collect-all tkinter \
  --add-data "bundled_configs:bundled_configs" \
  converter.py

echo "Built: $ROOT/dist/converter-linux"
