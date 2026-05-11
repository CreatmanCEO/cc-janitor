from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

ScopeKind = Literal["real", "nested", "junk"]

SKIP_DIRS: set[str] = {
    "node_modules", ".venv", "venv", ".git", "__pycache__",
    "dist", "build", ".next", ".tox", "target", "out",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
}

PROJECT_MARKERS: tuple[str, ...] = (
    "pyproject.toml", "package.json", "Cargo.toml", "go.mod",
    "pom.xml", "Gemfile", ".git",
)


@dataclass
class MonorepoLocation:
    path: Path
    parent: Path
    has_settings: bool
    has_skills: bool
    has_hooks: bool
    has_mcp: bool
    scope_kind: ScopeKind
    last_modified: datetime
    size_bytes: int
    project_marker: str | None


def _has_hooks_in_settings(settings_path: Path) -> bool:
    if not settings_path.exists():
        return False
    try:
        import json
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("hooks"))


def _find_project_marker(parent: Path) -> str | None:
    for marker in PROJECT_MARKERS:
        if (parent / marker).exists():
            return marker
    return None


def _max_mtime_and_size(root: Path) -> tuple[datetime, int]:
    max_mt = 0.0
    total = 0
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        if st.st_mtime > max_mt:
            max_mt = st.st_mtime
        total += st.st_size
    if max_mt == 0.0:
        max_mt = root.stat().st_mtime
    return datetime.fromtimestamp(max_mt, tz=timezone.utc), total


def _is_inside_skip_dir(path: Path, root: Path | None) -> bool:
    if root is None:
        return any(part in SKIP_DIRS for part in path.parts)
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    return any(part in SKIP_DIRS for part in rel.parts)


def classify_location(claude_dir: Path, *, root: Path | None = None) -> MonorepoLocation:
    parent = claude_dir.parent
    marker = _find_project_marker(parent)
    has_settings = (claude_dir / "settings.json").exists() or \
                   (claude_dir / "settings.local.json").exists()
    has_skills = (claude_dir / "skills").is_dir()
    has_hooks = _has_hooks_in_settings(claude_dir / "settings.json") or \
                _has_hooks_in_settings(claude_dir / "settings.local.json")
    has_mcp = (claude_dir / "mcp.json").exists() or (claude_dir / ".mcp.json").exists()
    last_mod, size = _max_mtime_and_size(claude_dir)

    inside_skip = _is_inside_skip_dir(claude_dir, root)

    if marker and not inside_skip:
        kind: ScopeKind = "real"
    elif marker and inside_skip:
        kind = "nested"
    else:
        kind = "junk"

    return MonorepoLocation(
        path=claude_dir, parent=parent,
        has_settings=has_settings, has_skills=has_skills,
        has_hooks=has_hooks, has_mcp=has_mcp,
        scope_kind=kind, last_modified=last_mod, size_bytes=size,
        project_marker=marker,
    )


def _walk(root: Path, *, follow_skip: bool) -> Iterator[Path]:
    """Yield every .claude/ directory under root.

    When follow_skip is False, do not descend into SKIP_DIRS at all
    (fast path for normal scan).
    """
    if not root.exists():
        return
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = list(d.iterdir())
        except (OSError, PermissionError):
            continue
        for e in entries:
            if not e.is_dir():
                continue
            if e.name == ".claude":
                yield e
                continue
            if not follow_skip and e.name in SKIP_DIRS:
                continue
            stack.append(e)


def discover_locations(
    root: Path | None = None,
    *,
    include_junk: bool = False,
    scope_filter: tuple[ScopeKind, ...] | None = None,
) -> list[MonorepoLocation]:
    root = root or Path.cwd()
    out: list[MonorepoLocation] = []
    # When include_junk=True we must descend into SKIP_DIRS too,
    # otherwise we never see vendored .claude/ dirs at all.
    for claude_dir in _walk(root, follow_skip=include_junk):
        loc = classify_location(claude_dir, root=root)
        if loc.scope_kind == "junk" and not include_junk:
            continue
        if scope_filter and loc.scope_kind not in scope_filter:
            continue
        out.append(loc)
    out.sort(key=lambda l: (l.scope_kind, str(l.path)))
    return out
