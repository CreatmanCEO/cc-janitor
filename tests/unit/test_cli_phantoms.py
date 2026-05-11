"""Tests for 0.3.3 — implementations of two previously-phantom commands.

Per the audit's C4 finding, ``CC_USAGE.md`` referenced these commands but
they did not exist in the CLI. 0.3.3 implements them; this test file
exercises that they are wired up.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from cc_janitor.cli import app
from cc_janitor.core.state import get_paths


def test_schedule_audit_empty(mock_claude_home):
    r = CliRunner().invoke(app, ["schedule", "audit"])
    assert r.exit_code == 0
    assert "no scheduled" in r.stdout.lower()


def test_schedule_audit_filters_to_scheduled_mode(mock_claude_home):
    paths = get_paths()
    paths.ensure_dirs()
    entries = [
        {
            "ts": "2026-05-11T10:00:00+0000",
            "mode": "cli",
            "user_confirmed": True,
            "cmd": "perms prune",
            "args": [],
            "exit_code": 0,
            "session_id": None,
            "changed": None,
            "backup_path": None,
        },
        {
            "ts": "2026-05-11T11:00:00+0000",
            "mode": "scheduled",
            "user_confirmed": True,
            "cmd": "perms prune",
            "args": [],
            "exit_code": 0,
            "session_id": None,
            "changed": None,
            "backup_path": None,
        },
    ]
    with paths.audit_log.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    r = CliRunner().invoke(app, ["schedule", "audit"])
    assert r.exit_code == 0
    assert "11:00" in r.stdout
    # cli entry should NOT appear
    assert "10:00" not in r.stdout


def test_memory_delete_soft_deletes_to_trash(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    # Find a memory file in mock home
    r0 = CliRunner().invoke(app, ["memory", "list", "--json"])
    assert r0.exit_code == 0
    items = json.loads(r0.stdout)
    assert items, "mock home should provide at least one memory file"
    name = items[0]["path"].split("/")[-1].split("\\")[-1]

    r = CliRunner().invoke(app, ["memory", "delete", name])
    assert r.exit_code == 0, r.stdout + (r.stderr or "")
    assert "trash" in r.stdout.lower()


def test_memory_delete_requires_confirm(mock_claude_home, monkeypatch):
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    r0 = CliRunner().invoke(app, ["memory", "list", "--json"])
    items = json.loads(r0.stdout)
    if not items:
        return  # nothing to delete
    name = items[0]["path"].split("/")[-1].split("\\")[-1]
    r = CliRunner().invoke(app, ["memory", "delete", name])
    assert r.exit_code != 0
