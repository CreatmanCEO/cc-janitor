from __future__ import annotations

import json

from typer.testing import CliRunner

from cc_janitor.cli import app

runner = CliRunner()


def test_memory_list_runs(mock_claude_home):
    r = runner.invoke(app, ["memory", "list"])
    assert r.exit_code == 0
    assert "MEMORY.md" in r.stdout


def test_memory_list_json(mock_claude_home):
    r = runner.invoke(app, ["memory", "list", "--json"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert any(item["path"].endswith("MEMORY.md") for item in data)


def test_memory_archive_requires_confirmed(mock_claude_home, monkeypatch):
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    r = runner.invoke(app, ["memory", "archive", "MEMORY.md"])
    assert r.exit_code != 0


def test_memory_archive_with_confirm(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    r = runner.invoke(app, ["memory", "archive", "MEMORY.md"])
    assert r.exit_code == 0


def test_memory_show(mock_claude_home):
    r = runner.invoke(app, ["memory", "show", "MEMORY.md"])
    assert r.exit_code == 0


def test_memory_find_duplicates_runs(mock_claude_home):
    r = runner.invoke(app, ["memory", "find-duplicates"])
    assert r.exit_code == 0


def test_memory_move_type(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    r = runner.invoke(app, ["memory", "move-type", "feedback_no_emojis.md", "user"])
    assert r.exit_code == 0
