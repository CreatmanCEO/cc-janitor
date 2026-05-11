from __future__ import annotations

import os
import sys


def main() -> None:
    # When Click's shell-completion hook is active (env var set by the
    # shell completion script), let the Typer/Click app handle it so it
    # can emit the completion script and exit.
    if len(sys.argv) > 1 or os.environ.get("_CC_JANITOR_COMPLETE"):
        from .cli import app
        app()
    else:
        from .tui.app import run
        run()


if __name__ == "__main__":
    main()
