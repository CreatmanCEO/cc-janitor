from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .dream_snapshot import (
    LockState,
    observe_lock,
    project_slug_from_memory_dir,
    record_pair,
    snapshot_post,
    snapshot_pre,
)
from .state import get_paths


@dataclass
class WatcherStatus:
    pid: int
    started_at: datetime
    watching_paths: list[Path]
    interval_seconds: int
    marker_writes_count: int
    last_change_at: datetime | None
    is_alive: bool


def _status_path() -> Path:
    return get_paths().home / "watcher-status.json"


def _pid_path() -> Path:
    return get_paths().home / "watcher.pid"


def write_status(s: WatcherStatus) -> None:
    _status_path().parent.mkdir(parents=True, exist_ok=True)
    d = asdict(s)
    d["watching_paths"] = [str(p) for p in s.watching_paths]
    d["started_at"] = s.started_at.isoformat()
    d["last_change_at"] = s.last_change_at.isoformat() if s.last_change_at else None
    _status_path().write_text(json.dumps(d, indent=2), encoding="utf-8")


def read_status() -> WatcherStatus | None:
    p = _status_path()
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    pid = int(d["pid"])
    return WatcherStatus(
        pid=pid,
        started_at=datetime.fromisoformat(d["started_at"]),
        watching_paths=[Path(x) for x in d["watching_paths"]],
        interval_seconds=int(d["interval_seconds"]),
        marker_writes_count=int(d["marker_writes_count"]),
        last_change_at=(
            datetime.fromisoformat(d["last_change_at"])
            if d.get("last_change_at")
            else None
        ),
        is_alive=is_pid_alive(pid),
    )


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil  # type: ignore

        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
    except ImportError:
        pass
    except Exception:
        return False
    if sys.platform == "win32":
        # No psutil — best-effort via tasklist.
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                check=False,
            )
            return str(pid) in out.stdout
        except OSError:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def iter_watched_files(dirs: list[Path]) -> Iterator[Path]:
    for d in dirs:
        if not d.exists():
            continue
        for f in d.rglob("*.md"):
            if ".archive" in f.parts:
                continue
            yield f


def run_watcher_once(
    memory_dirs: list[Path], last_mtimes: dict[Path, float]
) -> bool:
    """Single poll iteration. Returns True if marker was written."""
    changed = False
    for f in iter_watched_files(memory_dirs):
        try:
            mt = f.stat().st_mtime
        except OSError:
            continue
        previous = last_mtimes.get(f)
        last_mtimes[f] = mt
        if previous is not None and mt > previous:
            changed = True
    if changed:
        marker = get_paths().home / "reinject-pending"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        s = read_status()
        if s is not None:
            s.marker_writes_count += 1
            s.last_change_at = datetime.now(UTC)
            write_status(s)
    return changed


def _new_pair_id(slug: str) -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + f"-{slug}"


def run_dream_once(
    memory_dirs: list[Path],
    state: LockState,
    pending: dict[Path, dict],
) -> None:
    """Single dream-watch poll iteration.

    Observes ``.consolidate-lock`` lifecycle in each memory dir. On
    lock-appears, writes a pre-snapshot and stores transition metadata in
    ``pending``. On lock-gone, writes the post-snapshot and records a
    ``DreamSnapshotPair`` to the JSONL history.
    """
    for mem in memory_dirs:
        t = observe_lock(mem, state)
        if t.kind == "lock_appeared":
            slug = project_slug_from_memory_dir(mem)
            pair_id = _new_pair_id(slug)
            pre_dir = snapshot_pre(pair_id, mem)
            pending[mem] = {
                "pair_id": pair_id,
                "slug": slug,
                "pre_dir": pre_dir,
                "ts_pre": datetime.now(UTC),
                "pid": t.pid,
            }
        elif t.kind == "lock_gone":
            info = pending.pop(mem, None)
            if info is None:
                continue
            post_dir = snapshot_post(info["pair_id"], mem)
            record_pair(
                info["pair_id"],
                mem,
                project_slug=info["slug"],
                dream_pid_in_lock=info["pid"],
                ts_pre=info["ts_pre"],
                ts_post=datetime.now(UTC),
                pre_dir=info["pre_dir"],
                post_dir=post_dir,
            )


def run_watcher(
    memory_dirs: list[Path],
    interval: int,
    *,
    dream: bool = False,
    memory: bool = True,
) -> None:
    """Main loop — invoked by the spawned daemon process.

    Args:
        memory_dirs: per-project ``memory/`` dirs to observe.
        interval: poll interval, seconds.
        dream: if True, also poll ``.consolidate-lock`` lifecycle and
            snapshot pre/post around Auto Dream consolidation events.
        memory: if False, the mtime reinject watch is skipped (useful when
            running purely as a dream-snapshot daemon).
    """
    last_mtimes: dict[Path, float] = {}
    if memory:
        for f in iter_watched_files(memory_dirs):
            try:
                last_mtimes[f] = f.stat().st_mtime
            except OSError:
                pass
    lock_state = LockState() if dream else None
    pending: dict[Path, dict] = {}
    while True:
        try:
            time.sleep(interval)
            if memory:
                run_watcher_once(memory_dirs, last_mtimes)
            if dream and lock_state is not None:
                run_dream_once(memory_dirs, lock_state, pending)
        except KeyboardInterrupt:
            return
        except Exception:
            time.sleep(interval)


def spawn_daemon(args: list[str], cwd: Path, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("ab")
    if sys.platform == "win32":
        flags = 0x00000200 | 0x00000008  # CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
        proc = subprocess.Popen(
            args,
            cwd=str(cwd),
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
    else:
        proc = subprocess.Popen(
            args,
            cwd=str(cwd),
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    return proc.pid


def kill_pid(pid: int) -> None:
    if not is_pid_alive(pid):
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            check=False,
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(10):
        if not is_pid_alive(pid):
            return
        time.sleep(0.5)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
