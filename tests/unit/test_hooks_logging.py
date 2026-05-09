import json

from cc_janitor.core.hooks import disable_logging, enable_logging


def test_enable_logging_wraps_command(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    enable_logging("PreToolUse", matcher="Bash")
    settings_p = mock_claude_home / ".claude" / "settings.json"
    data = json.loads(settings_p.read_text(encoding="utf-8"))
    cmd = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "cc-janitor/hooks-log" in cmd
    assert "cc-janitor-original:" in cmd  # sentinel for disable


def test_disable_logging_restores(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    enable_logging("PreToolUse", matcher="Bash")
    disable_logging("PreToolUse", matcher="Bash")
    settings_p = mock_claude_home / ".claude" / "settings.json"
    data = json.loads(settings_p.read_text(encoding="utf-8"))
    cmd = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "cc-janitor/hooks-log" not in cmd
    assert cmd == "echo hi"
