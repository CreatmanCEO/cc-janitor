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


import json


def test_parse_empty_file(tmp_path):
    """Empty JSONL file produces a Session with zero messages and no error."""
    from cc_janitor.core.sessions import parse_session
    f = tmp_path / "empty.jsonl"
    f.write_text("", encoding="utf-8")
    s = parse_session(f, project="empty")
    assert s.id == "empty"
    assert s.message_count == 0
    assert s.first_user_msg == ""
    assert s.last_user_msg == ""
    assert s.compactions == 0
    assert s.summaries == []
    assert s.started_at is None
    assert s.related_dirs == []


def test_parse_skips_truncated_partial_line(tmp_path):
    """A truncated last line should not crash; complete lines still parse."""
    from cc_janitor.core.sessions import parse_session
    f = tmp_path / "trunc.jsonl"
    payload = (
        json.dumps({"type": "user", "message": {"content": "hello"}, "sessionId": "trunc"})
        + "\n"
        + '{"type":"user","message":{"content":"truncated'  # no closing brace
    )
    f.write_text(payload, encoding="utf-8")
    s = parse_session(f, project="trunc")
    # one good line was parsed; truncated line silently dropped
    assert s.message_count == 1
    assert s.first_user_msg == "hello"


def test_parse_related_dirs_only_session_dir(tmp_path):
    """related_dirs must NOT include sibling subagents/ or tool-results/ — only <sid>/."""
    from cc_janitor.core.sessions import parse_session
    proj = tmp_path / "proj"
    proj.mkdir()
    # session jsonl
    f = proj / "sess1.jsonl"
    f.write_text(
        json.dumps({"type": "user", "message": {"content": "hi"}, "sessionId": "sess1"}) + "\n",
        encoding="utf-8",
    )
    # SIBLING dirs (project-wide) — these MUST NOT be in related_dirs
    (proj / "subagents").mkdir()
    (proj / "tool-results").mkdir()
    # PER-SESSION dir — this MUST be in related_dirs
    sess_dir = proj / "sess1"
    sess_dir.mkdir()
    (sess_dir / "subagents").mkdir()  # nested subagents — that's fine, it's inside sess_dir

    s = parse_session(f, project="proj")
    assert s.related_dirs == [sess_dir]
    assert (proj / "subagents") not in s.related_dirs
    assert (proj / "tool-results") not in s.related_dirs


def test_parse_no_user_messages(tmp_path):
    """A file with only system/summary entries: started_at=None, no first_msg summary."""
    from cc_janitor.core.sessions import parse_session
    f = tmp_path / "nouser.jsonl"
    f.write_text(
        json.dumps({"type": "system", "content": "boot"}) + "\n"
        + json.dumps({"type": "summary", "summary": "only summary"}) + "\n",
        encoding="utf-8",
    )
    s = parse_session(f, project="nouser")
    assert s.started_at is None
    assert s.first_user_msg == ""
    assert s.compactions == 1
    # only the compact summary should appear, no first_msg fallback
    assert len(s.summaries) == 1
    assert s.summaries[0].source == "jsonl_compact"
