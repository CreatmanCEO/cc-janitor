from __future__ import annotations

import os

import typer
from click.shell_completion import ShellComplete, get_completion_class

from ...core.safety import NotConfirmedError, require_confirmed
from .._audit import audit_action

completions_app = typer.Typer(
    no_args_is_help=True,
    help="Shell completion install/show",
)

VALID_SHELLS = ("bash", "zsh", "fish", "powershell")


def _generate(shell: str) -> str:
    """Use Click's shell-completion API directly to render the source script.

    This mirrors what `_CC_JANITOR_COMPLETE=<shell>_source` would emit when
    Click's completion hook fires, but does so in-process so it works
    regardless of how cc-janitor was launched (python -m, console script,
    pytest)."""
    # Lazy import to avoid module-level circular import with cli.__init__.
    from .. import app as root_app

    # Typer's app exposes the underlying Click group lazily; fetching it
    # via main() construction path:
    from typer.main import get_command

    click_cmd = get_command(root_app)
    cls = get_completion_class(shell)
    if cls is None:
        raise RuntimeError(f"No completion class for shell: {shell}")
    comp: ShellComplete = cls(
        cli=click_cmd,
        ctx_args={},
        prog_name="cc-janitor",
        complete_var="_CC_JANITOR_COMPLETE",
    )
    return comp.source()


@completions_app.command("show")
def show(shell: str) -> None:
    if shell not in VALID_SHELLS:
        typer.echo(
            f"Unknown shell: {shell}. Choose: {list(VALID_SHELLS)}",
            err=True,
        )
        raise typer.Exit(code=2)
    typer.echo(_generate(shell))


@completions_app.command("install")
def install(shell: str) -> None:
    with audit_action("completions install", [shell]) as changed:
        if shell not in VALID_SHELLS:
            typer.echo(
                f"Unknown shell: {shell}. Choose: {list(VALID_SHELLS)}",
                err=True,
            )
            raise typer.Exit(code=2)
        try:
            require_confirmed()
        except NotConfirmedError as e:
            typer.echo(str(e), err=False)
            raise typer.Exit(code=2) from e
        script = _generate(shell)
        home = os.path.expanduser("~")
        if shell == "bash":
            target = os.path.join(home, ".bash_completion.d", "cc-janitor")
        elif shell == "zsh":
            target = os.path.join(home, ".zfunc", "_cc-janitor")
        elif shell == "fish":
            target = os.path.join(
                home, ".config", "fish", "completions", "cc-janitor.fish"
            )
        else:  # powershell
            target = os.path.join(
                home, "Documents", "PowerShell", "cc-janitor-completion.ps1"
            )
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(script)
        changed["target"] = target
        typer.echo(f"Wrote completion script to {target}")
        typer.echo("Restart your shell or source the file to activate.")
