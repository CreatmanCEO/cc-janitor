from __future__ import annotations

from typer.testing import CliRunner

from cc_janitor.cli import app

runner = CliRunner()


def test_schedule_list_empty(mock_claude_home, monkeypatch):
    import cc_janitor.core.schedule as schedmod

    monkeypatch.setattr(schedmod, "get_scheduler", lambda: schedmod.CronScheduler())
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: type(
            "R", (), {"returncode": 0, "stdout": b"", "stderr": b""}
        )(),
    )
    r = runner.invoke(app, ["schedule", "list"])
    assert r.exit_code == 0


def test_schedule_add_unknown_template(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    r = runner.invoke(app, ["schedule", "add", "no-such-template"])
    assert r.exit_code != 0


def test_schedule_list_json(mock_claude_home, monkeypatch):
    import cc_janitor.core.schedule as schedmod

    monkeypatch.setattr(schedmod, "get_scheduler", lambda: schedmod.CronScheduler())
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: type(
            "R", (), {"returncode": 0, "stdout": b"", "stderr": b""}
        )(),
    )
    import json

    r = runner.invoke(app, ["schedule", "list", "--json"])
    assert r.exit_code == 0
    assert json.loads(r.stdout) == []


def test_schedule_promote_missing(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    r = runner.invoke(app, ["schedule", "promote", "no-such-job"])
    assert r.exit_code != 0
