from pathlib import Path
from cc_janitor.core.memory import parse_memory_file, classify_type


def test_parse_with_frontmatter(mock_claude_home):
    p = mock_claude_home / ".claude" / "projects" / "test-proj" / "memory" / "feedback_no_emojis.md"
    m = parse_memory_file(p)
    assert m.type == "feedback"
    assert m.frontmatter["description"] == "Avoid emojis in commit messages"
    assert m.size_bytes > 0
    assert m.line_count >= 1


def test_classify_falls_back_to_filename(mock_claude_home):
    p = mock_claude_home / ".claude" / "projects" / "test-proj" / "memory" / "project_phase2_notes.md"
    m = parse_memory_file(p)
    assert m.type == "project"


def test_classify_unknown_when_no_hint(tmp_path):
    f = tmp_path / "random.md"
    f.write_text("# Hello\n", encoding="utf-8")
    m = parse_memory_file(f)
    assert m.type == "unknown"


def test_classify_helper_directly():
    assert classify_type({"type": "reference"}, Path("anything.md")) == "reference"
    assert classify_type({}, Path("research_x.md")) == "reference"
    assert classify_type({}, Path("feedback_y.md")) == "feedback"
    assert classify_type({}, Path("project_z.md")) == "project"
    assert classify_type({}, Path("MEMORY.md")) == "user"
    assert classify_type({}, Path("xyz.md")) == "unknown"
