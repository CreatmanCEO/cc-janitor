from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .state import get_paths

HookEvent = str  # "PreToolUse", "PostToolUse", ...
HookScope = Literal["user", "user-local", "project", "project-local", "managed"]


@dataclass
class HookEntry:
    event: HookEvent
    matcher: str
    type: Literal["command", "url", "subagent"]
    command: str | None
    url: str | None
    timeout: int | None
    source_path: Path
    source_scope: HookScope
    has_logging_wrapper: bool = False


@dataclass
class HookIssue:
    kind: Literal[
        "missing-hooks-array",
        "empty-matcher",
        "empty-command",
        "type-mismatch",
        "invalid-json",
    ]
    source_path: Path
    detail: str


def _settings_sources() -> list[tuple[Path, HookScope]]:
    home = get_paths().home.parent
    cwd = Path.cwd()
    return [
        (home / ".claude" / "settings.json", "user"),
        (home / ".claude" / "settings.local.json", "user-local"),
        (cwd / ".claude" / "settings.json", "project"),
        (cwd / ".claude" / "settings.local.json", "project-local"),
    ]


def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def discover_hooks() -> list[HookEntry]:
    out: list[HookEntry] = []
    for path, scope in _settings_sources():
        data = _load(path)
        if not isinstance(data, dict):
            continue
        hooks_block = data.get("hooks") or {}
        if not isinstance(hooks_block, dict):
            continue
        for event, entries in hooks_block.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                matcher = entry.get("matcher", "*")
                inner = entry.get("hooks")
                if not isinstance(inner, list):
                    continue  # malformed; surfaced via validate_hooks()
                for h in inner:
                    if not isinstance(h, dict):
                        continue
                    cmd = h.get("command")
                    out.append(
                        HookEntry(
                            event=event,
                            matcher=matcher,
                            type=h.get("type", "command"),
                            command=cmd,
                            url=h.get("url"),
                            timeout=h.get("timeout"),
                            source_path=path,
                            source_scope=scope,
                            has_logging_wrapper=bool(
                                cmd and "cc-janitor/hooks-log/" in cmd
                            ),
                        )
                    )
    return out


def validate_hooks() -> list[HookIssue]:
    issues: list[HookIssue] = []
    for path, _scope in _settings_sources():
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            issues.append(HookIssue("invalid-json", path, str(e)))
            continue
        hooks_block = data.get("hooks") or {}
        if not isinstance(hooks_block, dict):
            continue
        for event, entries in hooks_block.items():
            if not isinstance(entries, list):
                issues.append(
                    HookIssue("type-mismatch", path, f"{event} must be a list")
                )
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    issues.append(
                        HookIssue(
                            "type-mismatch", path, f"{event} entry not an object"
                        )
                    )
                    continue
                if "hooks" not in entry or not isinstance(entry.get("hooks"), list):
                    issues.append(
                        HookIssue(
                            "missing-hooks-array",
                            path,
                            f"{event} entry missing 'hooks' array",
                        )
                    )
                    continue
                for h in entry["hooks"]:
                    if not isinstance(h, dict):
                        issues.append(
                            HookIssue("type-mismatch", path, "hook not object")
                        )
                        continue
                    if h.get("type") == "command" and not h.get("command"):
                        issues.append(
                            HookIssue(
                                "empty-command",
                                path,
                                f"{event}/{entry.get('matcher', '*')}",
                            )
                        )
    return issues
