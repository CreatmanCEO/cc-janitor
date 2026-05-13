import os

import pytest
from textual.widgets import DataTable


@pytest.mark.asyncio
async def test_memory_screen_loads(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabbed = app.query_one("TabbedContent")
        tabbed.active = "memory"
        await pilot.pause()
        table = app.query_one("#memory-table", DataTable)
        # Mock home should expose at least the global CLAUDE.md
        assert table.row_count >= 1


@pytest.mark.asyncio
async def test_memory_screen_columns(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabbed = app.query_one("TabbedContent")
        tabbed.active = "memory"
        await pilot.pause()
        table = app.query_one("#memory-table", DataTable)
        labels = [str(c.label) for c in table.columns.values()]
        assert "Type" in labels
        assert "Name" in labels


@pytest.mark.asyncio
async def test_memory_reinject_no_longer_setdefaults_env(mock_claude_home, monkeypatch):
    """C1: action_reinject must no longer call os.environ.setdefault."""
    import inspect

    from cc_janitor.tui.screens import memory_screen

    src = inspect.getsource(memory_screen.MemoryScreen.action_reinject)
    assert "setdefault" not in src, "Memory screen still bypasses safety gate"
    assert "ConfirmModal" in src, "Memory screen must prompt via ConfirmModal"


@pytest.mark.asyncio
async def test_tui_confirmed_restores_prior_env(monkeypatch):
    """tui_confirmed() must not leak CC_JANITOR_USER_CONFIRMED to subsequent calls."""
    from cc_janitor.tui._confirm import tui_confirmed

    # Case 1: unset before → unset after
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    with tui_confirmed():
        assert os.environ["CC_JANITOR_USER_CONFIRMED"] == "1"
    assert "CC_JANITOR_USER_CONFIRMED" not in os.environ

    # Case 2: pre-set with value X → still X after
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    with tui_confirmed():
        assert os.environ["CC_JANITOR_USER_CONFIRMED"] == "1"
    assert os.environ["CC_JANITOR_USER_CONFIRMED"] == "1"


@pytest.mark.asyncio
async def test_memory_bindings_no_phantoms(mock_claude_home):
    """C4: BINDINGS must only declare actions that are actually implemented."""
    from cc_janitor.tui.screens.memory_screen import MemoryScreen

    keys = {b[0] for b in MemoryScreen.BINDINGS}
    assert keys == {"r", "a", "f"}, (
        f"Memory BINDINGS should be {{r, a, f}} after C4; got {keys}"
    )
    for binding in MemoryScreen.BINDINGS:
        action_name = f"action_{binding[1]}"
        assert hasattr(MemoryScreen, action_name), (
            f"Binding {binding!r} declared but {action_name} not implemented"
        )


@pytest.mark.asyncio
async def test_memory_find_dupes_toggle(mock_claude_home):
    """C4: pressing `f` toggles the duplicate-line preview pane."""
    from textual.widgets import Static

    from cc_janitor.tui.app import CcJanitorApp
    from cc_janitor.tui.screens.memory_screen import MemoryScreen

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        tabbed = app.query_one("TabbedContent")
        tabbed.active = "memory"
        await pilot.pause()
        screen = app.query_one(MemoryScreen)
        preview = app.query_one("#memory-preview", Static)

        assert not getattr(screen, "_dupes_open", False)
        screen.action_find_dupes()
        await pilot.pause()
        assert screen._dupes_open is True

        # Toggle off
        screen.action_find_dupes()
        await pilot.pause()
        assert screen._dupes_open is False
        assert preview is not None


@pytest.mark.asyncio
async def test_memory_archive_uses_confirm_modal(mock_claude_home, monkeypatch):
    """C4: action_archive must route through ConfirmModal."""
    import inspect

    from cc_janitor.tui.screens import memory_screen

    src = inspect.getsource(memory_screen.MemoryScreen.action_archive)
    assert "ConfirmModal" in src
    assert "tui_confirmed" in src


@pytest.mark.asyncio
async def test_reinject_does_not_run_when_modal_cancels(mock_claude_home, monkeypatch):
    """Modal returning False must abort the reinject — no marker file written."""
    from cc_janitor.core.reinject import is_reinject_pending
    from cc_janitor.tui.app import CcJanitorApp
    from cc_janitor.tui.screens.memory_screen import MemoryScreen

    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.query_one(MemoryScreen)

        # Simulate the modal returning False (user said No)
        pushed: list = []

        def fake_push(modal, callback):
            pushed.append(modal)
            callback(False)

        screen.app.push_screen = fake_push  # type: ignore[method-assign]
        screen.action_reinject()
        await pilot.pause()

    assert not is_reinject_pending(), "Reinject must NOT run when modal returns False"
    # Env var must not have been leaked
    assert "CC_JANITOR_USER_CONFIRMED" not in os.environ
