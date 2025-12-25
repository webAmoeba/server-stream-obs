#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from obsws_python import ReqClient

EP_RE = re.compile(r"S(?P<season>\d{2})E(?P<episode>\d{2})", re.IGNORECASE)


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if not key:
            continue
        if len(val) >= 2 and val[0] == val[-1] and val[0] in (chr(39), chr(34)):
            val = val[1:-1]
        os.environ.setdefault(key, val)


def env_str(key: str, default: Optional[str] = None, required: bool = False) -> str:
    val = os.environ.get(key, default)
    if required and (val is None or val == ""):
        raise ValueError(f"Missing required env: {key}")
    return "" if val is None else str(val)


def env_int(key: str, default: Optional[int] = None, required: bool = False) -> int:
    val = os.environ.get(key)
    if val is None or val == "":
        if required:
            raise ValueError(f"Missing required env: {key}")
        return int(default or 0)
    return int(val)


def env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_exts(raw: str) -> List[str]:
    parts = [p.strip().lower() for p in raw.replace(" ", ",").split(",") if p.strip()]
    exts: List[str] = []
    for p in parts:
        if not p.startswith("."):
            p = "." + p
        exts.append(p)
    return exts or [".mkv"]


def sort_key(path: Path) -> Tuple[int, int, int, str]:
    m = EP_RE.search(path.stem)
    if m:
        return (0, int(m.group("season")), int(m.group("episode")), path.as_posix().lower())
    return (1, 0, 0, path.as_posix().lower())


def scan_videos(video_dir: Path, exts: Iterable[str]) -> List[Path]:
    exts_lc = {e.lower() for e in exts}
    files: List[Path] = []
    for p in video_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts_lc:
            files.append(p)
    return sorted(files, key=sort_key)


def parse_ratio(raw: str) -> Tuple[int, int]:
    if "/" in raw:
        num, den = raw.split("/", 1)
        return int(num), int(den)
    return int(float(raw) * 1000), 1000


def parse_fps(value: str, default_num: int, default_den: int) -> Tuple[int, int]:
    if not value:
        return default_num, default_den
    raw = value.strip()
    if not raw:
        return default_num, default_den
    if "/" in raw:
        try:
            return parse_ratio(raw)
        except Exception:
            return default_num, default_den
    try:
        fps = float(raw)
    except ValueError:
        return default_num, default_den
    if fps <= 0:
        return default_num, default_den
    frac = Fraction(fps).limit_denominator(1001)
    return frac.numerator, frac.denominator




def format_time_ms(ms: int | None, force_hours: bool = False) -> str:
    if ms is None or ms < 0:
        return "--:--:--" if force_hours else "--:--"
    total = int(ms / 1000)
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    if force_hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def build_now_playing(title: str, cursor_ms: int | None, duration_ms: int | None) -> str:
    force_hours = False
    if cursor_ms and cursor_ms >= 3600 * 1000:
        force_hours = True
    if duration_ms and duration_ms >= 3600 * 1000:
        force_hours = True
    cur = format_time_ms(cursor_ms or 0, force_hours)
    dur = format_time_ms(duration_ms if duration_ms and duration_ms > 0 else -1, force_hours)
    return f"{title} {cur}/{dur}"


def maybe_update_text(ws, cfg, title: str, cursor_ms: int | None, duration_ms: int | None, cache: list[str | None]) -> None:
    text = build_now_playing(title, cursor_ms, duration_ms)
    if cache and cache[0] == text:
        return
    if cache:
        cache[0] = text
    update_text(ws, cfg, text)
def parse_kbps(value: str, default: int) -> int:
    if not value:
        return default
    raw = value.strip()
    if not raw:
        return default
    factor = 1
    if raw[-1] in {"k", "K"}:
        raw = raw[:-1]
    elif raw[-1] in {"m", "M"}:
        raw = raw[:-1]
        factor = 1000
    try:
        return int(float(raw) * factor)
    except ValueError:
        return default


def ffprobe_video_info(ffprobe: str, path: Path) -> Tuple[int, int, int, int]:
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate",
        "-of",
        "json",
        str(path),
    ]
    out = subprocess.check_output(cmd, text=True)
    data = json.loads(out)
    stream = data["streams"][0]
    width = int(stream["width"])
    height = int(stream["height"])
    fps_num, fps_den = parse_ratio(stream.get("r_frame_rate", "24/1"))
    return width, height, fps_num, fps_den


def title_for_path(path: Path) -> str:
    m = EP_RE.search(path.stem)
    if m:
        return f"S{m.group('season')}E{m.group('episode')}".upper()
    raw = path.stem
    first = re.match(r"[A-Za-z0-9]+", raw)
    if first:
        return first.group(0).upper()
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in raw)
    return safe[:64] if safe else "VIDEO"


def find_start_index(files: List[Path], start_ep: str) -> Optional[int]:
    if not start_ep:
        return None
    needle = start_ep.strip().upper()
    for i, p in enumerate(files):
        stem = p.stem.upper()
        if stem == needle or needle in stem:
            return i
    return None


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


class ObsClient:
    def __init__(self, host: str, port: int, password: str, timeout: float = 5.0):
        self._ws = ReqClient(host=host, port=port, password=password, timeout=timeout)

    def call(self, name: str, **kwargs):
        payload = kwargs or None
        return self._ws.send(name, payload, raw=True)


class Config:
    def __init__(self) -> None:
        self.vk_url = env_str("VK_URL", required=True)
        self.vk_key = env_str("VK_KEY", required=True)
        self.video_dir = Path(env_str("VIDEO_DIR", required=True)).expanduser().resolve()
        self.start_ep = env_str("START_EP", "")
        self.loop = env_bool("LOOP", True)
        self.ffprobe_path = env_str("FFPROBE_PATH", "ffprobe")
        self.video_exts = parse_exts(env_str("VIDEO_EXTS", ".mkv"))
        self.audio_index = env_int("AUDIO_INDEX", default=1)
        self.sub_si = env_int("SUB_SI", default=1)
        self.video_bitrate = env_str("STREAM_VIDEO_BITRATE", "3000k")
        self.audio_bitrate = env_str("STREAM_AUDIO_BITRATE", "160k")
        self.preset = env_str("STREAM_PRESET", "superfast")
        self.gop = env_int("STREAM_GOP", default=48)
        self.audio_rate = env_str("STREAM_AUDIO_RATE", "48000")
        self.audio_channels = env_int("STREAM_AUDIO_CHANNELS", default=2)
        self.output_width = env_int("OUTPUT_WIDTH", default=0)
        self.output_height = env_int("OUTPUT_HEIGHT", default=0)
        self.output_fps = env_str("OUTPUT_FPS", "")
        self.obs_host = env_str("OBS_HOST", "127.0.0.1")
        self.obs_port = env_int("OBS_PORT", default=4455)
        self.obs_password = env_str("OBS_PASSWORD", "", required=True)
        self.obs_scene = env_str("OBS_SCENE", "Scene")
        legacy_source = os.environ.get("OBS_VLC_SOURCE")
        self.obs_media_source = env_str("OBS_MEDIA_SOURCE", legacy_source or "Media")
        self.obs_text_source = env_str("OBS_TEXT_SOURCE", "NowPlaying")
        self.text_size = env_int('TEXT_SIZE', default=24)


def connect_obs(cfg: Config, retries: int = 90, delay: float = 1.0) -> ObsClient:
    last_err: Optional[Exception] = None
    for _ in range(retries):
        try:
            ws = ObsClient(cfg.obs_host, cfg.obs_port, cfg.obs_password)
            ws.call("GetVersion")
            return ws
        except Exception as exc:
            last_err = exc
            time.sleep(delay)
    raise RuntimeError(f"OBS websocket not reachable: {last_err}")


def ensure_scene(ws: ObsClient, scene_name: str) -> None:
    resp = ws.call("GetSceneList")
    scenes = resp.get("scenes", []) or []
    if not any(s.get("sceneName") == scene_name for s in scenes):
        ws.call("CreateScene", sceneName=scene_name)


def ensure_input(ws: ObsClient, scene_name: str, input_name: str, input_kind: str, input_settings: dict) -> None:
    resp = ws.call("GetInputList")
    inputs = resp.get("inputs", []) or []
    for item in inputs:
        if item.get("inputName") != input_name:
            continue
        existing_kind = item.get("inputKind")
        if existing_kind and existing_kind != input_kind:
            try:
                ws.call("RemoveInput", inputName=input_name)
            except Exception:
                pass
            for _ in range(10):
                time.sleep(0.2)
                resp = ws.call("GetInputList")
                inputs = resp.get("inputs", []) or []
                if not any(i.get("inputName") == input_name for i in inputs):
                    break
            break
        ws.call("SetInputSettings", inputName=input_name, inputSettings=input_settings, overlay=False)
        return
    ws.call(
        "CreateInput",
        sceneName=scene_name,
        inputName=input_name,
        inputKind=input_kind,
        inputSettings=input_settings,
        sceneItemEnabled=True,
    )


def pick_text_input_kind(ws: ObsClient) -> Optional[str]:
    candidates = ["text_ft2_source_v2", "text_ft2_source", "text_gdiplus", "text_source"]
    kinds = []
    try:
        resp = ws.call("GetInputKindList", unversioned=False)
        kinds = resp.get("inputKinds", []) or []
    except Exception:
        kinds = []
    for kind in candidates:
        if kind in kinds:
            return kind
    kinds2 = []
    try:
        resp = ws.call("GetInputKindList", unversioned=True)
        kinds2 = resp.get("inputKinds", []) or []
    except Exception:
        kinds2 = []
    for kind in candidates:
        if kind in kinds2:
            return kind
    for kind in kinds + kinds2:
        if "text" in kind.lower():
            return kind
    return None






def ensure_mpv_source(ws: ObsClient) -> str:
    kinds: list[str] = []
    try:
        resp = ws.call("GetInputKindList", unversioned=False)
        kinds.extend(resp.get("inputKinds", []) or [])
    except Exception:
        pass
    try:
        resp = ws.call("GetInputKindList", unversioned=True)
        kinds.extend(resp.get("inputKinds", []) or [])
    except Exception:
        pass
    if "mpvs_source" not in kinds:
        raise RuntimeError("mpvs_source input kind not available. Install obs-mpv plugin.")
    return "mpvs_source"


def set_scene_item_pos(ws: ObsClient, scene_name: str, source_name: str, x: float, y: float) -> None:
    resp = ws.call("GetSceneItemId", sceneName=scene_name, sourceName=source_name)
    item_id = resp.get("sceneItemId")
    if item_id is None:
        return
    ws.call(
        "SetSceneItemTransform",
        sceneName=scene_name,
        sceneItemId=item_id,
        sceneItemTransform={"positionX": x, "positionY": y},
    )




def bring_scene_item_to_top(ws: ObsClient, scene_name: str, source_name: str) -> None:
    try:
        resp = ws.call("GetSceneItemList", sceneName=scene_name)
    except Exception:
        return
    items = resp.get("sceneItems", []) or []
    target_id = None
    max_index = -1
    for item in items:
        idx = item.get("sceneItemIndex")
        if isinstance(idx, int) and idx > max_index:
            max_index = idx
        if item.get("sourceName") == source_name:
            target_id = item.get("sceneItemId")
    if target_id is None or max_index < 0:
        return
    try:
        ws.call(
            "SetSceneItemIndex",
            sceneName=scene_name,
            sceneItemId=target_id,
            sceneItemIndex=max_index,
        )
    except Exception:
        pass
def _format_keyframe_interval(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _gop_to_seconds(gop: int, fps_num: int, fps_den: int) -> Optional[float]:
    if gop <= 0:
        return None
    if gop <= 10:
        return float(gop)
    if fps_num > 0 and fps_den > 0:
        return gop / (fps_num / fps_den)
    return float(gop)


def _set_profile_param(ws: ObsClient, category: str, name: str, value: str) -> bool:
    try:
        ws.call(
            "SetProfileParameter",
            parameterCategory=category,
            parameterName=name,
            parameterValue=value,
        )
        return True
    except Exception:
        return False


def configure_output(ws: ObsClient, cfg: Config, fps_num: int, fps_den: int) -> None:
    v_kbps = parse_kbps(cfg.video_bitrate, 2500)
    a_kbps = parse_kbps(cfg.audio_bitrate, 160)
    preset = cfg.preset or "veryfast"
    try:
        ws.call(
            "SetProfileParameter",
            parameterCategory="SimpleOutput",
            parameterName="VBitrate",
            parameterValue=str(v_kbps),
        )
        ws.call(
            "SetProfileParameter",
            parameterCategory="SimpleOutput",
            parameterName="ABitrate",
            parameterValue=str(a_kbps),
        )
        ws.call(
            "SetProfileParameter",
            parameterCategory="SimpleOutput",
            parameterName="Preset",
            parameterValue=preset,
        )
        gop_sec = _gop_to_seconds(cfg.gop, fps_num, fps_den)
        if gop_sec:
            gop_value = _format_keyframe_interval(gop_sec)
            ok = False
            for category, name in (
                ("AdvOut", "KeyframeInterval"),
                ("SimpleOutput", "KeyframeInterval"),
                ("Output", "KeyframeInterval"),
            ):
                if _set_profile_param(ws, category, name, gop_value):
                    ok = True
                    break
            if ok:
                log(
                    "Output settings: preset=%s, v_bitrate=%sk, a_bitrate=%sk, keyint=%ss (STREAM_GOP=%s)"
                    % (preset, v_kbps, a_kbps, gop_value, cfg.gop)
                )
            else:
                log(
                    "Output settings: preset=%s, v_bitrate=%sk, a_bitrate=%sk (keyint not applied; STREAM_GOP=%s)"
                    % (preset, v_kbps, a_kbps, cfg.gop)
                )
        else:
            log(f"Output settings: preset={preset}, v_bitrate={v_kbps}k, a_bitrate={a_kbps}k")
    except Exception as exc:
        log(f"WARN: failed to set output params: {exc}")


def configure_stream(ws: ObsClient, cfg: Config) -> None:
    ws.call(
        "SetStreamServiceSettings",
        streamServiceType="rtmp_custom",
        streamServiceSettings={"server": cfg.vk_url, "key": cfg.vk_key},
    )


def ensure_streaming(ws: ObsClient) -> None:
    resp = ws.call("GetStreamStatus")
    if not resp.get("outputActive", False):
        ws.call("StartStream")


def build_media_settings(cfg: Config, playlist: list[Path]) -> dict:
    return {
        "playlist": [{"value": str(p), "hidden": False} for p in playlist],
        "loop": False,
        "shuffle": False,
        "audio_track": cfg.audio_index,
        "sub_track": cfg.sub_si,
        "video_track": 1,
    }


def update_text(ws: ObsClient, cfg: Config, title: str) -> None:
    settings = {
        "text": title,
        "font": {"face": "DejaVu Sans", "size": cfg.text_size, "style": "Regular"},
        "color1": 4294967295,
        "outline": True,
        "outline_size": 2,
        "outline_color": 4278190080,
    }
    ws.call("SetInputSettings", inputName=cfg.obs_text_source, inputSettings=settings, overlay=False)


def wait_for_media_end(ws: ObsClient, input_name: str, stop_flag, on_tick=None) -> int:
    seen_playing = False
    start_ts = time.time()
    while not stop_flag():
        resp = ws.call("GetMediaInputStatus", inputName=input_name)
        if on_tick:
            try:
                on_tick(resp)
            except Exception:
                pass
        state = resp.get("mediaState", "")
        if state == "OBS_MEDIA_STATE_ERROR":
            return 2
        if state in {"OBS_MEDIA_STATE_PLAYING", "OBS_MEDIA_STATE_PAUSED"}:
            seen_playing = True
        if seen_playing:
            if state in {"OBS_MEDIA_STATE_ENDED", "OBS_MEDIA_STATE_STOPPED"}:
                return 0
        else:
            if time.time() - start_ts > 15:
                return 0
        time.sleep(1)
    return 0


def main() -> int:
    load_env(Path.cwd() / ".env")

    try:
        cfg = Config()
    except Exception as exc:
        log(f"Config error: {exc}")
        return 2

    if not cfg.video_dir.exists():
        log(f"VIDEO_DIR does not exist: {cfg.video_dir}")
        return 2

    files = scan_videos(cfg.video_dir, cfg.video_exts)
    if not files:
        log("No video files found.")
        return 2

    width, height, fps_num, fps_den = ffprobe_video_info(cfg.ffprobe_path, files[0])

    ws = connect_obs(cfg)
    stop = False

    def handle(_sig: int, _frame) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)

    ensure_scene(ws, cfg.obs_scene)

    media_kind = ensure_mpv_source(ws)
    media_settings = build_media_settings(cfg, [])
    ensure_input(ws, cfg.obs_scene, cfg.obs_media_source, media_kind, media_settings)

    text_kind = pick_text_input_kind(ws)
    text_enabled = False
    if text_kind:
        text_settings = {
            "text": title_for_path(files[0]),
            "font": {"face": "DejaVu Sans", "size": cfg.text_size, "style": "Regular"},
            "color1": 4294967295,
            "outline": True,
            "outline_size": 2,
            "outline_color": 4278190080,
        }
        try:
            ensure_input(ws, cfg.obs_scene, cfg.obs_text_source, text_kind, text_settings)
            set_scene_item_pos(ws, cfg.obs_scene, cfg.obs_text_source, 10, 10)
            bring_scene_item_to_top(ws, cfg.obs_scene, cfg.obs_text_source)
            text_enabled = True
        except Exception as exc:
            log(f"WARN: failed to create text source ({text_kind}): {exc}")
    else:
        log("WARN: no text input kind available; text overlay disabled")

    out_width = cfg.output_width or width
    out_height = cfg.output_height or height
    fps_out_num, fps_out_den = parse_fps(cfg.output_fps, fps_num, fps_den)

    ws.call(
        "SetVideoSettings",
        baseWidth=width,
        baseHeight=height,
        outputWidth=out_width,
        outputHeight=out_height,
        fpsNumerator=fps_out_num,
        fpsDenominator=fps_out_den,
    )

    configure_output(ws, cfg, fps_out_num, fps_out_den)
    configure_stream(ws, cfg)
    ensure_streaming(ws)

    start_idx = find_start_index(files, cfg.start_ep)
    if cfg.start_ep and start_idx is None:
        log(f"WARN: START_EP not found: {cfg.start_ep}")
        start_idx = 0

    order = files
    if start_idx:
        order = files[start_idx:] + files[:start_idx]

    # Load full playlist once (mpv will advance automatically)
    ws.call(
        "SetInputSettings",
        inputName=cfg.obs_media_source,
        inputSettings=build_media_settings(cfg, order),
        overlay=False,
    )

    current_idx = 0
    current_title = title_for_path(order[current_idx])
    cache = [None]
    prev_cursor = None

    if text_enabled:
        maybe_update_text(ws, cfg, current_title, 0, 0, cache)

    try:
        while not stop:
            resp = ws.call("GetMediaInputStatus", inputName=cfg.obs_media_source)
            state = resp.get("mediaState", "")
            cursor = resp.get("mediaCursor")
            duration = resp.get("mediaDuration")

            if text_enabled:
                maybe_update_text(ws, cfg, current_title, cursor, duration, cache)

            if state == "OBS_MEDIA_STATE_ERROR":
                return 2

            # Detect file switch by cursor reset
            if prev_cursor is not None and cursor is not None and cursor + 2000 < prev_cursor:
                current_idx += 1
                if current_idx >= len(order):
                    if cfg.loop:
                        current_idx = 0
                        try:
                            ws.call(
                                "TriggerMediaInputAction",
                                inputName=cfg.obs_media_source,
                                mediaAction="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART",
                            )
                        except Exception:
                            pass
                    else:
                        break
                current_title = title_for_path(order[current_idx])
                cache[0] = None
                if text_enabled:
                    maybe_update_text(ws, cfg, current_title, 0, 0, cache)

            if state in {"OBS_MEDIA_STATE_ENDED", "OBS_MEDIA_STATE_STOPPED"} and not cfg.loop and current_idx >= len(order) - 1:
                break

            if cursor is not None:
                prev_cursor = cursor
            time.sleep(1)
    finally:
        try:
            if ws.call("GetStreamStatus").get("outputActive", False):
                ws.call("StopStream")
        except Exception:
            pass

        try:
            if ws.call("GetStreamStatus").get("outputActive", False):
                ws.call("StopStream")
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
