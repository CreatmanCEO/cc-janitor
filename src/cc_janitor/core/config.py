from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

from .state import get_paths

# Tracks paths for which we have already emitted a parse-error warning,
# so repeated load_config() calls within a single process do not spam.
_WARNED_PATHS: set[str] = set()


@dataclass(frozen=True)
class DreamDoctorConfig:
    disk_warning_mb: int = 100
    memory_file_count_threshold: int = 50
    memory_md_line_threshold: int = 180


@dataclass(frozen=True)
class SnapshotsConfig:
    raw_retention_days: int = 7
    tar_retention_days: int = 30


@dataclass(frozen=True)
class HygieneConfig:
    relative_date_terms_extra: tuple[str, ...] = ()
    contradiction_jaccard_threshold: float = 0.5


@dataclass(frozen=True)
class Config:
    dream_doctor: DreamDoctorConfig = field(default_factory=DreamDoctorConfig)
    snapshots: SnapshotsConfig = field(default_factory=SnapshotsConfig)
    hygiene: HygieneConfig = field(default_factory=HygieneConfig)


DEFAULTS = Config()


def _default_path() -> Path:
    return get_paths().home / "config.toml"


def load_config(path: Path | None = None) -> Config:
    p = path if path is not None else _default_path()
    if not p.exists():
        return DEFAULTS
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as e:
        key = str(p)
        if key not in _WARNED_PATHS:
            _WARNED_PATHS.add(key)
            print(
                f"WARN: config.toml at {p} failed to parse ({e}); using defaults",
                file=sys.stderr,
            )
        return DEFAULTS
    dd = data.get("dream_doctor", {}) or {}
    sn = data.get("snapshots", {}) or {}
    hy = data.get("hygiene", {}) or {}
    return Config(
        dream_doctor=replace(DEFAULTS.dream_doctor, **{
            k: v for k, v in dd.items()
            if k in {"disk_warning_mb", "memory_file_count_threshold",
                     "memory_md_line_threshold"}
        }),
        snapshots=replace(DEFAULTS.snapshots, **{
            k: v for k, v in sn.items()
            if k in {"raw_retention_days", "tar_retention_days"}
        }),
        hygiene=HygieneConfig(
            relative_date_terms_extra=tuple(
                hy.get("relative_date_terms_extra", ())
            ),
            contradiction_jaccard_threshold=float(
                hy.get("contradiction_jaccard_threshold", 0.5)
            ),
        ),
    )
