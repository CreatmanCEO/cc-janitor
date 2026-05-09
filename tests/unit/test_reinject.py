from __future__ import annotations

from cc_janitor.core.reinject import clear_reinject, is_reinject_pending, queue_reinject


def test_queue_creates_marker(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    queue_reinject()
    assert is_reinject_pending()


def test_queue_is_idempotent(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    queue_reinject()
    queue_reinject()
    queue_reinject()
    assert is_reinject_pending()


def test_clear_removes_marker(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    queue_reinject()
    clear_reinject()
    assert not is_reinject_pending()
