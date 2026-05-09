from __future__ import annotations

from cc_janitor.core.memory import discover_memory_files, find_duplicate_lines


def test_discover_finds_three(mock_claude_home):
    items = discover_memory_files()
    names = {i.path.name for i in items}
    assert {"MEMORY.md", "feedback_no_emojis.md", "project_phase2_notes.md"} <= names


def test_discover_filter_by_type(mock_claude_home):
    items = discover_memory_files(type_filter="feedback")
    assert all(i.type == "feedback" for i in items)
    assert any(i.path.name == "feedback_no_emojis.md" for i in items)


def test_find_duplicates_detects_repeated_lines(tmp_path):
    a = tmp_path / "a.md"
    a.write_text("- shared bullet line\nunique a\n")
    b = tmp_path / "b.md"
    b.write_text("- shared bullet line\nunique b\n")
    dups = find_duplicate_lines([a, b])
    assert any("shared bullet line" in d.line for d in dups)
    assert all(len(d.files) >= 2 for d in dups)
