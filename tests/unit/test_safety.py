from pathlib import Path

import pytest

from cc_janitor.core.safety import (
    NotConfirmedError,
    list_trash,
    require_confirmed,
    restore_from_trash,
    soft_delete,
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


def test_soft_delete_and_restore_directory(tmp_path):
    """A whole directory should round-trip cleanly (used for session deletes)."""
    paths = _paths(tmp_path)
    paths.ensure_dirs()
    src_dir = tmp_path / "session_42"
    src_dir.mkdir()
    (src_dir / "transcript.jsonl").write_text("line1\nline2\n", encoding="utf-8")
    (src_dir / "subagents").mkdir()
    (src_dir / "subagents" / "agent.jsonl").write_text("hi\n", encoding="utf-8")

    trash_id = soft_delete(src_dir, paths=paths)
    assert not src_dir.exists()

    restore_from_trash(trash_id, paths=paths)
    assert src_dir.is_dir()
    assert (src_dir / "transcript.jsonl").read_text(encoding="utf-8") == "line1\nline2\n"
    assert (src_dir / "subagents" / "agent.jsonl").read_text(encoding="utf-8") == "hi\n"


def test_restore_refuses_to_overwrite(tmp_path):
    """If the original path is occupied, restore must raise rather than clobber."""
    paths = _paths(tmp_path)
    paths.ensure_dirs()
    src = tmp_path / "victim.txt"
    src.write_text("original")
    trash_id = soft_delete(src, paths=paths)
    src.write_text("new content created after delete")

    with pytest.raises(FileExistsError):
        restore_from_trash(trash_id, paths=paths)
    # Trash bucket left intact for caller to decide
    assert any(i.id == trash_id for i in list_trash(paths))
    # Existing file untouched
    assert src.read_text() == "new content created after delete"


def test_soft_delete_unique_ids_under_concurrency_burst(tmp_path):
    """Bulk deletes (e.g. perms prune) must not collide on trash ids."""
    paths = _paths(tmp_path)
    paths.ensure_dirs()
    ids = []
    for i in range(50):
        f = tmp_path / f"f{i}.txt"
        f.write_text(str(i))
        ids.append(soft_delete(f, paths=paths))
    assert len(set(ids)) == 50, "All trash ids must be unique"
