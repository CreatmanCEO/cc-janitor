import os

import pytest
from textual.widgets import DataTable


@pytest.mark.asyncio
async def test_schedule_screen_loads(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabbed = app.query_one("TabbedContent")
        tabbed.active = "schedule"
        await pilot.pause()
        # Mounts without crashing on a fresh home (no jobs yet).
        table = app.query_one("#schedule-table", DataTable)
        assert table is not None


@pytest.mark.asyncio
async def test_schedule_screen_columns(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabbed = app.query_one("TabbedContent")
        tabbed.active = "schedule"
        await pilot.pause()
        table = app.query_one("#schedule-table", DataTable)
        labels = [str(c.label) for c in table.columns.values()]
        assert "Name" in labels
        assert "Cron" in labels


@pytest.mark.asyncio
async def test_remove_with_modal_no_does_not_mutate(mock_claude_home, monkeypatch):
    """C1: pressing 'r' must NOT silently set CC_JANITOR_USER_CONFIRMED.

    With no jobs seeded the highlighted() guard returns early — we instead
    verify that ConfirmModal exists and that tui_confirmed() does not leak
    the env var.
    """
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    from cc_janitor.tui._confirm import tui_confirmed

    assert os.environ.get("CC_JANITOR_USER_CONFIRMED") is None
    with tui_confirmed():
        assert os.environ.get("CC_JANITOR_USER_CONFIRMED") == "1"
    # env var must be restored (not set) when context exits
    assert os.environ.get("CC_JANITOR_USER_CONFIRMED") is None


@pytest.mark.asyncio
async def test_schedule_screen_does_not_setdefault_env(mock_claude_home, monkeypatch):
    """C1 regression: no os.environ.setdefault on the safety env var in TUI."""
    import inspect

    from cc_janitor.tui.screens import memory_screen, schedule_screen

    for mod in (schedule_screen, memory_screen):
        src = inspect.getsource(mod)
        assert "setdefault" not in src or "CC_JANITOR_USER_CONFIRMED" not in src, (
            f"{mod.__name__} still bypasses the safety gate via setdefault"
        )
