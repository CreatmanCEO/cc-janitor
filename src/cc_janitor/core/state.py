from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _user_home() -> Path:
    # Windows: USERPROFILE wins, else HOME
    return Path(os.environ.get("USERPROFILE") or os.environ["HOME"])


@dataclass(frozen=True)
class Paths:
    home: Path

    @property
    def cache(self) -> Path:
        return self.home / "cache"

    @property
    def trash(self) -> Path:
        return self.home / ".trash"

    @property
    def backups(self) -> Path:
        return self.home / "backups"

    @property
    def hooks_log(self) -> Path:
        return self.home / "hooks-log"

    @property
    def history(self) -> Path:
        return self.home / "history"

    @property
    def audit_log(self) -> Path:
        return self.home / "audit.log"

    @property
    def config(self) -> Path:
        return self.home / "config.toml"

    def ensure_dirs(self) -> None:
        for d in (self.cache, self.trash, self.backups, self.hooks_log, self.history):
            d.mkdir(parents=True, exist_ok=True)


def get_paths() -> Paths:
    override = os.environ.get("CC_JANITOR_HOME")
    home = Path(override) if override else _user_home() / ".cc-janitor"
    return Paths(home=home)
