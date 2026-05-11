from datetime import date, timedelta

from cc_janitor.core.stats import (
    StatsSnapshot,
    load_snapshots,
    render_sparkline,
    write_snapshot,
)


def test_render_sparkline_known_values():
    out = render_sparkline([0, 1, 2, 3, 4, 5, 6, 7], width=8)
    assert len(out) == 8
    assert out[0] == "▁"
    assert out[-1] == "█"


def test_sparkline_handles_flat():
    out = render_sparkline([5, 5, 5, 5], width=4)
    assert all(c == out[0] for c in out)


def test_sparkline_empty_returns_blank():
    assert render_sparkline([], width=10) == " " * 10


def test_snapshot_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    s = StatsSnapshot(
        date=date(2026, 5, 9),
        sessions_count=42, perm_rules_count=234,
        context_tokens=12450, trash_bytes=1245678,
        audit_entries_since_last=17,
    )
    write_snapshot(s)
    snaps = load_snapshots(since=timedelta(days=30))
    assert len(snaps) == 1
    assert snaps[0].sessions_count == 42


def test_load_filters_old(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    old = StatsSnapshot(
        date=date.today() - timedelta(days=60),
        sessions_count=1, perm_rules_count=1, context_tokens=1,
        trash_bytes=1, audit_entries_since_last=0,
    )
    new = StatsSnapshot(
        date=date.today() - timedelta(days=5),
        sessions_count=2, perm_rules_count=2, context_tokens=2,
        trash_bytes=2, audit_entries_since_last=1,
    )
    write_snapshot(old)
    write_snapshot(new)
    out = load_snapshots(since=timedelta(days=30))
    assert len(out) == 1
    assert out[0].sessions_count == 2
