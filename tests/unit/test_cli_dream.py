import json
from datetime import datetime, timezone
from pathlib import Path
from typer.testing import CliRunner
from cc_janitor.cli import app
from cc_janitor.core.dream_snapshot import (
    snapshot_pre, snapshot_post, record_pair,
)

runner = CliRunner()


def _setup_pair(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    mem = tmp_path / ".claude" / "projects" / "-proj" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("a\nb\n")
    pre = snapshot_pre("20260511T120000Z-proj", mem)
    (mem / "MEMORY.md").write_text("a\n")
    post = snapshot_post("20260511T120000Z-proj", mem)
    record_pair("20260511T120000Z-proj", mem, project_slug="proj",
                dream_pid_in_lock=4711,
                ts_pre=datetime.now(timezone.utc),
                ts_post=datetime.now(timezone.utc),
                pre_dir=pre, post_dir=post)
    return mem


def test_dream_history(tmp_path, monkeypatch):
    _setup_pair(tmp_path, monkeypatch)
    res = runner.invoke(app, ["dream", "history", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert any(d["pair_id"] == "20260511T120000Z-proj" for d in data)


def test_dream_diff(tmp_path, monkeypatch):
    _setup_pair(tmp_path, monkeypatch)
    res = runner.invoke(app, ["dream", "diff", "20260511T120000Z-proj"])
    assert res.exit_code == 0
    assert "MEMORY.md" in res.stdout


def test_dream_doctor_json(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text("{}")
    res = runner.invoke(app, ["dream", "doctor", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert isinstance(data, list)
    assert len(data) == 9


def test_dream_rollback_requires_confirm(tmp_path, monkeypatch):
    _setup_pair(tmp_path, monkeypatch)
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    res = runner.invoke(app, ["dream", "rollback", "20260511T120000Z-proj",
                              "--apply"])
    assert res.exit_code != 0


def test_dream_rollback_dry_run(tmp_path, monkeypatch):
    _setup_pair(tmp_path, monkeypatch)
    res = runner.invoke(app, ["dream", "rollback", "20260511T120000Z-proj"])
    assert res.exit_code == 0
    assert "dry" in res.stdout.lower() or "would" in res.stdout.lower()
