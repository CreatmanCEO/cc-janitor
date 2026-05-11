"""TUI Source filter dropdown — Permissions/Hooks/Memory tabs.

The dropdown sits at the top of each tab and lets the user opt into
``real``, ``real+nested``, or ``all (incl. junk)`` monorepo scopes. The
default is ``real`` so existing behavior is preserved.
"""
from __future__ import annotations

import pytest
from textual.widgets import Select


@pytest.mark.asyncio
async def test_perms_screen_has_source_filter(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        sel = app.query_one("#perms-source-filter", Select)
        assert sel.value == "real"


@pytest.mark.asyncio
async def test_hooks_screen_has_source_filter(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Activate Hooks tab so the screen mounts.
        app.query_one("TabbedContent").active = "hooks"
        await pilot.pause()
        sel = app.query_one("#hooks-source-filter", Select)
        assert sel.value == "real"


@pytest.mark.asyncio
async def test_memory_screen_has_source_filter(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("TabbedContent").active = "memory"
        await pilot.pause()
        sel = app.query_one("#memory-source-filter", Select)
        assert sel.value == "real"


@pytest.mark.asyncio
async def test_perms_source_filter_options_include_static_entries(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp

    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        sel = app.query_one("#perms-source-filter", Select)
        values = {value for _label, value in sel._options}  # noqa: SLF001
        assert {"real", "real+nested", "all"}.issubset(values)
