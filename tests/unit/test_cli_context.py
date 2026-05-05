from typer.testing import CliRunner

from cc_janitor.cli import app


def test_context_show(mock_claude_home):
    project = mock_claude_home / "myproject"
    project.mkdir(exist_ok=True)
    r = CliRunner().invoke(app, ["context", "show", "--project", str(project)])
    assert r.exit_code == 0
    assert "tokens" in r.stdout.lower() or "tok" in r.stdout.lower()


def test_context_cost(mock_claude_home):
    r = CliRunner().invoke(app, ["context", "cost"])
    assert r.exit_code == 0


def test_context_find_duplicates(mock_claude_home):
    """Should at least run without errors; output may say no dupes."""
    r = CliRunner().invoke(app, ["context", "find-duplicates"])
    assert r.exit_code == 0
