from __future__ import annotations
import sys


def main() -> None:
    if len(sys.argv) > 1:
        from .cli import app
        app()
    else:
        # TUI path — deferred to Task 21. For now route to CLI help.
        from .cli import app
        app(["--help"])


if __name__ == "__main__":
    main()
