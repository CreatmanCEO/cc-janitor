from typer.testing import CliRunner

from cc_janitor.cli import app


def test_audit_list_empty(mock_claude_home):
    r = CliRunner().invoke(app, ["audit", "list"])
    assert r.exit_code == 0  # no entries OK


def test_audit_list_after_mutation(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    CliRunner().invoke(app, ["session", "delete", "abc123"])
    r = CliRunner().invoke(app, ["audit", "list"])
    assert r.exit_code == 0
    assert "session delete" in r.stdout


def test_audit_list_filter_by_cmd(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    CliRunner().invoke(app, ["session", "delete", "abc123"])
    r = CliRunner().invoke(app, ["audit", "list", "--cmd", "session*"])
    assert r.exit_code == 0
    assert "session delete" in r.stdout


def test_audit_list_json(mock_claude_home, monkeypatch):
    import json
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    CliRunner().invoke(app, ["session", "delete", "abc123"])
    r = CliRunner().invoke(app, ["audit", "list", "--json"])
    assert r.exit_code == 0
    # at least one line should be valid JSON
    for line in r.stdout.splitlines():
        if line.strip().startswith("{"):
            json.loads(line)  # no raise
            break
    else:
        raise AssertionError("no JSON line found in --json output")


def test_audit_list_since_invalid(mock_claude_home):
    r = CliRunner().invoke(app, ["audit", "list", "--since", "invalid"])
    assert r.exit_code != 0
