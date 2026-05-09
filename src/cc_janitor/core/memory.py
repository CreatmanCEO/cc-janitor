from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import frontmatter

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
        last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        project=project,
        is_archived=is_archived,
    )
