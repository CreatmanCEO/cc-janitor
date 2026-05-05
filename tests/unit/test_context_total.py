def test_context_cost(mock_claude_home):
    from cc_janitor.core.context import context_cost
    project = mock_claude_home / "myproject"
    cost = context_cost(starting_from=project, claude_project_dir="test-proj")
    assert cost.total_bytes > 0
    assert cost.total_tokens > 0
    assert any(f.kind == "claude_md" for f in cost.files)
    assert any(f.kind == "memory" for f in cost.files)


def test_memory_files_lists_md(mock_claude_home):
    from cc_janitor.core.context import memory_files
    files = memory_files(claude_project_dir="test-proj")
    names = {f.path.name for f in files}
    assert "MEMORY.md" in names
    assert "project_test.md" in names
    assert all(f.kind == "memory" for f in files)


def test_enabled_skills_returns_list(mock_claude_home):
    """No skills in fixture → empty list, no crash."""
    from cc_janitor.core.context import enabled_skills
    files = enabled_skills()
    assert isinstance(files, list)
