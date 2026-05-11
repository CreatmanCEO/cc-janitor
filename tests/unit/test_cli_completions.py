from __future__ import annotations

from typer.testing import CliRunner

from cc_janitor.cli import app

runner = CliRunner()


def test_completions_show_bash_prints_script():
    res = runner.invoke(app, ["completions", "show", "bash"])
    assert res.exit_code == 0
    # Click's bash completion uses _CC_JANITOR_COMPLETE env-var hook.
    assert "_CC_JANITOR" in res.stdout or "complete" in res.stdout.lower()


def test_completions_show_unknown_shell():
    res = runner.invoke(app, ["completions", "show", "tcsh"])
    assert res.exit_code != 0


def test_completions_install_requires_confirm(monkeypatch):
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    res = runner.invoke(app, ["completions", "install", "bash"])
    assert res.exit_code != 0
