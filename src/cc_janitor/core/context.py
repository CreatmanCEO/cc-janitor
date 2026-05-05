from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from .tokens import count_file_tokens


@dataclass
class ContextFile:
    path: Path
    size_bytes: int
    tokens: int
    kind: str  # "claude_md" | "memory" | "skill" | "permissions"


@dataclass
class ContextCost:
    files: list[ContextFile]
    total_bytes: int
    total_tokens: int


def _user_home() -> Path:
    return Path.home()


def claude_md_hierarchy(*, starting_from: Path) -> list[ContextFile]:
    """Walk from ``starting_from`` up to filesystem root, collecting CLAUDE.md files,
    plus the global ``~/.claude/CLAUDE.md``."""
    out: list[ContextFile] = []
    seen: set[Path] = set()

    def add(p: Path) -> None:
        if p.exists() and p not in seen:
            seen.add(p)
            out.append(ContextFile(
                path=p,
                size_bytes=p.stat().st_size,
                tokens=count_file_tokens(p),
                kind="claude_md",
            ))

    cur = starting_from.resolve()
    while True:
        add(cur / "CLAUDE.md")
        if cur.parent == cur:
            break
        cur = cur.parent

    add(_user_home() / ".claude" / "CLAUDE.md")
    return out


def memory_files(*, claude_project_dir: str) -> list[ContextFile]:
    home = _user_home()
    mem_dir = home / ".claude" / "projects" / claude_project_dir / "memory"
    if not mem_dir.exists():
        return []
    out: list[ContextFile] = []
    for p in sorted(mem_dir.glob("*.md")):
        out.append(ContextFile(
            path=p,
            size_bytes=p.stat().st_size,
            tokens=count_file_tokens(p),
            kind="memory",
        ))
    return out


def enabled_skills() -> list[ContextFile]:
    home = _user_home()
    out: list[ContextFile] = []
    skills_root = home / ".claude" / "skills"
    if skills_root.exists():
        for skill_md in skills_root.rglob("SKILL.md"):
            out.append(ContextFile(
                path=skill_md,
                size_bytes=skill_md.stat().st_size,
                tokens=count_file_tokens(skill_md),
                kind="skill",
            ))
    return out


def context_cost(
    *,
    starting_from: Path,
    claude_project_dir: str | None = None,
) -> ContextCost:
    files: list[ContextFile] = []
    files += claude_md_hierarchy(starting_from=starting_from)
    if claude_project_dir:
        files += memory_files(claude_project_dir=claude_project_dir)
    files += enabled_skills()
    return ContextCost(
        files=files,
        total_bytes=sum(f.size_bytes for f in files),
        total_tokens=sum(f.tokens for f in files),
    )
