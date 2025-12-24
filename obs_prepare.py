#!/usr/bin/env python3
from __future__ import annotations

import configparser
import json
import os
from pathlib import Path


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


def write_ini_no_spaces(parser: configparser.RawConfigParser, path: Path) -> None:
    lines: list[str] = []
    for section in parser.sections():
        lines.append(f"[{section}]")
        for key, val in parser.items(section):
            lines.append(f"{key}={val}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    load_env(Path.cwd() / ".env")

    port = int(os.environ.get("OBS_PORT", "4455") or "4455")
    password = os.environ.get("OBS_PASSWORD", "")
    if not password:
        print("OBS_PASSWORD is required in .env")
        return 2

    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    config_dir = config_root / "obs-studio"
    config_dir.mkdir(parents=True, exist_ok=True)
    global_ini = config_dir / "global.ini"

    parser = configparser.RawConfigParser(strict=False)
    parser.optionxform = str
    if global_ini.exists():
        parser.read(global_ini)

    def ensure(section: str, items: dict) -> None:
        if section not in parser:
            parser[section] = {}
        parser[section].update(items)

    enabled = "true"
    first_load = "false"
    auth_required = "true"

    ensure(
        "OBSWebSocket",
        {
            "ServerEnabled": enabled,
            "ServerPort": str(port),
            "ServerPassword": password,
            "AuthRequired": auth_required,
            "AlertsEnabled": "false",
            "FirstLoad": first_load,
        },
    )
    ensure(
        "WebSocketServer",
        {
            "ServerEnabled": enabled,
            "ServerPort": str(port),
            "ServerPassword": password,
            "AuthRequired": auth_required,
            "AlertsEnabled": "false",
            "FirstLoad": first_load,
        },
    )
    ensure(
        "WebSocket",
        {
            "ServerEnabled": enabled,
            "ServerPort": str(port),
            "ServerPassword": password,
            "FirstLoad": first_load,
        },
    )
    ensure(
        "obs-websocket",
        {
            "server_enabled": enabled,
            "server_port": str(port),
            "server_password": password,
            "auth_required": auth_required,
            "first_load": first_load,
        },
    )

    write_ini_no_spaces(parser, global_ini)

    obsws_payload = {
        "server_enabled": True,
        "server_port": port,
        "auth_required": True,
        "first_load": False,
        "server_password": password,
        "ServerEnabled": True,
        "ServerPort": port,
        "AuthRequired": True,
        "FirstLoad": False,
        "ServerPassword": password,
    }

    candidate_dirs = [
        config_dir / "plugin_config" / "obs-websocket",
        config_dir / "obs-websocket",
        config_dir / "config" / "obs-websocket",
    ]
    for obsws_dir in candidate_dirs:
        obsws_dir.mkdir(parents=True, exist_ok=True)
        with (obsws_dir / "config.json").open("w", encoding="utf-8") as fh:
            json.dump(obsws_payload, fh, ensure_ascii=False, indent=2)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
