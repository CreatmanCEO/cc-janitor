from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .config import load_config
from .dream_snapshot import history
from .memory import find_duplicate_lines
from .state import get_paths

Severity = Literal["OK", "WARN", "FAIL", "INFO"]


@dataclass
class DoctorCheck:
    id: str
    title: str
    severity: Severity
    message: str
    detail: dict | None = None


def _claude_home() -> Path:
    return Path.home() / ".claude"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil  # type: ignore
        return psutil.pid_exists(pid)
    except ImportError:
        pass
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _check_stale_lock() -> DoctorCheck:
    projects = _claude_home() / "projects"
    if not projects.exists():
        return DoctorCheck("stale_lock", "Stale .consolidate-lock",
                           "OK", "No projects directory yet.")
    stale: list[tuple[Path, int]] = []
    for proj in projects.iterdir():
        lock = proj / "memory" / ".consolidate-lock"
        if not lock.exists():
            continue
        try:
            pid = int(lock.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            pid = 0
        if not _pid_alive(pid):
            stale.append((lock, pid))
    if stale:
        return DoctorCheck(
            "stale_lock", "Stale .consolidate-lock", "FAIL",
            f"{len(stale)} stale lock file(s) found "
            "(silently disables Auto Dream — Issue #50694).",
            {"locks": [{"path": str(p), "pid": pid} for p, pid in stale]},
        )
    return DoctorCheck("stale_lock", "Stale .consolidate-lock", "OK",
                       "No stale lock files.")


def _check_autodream_enabled() -> DoctorCheck:
    s = _claude_home() / "settings.json"
    if not s.exists():
        return DoctorCheck("autodream_enabled", "autoDreamEnabled", "INFO",
                           "settings.json missing.")
    try:
        data = json.loads(s.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DoctorCheck("autodream_enabled", "autoDreamEnabled", "WARN",
                           "settings.json unreadable.")
    val = data.get("autoDreamEnabled", False)
    if val:
        return DoctorCheck("autodream_enabled", "autoDreamEnabled", "OK",
                           "Enabled in settings.json.")
    return DoctorCheck("autodream_enabled", "autoDreamEnabled", "WARN",
                       "Auto Dream is disabled in settings.json.")


def _check_server_gate() -> DoctorCheck:
    # Inference only — not invoked at doctor time, would need claude CLI.
    return DoctorCheck("server_gate", "Server-gate inference", "INFO",
                       "Run `claude --print --headless \"/dream\"` to verify; "
                       "'Unknown skill' means flag is off server-side "
                       "(#38461).")


def _check_last_dream() -> DoctorCheck:
    h = history()
    if not h:
        return DoctorCheck("last_dream_ts", "Last dream observed",
                           "INFO", "No paired snapshots yet.")
    last = h[-1]
    return DoctorCheck("last_dream_ts", "Last dream observed", "OK",
                       f"Last paired snapshot: {last.ts_pre} "
                       f"({last.project_slug}).",
                       {"pair_id": last.pair_id})


def _dir_size_mb(d: Path) -> float:
    if not d.exists():
        return 0.0
    return sum(
        f.stat().st_size for f in d.rglob("*") if f.is_file()
    ) / 1024 / 1024


def _check_backup_dir_health() -> DoctorCheck:
    d = get_paths().home / "backups" / "dream"
    if not d.exists():
        return DoctorCheck("backup_dir_health", "Backup directory health",
                           "INFO", "No dream backups yet.")
    return DoctorCheck("backup_dir_health", "Backup directory health", "OK",
                       f"Exists, {_dir_size_mb(d):.1f} MB.")


def _check_memory_md_cap(cfg) -> DoctorCheck:
    threshold = cfg.dream_doctor.memory_md_line_threshold
    projects = _claude_home() / "projects"
    if not projects.exists():
        return DoctorCheck("memory_md_cap", "MEMORY.md cap usage", "OK",
                           "No projects.")
    over: list[tuple[str, int]] = []
    for p in projects.iterdir():
        m = p / "memory" / "MEMORY.md"
        if not m.exists():
            continue
        n = sum(1 for _ in m.open("r", encoding="utf-8", errors="ignore"))
        if n >= threshold:
            over.append((p.name, n))
    if over:
        return DoctorCheck(
            "memory_md_cap", "MEMORY.md cap usage", "WARN",
            f"{len(over)} project(s) within {threshold}-line warning band "
            "(Anthropic hard cap ~200).",
            {"projects": over},
        )
    return DoctorCheck("memory_md_cap", "MEMORY.md cap usage", "OK",
                       f"All MEMORY.md files under {threshold} lines.")


def _check_disk_usage(cfg) -> DoctorCheck:
    threshold = cfg.dream_doctor.disk_warning_mb
    used = _dir_size_mb(get_paths().home / "backups" / "dream")
    sev: Severity = "WARN" if used > threshold else "OK"
    return DoctorCheck("disk_usage", "Dream backup disk usage", sev,
                       f"{used:.1f} MB / threshold {threshold} MB.")


def _check_memory_file_count(cfg) -> DoctorCheck:
    threshold = cfg.dream_doctor.memory_file_count_threshold
    projects = _claude_home() / "projects"
    if not projects.exists():
        return DoctorCheck("memory_file_count", "Memory file count", "OK",
                           "No projects.")
    over: list[tuple[str, int]] = []
    for p in projects.iterdir():
        m = p / "memory"
        if not m.is_dir():
            continue
        cnt = sum(1 for _ in m.rglob("*.md"))
        if cnt > threshold:
            over.append((p.name, cnt))
    if over:
        return DoctorCheck(
            "memory_file_count", "Memory file count", "WARN",
            f"{len(over)} project(s) over {threshold} memory files; "
            "consider `cc-janitor memory archive --stale`.",
            {"projects": over},
        )
    return DoctorCheck("memory_file_count", "Memory file count", "OK",
                       f"All projects under {threshold} memory files.")


def _check_duplicate_summary() -> DoctorCheck:
    projects = _claude_home() / "projects"
    if not projects.exists():
        return DoctorCheck("duplicate_summary", "Cross-file duplicates",
                           "OK", "No projects.")
    all_paths: list[Path] = []
    for p in projects.iterdir():
        m = p / "memory"
        if m.is_dir():
            all_paths.extend(m.rglob("*.md"))
    dups = find_duplicate_lines(all_paths, min_length=8)
    if not dups:
        return DoctorCheck("duplicate_summary", "Cross-file duplicates",
                           "OK", "No cross-file duplicates >= 8 chars.")
    top = sorted(dups, key=lambda d: -len(d.files))[:5]
    return DoctorCheck(
        "duplicate_summary", "Cross-file duplicates", "INFO",
        f"{len(dups)} duplicated lines across memory files.",
        {"top": [{"line": d.line[:80], "count": len(d.files)} for d in top]},
    )


def run_checks() -> list[DoctorCheck]:
    cfg = load_config()
    return [
        _check_stale_lock(),
        _check_autodream_enabled(),
        _check_server_gate(),
        _check_last_dream(),
        _check_backup_dir_health(),
        _check_memory_md_cap(cfg),
        _check_disk_usage(cfg),
        _check_memory_file_count(cfg),
        _check_duplicate_summary(),
    ]
