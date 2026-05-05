def test_delete_session_requires_confirmed(mock_claude_home, monkeypatch):
    from cc_janitor.core.sessions import discover_sessions, delete_session
    from cc_janitor.core.safety import NotConfirmedError
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    s = discover_sessions()[0]
    import pytest
    with pytest.raises(NotConfirmedError):
        delete_session(s)


def test_delete_session_moves_to_trash(mock_claude_home, monkeypatch):
    from cc_janitor.core.sessions import discover_sessions, delete_session
    from cc_janitor.core.safety import list_trash
    from cc_janitor.core.state import get_paths
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    sessions = discover_sessions()
    s = next(s for s in sessions if s.id == "abc123")
    trash_id = delete_session(s)
    assert not s.jsonl_path.exists()
    assert any(i.id == trash_id for i in list_trash(get_paths()))


def test_delete_session_includes_related_dir(mock_claude_home, monkeypatch):
    """If <sid>/ exists with subagents, the whole bundle goes to trash together."""
    from cc_janitor.core.sessions import discover_sessions, delete_session
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    # Pre-create per-session dir for abc123
    abc_dir = mock_claude_home / ".claude" / "projects" / "test-proj" / "abc123"
    abc_dir.mkdir()
    (abc_dir / "subagents").mkdir()
    (abc_dir / "subagents" / "agent.jsonl").write_text("hello\n", encoding="utf-8")

    sessions = discover_sessions(refresh=True)  # force re-parse so related_dirs picks up the new dir
    s = next(s for s in sessions if s.id == "abc123")
    assert abc_dir in s.related_dirs

    delete_session(s)
    assert not s.jsonl_path.exists()
    assert not abc_dir.exists()  # related dir must move with the bundle
