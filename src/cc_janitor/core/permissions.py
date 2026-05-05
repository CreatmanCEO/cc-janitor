from __future__ import annotations
import fnmatch
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal


Scope = Literal["user", "user-local", "project", "project-local", "managed", "approved-tools"]


@dataclass(frozen=True)
class PermSource:
    path: Path
    scope: Scope


@dataclass
class PermRule:
    tool: str
    pattern: str
    decision: Literal["allow", "deny", "ask"]
    source: PermSource
    raw: str = ""
    last_matched_at: datetime | None = None
    match_count_30d: int = 0
    match_count_90d: int = 0
    stale: bool = False


_RULE_RE = re.compile(r"^([A-Za-z]+)(?:\(([^)]*)\))?$")


def parse_rule(raw: str, *, decision: str = "allow", source: PermSource) -> PermRule | None:
    m = _RULE_RE.match(raw.strip())
    if not m:
        return None
    return PermRule(
        tool=m.group(1),
        pattern=(m.group(2) or "").strip(),
        decision=decision,  # type: ignore[arg-type]
        source=source,
        raw=raw,
    )


def _user_home() -> Path:
    return Path.home()


def _settings_files() -> list[tuple[Path, Scope]]:
    home = _user_home()
    out: list[tuple[Path, Scope]] = []
    out.append((home / ".claude" / "settings.json", "user"))
    out.append((home / ".claude" / "settings.local.json", "user-local"))
    proj_root = home / ".claude" / "projects"
    if proj_root.exists():
        for proj in proj_root.iterdir():
            if not proj.is_dir():
                continue
            sd = proj / ".claude"
            out.append((sd / "settings.json", "project"))
            out.append((sd / "settings.local.json", "project-local"))
    return out


def _read_json(p: Path) -> dict | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def discover_rules() -> list[PermRule]:
    out: list[PermRule] = []
    # 5 settings layers
    for path, scope in _settings_files():
        d = _read_json(path)
        if not d:
            continue
        perms = (d or {}).get("permissions", {}) or {}
        src = PermSource(path=path, scope=scope)
        for kind in ("allow", "deny", "ask"):
            for raw in perms.get(kind, []) or []:
                r = parse_rule(raw, decision=kind, source=src)
                if r:
                    out.append(r)
    # ~/.claude.json approvedTools
    cj = _user_home() / ".claude.json"
    d = _read_json(cj)
    if d:
        src = PermSource(path=cj, scope="approved-tools")
        for raw in (d.get("approvedTools") or []):
            r = parse_rule(raw, decision="allow", source=src)
            if r:
                out.append(r)
    return out


def _iter_tool_uses(jsonl: Path):
    """Yield (tool_name, input, timestamp) tuples for every tool_use block."""
    if not jsonl.exists():
        return
    with jsonl.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            content = (m.get("message") or {}).get("content")
            ts = m.get("timestamp")
            try:
                t = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
            except (ValueError, AttributeError):
                t = None
            if isinstance(content, list):
                for blk in content:
                    if isinstance(blk, dict) and blk.get("type") == "tool_use":
                        yield blk.get("name"), blk.get("input") or {}, t


def _match_command(pattern: str, command: str) -> bool:
    """fnmatch-based glob with empty pattern == match-anything semantics."""
    if pattern == "":
        return True
    return fnmatch.fnmatchcase(command, pattern)


def analyze_usage(
    rules: list[PermRule],
    sessions,
    *,
    stale_after_days: int = 90,
) -> list[PermRule]:
    """Match transcript tool_use against rules; populate match counts + stale flag.

    Mutates and returns the same rules list.
    """
    now = datetime.now(timezone.utc)
    cutoff_30 = now - timedelta(days=30)
    cutoff_stale = now - timedelta(days=stale_after_days)

    for s in sessions:
        for tool_name, inp, ts in _iter_tool_uses(s.jsonl_path):
            target = inp.get("command") or inp.get("file_path") or ""
            if not isinstance(target, str):
                continue
            for r in rules:
                if r.tool != tool_name:
                    continue
                if not _match_command(r.pattern, target):
                    continue
                effective_ts = ts if ts is not None else now
                if r.last_matched_at is None or effective_ts > r.last_matched_at:
                    r.last_matched_at = effective_ts
                if effective_ts >= cutoff_30:
                    r.match_count_30d += 1
                if effective_ts >= cutoff_stale:
                    r.match_count_90d += 1

    for r in rules:
        r.stale = r.match_count_90d == 0
    return rules
