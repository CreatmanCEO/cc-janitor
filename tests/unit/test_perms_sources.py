def test_discover_rules_finds_user_local(mock_claude_home):
    from cc_janitor.core.permissions import discover_rules
    rules = discover_rules()
    sources = {r.source.scope for r in rules}
    assert "user-local" in sources
    patterns = {r.pattern for r in rules}
    assert "git *" in patterns


def test_discover_rules_distinguishes_scopes(mock_claude_home):
    from cc_janitor.core.permissions import discover_rules
    rules = discover_rules()
    by_scope = {}
    for r in rules:
        by_scope.setdefault(r.source.scope, []).append(r)
    assert "user-local" in by_scope
    # project scope from per-project settings.json
    assert "project" in by_scope or "project-local" in by_scope
    # approved-tools from .claude.json
    assert "approved-tools" in by_scope


def test_discover_rules_parses_decision(mock_claude_home):
    """allow vs deny preserved on each rule."""
    from cc_janitor.core.permissions import discover_rules
    rules = discover_rules()
    decisions = {r.decision for r in rules}
    assert "allow" in decisions
    # deny rule from project settings.json
    assert any(r.decision == "deny" and r.pattern == "rm -rf *" for r in rules)


def test_discover_rules_handles_missing_files(tmp_path, monkeypatch):
    """No claude home at all → empty list, no crash."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / ".cc-janitor"))
    from cc_janitor.core.permissions import discover_rules
    assert discover_rules() == []
