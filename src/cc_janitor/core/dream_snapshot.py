from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .state import get_paths


@dataclass
class LockState:
    """Per-daemon-iteration map: memory_dir → currently-seen-lock-pid."""
    seen: dict[Path, int] = field(default_factory=dict)


@dataclass
class LockTransition:
    kind: Literal["no_change", "lock_appeared", "lock_gone"]
    memory_dir: Path | None = None
    pid: int | None = None


@dataclass
class DreamSnapshotPair:
    pair_id: str
    project_slug: str
    project_path: str
    claude_memory_dir: str
    ts_pre: str
    ts_post: str | None
    paths_in_pre: list[str]
    paths_in_post: list[str] | None
    file_count_delta: int | None
    line_count_delta: int | None
    has_diff: bool | None
    dream_pid_in_lock: int | None
    storage: Literal["raw", "tar"] = "raw"


def _dream_root() -> Path:
    return get_paths().home / "backups" / "dream"


def _history_path() -> Path:
    return get_paths().home / "dream-snapshots.jsonl"


def observe_lock(memory_dir: Path, state: LockState) -> LockTransition:
    lock = memory_dir / ".consolidate-lock"
    prev_pid = state.seen.get(memory_dir)
    if lock.exists():
        try:
            pid = int(lock.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            pid = 0
        if prev_pid is None:
            state.seen[memory_dir] = pid
            return LockTransition("lock_appeared", memory_dir, pid)
        return LockTransition("no_change", memory_dir, pid)
    else:
        if prev_pid is not None:
            state.seen.pop(memory_dir, None)
            return LockTransition("lock_gone", memory_dir, prev_pid)
        return LockTransition("no_change", memory_dir, None)


def _copy_tree(src: Path, dst: Path) -> list[Path]:
    dst.mkdir(parents=True, exist_ok=True)
    rels: list[Path] = []
    for f in src.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(src)
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, out)
        rels.append(rel)
    return rels


def snapshot_pre(pair_id: str, memory_dir: Path) -> Path:
    out = _dream_root() / f"{pair_id}-pre"
    _copy_tree(memory_dir, out)
    return out


def snapshot_post(pair_id: str, memory_dir: Path) -> Path:
    out = _dream_root() / f"{pair_id}-post"
    _copy_tree(memory_dir, out)
    return out


def _count_lines(d: Path) -> int:
    total = 0
    for f in d.rglob("*.md"):
        try:
            total += sum(1 for _ in f.open("r", encoding="utf-8", errors="ignore"))
        except OSError:
            pass
    return total


def record_pair(
    pair_id: str,
    memory_dir: Path,
    *,
    project_slug: str,
    dream_pid_in_lock: int | None,
    ts_pre: datetime,
    ts_post: datetime | None,
    pre_dir: Path,
    post_dir: Path | None,
) -> DreamSnapshotPair:
    pre_files = sorted(str(p.relative_to(pre_dir))
                       for p in pre_dir.rglob("*") if p.is_file())
    post_files = (sorted(str(p.relative_to(post_dir))
                         for p in post_dir.rglob("*") if p.is_file())
                  if post_dir else None)
    file_delta = (len(post_files) - len(pre_files)) if post_files is not None else None
    line_delta = (_count_lines(post_dir) - _count_lines(pre_dir)) if post_dir else None
    has_diff = (file_delta != 0 or line_delta != 0) if line_delta is not None else None
    pair = DreamSnapshotPair(
        pair_id=pair_id,
        project_slug=project_slug,
        project_path=str(memory_dir.parent.parent),
        claude_memory_dir=str(memory_dir),
        ts_pre=ts_pre.isoformat(),
        ts_post=ts_post.isoformat() if ts_post else None,
        paths_in_pre=pre_files,
        paths_in_post=post_files,
        file_count_delta=file_delta,
        line_count_delta=line_delta,
        has_diff=has_diff,
        dream_pid_in_lock=dream_pid_in_lock,
        storage="raw",
    )
    hp = _history_path()
    hp.parent.mkdir(parents=True, exist_ok=True)
    with hp.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(pair)) + "\n")
    return pair


def history() -> list[DreamSnapshotPair]:
    hp = _history_path()
    if not hp.exists():
        return []
    out: list[DreamSnapshotPair] = []
    for line in hp.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        out.append(DreamSnapshotPair(**d))
    return out


def project_slug_from_memory_dir(memory_dir: Path) -> str:
    """`.../projects/-home-u-proj/memory` → "proj" (last hyphen-segment)."""
    parent = memory_dir.parent.name
    parts = [p for p in parent.split("-") if p]
    return parts[-1] if parts else parent
