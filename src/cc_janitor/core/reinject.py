from __future__ import annotations

from pathlib import Path

from .safety import require_confirmed
from .state import get_paths


def _marker_path() -> Path:
    return get_paths().home / "reinject-pending"


def queue_reinject(*, memory: bool = True, claude_md: bool = True) -> Path:
    require_confirmed()
    paths = get_paths()
    paths.ensure_dirs()
    marker = _marker_path()
    flags = []
    if memory:
        flags.append("memory")
    if claude_md:
        flags.append("claude_md")
    marker.write_text(",".join(flags) + "\n", encoding="utf-8")
    return marker


def is_reinject_pending() -> bool:
    return _marker_path().exists()


def clear_reinject() -> None:
    p = _marker_path()
    if p.exists():
        p.unlink()
