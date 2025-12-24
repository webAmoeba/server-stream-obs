#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found" >&2
  exit 1
fi

if [ ! -d "$ROOT_DIR/.venv" ]; then
  python3 -m venv "$ROOT_DIR/.venv"
fi

"$ROOT_DIR/.venv/bin/pip" install --upgrade pip
"$ROOT_DIR/.venv/bin/pip" install -r "$ROOT_DIR/requirements.txt"

"$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/obs_config.py"

if [ -f "$ROOT_DIR/.env" ]; then
  "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/obs_prepare.py"
fi
"$ROOT_DIR/bin/install_obs_mpv.sh"

