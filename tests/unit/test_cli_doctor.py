from typer.testing import CliRunner
from cc_janitor.cli import app


def test_doctor_runs(mock_claude_home):
    r = CliRunner().invoke(app, ["doctor"])
    assert r.exit_code == 0
    assert "Python" in r.stdout
    assert "Sessions" in r.stdout


def test_install_hooks_requires_confirm(mock_claude_home, monkeypatch):
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    r = CliRunner().invoke(app, ["install-hooks"])
    assert r.exit_code != 0


def test_install_hooks_creates_hook(mock_claude_home, monkeypatch):
    import json
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    r = CliRunner().invoke(app, ["install-hooks"])
    assert r.exit_code == 0
    settings = mock_claude_home / ".claude" / "settings.json"
    d = json.loads(settings.read_text(encoding="utf-8"))
    assert "hooks" in d and "PreToolUse" in d["hooks"]
    # idempotency: second invocation does not duplicate
    r2 = CliRunner().invoke(app, ["install-hooks"])
    assert r2.exit_code == 0
    d2 = json.loads(settings.read_text(encoding="utf-8"))
    assert len(d2["hooks"]["PreToolUse"]) == len(d["hooks"]["PreToolUse"])
