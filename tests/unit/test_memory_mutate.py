from __future__ import annotations

import frontmatter

from cc_janitor.core.memory import (
    archive_memory_file,
    move_memory_type,
    open_in_editor,
)


def test_archive_moves_to_dot_archive(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    p = mock_claude_home / ".claude" / "projects" / "test-proj" / "memory" / "MEMORY.md"
    archived = archive_memory_file(p)
    assert not p.exists()
    assert archived.exists()
    assert ".archive" in archived.parts


def test_move_type_rewrites_frontmatter(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    p = (
        mock_claude_home
        / ".claude"
        / "projects"
        / "test-proj"
        / "memory"
        / "feedback_no_emojis.md"
    )
    move_memory_type(p, "user")
    post = frontmatter.loads(p.read_text(encoding="utf-8"))
    assert post.metadata["type"] == "user"
    assert post.metadata["description"] == "Avoid emojis in commit messages"


def test_open_in_editor_uses_env_editor(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    f = tmp_path / "x.md"
    f.write_text("# x")
    captured: dict = {}

    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setenv("EDITOR", "myeditor")
    open_in_editor(f)
    assert captured["cmd"][0] == "myeditor"
    assert captured["cmd"][1] == str(f)
