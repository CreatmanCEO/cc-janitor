from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from ...core.safety import require_confirmed

REINJECT_PAYLOAD = (
    '{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
    '"additionalContext":"cc-janitor-reinject: please re-read MEMORY.md and CLAUDE.md"}}'
)


def _build_hook_command(platform: str) -> str:
    if platform == "win32":
        ps = (
            "if (Test-Path \"$env:USERPROFILE\\.cc-janitor\\reinject-pending\") {"
            " Remove-Item \"$env:USERPROFILE\\.cc-janitor\\reinject-pending\";"
            f" '{REINJECT_PAYLOAD}'"
            " }"
        )
        return f'powershell.exe -NoProfile -Command "{ps}"'
    return (
        "test -f ~/.cc-janitor/reinject-pending && "
        "{ rm ~/.cc-janitor/reinject-pending; "
        f"echo '{REINJECT_PAYLOAD}'; }} || true"
    )


def install_hooks() -> None:
    """Install the reinject PreToolUse hook (idempotent, cross-platform)."""
    require_confirmed()
    settings = Path.home() / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    d = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}

    hooks = d.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])

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
            "command": _build_hook_command(sys.platform),
            "timeout": 5,
        }],
    })

    settings.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    typer.echo(f"installed reinject hook in {settings}")
