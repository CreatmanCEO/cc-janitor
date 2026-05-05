from typer.testing import CliRunner
from cc_janitor.cli import app


def test_perms_audit(mock_claude_home):
    r = CliRunner().invoke(app, ["perms", "audit"])
    assert r.exit_code == 0
    assert "rules" in r.stdout.lower() or "stale" in r.stdout.lower()


def test_perms_list_stale(mock_claude_home):
    r = CliRunner().invoke(app, ["perms", "list", "--stale"])
    assert r.exit_code == 0
    assert "ssh user@old-host" in r.stdout


def test_perms_list_filter_by_source(mock_claude_home):
    r = CliRunner().invoke(app, ["perms", "list", "--source", "user-local"])
    assert r.exit_code == 0
    assert "git" in r.stdout


def test_perms_dedupe_dry_run(mock_claude_home):
    r = CliRunner().invoke(app, ["perms", "dedupe", "--dry-run"])
    assert r.exit_code == 0
    assert "subsumed" in r.stdout.lower() or "exact" in r.stdout.lower() or "empty" in r.stdout.lower()


def test_perms_prune_dry_run(mock_claude_home):
    r = CliRunner().invoke(app, ["perms", "prune", "--older-than", "90d", "--dry-run"])
    assert r.exit_code == 0
    assert "ssh user@old-host" in r.stdout
