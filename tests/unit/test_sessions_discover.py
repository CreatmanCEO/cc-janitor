from __future__ import annotations


def test_discover_returns_sessions(mock_claude_home):
    from cc_janitor.core.sessions import discover_sessions
    sessions = discover_sessions()
    assert len(sessions) >= 2
    ids = {s.id for s in sessions}
    assert {"abc123", "def456"} <= ids


def test_discover_respects_project_filter(mock_claude_home):
    from cc_janitor.core.sessions import discover_sessions
    sessions = discover_sessions(project="test-proj")
    assert all(s.project == "test-proj" for s in sessions)


def test_cache_avoids_re_parsing(mock_claude_home):
    from cc_janitor.core.sessions import discover_sessions
    discover_sessions()  # warm cache
    p = mock_claude_home / ".claude" / "projects" / "test-proj" / "abc123.jsonl"
    original_mtime = p.stat().st_mtime
    p.write_text("garbage")
    import os
    os.utime(p, (original_mtime, original_mtime))  # restore mtime so cache stays valid
    cached = discover_sessions()
    assert any(s.id == "abc123" and "hi" in s.first_user_msg for s in cached)
