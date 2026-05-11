import json
from pathlib import Path
from typer.testing import CliRunner
from cc_janitor.cli import app

runner = CliRunner()


def test_stats_sleep_hygiene_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    res = runner.invoke(app, ["stats", "sleep-hygiene", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert "projects" in data
    assert data["totals"]["projects"] == 0


def test_stats_sleep_hygiene_with_data(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    mem = tmp_path / ".claude" / "projects" / "-proj" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text(
        "yesterday we did x\nrecently changed y\n", encoding="utf-8")
    res = runner.invoke(app, ["stats", "sleep-hygiene", "--json"])
    data = json.loads(res.stdout)
    assert data["totals"]["total_relative_date_matches"] >= 2
