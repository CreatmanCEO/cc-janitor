from __future__ import annotations
import typer

__VERSION__ = "0.1.0"

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


from .commands.session import session_app
app.add_typer(session_app, name="session")

from .commands.perms import perms_app
app.add_typer(perms_app, name="perms")

from .commands.context import context_app
app.add_typer(context_app, name="context")
