from typer.testing import CliRunner

from cc_janitor.cli import app


def test_session_list(mock_claude_home):
    r = CliRunner().invoke(app, ["session", "list"])
    assert r.exit_code == 0
    assert "abc123" in r.stdout
    assert "def456" in r.stdout


def test_session_show(mock_claude_home):
    r = CliRunner().invoke(app, ["session", "show", "abc123"])
    assert r.exit_code == 0
    assert "abc123" in r.stdout


def test_session_summary(mock_claude_home):
    r = CliRunner().invoke(app, ["session", "summary", "def456"])
    assert r.exit_code == 0
    assert "git status" in r.stdout or "tree clean" in r.stdout


def test_session_delete_blocked_without_confirm(mock_claude_home, monkeypatch):
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    r = CliRunner().invoke(app, ["session", "delete", "abc123"])
    assert r.exit_code != 0


def test_session_search(mock_claude_home):
    r = CliRunner().invoke(app, ["session", "search", "git"])
    assert r.exit_code == 0
    assert "def456" in r.stdout


def test_session_prune_dry_run(mock_claude_home):
    r = CliRunner().invoke(app, ["session", "prune", "--older-than", "1d", "--dry-run"])
    assert r.exit_code == 0
    from cc_janitor.core.sessions import discover_sessions
    assert any(s.id == "abc123" for s in discover_sessions())
