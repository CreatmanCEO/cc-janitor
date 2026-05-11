import os

from typer.testing import CliRunner

from cc_janitor.cli import app

runner = CliRunner()


def test_start_requires_confirmation(monkeypatch, tmp_path):
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    res = runner.invoke(app, ["watch", "start"])
    assert res.exit_code != 0
    combined = (res.stdout + (res.output or "")).lower()
    assert "confirm" in combined


def test_status_when_not_running(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    res = runner.invoke(app, ["watch", "status"])
    assert res.exit_code == 0
    assert "not running" in res.stdout.lower()


def test_start_then_stop(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    # Provide a synthetic memory dir so start doesn't bail with exit 2.
    proj_root = tmp_path / "projects" / "demo" / "memory"
    proj_root.mkdir(parents=True)
    monkeypatch.setattr(
        "cc_janitor.cli.commands.watch._default_memory_dirs",
        lambda: [proj_root],
    )

    captured = {}

    def fake_spawn(args, cwd, log_path):
        captured["args"] = args
        return os.getpid()  # use our own PID — guaranteed alive

    monkeypatch.setattr("cc_janitor.core.watcher.spawn_daemon", fake_spawn)
    res = runner.invoke(app, ["watch", "start", "--interval", "5"])
    assert res.exit_code == 0, res.output
    assert (tmp_path / "watcher.pid").exists()

    # stop — but we don't actually want to kill our test process.
    monkeypatch.setattr("cc_janitor.core.watcher.kill_pid", lambda pid: None)
    res = runner.invoke(app, ["watch", "stop"])
    assert res.exit_code == 0
    assert not (tmp_path / "watcher.pid").exists()
