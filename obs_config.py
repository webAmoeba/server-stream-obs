#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
from pathlib import Path


def apply_tree(src_root: Path, dest_root: Path) -> None:
    for path in src_root.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(src_root)
        target = dest_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def main() -> int:
    repo_root = Path(__file__).resolve().parent
    template_root = repo_root / "config" / "obs"
    if not template_root.exists():
        print(f"Config template not found: {template_root}")
        return 2

    config_root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    obs_root = config_root / "obs-studio"
    obs_root.mkdir(parents=True, exist_ok=True)

    apply_tree(template_root, obs_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
