from __future__ import annotations

import json
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from croniter import croniter

from .safety import require_confirmed
from .state import get_paths

JobStatus = Literal["ok", "fail", "never"]


@dataclass
class ScheduledJob:
    name: str
    template: str
    cron_expr: str
    command: str
    next_run: datetime | None
    last_run: datetime | None
    last_status: JobStatus
    dry_run_pending: bool
    backend: Literal["cron", "schtasks"]


TEMPLATES: dict[str, dict] = {
    "perms-prune": {
        "default_cron": "0 3 * * 0",
        "command": "cc-janitor perms prune --older-than 90d",
    },
    "trash-cleanup": {
        "default_cron": "0 4 1 * *",
        "command": "cc-janitor trash empty --older-than 30d",
    },
    "session-prune": {
        "default_cron": "0 4 15 * *",
        "command": "cc-janitor session prune --older-than 90d",
    },
    "context-audit": {
        "default_cron": "5 0 * * *",
        "command": "cc-janitor context cost --json",
    },
    "backup-rotate": {
        "default_cron": "0 4 * * 0",
        "command": "cc-janitor backups prune --older-than-days 30",
    },
    "dream-tar-compact": {
        "default_cron": "0 5 * * 0",
        "command": (
            "cc-janitor backups tar-compact --kind dream "
            "--older-than-days 7 --apply"
        ),
    },
}

MARKER_PREFIX = "# cc-janitor-job:"


def _manifest_dir() -> Path:
    p = get_paths().home / "schedule"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _save_manifest(job: ScheduledJob) -> None:
    p = _manifest_dir() / f"{job.name}.json"
    d = asdict(job)
    for k in ("next_run", "last_run"):
        d[k] = d[k].isoformat() if d[k] else None
    p.write_text(json.dumps(d, indent=2), encoding="utf-8")


def _load_manifest(name: str) -> ScheduledJob | None:
    p = _manifest_dir() / f"{name}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    for k in ("next_run", "last_run"):
        d[k] = datetime.fromisoformat(d[k]) if d[k] else None
    return ScheduledJob(**d)


def _delete_manifest(name: str) -> None:
    p = _manifest_dir() / f"{name}.json"
    if p.exists():
        p.unlink()


def _next_run(cron_expr: str) -> datetime:
    return croniter(cron_expr, datetime.now(UTC)).get_next(datetime)


class Scheduler(ABC):
    @abstractmethod
    def list_jobs(self) -> list[ScheduledJob]: ...

    @abstractmethod
    def add_job(self, job: ScheduledJob) -> None: ...

    @abstractmethod
    def remove_job(self, name: str) -> None: ...

    def run_now(self, name: str) -> int:
        job = _load_manifest(name)
        if job is None:
            raise FileNotFoundError(name)
        env = {
            **os.environ,
            "CC_JANITOR_USER_CONFIRMED": "1",
            "CC_JANITOR_SCHEDULED": "1",
        }
        result = subprocess.run(job.command, shell=True, env=env)
        return result.returncode


class CronScheduler(Scheduler):
    def _read_crontab(self) -> str:
        proc = subprocess.run(["crontab", "-l"], capture_output=True)
        return proc.stdout.decode("utf-8", errors="replace") if proc.returncode == 0 else ""

    def _write_crontab(self, content: str) -> None:
        subprocess.run(["crontab", "-"], input=content.encode("utf-8"))

    def list_jobs(self) -> list[ScheduledJob]:
        out: list[ScheduledJob] = []
        for line in self._read_crontab().splitlines():
            if MARKER_PREFIX not in line:
                continue
            name = line.split(MARKER_PREFIX, 1)[1].strip()
            job = _load_manifest(name)
            if job:
                out.append(job)
        return out

    def add_job(self, job: ScheduledJob) -> None:
        require_confirmed()
        existing = self._read_crontab().splitlines()
        existing = [
            ln for ln in existing if not (MARKER_PREFIX in ln and ln.endswith(job.name))
        ]
        env = "CC_JANITOR_USER_CONFIRMED=1 CC_JANITOR_SCHEDULED=1"
        cmd = job.command + (" --dry-run" if job.dry_run_pending else "")
        existing.append(f"{job.cron_expr} {env} {cmd} {MARKER_PREFIX} {job.name}")
        self._write_crontab("\n".join(existing) + "\n")
        job.next_run = _next_run(job.cron_expr)
        _save_manifest(job)

    def remove_job(self, name: str) -> None:
        require_confirmed()
        existing = self._read_crontab().splitlines()
        existing = [
            ln for ln in existing if not (MARKER_PREFIX in ln and ln.endswith(name))
        ]
        self._write_crontab("\n".join(existing) + "\n")
        _delete_manifest(name)


class SchtasksScheduler(Scheduler):
    def _cron_to_schtasks(self, cron_expr: str) -> list[str]:
        # Minimal mapping: only common templates' cron forms.
        # m h dom mon dow
        m, h, dom, _mon, dow = cron_expr.split()
        if dow != "*" and dom == "*":
            map_dow = {
                "0": "SUN",
                "1": "MON",
                "2": "TUE",
                "3": "WED",
                "4": "THU",
                "5": "FRI",
                "6": "SAT",
            }
            return [
                "/SC",
                "WEEKLY",
                "/D",
                map_dow.get(dow, "SUN"),
                "/ST",
                f"{int(h):02d}:{int(m):02d}",
            ]
        if dom != "*" and dow == "*":
            return [
                "/SC",
                "MONTHLY",
                "/D",
                str(int(dom)),
                "/ST",
                f"{int(h):02d}:{int(m):02d}",
            ]
        return ["/SC", "DAILY", "/ST", f"{int(h):02d}:{int(m):02d}"]

    def list_jobs(self) -> list[ScheduledJob]:
        out: list[ScheduledJob] = []
        for p in _manifest_dir().glob("*.json"):
            job = _load_manifest(p.stem)
            if job and job.backend == "schtasks":
                out.append(job)
        return out

    def add_job(self, job: ScheduledJob) -> None:
        require_confirmed()
        cmd = job.command + (" --dry-run" if job.dry_run_pending else "")
        wrapper = (
            'cmd /c "set CC_JANITOR_USER_CONFIRMED=1 && '
            f'set CC_JANITOR_SCHEDULED=1 && {cmd}"'
        )
        args = [
            "schtasks",
            "/Create",
            "/TN",
            job.name,
            "/TR",
            wrapper,
            "/F",
            *self._cron_to_schtasks(job.cron_expr),
        ]
        subprocess.run(args)
        job.next_run = _next_run(job.cron_expr)
        _save_manifest(job)

    def remove_job(self, name: str) -> None:
        require_confirmed()
        subprocess.run(["schtasks", "/Delete", "/TN", name, "/F"])
        _delete_manifest(name)


def get_scheduler() -> Scheduler:
    return SchtasksScheduler() if sys.platform == "win32" else CronScheduler()
