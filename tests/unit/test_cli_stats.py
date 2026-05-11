import json
from datetime import date, timedelta

from typer.testing import CliRunner

from cc_janitor.cli import app
from cc_janitor.core.stats import StatsSnapshot, write_snapshot

runner = CliRunner()


def _seed(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    today = date.today()
    for i in range(7):
        write_snapshot(StatsSnapshot(
            date=today - timedelta(days=6 - i),
            sessions_count=10 + i, perm_rules_count=200 - i*5,
            context_tokens=12000 - i*200, trash_bytes=1_000_000 + i*1000,
            audit_entries_since_last=i,
        ))


def test_stats_text_output(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    res = runner.invoke(app, ["stats", "--since", "30d"])
    assert res.exit_code == 0, res.stdout
    assert "Sessions" in res.stdout
    assert "Perm rules" in res.stdout


def test_stats_json_output(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    res = runner.invoke(app, ["stats", "--since", "30d", "--format", "json"])
    assert res.exit_code == 0, res.stdout
    data = json.loads(res.stdout)
    assert len(data) == 7


def test_stats_snapshot_writes_file(tmp_path, monkeypatch, mock_claude_home):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    res = runner.invoke(app, ["stats", "snapshot"])
    assert res.exit_code == 0, res.stdout
    assert (tmp_path / "history" / f"{date.today().isoformat()}.json").exists()
