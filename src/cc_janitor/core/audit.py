from __future__ import annotations
import fnmatch, json, os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

ISO = "%Y-%m-%dT%H:%M:%S%z"

@dataclass
class AuditEntry:
    ts: str
    mode: str            # "cli" | "tui" | "scheduled"
    user_confirmed: bool
    cmd: str
    args: list[str]
    exit_code: int
    session_id: str | None = None
    changed: dict | None = None
    backup_path: str | None = None

class AuditLog:
    def __init__(self, path: Path, max_bytes: int = 10 * 1024 * 1024) -> None:
        self.path = path
        self.max_bytes = max_bytes
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _maybe_rotate(self) -> None:
        if not self.path.exists() or self.path.stat().st_size < self.max_bytes:
            return
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        target = self.path.with_name(f"{self.path.name}.{ts}")
        n = 0
        while target.exists():
            n += 1
            target = self.path.with_name(f"{self.path.name}.{ts}-{n}")
        self.path.rename(target)

    def record(self, **kwargs) -> AuditEntry:
        kwargs.setdefault("ts", datetime.now(timezone.utc).strftime(ISO))
        entry = AuditEntry(**kwargs)
        self._maybe_rotate()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        return entry

    def read(self, *, cmd_glob: str | None = None) -> Iterator[AuditEntry]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if cmd_glob and not fnmatch.fnmatch(d["cmd"], cmd_glob):
                    continue
                yield AuditEntry(**d)
