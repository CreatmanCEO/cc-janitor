from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import frontmatter

from .monorepo import classify_location, discover_locations
from .safety import require_confirmed
from .state import get_paths


def _normalize_scope(scope: str | None) -> tuple[str, ...] | None:
    if scope is None or scope == "all":
        return None
    if scope == "real+nested":
        return ("real", "nested")
    if scope in ("real", "nested", "junk"):
        return (scope,)
    return None


def _classify_memory_path(path: Path) -> str:
    """Classify a memory file by its enclosing .claude/ directory."""
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
        if rel.parts and rel.parts[0] == ".claude":
            return "real"
    except ValueError:
        pass
    try:
        return classify_location(claude_dir).scope_kind
    except Exception:
        return "real"

MemoryType = Literal["user", "feedback", "project", "reference", "unknown"]
KNOWN_TYPES: tuple[MemoryType, ...] = ("user", "feedback", "project", "reference")


@dataclass
class MemoryFile:
    path: Path
    type: MemoryType
    title: str | None
    description: str | None
    frontmatter: dict
    body: str
    size_bytes: int
    line_count: int
    last_modified: datetime
    project: str | None = None
    is_archived: bool = False


def classify_type(fm: dict, path: Path) -> MemoryType:
    explicit = (fm or {}).get("type")
    if isinstance(explicit, str) and explicit.lower() in KNOWN_TYPES:
        return explicit.lower()  # type: ignore[return-value]
    name = path.name.lower()
    if name.startswith("feedback_"):
        return "feedback"
    if name.startswith("project_"):
        return "project"
    if name.startswith("research_") or name.startswith("reference_"):
        return "reference"
    if name in {"memory.md", "user_profile.md"}:
        return "user"
    return "unknown"


def parse_memory_file(path: Path, *, project: str | None = None,
                      is_archived: bool = False) -> MemoryFile:
    raw = path.read_text(encoding="utf-8")
    post = frontmatter.loads(raw)
    fm = dict(post.metadata)
    body = post.content
    typ = classify_type(fm, path)
    title = fm.get("title")
    description = fm.get("description")
    if title is None:
        for line in body.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
    if description is None:
        for line in body.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                description = line[:200]
                break
    stat = path.stat()
    return MemoryFile(
        path=path,
        type=typ,
        title=title,
        description=description,
        frontmatter=fm,
        body=body,
        size_bytes=stat.st_size,
        line_count=raw.count("\n") + (0 if raw.endswith("\n") else 1),
        last_modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
        project=project,
        is_archived=is_archived,
    )


def _claude_projects_root() -> Path:
    paths = get_paths()
    home = paths.home.parent  # ~
    return home / ".claude" / "projects"


def _global_user_claude_md() -> Path:
    return get_paths().home.parent / ".claude" / "CLAUDE.md"


@dataclass
class DuplicateLine:
    line: str
    files: list[Path]


def discover_memory_files(
    *,
    type_filter: str | None = None,
    project: str | None = None,
    include_archived: bool = False,
    scope: str | None = None,
) -> list[MemoryFile]:
    out: list[MemoryFile] = []
    root = _claude_projects_root()
    if root.exists():
        for proj_dir in root.iterdir():
            if not proj_dir.is_dir():
                continue
            if project and proj_dir.name != project:
                continue
            mem_dir = proj_dir / "memory"
            if not mem_dir.exists():
                continue
            for f in mem_dir.rglob("*.md"):
                archived = ".archive" in f.parts
                if archived and not include_archived:
                    continue
                try:
                    out.append(
                        parse_memory_file(f, project=proj_dir.name, is_archived=archived)
                    )
                except Exception:
                    continue
    user_md = _global_user_claude_md()
    if user_md.exists():
        try:
            out.append(parse_memory_file(user_md, project=None))
        except Exception:
            pass
    # Walk monorepo .claude/ locations under cwd for additional memory files
    try:
        locs = discover_locations(include_junk=True)
    except Exception:
        locs = []
    seen_paths = {m.path for m in out}
    for loc in locs:
        # CLAUDE.md at .claude/CLAUDE.md
        cmd = loc.path / "CLAUDE.md"
        if cmd.exists() and cmd not in seen_paths:
            try:
                out.append(parse_memory_file(cmd, project=loc.parent.name))
                seen_paths.add(cmd)
            except Exception:
                pass
        # memory/*.md within nested .claude/
        mem_dir = loc.path / "memory"
        if mem_dir.exists():
            for f in mem_dir.rglob("*.md"):
                archived = ".archive" in f.parts
                if archived and not include_archived:
                    continue
                if f in seen_paths:
                    continue
                try:
                    out.append(
                        parse_memory_file(
                            f, project=loc.parent.name, is_archived=archived
                        )
                    )
                    seen_paths.add(f)
                except Exception:
                    continue

    if type_filter:
        out = [m for m in out if m.type == type_filter]

    if scope is not None and scope != "all":
        allowed = _normalize_scope(scope)
        if allowed is not None:
            out = [m for m in out if _classify_memory_path(m.path) in allowed]
        else:
            try:
                target = Path(scope).resolve()
                out = [
                    m for m in out
                    if target in m.path.resolve().parents
                    or m.path.resolve() == target
                ]
            except (OSError, ValueError):
                pass
    return out


def find_duplicate_lines(paths: list[Path], *, min_length: int = 8) -> list[DuplicateLine]:
    seen: dict[str, list[Path]] = {}
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if len(line) < min_length:
                continue
            if line.startswith("#"):
                continue
            seen.setdefault(line, []).append(p)
    return [DuplicateLine(line=k, files=v) for k, v in seen.items() if len(v) >= 2]


def archive_memory_file(path: Path) -> Path:
    require_confirmed()
    if not path.exists():
        raise FileNotFoundError(path)
    archive_root = path.parent / ".archive" / datetime.now(UTC).strftime(
        "%Y%m%dT%H%M%S"
    )
    archive_root.mkdir(parents=True, exist_ok=True)
    dst = archive_root / path.name
    shutil.move(str(path), str(dst))
    return dst


def move_memory_type(path: Path, new_type: str) -> None:
    require_confirmed()
    if new_type not in KNOWN_TYPES:
        raise ValueError(f"Unknown type: {new_type}; must be one of {KNOWN_TYPES}")
    raw = path.read_text(encoding="utf-8")
    post = frontmatter.loads(raw)
    post["type"] = new_type
    path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")


def _resolve_editor() -> list[str]:
    for var in ("EDITOR", "VISUAL"):
        val = os.environ.get(var)
        if val:
            return val.split()
    if sys.platform == "win32":
        return ["notepad.exe"]
    return ["vi"]


def open_in_editor(path: Path) -> int:
    require_confirmed()
    cmd = [*_resolve_editor(), str(path)]
    result = subprocess.run(cmd)
    return result.returncode
