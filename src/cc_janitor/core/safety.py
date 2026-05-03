from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .state import Paths


class NotConfirmedError(RuntimeError):
    """Raised when a mutation is attempted without CC_JANITOR_USER_CONFIRMED=1."""


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
    return now.strftime("%Y%m%dT%H%M%S%f")


def soft_delete(src: Path, *, paths: Paths) -> str:
    paths.ensure_dirs()
    now = datetime.now(timezone.utc)
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
    bucket = paths.trash / trash_id
    meta_p = bucket / "_meta.json"
    if not meta_p.exists():
        raise FileNotFoundError(f"No trash entry: {trash_id}")
    m = json.loads(meta_p.read_text(encoding="utf-8"))
    dst = Path(m["original_path"])
    src = bucket / m["name"]
    shutil.move(str(src), str(dst))
    meta_p.unlink()
    bucket.rmdir()
    return dst
