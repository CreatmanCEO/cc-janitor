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
    original_mtime_ns = p.stat().st_mtime_ns
    original_size = p.stat().st_size
    # Replace contents with garbage padded to original size so (mtime_ns, size)
    # cache key still matches and the cache is served as-is.
    p.write_bytes(b"x" * original_size)
    import os
    os.utime(p, ns=(original_mtime_ns, original_mtime_ns))  # restore mtime so cache stays valid
    cached = discover_sessions()
    assert any(s.id == "abc123" and "hi" in s.first_user_msg for s in cached)


def test_cache_round_trips_related_dirs_and_summaries(mock_claude_home):
    """Warm-cache Session must retain related_dirs and summaries from Task 6."""
    from cc_janitor.core.sessions import discover_sessions
    # Cold parse — populates related_dirs and summaries
    sessions_cold = discover_sessions()
    cold_def = next(s for s in sessions_cold if s.id == "def456")
    assert len(cold_def.summaries) >= 1, "cold parse must have at least the compact summary"

    # Warm path — must serve from cache and preserve those fields
    sessions_warm = discover_sessions()
    warm_def = next(s for s in sessions_warm if s.id == "def456")
    assert len(warm_def.summaries) == len(cold_def.summaries)
    assert warm_def.summaries[0].source == cold_def.summaries[0].source
    assert warm_def.summaries[0].text == cold_def.summaries[0].text
    assert warm_def.related_dirs == cold_def.related_dirs


def test_cache_invalidates_on_size_change_same_mtime(mock_claude_home):
    """Cache key includes size — a same-mtime content edit triggers re-parse."""
    import os

    from cc_janitor.core.sessions import discover_sessions
    discover_sessions()  # warm
    p = mock_claude_home / ".claude" / "projects" / "test-proj" / "abc123.jsonl"
    original_mtime_ns = p.stat().st_mtime_ns
    # Append a new line — changes size, but we restore mtime
    with p.open("a", encoding="utf-8") as f:
        f.write('{"type":"user","message":{"content":"NEW MESSAGE"},"sessionId":"abc123"}\n')
    # restore mtime so float-only check would have missed the change
    os.utime(p, ns=(original_mtime_ns, original_mtime_ns))
    rs = discover_sessions()
    abc = next(s for s in rs if s.id == "abc123")
    # If cache invalidated correctly, message_count grew from 3 to 4
    assert abc.message_count == 4
