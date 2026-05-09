from cc_janitor.core.hooks import discover_hooks, validate_hooks


def test_discover_picks_up_user_hook(mock_claude_home):
    entries = discover_hooks()
    matchers = {(e.event, e.matcher) for e in entries}
    assert ("PreToolUse", "Bash") in matchers


def test_validate_flags_malformed(mock_claude_home):
    issues = validate_hooks()
    assert any(i.kind == "missing-hooks-array" for i in issues)
