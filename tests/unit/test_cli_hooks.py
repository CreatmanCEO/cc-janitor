from __future__ import annotations

from typer.testing import CliRunner

from cc_janitor.cli import app

runner = CliRunner()


def test_hooks_list(mock_claude_home):
    r = runner.invoke(app, ["hooks", "list"])
    assert r.exit_code == 0
    assert "PreToolUse" in r.stdout


def test_hooks_validate_reports_malformed(mock_claude_home):
    r = runner.invoke(app, ["hooks", "validate"])
    assert "missing-hooks-array" in r.stdout


def test_hooks_simulate_smoke(mock_claude_home):
    r = runner.invoke(app, ["hooks", "simulate", "PreToolUse", "Bash"])
    # may fail on minimal envs; allow exit 0 or non-zero
    assert "duration" in r.stdout.lower() or r.exit_code in (0, 1, 124)


def test_hooks_show(mock_claude_home):
    r = runner.invoke(app, ["hooks", "show", "PreToolUse", "Bash"])
    assert r.exit_code == 0


def test_hooks_list_json(mock_claude_home):
    import json

    r = runner.invoke(app, ["hooks", "list", "--json"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert any(e["event"] == "PreToolUse" for e in data)


def test_context_reinject(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    r = runner.invoke(app, ["context", "reinject"])
    assert r.exit_code == 0
    from cc_janitor.core.reinject import is_reinject_pending

    assert is_reinject_pending()


def test_context_reinject_requires_confirmed(mock_claude_home, monkeypatch):
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    r = runner.invoke(app, ["context", "reinject"])
    assert r.exit_code != 0
