from __future__ import annotations
import json
from pathlib import Path

import typer

from ...core.safety import require_confirmed


def install_hooks() -> None:
    """Install the reinject PreToolUse hook (idempotent)."""
    require_confirmed()
    settings = Path.home() / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    if settings.exists():
        d = json.loads(settings.read_text(encoding="utf-8"))
    else:
        d = {}

    hooks = d.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])

    # idempotency: skip if cc-janitor reinject hook already present
    sentinel = "cc-janitor-reinject"
    for entry in pre:
        for h in entry.get("hooks", []):
            if isinstance(h, dict) and sentinel in (h.get("command") or ""):
                typer.echo("reinject hook already installed — nothing to do")
                return

    pre.append({
        "matcher": "*",
        "hooks": [{
            "type": "command",
            "command": (
                "test -f ~/.cc-janitor/reinject-pending && "
                "{ rm ~/.cc-janitor/reinject-pending; "
                "echo '{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"additionalContext\":\"cc-janitor-reinject: please re-read MEMORY.md and CLAUDE.md\"}}'; }"
                " || true"
            ),
            "timeout": 5,
        }],
    })

    settings.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    typer.echo(f"installed reinject hook in {settings}")
