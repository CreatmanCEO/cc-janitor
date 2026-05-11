"""``cc-janitor undo`` — reverse the most recent reversible audit-log entry.

Reversible commands (and their reversal strategy):

- ``session delete`` / ``session prune`` — restore each ``trash_id`` via
  :func:`core.safety.restore_from_trash`.
- ``perms remove`` / ``perms prune`` / ``perms dedupe`` — find the latest
  timestamped ``.bak`` in ``~/.cc-janitor/backups/<sha1-of-path>/`` for
  each affected ``source`` path and copy it back over the live file.
- ``memory archive`` — move the file from ``changed["archived"]["archive_path"]``
  back to ``changed["archived"]["original"]``.
- ``config import`` — restore each affected file from its
  ``backups/import-<ts>/`` snapshot (recorded in the entry's ``backup_path``).

Anything else (memory edit, perms add, hooks toggle-logging, schedule add/
remove, trash empty) is non-reversible and ``undo`` will refuse.

Defaults to ``--dry-run``; the caller must pass ``--apply`` to actually
mutate. ``CC_JANITOR_USER_CONFIRMED=1`` is required for ``--apply``.
"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Iterable
from pathlib import Path

import typer

from ...core.audit import AuditEntry, AuditLog
from ...core.safety import NotConfirmedError, require_confirmed, restore_from_trash
from ...core.state import get_paths
from .._audit import audit_action

REVERSIBLE_CMDS = {
    "session delete",
    "session prune",
    "perms remove",
    "perms prune",
    "perms dedupe",
    "memory archive",
    "config import",
}


def _is_reversible(entry: AuditEntry) -> bool:
    if entry.cmd not in REVERSIBLE_CMDS:
        return False
    if entry.exit_code != 0:
        return False
    ch = entry.changed or {}
    if entry.cmd in ("session delete", "session prune"):
        return bool(ch.get("deleted"))
    if entry.cmd in ("perms remove", "perms prune", "perms dedupe"):
        return bool(ch.get("removed"))
    if entry.cmd == "memory archive":
        return bool(ch.get("archived"))
    if entry.cmd == "config import":
        return bool(entry.backup_path or ch.get("backup_path"))
    return False


def _find_target(
    entries: Iterable[AuditEntry], entry_id: str | None
) -> AuditEntry | None:
    entries = list(entries)
    if entry_id:
        # Match by exact ts, by prefix, or by substring of ts
        for e in entries:
            if e.ts == entry_id or e.ts.startswith(entry_id) or entry_id in e.ts:
                if _is_reversible(e):
                    return e
        return None
    for e in reversed(entries):
        if _is_reversible(e):
            return e
    return None


def _latest_backup(source_path: Path) -> Path | None:
    """Return the most recent .bak in ~/.cc-janitor/backups/<sha>/."""
    paths = get_paths()
    h = hashlib.sha1(str(source_path).encode("utf-8")).hexdigest()[:12]
    bucket = paths.backups / h
    if not bucket.exists():
        return None
    candidates = sorted(bucket.glob(f"{source_path.name}.*.bak"))
    return candidates[-1] if candidates else None


def _plan(entry: AuditEntry) -> list[str]:
    """Return a human-readable plan describing the reversal steps."""
    steps: list[str] = []
    ch = entry.changed or {}
    if entry.cmd in ("session delete", "session prune"):
        for d in ch.get("deleted", []):
            steps.append(f"restore session {d['id']} from trash:{d['trash_id']}")
    elif entry.cmd in ("perms remove", "perms prune", "perms dedupe"):
        seen_sources: set[str] = set()
        for r in ch.get("removed", []):
            src = r["source"]
            if src in seen_sources:
                continue
            seen_sources.add(src)
            bak = _latest_backup(Path(src))
            if bak is None:
                steps.append(f"NO BACKUP FOUND for {src} — cannot reverse")
            else:
                steps.append(f"restore {src} <- {bak}")
    elif entry.cmd == "memory archive":
        a = ch.get("archived", {})
        steps.append(f"restore {a.get('original')} <- {a.get('archive_path')}")
    elif entry.cmd == "config import":
        bp = entry.backup_path or ch.get("backup_path")
        steps.append(f"config import: restore tree from {bp}")
    return steps


def _execute(entry: AuditEntry) -> dict:
    """Actually perform the reversal. Returns a ``changed`` dict for audit."""
    ch = entry.changed or {}
    paths = get_paths()
    result: dict = {"reversed_ts": entry.ts, "reversed_cmd": entry.cmd}

    if entry.cmd in ("session delete", "session prune"):
        restored = []
        for d in ch.get("deleted", []):
            dst = restore_from_trash(d["trash_id"], paths=paths)
            restored.append({"id": d["id"], "restored_to": str(dst)})
        result["restored"] = restored
        return result

    if entry.cmd in ("perms remove", "perms prune", "perms dedupe"):
        restored_files = []
        seen_sources: set[str] = set()
        for r in ch.get("removed", []):
            src = r["source"]
            if src in seen_sources:
                continue
            seen_sources.add(src)
            bak = _latest_backup(Path(src))
            if bak is None:
                raise RuntimeError(f"no backup available for {src}")
            shutil.copy2(bak, src)
            restored_files.append({"source": src, "from_backup": str(bak)})
        result["restored_files"] = restored_files
        return result

    if entry.cmd == "memory archive":
        a = ch.get("archived", {})
        original = Path(a["original"])
        archive_path = Path(a["archive_path"])
        if not archive_path.exists():
            raise RuntimeError(f"archived file missing: {archive_path}")
        if original.exists():
            raise FileExistsError(
                f"cannot restore: {original} now occupied"
            )
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(archive_path), str(original))
        result["restored"] = str(original)
        return result

    if entry.cmd == "config import":
        # Not implemented yet — bundle.import_bundle does not currently record
        # the backup tree path on the audit entry. Surface a friendly error.
        raise NotImplementedError(
            "config import undo requires --backup-path support (Phase 4)."
        )

    raise RuntimeError(f"not reversible: {entry.cmd}")


def undo(
    entry_id: str | None = typer.Argument(
        None, help="Audit entry ts prefix or substring; default = most recent reversible"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview only (default behaviour)"),
    apply: bool = typer.Option(False, "--apply", help="Actually execute the reversal"),
) -> None:
    """Reverse a recent mutation. Defaults to dry-run; pass ``--apply`` to execute."""
    paths = get_paths()
    log = AuditLog(paths.audit_log)
    entries = list(log.read())
    if not entries:
        typer.echo("audit log is empty — nothing to undo", err=True)
        raise typer.Exit(1)

    target = _find_target(entries, entry_id)
    if target is None:
        msg = (
            f"no reversible audit entry matches {entry_id!r}"
            if entry_id
            else "no reversible audit entry found"
        )
        typer.echo(msg, err=True)
        raise typer.Exit(1)

    typer.echo(f"target entry: {target.ts}  cmd={target.cmd}  args={target.args}")
    typer.echo("plan:")
    for step in _plan(target):
        typer.echo(f"  - {step}")

    if not apply:
        typer.echo("\n(dry run — pass --apply to execute)")
        return

    with audit_action("undo", [target.ts, target.cmd]) as changed:
        try:
            require_confirmed()
        except NotConfirmedError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(code=2) from e
        try:
            result = _execute(target)
        except Exception as e:
            typer.echo(f"undo failed: {e}", err=True)
            raise typer.Exit(code=1) from e
        changed.update(result)
    typer.echo("undo applied.")
