"""Tests for ``cc-janitor undo`` (0.3.3 — C3)."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from cc_janitor.cli import app
from cc_janitor.core.state import get_paths


def test_undo_with_empty_audit_log_friendly_error(mock_claude_home):
    r = CliRunner().invoke(app, ["undo"])
    assert r.exit_code != 0
    assert "empty" in r.stdout.lower() or "empty" in (r.stderr or "").lower() or \
           "nothing" in r.stdout.lower() or "nothing" in (r.stderr or "").lower()


def test_undo_session_delete_restores(mock_claude_home, monkeypatch):
    """End-to-end: delete a session, then undo → file back on disk."""
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")

    # Delete a session
    r1 = CliRunner().invoke(app, ["session", "delete", "abc123"])
    assert r1.exit_code == 0

    # The session jsonl is now in trash; original gone
    # Apply undo
    r2 = CliRunner().invoke(app, ["undo", "--apply"])
    assert r2.exit_code == 0, r2.stdout + (r2.stderr or "")
    assert "undo applied" in r2.stdout.lower()


def test_undo_dry_run_does_not_mutate(mock_claude_home, monkeypatch):
    """Without --apply, undo must only print the plan."""
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    CliRunner().invoke(app, ["session", "delete", "abc123"])

    r = CliRunner().invoke(app, ["undo"])
    assert r.exit_code == 0
    assert "dry run" in r.stdout.lower() or "--apply" in r.stdout

    # Trash bucket still has the entry — undo did not run
    r_trash = CliRunner().invoke(app, ["trash", "list"])
    # Not empty
    assert "empty" not in r_trash.stdout.lower()


def test_undo_requires_confirmed_on_apply(mock_claude_home, monkeypatch):
    """--apply without CC_JANITOR_USER_CONFIRMED=1 must refuse."""
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    CliRunner().invoke(app, ["session", "delete", "abc123"])

    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    r = CliRunner().invoke(app, ["undo", "--apply"])
    assert r.exit_code != 0


def test_undo_no_reversible_entry(mock_claude_home, monkeypatch):
    """If only non-reversible commands are in the audit log, refuse."""
    # Write a fake audit entry for a non-reversible cmd (memory edit)
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    paths = get_paths()
    paths.ensure_dirs()
    entry = {
        "ts": "2026-05-11T10:00:00+0000",
        "mode": "cli",
        "user_confirmed": True,
        "cmd": "memory edit",
        "args": ["/tmp/foo.md"],
        "exit_code": 0,
        "session_id": None,
        "changed": None,
        "backup_path": None,
    }
    paths.audit_log.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    r = CliRunner().invoke(app, ["undo"])
    assert r.exit_code != 0


def test_undo_with_entry_id_selects_older(mock_claude_home, monkeypatch):
    """An explicit entry_id should select an older entry than the most recent."""
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    paths = get_paths()
    paths.ensure_dirs()
    older = {
        "ts": "2026-05-10T10:00:00+0000",
        "mode": "cli",
        "user_confirmed": True,
        "cmd": "session delete",
        "args": ["x"],
        "exit_code": 0,
        "session_id": None,
        "changed": {"deleted": [{"id": "x", "trash_id": "nonexistent-id"}]},
        "backup_path": None,
    }
    newer = {
        "ts": "2026-05-11T10:00:00+0000",
        "mode": "cli",
        "user_confirmed": True,
        "cmd": "memory edit",
        "args": ["/tmp/foo.md"],
        "exit_code": 0,
        "session_id": None,
        "changed": None,
        "backup_path": None,
    }
    with paths.audit_log.open("w", encoding="utf-8") as f:
        f.write(json.dumps(older) + "\n")
        f.write(json.dumps(newer) + "\n")

    # Without entry_id: newer is non-reversible, falls back to older
    r = CliRunner().invoke(app, ["undo"])
    assert r.exit_code == 0
    assert "2026-05-10" in r.stdout

    # With entry_id selecting older
    r2 = CliRunner().invoke(app, ["undo", "2026-05-10"])
    assert r2.exit_code == 0
    assert "2026-05-10" in r2.stdout


def test_undo_dream_rollback_restores_memory(tmp_path, monkeypatch):
    """0.4.2: dream rollback is reversible via cc-janitor undo."""
    from datetime import UTC, datetime
    from pathlib import Path

    from cc_janitor.core.dream_snapshot import (
        record_pair, snapshot_post, snapshot_pre,
    )

    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")

    mem = tmp_path / ".claude" / "projects" / "-proj" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("pre-content\n")
    pre = snapshot_pre("p1", mem)
    (mem / "MEMORY.md").write_text("post-content\n")
    post = snapshot_post("p1", mem)
    record_pair("p1", mem, project_slug="proj", dream_pid_in_lock=1,
                ts_pre=datetime.now(UTC), ts_post=datetime.now(UTC),
                pre_dir=pre, post_dir=post)

    # Rollback — memory is now pre-content
    r1 = CliRunner().invoke(app, ["dream", "rollback", "p1", "--apply"])
    assert r1.exit_code == 0, r1.stdout
    assert (mem / "MEMORY.md").read_text() == "pre-content\n"

    # Undo — memory should be back to post-content
    r2 = CliRunner().invoke(app, ["undo", "--apply"])
    assert r2.exit_code == 0, r2.stdout + (r2.stderr or "")
    assert (mem / "MEMORY.md").read_text() == "post-content\n"
