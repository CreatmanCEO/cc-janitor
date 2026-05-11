import time
from datetime import datetime, timezone
from pathlib import Path

from cc_janitor.core.watcher import (
    WatcherStatus,
    iter_watched_files,
    read_status,
    run_watcher_once,
    write_status,
)


def test_status_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    s = WatcherStatus(
        pid=4711,
        started_at=datetime.now(timezone.utc),
        watching_paths=[tmp_path / "a"],
        interval_seconds=30,
        marker_writes_count=0,
        last_change_at=None,
        is_alive=True,
    )
    write_status(s)
    s2 = read_status()
    assert s2 is not None
    assert s2.pid == 4711
    assert s2.interval_seconds == 30


def test_iter_watched_files_finds_md(tmp_path):
    d = tmp_path / "memory"
    d.mkdir()
    (d / "a.md").write_text("x")
    (d / "b.md").write_text("y")
    (d / "ignore.txt").write_text("z")
    files = list(iter_watched_files([d]))
    assert {f.name for f in files} == {"a.md", "b.md"}


def test_run_once_writes_marker_on_change(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    (tmp_path / "jhome").mkdir()
    mem = tmp_path / "memory"
    mem.mkdir()
    f = mem / "MEMORY.md"
    f.write_text("v1")
    last: dict[Path, float] = {}
    # First call records mtime; no marker.
    run_watcher_once([mem], last)
    assert not (tmp_path / "jhome" / "reinject-pending").exists()
    # Touch — bump mtime, second call writes marker.
    time.sleep(0.05)
    f.write_text("v2")
    run_watcher_once([mem], last)
    assert (tmp_path / "jhome" / "reinject-pending").exists()
