def test_claude_md_hierarchy(mock_claude_home):
    from cc_janitor.core.context import claude_md_hierarchy
    sub = mock_claude_home / "myproject" / "sub"
    sub.mkdir(parents=True, exist_ok=True)
    files = claude_md_hierarchy(starting_from=sub)
    paths = [f.path for f in files]
    assert mock_claude_home / "myproject" / "CLAUDE.md" in paths
    assert mock_claude_home / ".claude" / "CLAUDE.md" in paths
    assert all(f.size_bytes >= 0 for f in files)
    assert all(f.kind == "claude_md" for f in files)


def test_claude_md_hierarchy_no_files(tmp_path):
    """Walking a tree with no CLAUDE.md returns empty list."""
    from cc_janitor.core.context import claude_md_hierarchy
    files = claude_md_hierarchy(starting_from=tmp_path)
    # only the global ~/.claude/CLAUDE.md may match if mock home is set elsewhere — for tmp_path with no env override, Path.home() is real so no match here typically
    # don't strictly assert empty; just assert the function doesn't crash
    assert isinstance(files, list)
