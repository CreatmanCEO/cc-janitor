"""Tests for the 8th tab: ``DreamScreen`` — snapshot list + diff viewer."""
from __future__ import annotations

import json

import pytest


@pytest.mark.asyncio
async def test_app_has_eight_tabs():
    from textual.widgets import TabbedContent, TabPane

    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabbed = app.query_one(TabbedContent)
        panes = list(tabbed.query(TabPane))
        assert len(panes) == 8
        assert any(p.id == "dream" for p in panes)


@pytest.mark.asyncio
async def test_dream_screen_lists_history(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    # Seed two history entries.
    from cc_janitor.core import dream_snapshot as ds
    hp = ds._history_path()
    hp.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "pair_id": "20260501T000000Z-proj",
        "project_slug": "proj",
        "project_path": "/x/proj",
        "claude_memory_dir": "/x/proj/.claude/memory",
        "ts_pre": "2026-05-01T00:00:00+00:00",
        "ts_post": "2026-05-01T00:05:00+00:00",
        "paths_in_pre": ["MEMORY.md"],
        "paths_in_post": ["MEMORY.md"],
        "file_count_delta": 0,
        "line_count_delta": 1,
        "has_diff": True,
        "dream_pid_in_lock": 1234,
        "storage": "raw",
    }
    hp.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    # Pre/post mirrors so the diff viewer can read them.
    pre = ds._dream_root() / "20260501T000000Z-proj-pre"
    post = ds._dream_root() / "20260501T000000Z-proj-post"
    pre.mkdir(parents=True)
    post.mkdir(parents=True)
    (pre / "MEMORY.md").write_text("old\n", encoding="utf-8")
    (post / "MEMORY.md").write_text("old\nnew\n", encoding="utf-8")

    from textual.widgets import DataTable, Static

    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Activate the dream tab.
        from textual.widgets import TabbedContent
        tabbed = app.query_one(TabbedContent)
        tabbed.active = "dream"
        await pilot.pause()
        table = app.query_one("#dream-list", DataTable)
        assert table.row_count == 1
        diff_widget = app.query_one("#dream-diff", Static)
        # After mount, _show_diff_for(None) → placeholder text.
        # On row highlight (auto on first row) → real diff content.
        # Force highlight to first row.
        table.move_cursor(row=0)
        await pilot.pause()
        rendered = str(diff_widget.render())
        assert "20260501T000000Z-proj" in rendered
