from __future__ import annotations

import json
import os
import secrets
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .state import Paths


class NotConfirmedError(RuntimeError):
    """Raised when a mutation is attempted without CC_JANITOR_USER_CONFIRMED=1."""


class RunawayCapError(RuntimeError):
    """Scheduled run exceeded the hard delete cap."""


_run_counter = 0


def reset_run_counter() -> None:
    global _run_counter
    _run_counter = 0


def _bump_and_check_cap() -> None:
    global _run_counter
    if os.environ.get("CC_JANITOR_SCHEDULED") != "1":
        return
    cap = int(os.environ.get("CC_JANITOR_HARD_CAP", "200"))
    _run_counter += 1
    if _run_counter > cap:
        raise RunawayCapError(
            f"scheduled run exceeded hard cap of {cap} deletions"
        )


def is_confirmed() -> bool:
    return os.environ.get("CC_JANITOR_USER_CONFIRMED") == "1"


def require_confirmed() -> None:
    if not is_confirmed():
        raise NotConfirmedError(
            "This action requires CC_JANITOR_USER_CONFIRMED=1 in environment. "
            "Set it to confirm you authorise this mutation."
        )


@dataclass
class TrashItem:
    id: str
    original_path: str
    deleted_at: str
    trashed_path: Path


def _trash_id(now: datetime) -> str:
    """Return a sortable, collision-resistant trash bucket id.

    Format: ``YYYYMMDDTHHMMSSffffff-<6-hex-chars>``. The timestamp gives
    chronological ordering when iterating buckets; the random suffix
    prevents collisions when many soft_delete calls occur in the same
    microsecond (e.g. bulk permission prune).
    """
    return now.strftime("%Y%m%dT%H%M%S%f") + "-" + secrets.token_hex(3)


def soft_delete(src: Path, *, paths: Paths) -> str:
    paths.ensure_dirs()
    _bump_and_check_cap()
    now = datetime.now(UTC)
    tid = _trash_id(now)
    bucket = paths.trash / tid
    bucket.mkdir(parents=True)
    dst = bucket / src.name
    shutil.move(str(src), str(dst))
    meta = {
        "original_path": str(src),
        "deleted_at": now.isoformat(),
        "name": src.name,
    }
    (bucket / "_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return tid


def list_trash(paths: Paths) -> list[TrashItem]:
    if not paths.trash.exists():
        return []
    out: list[TrashItem] = []
    for bucket in sorted(paths.trash.iterdir()):
        meta_p = bucket / "_meta.json"
        if not meta_p.exists():
            continue
        m = json.loads(meta_p.read_text(encoding="utf-8"))
        out.append(
            TrashItem(
                id=bucket.name,
                original_path=m["original_path"],
                deleted_at=m["deleted_at"],
                trashed_path=bucket / m["name"],
            )
        )
    return out


def restore_from_trash(trash_id: str, *, paths: Paths) -> Path:
    """Restore a trashed item to its original path.

    Raises:
        NotConfirmedError: if ``CC_JANITOR_USER_CONFIRMED`` is not set.
            Restore is a mutation — recovering a previously soft-deleted
            file (which may contain secrets) requires explicit user
            authorisation, same as any other write.
        FileNotFoundError: if ``trash_id`` does not name a known bucket.
        FileExistsError: if the original path is now occupied. The trash
            bucket is left intact so the caller can decide what to do.
    """
    require_confirmed()
    bucket = paths.trash / trash_id
    meta_p = bucket / "_meta.json"
    if not meta_p.exists():
        raise FileNotFoundError(f"No trash entry: {trash_id}")
    m = json.loads(meta_p.read_text(encoding="utf-8"))
    dst = Path(m["original_path"])
    if dst.exists():
        raise FileExistsError(
            f"Cannot restore — original path is occupied: {dst}"
        )
    dst.parent.mkdir(parents=True, exist_ok=True)
    src = bucket / m["name"]
    shutil.move(str(src), str(dst))
    meta_p.unlink()
    bucket.rmdir()
    return dst
