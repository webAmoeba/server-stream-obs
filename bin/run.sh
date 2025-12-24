#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export HOME="${HOME:-/root}"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/obs-runtime}"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

DISPLAY="${OBS_DISPLAY:-:99}"
export DISPLAY

Xvfb "$DISPLAY" -screen 0 1920x1080x24 -nolisten tcp &
XVFB_PID=$!

if command -v pulseaudio >/dev/null 2>&1; then
  pulseaudio --check || pulseaudio --start --exit-idle-time=-1 || true
fi

# Prepare OBS config (no spaces around =)
"$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/obs_prepare.py"

if ! command -v obs >/dev/null 2>&1; then
  echo "obs binary not found; install obs-studio" >&2
  exit 1
fi

# Start OBS with websocket overrides (forces server on)
obs --disable-shutdown-check --no-splash \
  --websocket_port "${OBS_PORT:-4455}" \
  --websocket_password "${OBS_PASSWORD:?OBS_PASSWORD missing}" \
  --websocket_ipv4_only \
  &
OBS_PID=$!

cleanup() {
  kill "$OBS_PID" "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT

# Wait for websocket port
for i in {1..60}; do
  if ss -ltn 2>/dev/null | grep -q ":${OBS_PORT:-4455}"; then
    break
  fi
  sleep 1
done

exec "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/stream_obs.py"
