"""Daemon entry-point. Spawned by `cc-janitor watch start`."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from . import watcher


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args()
    raw = os.environ.get("CC_JANITOR_WATCH_DIRS", "")
    dirs = [Path(p) for p in raw.split(os.pathsep) if p]
    watcher.run_watcher(dirs, args.interval)


if __name__ == "__main__":
    main()
