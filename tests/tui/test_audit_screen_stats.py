from datetime import date, timedelta

import pytest
from textual.widgets import Static

from cc_janitor.core.stats import StatsSnapshot, write_snapshot


def _seed(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    today = date.today()
    for i in range(5):
        write_snapshot(StatsSnapshot(
            date=today - timedelta(days=4 - i),
            sessions_count=10 + i, perm_rules_count=200 - i,
            context_tokens=12000 - i*100, trash_bytes=1_000_000 + i*1000,
            audit_entries_since_last=i,
        ))


@pytest.mark.asyncio
async def test_audit_screen_renders_sparklines(mock_claude_home, tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from cc_janitor.tui.app import CcJanitorApp
    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one("#audit-sparklines", Static)
        text = str(panel.render())
        assert "Sessions" in text
        assert "Perm rules" in text


@pytest.mark.asyncio
async def test_audit_screen_toggle_hides_sparklines(mock_claude_home, tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from cc_janitor.tui.app import CcJanitorApp
    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        panel = app.query_one("#audit-sparklines", Static)
        assert panel.display
        from cc_janitor.tui.screens.audit_screen import AuditScreen
        screen = app.query_one(AuditScreen)
        screen.action_toggle_sparklines()
        await pilot.pause()
        assert not panel.display
