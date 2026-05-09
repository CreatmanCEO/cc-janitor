from __future__ import annotations

import json
import subprocess
import sys
import time
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


@dataclass
class HookRunResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


STDIN_TEMPLATES: dict[str, dict] = {
    "PreToolUse": {
        "session_id": "sim-001",
        "transcript_path": "/tmp/x.jsonl",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
    },
    "PostToolUse": {
        "session_id": "sim-001",
        "transcript_path": "/tmp/x.jsonl",
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
        "tool_response": {"stdout": "hi"},
    },
    "UserPromptSubmit": {
        "session_id": "sim-001",
        "hook_event_name": "UserPromptSubmit",
        "user_prompt": "hello",
    },
    "Stop": {"session_id": "sim-001", "hook_event_name": "Stop"},
    "SubagentStop": {"session_id": "sim-001", "hook_event_name": "SubagentStop"},
    "Notification": {
        "session_id": "sim-001",
        "hook_event_name": "Notification",
        "message": "test",
    },
    "SessionStart": {"session_id": "sim-001", "hook_event_name": "SessionStart"},
    "SessionEnd": {"session_id": "sim-001", "hook_event_name": "SessionEnd"},
    "PreCompact": {"session_id": "sim-001", "hook_event_name": "PreCompact"},
}


def build_stdin_payload(event: str, **overrides) -> str:
    tpl = dict(STDIN_TEMPLATES.get(event, {"hook_event_name": event}))
    tpl.update(overrides)
    return json.dumps(tpl, indent=2)


def simulate_hook(
    command: str,
    *,
    event: str,
    matcher: str = "*",
    timeout: int = 30,
    stdin_override: str | None = None,
) -> HookRunResult:
    payload = stdin_override or build_stdin_payload(event, tool_name=matcher)
    if sys.platform == "win32":
        args = ["powershell.exe", "-NoProfile", "-Command", command]
    else:
        args = ["sh", "-c", command]
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            args,
            input=payload.encode("utf-8"),
            capture_output=True,
            timeout=timeout,
        )
        return HookRunResult(
            exit_code=proc.returncode,
            stdout=proc.stdout.decode("utf-8", errors="replace"),
            stderr=proc.stderr.decode("utf-8", errors="replace"),
            duration_ms=int((time.perf_counter() - start) * 1000),
        )
    except subprocess.TimeoutExpired:
        return HookRunResult(124, "", f"timeout after {timeout}s", timeout * 1000)


import base64

from .safety import require_confirmed

SENTINEL = "cc-janitor-original:"


def _log_path_for(event: str) -> Path:
    return get_paths().hooks_log / f"{event}.log"


def _wrap_posix(orig: str, log_p: Path) -> str:
    encoded = base64.b64encode(orig.encode("utf-8")).decode("ascii")
    return f"# {SENTINEL} {encoded}\n({orig}) 2>&1 | tee -a '{log_p.as_posix()}'"


def _wrap_powershell(orig: str, log_p: Path) -> str:
    encoded = base64.b64encode(orig.encode("utf-8")).decode("ascii")
    return (
        f"# {SENTINEL} {encoded}\n"
        f"({orig}) 2>&1 | Tee-Object -FilePath '{log_p.as_posix()}' -Append"
    )


def _unwrap(wrapped: str) -> str | None:
    for line in wrapped.splitlines():
        if SENTINEL in line:
            encoded = line.split(SENTINEL, 1)[1].strip()
            try:
                return base64.b64decode(encoded.encode("ascii")).decode("utf-8")
            except Exception:
                return None
    return None


def _modify_hook_command(event: str, matcher: str, transform) -> Path:
    require_confirmed()
    settings = get_paths().home.parent / ".claude" / "settings.json"
    data = (
        json.loads(settings.read_text(encoding="utf-8"))
        if settings.exists()
        else {}
    )
    pre = data.setdefault("hooks", {}).setdefault(event, [])
    for entry in pre:
        if entry.get("matcher") != matcher:
            continue
        for h in entry.get("hooks", []):
            cmd = h.get("command")
            if not cmd:
                continue
            new_cmd = transform(cmd)
            if new_cmd is not None:
                h["command"] = new_cmd
    settings.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return settings


def enable_logging(event: str, *, matcher: str = "*") -> Path:
    log_p = _log_path_for(event)
    log_p.parent.mkdir(parents=True, exist_ok=True)
    wrap = _wrap_powershell if sys.platform == "win32" else _wrap_posix
    return _modify_hook_command(event, matcher, lambda cmd: wrap(cmd, log_p))


def disable_logging(event: str, *, matcher: str = "*") -> Path:
    return _modify_hook_command(event, matcher, _unwrap)
