"""Structured pre/post comparison for Dream snapshot pairs.

Walks the raw mirror trees written by ``dream_snapshot.snapshot_pre`` /
``snapshot_post`` and emits a per-file delta with status, +/- line counts,
and an embedded ``difflib.unified_diff`` body. No semantic grouping —
that lands in Phase 5.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class DreamFileDelta:
    rel_path: Path
    status: Literal["added", "removed", "changed", "unchanged"]
    lines_added: int
    lines_removed: int
    unified_diff: str | None


@dataclass
class DreamDiff:
    pre_dir: Path
    post_dir: Path
    deltas: list[DreamFileDelta]
    summary: dict


def _read_lines(p: Path) -> list[str]:
    try:
        return p.read_text(encoding="utf-8").splitlines(keepends=True)
    except (OSError, UnicodeDecodeError):
        return []


def _walk_rel(d: Path) -> set[Path]:
    if not d.exists():
        return set()
    return {f.relative_to(d) for f in d.rglob("*") if f.is_file()}


def compute_diff(pre_dir: Path, post_dir: Path) -> DreamDiff:
    """Compare two raw mirror directories and return a structured diff."""
    pre_set = _walk_rel(pre_dir)
    post_set = _walk_rel(post_dir)
    all_paths = sorted(pre_set | post_set, key=str)
    deltas: list[DreamFileDelta] = []
    summary = {
        "files_added": 0,
        "files_removed": 0,
        "files_changed": 0,
        "files_unchanged": 0,
    }
    for rel in all_paths:
        in_pre = rel in pre_set
        in_post = rel in post_set
        if in_pre and not in_post:
            pre_lines = _read_lines(pre_dir / rel)
            deltas.append(
                DreamFileDelta(
                    rel_path=rel,
                    status="removed",
                    lines_added=0,
                    lines_removed=len(pre_lines),
                    unified_diff="".join(
                        difflib.unified_diff(
                            pre_lines,
                            [],
                            fromfile=str(rel),
                            tofile="/dev/null",
                        )
                    ),
                )
            )
            summary["files_removed"] += 1
            continue
        if in_post and not in_pre:
            post_lines = _read_lines(post_dir / rel)
            deltas.append(
                DreamFileDelta(
                    rel_path=rel,
                    status="added",
                    lines_added=len(post_lines),
                    lines_removed=0,
                    unified_diff="".join(
                        difflib.unified_diff(
                            [],
                            post_lines,
                            fromfile="/dev/null",
                            tofile=str(rel),
                        )
                    ),
                )
            )
            summary["files_added"] += 1
            continue
        pre_lines = _read_lines(pre_dir / rel)
        post_lines = _read_lines(post_dir / rel)
        if pre_lines == post_lines:
            deltas.append(DreamFileDelta(rel, "unchanged", 0, 0, None))
            summary["files_unchanged"] += 1
            continue
        ud = "".join(
            difflib.unified_diff(
                pre_lines,
                post_lines,
                fromfile=str(rel),
                tofile=str(rel),
                n=3,
            )
        )
        added = sum(
            1
            for ln in ud.splitlines()
            if ln.startswith("+") and not ln.startswith("+++")
        )
        removed = sum(
            1
            for ln in ud.splitlines()
            if ln.startswith("-") and not ln.startswith("---")
        )
        deltas.append(DreamFileDelta(rel, "changed", added, removed, ud))
        summary["files_changed"] += 1
    return DreamDiff(pre_dir, post_dir, deltas, summary)
