from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from ..core.audit import AuditLog
from ..core.safety import is_confirmed
from ..core.state import get_paths


@contextmanager
def audit_action(cmd: str, args: list[str]) -> Iterator[dict]:
    """Context manager that records the result of a CLI mutation to audit log.

    Yields a dict the caller can populate with extra ``changed`` info; the
    final entry is written to the audit log when the context exits, regardless
    of success or exception. Exit code is 0 on success, 1 on exception.
    """
    paths = get_paths()
    paths.ensure_dirs()
    log = AuditLog(paths.audit_log)
    changed: dict = {}
    exit_code = 0
    try:
        yield changed
    except SystemExit as e:
        exit_code = int(e.code) if e.code is not None else 0
        raise
    except BaseException as e:
        # typer.Exit / click.exceptions.Exit carry an `exit_code` attribute
        ec = getattr(e, "exit_code", None)
        exit_code = int(ec) if ec is not None else 1
        raise
    finally:
        log.record(
            mode="cli",
            user_confirmed=is_confirmed(),
            cmd=cmd,
            args=args,
            exit_code=exit_code,
            changed=changed if changed else None,
        )
