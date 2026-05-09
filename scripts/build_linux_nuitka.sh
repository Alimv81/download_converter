#!/usr/bin/env bash
# One-file Linux binary via Nuitka (requires patchelf: sudo apt install patchelf).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v patchelf >/dev/null 2>&1; then
  echo "patchelf is required for Nuitka standalone on Linux."
  echo "  sudo apt install patchelf"
  echo "Or without sudo: apt-get download patchelf && dpkg-deb -x patchelf_*.deb /tmp/patchelf_extract"
  echo "  export PATH=/tmp/patchelf_extract/usr/bin:\$PATH"
  exit 1
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -U pip nuitka intelhex

.venv/bin/python -m nuitka converter.py \
  --onefile \
  --enable-plugin=tk-inter \
  --include-module=gui \
  --include-module=config_manager \
  --include-module=api_client \
  --include-data-dir=bundled_configs=bundled_configs \
  --output-dir=dist \
  --assume-yes-for-downloads \
  --output-filename=converter-linux-nuitka

echo "Built: $ROOT/dist/converter-linux-nuitka"
