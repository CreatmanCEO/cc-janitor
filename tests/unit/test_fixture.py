def test_mock_home_loaded(mock_claude_home):
    assert (mock_claude_home / ".claude" / "settings.local.json").exists()
    assert (mock_claude_home / ".claude" / "projects" / "test-proj" / "abc123.jsonl").exists()
    assert (mock_claude_home / ".claude" / "projects" / "test-proj" / "def456.jsonl").exists()
