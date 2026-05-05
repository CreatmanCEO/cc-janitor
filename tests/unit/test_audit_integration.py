from __future__ import annotations


def test_session_delete_writes_audit(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    from typer.testing import CliRunner

    from cc_janitor.cli import app
    from cc_janitor.core.audit import AuditLog
    from cc_janitor.core.state import get_paths

    CliRunner().invoke(app, ["session", "delete", "abc123"])

    log = AuditLog(get_paths().audit_log)
    entries = list(log.read())
    assert any(e.cmd == "session delete" for e in entries)


def test_perms_remove_writes_audit(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    from typer.testing import CliRunner

    from cc_janitor.cli import app
    from cc_janitor.core.audit import AuditLog
    from cc_janitor.core.permissions import discover_rules
    from cc_janitor.core.state import get_paths

    rules = discover_rules()
    target = next(r for r in rules if r.pattern == "ssh user@old-host:*")
    r = CliRunner().invoke(
        app,
        ["perms", "remove", target.raw, "--from", str(target.source.path)],
    )
    assert r.exit_code == 0

    log = AuditLog(get_paths().audit_log)
    entries = list(log.read())
    assert any(e.cmd == "perms remove" for e in entries)


def test_audit_records_user_confirmed_flag(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    from typer.testing import CliRunner

    from cc_janitor.cli import app
    from cc_janitor.core.audit import AuditLog
    from cc_janitor.core.state import get_paths

    CliRunner().invoke(app, ["session", "delete", "abc123"])

    log = AuditLog(get_paths().audit_log)
    deletes = [e for e in log.read() if e.cmd == "session delete"]
    assert len(deletes) >= 1
    assert deletes[0].user_confirmed is True
