# cc-janitor Phase 4 Implementation Plan — Auto Dream safety net

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Ship `cc-janitor` v0.4.0 — the deterministic safety harness around
Claude Code's Auto Dream. Snapshot before consolidation, diff after, rollback
if needed, audit always. Surfaces verified user pain from issues #47959,
#50694, #38493 via 5 read-only diagnostic surfaces + 2 mutation surfaces, all
built on Phase 1–3 primitives. New top-level `dream` subapp; new 8th TUI tab;
new optional `~/.cc-janitor/config.toml`. No Phase 1/2/3 module is broken or
moved.

**Architecture:** Single-package, two-mode (TUI + CLI). Five new core modules
(`config.py`, `dream_snapshot.py`, `dream_diff.py`, `dream_doctor.py`,
`sleep_hygiene.py`), one new Typer subapp, one extended subapp (`stats`), one
extended watcher mode (`--dream`), one new TUI screen (`DreamScreen`), one
new scheduled-job template (`dream-tar-compact`). No new mandatory
dependencies — stdlib `tomllib`, `difflib`, `tarfile`.

**Reference design:** `docs/plans/2026-05-11-cc-janitor-phase4-dream-design.md`.

**Predecessor plans (style mirror):**
`docs/plans/2026-05-05-cc-janitor-phase2-mvp.md`,
`docs/plans/2026-05-09-cc-janitor-phase3-mvp.md`.

---

## Conventions used throughout this plan

- **Working dir** = `C:\Users\creat\OneDrive\Рабочий стол\CREATMAN\Tools\cc-janitor` (Windows path; in bash `~/OneDrive/Рабочий стол/CREATMAN/Tools/cc-janitor`).
- **Branch:** `feat/phase4-dream`. Branch from `main` after Phase 3 / 0.3.3
  merge (commit `9cd7b8d`). PR to `main` at the end.
- **Every task = TDD cycle:** write failing test → run it → implement → run
  again → commit. Conventional Commits with the
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`
  trailer.
- **Audit log policy:** every mutating CLI command starts with
  `safety.require_confirmed()` and is wrapped in `audit_action(...)` from
  `cli/_audit.py`. Use `mode="cli"` (CLI), `mode="tui"` (TUI mutations), or
  `mode="scheduled"` (scheduler-driven). `mode=` kwarg has existed since 0.3.2.
- **TUI mutations:** route every TUI-driven mutation through `tui/_confirm.py`'s
  `ConfirmModal` + `tui_confirmed()` context manager (introduced as part of
  0.3.2 C1 fix). Never `os.environ.setdefault("CC_JANITOR_USER_CONFIRMED", "1")`.
- **Claude home lookup:** use `Path.home() / ".claude"`. Do NOT use
  `get_paths().home.parent` — that was the broken pattern fixed in Phase 1.
- **No `--no-verify`, no `--amend` after hook failures** — fix and create a
  new commit.
- **Expected pytest count** is given per task so the implementer can spot
  regressions. Phase 3 / 0.3.3 baseline ≈ **200 passing**.

---

## Task 0: Branch + version bump

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/cc_janitor/cli/__init__.py` (`__VERSION__`)

**Step 1: Branch.**

```bash
git fetch origin
git switch main
git pull
git switch -c feat/phase4-dream
```

**Step 2: Bump version.** In `pyproject.toml`:

```toml
[project]
name = "cc-janitor"
version = "0.4.0.dev0"
```

In `src/cc_janitor/cli/__init__.py`:

```python
__VERSION__ = "0.4.0.dev0"
```

**Step 3: Verify.**

```bash
uv pip install -e ".[dev]"
uv run cc-janitor --version           # → 0.4.0.dev0
uv run pytest -q                      # full Phase 3 suite passes
```

**Step 4: Commit.**

```bash
git commit -am "$(cat <<'EOF'
chore: bump to 0.4.0.dev0 for Phase 4 Dream safety net

Phase 4 adds no new mandatory dependencies. tomllib is stdlib;
difflib + tarfile are already used elsewhere in the codebase.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 1: `core/config.py` — TOML loader

**Files:**
- Create: `src/cc_janitor/core/config.py`
- Create: `tests/unit/test_config_loader.py`

**Step 1: Failing test.**

```python
# tests/unit/test_config_loader.py
from pathlib import Path
from cc_janitor.core.config import (
    Config, DreamDoctorConfig, SnapshotsConfig, HygieneConfig,
    load_config, DEFAULTS,
)


def test_defaults_when_missing(tmp_path):
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert cfg.dream_doctor.disk_warning_mb == 100
    assert cfg.dream_doctor.memory_file_count_threshold == 50
    assert cfg.dream_doctor.memory_md_line_threshold == 180
    assert cfg.snapshots.raw_retention_days == 7
    assert cfg.snapshots.tar_retention_days == 30


def test_partial_override(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[dream_doctor]\n'
        'disk_warning_mb = 500\n'
        '[snapshots]\n'
        'raw_retention_days = 14\n',
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.dream_doctor.disk_warning_mb == 500
    assert cfg.dream_doctor.memory_md_line_threshold == 180  # default kept
    assert cfg.snapshots.raw_retention_days == 14
    assert cfg.snapshots.tar_retention_days == 30


def test_malformed_falls_back_to_defaults(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("this is not [valid toml", encoding="utf-8")
    cfg = load_config(p)
    assert cfg == DEFAULTS


def test_extra_relative_date_terms(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        '[hygiene]\n'
        'relative_date_terms_extra = ["позавчера", "tomorrow"]\n',
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert "позавчера" in cfg.hygiene.relative_date_terms_extra
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/core/config.py
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

from .state import get_paths


@dataclass(frozen=True)
class DreamDoctorConfig:
    disk_warning_mb: int = 100
    memory_file_count_threshold: int = 50
    memory_md_line_threshold: int = 180


@dataclass(frozen=True)
class SnapshotsConfig:
    raw_retention_days: int = 7
    tar_retention_days: int = 30


@dataclass(frozen=True)
class HygieneConfig:
    relative_date_terms_extra: tuple[str, ...] = ()
    contradiction_jaccard_threshold: float = 0.5


@dataclass(frozen=True)
class Config:
    dream_doctor: DreamDoctorConfig = field(default_factory=DreamDoctorConfig)
    snapshots: SnapshotsConfig = field(default_factory=SnapshotsConfig)
    hygiene: HygieneConfig = field(default_factory=HygieneConfig)


DEFAULTS = Config()


def _default_path() -> Path:
    return get_paths().home / "config.toml"


def load_config(path: Path | None = None) -> Config:
    p = path if path is not None else _default_path()
    if not p.exists():
        return DEFAULTS
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError):
        return DEFAULTS
    dd = data.get("dream_doctor", {}) or {}
    sn = data.get("snapshots", {}) or {}
    hy = data.get("hygiene", {}) or {}
    return Config(
        dream_doctor=replace(DEFAULTS.dream_doctor, **{
            k: v for k, v in dd.items()
            if k in {"disk_warning_mb", "memory_file_count_threshold",
                     "memory_md_line_threshold"}
        }),
        snapshots=replace(DEFAULTS.snapshots, **{
            k: v for k, v in sn.items()
            if k in {"raw_retention_days", "tar_retention_days"}
        }),
        hygiene=HygieneConfig(
            relative_date_terms_extra=tuple(
                hy.get("relative_date_terms_extra", ())
            ),
            contradiction_jaccard_threshold=float(
                hy.get("contradiction_jaccard_threshold", 0.5)
            ),
        ),
    )
```

**Step 4: Run, PASS. Commit.**

```bash
git add src/cc_janitor/core/config.py tests/unit/test_config_loader.py
git commit -m "$(cat <<'EOF'
feat(core): config.toml loader with documented defaults

All Phase 4 thresholds (dream_doctor disk/file/line limits, snapshot
retention, hygiene regex extras) loaded from optional
~/.cc-janitor/config.toml. Missing or malformed file → DEFAULTS.
Partial overrides preserve unspecified defaults.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **+4 → ~204**.

---

## Task 2: `core/dream_snapshot.py` — lifecycle state machine

**Files:**
- Create: `src/cc_janitor/core/dream_snapshot.py`
- Create: `tests/unit/test_dream_snapshot.py`

**Step 1: Failing test.**

```python
# tests/unit/test_dream_snapshot.py
import json
from datetime import datetime, timezone
from pathlib import Path
from cc_janitor.core.dream_snapshot import (
    DreamSnapshotPair, LockState, observe_lock, snapshot_pre,
    snapshot_post, record_pair, history,
)


def _fake_memory(root: Path) -> Path:
    mem = root / ".claude" / "projects" / "-home-u-proj" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("a\nb\nc\n")
    (mem / "x.md").write_text("x\n")
    return mem


def test_observe_lock_appearing(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    mem = _fake_memory(tmp_path)
    lock = mem / ".consolidate-lock"
    state = LockState()
    transition = observe_lock(mem, state)
    assert transition.kind == "no_change"
    lock.write_text("38249")
    transition = observe_lock(mem, state)
    assert transition.kind == "lock_appeared"
    assert transition.pid == 38249


def test_snapshot_pre_writes_raw_mirror(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    mem = _fake_memory(tmp_path)
    pair_id = "20260511T120000Z-proj"
    snapshot_pre(pair_id, mem)
    pre = tmp_path / "jhome" / "backups" / "dream" / f"{pair_id}-pre"
    assert (pre / "MEMORY.md").exists()
    assert (pre / "MEMORY.md").read_text() == "a\nb\nc\n"


def test_full_pair_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    mem = _fake_memory(tmp_path)
    pair_id = "20260511T120000Z-proj"
    pre = snapshot_pre(pair_id, mem)
    # Auto Dream "ran" — mutate.
    (mem / "MEMORY.md").write_text("a\nb\n")
    (mem / "x.md").unlink()
    post = snapshot_post(pair_id, mem)
    pair = record_pair(pair_id, mem, project_slug="proj",
                       dream_pid_in_lock=38249,
                       ts_pre=datetime.now(timezone.utc),
                       ts_post=datetime.now(timezone.utc),
                       pre_dir=pre, post_dir=post)
    assert pair.file_count_delta == -1
    assert pair.line_count_delta < 0
    # Reload from jsonl.
    items = history()
    assert any(p.pair_id == pair_id for p in items)
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/core/dream_snapshot.py
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .state import get_paths


@dataclass
class LockState:
    """Per-daemon-iteration map: memory_dir → currently-seen-lock-pid."""
    seen: dict[Path, int] = field(default_factory=dict)


@dataclass
class LockTransition:
    kind: Literal["no_change", "lock_appeared", "lock_gone"]
    memory_dir: Path | None = None
    pid: int | None = None


@dataclass
class DreamSnapshotPair:
    pair_id: str
    project_slug: str
    project_path: str
    claude_memory_dir: str
    ts_pre: str
    ts_post: str | None
    paths_in_pre: list[str]
    paths_in_post: list[str] | None
    file_count_delta: int | None
    line_count_delta: int | None
    has_diff: bool | None
    dream_pid_in_lock: int | None
    storage: Literal["raw", "tar"] = "raw"


def _dream_root() -> Path:
    return get_paths().home / "backups" / "dream"


def _history_path() -> Path:
    return get_paths().home / "dream-snapshots.jsonl"


def observe_lock(memory_dir: Path, state: LockState) -> LockTransition:
    lock = memory_dir / ".consolidate-lock"
    prev_pid = state.seen.get(memory_dir)
    if lock.exists():
        try:
            pid = int(lock.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            pid = 0
        if prev_pid is None:
            state.seen[memory_dir] = pid
            return LockTransition("lock_appeared", memory_dir, pid)
        return LockTransition("no_change", memory_dir, pid)
    else:
        if prev_pid is not None:
            state.seen.pop(memory_dir, None)
            return LockTransition("lock_gone", memory_dir, prev_pid)
        return LockTransition("no_change", memory_dir, None)


def _copy_tree(src: Path, dst: Path) -> list[Path]:
    dst.mkdir(parents=True, exist_ok=True)
    rels: list[Path] = []
    for f in src.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(src)
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, out)
        rels.append(rel)
    return rels


def snapshot_pre(pair_id: str, memory_dir: Path) -> Path:
    out = _dream_root() / f"{pair_id}-pre"
    _copy_tree(memory_dir, out)
    return out


def snapshot_post(pair_id: str, memory_dir: Path) -> Path:
    out = _dream_root() / f"{pair_id}-post"
    _copy_tree(memory_dir, out)
    return out


def _count_lines(d: Path) -> int:
    total = 0
    for f in d.rglob("*.md"):
        try:
            total += sum(1 for _ in f.open("r", encoding="utf-8", errors="ignore"))
        except OSError:
            pass
    return total


def record_pair(
    pair_id: str,
    memory_dir: Path,
    *,
    project_slug: str,
    dream_pid_in_lock: int | None,
    ts_pre: datetime,
    ts_post: datetime | None,
    pre_dir: Path,
    post_dir: Path | None,
) -> DreamSnapshotPair:
    pre_files = sorted(str(p.relative_to(pre_dir))
                       for p in pre_dir.rglob("*") if p.is_file())
    post_files = (sorted(str(p.relative_to(post_dir))
                         for p in post_dir.rglob("*") if p.is_file())
                  if post_dir else None)
    file_delta = (len(post_files) - len(pre_files)) if post_files is not None else None
    line_delta = (_count_lines(post_dir) - _count_lines(pre_dir)) if post_dir else None
    has_diff = (file_delta != 0 or line_delta != 0) if line_delta is not None else None
    pair = DreamSnapshotPair(
        pair_id=pair_id,
        project_slug=project_slug,
        project_path=str(memory_dir.parent.parent),
        claude_memory_dir=str(memory_dir),
        ts_pre=ts_pre.isoformat(),
        ts_post=ts_post.isoformat() if ts_post else None,
        paths_in_pre=pre_files,
        paths_in_post=post_files,
        file_count_delta=file_delta,
        line_count_delta=line_delta,
        has_diff=has_diff,
        dream_pid_in_lock=dream_pid_in_lock,
        storage="raw",
    )
    hp = _history_path()
    hp.parent.mkdir(parents=True, exist_ok=True)
    with hp.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(pair)) + "\n")
    return pair


def history() -> list[DreamSnapshotPair]:
    hp = _history_path()
    if not hp.exists():
        return []
    out: list[DreamSnapshotPair] = []
    for line in hp.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        out.append(DreamSnapshotPair(**d))
    return out


def project_slug_from_memory_dir(memory_dir: Path) -> str:
    """`.../projects/-home-u-proj/memory` → "proj" (last hyphen-segment)."""
    parent = memory_dir.parent.name
    parts = [p for p in parent.split("-") if p]
    return parts[-1] if parts else parent
```

**Step 4: Run, PASS. Commit.**

```bash
git add src/cc_janitor/core/dream_snapshot.py tests/unit/test_dream_snapshot.py
git commit -m "$(cat <<'EOF'
feat(core): dream snapshot lifecycle state machine + raw mirror

Lock-file observer with NO_LOCK/LOCK_HELD transitions. snapshot_pre
and snapshot_post copy ~/.claude/projects/<slug>/memory/ trees to
~/.cc-janitor/backups/dream/<pair_id>-{pre,post}/. record_pair writes
one JSONL record with file_count_delta, line_count_delta, has_diff,
dream_pid_in_lock. Storage starts as "raw"; tar compaction (Task 10)
flips it to "tar" later.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **+3 → ~207**.

---

## Task 3: Watcher `--dream` mode extension

**Files:**
- Modify: `src/cc_janitor/core/watcher.py`
- Modify: `src/cc_janitor/cli/commands/watch.py`
- Modify: `src/cc_janitor/core/watcher_main.py`
- Create: `tests/unit/test_watcher_dream.py`

**Step 1: Failing test.**

```python
# tests/unit/test_watcher_dream.py
from datetime import datetime, timezone
from pathlib import Path
from cc_janitor.core.dream_snapshot import LockState, history
from cc_janitor.core.watcher import run_dream_once


def test_run_dream_once_appears_then_gone(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    mem = tmp_path / ".claude" / "projects" / "-proj" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("a\n")
    state = LockState()
    pending: dict = {}

    # No lock yet.
    run_dream_once([mem], state, pending)
    assert not pending

    # Lock appears.
    (mem / ".consolidate-lock").write_text("4711")
    run_dream_once([mem], state, pending)
    assert mem in pending
    pair_id = pending[mem]["pair_id"]
    assert (tmp_path / "jhome" / "backups" / "dream" / f"{pair_id}-pre").exists()

    # Lock disappears + content changed.
    (mem / "MEMORY.md").write_text("a\nb\n")
    (mem / ".consolidate-lock").unlink()
    run_dream_once([mem], state, pending)
    assert mem not in pending
    h = history()
    assert any(p.pair_id == pair_id for p in h)
```

**Step 2: Run, FAIL.**

**Step 3: Implement.** Append to `core/watcher.py`:

```python
# core/watcher.py — append at module bottom
from .dream_snapshot import (
    LockState, LockTransition, observe_lock,
    snapshot_pre, snapshot_post, record_pair,
    project_slug_from_memory_dir,
)


def _new_pair_id(slug: str) -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{slug}"


def run_dream_once(
    memory_dirs: list[Path],
    state: LockState,
    pending: dict[Path, dict],
) -> None:
    """Single dream-watch poll iteration."""
    for mem in memory_dirs:
        t = observe_lock(mem, state)
        if t.kind == "lock_appeared":
            slug = project_slug_from_memory_dir(mem)
            pair_id = _new_pair_id(slug)
            pre_dir = snapshot_pre(pair_id, mem)
            pending[mem] = {
                "pair_id": pair_id,
                "slug": slug,
                "pre_dir": pre_dir,
                "ts_pre": datetime.now(timezone.utc),
                "pid": t.pid,
            }
        elif t.kind == "lock_gone":
            info = pending.pop(mem, None)
            if info is None:
                continue
            post_dir = snapshot_post(info["pair_id"], mem)
            record_pair(
                info["pair_id"], mem,
                project_slug=info["slug"],
                dream_pid_in_lock=info["pid"],
                ts_pre=info["ts_pre"],
                ts_post=datetime.now(timezone.utc),
                pre_dir=info["pre_dir"],
                post_dir=post_dir,
            )
```

Extend `run_watcher` to accept `dream: bool` and `memory_dirs_for_dream`, and
update `watcher_main.py` to parse `--dream` and pass through. In
`cli/commands/watch.py` `start()` add `--dream/--no-dream` Typer option,
default `False`, propagating via env var
`CC_JANITOR_WATCH_DREAM=1` to `watcher_main.py`.

```python
# cli/commands/watch.py — add to start()
dream: bool = typer.Option(False, "--dream/--no-dream",
                           help="Also snapshot around Auto Dream lock-file lifecycle"),
no_memory: bool = typer.Option(False, "--no-memory",
                               help="Disable mtime reinject watch; only --dream"),
# ...
if dream:
    os.environ["CC_JANITOR_WATCH_DREAM"] = "1"
if no_memory:
    os.environ["CC_JANITOR_WATCH_NO_MEMORY"] = "1"
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(watcher): --dream mode polls .consolidate-lock lifecycle

Extends the Phase 3 watcher daemon to optionally observe per-project
.consolidate-lock files. On lock-appears: write pre-snapshot to
~/.cc-janitor/backups/dream/<pair_id>-pre/. On lock-gone: write
post-snapshot and record a DreamSnapshotPair to dream-snapshots.jsonl.
Opt-in via `cc-janitor watch start --dream`. mtime reinject watch
remains the default; add --no-memory to disable it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **+1 → ~208**.

---

## Task 4: `core/dream_diff.py` — pre vs post comparison

**Files:**
- Create: `src/cc_janitor/core/dream_diff.py`
- Create: `tests/unit/test_dream_diff.py`

**Step 1: Failing test.**

```python
# tests/unit/test_dream_diff.py
from pathlib import Path
from cc_janitor.core.dream_diff import compute_diff, DreamFileDelta


def _mk(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_compute_diff_added_removed_changed(tmp_path):
    pre = tmp_path / "pre"
    post = tmp_path / "post"
    _mk(pre / "MEMORY.md", "a\nb\nc\n")
    _mk(pre / "removed.md", "x\n")
    _mk(post / "MEMORY.md", "a\nB\nc\n")
    _mk(post / "added.md", "y\n")
    diff = compute_diff(pre, post)
    by = {str(d.rel_path): d for d in diff.deltas}
    assert by["MEMORY.md"].status == "changed"
    assert by["MEMORY.md"].lines_added == 1
    assert by["MEMORY.md"].lines_removed == 1
    assert by["MEMORY.md"].unified_diff is not None
    assert by["removed.md"].status == "removed"
    assert by["added.md"].status == "added"
    assert diff.summary["files_added"] == 1
    assert diff.summary["files_removed"] == 1
    assert diff.summary["files_changed"] == 1
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/core/dream_diff.py
from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class DreamFileDelta:
    rel_path: Path
    status: Literal["added", "removed", "changed", "unchanged"]
    lines_added: int
    lines_removed: int
    unified_diff: str | None


@dataclass
class DreamDiff:
    pre_dir: Path
    post_dir: Path
    deltas: list[DreamFileDelta]
    summary: dict


def _read_lines(p: Path) -> list[str]:
    try:
        return p.read_text(encoding="utf-8").splitlines(keepends=True)
    except (OSError, UnicodeDecodeError):
        return []


def _walk_rel(d: Path) -> set[Path]:
    return {f.relative_to(d) for f in d.rglob("*") if f.is_file()}


def compute_diff(pre_dir: Path, post_dir: Path) -> DreamDiff:
    pre_set = _walk_rel(pre_dir)
    post_set = _walk_rel(post_dir)
    all_paths = sorted(pre_set | post_set, key=str)
    deltas: list[DreamFileDelta] = []
    summary = {"files_added": 0, "files_removed": 0,
               "files_changed": 0, "files_unchanged": 0}
    for rel in all_paths:
        in_pre = rel in pre_set
        in_post = rel in post_set
        if in_pre and not in_post:
            pre_lines = _read_lines(pre_dir / rel)
            deltas.append(DreamFileDelta(
                rel_path=rel, status="removed",
                lines_added=0, lines_removed=len(pre_lines),
                unified_diff="".join(difflib.unified_diff(
                    pre_lines, [], fromfile=str(rel), tofile="/dev/null")),
            ))
            summary["files_removed"] += 1
            continue
        if in_post and not in_pre:
            post_lines = _read_lines(post_dir / rel)
            deltas.append(DreamFileDelta(
                rel_path=rel, status="added",
                lines_added=len(post_lines), lines_removed=0,
                unified_diff="".join(difflib.unified_diff(
                    [], post_lines, fromfile="/dev/null", tofile=str(rel))),
            ))
            summary["files_added"] += 1
            continue
        pre_lines = _read_lines(pre_dir / rel)
        post_lines = _read_lines(post_dir / rel)
        if pre_lines == post_lines:
            deltas.append(DreamFileDelta(rel, "unchanged", 0, 0, None))
            summary["files_unchanged"] += 1
            continue
        ud = "".join(difflib.unified_diff(
            pre_lines, post_lines, fromfile=str(rel), tofile=str(rel), n=3))
        added = sum(1 for ln in ud.splitlines()
                    if ln.startswith("+") and not ln.startswith("+++"))
        removed = sum(1 for ln in ud.splitlines()
                      if ln.startswith("-") and not ln.startswith("---"))
        deltas.append(DreamFileDelta(rel, "changed", added, removed, ud))
        summary["files_changed"] += 1
    return DreamDiff(pre_dir, post_dir, deltas, summary)
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(core): dream_diff — file-level + unified-diff over pre/post mirrors

DreamFileDelta classifies each path as added/removed/changed/unchanged,
counts +/- lines, embeds difflib.unified_diff body. Summary dict
aggregates counts. No semantic grouping (Phase 5).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **+1 → ~209**.

---

## Task 5: `core/dream_doctor.py` — 9-check matrix

**Files:**
- Create: `src/cc_janitor/core/dream_doctor.py`
- Create: `tests/unit/test_dream_doctor.py`

**Step 1: Failing test.**

```python
# tests/unit/test_dream_doctor.py
from pathlib import Path
from cc_janitor.core.dream_doctor import run_checks, DoctorCheck


def test_doctor_runs_all_9_checks(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        '{"autoDreamEnabled": true}', encoding="utf-8")
    checks = run_checks()
    ids = {c.id for c in checks}
    expected = {"stale_lock", "autodream_enabled", "server_gate",
                "last_dream_ts", "backup_dir_health", "memory_md_cap",
                "disk_usage", "memory_file_count", "duplicate_summary"}
    assert expected.issubset(ids)


def test_stale_lock_with_dead_pid_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    mem = tmp_path / ".claude" / "projects" / "-proj" / "memory"
    mem.mkdir(parents=True)
    (mem / ".consolidate-lock").write_text("999999")  # very unlikely-alive PID
    (tmp_path / ".claude" / "settings.json").write_text("{}")
    checks = {c.id: c for c in run_checks()}
    assert checks["stale_lock"].severity == "FAIL"
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/core/dream_doctor.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .config import load_config
from .dream_snapshot import history
from .memory import find_duplicate_lines
from .state import get_paths

Severity = Literal["OK", "WARN", "FAIL", "INFO"]


@dataclass
class DoctorCheck:
    id: str
    title: str
    severity: Severity
    message: str
    detail: dict | None = None


def _claude_home() -> Path:
    return Path.home() / ".claude"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil  # type: ignore
        return psutil.pid_exists(pid)
    except ImportError:
        pass
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def _check_stale_lock() -> DoctorCheck:
    projects = _claude_home() / "projects"
    if not projects.exists():
        return DoctorCheck("stale_lock", "Stale .consolidate-lock",
                           "OK", "No projects directory yet.")
    stale: list[tuple[Path, int]] = []
    for proj in projects.iterdir():
        lock = proj / "memory" / ".consolidate-lock"
        if not lock.exists():
            continue
        try:
            pid = int(lock.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            pid = 0
        if not _pid_alive(pid):
            stale.append((lock, pid))
    if stale:
        return DoctorCheck(
            "stale_lock", "Stale .consolidate-lock", "FAIL",
            f"{len(stale)} stale lock file(s) found (silently disables Auto Dream — Issue #50694).",
            {"locks": [{"path": str(p), "pid": pid} for p, pid in stale]},
        )
    return DoctorCheck("stale_lock", "Stale .consolidate-lock", "OK",
                       "No stale lock files.")


def _check_autodream_enabled() -> DoctorCheck:
    s = _claude_home() / "settings.json"
    if not s.exists():
        return DoctorCheck("autodream_enabled", "autoDreamEnabled", "INFO",
                           "settings.json missing.")
    try:
        data = json.loads(s.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DoctorCheck("autodream_enabled", "autoDreamEnabled", "WARN",
                           "settings.json unreadable.")
    val = data.get("autoDreamEnabled", False)
    if val:
        return DoctorCheck("autodream_enabled", "autoDreamEnabled", "OK",
                           "Enabled in settings.json.")
    return DoctorCheck("autodream_enabled", "autoDreamEnabled", "WARN",
                       "Auto Dream is disabled in settings.json.")


def _check_server_gate() -> DoctorCheck:
    # Inference only — not invoked at doctor time, would need claude CLI.
    return DoctorCheck("server_gate", "Server-gate inference", "INFO",
                       "Run `claude --print --headless \"/dream\"` to verify; "
                       "'Unknown skill' means flag is off server-side (#38461).")


def _check_last_dream() -> DoctorCheck:
    h = history()
    if not h:
        return DoctorCheck("last_dream_ts", "Last dream observed",
                           "INFO", "No paired snapshots yet.")
    last = h[-1]
    return DoctorCheck("last_dream_ts", "Last dream observed", "OK",
                       f"Last paired snapshot: {last.ts_pre} ({last.project_slug}).",
                       {"pair_id": last.pair_id})


def _dir_size_mb(d: Path) -> float:
    if not d.exists():
        return 0.0
    return sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1024 / 1024


def _check_backup_dir_health() -> DoctorCheck:
    d = get_paths().home / "backups" / "dream"
    if not d.exists():
        return DoctorCheck("backup_dir_health", "Backup directory health",
                           "INFO", "No dream backups yet.")
    return DoctorCheck("backup_dir_health", "Backup directory health", "OK",
                       f"Exists, {_dir_size_mb(d):.1f} MB.")


def _check_memory_md_cap(cfg) -> DoctorCheck:
    threshold = cfg.dream_doctor.memory_md_line_threshold
    projects = _claude_home() / "projects"
    if not projects.exists():
        return DoctorCheck("memory_md_cap", "MEMORY.md cap usage", "OK",
                           "No projects.")
    over: list[tuple[str, int]] = []
    for p in projects.iterdir():
        m = p / "memory" / "MEMORY.md"
        if not m.exists():
            continue
        n = sum(1 for _ in m.open("r", encoding="utf-8", errors="ignore"))
        if n >= threshold:
            over.append((p.name, n))
    if over:
        return DoctorCheck("memory_md_cap", "MEMORY.md cap usage", "WARN",
                           f"{len(over)} project(s) within {threshold}-line warning band "
                           "(Anthropic hard cap ≈ 200).",
                           {"projects": over})
    return DoctorCheck("memory_md_cap", "MEMORY.md cap usage", "OK",
                       f"All MEMORY.md files under {threshold} lines.")


def _check_disk_usage(cfg) -> DoctorCheck:
    threshold = cfg.dream_doctor.disk_warning_mb
    used = _dir_size_mb(get_paths().home / "backups" / "dream")
    sev: Severity = "WARN" if used > threshold else "OK"
    return DoctorCheck("disk_usage", "Dream backup disk usage", sev,
                       f"{used:.1f} MB / threshold {threshold} MB.")


def _check_memory_file_count(cfg) -> DoctorCheck:
    threshold = cfg.dream_doctor.memory_file_count_threshold
    projects = _claude_home() / "projects"
    if not projects.exists():
        return DoctorCheck("memory_file_count", "Memory file count", "OK",
                           "No projects.")
    over: list[tuple[str, int]] = []
    for p in projects.iterdir():
        m = p / "memory"
        if not m.is_dir():
            continue
        cnt = sum(1 for _ in m.rglob("*.md"))
        if cnt > threshold:
            over.append((p.name, cnt))
    if over:
        return DoctorCheck("memory_file_count", "Memory file count", "WARN",
                           f"{len(over)} project(s) over {threshold} memory files; "
                           "consider `cc-janitor memory archive --stale`.",
                           {"projects": over})
    return DoctorCheck("memory_file_count", "Memory file count", "OK",
                       f"All projects under {threshold} memory files.")


def _check_duplicate_summary() -> DoctorCheck:
    projects = _claude_home() / "projects"
    if not projects.exists():
        return DoctorCheck("duplicate_summary", "Cross-file duplicates",
                           "OK", "No projects.")
    all_paths: list[Path] = []
    for p in projects.iterdir():
        m = p / "memory"
        if m.is_dir():
            all_paths.extend(m.rglob("*.md"))
    dups = find_duplicate_lines(all_paths, min_length=8)
    if not dups:
        return DoctorCheck("duplicate_summary", "Cross-file duplicates",
                           "OK", "No cross-file duplicates ≥ 8 chars.")
    top = sorted(dups, key=lambda d: -len(d.occurrences))[:5]
    return DoctorCheck("duplicate_summary", "Cross-file duplicates", "INFO",
                       f"{len(dups)} duplicated lines across memory files.",
                       {"top": [{"line": d.line[:80],
                                 "count": len(d.occurrences)} for d in top]})


def run_checks() -> list[DoctorCheck]:
    cfg = load_config()
    return [
        _check_stale_lock(),
        _check_autodream_enabled(),
        _check_server_gate(),
        _check_last_dream(),
        _check_backup_dir_health(),
        _check_memory_md_cap(cfg),
        _check_disk_usage(cfg),
        _check_memory_file_count(cfg),
        _check_duplicate_summary(),
    ]
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(core): dream_doctor — 9-check diagnostic matrix

stale_lock (Issue #50694), autodream_enabled, server_gate (Issue
#38461), last_dream_ts, backup_dir_health, memory_md_cap, disk_usage,
memory_file_count, duplicate_summary. All thresholds from
config.toml; cross-file dup check reuses Phase 1 find_duplicate_lines.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **+2 → ~211**.

---

## Task 6: `core/sleep_hygiene.py` — 4 metrics

**Files:**
- Create: `src/cc_janitor/core/sleep_hygiene.py`
- Create: `tests/unit/test_sleep_hygiene.py`

**Step 1: Failing test.**

```python
# tests/unit/test_sleep_hygiene.py
from pathlib import Path
from cc_janitor.core.sleep_hygiene import (
    compute_project_hygiene, _scan_relative_dates,
    _extract_contradiction_subjects,
)


def test_relative_date_density_finds_en_and_ru(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("yesterday we did X\nна прошлой неделе also Y\nstable text\n",
                 encoding="utf-8")
    matches = _scan_relative_dates([f], extra_terms=())
    terms = {m[2] for m in matches}
    assert "yesterday" in terms
    assert "на прошлой неделе" in terms


def test_contradiction_extraction(tmp_path):
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("never use openai apis directly\n", encoding="utf-8")
    b.write_text("always use openai apis for embeddings\n", encoding="utf-8")
    pairs = _extract_contradiction_subjects([a, b], jaccard_threshold=0.5)
    assert pairs
    subj, files = pairs[0]
    assert "openai" in subj.lower()
    assert len(files) >= 2
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/core/sleep_hygiene.py
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config
from .memory import find_duplicate_lines


DEFAULT_RELATIVE_TERMS = (
    "yesterday", "today", "recently", "now", "last week",
    "вчера", "сегодня", "недавно", "на прошлой неделе",
    "в прошлый раз", "в этот раз", "на днях",
)

NEG_PATTERN = re.compile(r"(?i)\b(never|don'?t|stop|avoid)\b\s+(.+)")
POS_PATTERN = re.compile(r"(?i)\b(always|prefer|use)\b\s+(.+)")


@dataclass
class ProjectHygiene:
    project_slug: str
    memory_md_size_lines: int
    memory_md_cap: int
    relative_date_density: float
    relative_date_matches: list[tuple[Path, int, str]]
    cross_file_dup_count: int
    contradicting_pairs: list[tuple[str, list[Path]]]


@dataclass
class HygieneReport:
    generated_at: datetime
    projects: list[ProjectHygiene]
    totals: dict


def _scan_relative_dates(
    paths: list[Path],
    *,
    extra_terms: tuple[str, ...],
) -> list[tuple[Path, int, str]]:
    terms = tuple(DEFAULT_RELATIVE_TERMS) + tuple(extra_terms)
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b",
        re.IGNORECASE,
    )
    out: list[tuple[Path, int, str]] = []
    for f in paths:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for m in pattern.finditer(line):
                out.append((f, i, m.group(1).lower()))
    return out


def _tokens(s: str) -> set[str]:
    return set(w.lower() for w in re.findall(r"\w+", s) if len(w) > 2)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _extract_contradiction_subjects(
    paths: list[Path],
    *,
    jaccard_threshold: float,
) -> list[tuple[str, list[Path]]]:
    neg: list[tuple[str, Path]] = []
    pos: list[tuple[str, Path]] = []
    for f in paths:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            mn = NEG_PATTERN.search(line)
            if mn:
                neg.append((mn.group(2).strip(), f))
            mp = POS_PATTERN.search(line)
            if mp:
                pos.append((mp.group(2).strip(), f))
    pairs: list[tuple[str, list[Path]]] = []
    for ns, nf in neg:
        nt = _tokens(ns)
        for ps, pf in pos:
            if _jaccard(nt, _tokens(ps)) >= jaccard_threshold:
                pairs.append((ns, [nf, pf]))
                break
    return pairs


def compute_project_hygiene(memory_dir: Path) -> ProjectHygiene:
    cfg = load_config()
    md_files = sorted(memory_dir.rglob("*.md"))
    memory_md = memory_dir / "MEMORY.md"
    total_lines = sum(
        sum(1 for _ in f.open("r", encoding="utf-8", errors="ignore"))
        for f in md_files
    ) or 1
    rel_matches = _scan_relative_dates(
        md_files, extra_terms=cfg.hygiene.relative_date_terms_extra,
    )
    dups = find_duplicate_lines(md_files, min_length=8)
    contradictions = _extract_contradiction_subjects(
        md_files,
        jaccard_threshold=cfg.hygiene.contradiction_jaccard_threshold,
    )
    memory_md_lines = (
        sum(1 for _ in memory_md.open("r", encoding="utf-8", errors="ignore"))
        if memory_md.exists() else 0
    )
    return ProjectHygiene(
        project_slug=memory_dir.parent.name,
        memory_md_size_lines=memory_md_lines,
        memory_md_cap=cfg.dream_doctor.memory_md_line_threshold,
        relative_date_density=len(rel_matches) / total_lines,
        relative_date_matches=rel_matches,
        cross_file_dup_count=len(dups),
        contradicting_pairs=contradictions,
    )


def compute_report() -> HygieneReport:
    projects_root = Path.home() / ".claude" / "projects"
    projects: list[ProjectHygiene] = []
    if projects_root.exists():
        for p in projects_root.iterdir():
            mem = p / "memory"
            if mem.is_dir():
                projects.append(compute_project_hygiene(mem))
    totals = {
        "projects": len(projects),
        "total_relative_date_matches": sum(
            len(p.relative_date_matches) for p in projects),
        "total_cross_file_dups": sum(p.cross_file_dup_count for p in projects),
        "total_contradiction_pairs": sum(
            len(p.contradicting_pairs) for p in projects),
    }
    return HygieneReport(datetime.now(timezone.utc), projects, totals)
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(core): sleep_hygiene — 4 keyword/regex/dup metrics

memory_md_size_lines, relative_date_density (en+ru regex over 12 default
terms, user-extensible via config.toml), cross_file_dup_count (reuses
Phase 1 find_duplicate_lines), contradicting_pairs (NEG/POS regex +
Jaccard token overlap, threshold from config.toml). LLM-based semantic
analysis explicitly deferred to Phase 5.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **+2 → ~213**.

---

## Task 7: `cli/commands/dream.py` — full subapp

**Files:**
- Create: `src/cc_janitor/cli/commands/dream.py`
- Modify: `src/cc_janitor/cli/__init__.py`
- Create: `tests/unit/test_cli_dream.py`

**Step 1: Failing test.**

```python
# tests/unit/test_cli_dream.py
import json
from datetime import datetime, timezone
from pathlib import Path
from typer.testing import CliRunner
from cc_janitor.cli import app
from cc_janitor.core.dream_snapshot import (
    snapshot_pre, snapshot_post, record_pair,
)

runner = CliRunner()


def _setup_pair(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    mem = tmp_path / ".claude" / "projects" / "-proj" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text("a\nb\n")
    pre = snapshot_pre("20260511T120000Z-proj", mem)
    (mem / "MEMORY.md").write_text("a\n")
    post = snapshot_post("20260511T120000Z-proj", mem)
    record_pair("20260511T120000Z-proj", mem, project_slug="proj",
                dream_pid_in_lock=4711,
                ts_pre=datetime.now(timezone.utc),
                ts_post=datetime.now(timezone.utc),
                pre_dir=pre, post_dir=post)
    return mem


def test_dream_history(tmp_path, monkeypatch):
    _setup_pair(tmp_path, monkeypatch)
    res = runner.invoke(app, ["dream", "history", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert any(d["pair_id"] == "20260511T120000Z-proj" for d in data)


def test_dream_diff(tmp_path, monkeypatch):
    _setup_pair(tmp_path, monkeypatch)
    res = runner.invoke(app, ["dream", "diff", "20260511T120000Z-proj"])
    assert res.exit_code == 0
    assert "MEMORY.md" in res.stdout


def test_dream_doctor_json(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text("{}")
    res = runner.invoke(app, ["dream", "doctor", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert isinstance(data, list)
    assert len(data) == 9


def test_dream_rollback_requires_confirm(tmp_path, monkeypatch):
    _setup_pair(tmp_path, monkeypatch)
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    res = runner.invoke(app, ["dream", "rollback", "20260511T120000Z-proj",
                              "--apply"])
    assert res.exit_code != 0


def test_dream_rollback_dry_run(tmp_path, monkeypatch):
    _setup_pair(tmp_path, monkeypatch)
    res = runner.invoke(app, ["dream", "rollback", "20260511T120000Z-proj"])
    assert res.exit_code == 0
    assert "dry" in res.stdout.lower() or "would" in res.stdout.lower()
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/cli/commands/dream.py
from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import typer

from ...core import dream_diff as dd
from ...core import dream_doctor as ddoc
from ...core.dream_snapshot import history, _dream_root
from ...core.safety import require_confirmed, soft_delete
from ...core.state import get_paths
from .._audit import audit_action

dream_app = typer.Typer(no_args_is_help=True,
                        help="Auto Dream safety net (snapshot/diff/doctor/rollback)")


@dream_app.command("history")
def history_cmd(
    project: str | None = typer.Option(None, "--project"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    items = history()
    if project:
        items = [p for p in items if p.project_slug == project]
    if json_out:
        typer.echo(json.dumps([asdict(p) for p in items], indent=2))
        return
    typer.echo(f"{'PAIR_ID':<32} {'PROJECT':<20} {'ΔFILES':<8} {'ΔLINES':<8}")
    for p in items:
        typer.echo(f"{p.pair_id:<32} {p.project_slug:<20} "
                   f"{str(p.file_count_delta or 0):<8} "
                   f"{str(p.line_count_delta or 0):<8}")


def _find_pair(pair_id: str):
    for p in history():
        if p.pair_id == pair_id:
            return p
    return None


@dream_app.command("diff")
def diff_cmd(
    pair_id: str,
    file: str | None = typer.Option(None, "--file"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    pair = _find_pair(pair_id)
    if pair is None:
        typer.echo(f"No such pair: {pair_id}")
        raise typer.Exit(code=1)
    pre = _dream_root() / f"{pair_id}-pre"
    post = _dream_root() / f"{pair_id}-post"
    if not pre.exists() or not post.exists():
        typer.echo("Snapshot mirrors missing (tar storage not yet supported in dry-run).")
        raise typer.Exit(code=1)
    diff = dd.compute_diff(pre, post)
    if file:
        diff.deltas = [d for d in diff.deltas if str(d.rel_path) == file]
    if json_out:
        typer.echo(json.dumps({
            "summary": diff.summary,
            "deltas": [{"rel_path": str(d.rel_path), "status": d.status,
                        "lines_added": d.lines_added,
                        "lines_removed": d.lines_removed,
                        "unified_diff": d.unified_diff}
                       for d in diff.deltas],
        }, indent=2))
        return
    typer.echo(f"Pair: {pair_id}  Summary: {diff.summary}")
    for d in diff.deltas:
        typer.echo(f"  [{d.status:<9}] {d.rel_path}  +{d.lines_added} -{d.lines_removed}")
    for d in diff.deltas:
        if d.unified_diff:
            typer.echo("")
            typer.echo(d.unified_diff)


@dream_app.command("doctor")
def doctor_cmd(json_out: bool = typer.Option(False, "--json")) -> None:
    checks = ddoc.run_checks()
    if json_out:
        typer.echo(json.dumps([asdict(c) for c in checks], indent=2))
        return
    typer.echo("cc-janitor dream doctor")
    typer.echo("─" * 60)
    for c in checks:
        typer.echo(f"  [{c.severity:<4}] {c.title}: {c.message}")


@dream_app.command("rollback")
def rollback_cmd(
    pair_id: str,
    apply: bool = typer.Option(False, "--apply",
                               help="Actually restore (otherwise dry-run)"),
) -> None:
    pair = _find_pair(pair_id)
    if pair is None:
        typer.echo(f"No such pair: {pair_id}")
        raise typer.Exit(code=1)
    pre = _dream_root() / f"{pair_id}-pre"
    target = Path(pair.claude_memory_dir)
    if not apply:
        typer.echo(f"[dry-run] Would restore {pre} → {target}")
        typer.echo(f"          Current target post-state would be soft-deleted to trash.")
        return
    require_confirmed()
    with audit_action(cmd="dream rollback",
                      args=[pair_id, "--apply"]) as changed:
        # Soft-delete the current state first.
        trash = get_paths().home / ".trash" / \
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") / \
            f"dream-rollback-{pair_id}"
        trash.mkdir(parents=True, exist_ok=True)
        for f in target.rglob("*"):
            if f.is_file():
                rel = f.relative_to(target)
                out = trash / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(f), str(out))
        # Copy the pre-mirror back.
        for f in pre.rglob("*"):
            if f.is_file():
                rel = f.relative_to(pre)
                out = target / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, out)
        changed["pair_id"] = pair_id
        changed["files_restored"] = sum(1 for _ in pre.rglob("*") if _.is_file())
        changed["trash_path"] = str(trash)
    typer.echo(f"Restored {pair_id}; previous state preserved in {trash}.")


@dream_app.command("prune")
def prune_cmd(
    older_than_days: int = typer.Option(30, "--older-than-days"),
    apply: bool = typer.Option(False, "--apply"),
) -> None:
    root = _dream_root()
    if not root.exists():
        typer.echo("Nothing to prune.")
        return
    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - older_than_days * 86400
    victims = [d for d in root.iterdir()
               if d.stat().st_mtime < cutoff]
    if not apply:
        typer.echo(f"[dry-run] Would remove {len(victims)} dream artifact(s) "
                   f"older than {older_than_days} days.")
        return
    require_confirmed()
    with audit_action(cmd="dream prune",
                      args=[f"--older-than-days={older_than_days}"]) as ch:
        for v in victims:
            if v.is_dir():
                shutil.rmtree(v)
            else:
                v.unlink()
        ch["removed"] = [str(v) for v in victims]
    typer.echo(f"Removed {len(victims)} artifact(s).")
```

Register in `cli/__init__.py`:

```python
from .commands.dream import dream_app
# ...
app.add_typer(dream_app, name="dream")
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(cli): cc-janitor dream history/diff/doctor/rollback/prune

Read-only: history (list pairs), diff (file-level + unified diff),
doctor (9 checks). Mutating: rollback (soft-deletes current state to
trash, copies pre-mirror back; --apply gated by require_confirmed +
audit_action), prune (removes artifacts older than N days).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **+5 → ~218**.

---

## Task 8: `cli/commands/stats.py` — `stats sleep-hygiene`

**Files:**
- Modify: `src/cc_janitor/cli/commands/stats.py`
- Create: `tests/unit/test_cli_stats_hygiene.py`

**Step 1: Failing test.**

```python
# tests/unit/test_cli_stats_hygiene.py
import json
from pathlib import Path
from typer.testing import CliRunner
from cc_janitor.cli import app

runner = CliRunner()


def test_stats_sleep_hygiene_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    res = runner.invoke(app, ["stats", "sleep-hygiene", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert "projects" in data
    assert data["totals"]["projects"] == 0


def test_stats_sleep_hygiene_with_data(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    mem = tmp_path / ".claude" / "projects" / "-proj" / "memory"
    mem.mkdir(parents=True)
    (mem / "MEMORY.md").write_text(
        "yesterday we did x\nrecently changed y\n", encoding="utf-8")
    res = runner.invoke(app, ["stats", "sleep-hygiene", "--json"])
    data = json.loads(res.stdout)
    assert data["totals"]["total_relative_date_matches"] >= 2
```

**Step 2: Run, FAIL.**

**Step 3: Implement.** Append to `cli/commands/stats.py`:

```python
from ...core.sleep_hygiene import compute_report


@stats_app.command("sleep-hygiene")
def sleep_hygiene(
    project: str | None = typer.Option(None, "--project"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    report = compute_report()
    projects = report.projects
    if project:
        projects = [p for p in projects if p.project_slug == project]
    if json_out:
        import json as _json
        typer.echo(_json.dumps({
            "generated_at": report.generated_at.isoformat(),
            "totals": report.totals,
            "projects": [{
                "project_slug": p.project_slug,
                "memory_md_size_lines": p.memory_md_size_lines,
                "memory_md_cap": p.memory_md_cap,
                "relative_date_density": p.relative_date_density,
                "relative_date_match_count": len(p.relative_date_matches),
                "cross_file_dup_count": p.cross_file_dup_count,
                "contradicting_pair_count": len(p.contradicting_pairs),
            } for p in projects],
        }, indent=2))
        return
    typer.echo("Sleep hygiene report")
    typer.echo("─" * 70)
    for p in projects:
        typer.echo(
            f"  {p.project_slug:<25} "
            f"MEMORY.md {p.memory_md_size_lines}/{p.memory_md_cap}  "
            f"rel-date density {p.relative_date_density:.3f}  "
            f"dups {p.cross_file_dup_count}  "
            f"contradictions {len(p.contradicting_pairs)}"
        )
    typer.echo(f"Totals: {report.totals}")
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(cli): cc-janitor stats sleep-hygiene

Surfaces the 4 keyword/regex/dup metrics from core.sleep_hygiene as a
per-project summary table or JSON document. Read-only; safe to invoke
from inside a Claude Code session.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **+2 → ~220**.

---

## Task 9: TUI 8th tab — `DreamScreen`

**Files:**
- Create: `src/cc_janitor/tui/screens/dream_screen.py`
- Modify: `src/cc_janitor/tui/app.py`
- Create: `tests/tui/test_dream_screen.py`

**Step 1: Failing snapshot test.**

```python
# tests/tui/test_dream_screen.py
from cc_janitor.tui.app import CcJanitorApp


def test_dream_tab_renders(snap_compare):
    assert snap_compare(CcJanitorApp(), terminal_size=(120, 40),
                        press=["right", "right", "right", "right",
                               "right", "right", "right"])  # navigate to 8th tab
```

(Snapshot will be generated on first run via `--snapshot-update`.)

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/tui/screens/dream_screen.py
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import DataTable, Static

from ...core.dream_diff import compute_diff
from ...core.dream_snapshot import history, _dream_root


class DreamScreen(Widget):
    DEFAULT_CSS = """
    DreamScreen { layout: horizontal; height: 100%; }
    DreamScreen DataTable { width: 60; }
    DreamScreen Static { width: 1fr; padding: 0 1; }
    """

    def compose(self) -> ComposeResult:
        yield DataTable(id="dream-list")
        yield Static(id="dream-diff", expand=True)

    def on_mount(self) -> None:
        table: DataTable = self.query_one("#dream-list", DataTable)
        table.add_columns("Date", "Project", "ΔFiles", "ΔLines")
        for pair in reversed(history()):
            table.add_row(
                pair.ts_pre[:19],
                pair.project_slug,
                str(pair.file_count_delta or 0),
                str(pair.line_count_delta or 0),
                key=pair.pair_id,
            )
        self._show_diff_for(None)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._show_diff_for(event.row_key.value if event.row_key else None)

    def _show_diff_for(self, pair_id: str | None) -> None:
        diff_widget: Static = self.query_one("#dream-diff", Static)
        if not pair_id:
            diff_widget.update("Select a snapshot pair on the left.")
            return
        pre = _dream_root() / f"{pair_id}-pre"
        post = _dream_root() / f"{pair_id}-post"
        if not pre.exists() or not post.exists():
            diff_widget.update(f"Mirrors missing for {pair_id} "
                               "(may be in tar storage).")
            return
        diff = compute_diff(pre, post)
        body = [f"Pair {pair_id}  {diff.summary}\n"]
        for d in diff.deltas:
            body.append(f"  [{d.status}] {d.rel_path} "
                        f"+{d.lines_added} -{d.lines_removed}")
        for d in diff.deltas:
            if d.unified_diff:
                body.append("")
                body.append(d.unified_diff)
        diff_widget.update("\n".join(body))
```

Update `tui/app.py` `compose()`:

```python
with TabPane("Dream", id="dream"):
    from .screens.dream_screen import DreamScreen
    yield DreamScreen()
```

**Step 4: Run, PASS (snapshot update). Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(tui): 8th Dream tab — snapshot list + diff viewer

DreamScreen lays out a DataTable (snapshot history) beside a Static
diff viewer. Row highlight triggers compute_diff() for the selected
pair_id and renders summary + per-file deltas + unified diff body.
Read-only; future TUI-driven rollback will route through ConfirmModal
from tui/_confirm.py (Phase 4 task 11 stretch / Phase 5).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **+1 → ~221**.

---

## Task 10: Tar-compaction scheduled-job template

**Files:**
- Modify: `src/cc_janitor/core/schedule.py` (TEMPLATES dict)
- Create: `src/cc_janitor/cli/commands/backups.py` — add `tar-compact` subcommand (or extend existing)
- Create: `tests/unit/test_tar_compact.py`

**Step 1: Failing test.**

```python
# tests/unit/test_tar_compact.py
import tarfile
from pathlib import Path
from typer.testing import CliRunner
from cc_janitor.cli import app

runner = CliRunner()


def test_tar_compact_archives_old_pairs(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    dream = tmp_path / "jhome" / "backups" / "dream"
    (dream / "20260401T000000Z-old-pre").mkdir(parents=True)
    (dream / "20260401T000000Z-old-pre" / "MEMORY.md").write_text("a\n")
    (dream / "20260401T000000Z-old-post").mkdir()
    (dream / "20260401T000000Z-old-post" / "MEMORY.md").write_text("b\n")
    import os, time
    old = time.time() - 30 * 86400
    for d in dream.rglob("*"):
        os.utime(d, (old, old))
    res = runner.invoke(app, ["backups", "tar-compact",
                              "--kind", "dream",
                              "--older-than-days", "7",
                              "--apply"])
    assert res.exit_code == 0
    tars = list(dream.glob("*.tar.gz"))
    assert len(tars) == 1
    with tarfile.open(tars[0]) as tf:
        names = tf.getnames()
        assert any("pre/MEMORY.md" in n for n in names)
        assert any("post/MEMORY.md" in n for n in names)
```

**Step 2: Run, FAIL.**

**Step 3: Implement.** Append a `tar_compact()` Typer command to
`cli/commands/backups.py`:

```python
@backups_app.command("tar-compact")
def tar_compact(
    kind: str = typer.Option("dream", "--kind"),
    older_than_days: int = typer.Option(7, "--older-than-days"),
    apply: bool = typer.Option(False, "--apply"),
) -> None:
    import tarfile, shutil
    from datetime import datetime, timezone
    from ...core.state import get_paths
    from ...core.safety import require_confirmed
    from .._audit import audit_action

    root = get_paths().home / "backups" / kind
    if not root.exists():
        typer.echo("Nothing to compact.")
        return
    cutoff = datetime.now(timezone.utc).timestamp() - older_than_days * 86400
    # Group by pair_id stem (strip -pre / -post suffix).
    pair_dirs: dict[str, list[Path]] = {}
    for d in root.iterdir():
        if not d.is_dir():
            continue
        name = d.name
        if name.endswith("-pre"):
            pair_dirs.setdefault(name[:-4], []).append(d)
        elif name.endswith("-post"):
            pair_dirs.setdefault(name[:-5], []).append(d)
    old_pairs = {pid: dirs for pid, dirs in pair_dirs.items()
                 if all(d.stat().st_mtime < cutoff for d in dirs)}
    if not apply:
        typer.echo(f"[dry-run] Would tar-compact {len(old_pairs)} pair(s).")
        return
    require_confirmed()
    with audit_action(cmd="backups tar-compact",
                      args=[f"--kind={kind}",
                            f"--older-than-days={older_than_days}"]) as ch:
        archived = []
        for pid, dirs in old_pairs.items():
            archive_path = root / f"{pid}.tar.gz"
            with tarfile.open(archive_path, "w:gz") as tf:
                for d in dirs:
                    arc = "pre" if d.name.endswith("-pre") else "post"
                    for f in d.rglob("*"):
                        if f.is_file():
                            tf.add(f, arcname=f"{arc}/{f.relative_to(d)}")
            for d in dirs:
                shutil.rmtree(d)
            archived.append(pid)
        ch["archived"] = archived
    typer.echo(f"Compacted {len(old_pairs)} pair(s).")
```

Also add a template entry in `core/schedule.py` TEMPLATES dict for
`dream-tar-compact`:

```python
"dream-tar-compact": {
    "description": "Compact dream snapshot mirrors older than 7 days into tar.gz",
    "command": "cc-janitor backups tar-compact --kind dream "
               "--older-than-days 7 --apply",
    "default_cron": "0 5 * * 0",  # Sunday 05:00
},
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(scheduler): dream-tar-compact template + backups tar-compact CLI

cc-janitor backups tar-compact --kind dream --older-than-days 7 --apply
groups <pair_id>-pre / <pair_id>-post dirs into <pair_id>.tar.gz and
removes raw mirrors. New scheduler template `dream-tar-compact` runs
this weekly. Audit-logged via audit_action; --apply gated.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **+1 → ~222**.

---

## Task 11: Settings-audit hook

**Files:**
- Create: `src/cc_janitor/core/settings_observer.py`
- Modify: `src/cc_janitor/core/dream_doctor.py` (call observer at start of `run_checks`)
- Create: `tests/unit/test_settings_observer.py`

**Step 1: Failing test.**

```python
# tests/unit/test_settings_observer.py
from pathlib import Path
from cc_janitor.core.settings_observer import observe_autodream_change


def test_first_observation_no_change(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        '{"autoDreamEnabled": false}')
    delta = observe_autodream_change()
    assert delta is None  # first run, nothing to compare


def test_change_detected(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "jhome"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=False)
    (tmp_path / ".claude").mkdir()
    s = tmp_path / ".claude" / "settings.json"
    s.write_text('{"autoDreamEnabled": false}')
    observe_autodream_change()
    s.write_text('{"autoDreamEnabled": true}')
    delta = observe_autodream_change()
    assert delta == (False, True)
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/core/settings_observer.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .audit import AuditLog
from .state import get_paths


def _cache_path() -> Path:
    return get_paths().home / "settings-audit.json"


def _claude_settings() -> Path:
    return Path.home() / ".claude" / "settings.json"


def observe_autodream_change() -> tuple[bool, bool] | None:
    """Returns (old, new) tuple if autoDreamEnabled changed since last observation,
    else None.
    """
    s = _claude_settings()
    if not s.exists():
        return None
    try:
        current = bool(json.loads(s.read_text(encoding="utf-8"))
                       .get("autoDreamEnabled", False))
    except (OSError, json.JSONDecodeError):
        return None
    cache = _cache_path()
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"autoDreamEnabled": current}),
                         encoding="utf-8")
        return None
    try:
        prev = bool(json.loads(cache.read_text(encoding="utf-8"))
                    .get("autoDreamEnabled", False))
    except (OSError, json.JSONDecodeError):
        prev = current
    if prev == current:
        return None
    cache.write_text(json.dumps({"autoDreamEnabled": current}),
                     encoding="utf-8")
    log = AuditLog(get_paths().audit_log)
    log.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "cmd": "settings-observe",
        "mode": "observer",
        "changed": {"key": "autoDreamEnabled",
                    "old": prev, "new": current,
                    "source": str(s)},
    })
    return (prev, current)
```

In `core/dream_doctor.py` `run_checks()`, call `observe_autodream_change()`
at the top and append a DoctorCheck INFO row if a change is detected.

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "$(cat <<'EOF'
feat(core): settings_observer — detect autoDreamEnabled changes

Caches last-seen autoDreamEnabled value at ~/.cc-janitor/settings-audit.json.
On every dream doctor invocation, compares with current ~/.claude/settings.json
and appends an audit-log entry on flip. Surfaces as a DoctorCheck INFO row
("Auto Dream was enabled on <date>; do you have backups configured?").

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **+2 → ~224**.

---

## Task 12: i18n + cookbook + CHANGELOG + version bump

**Files:**
- Modify: `src/cc_janitor/i18n/en.toml` + `ru.toml`
- Modify: `docs/cookbook.md`
- Modify: `docs/CC_USAGE.md`
- Modify: `docs/architecture.md`
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`
- Modify: `src/cc_janitor/cli/__init__.py`
- Modify: `README.md` + `README.ru.md`

**i18n keys.** Add a `[dream]` table to both en.toml and ru.toml:

```toml
[dream]
title = "Dream"
list_header = "Date    Project    ΔFiles    ΔLines"
no_pairs = "No snapshot pairs yet. Run `cc-janitor watch start --dream`."
diff_select = "Select a snapshot pair on the left."
doctor_running = "Running 9 dream-doctor checks..."
```

(Russian equivalents in `ru.toml`.)

**Cookbook recipes** — add three:

1. **"Auto Dream just rewrote my memory — how do I see what changed?"** →
   `cc-janitor dream history` → pick pair_id →
   `cc-janitor dream diff <pair_id>` → if regret →
   `cc-janitor dream rollback <pair_id> --apply` (with confirm var).
2. **"Auto Dream is silently disabled — diagnose it"** →
   `cc-janitor dream doctor` → look for FAIL on `stale_lock` → if present,
   manually delete the stale lock file (or `cc-janitor` will add a `dream
   fix-stale-lock` in Phase 5).
3. **"Set up scheduled snapshot-around-Dream so I never lose memory again"**
   → `CC_JANITOR_USER_CONFIRMED=1 cc-janitor watch start --dream` → confirm
   with `cc-janitor watch status` → `cc-janitor schedule add
   dream-tar-compact` for retention.

**CC_USAGE.md** — append:

```
## Phase 4 — Auto Dream safety net (read-only commands safe for Claude)
- cc-janitor dream history [--project P] [--json]
- cc-janitor dream diff <pair_id> [--file F] [--json]
- cc-janitor dream doctor [--json]
- cc-janitor stats sleep-hygiene [--project P] [--json]
- cc-janitor watch status [--json]

Mutating (require CC_JANITOR_USER_CONFIRMED=1, user must explicitly OK):
- cc-janitor dream rollback <pair_id> --apply
- cc-janitor dream prune --older-than-days N --apply
- cc-janitor watch start --dream
```

**CHANGELOG.md** — prepend:

```markdown
## [0.4.0] — 2026-05-XX

### Added

- **Dream safety net (Phase 4).** Deterministic backup-and-diff harness
  around Anthropic's Auto Dream. New top-level `cc-janitor dream`
  subapp: `history`, `diff <pair_id>`, `doctor` (9 checks), `rollback
  <pair_id> --apply`, `prune`.
- **Watcher `--dream` mode.** `cc-janitor watch start --dream` polls
  every `~/.claude/projects/*/memory/.consolidate-lock` file; on
  lock-appears writes a raw mirror snapshot to
  `~/.cc-janitor/backups/dream/<pair_id>-pre/`, on lock-gone writes
  `<pair_id>-post/` and records the pair to
  `~/.cc-janitor/dream-snapshots.jsonl`.
- **`cc-janitor stats sleep-hygiene`.** Four keyword/regex/dup metrics
  (MEMORY.md size, relative-date density, cross-file dup count,
  contradicting-feedback pairs) — surfaces lines that will go stale on
  next Dream.
- **`cc-janitor backups tar-compact --kind dream`** + new scheduler
  template `dream-tar-compact`. Raw mirrors compacted to tar.gz after 7
  days, tarballs purged after 30 days (thresholds configurable).
- **`~/.cc-janitor/config.toml`** (optional). User-tunable thresholds
  for dream doctor, snapshot retention, hygiene regex extras.
- **8th TUI tab: `Dream`.** Snapshot list + diff viewer panes.
- **Settings audit hook.** Detects flips of `autoDreamEnabled` in
  `~/.claude/settings.json` and writes audit-log entries.

### Fixed

- Closes verified user pain in upstream Issues #47959 (silent memory
  deletion), #50694 (stale `.consolidate-lock`), #38493 (missing
  `.dream-log.md`).
```

**Version bump:**

```toml
# pyproject.toml
version = "0.4.0"
```

```python
# cli/__init__.py
__VERSION__ = "0.4.0"
```

**README hero update** (both English and Russian): add one line under the
existing feature list:

> **Dream safety net** — snapshot before Auto Dream, diff after, rollback
> if needed. Closes Issues #47959, #50694, #38493.

**Commit.**

```bash
git commit -am "$(cat <<'EOF'
docs: i18n + cookbook + CHANGELOG + bump to 0.4.0

Three new cookbook recipes, CC_USAGE.md updated with five new
read-only commands + three mutating ones, README hero gains a Dream
safety net bullet point, CHANGELOG [0.4.0] block. Version bumped.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected pytest count: **unchanged (~224 passing)**.

---

## Task 13: PR + tag + release + PyPI verify

**Step 1: Push branch + create PR.**

```bash
git push -u origin feat/phase4-dream
gh pr create --title "Phase 4 — Auto Dream safety net (v0.4.0)" \
  --body "$(cat <<'EOF'
## Summary

Phase 4 = "Sleep safety net" around Anthropic's Auto Dream. Six
features, 13 TDD tasks, ~+24 passing tests.

- `cc-janitor watch start --dream` — opt-in lock-file polling +
  pre/post snapshots
- `cc-janitor dream history|diff|doctor|rollback|prune`
- `cc-janitor stats sleep-hygiene` — 4 keyword/regex metrics
- 8th TUI tab with diff viewer
- Optional `~/.cc-janitor/config.toml`
- Settings audit hook on `autoDreamEnabled` flips
- `dream-tar-compact` scheduler template, 7d raw / 30d tar retention

Closes verified user pain in upstream Issues #47959, #50694, #38493.

## Test plan

- [ ] `uv run pytest -q` — full suite ≈ 224 passing
- [ ] Manual: `cc-janitor watch start --dream`, write a fake
      `.consolidate-lock`, remove it, confirm pair appears in
      `cc-janitor dream history`.
- [ ] Manual: `cc-janitor dream doctor` — verify all 9 checks render.
- [ ] Manual: `cc-janitor dream rollback <pair_id>` dry-run, then
      `--apply` with `CC_JANITOR_USER_CONFIRMED=1`.
- [ ] Manual: TUI `Dream` tab navigates and renders diff.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 2: Merge after CI green.** Squash-merge by maintainer.

**Step 3: Tag + GitHub release.**

```bash
git switch main
git pull
git tag -a v0.4.0 -m "v0.4.0 — Auto Dream safety net"
git push origin v0.4.0
```

The existing `.github/workflows/release.yml` (Phase 1) will publish to PyPI
on tag.

**Step 4: Verify PyPI install.**

```bash
pipx install --force cc-janitor==0.4.0
cc-janitor --version              # → 0.4.0
cc-janitor dream doctor           # exercises the new subapp
```

---

## Summary

| Task | New files | Test delta | Cumulative |
|------|-----------|------------|------------|
| 0 | — | 0 | ~200 |
| 1 | core/config.py | +4 | ~204 |
| 2 | core/dream_snapshot.py | +3 | ~207 |
| 3 | (watcher.py extension) | +1 | ~208 |
| 4 | core/dream_diff.py | +1 | ~209 |
| 5 | core/dream_doctor.py | +2 | ~211 |
| 6 | core/sleep_hygiene.py | +2 | ~213 |
| 7 | cli/commands/dream.py | +5 | ~218 |
| 8 | (stats.py extension) | +2 | ~220 |
| 9 | tui/screens/dream_screen.py | +1 | ~221 |
| 10 | (backups + scheduler templates) | +1 | ~222 |
| 11 | core/settings_observer.py | +2 | ~224 |
| 12 | docs + i18n + version | 0 | ~224 |
| 13 | PR + tag + release | n/a | n/a |

Net: 5 new core modules, 1 new CLI subapp, 1 new TUI screen, 1 new scheduler
template, 1 new optional config file, ~24 new tests, zero new mandatory
dependencies, zero Phase 1/2/3 regressions.

**Target ship velocity: ~1 week.** First-mover advantage on the safety
harness niche is real and time-bounded.
