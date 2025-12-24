#!/usr/bin/env bash
set -euo pipefail

# Install/build obs-mpv plugin for OBS
# Env overrides:
#   OBS_MPV_SRC  - base dir for source clone (default: /root/repos/obs-mpv-src)
#   OBS_MPV_REF  - git ref/tag/branch (default: master)
#   SKIP_OBS_MPV - if set to 1, skip install

if [ "${SKIP_OBS_MPV:-0}" = "1" ]; then
  echo "SKIP_OBS_MPV=1, skipping obs-mpv install"
  exit 0
fi

OBS_MPV_SRC="${OBS_MPV_SRC:-/root/repos/obs-mpv-src}"
OBS_MPV_REF="${OBS_MPV_REF:-master}"

apt-get update -y
apt-get install -y git build-essential cmake pkg-config libobs-dev libmpv-dev libegl1-mesa-dev

mkdir -p "$OBS_MPV_SRC"
if [ ! -d "$OBS_MPV_SRC/obs-mpv" ]; then
  git clone https://github.com/univrsal/obs-mpv "$OBS_MPV_SRC/obs-mpv"
fi

cd "$OBS_MPV_SRC/obs-mpv"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git fetch --all --tags
  git checkout "$OBS_MPV_REF"
fi

python3 - <<"PY"
from pathlib import Path

# Patch mpv-source.c: set aid correctly
path = Path("src/mpv-source.c")
text = path.read_text(encoding="utf-8")
old = """    if (audio_track != context->current_audio_track) {\n        context->current_audio_track = audio_track;\n        dstr_printf(&str, \"%d\", context->current_video_track);\n        MPV_SEND_COMMAND_ASYNC(\"set\", \"vid\", str.array);\n    }\n"""
new = """    if (audio_track != context->current_audio_track) {\n        context->current_audio_track = audio_track;\n        dstr_printf(&str, \"%d\", context->current_audio_track);\n        MPV_SEND_COMMAND_ASYNC(\"set\", \"aid\", str.array);\n    }\n"""
if old in text:
    text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")

# Patch mpv-backend.c: set aid on init + force libmpv rendering settings
path = Path("src/mpv-backend.c")
text = path.read_text(encoding="utf-8")
old = """    dstr_printf(&str, \"%d\", context->current_video_track);\n    MPV_SEND_COMMAND_ASYNC(\"set\", \"vid\", str.array);\n\n    dstr_printf(&str, \"%d\", context->current_video_track);\n    MPV_SEND_COMMAND_ASYNC(\"set\", \"vid\", str.array);\n\n    dstr_printf(&str, \"%d\", context->current_sub_track);\n    MPV_SEND_COMMAND_ASYNC(\"set\", \"sid\", str.array);\n"""
new = """    dstr_printf(&str, \"%d\", context->current_video_track);\n    MPV_SEND_COMMAND_ASYNC(\"set\", \"vid\", str.array);\n\n    dstr_printf(&str, \"%d\", context->current_audio_track);\n    MPV_SEND_COMMAND_ASYNC(\"set\", \"aid\", str.array);\n\n    dstr_printf(&str, \"%d\", context->current_sub_track);\n    MPV_SEND_COMMAND_ASYNC(\"set\", \"sid\", str.array);\n"""
if old in text:
    text = text.replace(old, new)

old = """    context->mpv = mpv_create();\n\n    MPV_SET_OPTION(\"audio-client-name\", \"OBS\");\n\n    int result = mpv_initialize(context->mpv) < 0;\n"""
new = """    context->mpv = mpv_create();\n    if (!context->mpv) {\n        obs_log(LOG_ERROR, \"Failed to create mpv context\");\n        context->init_failed = true;\n        return;\n    }\n\n    mpv_set_option_string(context->mpv, \"vo\", \"libmpv\");\n    mpv_set_option_string(context->mpv, \"hwdec\", \"no\");\n    mpv_set_option_string(context->mpv, \"gpu-context\", \"egl\");\n    mpv_set_option_string(context->mpv, \"audio-client-name\", \"OBS\");\n\n    int result = mpv_initialize(context->mpv) < 0;\n"""
if old in text:
    text = text.replace(old, new)

path.write_text(text, encoding="utf-8")
PY

cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
cmake --install build

# Ensure OBS sees plugin even if it does not scan /usr/local
if [ ! -e /usr/lib/x86_64-linux-gnu/obs-plugins/obs-mpv.so ]; then
  ln -s /usr/local/lib/obs-plugins/obs-mpv.so /usr/lib/x86_64-linux-gnu/obs-plugins/obs-mpv.so
fi
if [ ! -e /usr/share/obs/obs-plugins/obs-mpv ]; then
  ln -s /usr/local/share/obs/obs-plugins/obs-mpv /usr/share/obs/obs-plugins/obs-mpv
fi
