import os
import pytest
from pathlib import Path
from cc_janitor.core.safety import (
    require_confirmed, NotConfirmedError, soft_delete, restore_from_trash, list_trash,
)
from cc_janitor.core.state import Paths


def _paths(tmp_path: Path) -> Paths:
    return Paths(home=tmp_path / ".cc-janitor")


def test_require_confirmed_raises_when_missing(monkeypatch):
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    with pytest.raises(NotConfirmedError):
        require_confirmed()


def test_require_confirmed_passes_when_set(monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    require_confirmed()  # no raise


def test_soft_delete_moves_file(tmp_path):
    paths = _paths(tmp_path)
    paths.ensure_dirs()
    src = tmp_path / "victim.txt"
    src.write_text("data")
    trash_id = soft_delete(src, paths=paths)
    assert not src.exists()
    items = list_trash(paths)
    assert any(i.id == trash_id for i in items)


def test_restore_from_trash(tmp_path):
    paths = _paths(tmp_path)
    paths.ensure_dirs()
    src = tmp_path / "victim.txt"
    src.write_text("data")
    trash_id = soft_delete(src, paths=paths)
    restore_from_trash(trash_id, paths=paths)
    assert src.exists() and src.read_text() == "data"
