def test_analyze_usage_marks_stale(mock_claude_home):
    from cc_janitor.core.permissions import analyze_usage, discover_rules
    from cc_janitor.core.sessions import discover_sessions
    rules = discover_rules()
    sessions = discover_sessions()
    enriched = analyze_usage(rules, sessions, stale_after_days=90)
    by_pat = {r.pattern: r for r in enriched if r.tool == "Bash"}
    # "git *" should match the def456 git status command
    assert by_pat["git *"].match_count_90d >= 1
    # "ssh user@old-host:*" never matches → stale
    assert by_pat["ssh user@old-host:*"].stale is True


def test_analyze_usage_match_command_exact():
    from cc_janitor.core.permissions import _match_command
    assert _match_command("git *", "git status") is True
    assert _match_command("git status", "git status") is True
    assert _match_command("git *", "npm test") is False
    assert _match_command("", "anything goes") is True


def test_analyze_usage_empty_sessions(mock_claude_home):
    from cc_janitor.core.permissions import analyze_usage, discover_rules
    rules = discover_rules()
    enriched = analyze_usage(rules, [], stale_after_days=90)
    # All rules with non-empty pattern should be stale (no matches)
    for r in enriched:
        if r.pattern:  # exclude empty pattern (matches anything)
            assert r.stale is True
