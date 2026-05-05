from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) > 1:
        from .cli import app
        app()
    else:
        from .tui.app import run
        run()


if __name__ == "__main__":
    main()
