from typer.testing import CliRunner

from cc_janitor.cli import app


def test_version():
    r = CliRunner().invoke(app, ["--version"])
    assert r.exit_code == 0
    assert "0.4.0" in r.stdout


def test_help_works():
    r = CliRunner().invoke(app, ["--help"])
    assert r.exit_code == 0
    assert "cc-janitor" in r.stdout.lower()


def test_lang_flag(monkeypatch):
    """--lang ru sets the global language for subsequent t() calls."""
    from cc_janitor.i18n import _current_lang as _initial  # noqa
    r = CliRunner().invoke(app, ["--lang", "ru", "--help"])
    assert r.exit_code == 0
    # We don't assert specific i18n strings here — just that the flag accepted
