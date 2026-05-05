from __future__ import annotations

import typer

from .commands.audit import audit_app
from .commands.context import context_app
from .commands.doctor import doctor as _doctor
from .commands.install_hooks import install_hooks as _install_hooks
from .commands.perms import perms_app
from .commands.session import session_app
from .commands.trash import trash_app

__VERSION__ = "0.1.1"

app = typer.Typer(no_args_is_help=False, help="cc-janitor — Tidy Claude Code")


def _version_cb(value: bool):
    if value:
        typer.echo(f"cc-janitor {__VERSION__}")
        raise typer.Exit()


@app.callback()
def root(
    version: bool = typer.Option(
        False, "--version", callback=_version_cb, is_eager=True,
        help="Show version and exit",
    ),
    lang: str = typer.Option(
        None, "--lang", help="UI language: en|ru (default: auto-detect from LANG)",
    ),
) -> None:
    if lang:
        from ..i18n import set_lang
        set_lang(lang)


app.add_typer(audit_app, name="audit")
app.add_typer(context_app, name="context")
app.add_typer(perms_app, name="perms")
app.add_typer(session_app, name="session")
app.add_typer(trash_app, name="trash")
app.command("doctor", help="Health check")(_doctor)
app.command("install-hooks", help="Install reinject PreToolUse hook")(_install_hooks)
