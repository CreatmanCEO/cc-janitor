from __future__ import annotations

import os
import sys


def main() -> None:
    # Windows console (cp1251 / cp866) cannot encode Cyrillic / CJK / emoji
    # in Claude Code paths and previews. Force UTF-8 on stdout/stderr so
    # commands like `session list` don't crash on real user data.
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            # reconfigure() is Python 3.7+; older or piped streams may fail.
            # errors="replace" downstream means worst case is mojibake, not crash.
            pass
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
