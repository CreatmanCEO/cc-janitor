from pathlib import Path

from cc_janitor.core.dream_diff import compute_diff


def _mk(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_compute_diff_added_removed_changed(tmp_path):
    pre = tmp_path / "pre"
    post = tmp_path / "post"
    _mk(pre / "MEMORY.md", "a\nb\nc\n")
    _mk(pre / "removed.md", "x\n")
    _mk(post / "MEMORY.md", "a\nB\nc\n")
    _mk(post / "added.md", "y\n")
    diff = compute_diff(pre, post)
    by = {str(d.rel_path): d for d in diff.deltas}
    assert by["MEMORY.md"].status == "changed"
    assert by["MEMORY.md"].lines_added == 1
    assert by["MEMORY.md"].lines_removed == 1
    assert by["MEMORY.md"].unified_diff is not None
    assert by["removed.md"].status == "removed"
    assert by["added.md"].status == "added"
    assert diff.summary["files_added"] == 1
    assert diff.summary["files_removed"] == 1
    assert diff.summary["files_changed"] == 1
