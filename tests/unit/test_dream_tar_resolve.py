"""C1 — transparent tar extraction for Dream pair resolution."""

from __future__ import annotations

import tarfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cc_janitor.cli import app
from cc_janitor.core.dream_snapshot import (
    _dream_root,
    pair_paths,
    record_pair,
    resolve_pair_paths,
    snapshot_post,
    snapshot_pre,
)


def _seed(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    mem = tmp_path / ".claude" / "projects" / "-proj" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("a\nb\nc\n")
    pre = snapshot_pre("20260513T120000Z-proj", mem)
    (mem / "MEMORY.md").write_text("a\n")
    post = snapshot_post("20260513T120000Z-proj", mem)
    record_pair(
        "20260513T120000Z-proj", mem,
        project_slug="proj",
        dream_pid_in_lock=1234,
        ts_pre=datetime.now(UTC),
        ts_post=datetime.now(UTC),
        pre_dir=pre, post_dir=post,
    )
    return mem


def _tar_pair(pair_id: str) -> Path:
    root = _dream_root()
    pre = root / f"{pair_id}-pre"
    post = root / f"{pair_id}-post"
    archive = root / f"{pair_id}.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for f in pre.rglob("*"):
            if f.is_file():
                tf.add(f, arcname=f"pre/{f.relative_to(pre)}")
        for f in post.rglob("*"):
            if f.is_file():
                tf.add(f, arcname=f"post/{f.relative_to(post)}")
    import shutil

    shutil.rmtree(pre)
    shutil.rmtree(post)
    return archive


def test_resolve_raw_mirrors(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    pre, post, cleanup = resolve_pair_paths("20260513T120000Z-proj")
    try:
        assert pre.is_dir() and post.is_dir()
        assert (pre / "MEMORY.md").read_text() == "a\nb\nc\n"
        assert (post / "MEMORY.md").read_text() == "a\n"
    finally:
        cleanup()


def test_resolve_tar_archive(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    _tar_pair("20260513T120000Z-proj")
    pre, post, cleanup = resolve_pair_paths("20260513T120000Z-proj")
    try:
        assert pre.is_dir() and post.is_dir()
        assert (pre / "MEMORY.md").read_text() == "a\nb\nc\n"
        assert (post / "MEMORY.md").read_text() == "a\n"
        tmp_marker = pre.parent
    finally:
        cleanup()
    assert not tmp_marker.exists(), "tempdir should be removed by cleanup"


def test_resolve_missing_raises(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    with pytest.raises(FileNotFoundError, match="ghost-pair"):
        resolve_pair_paths("ghost-pair")


def test_pair_paths_contextmanager(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    _tar_pair("20260513T120000Z-proj")
    tmp_marker: list[Path] = []
    with pair_paths("20260513T120000Z-proj") as (pre, post):
        assert pre.is_dir()
        tmp_marker.append(pre.parent)
    assert not tmp_marker[0].exists()


def test_dream_diff_works_on_tar(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    _tar_pair("20260513T120000Z-proj")
    r = CliRunner().invoke(app, ["dream", "diff", "20260513T120000Z-proj"])
    assert r.exit_code == 0, r.stdout
    assert "MEMORY.md" in r.stdout


def test_dream_rollback_works_on_tar(tmp_path, monkeypatch):
    mem = _seed(tmp_path, monkeypatch)
    _tar_pair("20260513T120000Z-proj")
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    r = CliRunner().invoke(
        app, ["dream", "rollback", "20260513T120000Z-proj", "--apply"]
    )
    assert r.exit_code == 0, r.stdout
    # Restored "pre" content (a/b/c)
    assert (mem / "MEMORY.md").read_text() == "a\nb\nc\n"
