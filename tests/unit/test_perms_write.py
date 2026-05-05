def test_remove_rule_writes_backup_and_removes(mock_claude_home, monkeypatch):
    from cc_janitor.core.permissions import discover_rules, remove_rule
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    rules = discover_rules()
    target = next(r for r in rules if r.pattern == "ssh user@old-host:*")
    remove_rule(target)

    new_rules = discover_rules()
    assert all(r.pattern != "ssh user@old-host:*" for r in new_rules)

    # backup created
    from cc_janitor.core.state import get_paths
    paths = get_paths()
    backups = list(paths.backups.rglob("*.bak"))
    assert len(backups) >= 1


def test_remove_rule_requires_confirmed(mock_claude_home, monkeypatch):
    from cc_janitor.core.permissions import discover_rules, remove_rule
    from cc_janitor.core.safety import NotConfirmedError
    import pytest
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    rules = discover_rules()
    with pytest.raises(NotConfirmedError):
        remove_rule(rules[0])


def test_add_rule_creates_file_if_missing(mock_claude_home, monkeypatch, tmp_path):
    """Adding a rule to a scope whose file does not yet exist should create it."""
    from cc_janitor.core.permissions import add_rule, discover_rules
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    # Remove the existing user/settings.json (it exists but might be empty)
    user_settings = mock_claude_home / ".claude" / "settings.json"
    if user_settings.exists():
        user_settings.unlink()

    add_rule("Bash(uv *)", scope="user", decision="allow")

    rules_after = discover_rules()
    user_rules = [r for r in rules_after if r.source.scope == "user"]
    assert any(r.pattern == "uv *" for r in user_rules)


def test_remove_approved_tool(mock_claude_home, monkeypatch):
    """Approved-tools (~/.claude.json approvedTools array) deletion path."""
    from cc_janitor.core.permissions import discover_rules, remove_rule
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    rules = discover_rules()
    target = next(r for r in rules if r.source.scope == "approved-tools" and r.raw == "Bash(echo *)")
    remove_rule(target)

    new_rules = discover_rules()
    assert not any(r.source.scope == "approved-tools" and r.raw == "Bash(echo *)" for r in new_rules)
