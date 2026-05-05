from pathlib import Path
from cc_janitor.core.sessions import parse_session


def test_parse_basic(mock_claude_home):
    p = mock_claude_home / ".claude" / "projects" / "test-proj" / "abc123.jsonl"
    s = parse_session(p, project="test-proj")
    assert s.id == "abc123"
    assert s.project == "test-proj"
    assert s.message_count >= 2
    assert "hi" in s.first_user_msg


def test_parse_counts_compactions(mock_claude_home):
    p = mock_claude_home / ".claude" / "projects" / "test-proj" / "def456.jsonl"
    s = parse_session(p, project="test-proj")
    assert s.compactions == 1
    assert "git status" in s.first_user_msg or "npm test" in s.first_user_msg
