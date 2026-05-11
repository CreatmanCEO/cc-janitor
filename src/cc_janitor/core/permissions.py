from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from .monorepo import classify_location, discover_locations
from .safety import require_confirmed
from .state import get_paths

Scope = Literal["user", "user-local", "project", "project-local", "managed", "approved-tools"]


def _normalize_scope(scope: str | None) -> tuple[str, ...] | None:
    """Return the set of acceptable monorepo scope_kind values, or None to allow all."""
    if scope is None or scope == "all":
        return None
    if scope == "real+nested":
        return ("real", "nested")
    if scope in ("real", "nested", "junk"):
        return (scope,)
    # Treat as a concrete path filter — caller will compare full path
    return None


def _classify_source_path(path: Path) -> str:
    """Classify a settings file by its enclosing .claude/ directory.

    The user's global ~/.claude/ and ~/.claude/projects/<id>/.claude/ are treated
    as "real" — these are canonical Claude Code locations, not monorepo discoveries.
    """
    claude_dir = None
    for parent in path.parents:
        if parent.name == ".claude":
            claude_dir = parent
            break
    if claude_dir is None:
        return "real"
    home = Path.home()
    try:
        rel = claude_dir.relative_to(home)
        # ~/.claude or ~/.claude/projects/<id>/.claude are canonical
        if rel.parts and rel.parts[0] == ".claude":
            return "real"
    except ValueError:
        pass
    try:
        return classify_location(claude_dir).scope_kind
    except Exception:
        return "real"


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


def _monorepo_settings_files() -> list[tuple[Path, Scope]]:
    """Settings files from discovered monorepo .claude/ locations under cwd."""
    out: list[tuple[Path, Scope]] = []
    try:
        locs = discover_locations(include_junk=True)
    except Exception:
        return out
    for loc in locs:
        for fname, scope in (
            ("settings.json", "project"),
            ("settings.local.json", "project-local"),
        ):
            p = loc.path / fname
            if p.exists():
                out.append((p, scope))
    return out


def discover_rules(scope: str | None = None) -> list[PermRule]:
    """Discover permission rules across all sources.

    ``scope`` filters by the enclosing .claude/ directory's monorepo
    classification: ``"real" | "nested" | "junk" | "real+nested" | "all"``
    (or ``None`` for all). Concrete path strings filter to a single source.
    """
    out: list[PermRule] = []
    # 5 standard settings layers + monorepo discoveries
    sources: list[tuple[Path, Scope]] = list(_settings_files())
    seen_paths = {p for p, _ in sources}
    for p, s in _monorepo_settings_files():
        if p not in seen_paths:
            sources.append((p, s))
            seen_paths.add(p)

    for path, scope_label in sources:
        d = _read_json(path)
        if not d:
            continue
        perms = (d or {}).get("permissions", {}) or {}
        src = PermSource(path=path, scope=scope_label)
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

    # Apply scope filter
    if scope is None or scope == "all":
        return out
    allowed_kinds = _normalize_scope(scope)
    if allowed_kinds is not None:
        out = [r for r in out if _classify_source_path(r.source.path) in allowed_kinds]
    else:
        # Concrete path: keep rules whose source path lives under that dir
        try:
            target = Path(scope).resolve()
            out = [
                r for r in out
                if target in r.source.path.resolve().parents
                or r.source.path.resolve() == target
            ]
        except (OSError, ValueError):
            pass
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
    now = datetime.now(UTC)
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


@dataclass
class PermDup:
    kind: Literal["subsumed", "exact", "conflict", "empty"]
    rules: list[PermRule]
    suggestion: str


def _pattern_subsumes(broad: str, narrow: str) -> bool:
    """True iff `broad` matches `narrow` as a literal AND broad != narrow."""
    if broad == narrow or broad == "":
        return False
    return fnmatch.fnmatchcase(narrow, broad)


def find_duplicates(rules: list[PermRule]) -> list[PermDup]:
    """Detect 4 kinds of duplication: empty, exact, subsumed, conflict.

    - **empty**: rule body like ``Bash()`` (no pattern).
    - **exact**: same (tool, pattern, decision) across multiple sources.
    - **subsumed**: same tool/decision, broader pattern fully covers narrower.
    - **conflict**: allow vs deny with overlapping patterns (warn only — never auto-fix).
    """
    out: list[PermDup] = []

    # 1) empty
    for r in rules:
        if r.tool and not r.pattern.strip() and r.raw.endswith("()"):
            out.append(PermDup(
                kind="empty", rules=[r],
                suggestion=f"Remove empty rule {r.raw} from {r.source.path}",
            ))

    # group by tool for the rest
    by_tool: dict[str, list[PermRule]] = {}
    for r in rules:
        by_tool.setdefault(r.tool, []).append(r)

    for tool, group in by_tool.items():
        # 2) exact duplicates by (pattern, decision)
        seen: dict[tuple[str, str], list[PermRule]] = {}
        for r in group:
            seen.setdefault((r.pattern, r.decision), []).append(r)
        for (pat, dec), rs in seen.items():
            if len(rs) > 1:
                out.append(PermDup(
                    kind="exact", rules=rs,
                    suggestion=(
                        f"Same rule ({tool}({pat}), {dec}) appears in "
                        f"{len(rs)} sources — keep one."
                    ),
                ))

        # 3) subsumed: same decision=allow, broad covers narrow
        allows = [r for r in group if r.decision == "allow"]
        for broad in allows:
            for narrow in allows:
                if broad is narrow:
                    continue
                if not broad.pattern or not narrow.pattern:
                    continue
                if _pattern_subsumes(broad.pattern, narrow.pattern):
                    out.append(PermDup(
                        kind="subsumed", rules=[broad, narrow],
                        suggestion=(
                            f"{tool}({broad.pattern}) already covers "
                            f"{tool}({narrow.pattern})"
                        ),
                    ))

        # 4) conflict: allow + deny with overlapping patterns
        denies = [r for r in group if r.decision == "deny"]
        for a in allows:
            for d in denies:
                if (a.pattern == d.pattern
                        or _pattern_subsumes(a.pattern, d.pattern)
                        or _pattern_subsumes(d.pattern, a.pattern)):
                    out.append(PermDup(
                        kind="conflict", rules=[a, d],
                        suggestion="Allow vs deny overlap — review manually, do not auto-fix.",
                    ))

    return out


def _backup(path: Path) -> Path:
    """Copy ``path`` into ~/.cc-janitor/backups/<sha1-of-path>/<basename>.<ts>.bak."""
    paths = get_paths()
    paths.ensure_dirs()
    h = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
    bucket = paths.backups / h
    bucket.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    dst = bucket / f"{path.name}.{ts}.bak"
    shutil.copy2(path, dst)
    return dst


def _read_settings(path: Path) -> dict:
    """Read JSON settings, returning empty dict on missing or malformed."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_settings(path: Path, data: dict) -> None:
    """Write JSON with 2-space indent + trailing newline (Claude Code convention)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def remove_rule(rule: PermRule) -> None:
    """Delete a rule from its source file. Requires CC_JANITOR_USER_CONFIRMED=1."""
    require_confirmed()
    path = rule.source.path
    if not path.exists():
        raise FileNotFoundError(path)
    _backup(path)

    if rule.source.scope == "approved-tools":
        d = _read_settings(path)
        arr = d.get("approvedTools") or []
        d["approvedTools"] = [x for x in arr if x != rule.raw]
        _write_settings(path, d)
        return

    d = _read_settings(path)
    perms = d.setdefault("permissions", {})
    arr = perms.get(rule.decision) or []
    perms[rule.decision] = [x for x in arr if x != rule.raw]
    _write_settings(path, d)


def add_rule(raw: str, *, scope: str, decision: str = "allow") -> None:
    """Add a new rule string to the file matching ``scope``. Creates file if missing."""
    require_confirmed()
    candidates = [(p, s) for p, s in _settings_files() if s == scope]
    if not candidates:
        raise ValueError(f"No file for scope {scope}")
    path, _ = candidates[0]
    if path.exists():
        _backup(path)
    d = _read_settings(path)
    if scope == "approved-tools":
        d.setdefault("approvedTools", []).append(raw)
    else:
        d.setdefault("permissions", {}).setdefault(decision, []).append(raw)
    _write_settings(path, d)
