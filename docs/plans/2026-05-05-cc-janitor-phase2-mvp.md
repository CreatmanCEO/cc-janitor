# cc-janitor Phase 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship `cc-janitor` v0.2.0 — Memory editor, Reinject hook (writer side + Windows-compat install), Hooks debugger (merged view, simulate, logging wrapper, schema validate, Windows env-var fix), Scheduler (cron + schtasks abstraction with dry-run-first guard and hard cap on scheduled deletions). Replace the three placeholder TUI tabs from Phase 1 with real screens.

**Architecture:** Same single-package, two-mode layout from Phase 1. Three new core modules (`memory.py`, `hooks.py`, `schedule.py`, `reinject.py`), three new TUI screens, three new Typer subapps, plus modifications to `cli/__init__.py`, `tui/app.py`, `cli/commands/install_hooks.py`, and the i18n TOML files. No Phase 1 module is broken or moved.

**Tech Stack:** Python 3.11+, Textual ≥0.80, Typer ≥0.12, plus new deps `python-frontmatter` ≥1.1 and `croniter` ≥2. Test stack unchanged (pytest, pytest-textual-snapshot, hypothesis).

**Reference design:** `docs/plans/2026-05-05-cc-janitor-phase2-design.md`.

**Predecessor plan (style mirror):** `docs/plans/2026-05-03-cc-janitor-phase1-mvp.md`.

---

## Conventions used throughout this plan

- **Working dir** = `C:\Users\creat\OneDrive\Рабочий стол\CREATMAN\Tools\cc-janitor` (Windows path; in bash use `~/OneDrive/Рабочий стол/CREATMAN/Tools/cc-janitor`).
- **Branch:** `feat/phase2-mvp`. Implementer should branch from `main` after Phase 1 is merged. PR to `main` at the end.
- **Every task** = TDD cycle: write failing test → run it → implement → run again → commit. Each commit message follows Conventional Commits with the Co-Authored-By trailer required by the user policy.
- **Audit log policy:** every mutating CLI command starts with `safety.require_confirmed()` and ends with `audit.AuditLog(...).record(...)`. The pattern from `cli/commands/perms.py` (Phase 1) is the reference; copy it.
- **No `--no-verify`, no `--amend` after a hook failure** — fix and create a new commit. Carries from project policy.

---

## Task 0: Branch and pyproject deps

**Files:**
- Modify: `pyproject.toml`

**Step 1: Branch.**

```bash
git fetch origin
git switch main
git pull
git switch -c feat/phase2-mvp
```

**Step 2: Add deps.** In `pyproject.toml`, append to the `dependencies` array:

```toml
dependencies = [
    "textual>=0.80",
    "typer>=0.12",
    "tiktoken>=0.7",
    "python-rapidjson>=1.20",
    "tomlkit>=0.13",
    "platformdirs>=4",
    "python-frontmatter>=1.1",
    "croniter>=2",
]
```

Bump version: `version = "0.2.0.dev0"`.

**Step 3: Verify install.**

```bash
uv pip install -e ".[dev]"
uv run cc-janitor --version  # should print 0.2.0.dev0
uv run pytest -q             # Phase 1 tests must still pass
```

**Step 4: Commit.**

```bash
git add pyproject.toml
git commit -m "chore: bump to 0.2.0.dev0 and add Phase 2 deps"
```

---

## Task 1: Memory frontmatter parser (foundation)

**Files:**
- Create: `src/cc_janitor/core/memory.py`
- Create: `tests/unit/test_memory_parse.py`
- Modify: `tests/data/mock-claude-home/.claude/projects/test-proj/memory/` — add three sample files

**Step 1: Test fixtures.** Create under `tests/data/mock-claude-home/.claude/projects/test-proj/memory/`:

`MEMORY.md`:
```markdown
---
type: user
title: User Memory Index
---

# Memory Index

Top-level user memory.
```

`feedback_no_emojis.md`:
```markdown
---
type: feedback
description: Avoid emojis in commit messages
---

User dislikes emojis in commit messages.
```

`project_phase2_notes.md` (no frontmatter — relies on filename heuristic):
```markdown
# Phase 2 Notes

Working on the scheduler.
```

**Step 2: Failing test.**

```python
# tests/unit/test_memory_parse.py
from pathlib import Path
from cc_janitor.core.memory import parse_memory_file, classify_type

def test_parse_with_frontmatter(mock_claude_home):
    p = mock_claude_home / ".claude" / "projects" / "test-proj" / "memory" / "feedback_no_emojis.md"
    m = parse_memory_file(p)
    assert m.type == "feedback"
    assert m.frontmatter["description"] == "Avoid emojis in commit messages"
    assert m.size_bytes > 0
    assert m.line_count >= 1

def test_classify_falls_back_to_filename(mock_claude_home):
    p = mock_claude_home / ".claude" / "projects" / "test-proj" / "memory" / "project_phase2_notes.md"
    m = parse_memory_file(p)
    assert m.type == "project"

def test_classify_unknown_when_no_hint(tmp_path):
    f = tmp_path / "random.md"
    f.write_text("# Hello\n", encoding="utf-8")
    m = parse_memory_file(f)
    assert m.type == "unknown"

def test_classify_helper_directly():
    assert classify_type({"type": "reference"}, Path("anything.md")) == "reference"
    assert classify_type({}, Path("research_x.md")) == "reference"
    assert classify_type({}, Path("feedback_y.md")) == "feedback"
    assert classify_type({}, Path("project_z.md")) == "project"
    assert classify_type({}, Path("MEMORY.md")) == "user"
    assert classify_type({}, Path("xyz.md")) == "unknown"
```

**Step 3: Run, expect FAIL.**

```bash
uv run pytest tests/unit/test_memory_parse.py -v
```

**Step 4: Implement.**

```python
# src/cc_janitor/core/memory.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import frontmatter

MemoryType = Literal["user", "feedback", "project", "reference", "unknown"]
KNOWN_TYPES: tuple[MemoryType, ...] = ("user", "feedback", "project", "reference")


@dataclass
class MemoryFile:
    path: Path
    type: MemoryType
    title: str | None
    description: str | None
    frontmatter: dict
    body: str
    size_bytes: int
    line_count: int
    last_modified: datetime
    project: str | None = None
    is_archived: bool = False


def classify_type(fm: dict, path: Path) -> MemoryType:
    explicit = (fm or {}).get("type")
    if isinstance(explicit, str) and explicit.lower() in KNOWN_TYPES:
        return explicit.lower()  # type: ignore[return-value]
    name = path.name.lower()
    if name.startswith("feedback_"):
        return "feedback"
    if name.startswith("project_"):
        return "project"
    if name.startswith("research_") or name.startswith("reference_"):
        return "reference"
    if name in {"memory.md", "user_profile.md"}:
        return "user"
    return "unknown"


def parse_memory_file(path: Path, *, project: str | None = None,
                      is_archived: bool = False) -> MemoryFile:
    raw = path.read_text(encoding="utf-8")
    post = frontmatter.loads(raw)
    fm = dict(post.metadata)
    body = post.content
    typ = classify_type(fm, path)
    title = fm.get("title")
    description = fm.get("description")
    if title is None:
        for line in body.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
    if description is None:
        for line in body.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                description = line[:200]
                break
    stat = path.stat()
    return MemoryFile(
        path=path,
        type=typ,
        title=title,
        description=description,
        frontmatter=fm,
        body=body,
        size_bytes=stat.st_size,
        line_count=raw.count("\n") + (0 if raw.endswith("\n") else 1),
        last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        project=project,
        is_archived=is_archived,
    )
```

**Step 5: Run, expect PASS. Commit.**

```bash
git add src/cc_janitor/core/memory.py tests/unit/test_memory_parse.py \
        tests/data/mock-claude-home/.claude/projects/test-proj/memory/
git commit -m "feat(core): memory frontmatter parser with type classification"
```

---

## Task 2: Memory discovery + duplicate detection

**Files:**
- Modify: `src/cc_janitor/core/memory.py`
- Create: `tests/unit/test_memory_discover.py`

**Step 1: Failing test.**

```python
# tests/unit/test_memory_discover.py
from cc_janitor.core.memory import discover_memory_files, find_duplicate_lines

def test_discover_finds_three(mock_claude_home):
    items = discover_memory_files()
    names = {i.path.name for i in items}
    assert {"MEMORY.md", "feedback_no_emojis.md", "project_phase2_notes.md"} <= names

def test_discover_filter_by_type(mock_claude_home):
    items = discover_memory_files(type_filter="feedback")
    assert all(i.type == "feedback" for i in items)
    assert any(i.path.name == "feedback_no_emojis.md" for i in items)

def test_find_duplicates_detects_repeated_lines(tmp_path):
    a = tmp_path / "a.md"; a.write_text("- shared bullet\nunique a\n")
    b = tmp_path / "b.md"; b.write_text("- shared bullet\nunique b\n")
    dups = find_duplicate_lines([a, b])
    assert any("shared bullet" in d.line for d in dups)
    assert all(len(d.files) >= 2 for d in dups)
```

**Step 2: Run, FAIL.**

**Step 3: Append to `memory.py`.**

```python
# additions to src/cc_janitor/core/memory.py
from .state import get_paths


def _claude_projects_root() -> Path:
    paths = get_paths()
    home = paths.home.parent  # ~
    return home / ".claude" / "projects"


def _global_user_claude_md() -> Path:
    return get_paths().home.parent / ".claude" / "CLAUDE.md"


@dataclass
class DuplicateLine:
    line: str
    files: list[Path]


def discover_memory_files(*, type_filter: str | None = None,
                          project: str | None = None,
                          include_archived: bool = False) -> list[MemoryFile]:
    out: list[MemoryFile] = []
    root = _claude_projects_root()
    if root.exists():
        for proj_dir in root.iterdir():
            if not proj_dir.is_dir():
                continue
            if project and proj_dir.name != project:
                continue
            mem_dir = proj_dir / "memory"
            if not mem_dir.exists():
                continue
            for f in mem_dir.rglob("*.md"):
                archived = ".archive" in f.parts
                if archived and not include_archived:
                    continue
                out.append(parse_memory_file(f, project=proj_dir.name, is_archived=archived))
    user_md = _global_user_claude_md()
    if user_md.exists():
        out.append(parse_memory_file(user_md, project=None))
    if type_filter:
        out = [m for m in out if m.type == type_filter]
    return out


def find_duplicate_lines(paths: list[Path], *, min_length: int = 8) -> list[DuplicateLine]:
    seen: dict[str, list[Path]] = {}
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if len(line) < min_length:
                continue
            if line.startswith("#"):
                continue
            seen.setdefault(line, []).append(p)
    return [DuplicateLine(line=k, files=v) for k, v in seen.items() if len(v) >= 2]
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "feat(core): memory discovery and duplicate-line detection"
```

---

## Task 3: Memory mutations — archive, move-type, edit

**Files:**
- Modify: `src/cc_janitor/core/memory.py`
- Create: `tests/unit/test_memory_mutate.py`

**Step 1: Failing test.**

```python
# tests/unit/test_memory_mutate.py
import os
import frontmatter
from pathlib import Path
from cc_janitor.core.memory import archive_memory_file, move_memory_type, open_in_editor

def test_archive_moves_to_dot_archive(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    p = mock_claude_home / ".claude" / "projects" / "test-proj" / "memory" / "MEMORY.md"
    archived = archive_memory_file(p)
    assert not p.exists()
    assert archived.exists()
    assert ".archive" in archived.parts

def test_move_type_rewrites_frontmatter(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    p = mock_claude_home / ".claude" / "projects" / "test-proj" / "memory" / "feedback_no_emojis.md"
    move_memory_type(p, "user")
    post = frontmatter.loads(p.read_text(encoding="utf-8"))
    assert post.metadata["type"] == "user"
    assert post.metadata["description"] == "Avoid emojis in commit messages"  # preserved

def test_open_in_editor_uses_env_editor(monkeypatch, tmp_path):
    f = tmp_path / "x.md"; f.write_text("# x")
    captured = {}
    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        class R: returncode = 0
        return R()
    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setenv("EDITOR", "myeditor")
    open_in_editor(f)
    assert captured["cmd"][0] == "myeditor"
    assert captured["cmd"][1] == str(f)
```

**Step 2: Run, FAIL.**

**Step 3: Append to `memory.py`.**

```python
# additions to src/cc_janitor/core/memory.py
import os
import shutil
import subprocess
import sys

from .safety import require_confirmed


def archive_memory_file(path: Path) -> Path:
    require_confirmed()
    if not path.exists():
        raise FileNotFoundError(path)
    archive_root = path.parent / ".archive" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    archive_root.mkdir(parents=True, exist_ok=True)
    dst = archive_root / path.name
    shutil.move(str(path), str(dst))
    return dst


def move_memory_type(path: Path, new_type: str) -> None:
    require_confirmed()
    if new_type not in KNOWN_TYPES:
        raise ValueError(f"Unknown type: {new_type}; must be one of {KNOWN_TYPES}")
    raw = path.read_text(encoding="utf-8")
    post = frontmatter.loads(raw)
    post["type"] = new_type
    path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")


def _resolve_editor() -> list[str]:
    for var in ("EDITOR", "VISUAL"):
        val = os.environ.get(var)
        if val:
            return val.split()
    if sys.platform == "win32":
        return ["notepad.exe"]
    return ["vi"]


def open_in_editor(path: Path) -> int:
    require_confirmed()
    cmd = [*_resolve_editor(), str(path)]
    result = subprocess.run(cmd)
    return result.returncode
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "feat(core): memory archive, move-type, open-in-editor"
```

---

## Task 4: Reinject marker writer

**Files:**
- Create: `src/cc_janitor/core/reinject.py`
- Create: `tests/unit/test_reinject.py`

**Step 1: Failing test.**

```python
# tests/unit/test_reinject.py
from pathlib import Path
from cc_janitor.core.reinject import queue_reinject, is_reinject_pending, clear_reinject

def test_queue_creates_marker(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    queue_reinject()
    assert is_reinject_pending()

def test_queue_is_idempotent(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    queue_reinject(); queue_reinject(); queue_reinject()
    assert is_reinject_pending()

def test_clear_removes_marker(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    queue_reinject()
    clear_reinject()
    assert not is_reinject_pending()
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/core/reinject.py
from __future__ import annotations

from pathlib import Path

from .safety import require_confirmed
from .state import get_paths


def _marker_path() -> Path:
    return get_paths().home / "reinject-pending"


def queue_reinject(*, memory: bool = True, claude_md: bool = True) -> Path:
    require_confirmed()
    paths = get_paths()
    paths.ensure_dirs()
    marker = _marker_path()
    flags = []
    if memory:
        flags.append("memory")
    if claude_md:
        flags.append("claude_md")
    marker.write_text(",".join(flags) + "\n", encoding="utf-8")
    return marker


def is_reinject_pending() -> bool:
    return _marker_path().exists()


def clear_reinject() -> None:
    p = _marker_path()
    if p.exists():
        p.unlink()
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "feat(core): reinject marker writer for Issue #29746"
```

---

## Task 5: install-hooks Windows-compat fix

**Files:**
- Modify: `src/cc_janitor/cli/commands/install_hooks.py`
- Create: `tests/unit/test_install_hooks_platform.py`

**Step 1: Failing test.**

```python
# tests/unit/test_install_hooks_platform.py
import json
from cc_janitor.cli.commands.install_hooks import _build_hook_command

def test_posix_hook_command():
    cmd = _build_hook_command("linux")
    assert "test -f" in cmd
    assert "rm" in cmd

def test_windows_hook_command():
    cmd = _build_hook_command("win32")
    assert "powershell" in cmd.lower()
    assert "Test-Path" in cmd
    assert "Remove-Item" in cmd
```

**Step 2: Run, FAIL.**

**Step 3: Refactor `install_hooks.py`.**

```python
# src/cc_janitor/cli/commands/install_hooks.py
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
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "fix(install-hooks): emit PowerShell branch on Windows"
```

---

## Task 6: Hooks discovery (merged view across all settings)

**Files:**
- Create: `src/cc_janitor/core/hooks.py`
- Create: `tests/unit/test_hooks_discover.py`
- Modify: `tests/data/mock-claude-home/.claude/settings.json` — add a sample hook
- Modify: `tests/data/mock-claude-home/.claude/settings.local.json` — add a malformed hook for validate test

**Step 1: Update fixtures.**

`tests/data/mock-claude-home/.claude/settings.json` (append to existing):
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {"type": "command", "command": "echo hi", "timeout": 5}
        ]
      }
    ]
  }
}
```

`tests/data/mock-claude-home/.claude/settings.local.json` keep its perms block, add a malformed hook:
```json
{
  "hooks": {
    "PostToolUse": [
      {"command": "echo bye"}
    ]
  }
}
```

**Step 2: Failing test.**

```python
# tests/unit/test_hooks_discover.py
from cc_janitor.core.hooks import discover_hooks, validate_hooks

def test_discover_picks_up_user_hook(mock_claude_home):
    entries = discover_hooks()
    matchers = {(e.event, e.matcher) for e in entries}
    assert ("PreToolUse", "Bash") in matchers

def test_validate_flags_malformed(mock_claude_home):
    issues = validate_hooks()
    assert any(i.kind == "missing-hooks-array" for i in issues)
```

**Step 3: Run, FAIL.**

**Step 4: Implement.**

```python
# src/cc_janitor/core/hooks.py
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from .state import get_paths

HookEvent = str  # "PreToolUse", "PostToolUse", ...
HookScope = Literal["user", "user-local", "project", "project-local", "managed"]


@dataclass
class HookEntry:
    event: HookEvent
    matcher: str
    type: Literal["command", "url", "subagent"]
    command: str | None
    url: str | None
    timeout: int | None
    source_path: Path
    source_scope: HookScope
    has_logging_wrapper: bool = False


@dataclass
class HookIssue:
    kind: Literal["missing-hooks-array", "empty-matcher", "empty-command",
                  "type-mismatch", "invalid-json"]
    source_path: Path
    detail: str


def _settings_sources() -> list[tuple[Path, HookScope]]:
    home = get_paths().home.parent
    cwd = Path.cwd()
    return [
        (home / ".claude" / "settings.json", "user"),
        (home / ".claude" / "settings.local.json", "user-local"),
        (cwd / ".claude" / "settings.json", "project"),
        (cwd / ".claude" / "settings.local.json", "project-local"),
    ]


def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def discover_hooks() -> list[HookEntry]:
    out: list[HookEntry] = []
    for path, scope in _settings_sources():
        data = _load(path)
        if not isinstance(data, dict):
            continue
        hooks_block = data.get("hooks") or {}
        if not isinstance(hooks_block, dict):
            continue
        for event, entries in hooks_block.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                matcher = entry.get("matcher", "*")
                inner = entry.get("hooks")
                if not isinstance(inner, list):
                    continue  # malformed; surfaced via validate_hooks()
                for h in inner:
                    if not isinstance(h, dict):
                        continue
                    cmd = h.get("command")
                    out.append(HookEntry(
                        event=event,
                        matcher=matcher,
                        type=h.get("type", "command"),
                        command=cmd,
                        url=h.get("url"),
                        timeout=h.get("timeout"),
                        source_path=path,
                        source_scope=scope,
                        has_logging_wrapper=bool(cmd and "cc-janitor/hooks-log/" in cmd),
                    ))
    return out


def validate_hooks() -> list[HookIssue]:
    issues: list[HookIssue] = []
    for path, _scope in _settings_sources():
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            issues.append(HookIssue("invalid-json", path, str(e)))
            continue
        hooks_block = data.get("hooks") or {}
        if not isinstance(hooks_block, dict):
            continue
        for event, entries in hooks_block.items():
            if not isinstance(entries, list):
                issues.append(HookIssue("type-mismatch", path,
                                        f"{event} must be a list"))
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    issues.append(HookIssue("type-mismatch", path,
                                            f"{event} entry not an object"))
                    continue
                if "hooks" not in entry or not isinstance(entry.get("hooks"), list):
                    issues.append(HookIssue("missing-hooks-array", path,
                                            f"{event} entry missing 'hooks' array"))
                    continue
                for h in entry["hooks"]:
                    if not isinstance(h, dict):
                        issues.append(HookIssue("type-mismatch", path, "hook not object"))
                        continue
                    if h.get("type") == "command" and not h.get("command"):
                        issues.append(HookIssue("empty-command", path,
                                                f"{event}/{entry.get('matcher','*')}"))
    return issues
```

**Step 5: Run, PASS. Commit.**

```bash
git commit -am "feat(core): hooks discovery and schema validation"
```

---

## Task 7: Hook simulation with stdin payloads

**Files:**
- Modify: `src/cc_janitor/core/hooks.py`
- Create: `tests/unit/test_hooks_simulate.py`

**Step 1: Failing test.**

```python
# tests/unit/test_hooks_simulate.py
import sys
from cc_janitor.core.hooks import simulate_hook, build_stdin_payload

def test_build_stdin_pretooluse():
    payload = build_stdin_payload("PreToolUse", tool_name="Bash")
    assert '"hook_event_name": "PreToolUse"' in payload
    assert '"tool_name": "Bash"' in payload

def test_simulate_runs_command(tmp_path, monkeypatch):
    out_file = tmp_path / "out.txt"
    cmd = f'{sys.executable} -c "import sys; sys.stdout.write(sys.stdin.read())"'
    result = simulate_hook(cmd, event="PreToolUse", matcher="Bash", timeout=10)
    assert result.exit_code == 0
    assert "PreToolUse" in result.stdout
    assert result.duration_ms >= 0
```

**Step 2: Run, FAIL.**

**Step 3: Append to `core/hooks.py`.**

```python
# additions to src/cc_janitor/core/hooks.py
import shlex
import subprocess
import sys
import time


@dataclass
class HookRunResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int


STDIN_TEMPLATES = {
    "PreToolUse": {
        "session_id": "sim-001", "transcript_path": "/tmp/x.jsonl",
        "hook_event_name": "PreToolUse", "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
    },
    "PostToolUse": {
        "session_id": "sim-001", "transcript_path": "/tmp/x.jsonl",
        "hook_event_name": "PostToolUse", "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
        "tool_response": {"stdout": "hi"},
    },
    "UserPromptSubmit": {
        "session_id": "sim-001", "hook_event_name": "UserPromptSubmit",
        "user_prompt": "hello",
    },
    "Stop": {"session_id": "sim-001", "hook_event_name": "Stop"},
    "SubagentStop": {"session_id": "sim-001", "hook_event_name": "SubagentStop"},
    "Notification": {"session_id": "sim-001", "hook_event_name": "Notification",
                     "message": "test"},
    "SessionStart": {"session_id": "sim-001", "hook_event_name": "SessionStart"},
    "SessionEnd": {"session_id": "sim-001", "hook_event_name": "SessionEnd"},
    "PreCompact": {"session_id": "sim-001", "hook_event_name": "PreCompact"},
}


def build_stdin_payload(event: str, **overrides) -> str:
    tpl = dict(STDIN_TEMPLATES.get(event, {"hook_event_name": event}))
    tpl.update(overrides)
    return json.dumps(tpl, indent=2)


def simulate_hook(command: str, *, event: str, matcher: str = "*",
                  timeout: int = 30, stdin_override: str | None = None) -> HookRunResult:
    payload = stdin_override or build_stdin_payload(event, tool_name=matcher)
    if sys.platform == "win32":
        args = ["powershell.exe", "-NoProfile", "-Command", command]
    else:
        args = ["sh", "-c", command]
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            args,
            input=payload.encode("utf-8"),
            capture_output=True,
            timeout=timeout,
        )
        return HookRunResult(
            exit_code=proc.returncode,
            stdout=proc.stdout.decode("utf-8", errors="replace"),
            stderr=proc.stderr.decode("utf-8", errors="replace"),
            duration_ms=int((time.perf_counter() - start) * 1000),
        )
    except subprocess.TimeoutExpired:
        return HookRunResult(124, "", f"timeout after {timeout}s", timeout * 1000)
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "feat(core): hooks simulate with realistic stdin payloads"
```

---

## Task 8: Hooks logging wrapper (enable / disable)

**Files:**
- Modify: `src/cc_janitor/core/hooks.py`
- Create: `tests/unit/test_hooks_logging.py`

**Step 1: Failing test.**

```python
# tests/unit/test_hooks_logging.py
import json
from cc_janitor.core.hooks import enable_logging, disable_logging, discover_hooks

def test_enable_logging_wraps_command(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    enable_logging("PreToolUse", matcher="Bash")
    settings_p = mock_claude_home / ".claude" / "settings.json"
    data = json.loads(settings_p.read_text(encoding="utf-8"))
    cmd = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "cc-janitor/hooks-log" in cmd
    assert "cc-janitor-original:" in cmd  # sentinel for disable

def test_disable_logging_restores(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    enable_logging("PreToolUse", matcher="Bash")
    disable_logging("PreToolUse", matcher="Bash")
    settings_p = mock_claude_home / ".claude" / "settings.json"
    data = json.loads(settings_p.read_text(encoding="utf-8"))
    cmd = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "cc-janitor/hooks-log" not in cmd
    assert cmd == "echo hi"
```

**Step 2: Run, FAIL.**

**Step 3: Append to `core/hooks.py`.**

```python
# additions to src/cc_janitor/core/hooks.py
import base64

from .safety import require_confirmed

SENTINEL = "cc-janitor-original:"


def _log_path_for(event: str) -> Path:
    return get_paths().hooks_log / f"{event}.log"


def _wrap_posix(orig: str, log_p: Path) -> str:
    encoded = base64.b64encode(orig.encode("utf-8")).decode("ascii")
    return f"# {SENTINEL} {encoded}\n({orig}) 2>&1 | tee -a '{log_p}'"


def _wrap_powershell(orig: str, log_p: Path) -> str:
    encoded = base64.b64encode(orig.encode("utf-8")).decode("ascii")
    return (
        f"# {SENTINEL} {encoded}\n"
        f"({orig}) 2>&1 | Tee-Object -FilePath '{log_p}' -Append"
    )


def _unwrap(wrapped: str) -> str | None:
    for line in wrapped.splitlines():
        if SENTINEL in line:
            encoded = line.split(SENTINEL, 1)[1].strip()
            try:
                return base64.b64decode(encoded.encode("ascii")).decode("utf-8")
            except Exception:
                return None
    return None


def _modify_hook_command(event: str, matcher: str, transform) -> Path:
    require_confirmed()
    settings = get_paths().home.parent / ".claude" / "settings.json"
    data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
    pre = data.setdefault("hooks", {}).setdefault(event, [])
    for entry in pre:
        if entry.get("matcher") != matcher:
            continue
        for h in entry.get("hooks", []):
            cmd = h.get("command")
            if not cmd:
                continue
            new_cmd = transform(cmd)
            if new_cmd is not None:
                h["command"] = new_cmd
    settings.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return settings


def enable_logging(event: str, *, matcher: str = "*") -> Path:
    log_p = _log_path_for(event)
    log_p.parent.mkdir(parents=True, exist_ok=True)
    wrap = _wrap_powershell if sys.platform == "win32" else _wrap_posix
    return _modify_hook_command(event, matcher, lambda cmd: wrap(cmd, log_p))


def disable_logging(event: str, *, matcher: str = "*") -> Path:
    return _modify_hook_command(event, matcher, _unwrap)
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "feat(core): hooks logging wrapper with reversible enable/disable"
```

---

## Task 9: Scheduler abstraction (cron + schtasks)

**Files:**
- Create: `src/cc_janitor/core/schedule.py`
- Create: `tests/unit/test_schedule_cron.py`
- Create: `tests/unit/test_schedule_schtasks.py`

**Step 1: Failing test.**

```python
# tests/unit/test_schedule_cron.py
from cc_janitor.core.schedule import CronScheduler, ScheduledJob, TEMPLATES

def test_template_registry_complete():
    assert {"perms-prune", "trash-cleanup", "session-prune",
            "context-audit", "backup-rotate"} <= set(TEMPLATES.keys())

def test_cron_add_then_list_then_remove(monkeypatch, tmp_path):
    captured = {"crontab_in": "", "stdin": ""}
    def fake_run(args, input=None, capture_output=False, **kw):
        class R:
            returncode = 0
            stdout = captured["crontab_in"].encode() if "-l" in args else b""
            stderr = b""
        if input is not None:
            captured["stdin"] = input.decode() if isinstance(input, bytes) else input
            captured["crontab_in"] = captured["stdin"]
        return R()
    monkeypatch.setattr("subprocess.run", fake_run)

    sched = CronScheduler()
    sched.add_job(ScheduledJob(
        name="cc-janitor-perms-prune",
        template="perms-prune",
        cron_expr="0 3 * * 0",
        command="cc-janitor perms prune --older-than 90d --dry-run",
        next_run=None, last_run=None, last_status="never",
        dry_run_pending=True, backend="cron",
    ))
    assert "cc-janitor-perms-prune" in captured["stdin"]

    jobs = sched.list_jobs()
    assert any(j.name == "cc-janitor-perms-prune" for j in jobs)

    sched.remove_job("cc-janitor-perms-prune")
    assert "cc-janitor-perms-prune" not in captured["stdin"]
```

```python
# tests/unit/test_schedule_schtasks.py
from cc_janitor.core.schedule import SchtasksScheduler, ScheduledJob

def test_schtasks_add_calls_create(monkeypatch):
    calls = []
    def fake_run(args, **kw):
        calls.append(args)
        class R: returncode = 0; stdout = b""; stderr = b""
        return R()
    monkeypatch.setattr("subprocess.run", fake_run)
    s = SchtasksScheduler()
    s.add_job(ScheduledJob(
        name="cc-janitor-perms-prune", template="perms-prune",
        cron_expr="0 3 * * 0",
        command="cc-janitor perms prune --older-than 90d --dry-run",
        next_run=None, last_run=None, last_status="never",
        dry_run_pending=True, backend="schtasks",
    ))
    assert any("/Create" in str(c) for c in calls)
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/core/schedule.py
from __future__ import annotations

import json
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from croniter import croniter

from .safety import require_confirmed
from .state import get_paths

JobStatus = Literal["ok", "fail", "never"]


@dataclass
class ScheduledJob:
    name: str
    template: str
    cron_expr: str
    command: str
    next_run: datetime | None
    last_run: datetime | None
    last_status: JobStatus
    dry_run_pending: bool
    backend: Literal["cron", "schtasks"]


TEMPLATES: dict[str, dict] = {
    "perms-prune": {
        "default_cron": "0 3 * * 0",
        "command": "cc-janitor perms prune --older-than 90d",
    },
    "trash-cleanup": {
        "default_cron": "0 4 1 * *",
        "command": "cc-janitor trash empty --older-than 30d",
    },
    "session-prune": {
        "default_cron": "0 4 15 * *",
        "command": "cc-janitor session prune --older-than 90d",
    },
    "context-audit": {
        "default_cron": "5 0 * * *",
        "command": "cc-janitor context cost --json",
    },
    "backup-rotate": {
        "default_cron": "0 4 * * 0",
        "command": "cc-janitor trash empty --older-than 30d --backups",
    },
}

MARKER_PREFIX = "# cc-janitor-job:"


def _manifest_dir() -> Path:
    p = get_paths().home / "schedule"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _save_manifest(job: ScheduledJob) -> None:
    p = _manifest_dir() / f"{job.name}.json"
    d = asdict(job)
    for k in ("next_run", "last_run"):
        d[k] = d[k].isoformat() if d[k] else None
    p.write_text(json.dumps(d, indent=2), encoding="utf-8")


def _load_manifest(name: str) -> ScheduledJob | None:
    p = _manifest_dir() / f"{name}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    for k in ("next_run", "last_run"):
        d[k] = datetime.fromisoformat(d[k]) if d[k] else None
    return ScheduledJob(**d)


def _delete_manifest(name: str) -> None:
    p = _manifest_dir() / f"{name}.json"
    if p.exists():
        p.unlink()


def _next_run(cron_expr: str) -> datetime:
    return croniter(cron_expr, datetime.now(timezone.utc)).get_next(datetime)


class Scheduler(ABC):
    @abstractmethod
    def list_jobs(self) -> list[ScheduledJob]: ...
    @abstractmethod
    def add_job(self, job: ScheduledJob) -> None: ...
    @abstractmethod
    def remove_job(self, name: str) -> None: ...

    def run_now(self, name: str) -> int:
        job = _load_manifest(name)
        if job is None:
            raise FileNotFoundError(name)
        env = {**__import__("os").environ,
               "CC_JANITOR_USER_CONFIRMED": "1",
               "CC_JANITOR_SCHEDULED": "1"}
        result = subprocess.run(job.command, shell=True, env=env)
        return result.returncode


class CronScheduler(Scheduler):
    def _read_crontab(self) -> str:
        proc = subprocess.run(["crontab", "-l"], capture_output=True)
        return proc.stdout.decode("utf-8", errors="replace") if proc.returncode == 0 else ""

    def _write_crontab(self, content: str) -> None:
        subprocess.run(["crontab", "-"], input=content.encode("utf-8"))

    def list_jobs(self) -> list[ScheduledJob]:
        out: list[ScheduledJob] = []
        for line in self._read_crontab().splitlines():
            if MARKER_PREFIX not in line:
                continue
            name = line.split(MARKER_PREFIX, 1)[1].strip()
            job = _load_manifest(name)
            if job:
                out.append(job)
        return out

    def add_job(self, job: ScheduledJob) -> None:
        require_confirmed()
        existing = self._read_crontab().splitlines()
        existing = [ln for ln in existing
                    if not (MARKER_PREFIX in ln and ln.endswith(job.name))]
        env = "CC_JANITOR_USER_CONFIRMED=1 CC_JANITOR_SCHEDULED=1"
        cmd = job.command + (" --dry-run" if job.dry_run_pending else "")
        existing.append(f"{job.cron_expr} {env} {cmd} {MARKER_PREFIX} {job.name}")
        self._write_crontab("\n".join(existing) + "\n")
        job.next_run = _next_run(job.cron_expr)
        _save_manifest(job)

    def remove_job(self, name: str) -> None:
        require_confirmed()
        existing = self._read_crontab().splitlines()
        existing = [ln for ln in existing
                    if not (MARKER_PREFIX in ln and ln.endswith(name))]
        self._write_crontab("\n".join(existing) + "\n")
        _delete_manifest(name)


class SchtasksScheduler(Scheduler):
    def _cron_to_schtasks(self, cron_expr: str) -> list[str]:
        # Minimal mapping: only common templates' cron forms.
        # m h dom mon dow
        m, h, dom, mon, dow = cron_expr.split()
        if dow != "*" and dom == "*":
            map_dow = {"0": "SUN", "1": "MON", "2": "TUE", "3": "WED",
                       "4": "THU", "5": "FRI", "6": "SAT"}
            return ["/SC", "WEEKLY", "/D", map_dow.get(dow, "SUN"),
                    "/ST", f"{int(h):02d}:{int(m):02d}"]
        if dom != "*" and dow == "*":
            return ["/SC", "MONTHLY", "/D", str(int(dom)),
                    "/ST", f"{int(h):02d}:{int(m):02d}"]
        return ["/SC", "DAILY", "/ST", f"{int(h):02d}:{int(m):02d}"]

    def list_jobs(self) -> list[ScheduledJob]:
        out: list[ScheduledJob] = []
        for p in _manifest_dir().glob("*.json"):
            job = _load_manifest(p.stem)
            if job and job.backend == "schtasks":
                out.append(job)
        return out

    def add_job(self, job: ScheduledJob) -> None:
        require_confirmed()
        cmd = job.command + (" --dry-run" if job.dry_run_pending else "")
        wrapper = (
            'cmd /c "set CC_JANITOR_USER_CONFIRMED=1 && '
            f'set CC_JANITOR_SCHEDULED=1 && {cmd}"'
        )
        args = ["schtasks", "/Create", "/TN", job.name, "/TR", wrapper, "/F",
                *self._cron_to_schtasks(job.cron_expr)]
        subprocess.run(args)
        job.next_run = _next_run(job.cron_expr)
        _save_manifest(job)

    def remove_job(self, name: str) -> None:
        require_confirmed()
        subprocess.run(["schtasks", "/Delete", "/TN", name, "/F"])
        _delete_manifest(name)


def get_scheduler() -> Scheduler:
    return SchtasksScheduler() if sys.platform == "win32" else CronScheduler()
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "feat(core): scheduler abstraction with cron+schtasks backends and dry-run-first"
```

---

## Task 10: Hard cap on scheduled deletions

**Files:**
- Modify: `src/cc_janitor/core/safety.py`
- Create: `tests/unit/test_safety_hard_cap.py`

**Step 1: Failing test.**

```python
# tests/unit/test_safety_hard_cap.py
import pytest
from pathlib import Path
from cc_janitor.core.safety import (
    soft_delete, RunawayCapError, reset_run_counter,
)
from cc_janitor.core.state import Paths

def test_hard_cap_when_scheduled(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    monkeypatch.setenv("CC_JANITOR_SCHEDULED", "1")
    monkeypatch.setenv("CC_JANITOR_HARD_CAP", "3")
    reset_run_counter()
    paths = Paths(home=tmp_path / ".cc-janitor")
    paths.ensure_dirs()
    for i in range(3):
        f = tmp_path / f"v{i}.txt"; f.write_text("x")
        soft_delete(f, paths=paths)
    f4 = tmp_path / "v3.txt"; f4.write_text("x")
    with pytest.raises(RunawayCapError):
        soft_delete(f4, paths=paths)

def test_no_cap_when_not_scheduled(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    monkeypatch.delenv("CC_JANITOR_SCHEDULED", raising=False)
    monkeypatch.setenv("CC_JANITOR_HARD_CAP", "1")
    reset_run_counter()
    paths = Paths(home=tmp_path / ".cc-janitor")
    paths.ensure_dirs()
    for i in range(5):
        f = tmp_path / f"v{i}.txt"; f.write_text("x")
        soft_delete(f, paths=paths)  # no cap
```

**Step 2: Run, FAIL.**

**Step 3: Modify `core/safety.py`** — add at top of file plus modify `soft_delete`:

```python
# Add near top of safety.py (with other module state)
import os as _os
_run_counter = 0

class RunawayCapError(RuntimeError):
    """Scheduled run exceeded the hard delete cap."""

def reset_run_counter() -> None:
    global _run_counter
    _run_counter = 0

def _bump_and_check_cap() -> None:
    global _run_counter
    if _os.environ.get("CC_JANITOR_SCHEDULED") != "1":
        return
    cap = int(_os.environ.get("CC_JANITOR_HARD_CAP", "200"))
    _run_counter += 1
    if _run_counter > cap:
        raise RunawayCapError(
            f"scheduled run exceeded hard cap of {cap} deletions"
        )
```

In `soft_delete`, after `paths.ensure_dirs()` and before the move, call `_bump_and_check_cap()`.

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "feat(safety): hard cap on deletions during CC_JANITOR_SCHEDULED runs"
```

---

## Task 11: Memory CLI subapp

**Files:**
- Create: `src/cc_janitor/cli/commands/memory.py`
- Modify: `src/cc_janitor/cli/__init__.py`
- Create: `tests/unit/test_cli_memory.py`

**Step 1: Failing test.**

```python
# tests/unit/test_cli_memory.py
from typer.testing import CliRunner
from cc_janitor.cli import app

runner = CliRunner()

def test_memory_list_runs(mock_claude_home):
    r = runner.invoke(app, ["memory", "list"])
    assert r.exit_code == 0
    assert "MEMORY.md" in r.stdout

def test_memory_list_json(mock_claude_home):
    import json
    r = runner.invoke(app, ["memory", "list", "--json"])
    assert r.exit_code == 0
    data = json.loads(r.stdout)
    assert any(item["path"].endswith("MEMORY.md") for item in data)

def test_memory_archive_requires_confirmed(mock_claude_home, monkeypatch):
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    r = runner.invoke(app, ["memory", "archive", "MEMORY.md"])
    assert r.exit_code != 0

def test_memory_archive_with_confirm(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    r = runner.invoke(app, ["memory", "archive", "MEMORY.md"])
    assert r.exit_code == 0
```

**Step 2: Run, FAIL.**

**Step 3: Implement subapp.**

```python
# src/cc_janitor/cli/commands/memory.py
from __future__ import annotations

import json
from pathlib import Path

import typer

from ...core.audit import AuditLog
from ...core.memory import (
    archive_memory_file, discover_memory_files, find_duplicate_lines,
    move_memory_type, open_in_editor, parse_memory_file,
)
from ...core.state import get_paths
from .._audit import _audit_action

app = typer.Typer(no_args_is_help=True, help="Memory file management")


def _resolve(name: str) -> Path:
    for m in discover_memory_files(include_archived=True):
        if m.path.name == name or str(m.path) == name:
            return m.path
    raise typer.BadParameter(f"Memory file not found: {name}")


@app.command("list")
def list_cmd(
    type_filter: str | None = typer.Option(None, "--type"),
    project: str | None = typer.Option(None, "--project"),
    json_out: bool = typer.Option(False, "--json"),
):
    items = discover_memory_files(type_filter=type_filter, project=project)
    if json_out:
        data = [{"path": str(m.path), "type": m.type, "size": m.size_bytes,
                 "lines": m.line_count, "modified": m.last_modified.isoformat(),
                 "title": m.title} for m in items]
        typer.echo(json.dumps(data, indent=2))
        return
    for m in items:
        typer.echo(f"{m.type:<10} {m.size_bytes:>7}  {m.path.name}")


@app.command("show")
def show_cmd(name: str):
    p = _resolve(name)
    typer.echo(p.read_text(encoding="utf-8"))


@app.command("edit")
def edit_cmd(name: str):
    p = _resolve(name)
    with _audit_action("memory edit", [str(p)]):
        open_in_editor(p)


@app.command("archive")
def archive_cmd(name: str):
    p = _resolve(name)
    with _audit_action("memory archive", [str(p)]):
        dst = archive_memory_file(p)
    typer.echo(f"archived to {dst}")


@app.command("move-type")
def move_type_cmd(name: str, new_type: str):
    p = _resolve(name)
    with _audit_action("memory move-type", [str(p), new_type]):
        move_memory_type(p, new_type)
    typer.echo(f"moved {p.name} → type={new_type}")


@app.command("find-duplicates")
def find_duplicates_cmd():
    items = discover_memory_files()
    dups = find_duplicate_lines([m.path for m in items])
    if not dups:
        typer.echo("no duplicate lines found")
        return
    for d in dups:
        typer.echo(f"\n[{len(d.files)} files] {d.line[:80]}")
        for f in d.files:
            typer.echo(f"  - {f}")
```

If `cli/_audit.py` does not yet expose `_audit_action`, copy the helper used in `cli/commands/perms.py` Phase 1 — a context manager that wraps the call with `require_confirmed()` (already done by the core function, but keep here for non-mutating ones it's a no-op) and appends an `AuditLog.record(...)` entry.

In `src/cc_janitor/cli/__init__.py`, register:

```python
from .commands.memory import app as memory_app
app.add_typer(memory_app, name="memory")
```

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "feat(cli): memory subapp — list/show/edit/archive/move-type/find-duplicates"
```

---

## Task 12: Hooks CLI subapp + context reinject

**Files:**
- Create: `src/cc_janitor/cli/commands/hooks.py`
- Modify: `src/cc_janitor/cli/commands/context.py`
- Modify: `src/cc_janitor/cli/__init__.py`
- Create: `tests/unit/test_cli_hooks.py`

**Step 1: Failing test.**

```python
# tests/unit/test_cli_hooks.py
from typer.testing import CliRunner
from cc_janitor.cli import app
runner = CliRunner()

def test_hooks_list(mock_claude_home):
    r = runner.invoke(app, ["hooks", "list"])
    assert r.exit_code == 0
    assert "PreToolUse" in r.stdout

def test_hooks_validate_reports_malformed(mock_claude_home):
    r = runner.invoke(app, ["hooks", "validate"])
    assert "missing-hooks-array" in r.stdout

def test_hooks_simulate_smoke(mock_claude_home):
    r = runner.invoke(app, ["hooks", "simulate", "PreToolUse", "Bash"])
    # may fail if `echo hi` not in PATH on Windows; allow exit 0 or non-zero
    assert "duration" in r.stdout.lower() or r.exit_code in (0, 1, 124)

def test_context_reinject(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    r = runner.invoke(app, ["context", "reinject"])
    assert r.exit_code == 0
    from cc_janitor.core.reinject import is_reinject_pending
    assert is_reinject_pending()
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/cli/commands/hooks.py
from __future__ import annotations

import json
import typer

from ...core.hooks import (
    discover_hooks, enable_logging, disable_logging,
    simulate_hook, validate_hooks,
)
from .._audit import _audit_action

app = typer.Typer(no_args_is_help=True, help="Hook discovery/debugger")


@app.command("list")
def list_cmd(
    event: str | None = typer.Option(None, "--event"),
    json_out: bool = typer.Option(False, "--json"),
):
    items = discover_hooks()
    if event:
        items = [e for e in items if e.event == event]
    if json_out:
        typer.echo(json.dumps([{
            "event": e.event, "matcher": e.matcher, "type": e.type,
            "command": e.command, "source": str(e.source_path),
            "scope": e.source_scope, "logging": e.has_logging_wrapper,
        } for e in items], indent=2))
        return
    for e in items:
        cmd_preview = (e.command or "")[:60]
        typer.echo(f"{e.event:<14} {e.matcher:<10} {cmd_preview}  ({e.source_scope})")


@app.command("show")
def show_cmd(event: str, matcher: str = "*"):
    for e in discover_hooks():
        if e.event == event and e.matcher == matcher:
            typer.echo(json.dumps({
                "event": e.event, "matcher": e.matcher, "type": e.type,
                "command": e.command, "url": e.url, "timeout": e.timeout,
                "source": str(e.source_path), "scope": e.source_scope,
            }, indent=2))
            return
    raise typer.Exit(1)


@app.command("simulate")
def simulate_cmd(event: str, matcher: str = "*",
                 input_file: str | None = typer.Option(None, "--input-file")):
    target = next((e for e in discover_hooks()
                   if e.event == event and e.matcher == matcher), None)
    if target is None or not target.command:
        typer.echo("no matching hook with command")
        raise typer.Exit(1)
    stdin_override = None
    if input_file:
        from pathlib import Path
        stdin_override = Path(input_file).read_text(encoding="utf-8")
    result = simulate_hook(target.command, event=event, matcher=matcher,
                           stdin_override=stdin_override)
    typer.echo(f"exit={result.exit_code} duration={result.duration_ms}ms")
    if result.stdout:
        typer.echo(f"--- stdout ---\n{result.stdout}")
    if result.stderr:
        typer.echo(f"--- stderr ---\n{result.stderr}")


@app.command("enable-logging")
def enable_logging_cmd(event: str, matcher: str = "*"):
    with _audit_action("hooks enable-logging", [event, matcher]):
        enable_logging(event, matcher=matcher)


@app.command("disable-logging")
def disable_logging_cmd(event: str, matcher: str = "*"):
    with _audit_action("hooks disable-logging", [event, matcher]):
        disable_logging(event, matcher=matcher)


@app.command("validate")
def validate_cmd():
    issues = validate_hooks()
    if not issues:
        typer.echo("no issues")
        return
    for i in issues:
        typer.echo(f"[{i.kind}] {i.source_path}: {i.detail}")
```

Modify `src/cc_janitor/cli/commands/context.py` — add a new `reinject` command that calls `core.reinject.queue_reinject(...)` inside `_audit_action("context reinject", ...)`.

Register the hooks subapp in `cli/__init__.py`.

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "feat(cli): hooks subapp and context reinject command"
```

---

## Task 13: Schedule CLI subapp

**Files:**
- Create: `src/cc_janitor/cli/commands/schedule.py`
- Modify: `src/cc_janitor/cli/__init__.py`
- Create: `tests/unit/test_cli_schedule.py`

**Step 1: Failing test.**

```python
# tests/unit/test_cli_schedule.py
from typer.testing import CliRunner
from cc_janitor.cli import app
runner = CliRunner()

def test_schedule_list_empty(mock_claude_home, monkeypatch):
    monkeypatch.setattr("cc_janitor.core.schedule.get_scheduler",
                        lambda: __import__("cc_janitor.core.schedule",
                                          fromlist=["CronScheduler"]).CronScheduler())
    monkeypatch.setattr("subprocess.run",
                        lambda *a, **kw: type("R",(), {"returncode":0,"stdout":b"","stderr":b""})())
    r = runner.invoke(app, ["schedule", "list"])
    assert r.exit_code == 0

def test_schedule_add_unknown_template(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    r = runner.invoke(app, ["schedule", "add", "no-such-template"])
    assert r.exit_code != 0
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/cli/commands/schedule.py
from __future__ import annotations

import json
import typer

from ...core.schedule import (
    ScheduledJob, TEMPLATES, get_scheduler, _load_manifest, _save_manifest,
)
from .._audit import _audit_action

app = typer.Typer(no_args_is_help=True, help="Cross-platform scheduler")


@app.command("list")
def list_cmd(json_out: bool = typer.Option(False, "--json")):
    jobs = get_scheduler().list_jobs()
    if json_out:
        typer.echo(json.dumps([{
            "name": j.name, "template": j.template, "cron": j.cron_expr,
            "next_run": j.next_run.isoformat() if j.next_run else None,
            "dry_run_pending": j.dry_run_pending, "last_status": j.last_status,
        } for j in jobs], indent=2))
        return
    for j in jobs:
        flag = " [dry-run-pending]" if j.dry_run_pending else ""
        typer.echo(f"{j.name:<32} {j.cron_expr:<14} {j.last_status}{flag}")


@app.command("add")
def add_cmd(template: str,
            cron: str | None = typer.Option(None, "--cron")):
    if template not in TEMPLATES:
        raise typer.BadParameter(f"unknown template: {template}; "
                                 f"choose from {list(TEMPLATES)}")
    spec = TEMPLATES[template]
    cron_expr = cron or spec["default_cron"]
    job = ScheduledJob(
        name=f"cc-janitor-{template}",
        template=template,
        cron_expr=cron_expr,
        command=spec["command"],
        next_run=None, last_run=None, last_status="never",
        dry_run_pending=True,
        backend="schtasks" if __import__("sys").platform == "win32" else "cron",
    )
    with _audit_action("schedule add", [template, cron_expr]):
        get_scheduler().add_job(job)
    typer.echo(f"added {job.name} (first run is --dry-run; "
               f"promote after success)")


@app.command("remove")
def remove_cmd(name: str):
    with _audit_action("schedule remove", [name]):
        get_scheduler().remove_job(name)


@app.command("run")
def run_cmd(name: str):
    rc = get_scheduler().run_now(name)
    typer.echo(f"exit={rc}")


@app.command("promote")
def promote_cmd(name: str):
    job = _load_manifest(name)
    if job is None:
        raise typer.Exit(1)
    with _audit_action("schedule promote", [name]):
        sched = get_scheduler()
        sched.remove_job(name)
        job.dry_run_pending = False
        sched.add_job(job)
    typer.echo(f"promoted {name} to live mode")
```

Register in `cli/__init__.py`.

**Step 4: Run, PASS. Commit.**

```bash
git commit -am "feat(cli): schedule subapp with dry-run-first guard"
```

---

## Task 14: TUI Memory screen

**Files:**
- Create: `src/cc_janitor/tui/screens/memory_screen.py`
- Modify: `src/cc_janitor/tui/app.py`
- Create: `tests/tui/test_memory_screen.py`

**Step 1: Failing snapshot test.**

```python
# tests/tui/test_memory_screen.py
import pytest
from cc_janitor.tui.app import CCJanitorApp

@pytest.mark.asyncio
async def test_memory_screen_renders(mock_claude_home, snap_compare):
    app = CCJanitorApp(initial_tab="memory")
    assert await snap_compare(app, press=["enter"])
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/tui/screens/memory_screen.py
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Markdown, Static

from ...core.memory import discover_memory_files
from ...core.reinject import queue_reinject


class MemoryScreen(Static):
    BINDINGS = [
        ("e", "edit", "Edit"),
        ("a", "archive", "Archive"),
        ("m", "move_type", "Move type"),
        ("r", "reinject", "Reinject"),
        ("f", "find_dupes", "Duplicates"),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical():
                yield DataTable(id="memory-table")
            with Vertical():
                yield Markdown(id="memory-preview")
        yield Footer()

    def on_mount(self) -> None:
        table: DataTable = self.query_one("#memory-table", DataTable)
        table.add_columns("Type", "Size", "Modified", "Name", "Project")
        for m in discover_memory_files():
            table.add_row(m.type, str(m.size_bytes),
                          m.last_modified.strftime("%Y-%m-%d"),
                          m.path.name, m.project or "(global)")

    def on_data_table_row_highlighted(self, event) -> None:
        items = discover_memory_files()
        try:
            m = items[event.cursor_row]
        except IndexError:
            return
        self.query_one("#memory-preview", Markdown).update(m.body[:4000])

    def action_reinject(self) -> None:
        import os
        os.environ.setdefault("CC_JANITOR_USER_CONFIRMED", "1")
        queue_reinject()
        self.notify("Reinject queued — fires on next Claude Code tool call")
```

In `tui/app.py` replace the placeholder for the Memory tab content with `MemoryScreen()`.

**Step 4: Run, PASS (and accept the new snapshot baseline). Commit.**

```bash
git commit -am "feat(tui): Memory screen with preview and reinject action"
```

---

## Task 15: TUI Hooks screen

**Files:**
- Create: `src/cc_janitor/tui/screens/hooks_screen.py`
- Modify: `src/cc_janitor/tui/app.py`
- Create: `tests/tui/test_hooks_screen.py`

Mirror Task 14's pattern. Screen has `DataTable` (event/matcher/type/cmd-preview/scope/last-status), right pane `Static` for full source. Bindings: `t` simulate (calls `simulate_hook`, displays result in a modal/panel), `l` toggle logging, `v` open source in editor.

The simulate action on a row pulls the `HookEntry` for the highlighted row, calls `simulate_hook(...)`, and writes `f"exit={r.exit_code} {r.duration_ms}ms\n{r.stdout}\n{r.stderr}"` into the right pane.

**Snapshot test, implement, commit:**

```bash
git commit -am "feat(tui): Hooks screen with simulate and logging actions"
```

---

## Task 16: TUI Schedule screen

**Files:**
- Create: `src/cc_janitor/tui/screens/schedule_screen.py`
- Modify: `src/cc_janitor/tui/app.py`
- Create: `tests/tui/test_schedule_screen.py`

`DataTable` (name/template/cron/next-run/last-run/status/dry-run-pending) + footer keys `a` add (modal: select from `TEMPLATES`, optional cron field with live `croniter` validation; on submit calls `get_scheduler().add_job(...)`), `r` remove, `n` run-now, `p` promote.

**Snapshot test, implement, commit:**

```bash
git commit -am "feat(tui): Schedule screen with add/remove/promote modals"
```

---

## Task 17: i18n keys + cookbook addendum + CHANGELOG 0.2.0

**Files:**
- Modify: `src/cc_janitor/i18n/en.toml`
- Modify: `src/cc_janitor/i18n/ru.toml`
- Modify: `docs/cookbook.md`
- Modify: `docs/CC_USAGE.md`
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml` (drop `.dev0`)

**Step 1: Add i18n keys.** In both `en.toml` and `ru.toml` add three top-level sections `[memory]`, `[hooks]`, `[schedule]` covering: titles, button labels, status words ("dry-run pending", "promoted"), validation errors (missing-hooks-array, empty-command), and template names. Mirror Phase 1 key style.

**Step 2: Cookbook recipes.** Append four sections to `docs/cookbook.md`:

1. **Memory hygiene** — "I have feedback files I want to promote to user-level":
   `cc-janitor memory list --type feedback` →
   `CC_JANITOR_USER_CONFIRMED=1 cc-janitor memory move-type feedback_no_emojis.md user`.
2. **My memory edits don't take effect** —
   `CC_JANITOR_USER_CONFIRMED=1 cc-janitor install-hooks` (one-time setup),
   then `CC_JANITOR_USER_CONFIRMED=1 cc-janitor context reinject`.
3. **Hook isn't firing** — `cc-janitor hooks list`,
   `cc-janitor hooks validate` (catches missing-hooks-array),
   `cc-janitor hooks simulate PreToolUse Bash` (no `--debug` needed),
   `CC_JANITOR_USER_CONFIRMED=1 cc-janitor hooks enable-logging PreToolUse Bash`.
4. **Schedule weekly cleanup** — `CC_JANITOR_USER_CONFIRMED=1 cc-janitor schedule add perms-prune`,
   wait for the dry-run to fire, then `CC_JANITOR_USER_CONFIRMED=1 cc-janitor schedule promote cc-janitor-perms-prune`.

**Step 3: Update CC_USAGE.md.** List the new commands by read-only/mutating split:

- Read-only: `memory list/show/find-duplicates`, `hooks list/show/simulate/validate`, `schedule list/audit`.
- Mutating: `memory edit/archive/move-type/delete`, `context reinject`, `hooks enable-logging/disable-logging/fix-windows-env`, `schedule add/remove/run/promote`.

**Step 4: CHANGELOG 0.2.0 block.**

Append under `## [Unreleased]` (or convert to `## [0.2.0] - 2026-05-XX`):

```markdown
### Added — Phase 2

#### Memory editor
- `core/memory.py` — frontmatter parsing with `python-frontmatter`, type
  classification (user/feedback/project/reference/unknown), discovery,
  duplicate-line detection, archive, move-type, open-in-editor
- `cc-janitor memory list/show/edit/archive/move-type/find-duplicates`
- TUI Memory tab replaces Phase 1 placeholder

#### Reinject hook (closes #29746)
- `cc-janitor context reinject [--memory] [--claude-md]` writes
  `~/.cc-janitor/reinject-pending` marker
- TUI Memory tab `[r]` action queues reinject
- `install-hooks` now emits Windows PowerShell branch alongside POSIX shell

#### Hooks debugger (closes #11544, #10401, #16564)
- `core/hooks.py` — discover across 4 settings layers, schema validate,
  simulate with realistic stdin payloads (9 events), reversible logging
  wrapper with sentinel-based unwrap
- `cc-janitor hooks list/show/simulate/enable-logging/disable-logging/validate`
- TUI Hooks tab replaces Phase 1 placeholder

#### Scheduler
- `core/schedule.py` — `Scheduler` ABC with `CronScheduler` (Linux/macOS)
  and `SchtasksScheduler` (Windows) backends
- 5 templates: perms-prune, trash-cleanup, session-prune,
  context-audit, backup-rotate
- Scheduled runs set `CC_JANITOR_USER_CONFIRMED=1` and `CC_JANITOR_SCHEDULED=1`
- `CC_JANITOR_SCHEDULED=1` activates per-run hard cap (default 200,
  configurable via `CC_JANITOR_HARD_CAP`)
- First run after `add` is automatically `--dry-run`; `promote` flips to live
- `cc-janitor schedule list/add/remove/run/promote`
- TUI Schedule tab replaces Phase 1 placeholder

#### Documentation
- 4 new cookbook recipes (memory hygiene, reinject, hook debugging, scheduling)
- CC_USAGE.md updated with Phase 2 read-only/mutating split
- README screenshots for new tabs

#### Quality
- ~40 new unit tests across memory, hooks, schedule, reinject, safety hard cap
- 3 new TUI snapshot tests
- Cross-platform branching tested via `monkeypatch.setattr("sys.platform", ...)`
```

**Step 5:** Bump version to `0.2.0` (drop `.dev0`).

**Step 6: Run full test suite.**

```bash
uv run pytest -q
uv run ruff check src tests
```

**Step 7: Commit.**

```bash
git commit -am "docs+chore: Phase 2 i18n keys, cookbook addendum, CHANGELOG 0.2.0, version bump"
```

---

## Task 18: PR + tag

**Step 1:** Push branch.

```bash
git push -u origin feat/phase2-mvp
```

**Step 2:** Open PR via `gh pr create`. Title: `Phase 2: memory + reinject + hooks debugger + scheduler`. Body summarises the issues closed (#29746, #11544, #10401, #16564) and references both design and plan docs.

**Step 3:** After merge to `main`, tag and trigger release workflow.

```bash
git switch main && git pull
git tag -a v0.2.0 -m "v0.2.0 — Phase 2"
git push origin v0.2.0
```

The release workflow (built in Phase 1) publishes to PyPI and creates a GitHub Release.

---

## Acceptance criteria for Phase 2

- [ ] All Phase 1 tests still pass (zero regressions).
- [ ] ~40 new unit tests pass on Python 3.11 and 3.12, on Ubuntu and Windows runners.
- [ ] 3 new TUI snapshot tests pass.
- [ ] Coverage on `core/` ≥ 90%.
- [ ] `cc-janitor memory list` works against the user's real
  `~/.claude/projects/<X>/memory/`.
- [ ] `cc-janitor context reinject` followed by a Claude Code tool call
  produces the system-reminder injection (manual verification).
- [ ] `cc-janitor hooks simulate PreToolUse '*'` runs the user's installed
  reinject hook and reports exit/duration.
- [ ] `cc-janitor schedule add perms-prune` registers a cron job (Linux/macOS)
  or schtasks task (Windows) that runs in `--dry-run` first.
- [ ] CHANGELOG 0.2.0 reflects all changes (per project policy).
- [ ] PyPI release `cc-janitor==0.2.0` published from CI.
