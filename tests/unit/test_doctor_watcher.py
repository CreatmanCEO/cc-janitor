import os
from datetime import datetime, timezone

from typer.testing import CliRunner

from cc_janitor.cli import app
from cc_janitor.core.watcher import WatcherStatus, write_status

runner = CliRunner()


def test_doctor_reports_no_watcher(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    res = runner.invoke(app, ["doctor"])
    assert res.exit_code == 0
    assert "Watcher" in res.stdout
    assert "not running" in res.stdout.lower()


def test_doctor_reports_running_watcher(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    s = WatcherStatus(
        pid=os.getpid(),  # alive!
        started_at=datetime.now(timezone.utc),
        watching_paths=[],
        interval_seconds=30,
        marker_writes_count=7,
        last_change_at=None,
        is_alive=True,
    )
    write_status(s)
    res = runner.invoke(app, ["doctor"])
    assert res.exit_code == 0
    assert "Watcher" in res.stdout
    assert "running" in res.stdout.lower()
    assert "7" in res.stdout
