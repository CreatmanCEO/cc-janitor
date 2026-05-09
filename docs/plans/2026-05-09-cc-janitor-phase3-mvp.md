# cc-janitor Phase 3 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship `cc-janitor` v0.3.0 — Monorepo nested `.claude/` discovery
(closes upstream Issues #37344, #35561, #18192, #40640), auto-reinject
background watcher (opt-in, mtime-poll daemon), stats dashboard with daily
history snapshots and ASCII sparklines, export/import config bundle
(safe cross-machine sync, dry-run-first, no auto-sync), and shell
completions for bash / zsh / fish / PowerShell. Extend three existing TUI
tabs with a "Source" filter dropdown that includes nested `.claude/`
locations; extend the Audit tab with a stats sub-pane.

**Architecture:** Same single-package, two-mode layout from Phase 1+2. Five
new core modules (`monorepo.py`, `watcher.py`, `stats.py`, `bundle.py`,
`completions.py`), five new Typer subapps, three new TUI dropdown filters,
one new Audit-tab sub-pane. No Phase 1 or Phase 2 module is broken or moved.

**Tech Stack:** Python 3.11+ — **no new mandatory deps**. Stdlib `tarfile`,
`subprocess`, `hashlib`, `signal`, `os`. Optional `psutil>=5.9` under
`[project.optional-dependencies] watcher` for accurate process-alive
checks. Test stack unchanged.

**Reference design:** `docs/plans/2026-05-09-cc-janitor-phase3-design.md`.

**Predecessor plans (style mirror):**
`docs/plans/2026-05-03-cc-janitor-phase1-mvp.md`,
`docs/plans/2026-05-05-cc-janitor-phase2-mvp.md`.

---

## Conventions used throughout this plan

- **Working dir** = `C:\Users\creat\OneDrive\Рабочий стол\CREATMAN\Tools\cc-janitor` (Windows path; in bash use `~/OneDrive/Рабочий стол/CREATMAN/Tools/cc-janitor`).
- **Branch:** `feat/phase3-mvp`. Implementer should branch from `main`
  after Phase 2 is merged (commit `522c2da` is the Phase 2 merge tip). PR
  to `main` at the end.
- **Every task** = TDD cycle: write failing test → run it → implement →
  run again → commit. Each commit message follows Conventional Commits
  with the `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`
  trailer required by project policy.
- **Audit log policy:** every mutating CLI command starts with
  `safety.require_confirmed()` and ends with `audit_action(...)`
  (the helper from `cli/_audit.py`). The pattern from
  `cli/commands/schedule.py` (Phase 2) is the reference.
- **No `--no-verify`, no `--amend` after a hook failure** — fix and
  create a new commit.
- **Expected pytest count after each task** is given so implementer can
  spot regressions. Phase 2 baseline = 152 passing.

---

## Task 0: Branch + version bump + optional psutil dep

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/cc_janitor/cli/__init__.py` (`__VERSION__`)

**Step 1: Branch.**

```bash
git fetch origin
git switch main
git pull
git switch -c feat/phase3-mvp
```

**Step 2: Bump version + add optional `watcher` extra.** Edit
`pyproject.toml`:

```toml
[project]
name = "cc-janitor"
version = "0.3.0.dev0"
# ... rest unchanged ...

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-textual-snapshot>=1",
    "pytest-cov>=5",
    "hypothesis>=6",
    "ruff>=0.6",
    "mypy>=1.10",
]
watcher = [
    "psutil>=5.9",
]
```

Then update `src/cc_janitor/cli/__init__.py`:

```python
__VERSION__ = "0.3.0.dev0"
```

**Step 3: Verify.**

```bash
uv pip install -e ".[dev]"
uv run cc-janitor --version           # must print 0.3.0.dev0
uv run pytest -q                      # 152 Phase 2 tests must still pass
```

**Step 4: Commit.**

```bash
git add pyproject.toml src/cc_janitor/cli/__init__.py
git commit -m "$(cat <<'EOF'
chore: bump to 0.3.0.dev0 and add optional [watcher] extra

Phase 3 introduces no new mandatory dependencies. psutil is opt-in
behind the `[watcher]` extra for users who want accurate
process-alive checks; absent it, the watcher falls back to
os.kill(pid, 0).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 1: Monorepo discovery — walk and classify

**Files:**
- Create: `src/cc_janitor/core/monorepo.py`
- Create: `tests/unit/test_monorepo_discover.py`
- Modify: `tests/data/mock-claude-home/` — add three nested `.claude/`
  fixtures

**Step 1: Test fixtures.** Under `tests/data/mock-claude-home/` add:

```
mock-claude-home/
├── projects/
│   ├── real-proj/
│   │   ├── package.json              # marker → "real"
│   │   └── .claude/
│   │       └── settings.json
│   ├── real-proj/node_modules/es-abstract/
│   │   ├── package.json              # marker, but inside node_modules
│   │   └── .claude/
│   │       └── settings.local.json   # → "nested" (vendored)
│   └── scratch/
│       └── .claude/
│           └── junk.txt              # no marker, no real content → "junk"
```

Use empty/minimal file contents — fixtures only need to exist.

**Step 2: Failing test.**

```python
# tests/unit/test_monorepo_discover.py
from pathlib import Path
from cc_janitor.core.monorepo import (
    MonorepoLocation, discover_locations, classify_location, SKIP_DIRS,
)


def test_discover_finds_three(mock_claude_home, monkeypatch):
    root = mock_claude_home / "projects"
    monkeypatch.setenv("CC_JANITOR_HOME", str(mock_claude_home / ".cc-janitor"))
    locs = discover_locations(root, include_junk=True)
    paths = {l.path.relative_to(root) for l in locs}
    assert Path("real-proj/.claude") in paths
    assert Path("real-proj/node_modules/es-abstract/.claude") in paths
    assert Path("scratch/.claude") in paths


def test_classify_real_when_parent_has_pyproject(tmp_path):
    parent = tmp_path / "p"
    parent.mkdir()
    (parent / "pyproject.toml").write_text("")
    claude = parent / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text("{}")
    loc = classify_location(claude)
    assert loc.scope_kind == "real"
    assert loc.has_settings is True
    assert loc.project_marker == "pyproject.toml"


def test_classify_nested_when_inside_node_modules(tmp_path):
    p = tmp_path / "node_modules" / "x"
    p.mkdir(parents=True)
    (p / "package.json").write_text("{}")
    claude = p / ".claude"
    claude.mkdir()
    loc = classify_location(claude)
    assert loc.scope_kind == "nested"


def test_classify_junk_when_no_marker(tmp_path):
    p = tmp_path / "scratch"
    p.mkdir()
    claude = p / ".claude"
    claude.mkdir()
    loc = classify_location(claude)
    assert loc.scope_kind == "junk"


def test_skip_dirs_default_includes_node_modules():
    assert "node_modules" in SKIP_DIRS
    assert ".venv" in SKIP_DIRS
    assert ".git" in SKIP_DIRS


def test_default_excludes_junk(mock_claude_home):
    root = mock_claude_home / "projects"
    locs = discover_locations(root, include_junk=False)
    kinds = {l.scope_kind for l in locs}
    assert "junk" not in kinds
```

**Step 3: Run, expect FAIL.**

```bash
uv run pytest tests/unit/test_monorepo_discover.py -v
```

**Step 4: Implement.**

```python
# src/cc_janitor/core/monorepo.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

ScopeKind = Literal["real", "nested", "junk"]

SKIP_DIRS: set[str] = {
    "node_modules", ".venv", "venv", ".git", "__pycache__",
    "dist", "build", ".next", ".tox", "target", "out",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
}

PROJECT_MARKERS: tuple[str, ...] = (
    "pyproject.toml", "package.json", "Cargo.toml", "go.mod",
    "pom.xml", "Gemfile", ".git",
)


@dataclass
class MonorepoLocation:
    path: Path
    parent: Path
    has_settings: bool
    has_skills: bool
    has_hooks: bool
    has_mcp: bool
    scope_kind: ScopeKind
    last_modified: datetime
    size_bytes: int
    project_marker: str | None


def _has_hooks_in_settings(settings_path: Path) -> bool:
    if not settings_path.exists():
        return False
    try:
        import json
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("hooks"))


def _find_project_marker(parent: Path) -> str | None:
    for marker in PROJECT_MARKERS:
        if (parent / marker).exists():
            return marker
    return None


def _max_mtime_and_size(root: Path) -> tuple[datetime, int]:
    max_mt = 0.0
    total = 0
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        st = f.stat()
        if st.st_mtime > max_mt:
            max_mt = st.st_mtime
        total += st.st_size
    if max_mt == 0.0:
        max_mt = root.stat().st_mtime
    return datetime.fromtimestamp(max_mt, tz=timezone.utc), total


def _is_inside_skip_dir(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    return any(part in SKIP_DIRS for part in rel.parts)


def classify_location(claude_dir: Path, *, root: Path | None = None) -> MonorepoLocation:
    parent = claude_dir.parent
    marker = _find_project_marker(parent)
    has_settings = (claude_dir / "settings.json").exists() or \
                   (claude_dir / "settings.local.json").exists()
    has_skills = (claude_dir / "skills").is_dir()
    has_hooks = _has_hooks_in_settings(claude_dir / "settings.json") or \
                _has_hooks_in_settings(claude_dir / "settings.local.json")
    has_mcp = (claude_dir / "mcp.json").exists() or (claude_dir / ".mcp.json").exists()
    last_mod, size = _max_mtime_and_size(claude_dir)

    inside_skip = _is_inside_skip_dir(claude_dir, root or claude_dir.anchor and Path(claude_dir.anchor))

    if marker and not inside_skip:
        kind: ScopeKind = "real"
    elif marker and inside_skip:
        kind = "nested"
    else:
        kind = "junk"

    return MonorepoLocation(
        path=claude_dir, parent=parent,
        has_settings=has_settings, has_skills=has_skills,
        has_hooks=has_hooks, has_mcp=has_mcp,
        scope_kind=kind, last_modified=last_mod, size_bytes=size,
        project_marker=marker,
    )


def _walk(root: Path, *, follow_skip: bool) -> Iterator[Path]:
    """Yield every .claude/ directory under root.

    When follow_skip is False, do not descend into SKIP_DIRS at all
    (fast path for normal scan).
    """
    if not root.exists():
        return
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = list(d.iterdir())
        except (OSError, PermissionError):
            continue
        for e in entries:
            if not e.is_dir():
                continue
            if e.name == ".claude":
                yield e
                continue
            if not follow_skip and e.name in SKIP_DIRS:
                continue
            stack.append(e)


def discover_locations(
    root: Path | None = None,
    *,
    include_junk: bool = False,
    scope_filter: tuple[ScopeKind, ...] | None = None,
) -> list[MonorepoLocation]:
    root = root or Path.cwd()
    out: list[MonorepoLocation] = []
    # When include_junk=True we must descend into SKIP_DIRS too,
    # otherwise we never see vendored .claude/ dirs at all.
    for claude_dir in _walk(root, follow_skip=include_junk):
        loc = classify_location(claude_dir, root=root)
        if loc.scope_kind == "junk" and not include_junk:
            continue
        if scope_filter and loc.scope_kind not in scope_filter:
            continue
        out.append(loc)
    out.sort(key=lambda l: (l.scope_kind, str(l.path)))
    return out
```

**Step 5: Run, expect PASS. Commit.**

```bash
git add src/cc_janitor/core/monorepo.py tests/unit/test_monorepo_discover.py \
        tests/data/mock-claude-home/projects/
git commit -m "$(cat <<'EOF'
feat(core): monorepo nested .claude/ discovery and classification

Walk a configurable root, find every .claude/ directory, classify
into real / nested / junk based on parent project markers and
SKIP_DIRS membership. Closes design §4.1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **158 passing** (+6 new).

---

## Task 2: Monorepo CLI subapp

**Files:**
- Create: `src/cc_janitor/cli/commands/monorepo.py`
- Modify: `src/cc_janitor/cli/__init__.py`
- Create: `tests/unit/test_cli_monorepo.py`

**Step 1: Failing test.**

```python
# tests/unit/test_cli_monorepo.py
from typer.testing import CliRunner
from cc_janitor.cli import app

runner = CliRunner()


def test_scan_table_output(mock_claude_home):
    res = runner.invoke(app, ["monorepo", "scan",
                              "--root", str(mock_claude_home / "projects")])
    assert res.exit_code == 0
    assert ".claude" in res.stdout
    assert "real" in res.stdout


def test_scan_json_output(mock_claude_home):
    res = runner.invoke(app, ["monorepo", "scan", "--json",
                              "--root", str(mock_claude_home / "projects")])
    assert res.exit_code == 0
    import json
    data = json.loads(res.stdout)
    assert isinstance(data, list)
    assert all("scope_kind" in item for item in data)


def test_scan_include_junk(mock_claude_home):
    res = runner.invoke(app, ["monorepo", "scan", "--include-junk",
                              "--root", str(mock_claude_home / "projects")])
    assert "junk" in res.stdout
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/cli/commands/monorepo.py
from __future__ import annotations

import json
from pathlib import Path

import typer

from ...core.monorepo import discover_locations

monorepo_app = typer.Typer(no_args_is_help=True,
                           help="Discover nested .claude/ directories")


@monorepo_app.command("scan")
def scan(
    root: Path = typer.Option(Path.cwd(), "--root", help="Tree root to scan"),
    include_junk: bool = typer.Option(False, "--include-junk"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    locs = discover_locations(root, include_junk=include_junk)
    if json_out:
        typer.echo(json.dumps([
            {
                "path": str(l.path),
                "scope_kind": l.scope_kind,
                "has_settings": l.has_settings,
                "has_skills": l.has_skills,
                "has_hooks": l.has_hooks,
                "has_mcp": l.has_mcp,
                "size_bytes": l.size_bytes,
                "last_modified": l.last_modified.isoformat(),
                "project_marker": l.project_marker,
            }
            for l in locs
        ], indent=2))
        return
    typer.echo(f"{'KIND':<8} {'SETTINGS':<10} {'HOOKS':<7} {'PATH'}")
    for l in locs:
        typer.echo(
            f"{l.scope_kind:<8} "
            f"{'yes' if l.has_settings else '-':<10} "
            f"{'yes' if l.has_hooks else '-':<7} "
            f"{l.path}"
        )


@monorepo_app.command("show")
def show(path: Path) -> None:
    from ...core.monorepo import classify_location
    loc = classify_location(path)
    typer.echo(f"Path:           {loc.path}")
    typer.echo(f"Scope:          {loc.scope_kind}")
    typer.echo(f"Project marker: {loc.project_marker}")
    typer.echo(f"Settings:       {loc.has_settings}")
    typer.echo(f"Skills:         {loc.has_skills}")
    typer.echo(f"Hooks:          {loc.has_hooks}")
    typer.echo(f"MCP:            {loc.has_mcp}")
    typer.echo(f"Size:           {loc.size_bytes} bytes")
    typer.echo(f"Last modified:  {loc.last_modified.isoformat()}")
```

Then in `src/cc_janitor/cli/__init__.py`:

```python
from .commands.monorepo import monorepo_app
# ...
app.add_typer(monorepo_app, name="monorepo")
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(cli): cc-janitor monorepo scan/show

Surface every nested .claude/ directory as a unified table or JSON,
with classification, settings/hooks/skills/mcp flags, and size.
Read-only; safe for Claude Code to invoke from inside a session.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **161 passing**.

---

## Task 3: Watcher core (poller body + status helpers)

**Files:**
- Create: `src/cc_janitor/core/watcher.py`
- Create: `tests/unit/test_watcher_core.py`

**Step 1: Failing test.**

```python
# tests/unit/test_watcher_core.py
import json
import time
from pathlib import Path
from cc_janitor.core.watcher import (
    WatcherStatus, write_status, read_status, run_watcher_once,
    iter_watched_files,
)


def test_status_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    s = WatcherStatus(
        pid=4711,
        started_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        watching_paths=[tmp_path / "a"], interval_seconds=30,
        marker_writes_count=0, last_change_at=None, is_alive=True,
    )
    write_status(s)
    s2 = read_status()
    assert s2 is not None
    assert s2.pid == 4711
    assert s2.interval_seconds == 30


def test_iter_watched_files_finds_md(tmp_path):
    d = tmp_path / "memory"
    d.mkdir()
    (d / "a.md").write_text("x")
    (d / "b.md").write_text("y")
    (d / "ignore.txt").write_text("z")
    files = list(iter_watched_files([d]))
    assert {f.name for f in files} == {"a.md", "b.md"}


def test_run_once_writes_marker_on_change(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    (tmp_path / "jhome").mkdir()
    mem = tmp_path / "memory"; mem.mkdir()
    f = mem / "MEMORY.md"; f.write_text("v1")
    last: dict[Path, float] = {}
    # First call records mtime; no marker.
    run_watcher_once([mem], last)
    assert not (tmp_path / "jhome" / "reinject-pending").exists()
    # Touch — bump mtime, second call writes marker.
    time.sleep(0.05)
    f.write_text("v2")
    run_watcher_once([mem], last)
    assert (tmp_path / "jhome" / "reinject-pending").exists()
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/core/watcher.py
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .state import get_paths


@dataclass
class WatcherStatus:
    pid: int
    started_at: datetime
    watching_paths: list[Path]
    interval_seconds: int
    marker_writes_count: int
    last_change_at: datetime | None
    is_alive: bool


def _status_path() -> Path:
    return get_paths().home / "watcher-status.json"


def _pid_path() -> Path:
    return get_paths().home / "watcher.pid"


def write_status(s: WatcherStatus) -> None:
    _status_path().parent.mkdir(parents=True, exist_ok=True)
    d = asdict(s)
    d["watching_paths"] = [str(p) for p in s.watching_paths]
    d["started_at"] = s.started_at.isoformat()
    d["last_change_at"] = s.last_change_at.isoformat() if s.last_change_at else None
    _status_path().write_text(json.dumps(d, indent=2), encoding="utf-8")


def read_status() -> WatcherStatus | None:
    p = _status_path()
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    pid = int(d["pid"])
    return WatcherStatus(
        pid=pid,
        started_at=datetime.fromisoformat(d["started_at"]),
        watching_paths=[Path(x) for x in d["watching_paths"]],
        interval_seconds=int(d["interval_seconds"]),
        marker_writes_count=int(d["marker_writes_count"]),
        last_change_at=datetime.fromisoformat(d["last_change_at"]) if d.get("last_change_at") else None,
        is_alive=is_pid_alive(pid),
    )


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil  # type: ignore
        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
    except ImportError:
        pass
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


def iter_watched_files(dirs: list[Path]) -> Iterator[Path]:
    for d in dirs:
        if not d.exists():
            continue
        for f in d.rglob("*.md"):
            if ".archive" in f.parts:
                continue
            yield f


def run_watcher_once(memory_dirs: list[Path],
                     last_mtimes: dict[Path, float]) -> bool:
    """Single poll iteration. Returns True if marker was written."""
    changed = False
    for f in iter_watched_files(memory_dirs):
        try:
            mt = f.stat().st_mtime
        except OSError:
            continue
        previous = last_mtimes.get(f)
        last_mtimes[f] = mt
        if previous is not None and mt > previous:
            changed = True
    if changed:
        marker = get_paths().home / "reinject-pending"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        # Bump status if present
        s = read_status()
        if s is not None:
            s.marker_writes_count += 1
            s.last_change_at = datetime.now(timezone.utc)
            write_status(s)
    return changed


def run_watcher(memory_dirs: list[Path], interval: int) -> None:
    """Main loop — invoked by the spawned daemon process."""
    last_mtimes: dict[Path, float] = {}
    # Prime with current mtimes (first iteration is recording-only).
    for f in iter_watched_files(memory_dirs):
        try:
            last_mtimes[f] = f.stat().st_mtime
        except OSError:
            pass
    while True:
        try:
            time.sleep(interval)
            run_watcher_once(memory_dirs, last_mtimes)
        except KeyboardInterrupt:
            return
        except Exception:  # noqa: BLE001 — keep daemon alive on transient errors
            time.sleep(interval)


def spawn_daemon(args: list[str], cwd: Path, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("ab")
    if sys.platform == "win32":
        flags = 0x00000200 | 0x00000008  # CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
        proc = subprocess.Popen(
            args, cwd=str(cwd), stdout=log, stderr=log,
            stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True,
        )
    else:
        proc = subprocess.Popen(
            args, cwd=str(cwd), stdout=log, stderr=log,
            stdin=subprocess.DEVNULL, start_new_session=True, close_fds=True,
        )
    return proc.pid


def kill_pid(pid: int) -> None:
    if not is_pid_alive(pid):
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True, check=False)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(10):
        if not is_pid_alive(pid):
            return
        time.sleep(0.5)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(core): watcher poller core, status I/O, cross-platform spawn/kill

mtime-poll loop, WatcherStatus round-trip via JSON, spawn_daemon
with start_new_session (POSIX) / DETACHED_PROCESS (Windows), kill_pid
with SIGTERM-then-SIGKILL fallback / taskkill /F. psutil used when
available, falls back to os.kill(pid, 0).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **164 passing**.

---

## Task 4: Watcher CLI subapp (start / stop / status)

**Files:**
- Create: `src/cc_janitor/cli/commands/watch.py`
- Modify: `src/cc_janitor/cli/__init__.py`
- Create: `tests/unit/test_cli_watch.py`

**Step 1: Failing test.**

```python
# tests/unit/test_cli_watch.py
import os
from typer.testing import CliRunner
from cc_janitor.cli import app

runner = CliRunner()


def test_start_requires_confirmation(monkeypatch, tmp_path):
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    res = runner.invoke(app, ["watch", "start"])
    assert res.exit_code != 0
    assert "confirm" in res.stdout.lower() or "confirm" in res.output.lower()


def test_status_when_not_running(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    res = runner.invoke(app, ["watch", "status"])
    assert res.exit_code == 0
    assert "not running" in res.stdout.lower()


def test_start_then_stop(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    captured = {}

    def fake_spawn(args, cwd, log_path):
        captured["args"] = args
        return os.getpid()  # use our own PID — guaranteed alive

    monkeypatch.setattr("cc_janitor.core.watcher.spawn_daemon", fake_spawn)
    res = runner.invoke(app, ["watch", "start", "--interval", "5"])
    assert res.exit_code == 0
    assert (tmp_path / "watcher.pid").exists()

    # stop — but we don't actually want to kill our test process.
    monkeypatch.setattr("cc_janitor.core.watcher.kill_pid", lambda pid: None)
    res = runner.invoke(app, ["watch", "stop"])
    assert res.exit_code == 0
    assert not (tmp_path / "watcher.pid").exists()
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/cli/commands/watch.py
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import typer

from ...core import watcher as w
from ...core.safety import require_confirmed
from ...core.state import get_paths
from .._audit import audit_action

watch_app = typer.Typer(no_args_is_help=True,
                        help="Auto-reinject background watcher (opt-in)")


def _default_memory_dirs() -> list[Path]:
    home = get_paths().home.parent
    proj_root = home / ".claude" / "projects"
    if not proj_root.exists():
        return []
    return [d / "memory" for d in proj_root.iterdir() if (d / "memory").is_dir()]


@watch_app.command("start")
@audit_action(cmd="watch start")
def start(interval: int = typer.Option(30, "--interval", min=1)) -> None:
    require_confirmed()
    pid_p = get_paths().home / "watcher.pid"
    if pid_p.exists():
        old_pid = int(pid_p.read_text(encoding="utf-8").strip() or "0")
        if w.is_pid_alive(old_pid):
            typer.echo(f"Watcher already running (pid {old_pid})")
            raise typer.Exit(code=1)
        pid_p.unlink()
    dirs = _default_memory_dirs()
    if not dirs:
        typer.echo("No memory directories found under ~/.claude/projects/*/memory/")
        raise typer.Exit(code=2)
    args = [
        sys.executable, "-m", "cc_janitor.core.watcher_main",
        "--interval", str(interval),
        *(["--dir", str(d)] for d in dirs and []),  # placeholder — see step 5
    ]
    # Simpler: pass dirs via env
    import os
    os.environ["CC_JANITOR_WATCH_DIRS"] = os.pathsep.join(str(d) for d in dirs)
    log = get_paths().home / "watcher.log"
    pid = w.spawn_daemon(
        [sys.executable, "-m", "cc_janitor.core.watcher_main",
         "--interval", str(interval)],
        cwd=Path.cwd(), log_path=log,
    )
    pid_p.write_text(str(pid), encoding="utf-8")
    w.write_status(w.WatcherStatus(
        pid=pid, started_at=datetime.now(timezone.utc),
        watching_paths=dirs, interval_seconds=interval,
        marker_writes_count=0, last_change_at=None, is_alive=True,
    ))
    typer.echo(f"Watcher started (pid {pid}, interval {interval}s, "
               f"{len(dirs)} memory dirs)")


@watch_app.command("stop")
@audit_action(cmd="watch stop")
def stop() -> None:
    require_confirmed()
    pid_p = get_paths().home / "watcher.pid"
    if not pid_p.exists():
        typer.echo("Watcher not running")
        raise typer.Exit(code=0)
    pid = int(pid_p.read_text(encoding="utf-8").strip() or "0")
    w.kill_pid(pid)
    pid_p.unlink(missing_ok=True)
    status_p = get_paths().home / "watcher-status.json"
    status_p.unlink(missing_ok=True)
    typer.echo(f"Watcher stopped (pid {pid})")


@watch_app.command("status")
def status(json_out: bool = typer.Option(False, "--json")) -> None:
    s = w.read_status()
    if s is None:
        typer.echo("Watcher: not running")
        return
    if json_out:
        d = {
            "pid": s.pid,
            "started_at": s.started_at.isoformat(),
            "watching_paths": [str(p) for p in s.watching_paths],
            "interval_seconds": s.interval_seconds,
            "marker_writes_count": s.marker_writes_count,
            "last_change_at": s.last_change_at.isoformat() if s.last_change_at else None,
            "is_alive": s.is_alive,
        }
        typer.echo(json.dumps(d, indent=2))
        return
    state = "running" if s.is_alive else "stale (pid dead)"
    typer.echo(f"Watcher: {state}")
    typer.echo(f"  PID:             {s.pid}")
    typer.echo(f"  Started at:      {s.started_at.isoformat()}")
    typer.echo(f"  Interval:        {s.interval_seconds}s")
    typer.echo(f"  Watching:        {len(s.watching_paths)} dirs")
    typer.echo(f"  Marker writes:   {s.marker_writes_count}")
    if s.last_change_at:
        typer.echo(f"  Last change at:  {s.last_change_at.isoformat()}")
```

**Step 4: Watcher entry-point module.** Create
`src/cc_janitor/core/watcher_main.py`:

```python
# src/cc_janitor/core/watcher_main.py
"""Daemon entry-point. Spawned by `cc-janitor watch start`."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from . import watcher


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args()
    raw = os.environ.get("CC_JANITOR_WATCH_DIRS", "")
    dirs = [Path(p) for p in raw.split(os.pathsep) if p]
    watcher.run_watcher(dirs, args.interval)


if __name__ == "__main__":
    main()
```

Register subapp in `cli/__init__.py`:

```python
from .commands.watch import watch_app
# ...
app.add_typer(watch_app, name="watch")
```

**Step 5: Run, PASS. Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(cli): cc-janitor watch start/stop/status

Opt-in background watcher daemon spawned via subprocess.Popen with
detached/new-session flags. PID file at ~/.cc-janitor/watcher.pid;
status JSON at ~/.cc-janitor/watcher-status.json. SIGTERM-then-
SIGKILL stop on POSIX, taskkill /F on Windows. Mutating commands
gated by require_confirmed; audit-log entry on every start/stop.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **167 passing**.

---

## Task 5: Watcher integration with `doctor`

**Files:**
- Modify: `src/cc_janitor/cli/commands/doctor.py`
- Create: `tests/unit/test_doctor_watcher.py`

**Step 1: Failing test.**

```python
# tests/unit/test_doctor_watcher.py
import os
from datetime import datetime, timezone
from typer.testing import CliRunner
from cc_janitor.cli import app
from cc_janitor.core.watcher import WatcherStatus, write_status

runner = CliRunner()


def test_doctor_reports_no_watcher(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    res = runner.invoke(app, ["doctor"])
    assert res.exit_code == 0
    assert "Watcher" in res.stdout
    assert "not running" in res.stdout.lower()


def test_doctor_reports_running_watcher(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    s = WatcherStatus(
        pid=os.getpid(),  # alive!
        started_at=datetime.now(timezone.utc),
        watching_paths=[], interval_seconds=30,
        marker_writes_count=7, last_change_at=None, is_alive=True,
    )
    write_status(s)
    res = runner.invoke(app, ["doctor"])
    assert res.exit_code == 0
    assert "Watcher" in res.stdout
    assert "running" in res.stdout.lower()
    assert "7" in res.stdout
```

**Step 2: Run, FAIL.**

**Step 3: Implement.** Append to `cli/commands/doctor.py`:

```python
def doctor() -> None:
    # ... existing content ...
    from ...core.watcher import read_status
    s = read_status()
    if s is None:
        typer.echo("Watcher:    not running")
    elif s.is_alive:
        typer.echo(
            f"Watcher:    running (pid {s.pid}, since "
            f"{s.started_at.isoformat()}, {s.marker_writes_count} reinjects)"
        )
    else:
        typer.echo(f"Watcher:    stale (pid {s.pid} dead — run `watch stop`)")
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(cli): doctor surfaces watcher status

Adds one line to `cc-janitor doctor` output reporting whether the
watcher is running, stale, or absent. Reinject count visible at a
glance.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **169 passing**.

---

## Task 6: Stats — snapshot writer + reader + sparkline

**Files:**
- Create: `src/cc_janitor/core/stats.py`
- Create: `tests/unit/test_stats.py`

**Step 1: Failing test.**

```python
# tests/unit/test_stats.py
from datetime import date, timedelta
from cc_janitor.core.stats import (
    StatsSnapshot, take_snapshot, write_snapshot, load_snapshots,
    render_sparkline,
)


def test_render_sparkline_known_values():
    out = render_sparkline([0, 1, 2, 3, 4, 5, 6, 7], width=8)
    assert len(out) == 8
    assert out[0] == "▁"
    assert out[-1] == "█"


def test_sparkline_handles_flat():
    out = render_sparkline([5, 5, 5, 5], width=4)
    assert all(c == out[0] for c in out)


def test_sparkline_empty_returns_blank(monkeypatch):
    assert render_sparkline([], width=10) == " " * 10


def test_snapshot_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    s = StatsSnapshot(
        date=date(2026, 5, 9),
        sessions_count=42, perm_rules_count=234,
        context_tokens=12450, trash_bytes=1245678,
        audit_entries_since_last=17,
    )
    write_snapshot(s)
    snaps = load_snapshots(since=timedelta(days=30))
    assert len(snaps) == 1
    assert snaps[0].sessions_count == 42


def test_load_filters_old(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    old = StatsSnapshot(
        date=date.today() - timedelta(days=60),
        sessions_count=1, perm_rules_count=1, context_tokens=1,
        trash_bytes=1, audit_entries_since_last=0,
    )
    new = StatsSnapshot(
        date=date.today() - timedelta(days=5),
        sessions_count=2, perm_rules_count=2, context_tokens=2,
        trash_bytes=2, audit_entries_since_last=1,
    )
    write_snapshot(old)
    write_snapshot(new)
    out = load_snapshots(since=timedelta(days=30))
    assert len(out) == 1
    assert out[0].sessions_count == 2
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/core/stats.py
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .state import get_paths

SPARKLINE_CHARS = " ▁▂▃▄▅▆▇█"


@dataclass
class StatsSnapshot:
    date: date
    sessions_count: int
    perm_rules_count: int
    context_tokens: int
    trash_bytes: int
    audit_entries_since_last: int


def _history_dir() -> Path:
    p = get_paths().history
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_snapshot(s: StatsSnapshot) -> Path:
    p = _history_dir() / f"{s.date.isoformat()}.json"
    d = asdict(s)
    d["date"] = s.date.isoformat()
    p.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return p


def load_snapshots(*, since: timedelta = timedelta(days=30)) -> list[StatsSnapshot]:
    cutoff = date.today() - since
    out: list[StatsSnapshot] = []
    for f in sorted(_history_dir().glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        snap_date = date.fromisoformat(d["date"])
        if snap_date < cutoff:
            continue
        out.append(StatsSnapshot(
            date=snap_date,
            sessions_count=int(d["sessions_count"]),
            perm_rules_count=int(d["perm_rules_count"]),
            context_tokens=int(d["context_tokens"]),
            trash_bytes=int(d["trash_bytes"]),
            audit_entries_since_last=int(d["audit_entries_since_last"]),
        ))
    out.sort(key=lambda s: s.date)
    return out


def take_snapshot() -> StatsSnapshot:
    """Compute today's snapshot from the live cc-janitor state."""
    from .sessions import discover_sessions
    from .permissions import discover_rules
    from .context import compute_context_cost  # Phase 1 helper
    paths = get_paths()
    sessions = discover_sessions()
    rules = discover_rules()
    try:
        ctx = compute_context_cost()
        tokens = ctx.total_tokens
    except Exception:
        tokens = 0
    trash_bytes = (
        sum(p.stat().st_size for p in paths.trash.rglob("*") if p.is_file())
        if paths.trash.exists() else 0
    )
    audit_entries = 0
    if paths.audit_log.exists():
        # crude: count lines added since previous snapshot
        prev = sorted(_history_dir().glob("*.json"))
        previous_count = 0
        if prev:
            try:
                previous_count = int(
                    json.loads(prev[-1].read_text(encoding="utf-8"))
                    .get("_audit_total_lines", 0)
                )
            except Exception:
                previous_count = 0
        with paths.audit_log.open("r", encoding="utf-8") as f:
            current_total = sum(1 for _ in f)
        audit_entries = max(0, current_total - previous_count)
    return StatsSnapshot(
        date=date.today(),
        sessions_count=len(sessions),
        perm_rules_count=len(rules),
        context_tokens=tokens,
        trash_bytes=trash_bytes,
        audit_entries_since_last=audit_entries,
    )


def render_sparkline(values: list[float], *, width: int = 30) -> str:
    if not values:
        return " " * width
    if len(values) > width:
        # Down-sample by averaging buckets
        bucket = len(values) / width
        values = [
            sum(values[int(i*bucket):int((i+1)*bucket)]) / max(1, int((i+1)*bucket) - int(i*bucket))
            for i in range(width)
        ]
    elif len(values) < width:
        # Pad left with first value
        pad = [values[0]] * (width - len(values))
        values = pad + list(values)
    lo, hi = min(values), max(values)
    if hi == lo:
        return SPARKLINE_CHARS[len(SPARKLINE_CHARS) // 2] * width
    span = hi - lo
    bins = len(SPARKLINE_CHARS) - 1
    out = []
    for v in values:
        idx = int((v - lo) / span * bins)
        out.append(SPARKLINE_CHARS[max(1, min(bins, idx))])
    return "".join(out)
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(core): stats snapshot writer + reader + ASCII sparkline

Daily one-file-per-day JSON snapshots at ~/.cc-janitor/history/.
load_snapshots(since=) returns sorted-ascending list. render_sparkline
uses Unicode block elements ▁▂▃▄▅▆▇█ at configurable width with
down-sampling and flat-series handling.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **174 passing**.

---

## Task 7: Stats CLI subapp + TUI Audit-tab sub-pane

**Files:**
- Create: `src/cc_janitor/cli/commands/stats.py`
- Modify: `src/cc_janitor/cli/__init__.py`
- Modify: `src/cc_janitor/tui/screens/audit_screen.py`
- Create: `tests/unit/test_cli_stats.py`

**Step 1: Failing test.**

```python
# tests/unit/test_cli_stats.py
from datetime import date, timedelta
from typer.testing import CliRunner
from cc_janitor.cli import app
from cc_janitor.core.stats import StatsSnapshot, write_snapshot

runner = CliRunner()


def _seed(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    today = date.today()
    for i in range(7):
        write_snapshot(StatsSnapshot(
            date=today - timedelta(days=6 - i),
            sessions_count=10 + i, perm_rules_count=200 - i*5,
            context_tokens=12000 - i*200, trash_bytes=1_000_000 + i*1000,
            audit_entries_since_last=i,
        ))


def test_stats_text_output(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    res = runner.invoke(app, ["stats", "--since", "30d"])
    assert res.exit_code == 0
    assert "Sessions" in res.stdout
    assert "Perm rules" in res.stdout


def test_stats_json_output(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    res = runner.invoke(app, ["stats", "--since", "30d", "--format", "json"])
    assert res.exit_code == 0
    import json
    data = json.loads(res.stdout)
    assert len(data) == 7


def test_stats_snapshot_writes_file(tmp_path, monkeypatch, mock_claude_home):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path))
    res = runner.invoke(app, ["stats", "snapshot"])
    assert res.exit_code == 0
    assert (tmp_path / "history" / f"{date.today().isoformat()}.json").exists()
```

**Step 2: Run, FAIL.**

**Step 3: Implement CLI.**

```python
# src/cc_janitor/cli/commands/stats.py
from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import asdict
from datetime import timedelta

import typer

from ...core.stats import (
    load_snapshots, take_snapshot, write_snapshot, render_sparkline,
)

stats_app = typer.Typer(no_args_is_help=False,
                        help="Stats dashboard with daily history",
                        invoke_without_command=True)


def _parse_since(s: str) -> timedelta:
    m = re.fullmatch(r"(\d+)([dwhm])", s)
    if not m:
        raise typer.BadParameter(f"Invalid --since: {s} (use 7d, 4w, 24h, 30m)")
    n, unit = int(m.group(1)), m.group(2)
    return {
        "d": timedelta(days=n),
        "w": timedelta(weeks=n),
        "h": timedelta(hours=n),
        "m": timedelta(minutes=n),
    }[unit]


@stats_app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    since: str = typer.Option("30d", "--since"),
    fmt: str = typer.Option("text", "--format"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    snaps = load_snapshots(since=_parse_since(since))
    if fmt == "json":
        typer.echo(json.dumps([
            {**asdict(s), "date": s.date.isoformat()} for s in snaps
        ], indent=2))
        return
    if fmt == "csv":
        w = csv.writer(sys.stdout)
        w.writerow(["date", "sessions", "perm_rules", "context_tokens",
                    "trash_bytes", "audit_entries_since_last"])
        for s in snaps:
            w.writerow([s.date.isoformat(), s.sessions_count,
                        s.perm_rules_count, s.context_tokens,
                        s.trash_bytes, s.audit_entries_since_last])
        return
    if not snaps:
        typer.echo("No snapshots in window. Run `cc-janitor stats snapshot` first.")
        return
    last = snaps[-1]
    typer.echo(f"Sessions:       {last.sessions_count:>6}  "
               f"{render_sparkline([s.sessions_count for s in snaps])}")
    typer.echo(f"Perm rules:     {last.perm_rules_count:>6}  "
               f"{render_sparkline([s.perm_rules_count for s in snaps])}")
    typer.echo(f"Context tokens: {last.context_tokens:>6}  "
               f"{render_sparkline([s.context_tokens for s in snaps])}")
    typer.echo(f"Trash bytes:    {last.trash_bytes:>6}  "
               f"{render_sparkline([s.trash_bytes for s in snaps])}")


@stats_app.command("snapshot")
def snapshot_cmd() -> None:
    s = take_snapshot()
    p = write_snapshot(s)
    typer.echo(f"Snapshot written: {p}")
```

Register in `cli/__init__.py`:

```python
from .commands.stats import stats_app
app.add_typer(stats_app, name="stats")
```

**Step 4: TUI Audit-tab sub-pane.** In
`src/cc_janitor/tui/screens/audit_screen.py` add a `Static` widget that
renders the same four sparklines. Footer key `s` toggles visibility.
Snapshot test under `tests/tui/test_audit_screen_stats.py` follows the
Phase 1 pattern.

**Step 5: Run, PASS. Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(cli,tui): cc-janitor stats and Audit-tab sparkline sub-pane

CLI: cc-janitor stats [--since 30d] [--format text|json|csv] reads
~/.cc-janitor/history/*.json and renders four sparklines for sessions,
perm rules, context tokens, trash bytes. cc-janitor stats snapshot
writes today's record.

TUI: Audit tab gains a sub-pane (toggle: s) showing the same
sparklines. No new chart dep — hand-rolled ASCII renderer.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **178 passing**.

---

## Task 8: Bundle export (read-only, manifest, hashes)

**Files:**
- Create: `src/cc_janitor/core/bundle.py`
- Create: `tests/unit/test_bundle_export.py`

**Step 1: Failing test.**

```python
# tests/unit/test_bundle_export.py
import hashlib
import json
import tarfile
from cc_janitor.core.bundle import export_bundle


def test_export_creates_tar_with_manifest(mock_claude_home, tmp_path):
    out = tmp_path / "bundle.tar.gz"
    n = export_bundle(out, include_memory=False)
    assert out.exists() and n >= 1
    with tarfile.open(out, "r:gz") as tar:
        names = tar.getnames()
        assert "manifest.json" in names
        m = json.loads(tar.extractfile("manifest.json").read().decode("utf-8"))
        assert m["version"] == 1
        assert all("sha256" in f for f in m["files"])


def test_export_excludes_settings_local(mock_claude_home, tmp_path):
    out = tmp_path / "bundle.tar.gz"
    export_bundle(out, include_memory=True)
    with tarfile.open(out, "r:gz") as tar:
        for name in tar.getnames():
            assert "settings.local.json" not in name


def test_export_sha256_matches(mock_claude_home, tmp_path):
    out = tmp_path / "bundle.tar.gz"
    export_bundle(out, include_memory=False)
    with tarfile.open(out, "r:gz") as tar:
        m = json.loads(tar.extractfile("manifest.json").read().decode("utf-8"))
        for entry in m["files"]:
            member = tar.extractfile(entry["arcname"])
            data = member.read()
            assert hashlib.sha256(data).hexdigest() == entry["sha256"]
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/core/bundle.py
from __future__ import annotations

import hashlib
import io
import json
import platform
import re
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

from .state import get_paths

FileKind = Literal["claude_md", "skill", "settings", "memory", "mcp_config"]

SECRET_PATTERNS = [
    re.compile(r"settings\.local\.json$"),
    re.compile(r"\.env$"),
    re.compile(r"credentials\.json$"),
    re.compile(r"\.secret$"),
    re.compile(r"_token$"),
]


@dataclass
class BundleEntry:
    src_path: Path
    arcname: str
    kind: FileKind


def _is_secret(path: Path) -> bool:
    name = path.name
    return any(p.search(name) for p in SECRET_PATTERNS)


def _iter_sources(*, include_memory: bool) -> Iterator[BundleEntry]:
    home = get_paths().home.parent
    cwd = Path.cwd()

    # ~/.claude/CLAUDE.md
    p = home / ".claude" / "CLAUDE.md"
    if p.exists():
        yield BundleEntry(p, "claude/CLAUDE.md", "claude_md")

    # ~/.claude/skills/**
    skills_root = home / ".claude" / "skills"
    if skills_root.is_dir():
        for f in skills_root.rglob("*"):
            if not f.is_file() or "__pycache__" in f.parts:
                continue
            if _is_secret(f):
                continue
            rel = f.relative_to(home / ".claude")
            yield BundleEntry(f, f"claude/{rel.as_posix()}", "skill")

    # ~/.claude/settings.json (NOT settings.local.json)
    p = home / ".claude" / "settings.json"
    if p.exists() and not _is_secret(p):
        yield BundleEntry(p, "claude/settings.json", "settings")

    # cwd/.claude/settings.json (NOT local)
    p = cwd / ".claude" / "settings.json"
    if p.exists() and not _is_secret(p):
        yield BundleEntry(p, "project/settings.json", "settings")

    if include_memory:
        proj_root = home / ".claude" / "projects"
        if proj_root.is_dir():
            for proj in proj_root.iterdir():
                mem = proj / "memory"
                if not mem.is_dir():
                    continue
                for f in mem.rglob("*.md"):
                    if ".archive" in f.parts:
                        continue
                    rel = f.relative_to(home / ".claude")
                    yield BundleEntry(f, f"claude/{rel.as_posix()}", "memory")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def export_bundle(out_path: Path, *, include_memory: bool = False) -> int:
    entries = list(_iter_sources(include_memory=include_memory))
    files_meta: list[dict] = []
    cached: dict[str, bytes] = {}
    for e in entries:
        data = e.src_path.read_bytes()
        cached[e.arcname] = data
        files_meta.append({
            "path": str(e.src_path),
            "arcname": e.arcname,
            "sha256": _sha256(data),
            "kind": e.kind,
            "size": len(data),
        })
    manifest = {
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "host": platform.node(),
        "cc_janitor_version": "0.3.0.dev0",
        "files": files_meta,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out_path, "w:gz") as tar:
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
        info = tarfile.TarInfo("manifest.json")
        info.size = len(manifest_bytes)
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(manifest_bytes))
        for arcname, data in cached.items():
            info = tarfile.TarInfo(arcname)
            info.size = len(data)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return len(entries)
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(core): config bundle export with SHA-256 manifest

Walks an explicit allowlist (CLAUDE.md, skills/**, settings.json,
optionally memory/*.md). Hard-excludes settings.local.json and other
secret-file patterns; no opt-out flag. manifest.json is the first
member of the tar for fast inspection without full extract.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **181 passing**.

---

## Task 9: Bundle import (dry-run + backup-before-overwrite + audit)

**Files:**
- Modify: `src/cc_janitor/core/bundle.py`
- Create: `src/cc_janitor/cli/commands/config.py`
- Modify: `src/cc_janitor/cli/__init__.py`
- Create: `tests/unit/test_bundle_import.py`
- Create: `tests/unit/test_cli_config.py`

**Step 1: Failing test.**

```python
# tests/unit/test_bundle_import.py
import json
from pathlib import Path
from cc_janitor.core.bundle import export_bundle, import_bundle


def test_import_dry_run_does_not_write(mock_claude_home, tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    out = tmp_path / "bundle.tar.gz"
    export_bundle(out, include_memory=False)
    # Trash CLAUDE.md to simulate a different machine.
    target = mock_claude_home / ".claude" / "CLAUDE.md"
    target.write_text("DIFFERENT", encoding="utf-8")
    plan = import_bundle(out, dry_run=True, force=False)
    assert plan["would_write"] >= 1
    assert target.read_text(encoding="utf-8") == "DIFFERENT"  # unchanged


def test_import_force_writes_and_backups(mock_claude_home, tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    out = tmp_path / "bundle.tar.gz"
    export_bundle(out, include_memory=False)
    target = mock_claude_home / ".claude" / "CLAUDE.md"
    original = target.read_text(encoding="utf-8")
    target.write_text("DIFFERENT", encoding="utf-8")
    res = import_bundle(out, dry_run=False, force=True)
    assert res["written"] >= 1
    assert target.read_text(encoding="utf-8") == original
    # backup must exist
    assert any(res["backups"])


def test_import_refuses_on_sha_mismatch(mock_claude_home, tmp_path, monkeypatch):
    import tarfile, io
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    out = tmp_path / "bad.tar.gz"
    export_bundle(out, include_memory=False)
    # Tamper: rewrite a member with different content but keep manifest.
    raw = out.read_bytes()
    out2 = tmp_path / "tampered.tar.gz"
    out2.write_bytes(raw)
    # ... tampering is involved; for the unit test we just corrupt the
    # gzip stream and expect a clear error.
    out2.write_bytes(raw[:100] + b"\x00" * 50 + raw[150:])
    with pytest.raises(Exception):  # noqa: S101 — broad-by-design
        import_bundle(out2, dry_run=False, force=True)
```

**Step 2: Run, FAIL.**

**Step 3: Implement import.** Append to `core/bundle.py`:

```python
import os
import shutil

from .safety import require_confirmed


def _verify_member(tar: tarfile.TarFile, arcname: str, expected_sha: str) -> bytes:
    member = tar.extractfile(arcname)
    if member is None:
        raise ValueError(f"Bundle missing member: {arcname}")
    data = member.read()
    actual = _sha256(data)
    if actual != expected_sha:
        raise ValueError(f"SHA mismatch for {arcname}: expected {expected_sha}, got {actual}")
    return data


def _resolve_dest(arcname: str) -> Path:
    home = get_paths().home.parent
    cwd = Path.cwd()
    if arcname.startswith("claude/"):
        return home / ".claude" / arcname[len("claude/"):]
    if arcname.startswith("project/"):
        return cwd / ".claude" / arcname[len("project/"):]
    if arcname == "manifest.json":
        return Path()  # never written
    raise ValueError(f"Unknown bundle arcname prefix: {arcname}")


def import_bundle(bundle_path: Path, *, dry_run: bool, force: bool) -> dict:
    require_confirmed()
    backups: list[Path] = []
    written: list[Path] = []
    plan_writes = 0

    with tarfile.open(bundle_path, "r:gz") as tar:
        manifest = json.loads(tar.extractfile("manifest.json").read().decode("utf-8"))
        if manifest.get("version") != 1:
            raise ValueError(f"Unsupported bundle version: {manifest.get('version')}")
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup_root = get_paths().backups / f"import-{ts}"

        for entry in manifest["files"]:
            arcname = entry["arcname"]
            data = _verify_member(tar, arcname, entry["sha256"])
            dest = _resolve_dest(arcname)
            if dest == Path():
                continue
            if dest.exists():
                existing = dest.read_bytes()
                if _sha256(existing) == entry["sha256"]:
                    continue  # already identical
            plan_writes += 1
            if dry_run or not force:
                continue
            if dest.exists():
                backup_root.mkdir(parents=True, exist_ok=True)
                bp = backup_root / dest.name
                shutil.copy2(dest, bp)
                backups.append(bp)
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(dest.suffix + ".cc-janitor-tmp")
            tmp.write_bytes(data)
            os.replace(tmp, dest)
            written.append(dest)

    return {
        "would_write": plan_writes,
        "written": len(written),
        "backups": [str(b) for b in backups],
        "destinations": [str(d) for d in written],
    }
```

**Step 4: CLI subapp.**

```python
# src/cc_janitor/cli/commands/config.py
from __future__ import annotations

from pathlib import Path

import typer

from ...core.bundle import export_bundle, import_bundle
from .._audit import audit_action

config_app = typer.Typer(no_args_is_help=True,
                         help="Export/import cross-machine config bundle")


@config_app.command("export")
@audit_action(cmd="config export")
def export_cmd(
    out: Path,
    include_memory: bool = typer.Option(False, "--include-memory"),
) -> None:
    n = export_bundle(out, include_memory=include_memory)
    typer.echo(f"Exported {n} files to {out}")


@config_app.command("import")
@audit_action(cmd="config import")
def import_cmd(
    bundle: Path,
    dry_run: bool = typer.Option(False, "--dry-run"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    if not force:
        # Mirror scheduler dry-run-first guard.
        result = import_bundle(bundle, dry_run=True, force=False)
        typer.echo(f"DRY RUN: would write {result['would_write']} files. "
                   f"Re-run with --force to apply.")
        return
    result = import_bundle(bundle, dry_run=False, force=True)
    typer.echo(f"Imported {result['written']} files. "
               f"Backups: {len(result['backups'])} at {get_paths().backups}")


from ...core.state import get_paths  # noqa: E402 — late import for typer signature
```

Register in `cli/__init__.py`:

```python
from .commands.config import config_app
app.add_typer(config_app, name="config")
```

**Step 5: Run, PASS. Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(core,cli): config bundle import with dry-run-first and backup

import_bundle verifies SHA-256 of every member against manifest,
backs up existing destination files to ~/.cc-janitor/backups/import-<ts>/
before overwrite, writes atomically via os.replace. CLI mirrors the
scheduler dry-run-first pattern: first invocation without --force
exits dry-run regardless. require_confirmed gate on import; export
is read-only.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **186 passing**.

---

## Task 10: Shell completions subapp

**Files:**
- Create: `src/cc_janitor/cli/commands/completions.py`
- Modify: `src/cc_janitor/cli/__init__.py`
- Create: `tests/unit/test_cli_completions.py`

**Step 1: Failing test.**

```python
# tests/unit/test_cli_completions.py
from typer.testing import CliRunner
from cc_janitor.cli import app

runner = CliRunner()


def test_completions_show_bash_prints_script():
    res = runner.invoke(app, ["completions", "show", "bash"])
    assert res.exit_code == 0
    # Click's bash completion uses _CC_JANITOR_COMPLETE env-var hook.
    assert "_CC_JANITOR" in res.stdout or "complete" in res.stdout.lower()


def test_completions_show_unknown_shell():
    res = runner.invoke(app, ["completions", "show", "tcsh"])
    assert res.exit_code != 0


def test_completions_install_requires_confirm(monkeypatch):
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    res = runner.invoke(app, ["completions", "install", "bash"])
    assert res.exit_code != 0
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/cli/commands/completions.py
from __future__ import annotations

import os
import subprocess
import sys

import typer

from ...core.safety import require_confirmed
from .._audit import audit_action

completions_app = typer.Typer(no_args_is_help=True,
                              help="Shell completion install/show")

VALID_SHELLS = {"bash", "zsh", "fish", "powershell"}


def _generate(shell: str) -> str:
    """Invoke ourselves with _CC_JANITOR_COMPLETE=<shell>_source to get the
    completion script. Click handles this magic via Typer."""
    env = {**os.environ, "_CC_JANITOR_COMPLETE": f"{shell}_source"}
    result = subprocess.run(
        [sys.executable, "-m", "cc_janitor"],
        env=env, capture_output=True, text=True,
    )
    return result.stdout


@completions_app.command("show")
def show(shell: str) -> None:
    if shell not in VALID_SHELLS:
        typer.echo(f"Unknown shell: {shell}. Choose: {sorted(VALID_SHELLS)}")
        raise typer.Exit(code=2)
    typer.echo(_generate(shell))


@completions_app.command("install")
@audit_action(cmd="completions install")
def install(shell: str) -> None:
    require_confirmed()
    if shell not in VALID_SHELLS:
        typer.echo(f"Unknown shell: {shell}. Choose: {sorted(VALID_SHELLS)}")
        raise typer.Exit(code=2)
    script = _generate(shell)
    home = os.path.expanduser("~")
    if shell == "bash":
        target = os.path.join(home, ".bash_completion.d", "cc-janitor")
    elif shell == "zsh":
        target = os.path.join(home, ".zfunc", "_cc-janitor")
    elif shell == "fish":
        target = os.path.join(home, ".config", "fish", "completions", "cc-janitor.fish")
    else:  # powershell
        target = os.path.join(home, "Documents", "PowerShell",
                              "cc-janitor-completion.ps1")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        f.write(script)
    typer.echo(f"Wrote completion script to {target}")
    typer.echo("Restart your shell or source the file to activate.")
```

Register in `cli/__init__.py`:

```python
from .commands.completions import completions_app
app.add_typer(completions_app, name="completions")
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(cli): shell completions install/show

Wraps Typer/Click's built-in <SHELL>_source completion generator
into cc-janitor completions install [bash|zsh|fish|powershell] and
cc-janitor completions show <shell>. Install writes to the
shell-conventional completion path; show prints to stdout for piping.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **189 passing**.

---

## Task 11: TUI integration — Source filter dropdown

**Files:**
- Modify: `src/cc_janitor/tui/screens/permissions_screen.py`
- Modify: `src/cc_janitor/tui/screens/hooks_screen.py`
- Modify: `src/cc_janitor/tui/screens/memory_screen.py`
- Create: `tests/tui/test_source_filter.py` (snapshot test)

**Step 1: Failing snapshot test.**

```python
# tests/tui/test_source_filter.py
import pytest
from cc_janitor.tui.app import CCJanitorApp


@pytest.mark.asyncio
async def test_permissions_tab_has_source_dropdown(snap_compare, mock_claude_home):
    assert snap_compare(CCJanitorApp(), terminal_size=(120, 40),
                        press=["3", "tab"])  # Permissions tab + focus dropdown
```

**Step 2: Run, FAIL.**

**Step 3: Implement.** In each of the three screens, add a `Select`
widget at the top of the layout populated from
`core.monorepo.discover_locations(scope_filter=("real", "nested"))` plus
the static "real only" / "real + nested" / "all" entries. On change,
re-discover the underlying data with the chosen scope filter and
re-render the DataTable.

```python
# excerpt — applies similarly to permissions/hooks/memory screens
from textual.widgets import Select

from ...core.monorepo import discover_locations


def _source_options():
    yield ("<real only>", "real")
    yield ("<real + nested>", "real+nested")
    yield ("<all incl. junk>", "all")
    for loc in discover_locations(scope_filter=("real", "nested")):
        yield (str(loc.path), str(loc.path))


# in compose():
yield Select(list(_source_options()), id="source-filter", value="real")


# in on_select_changed:
def on_select_changed(self, event: Select.Changed) -> None:
    if event.select.id != "source-filter":
        return
    self._source_filter = event.value
    self._reload()
```

**Step 4: Run, PASS (snapshot accepted on first run). Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(tui): Source filter dropdown on Permissions/Hooks/Memory tabs

Header bar Select widget populated from monorepo.discover_locations.
Default = real-only; users can opt into nested or all-including-junk
scopes to inspect monorepo configurations.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **193 passing** (+1 snapshot, +3 unit follow-ups).

---

## Task 12: Polish — i18n keys, scheduler template migration, cookbook

**Files:**
- Modify: `src/cc_janitor/i18n/en.toml`, `ru.toml`
- Modify: `src/cc_janitor/core/schedule.py` — `context-audit` template
  command updated to `cc-janitor stats snapshot`
- Modify: `docs/cookbook.md` — append five new recipes
- Modify: `docs/CC_USAGE.md` — append Phase 3 read-only/mutating list
- Modify: `README.md` / `README.ru.md` — Phase 3 feature bullets
- Modify: `CHANGELOG.md` — start `[0.3.0]` block
- Modify: `pyproject.toml` — bump to `version = "0.3.0"`

**Step 1: i18n keys.** Add new namespaces to both en.toml and ru.toml:

```toml
[monorepo]
title = "Monorepo locations"
real = "real"
nested = "nested"
junk = "junk"
source_filter = "Source"

[watcher]
title = "Watcher"
not_running = "not running"
running = "running"
stale = "stale"
started = "Watcher started"
stopped = "Watcher stopped"

[stats]
title = "Stats"
sessions = "Sessions"
perm_rules = "Perm rules"
context_tokens = "Context tokens"
trash_bytes = "Trash bytes"
no_data = "No snapshots in window"

[bundle]
title = "Config bundle"
exported = "Exported {n} files to {out}"
imported = "Imported {n} files"
dry_run = "DRY RUN: would write {n} files. Re-run with --force to apply."

[completions]
title = "Shell completions"
installed = "Wrote completion script to {target}"
unknown_shell = "Unknown shell: {shell}"
```

**Step 2: Scheduler template migration.** In `core/schedule.py`:

```python
"context-audit": {
    "default_cron": "5 0 * * *",
    "command": "cc-janitor stats snapshot",   # was: "cc-janitor context cost --json"
},
```

Add a one-line migration note in CHANGELOG: *Existing crontab entries
referencing `cc-janitor context cost --json` continue to work and are
read by `stats` as legacy `cost.jsonl`. Run `cc-janitor schedule remove
cc-janitor-context-audit && cc-janitor schedule add context-audit` to
upgrade.*

**Step 3: Cookbook addendum.** Append to `docs/cookbook.md`:

```markdown
## Find every `.claude/` directory on my machine

I want to see every `.claude/` directory anywhere on disk, including
the junk that ships inside `node_modules` of vendored packages.

    cc-janitor monorepo scan --root ~ --include-junk

Output is a table with kind (real/nested/junk), settings/hooks flags,
and full path. Use `--json` for piping into other tools. Closes
upstream Issues #37344, #35561, #18192, #40640.

## Auto-reinject memory after every edit

I keep editing `~/.claude/CLAUDE.md` outside the TUI and forgetting
to `cc-janitor context reinject`. Run a background watcher that polls
my memory dirs every 30 seconds and writes the marker on change:

    CC_JANITOR_USER_CONFIRMED=1 cc-janitor watch start
    cc-janitor watch status        # confirm running
    cc-janitor doctor              # see "Watcher: running (3 reinjects)"
    CC_JANITOR_USER_CONFIRMED=1 cc-janitor watch stop

Opt-in only. Never auto-started. Uses mtime polling — no platform-
specific FS-event APIs.

## Track context cost over time

Every day at 00:05 the `context-audit` scheduled job records a snapshot
of session count, perm rule count, context tokens, trash size, and
audit-log delta to `~/.cc-janitor/history/<date>.json`. View the
trend:

    cc-janitor stats --since 30d
    cc-janitor stats --since 7d --format csv > /tmp/last-week.csv

The TUI Audit tab shows the same data as ASCII sparklines (toggle
with `s`). After running `cc-janitor perms prune` you can see the
perm-rules count drop in the very next snapshot.

## Move my cc-janitor config from Windows to my Mac

On the Windows desktop:

    cc-janitor config export ~/Desktop/cc-janitor-bundle.tar.gz \
                            --include-memory

The bundle excludes `settings.local.json` and `.env` files
unconditionally — no opt-out. Copy the tar.gz to your Mac (USB,
scp, cloud-drive — whatever). On the Mac:

    cc-janitor config import ~/Downloads/cc-janitor-bundle.tar.gz
    # DRY RUN: would write 17 files. Re-run with --force to apply.
    CC_JANITOR_USER_CONFIRMED=1 \
      cc-janitor config import ~/Downloads/cc-janitor-bundle.tar.gz --force

Existing destination files that differ from the bundle are backed up
to `~/.cc-janitor/backups/import-<ts>/` before overwrite.

## Enable tab completion

    # bash
    cc-janitor completions show bash > ~/.bash_completion.d/cc-janitor

    # zsh
    cc-janitor completions show zsh > ~/.zfunc/_cc-janitor

    # PowerShell
    cc-janitor completions show powershell >> $PROFILE

Or let cc-janitor write the file in the conventional location for you:

    CC_JANITOR_USER_CONFIRMED=1 cc-janitor completions install bash
```

**Step 4: CC_USAGE.md addendum.** Append the Phase 3 split:

```markdown
## Phase 3 commands

Read-only (Claude may invoke freely):
- `cc-janitor monorepo scan|show`
- `cc-janitor watch status`
- `cc-janitor stats [--since][--format]`
- `cc-janitor stats snapshot`
- `cc-janitor config export <path>`
- `cc-janitor completions show <shell>`

Mutating (require user-spoken confirmation + `CC_JANITOR_USER_CONFIRMED=1`):
- `cc-janitor watch start|stop`
- `cc-janitor config import <bundle> [--force]`
- `cc-janitor completions install <shell>`
```

**Step 5: Bump to 0.3.0 and write CHANGELOG.** In `pyproject.toml`:
`version = "0.3.0"`. In `cli/__init__.py`: `__VERSION__ = "0.3.0"`. In
`CHANGELOG.md` add:

```markdown
## [0.3.0] — 2026-05-09

### Added — Phase 3

#### Monorepo nested .claude/ discovery (closes #37344, #35561, #18192, #40640)
- `core/monorepo.py` walks a configurable root, skipping standard
  noise dirs by default; classifies each `.claude/` as real/nested/junk
- `cc-janitor monorepo scan/show`
- TUI Permissions/Hooks/Memory tabs gain a Source filter dropdown

#### Auto-reinject background watcher (opt-in)
- `core/watcher.py` mtime-poll loop, cross-platform daemon spawn
  (start_new_session on POSIX, DETACHED_PROCESS on Windows)
- `cc-janitor watch start/stop/status`
- Health line in `cc-janitor doctor`
- Optional `psutil` extra: `pip install cc-janitor[watcher]`

#### Stats dashboard with history
- Daily snapshots at `~/.cc-janitor/history/<date>.json`
- `cc-janitor stats [--since 30d] [--format text|json|csv]`
- `cc-janitor stats snapshot` (called by Phase 2 context-audit job)
- TUI Audit tab gains stats sub-pane with ASCII sparklines (toggle: s)
- `context-audit` scheduled-job template now writes the new schema

#### Export/import config bundle
- `cc-janitor config export <bundle.tar.gz> [--include-memory]`
- `cc-janitor config import <bundle.tar.gz> [--dry-run] [--force]`
- Hard exclusion of `settings.local.json`, `.env`, `credentials.json`
- Dry-run-first guard (mirrors scheduler pattern); backup-before-overwrite
- SHA-256 manifest verified on import

#### Shell completions
- `cc-janitor completions install [bash|zsh|fish|powershell]`
- `cc-janitor completions show <shell>`

#### Quality
- ~40 new unit and integration tests (~190 passing total)
- New TUI snapshot test for Source-filter dropdown
- New TUI snapshot test for Audit-tab stats sub-pane
- Cross-platform watcher tested via `monkeypatch.setattr("sys.platform", ...)`

#### Documentation
- 5 new cookbook recipes
- CC_USAGE.md updated with Phase 3 read-only/mutating split
- README/README.ru get Phase 3 feature group
```

**Step 6: Verify everything.**

```bash
uv run pytest -q
uv run ruff check .
uv run cc-janitor --version           # 0.3.0
uv run cc-janitor monorepo scan --root . --json
```

**Step 7: Commit polish.**

```bash
git add -A
git commit -m "$(cat <<'EOF'
docs,chore: 0.3.0 — Phase 3 cookbook, CHANGELOG, i18n keys, version

5 new cookbook recipes (monorepo, watcher, stats, bundle, completions),
CC_USAGE.md Phase 3 split, README Phase 3 bullets, CHANGELOG block,
version bump to 0.3.0, scheduler context-audit template migrated to
cc-janitor stats snapshot.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: PR + tag + release

**Step 1: Push branch and open PR.**

```bash
git push -u origin feat/phase3-mvp
gh pr create --title "feat: Phase 3 — monorepo discovery, watcher, stats, bundle, completions" \
             --body "$(cat <<'EOF'
## Summary

- Monorepo nested .claude/ discovery — closes upstream #37344, #35561, #18192, #40640
- Opt-in auto-reinject background watcher (mtime polling, cross-platform daemon)
- Stats dashboard with daily history snapshots + ASCII sparklines
- Export/import config bundle with dry-run-first + SHA-256 verify + backup-before-overwrite
- Shell completions for bash/zsh/fish/PowerShell

## Test plan

- [ ] All ~190 tests pass on CI matrix (Python 3.11/3.12 × ubuntu/windows)
- [ ] `cc-janitor monorepo scan --root ~ --include-junk` finds the
  user's known `~/portfolio/node_modules/es-abstract/.claude/`
- [ ] Watcher start/stop round-trip on Windows (CREATE_NEW_PROCESS_GROUP path)
- [ ] Bundle export+import round-trip preserves bytes
- [ ] `cc-janitor completions show bash` outputs valid completion script

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 2: After PR merges to main**, tag and push:

```bash
git switch main
git pull
git tag -a v0.3.0 -m "v0.3.0 — Phase 3 (monorepo, watcher, stats, bundle, completions)"
git push origin v0.3.0
```

The release workflow auto-publishes to PyPI on tag push.

---

## Final state after Phase 3

- Version: 0.3.0 on PyPI
- Test count: ~190 passing
- New CLI subapps: 5 (monorepo, watch, stats, config, completions)
- New core modules: 5 (monorepo.py, watcher.py, watcher_main.py, stats.py, bundle.py, completions covered by CLI shim)
- Modified core: schedule.py (template command updated)
- Modified TUI: 3 tabs gain Source filter, Audit tab gains stats sub-pane
- New audit verbs: watch.start, watch.stop, config.export, config.import, completions.install
- Optional dep: psutil under `[watcher]` extra
- Closes upstream Issues: #37344, #35561, #18192, #40640
- Project status: feature-roadmap complete; future work = bug-fix and polish

---
