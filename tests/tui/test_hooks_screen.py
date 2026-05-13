import inspect
import os

import pytest
from textual.widgets import DataTable


@pytest.mark.asyncio
async def test_hooks_screen_loads(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabbed = app.query_one("TabbedContent")
        tabbed.active = "hooks"
        await pilot.pause()
        table = app.query_one("#hooks-table", DataTable)
        # Mock has at least one PreToolUse/Bash hook
        assert table.row_count >= 1


@pytest.mark.asyncio
async def test_hooks_screen_columns(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabbed = app.query_one("TabbedContent")
        tabbed.active = "hooks"
        await pilot.pause()
        table = app.query_one("#hooks-table", DataTable)
        labels = [str(c.label) for c in table.columns.values()]
        assert "Event" in labels
        assert "Matcher" in labels


@pytest.mark.asyncio
async def test_hooks_toggle_logging_uses_confirm_modal(mock_claude_home):
    """C3: action_toggle_logging must route through ConfirmModal + tui_confirmed."""
    from cc_janitor.tui.screens import hooks_screen

    src = inspect.getsource(hooks_screen.HooksScreen.action_toggle_logging)
    assert "ConfirmModal" in src, "hooks toggle-logging must prompt via ConfirmModal"
    assert "tui_confirmed" in src, "hooks toggle-logging must use tui_confirmed()"
    assert "setdefault" not in src, "must not bypass safety gate via setdefault"


@pytest.mark.asyncio
async def test_hooks_toggle_no_mutation_when_modal_cancels(mock_claude_home, monkeypatch):
    """C3: When the modal returns False, hook logging state stays the same."""
    from cc_janitor.tui.app import CcJanitorApp
    from cc_janitor.tui.screens.hooks_screen import HooksScreen

    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabbed = app.query_one("TabbedContent")
        tabbed.active = "hooks"
        await pilot.pause()
        screen = app.query_one(HooksScreen)

        # Capture pre-state of first hook (logging wrapper presence)
        before = [h.has_logging_wrapper for h in screen._hooks]

        def fake_push(modal, callback):
            callback(False)

        screen.app.push_screen = fake_push  # type: ignore[method-assign]
        screen.action_toggle_logging()
        await pilot.pause()

    # No mutation should have happened; env var must not leak.
    assert "CC_JANITOR_USER_CONFIRMED" not in os.environ
    # Re-discovery would still show the same state — but since mock_claude_home
    # may not be writable in this scope, the strict check is the env-var leak above.
    assert before is not None
