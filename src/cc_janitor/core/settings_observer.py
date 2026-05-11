from __future__ import annotations

import json
from pathlib import Path

from .audit import AuditLog
from .state import get_paths


def _cache_path() -> Path:
    state_dir = get_paths().home / "state"
    return state_dir / "autodream-last-seen.json"


def _claude_settings() -> Path:
    return Path.home() / ".claude" / "settings.json"


def observe_autodream_change() -> tuple[bool, bool] | None:
    """Detect changes to ~/.claude/settings.json:autoDreamEnabled.

    Returns (old, new) if the flag has flipped since the last observation,
    else None. On first observation, seeds the cache and returns None.

    Writes an audit-log entry (cmd=``settings-observe``, mode=``observer``)
    on every detected flip so users can grep the audit log for
    autoDreamEnabled toggles.
    """
    s = _claude_settings()
    if not s.exists():
        return None
    try:
        current = bool(
            json.loads(s.read_text(encoding="utf-8")).get(
                "autoDreamEnabled", False
            )
        )
    except (OSError, json.JSONDecodeError):
        return None
    cache = _cache_path()
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists():
        cache.write_text(
            json.dumps({"autoDreamEnabled": current}), encoding="utf-8"
        )
        return None
    try:
        prev = bool(
            json.loads(cache.read_text(encoding="utf-8")).get(
                "autoDreamEnabled", False
            )
        )
    except (OSError, json.JSONDecodeError):
        prev = current
    if prev == current:
        return None
    cache.write_text(
        json.dumps({"autoDreamEnabled": current}), encoding="utf-8"
    )
    log = AuditLog(get_paths().audit_log)
    log.record(
        mode="observer",
        user_confirmed=False,
        cmd="settings-observe",
        args=[],
        exit_code=0,
        changed={
            "key": "autoDreamEnabled",
            "old": prev,
            "new": current,
            "source": str(s),
        },
    )
    return (prev, current)
