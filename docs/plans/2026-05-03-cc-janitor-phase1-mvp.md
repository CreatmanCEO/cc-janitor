# cc-janitor Phase 1 MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship a working Python TUI/CLI tool (`cc-janitor`) that lets a user list/preview/delete Claude Code sessions, audit & prune stale permission rules, and inspect CLAUDE.md/memory/skills context cost — with safety primitives (audit log, soft-delete, USER_CONFIRMED gate) baked in from task 1.

**Architecture:** Single Python package, two execution modes — Textual TUI when launched without args, Typer CLI with args. Pure `core/` (no UI) consumed by both. Safety layer always on. State in `~/.cc-janitor/` (cache, trash, backups, audit log).

**Tech Stack:** Python 3.11+, Textual ≥0.80, Typer ≥0.12, tiktoken, rapidjson, pytest, pytest-textual-snapshot, hypothesis, ruff, uv.

**Reference design:** `docs/plans/2026-05-03-cc-janitor-design.md` (sections 3, 4.1, 5, 6, 7).

---

## Conventions used throughout this plan

- **Working dir** = `C:\Users\creat\OneDrive\Рабочий стол\CREATMAN\Tools\cc-janitor` (Windows path; in bash use `~/OneDrive/Рабочий стол/CREATMAN/Tools/cc-janitor`).
- **Python package import name:** `cc_janitor` (underscore — Python rule).
- **PyPI distribution name:** `cc-janitor` (hyphen).
- **Every task** = TDD cycle: write failing test → run it → implement → run again → commit.
- **Commits use Conventional Commits:** `feat:`, `fix:`, `test:`, `chore:`, `docs:`. Co-author trailer required.
- **Run all commands from working dir** unless stated otherwise.

---

## Task 0: Repo bootstrap

**Files:**
- Create: `pyproject.toml`
- Create: `README.md` (placeholder)
- Create: `LICENSE` (MIT)
- Create: `.gitignore`
- Create: `src/cc_janitor/__init__.py`
- Create: `src/cc_janitor/__main__.py` (stub)
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Create directory tree.**

```bash
mkdir -p src/cc_janitor/{core,tui/screens,cli/commands,i18n}
mkdir -p tests/{unit,tui,data/mock-claude-home}
touch src/cc_janitor/__init__.py
touch src/cc_janitor/{core,tui,cli,i18n}/__init__.py
touch src/cc_janitor/tui/screens/__init__.py
touch src/cc_janitor/cli/commands/__init__.py
touch tests/__init__.py
```

**Step 2: Write `pyproject.toml`.**

```toml
[project]
name = "cc-janitor"
version = "0.1.0"
description = "Tidy up your Claude Code environment — sessions, permissions, context, hooks, schedule."
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
authors = [{ name = "Creatman", email = "creatmanick@gmail.com" }]
keywords = ["claude-code", "tui", "cli", "anthropic", "developer-tools"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Environment :: Console :: Curses",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Software Development :: Tools",
]
dependencies = [
    "textual>=0.80",
    "typer>=0.12",
    "tiktoken>=0.7",
    "python-rapidjson>=1.20",
    "tomlkit>=0.13",
    "platformdirs>=4",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-textual-snapshot>=1",
    "pytest-cov>=5",
    "hypothesis>=6",
    "ruff>=0.6",
    "mypy>=1.10",
]

[project.scripts]
cc-janitor = "cc_janitor.__main__:main"

[project.urls]
Homepage = "https://github.com/CreatmanCEO/cc-janitor"
Issues = "https://github.com/CreatmanCEO/cc-janitor/issues"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/cc_janitor"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "RUF"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
```

**Step 3: Stub `__main__.py`.**

```python
# src/cc_janitor/__main__.py
def main() -> None:
    print("cc-janitor 0.1.0 — placeholder, run real entry from later tasks")

if __name__ == "__main__":
    main()
```

**Step 4: Write `.gitignore`.**

```gitignore
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
dist/
build/
*.egg-info/
.coverage
htmlcov/
tests/__snapshots__/.last_run
```

**Step 5: MIT LICENSE.**

Standard MIT text, holder = "Creatman", year = 2026.

**Step 6: Verify install.**

```bash
uv venv
uv pip install -e ".[dev]"
uv run cc-janitor
```

Expected: prints `cc-janitor 0.1.0 — placeholder, run real entry from later tasks`.

**Step 7: Init git and first commit.**

```bash
git init -b main
git add .
git commit -m "chore: bootstrap cc-janitor package skeleton"
```

---

## Task 1: State directories and config

**Files:**
- Create: `src/cc_janitor/core/state.py`
- Create: `tests/unit/test_state.py`

**Goal:** Resolve `~/.cc-janitor/` (overridable via `CC_JANITOR_HOME`), create subdirs lazily, expose typed `Paths` object.

**Step 1: Failing test.**

```python
# tests/unit/test_state.py
import os
from pathlib import Path
from cc_janitor.core.state import get_paths

def test_get_paths_uses_default_home(monkeypatch, tmp_path):
    monkeypatch.delenv("CC_JANITOR_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows
    p = get_paths()
    assert p.home == tmp_path / ".cc-janitor"
    assert p.cache == tmp_path / ".cc-janitor" / "cache"
    assert p.trash == tmp_path / ".cc-janitor" / ".trash"
    assert p.backups == tmp_path / ".cc-janitor" / "backups"
    assert p.audit_log == tmp_path / ".cc-janitor" / "audit.log"

def test_get_paths_respects_override(monkeypatch, tmp_path):
    custom = tmp_path / "custom"
    monkeypatch.setenv("CC_JANITOR_HOME", str(custom))
    p = get_paths()
    assert p.home == custom

def test_ensure_dirs_creates_them(monkeypatch, tmp_path):
    monkeypatch.setenv("CC_JANITOR_HOME", str(tmp_path / "x"))
    p = get_paths()
    p.ensure_dirs()
    for d in (p.cache, p.trash, p.backups, p.hooks_log):
        assert d.is_dir()
```

**Step 2: Run, expect ImportError.**

```bash
uv run pytest tests/unit/test_state.py -v
```

**Step 3: Implement.**

```python
# src/cc_janitor/core/state.py
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

def _user_home() -> Path:
    # Windows: USERPROFILE wins, else HOME
    return Path(os.environ.get("USERPROFILE") or os.environ["HOME"])

@dataclass(frozen=True)
class Paths:
    home: Path

    @property
    def cache(self) -> Path: return self.home / "cache"
    @property
    def trash(self) -> Path: return self.home / ".trash"
    @property
    def backups(self) -> Path: return self.home / "backups"
    @property
    def hooks_log(self) -> Path: return self.home / "hooks-log"
    @property
    def history(self) -> Path: return self.home / "history"
    @property
    def audit_log(self) -> Path: return self.home / "audit.log"
    @property
    def config(self) -> Path: return self.home / "config.toml"

    def ensure_dirs(self) -> None:
        for d in (self.cache, self.trash, self.backups, self.hooks_log, self.history):
            d.mkdir(parents=True, exist_ok=True)

def get_paths() -> Paths:
    override = os.environ.get("CC_JANITOR_HOME")
    home = Path(override) if override else _user_home() / ".cc-janitor"
    return Paths(home=home)
```

**Step 4: Run, expect PASS.**

**Step 5: Commit.**

```bash
git add src/cc_janitor/core/state.py tests/unit/test_state.py
git commit -m "feat(core): state directory resolution"
```

---

## Task 2: Audit log

**Files:**
- Create: `src/cc_janitor/core/audit.py`
- Create: `tests/unit/test_audit.py`

**Goal:** Append-only JSONL audit log; rotates when >10 MB; provides `record(...)` and `read(filter=...)`.

**Step 1: Failing test.**

```python
# tests/unit/test_audit.py
import json
from pathlib import Path
from cc_janitor.core.audit import AuditLog, AuditEntry

def test_record_and_read(tmp_path):
    log = AuditLog(tmp_path / "audit.log")
    log.record(mode="cli", user_confirmed=True, cmd="session list", args=[], exit_code=0)
    entries = list(log.read())
    assert len(entries) == 1
    assert entries[0].cmd == "session list"
    assert entries[0].user_confirmed is True

def test_rotates_when_too_large(tmp_path):
    p = tmp_path / "audit.log"
    log = AuditLog(p, max_bytes=200)
    for i in range(50):
        log.record(mode="cli", user_confirmed=False, cmd=f"x{i}", args=[], exit_code=0)
    rotated = list(tmp_path.glob("audit.log.*"))
    assert len(rotated) >= 1, "Should have rotated at least once"

def test_read_filter_by_cmd(tmp_path):
    log = AuditLog(tmp_path / "audit.log")
    log.record(mode="cli", user_confirmed=True, cmd="session delete", args=["x"], exit_code=0)
    log.record(mode="cli", user_confirmed=True, cmd="perms prune", args=[], exit_code=0)
    rs = list(log.read(cmd_glob="session*"))
    assert len(rs) == 1 and rs[0].cmd == "session delete"
```

**Step 2: Run, expect FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/core/audit.py
from __future__ import annotations
import fnmatch, json, os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

ISO = "%Y-%m-%dT%H:%M:%S%z"

@dataclass
class AuditEntry:
    ts: str
    mode: str            # "cli" | "tui" | "scheduled"
    user_confirmed: bool
    cmd: str
    args: list[str]
    exit_code: int
    session_id: str | None = None
    changed: dict | None = None
    backup_path: str | None = None

class AuditLog:
    def __init__(self, path: Path, max_bytes: int = 10 * 1024 * 1024) -> None:
        self.path = path
        self.max_bytes = max_bytes
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _maybe_rotate(self) -> None:
        if not self.path.exists() or self.path.stat().st_size < self.max_bytes:
            return
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        self.path.rename(self.path.with_name(f"{self.path.name}.{ts}"))

    def record(self, **kwargs) -> AuditEntry:
        kwargs.setdefault("ts", datetime.now(timezone.utc).strftime(ISO))
        entry = AuditEntry(**kwargs)
        self._maybe_rotate()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        return entry

    def read(self, *, cmd_glob: str | None = None) -> Iterator[AuditEntry]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if cmd_glob and not fnmatch.fnmatch(d["cmd"], cmd_glob):
                    continue
                yield AuditEntry(**d)
```

**Step 4: Run, expect PASS.**

**Step 5: Commit.**

```bash
git commit -am "feat(core): audit log with rotation and filter"
```

---

## Task 3: Safety guards (USER_CONFIRMED, soft-delete)

**Files:**
- Create: `src/cc_janitor/core/safety.py`
- Create: `tests/unit/test_safety.py`

**Goal:** `require_confirmed()` raises `NotConfirmedError` when env not set; `soft_delete(path)` moves to trash with timestamp; `restore(trash_id, dst)` reverses it.

**Step 1: Failing test.**

```python
# tests/unit/test_safety.py
import os
import pytest
from pathlib import Path
from cc_janitor.core.safety import (
    require_confirmed, NotConfirmedError, soft_delete, restore_from_trash, list_trash,
)
from cc_janitor.core.state import Paths

def _paths(tmp_path: Path) -> Paths:
    return Paths(home=tmp_path / ".cc-janitor")

def test_require_confirmed_raises_when_missing(monkeypatch):
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    with pytest.raises(NotConfirmedError):
        require_confirmed()

def test_require_confirmed_passes_when_set(monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    require_confirmed()  # no raise

def test_soft_delete_moves_file(tmp_path):
    paths = _paths(tmp_path)
    paths.ensure_dirs()
    src = tmp_path / "victim.txt"
    src.write_text("data")
    trash_id = soft_delete(src, paths=paths)
    assert not src.exists()
    items = list_trash(paths)
    assert any(i.id == trash_id for i in items)

def test_restore_from_trash(tmp_path):
    paths = _paths(tmp_path)
    paths.ensure_dirs()
    src = tmp_path / "victim.txt"
    src.write_text("data")
    trash_id = soft_delete(src, paths=paths)
    restore_from_trash(trash_id, paths=paths)
    assert src.exists() and src.read_text() == "data"
```

**Step 2: Run, expect FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/core/safety.py
from __future__ import annotations
import os, shutil, json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from .state import Paths

class NotConfirmedError(RuntimeError):
    """Raised when a mutation is attempted without CC_JANITOR_USER_CONFIRMED=1."""

def is_confirmed() -> bool:
    return os.environ.get("CC_JANITOR_USER_CONFIRMED") == "1"

def require_confirmed() -> None:
    if not is_confirmed():
        raise NotConfirmedError(
            "This action requires CC_JANITOR_USER_CONFIRMED=1 in environment. "
            "Set it to confirm you authorise this mutation."
        )

@dataclass
class TrashItem:
    id: str
    original_path: str
    deleted_at: str
    trashed_path: Path

def _trash_id(now: datetime) -> str:
    return now.strftime("%Y%m%dT%H%M%S%f")

def soft_delete(src: Path, *, paths: Paths) -> str:
    paths.ensure_dirs()
    now = datetime.now(timezone.utc)
    tid = _trash_id(now)
    bucket = paths.trash / tid
    bucket.mkdir(parents=True)
    dst = bucket / src.name
    if src.is_dir():
        shutil.move(str(src), str(dst))
    else:
        shutil.move(str(src), str(dst))
    meta = {"original_path": str(src), "deleted_at": now.isoformat(), "name": src.name}
    (bucket / "_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return tid

def list_trash(paths: Paths) -> list[TrashItem]:
    if not paths.trash.exists():
        return []
    out: list[TrashItem] = []
    for bucket in sorted(paths.trash.iterdir()):
        meta_p = bucket / "_meta.json"
        if not meta_p.exists():
            continue
        m = json.loads(meta_p.read_text(encoding="utf-8"))
        out.append(TrashItem(
            id=bucket.name,
            original_path=m["original_path"],
            deleted_at=m["deleted_at"],
            trashed_path=bucket / m["name"],
        ))
    return out

def restore_from_trash(trash_id: str, *, paths: Paths) -> Path:
    bucket = paths.trash / trash_id
    meta_p = bucket / "_meta.json"
    if not meta_p.exists():
        raise FileNotFoundError(f"No trash entry: {trash_id}")
    m = json.loads(meta_p.read_text(encoding="utf-8"))
    dst = Path(m["original_path"])
    src = bucket / m["name"]
    shutil.move(str(src), str(dst))
    meta_p.unlink()
    bucket.rmdir()
    return dst
```

**Step 4: Run, expect PASS.**

**Step 5: Commit.**

```bash
git commit -am "feat(core): safety guards — USER_CONFIRMED gate, soft-delete, restore"
```

---

## Task 4: i18n loader

**Files:**
- Create: `src/cc_janitor/i18n/en.toml`
- Create: `src/cc_janitor/i18n/ru.toml`
- Create: `src/cc_janitor/i18n/__init__.py`
- Create: `tests/unit/test_i18n.py`

**Goal:** `t("key.subkey", lang="ru", **vars)` → translated string; falls back to `en` if key missing in target; auto-detects from `LANG`.

**Step 1: Failing test.**

```python
# tests/unit/test_i18n.py
from cc_janitor.i18n import t, set_lang, detect_lang

def test_basic_translation():
    set_lang("en")
    assert t("common.delete") == "Delete"
    set_lang("ru")
    assert t("common.delete") == "Удалить"

def test_format_args():
    set_lang("en")
    assert t("sessions.delete_confirm", count=3) == "Delete 3 session(s)?"

def test_fallback_to_en_when_key_missing(monkeypatch):
    set_lang("ru")
    # Assume ru.toml has 'common' but not 'common.untranslated_key' — we add a fixture key in en only
    # For test, we trust missing-key behaviour returns en value or the key itself
    val = t("common.delete")
    assert val == "Удалить"  # exists in ru

def test_detect_lang_from_env(monkeypatch):
    monkeypatch.setenv("CC_JANITOR_LANG", "ru")
    assert detect_lang() == "ru"
    monkeypatch.delenv("CC_JANITOR_LANG")
    monkeypatch.setenv("LANG", "ru_RU.UTF-8")
    assert detect_lang() == "ru"
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert detect_lang() == "en"
```

**Step 2: Run, expect FAIL.**

**Step 3: Implement minimal TOML files.**

```toml
# src/cc_janitor/i18n/en.toml
[common]
delete = "Delete"
cancel = "Cancel"
confirm = "Confirm"
yes = "Yes"
no = "No"

[sessions]
title = "Sessions"
delete_confirm = "Delete {count} session(s)?"
preview_first_msg = "First user message"

[perms]
title = "Permissions"
stale = "stale"
duplicate = "duplicate"

[context]
title = "Context"
total_per_request = "Total recurring per request"
```

```toml
# src/cc_janitor/i18n/ru.toml
[common]
delete = "Удалить"
cancel = "Отмена"
confirm = "Подтвердить"
yes = "Да"
no = "Нет"

[sessions]
title = "Сессии"
delete_confirm = "Удалить {count} сессий?"
preview_first_msg = "Первое сообщение пользователя"

[perms]
title = "Разрешения"
stale = "устаревшее"
duplicate = "дубликат"

[context]
title = "Контекст"
total_per_request = "Всего на каждый запрос"
```

**Step 4: Implement loader.**

```python
# src/cc_janitor/i18n/__init__.py
from __future__ import annotations
import os
import tomllib
from functools import lru_cache
from pathlib import Path

_HERE = Path(__file__).parent
_current_lang = "en"

@lru_cache(maxsize=8)
def _load(lang: str) -> dict:
    p = _HERE / f"{lang}.toml"
    if not p.exists():
        return {}
    return tomllib.loads(p.read_text(encoding="utf-8"))

def set_lang(lang: str) -> None:
    global _current_lang
    _current_lang = lang

def detect_lang() -> str:
    explicit = os.environ.get("CC_JANITOR_LANG")
    if explicit:
        return "ru" if explicit.lower().startswith("ru") else "en"
    sys_lang = os.environ.get("LANG", "")
    return "ru" if sys_lang.lower().startswith("ru") else "en"

def t(key: str, *, lang: str | None = None, **fmt) -> str:
    lang = lang or _current_lang
    parts = key.split(".")
    for source in (lang, "en"):
        d = _load(source)
        ok = True
        for p in parts:
            if isinstance(d, dict) and p in d:
                d = d[p]
            else:
                ok = False
                break
        if ok and isinstance(d, str):
            return d.format(**fmt) if fmt else d
    return key  # last resort
```

**Step 5: Run, expect PASS. Commit.**

```bash
git add . && git commit -m "feat(i18n): TOML-based translations with fallback"
```

---

## Task 5: Mock Claude home fixture

**Files:**
- Create: `tests/data/mock-claude-home/.claude/settings.json`
- Create: `tests/data/mock-claude-home/.claude/settings.local.json`
- Create: `tests/data/mock-claude-home/.claude/projects/test-proj/abc123.jsonl`
- Create: `tests/data/mock-claude-home/.claude/projects/test-proj/def456.jsonl`
- Create: `tests/conftest.py` (extend with shared fixtures)

**Goal:** Realistic-but-tiny `~/.claude` tree used by every subsequent test.

**Step 1: Create files.** Hand-curated minimal samples — one short session, one with `/compact`, one with realistic Bash tool_input commands for permissions matching tests.

`abc123.jsonl` (3 messages):
```jsonl
{"type":"summary","leafUuid":"u1","sessionId":"abc123"}
{"type":"user","message":{"content":"hi"},"sessionId":"abc123","timestamp":"2026-04-01T10:00:00Z"}
{"type":"assistant","message":{"content":"hello"},"sessionId":"abc123","timestamp":"2026-04-01T10:00:01Z"}
```

`def456.jsonl` (with /compact summary, plus tool_input Bash to support permissions matching):
```jsonl
{"type":"user","message":{"content":"run git status"},"sessionId":"def456","timestamp":"2026-04-15T12:00:00Z"}
{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"git status"}}]},"sessionId":"def456"}
{"type":"user","message":{"content":[{"type":"tool_result","content":"clean"}]},"sessionId":"def456"}
{"type":"summary","summary":"Ran git status, tree clean.","sessionId":"def456","timestamp":"2026-04-15T12:01:00Z"}
{"type":"user","message":{"content":"now npm test"},"sessionId":"def456","timestamp":"2026-04-15T12:02:00Z"}
{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Bash","input":{"command":"npm test"}}]},"sessionId":"def456"}
```

`settings.local.json`:
```json
{
  "permissions": {
    "allow": [
      "Bash(git *)",
      "Bash(git status)",
      "Bash(npm *)",
      "Bash(ssh user@old-host:*)"
    ]
  }
}
```

**Step 2: Add `conftest.py` fixture.**

```python
# tests/conftest.py
from __future__ import annotations
import shutil
from pathlib import Path
import pytest

DATA = Path(__file__).parent / "data" / "mock-claude-home"

@pytest.fixture
def mock_claude_home(tmp_path: Path, monkeypatch) -> Path:
    target = tmp_path / "mock-claude-home"
    shutil.copytree(DATA, target)
    monkeypatch.setenv("HOME", str(target))
    monkeypatch.setenv("USERPROFILE", str(target))  # Windows
    monkeypatch.setenv("CC_JANITOR_HOME", str(target / ".cc-janitor"))
    return target
```

**Step 3: Smoke test the fixture.**

```python
# tests/unit/test_fixture.py
def test_mock_home_loaded(mock_claude_home):
    assert (mock_claude_home / ".claude" / "settings.local.json").exists()
    assert (mock_claude_home / ".claude" / "projects" / "test-proj" / "abc123.jsonl").exists()
```

**Step 4: Run, PASS, commit.**

```bash
git commit -am "test: add mock-claude-home fixture for downstream tests"
```

---

## Task 6: Sessions parser — basic metadata

**Files:**
- Create: `src/cc_janitor/core/sessions.py`
- Create: `tests/unit/test_sessions_parse.py`

**Goal:** Parse a JSONL file → `Session` dataclass with id, project, started_at, last_activity, size, message_count, first/last user message, compactions count.

**Step 1: Test.**

```python
# tests/unit/test_sessions_parse.py
from pathlib import Path
from cc_janitor.core.sessions import parse_session

def test_parse_basic(mock_claude_home):
    p = mock_claude_home / ".claude" / "projects" / "test-proj" / "abc123.jsonl"
    s = parse_session(p, project="test-proj")
    assert s.id == "abc123"
    assert s.project == "test-proj"
    assert s.message_count >= 2
    assert "hi" in s.first_user_msg

def test_parse_counts_compactions(mock_claude_home):
    p = mock_claude_home / ".claude" / "projects" / "test-proj" / "def456.jsonl"
    s = parse_session(p, project="test-proj")
    assert s.compactions == 1
    assert "git status" in s.first_user_msg or "npm test" in s.first_user_msg
```

**Step 2: Run, FAIL.**

**Step 3: Implement.**

```python
# src/cc_janitor/core/sessions.py
from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

@dataclass
class SessionSummary:
    source: Literal["jsonl_compact", "user_indexer_md", "first_msg"]
    text: str
    timestamp: datetime | None = None
    md_path: Path | None = None

@dataclass
class Session:
    id: str
    project: str
    jsonl_path: Path
    started_at: datetime | None
    last_activity: datetime
    size_bytes: int
    message_count: int
    first_user_msg: str
    last_user_msg: str
    compactions: int
    related_dirs: list[Path] = field(default_factory=list)
    summaries: list[SessionSummary] = field(default_factory=list)
    tokens_estimate: int = 0  # filled in later by token_count module

def _iter_jsonl(p: Path) -> Iterator[dict]:
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for blk in content:
            if isinstance(blk, dict) and blk.get("type") == "text":
                return blk.get("text", "")
        return ""
    return ""

def parse_session(jsonl_path: Path, *, project: str) -> Session:
    sid = jsonl_path.stem
    msgs = list(_iter_jsonl(jsonl_path))
    user_msgs = [m for m in msgs if m.get("type") == "user"]
    compact_summaries = [m for m in msgs if m.get("type") == "summary" and "summary" in m]

    def _ts(m):
        ts = m.get("timestamp")
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None

    started_at = _ts(user_msgs[0]) if user_msgs else None
    last_activity = datetime.fromtimestamp(jsonl_path.stat().st_mtime, tz=timezone.utc)

    first_user = ""
    last_user = ""
    if user_msgs:
        first_user = _extract_text(user_msgs[0].get("message", {}).get("content", ""))[:200]
        last_user = _extract_text(user_msgs[-1].get("message", {}).get("content", ""))[:200]

    summaries = [
        SessionSummary(source="jsonl_compact", text=m["summary"], timestamp=_ts(m))
        for m in compact_summaries
    ]
    if first_user:
        summaries.append(SessionSummary(source="first_msg", text=first_user))

    related = []
    for d in (jsonl_path.parent / sid, jsonl_path.parent / "subagents",
              jsonl_path.parent / "tool-results"):
        if d.is_dir():
            related.append(d)

    return Session(
        id=sid,
        project=project,
        jsonl_path=jsonl_path,
        started_at=started_at,
        last_activity=last_activity,
        size_bytes=jsonl_path.stat().st_size,
        message_count=len(msgs),
        first_user_msg=first_user,
        last_user_msg=last_user,
        compactions=len(compact_summaries),
        related_dirs=related,
        summaries=summaries,
    )
```

**Step 4: Run PASS. Commit.**

```bash
git commit -am "feat(core): parse_session — JSONL → Session dataclass"
```

---

## Task 7: Sessions discovery + cache

**Files:**
- Modify: `src/cc_janitor/core/sessions.py` (add `discover_sessions` and cache)
- Create: `tests/unit/test_sessions_discover.py`

**Goal:** Walk `~/.claude/projects/<project>/*.jsonl`, return list of Sessions. Cache to `~/.cc-janitor/cache/sessions.json` with mtime-based invalidation.

**Step 1: Test.**

```python
# tests/unit/test_sessions_discover.py
from cc_janitor.core.sessions import discover_sessions
from cc_janitor.core.state import get_paths

def test_discover_returns_sessions(mock_claude_home):
    sessions = discover_sessions()
    assert len(sessions) >= 2
    ids = {s.id for s in sessions}
    assert {"abc123", "def456"} <= ids

def test_discover_respects_project_filter(mock_claude_home):
    sessions = discover_sessions(project="test-proj")
    assert all(s.project == "test-proj" for s in sessions)

def test_cache_avoids_re_parsing(mock_claude_home, monkeypatch):
    discover_sessions()  # warm
    # corrupt the file but keep mtime — cache should still serve
    p = mock_claude_home / ".claude" / "projects" / "test-proj" / "abc123.jsonl"
    original_mtime = p.stat().st_mtime
    p.write_text("garbage")
    import os; os.utime(p, (original_mtime, original_mtime))
    cached = discover_sessions()
    assert any(s.id == "abc123" and "hi" in s.first_user_msg for s in cached)
```

**Step 2: Run, FAIL.**

**Step 3: Append to `sessions.py`.**

```python
# additions to sessions.py
import json
from .state import get_paths

def _claude_projects_root() -> Path:
    paths = get_paths()
    home = paths.home.parent  # ~
    return home / ".claude" / "projects"

def _cache_path() -> Path:
    return get_paths().cache / "sessions.json"

def _serialize(s: Session) -> dict:
    return {
        "id": s.id, "project": s.project, "jsonl_path": str(s.jsonl_path),
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "last_activity": s.last_activity.isoformat(),
        "size_bytes": s.size_bytes, "message_count": s.message_count,
        "first_user_msg": s.first_user_msg, "last_user_msg": s.last_user_msg,
        "compactions": s.compactions, "tokens_estimate": s.tokens_estimate,
        "mtime": s.jsonl_path.stat().st_mtime if s.jsonl_path.exists() else 0,
    }

def _deserialize(d: dict) -> Session | None:
    p = Path(d["jsonl_path"])
    if not p.exists() or p.stat().st_mtime != d.get("mtime"):
        return None  # cache invalid for this entry
    return Session(
        id=d["id"], project=d["project"], jsonl_path=p,
        started_at=datetime.fromisoformat(d["started_at"]) if d["started_at"] else None,
        last_activity=datetime.fromisoformat(d["last_activity"]),
        size_bytes=d["size_bytes"], message_count=d["message_count"],
        first_user_msg=d["first_user_msg"], last_user_msg=d["last_user_msg"],
        compactions=d["compactions"], tokens_estimate=d.get("tokens_estimate", 0),
    )

def discover_sessions(*, project: str | None = None, refresh: bool = False) -> list[Session]:
    paths = get_paths()
    paths.ensure_dirs()
    cache_p = _cache_path()
    cache: dict[str, dict] = {}
    if cache_p.exists() and not refresh:
        try:
            cache = {e["id"]: e for e in json.loads(cache_p.read_text(encoding="utf-8"))}
        except (json.JSONDecodeError, KeyError):
            cache = {}

    out: list[Session] = []
    root = _claude_projects_root()
    if not root.exists():
        return out
    for proj_dir in root.iterdir():
        if not proj_dir.is_dir():
            continue
        if project and proj_dir.name != project:
            continue
        for jsonl_p in proj_dir.glob("*.jsonl"):
            sid = jsonl_p.stem
            cached_entry = cache.get(sid)
            session = None
            if cached_entry:
                session = _deserialize(cached_entry)
            if session is None:
                session = parse_session(jsonl_p, project=proj_dir.name)
            out.append(session)

    # write cache back
    cache_p.write_text(
        json.dumps([_serialize(s) for s in out], ensure_ascii=False),
        encoding="utf-8",
    )
    return out
```

**Step 4: Run PASS. Commit.**

```bash
git commit -am "feat(core): discover_sessions with mtime-based cache"
```

---

## Task 8: Token cost estimator

**Files:**
- Create: `src/cc_janitor/core/tokens.py`
- Create: `tests/unit/test_tokens.py`

**Goal:** Wrap tiktoken `cl100k_base`, expose `count_tokens(text)` and `count_file_tokens(path)`.

**Step 1: Test.**

```python
# tests/unit/test_tokens.py
from cc_janitor.core.tokens import count_tokens, count_file_tokens

def test_count_tokens_basic():
    assert count_tokens("hello world") > 0
    assert count_tokens("") == 0

def test_count_file_tokens(tmp_path):
    f = tmp_path / "x.md"
    f.write_text("# Title\n\nSome words here.\n", encoding="utf-8")
    assert count_file_tokens(f) > 0
```

**Step 2: Run, FAIL. Implement.**

```python
# src/cc_janitor/core/tokens.py
from __future__ import annotations
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=1)
def _enc():
    import tiktoken
    return tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_enc().encode(text))

def count_file_tokens(p: Path) -> int:
    if not p.exists():
        return 0
    return count_tokens(p.read_text(encoding="utf-8", errors="replace"))
```

**Step 3: Run PASS. Commit.**

```bash
git commit -am "feat(core): tiktoken-based token counter"
```

---

## Task 9: Session summary discovery (linking user-indexer markdown)

**Files:**
- Modify: `src/cc_janitor/core/sessions.py` — add `enrich_with_indexer_summaries(sessions)`
- Modify: `tests/data/mock-claude-home/` — add a `Conversations/claude-code/2026-04-15_def456_test.md`
- Create: `tests/unit/test_sessions_summaries.py`

**Goal:** If a sibling directory `Conversations/claude-code/` exists (from user's `index-session.sh` hook) and has files matching `*_<session-id>*.md`, attach as `SessionSummary(source="user_indexer_md")`.

**Step 1: Add fixture file `tests/data/mock-claude-home/Conversations/claude-code/2026-04-15_test-summary_def456.md`** with YAML frontmatter and a paragraph.

**Step 2: Test.**

```python
def test_enrich_with_indexer_summaries(mock_claude_home):
    from cc_janitor.core.sessions import discover_sessions, enrich_with_indexer_summaries
    sessions = discover_sessions()
    enriched = enrich_with_indexer_summaries(
        sessions,
        indexer_root=mock_claude_home / "Conversations" / "claude-code",
    )
    target = next((s for s in enriched if s.id == "def456"), None)
    assert target is not None
    md_summaries = [x for x in target.summaries if x.source == "user_indexer_md"]
    assert len(md_summaries) == 1
```

**Step 3: Implement.**

```python
def enrich_with_indexer_summaries(sessions: list[Session], *, indexer_root: Path) -> list[Session]:
    if not indexer_root.exists():
        return sessions
    md_files = list(indexer_root.glob("*.md"))
    for s in sessions:
        for md in md_files:
            # filenames look like: 2026-04-15_some-title_<sid>.md or _<sid_short>.md
            if s.id in md.stem or s.id[:8] in md.stem:
                s.summaries.append(SessionSummary(
                    source="user_indexer_md",
                    text=md.read_text(encoding="utf-8", errors="replace")[:1000],
                    md_path=md,
                ))
                break
    return sessions
```

**Step 4: PASS, commit.**

---

## Task 10: Session deletion (soft + related dirs)

**Files:**
- Modify: `src/cc_janitor/core/sessions.py` — add `delete_session(session)`
- Create: `tests/unit/test_sessions_delete.py`

**Goal:** Move JSONL + related subdirs to trash atomically; refuse if not confirmed.

**Step 1: Test.**

```python
def test_delete_session_requires_confirmed(mock_claude_home, monkeypatch):
    from cc_janitor.core.sessions import discover_sessions, delete_session
    from cc_janitor.core.safety import NotConfirmedError
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    s = discover_sessions()[0]
    import pytest
    with pytest.raises(NotConfirmedError):
        delete_session(s)

def test_delete_session_moves_to_trash(mock_claude_home, monkeypatch):
    from cc_janitor.core.sessions import discover_sessions, delete_session
    from cc_janitor.core.safety import list_trash
    from cc_janitor.core.state import get_paths
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    sessions = discover_sessions()
    s = next(s for s in sessions if s.id == "abc123")
    trash_id = delete_session(s)
    assert not s.jsonl_path.exists()
    assert any(i.id == trash_id for i in list_trash(get_paths()))
```

**Step 2: FAIL. Implement.**

```python
from .safety import require_confirmed, soft_delete
from .state import get_paths

def delete_session(s: Session) -> str:
    require_confirmed()
    paths = get_paths()
    paths.ensure_dirs()
    # bundle: move whole jsonl+related under same trash bucket via single soft_delete on a temp dir
    import tempfile, shutil
    with tempfile.TemporaryDirectory(prefix="ccj-bundle-", dir=paths.home) as td:
        bundle = Path(td) / s.id
        bundle.mkdir()
        shutil.move(str(s.jsonl_path), str(bundle / s.jsonl_path.name))
        for d in s.related_dirs:
            if d.exists():
                shutil.move(str(d), str(bundle / d.name))
        # now soft-delete the bundle (renames bundle into trash bucket)
        return soft_delete(bundle, paths=paths)
```

**Step 3: PASS, commit.**

```bash
git commit -am "feat(core): delete_session — atomic soft-delete with related dirs"
```

---

## Task 11: Permission sources discovery

**Files:**
- Create: `src/cc_janitor/core/permissions.py`
- Create: `tests/unit/test_perms_sources.py`

**Goal:** Walk the 5 settings.json layers + `~/.claude.json` `approvedTools`, parse rules, attribute each to its source.

**Step 1: Add fixture** — `tests/data/mock-claude-home/.claude/settings.json` (global), `.claude/projects/test-proj/.claude/settings.json` (per-project) with sample rules. Also add `tests/data/mock-claude-home/.claude.json` with `approvedTools` array.

**Step 2: Test.**

```python
# tests/unit/test_perms_sources.py
from cc_janitor.core.permissions import discover_rules, PermSource

def test_discover_rules_finds_user_local(mock_claude_home):
    rules = discover_rules()
    sources = {r.source.scope for r in rules}
    assert "user-local" in sources
    patterns = {r.pattern for r in rules}
    assert "git *" in patterns

def test_discover_rules_distinguishes_scopes(mock_claude_home):
    rules = discover_rules()
    by_scope = {}
    for r in rules:
        by_scope.setdefault(r.source.scope, []).append(r)
    assert "user-local" in by_scope
```

**Step 3: Implement.**

```python
# src/cc_janitor/core/permissions.py
from __future__ import annotations
import json, re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator, Literal
from .state import get_paths

Scope = Literal["user", "user-local", "project", "project-local", "managed", "approved-tools"]

@dataclass(frozen=True)
class PermSource:
    path: Path
    scope: Scope

@dataclass
class PermRule:
    tool: str           # "Bash", "Edit", "Read"
    pattern: str        # rule body, e.g. "git *" or "" if pattern-less
    decision: Literal["allow", "deny", "ask"]
    source: PermSource
    raw: str = ""       # original rule string e.g. "Bash(git *)"
    last_matched_at: datetime | None = None
    match_count_30d: int = 0
    match_count_90d: int = 0
    stale: bool = False

_RULE_RE = re.compile(r"^([A-Za-z]+)(?:\(([^)]*)\))?$")

def parse_rule(raw: str, *, decision="allow", source: PermSource) -> PermRule | None:
    m = _RULE_RE.match(raw.strip())
    if not m:
        return None
    return PermRule(tool=m.group(1), pattern=(m.group(2) or "").strip(),
                    decision=decision, source=source, raw=raw)

def _user_home() -> Path:
    import os
    return Path(os.environ.get("USERPROFILE") or os.environ["HOME"])

def _settings_files() -> list[tuple[Path, Scope]]:
    home = _user_home()
    out: list[tuple[Path, Scope]] = []
    out.append((home / ".claude" / "settings.json", "user"))
    out.append((home / ".claude" / "settings.local.json", "user-local"))
    # project-level: walk ~/.claude/projects/*/.claude/settings*.json — Claude Code's location
    proj_root = home / ".claude" / "projects"
    if proj_root.exists():
        for proj in proj_root.iterdir():
            sd = proj / ".claude"
            out.append((sd / "settings.json", "project"))
            out.append((sd / "settings.local.json", "project-local"))
    return out

def _read_json(p: Path) -> dict | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

def discover_rules() -> list[PermRule]:
    out: list[PermRule] = []
    for path, scope in _settings_files():
        d = _read_json(path)
        if not d:
            continue
        perms = (d or {}).get("permissions", {}) or {}
        src = PermSource(path=path, scope=scope)
        for kind in ("allow", "deny", "ask"):
            for raw in perms.get(kind, []) or []:
                r = parse_rule(raw, decision=kind, source=src)
                if r:
                    out.append(r)
    # ~/.claude.json approvedTools
    cj = _user_home() / ".claude.json"
    d = _read_json(cj)
    if d:
        src = PermSource(path=cj, scope="approved-tools")
        for raw in (d.get("approvedTools") or []):
            r = parse_rule(raw, decision="allow", source=src)
            if r:
                out.append(r)
    return out
```

**Step 4: PASS, commit.**

```bash
git commit -am "feat(core): permissions — discover rules across all settings sources"
```

---

## Task 12: Permission usage analysis (transcript scan)

**Files:**
- Modify: `src/cc_janitor/core/permissions.py` — add `analyze_usage(rules, sessions)`
- Create: `tests/unit/test_perms_usage.py`

**Goal:** Scan JSONL transcripts for `tool_use` blocks with `name=Bash/Edit/...`, match each against rules using fnmatch, populate `last_matched_at` / `match_count_*` / `stale`.

**Step 1: Test.**

```python
def test_analyze_usage_marks_stale(mock_claude_home, monkeypatch):
    from cc_janitor.core.permissions import discover_rules, analyze_usage
    from cc_janitor.core.sessions import discover_sessions
    rules = discover_rules()
    sessions = discover_sessions()
    enriched = analyze_usage(rules, sessions, stale_after_days=90)
    by_pat = {r.pattern: r for r in enriched if r.tool == "Bash"}
    # "git *" should match the def456 git status command
    assert by_pat["git *"].match_count_90d >= 1
    # "ssh user@old-host:*" never matches → stale
    assert by_pat["ssh user@old-host:*"].stale is True
```

**Step 2: FAIL. Implement.**

```python
import fnmatch
from datetime import datetime, timedelta, timezone

def _iter_tool_uses(jsonl: Path):
    import json
    with jsonl.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                m = json.loads(line)
            except json.JSONDecodeError:
                continue
            content = (m.get("message") or {}).get("content")
            ts = m.get("timestamp")
            try:
                t = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
            except Exception:
                t = None
            if isinstance(content, list):
                for blk in content:
                    if isinstance(blk, dict) and blk.get("type") == "tool_use":
                        yield blk.get("name"), blk.get("input") or {}, t

def _match_command(pattern: str, command: str) -> bool:
    # pattern like "git *" — fnmatch translates to glob.
    # empty pattern means "any" within tool, equivalent to "*"
    if pattern == "":
        return True
    return fnmatch.fnmatchcase(command, pattern)

def analyze_usage(rules: list[PermRule], sessions, *, stale_after_days: int = 90) -> list[PermRule]:
    now = datetime.now(timezone.utc)
    cutoff_30 = now - timedelta(days=30)
    cutoff_90 = now - timedelta(days=stale_after_days)
    for s in sessions:
        for tool_name, inp, ts in _iter_tool_uses(s.jsonl_path):
            target = inp.get("command") or inp.get("file_path") or ""
            if not isinstance(target, str):
                continue
            for r in rules:
                if r.tool != tool_name:
                    continue
                if not _match_command(r.pattern, target):
                    continue
                if ts:
                    if r.last_matched_at is None or ts > r.last_matched_at:
                        r.last_matched_at = ts
                    if ts >= cutoff_30:
                        r.match_count_30d += 1
                    if ts >= cutoff_90:
                        r.match_count_90d += 1
    for r in rules:
        r.stale = r.match_count_90d == 0
    return rules
```

**Step 3: PASS, commit.**

```bash
git commit -am "feat(core): permissions — usage analysis via transcript scan"
```

---

## Task 13: Permission dedupe detection

**Files:**
- Modify: `src/cc_janitor/core/permissions.py` — add `find_duplicates(rules)`
- Create: `tests/unit/test_perms_dedupe.py`

**Goal:** Detect 4 dup kinds (subsumed, exact, conflict, empty), return `list[PermDup]` with suggestions.

**Step 1: Test.**

```python
def test_find_subsumed():
    from cc_janitor.core.permissions import (
        PermRule, PermSource, find_duplicates,
    )
    src = PermSource(path=__import__("pathlib").Path("/x"), scope="user-local")
    rs = [
        PermRule(tool="Bash", pattern="git *", decision="allow", source=src, raw="Bash(git *)"),
        PermRule(tool="Bash", pattern="git status", decision="allow", source=src, raw="Bash(git status)"),
    ]
    dups = find_duplicates(rs)
    kinds = [d.kind for d in dups]
    assert "subsumed" in kinds

def test_find_exact_duplicate():
    from cc_janitor.core.permissions import PermRule, PermSource, find_duplicates
    p = __import__("pathlib").Path
    a = PermSource(path=p("/a"), scope="user-local")
    b = PermSource(path=p("/b"), scope="project-local")
    rs = [
        PermRule(tool="Bash", pattern="npm *", decision="allow", source=a, raw="Bash(npm *)"),
        PermRule(tool="Bash", pattern="npm *", decision="allow", source=b, raw="Bash(npm *)"),
    ]
    dups = find_duplicates(rs)
    assert any(d.kind == "exact" for d in dups)

def test_empty_pattern_flagged():
    from cc_janitor.core.permissions import PermRule, PermSource, find_duplicates
    p = __import__("pathlib").Path
    src = PermSource(path=p("/a"), scope="user-local")
    rs = [PermRule(tool="Bash", pattern="", decision="allow", source=src, raw="Bash()")]
    dups = find_duplicates(rs)
    assert any(d.kind == "empty" for d in dups)
```

**Step 2: FAIL. Implement.**

```python
@dataclass
class PermDup:
    kind: Literal["subsumed", "exact", "conflict", "empty"]
    rules: list[PermRule]
    suggestion: str

def _pattern_subsumes(broad: str, narrow: str) -> bool:
    """Returns True if `broad` matches `narrow` as a literal."""
    if broad == narrow or broad == "*":
        return False  # equal = exact, not subsumed
    return fnmatch.fnmatchcase(narrow, broad)

def find_duplicates(rules: list[PermRule]) -> list[PermDup]:
    out: list[PermDup] = []
    # empty
    for r in rules:
        if r.tool and not r.pattern.strip() and r.raw.endswith("()"):
            out.append(PermDup(kind="empty", rules=[r],
                               suggestion=f"Remove empty rule {r.raw} from {r.source.path}"))
    # group by tool
    by_tool: dict[str, list[PermRule]] = {}
    for r in rules:
        by_tool.setdefault(r.tool, []).append(r)
    for tool, group in by_tool.items():
        # exact duplicates
        seen: dict[tuple[str, str], list[PermRule]] = {}
        for r in group:
            key = (r.pattern, r.decision)
            seen.setdefault(key, []).append(r)
        for key, rs in seen.items():
            if len(rs) > 1:
                out.append(PermDup(kind="exact", rules=rs,
                                   suggestion=f"Same rule ({tool}({key[0]}), {key[1]}) appears in {len(rs)} sources — keep one."))
        # subsumed: same decision, broad subsumes narrow
        for r1 in group:
            if r1.decision != "allow":
                continue
            for r2 in group:
                if r1 is r2 or r2.decision != "allow":
                    continue
                if r1.pattern and r2.pattern and _pattern_subsumes(r1.pattern, r2.pattern):
                    out.append(PermDup(kind="subsumed", rules=[r1, r2],
                                       suggestion=f"{tool}({r1.pattern}) already covers {tool}({r2.pattern})"))
        # conflict: allow + deny on overlapping patterns
        allows = [r for r in group if r.decision == "allow"]
        denies = [r for r in group if r.decision == "deny"]
        for a in allows:
            for d in denies:
                if a.pattern == d.pattern or _pattern_subsumes(a.pattern, d.pattern) or _pattern_subsumes(d.pattern, a.pattern):
                    out.append(PermDup(kind="conflict", rules=[a, d],
                                       suggestion="Allow vs deny overlap — review manually, do not auto-fix."))
    return out
```

**Step 3: PASS, commit.**

```bash
git commit -am "feat(core): permission dedupe detection (subsumed/exact/conflict/empty)"
```

---

## Task 14: Permission write-back with backup

**Files:**
- Modify: `src/cc_janitor/core/permissions.py` — add `remove_rule(rule)`, `add_rule(...)`, internal `_backup_and_write(...)`
- Create: `tests/unit/test_perms_write.py`

**Goal:** Mutate settings.json files preserving JSON formatting (use `tomlkit`-like for JSON via `json.loads` + custom dumps that preserve indentation we read from original); always backup first.

**Step 1: Test.**

```python
def test_remove_rule_writes_backup_and_removes(mock_claude_home, monkeypatch):
    from cc_janitor.core.permissions import discover_rules, remove_rule
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    rules = discover_rules()
    target = next(r for r in rules if r.pattern == "ssh user@old-host:*")
    remove_rule(target)
    new_rules = discover_rules()
    assert all(r.pattern != "ssh user@old-host:*" for r in new_rules)
    # backup created
    from cc_janitor.core.state import get_paths
    paths = get_paths()
    backups = list(paths.backups.rglob("*.json"))
    assert len(backups) >= 1

def test_remove_rule_requires_confirmed(mock_claude_home, monkeypatch):
    from cc_janitor.core.permissions import discover_rules, remove_rule
    from cc_janitor.core.safety import NotConfirmedError
    import pytest
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    rules = discover_rules()
    with pytest.raises(NotConfirmedError):
        remove_rule(rules[0])
```

**Step 2: FAIL. Implement.**

```python
import hashlib, shutil
from .safety import require_confirmed
from .state import get_paths

def _backup(path: Path) -> Path:
    paths = get_paths()
    paths.ensure_dirs()
    h = hashlib.sha1(str(path).encode()).hexdigest()[:12]
    bucket = paths.backups / h
    bucket.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    dst = bucket / f"{path.name}.{ts}.bak"
    shutil.copy2(path, dst)
    return dst

def _read_settings(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

def _write_settings(path: Path, data: dict) -> None:
    # Preserve 2-space indent — Claude Code's settings.json convention.
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def remove_rule(rule: PermRule) -> None:
    require_confirmed()
    path = rule.source.path
    if not path.exists():
        raise FileNotFoundError(path)
    _backup(path)

    if rule.source.scope == "approved-tools":
        d = _read_settings(path)
        arr = d.get("approvedTools") or []
        d["approvedTools"] = [x for x in arr if x != rule.raw]
        _write_settings(path, d)
        return

    d = _read_settings(path)
    perms = d.setdefault("permissions", {})
    arr = perms.get(rule.decision) or []
    perms[rule.decision] = [x for x in arr if x != rule.raw]
    _write_settings(path, d)

def add_rule(raw: str, *, scope: Scope, decision: str = "allow") -> None:
    require_confirmed()
    # find target file from scope
    candidates = [(p, s) for p, s in _settings_files() if s == scope]
    if not candidates:
        raise ValueError(f"No file for scope {scope}")
    path, _ = candidates[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    d = _read_settings(path)
    if scope == "approved-tools":
        d.setdefault("approvedTools", []).append(raw)
    else:
        d.setdefault("permissions", {}).setdefault(decision, []).append(raw)
    _backup(path) if path.exists() else None
    _write_settings(path, d)
```

**Step 3: PASS, commit.**

```bash
git commit -am "feat(core): permission write-back with timestamped backups"
```

---

## Task 15: Context inspector — CLAUDE.md hierarchy

**Files:**
- Create: `src/cc_janitor/core/context.py`
- Create: `tests/unit/test_context_claudemd.py`

**Goal:** Walk from cwd up + `~/.claude/CLAUDE.md`, return ordered list with size/tokens.

**Step 1: Add fixture** — `tests/data/mock-claude-home/.claude/CLAUDE.md` (some text), `tests/data/mock-claude-home/myproject/CLAUDE.md`, `tests/data/mock-claude-home/myproject/sub/`.

**Step 2: Test.**

```python
def test_claude_md_hierarchy(mock_claude_home):
    from cc_janitor.core.context import claude_md_hierarchy
    sub = mock_claude_home / "myproject" / "sub"
    sub.mkdir(parents=True, exist_ok=True)
    files = claude_md_hierarchy(starting_from=sub)
    paths = [f.path for f in files]
    assert mock_claude_home / "myproject" / "CLAUDE.md" in paths
    assert mock_claude_home / ".claude" / "CLAUDE.md" in paths
    assert all(f.size_bytes >= 0 for f in files)
```

**Step 3: Implement.**

```python
# src/cc_janitor/core/context.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from .tokens import count_file_tokens
import os

@dataclass
class ContextFile:
    path: Path
    size_bytes: int
    tokens: int
    kind: str  # "claude_md" | "memory" | "skill" | "permissions"

def _user_home() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.environ["HOME"])

def claude_md_hierarchy(*, starting_from: Path) -> list[ContextFile]:
    out: list[ContextFile] = []
    seen: set[Path] = set()

    def add(p: Path) -> None:
        if p.exists() and p not in seen:
            seen.add(p)
            out.append(ContextFile(
                path=p, size_bytes=p.stat().st_size,
                tokens=count_file_tokens(p), kind="claude_md",
            ))

    cur = starting_from.resolve()
    stop = cur.anchor
    while True:
        add(cur / "CLAUDE.md")
        if str(cur) == stop or cur.parent == cur:
            break
        cur = cur.parent

    add(_user_home() / ".claude" / "CLAUDE.md")
    return out
```

**Step 4: PASS, commit.**

```bash
git commit -am "feat(core): CLAUDE.md hierarchy walker with token counts"
```

---

## Task 16: Context inspector — memory + skills + total

**Files:**
- Modify: `src/cc_janitor/core/context.py` — `memory_files(project_dir)`, `enabled_skills()`, `context_cost(project_dir)`
- Create: `tests/unit/test_context_total.py`

**Goal:** Aggregate CLAUDE.md + memory + skills into a `ContextCost` summary with totals.

**Step 1: Add fixture** — `tests/data/mock-claude-home/.claude/projects/test-proj/memory/MEMORY.md` and one referenced `*.md`.

**Step 2: Test.**

```python
def test_context_cost(mock_claude_home):
    from cc_janitor.core.context import context_cost
    project = mock_claude_home / "myproject"
    project.mkdir(exist_ok=True)
    cost = context_cost(starting_from=project, claude_project_dir="test-proj")
    assert cost.total_bytes > 0
    assert cost.total_tokens > 0
    assert any(f.kind == "claude_md" for f in cost.files)
    assert any(f.kind == "memory" for f in cost.files)
```

**Step 3: Implement (skip skills depth — listing only by file size for now).**

```python
@dataclass
class ContextCost:
    files: list[ContextFile]
    total_bytes: int
    total_tokens: int

def memory_files(*, claude_project_dir: str) -> list[ContextFile]:
    home = _user_home()
    mem_dir = home / ".claude" / "projects" / claude_project_dir / "memory"
    if not mem_dir.exists():
        return []
    out = []
    for p in mem_dir.glob("*.md"):
        out.append(ContextFile(path=p, size_bytes=p.stat().st_size,
                               tokens=count_file_tokens(p), kind="memory"))
    return out

def enabled_skills() -> list[ContextFile]:
    home = _user_home()
    out: list[ContextFile] = []
    skills_root = home / ".claude" / "skills"
    if skills_root.exists():
        for skill_md in skills_root.rglob("SKILL.md"):
            out.append(ContextFile(
                path=skill_md, size_bytes=skill_md.stat().st_size,
                tokens=count_file_tokens(skill_md), kind="skill"))
    return out

def context_cost(*, starting_from: Path, claude_project_dir: str | None = None) -> ContextCost:
    files: list[ContextFile] = []
    files += claude_md_hierarchy(starting_from=starting_from)
    if claude_project_dir:
        files += memory_files(claude_project_dir=claude_project_dir)
    files += enabled_skills()
    return ContextCost(
        files=files,
        total_bytes=sum(f.size_bytes for f in files),
        total_tokens=sum(f.tokens for f in files),
    )
```

**Step 4: PASS, commit.**

```bash
git commit -am "feat(core): context_cost aggregator (CLAUDE.md + memory + skills)"
```

---

## Task 17: CLI skeleton

**Files:**
- Create: `src/cc_janitor/cli/__init__.py` (Typer app)
- Modify: `src/cc_janitor/__main__.py` (route to TUI vs CLI)
- Create: `tests/unit/test_cli_skeleton.py`

**Goal:** `cc-janitor --version` and `cc-janitor --help` work; with no args, would launch TUI (deferred to Task 24).

**Step 1: Test.**

```python
# tests/unit/test_cli_skeleton.py
from typer.testing import CliRunner
from cc_janitor.cli import app

def test_version():
    r = CliRunner().invoke(app, ["--version"])
    assert r.exit_code == 0
    assert "0.1.0" in r.stdout
```

**Step 2: FAIL. Implement.**

```python
# src/cc_janitor/cli/__init__.py
from __future__ import annotations
import typer
from .. import __version__ if False else None  # placeholder
__VERSION__ = "0.1.0"

app = typer.Typer(no_args_is_help=False, help="cc-janitor — Tidy Claude Code")

def _version_cb(value: bool):
    if value:
        typer.echo(f"cc-janitor {__VERSION__}")
        raise typer.Exit()

@app.callback()
def root(
    version: bool = typer.Option(False, "--version", callback=_version_cb, is_eager=True),
    lang: str = typer.Option(None, "--lang", help="UI language: en|ru"),
):
    if lang:
        from ..i18n import set_lang
        set_lang(lang)
```

```python
# src/cc_janitor/__main__.py
from __future__ import annotations
import sys

def main() -> None:
    if len(sys.argv) > 1:
        from .cli import app
        app()
    else:
        # TUI path — deferred to Task 24
        from .cli import app
        app(["--help"])

if __name__ == "__main__":
    main()
```

**Step 3: PASS, commit.**

```bash
git commit -am "feat(cli): typer skeleton with --version and --lang"
```

---

## Task 18: CLI session subcommands

**Files:**
- Create: `src/cc_janitor/cli/commands/session.py`
- Modify: `src/cc_janitor/cli/__init__.py` — register `app.add_typer(session_app, name="session")`
- Create: `tests/unit/test_cli_session.py`

**Subcommands implemented:** `list`, `show <id>`, `summary <id>`, `delete <id>...`, `prune --older-than <days>`, `search <query>`.

**Step 1: Test.**

```python
def test_session_list(mock_claude_home):
    from typer.testing import CliRunner
    from cc_janitor.cli import app
    r = CliRunner().invoke(app, ["session", "list"])
    assert r.exit_code == 0
    assert "abc123" in r.stdout
    assert "def456" in r.stdout

def test_session_summary(mock_claude_home):
    from typer.testing import CliRunner
    from cc_janitor.cli import app
    r = CliRunner().invoke(app, ["session", "summary", "def456"])
    assert r.exit_code == 0
    assert "git status" in r.stdout or "tree clean" in r.stdout

def test_session_delete_blocked_without_confirm(mock_claude_home, monkeypatch):
    monkeypatch.delenv("CC_JANITOR_USER_CONFIRMED", raising=False)
    from typer.testing import CliRunner
    from cc_janitor.cli import app
    r = CliRunner().invoke(app, ["session", "delete", "abc123"])
    assert r.exit_code != 0
```

**Step 2: FAIL. Implement.**

```python
# src/cc_janitor/cli/commands/session.py
from __future__ import annotations
import typer
from ...core.sessions import discover_sessions, delete_session, enrich_with_indexer_summaries
from ...core.safety import NotConfirmedError

session_app = typer.Typer(help="Manage Claude Code sessions")

@session_app.command("list")
def list_(project: str = typer.Option(None, "--project")):
    rows = discover_sessions(project=project)
    for s in sorted(rows, key=lambda x: x.last_activity, reverse=True):
        msg = (s.first_user_msg or "").replace("\n", " ")[:60]
        typer.echo(f"{s.id}  {s.project:24}  {s.size_bytes:>10}b  {s.message_count:>4}msg  {msg}")

@session_app.command("show")
def show(session_id: str):
    s = next((x for x in discover_sessions() if x.id == session_id), None)
    if not s:
        raise typer.BadParameter(f"No session {session_id}")
    typer.echo(f"ID: {s.id}\nProject: {s.project}\nMessages: {s.message_count}\nCompactions: {s.compactions}")
    typer.echo(f"First user msg:\n  {s.first_user_msg}")

@session_app.command("summary")
def summary(session_id: str):
    sessions = enrich_with_indexer_summaries(
        discover_sessions(),
        indexer_root=__import__("pathlib").Path.home() / "OneDrive" / "Рабочий стол" / "CREATMAN" / "Conversations" / "claude-code",
    )
    s = next((x for x in sessions if x.id == session_id), None)
    if not s:
        raise typer.BadParameter(f"No session {session_id}")
    for sm in s.summaries:
        typer.echo(f"\n[{sm.source}] {(sm.timestamp.isoformat() if sm.timestamp else '')}")
        typer.echo(sm.text[:500])

@session_app.command("delete")
def delete(session_ids: list[str]):
    sessions = {s.id: s for s in discover_sessions()}
    failures = 0
    for sid in session_ids:
        if sid not in sessions:
            typer.echo(f"skip {sid}: not found", err=True)
            failures += 1
            continue
        try:
            tid = delete_session(sessions[sid])
            typer.echo(f"deleted {sid} → trash:{tid}")
        except NotConfirmedError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(code=2)
    if failures:
        raise typer.Exit(code=1)

@session_app.command("prune")
def prune(older_than: str = typer.Option("90d", "--older-than"),
          dry_run: bool = typer.Option(False, "--dry-run")):
    from datetime import datetime, timedelta, timezone
    days = int(older_than.rstrip("d"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = [s for s in discover_sessions() if s.last_activity < cutoff]
    typer.echo(f"{len(rows)} sessions older than {older_than}")
    for s in rows:
        typer.echo(f"  {s.id}  {s.last_activity.date()}  {s.first_user_msg[:50]}")
    if dry_run:
        return
    for s in rows:
        try:
            delete_session(s)
        except NotConfirmedError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(code=2)

@session_app.command("search")
def search(query: str):
    import re
    pat = re.compile(re.escape(query), re.IGNORECASE)
    for s in discover_sessions():
        if pat.search(s.first_user_msg) or pat.search(s.last_user_msg):
            typer.echo(f"{s.id}  {s.first_user_msg[:80]}")
```

Register in `cli/__init__.py`:

```python
from .commands.session import session_app
app.add_typer(session_app, name="session")
```

**Step 3: PASS, commit.**

```bash
git commit -am "feat(cli): session subcommands (list/show/summary/delete/prune/search)"
```

---

## Task 19: CLI permissions subcommands

**Files:**
- Create: `src/cc_janitor/cli/commands/perms.py`
- Modify: `cli/__init__.py` — register
- Create: `tests/unit/test_cli_perms.py`

**Subcommands:** `audit`, `list [--stale|--dup]`, `dedupe [--dry-run]`, `prune --older-than <d> [--dry-run]`, `remove <rule> --from <path>`, `add <rule> --to <scope>`.

**Step 1: Test.**

```python
def test_perms_audit(mock_claude_home):
    from typer.testing import CliRunner
    from cc_janitor.cli import app
    r = CliRunner().invoke(app, ["perms", "audit"])
    assert r.exit_code == 0
    assert "rules" in r.stdout.lower()

def test_perms_list_stale(mock_claude_home):
    from typer.testing import CliRunner
    from cc_janitor.cli import app
    r = CliRunner().invoke(app, ["perms", "list", "--stale"])
    assert r.exit_code == 0
    assert "ssh user@old-host" in r.stdout
```

**Step 2: FAIL. Implement.** Wire to `core.permissions` functions; sessions for usage analysis come from `discover_sessions()`. Same `NotConfirmedError` handling pattern as Task 18.

```python
# src/cc_janitor/cli/commands/perms.py
from __future__ import annotations
import typer
from ...core.permissions import discover_rules, analyze_usage, find_duplicates, remove_rule, add_rule
from ...core.sessions import discover_sessions
from ...core.safety import NotConfirmedError

perms_app = typer.Typer(help="Audit and prune permission rules")

def _rules_with_usage():
    return analyze_usage(discover_rules(), discover_sessions())

@perms_app.command("audit")
def audit():
    rules = _rules_with_usage()
    by_source = {}
    for r in rules:
        by_source.setdefault(r.source.path, []).append(r)
    typer.echo(f"Total rules: {len(rules)}")
    stale = sum(1 for r in rules if r.stale)
    typer.echo(f"Stale (no match in 90d): {stale}")
    dups = find_duplicates(rules)
    typer.echo(f"Duplicates detected: {len(dups)}")
    typer.echo("\nBy source:")
    for path, rs in by_source.items():
        typer.echo(f"  {path}: {len(rs)} rules")

@perms_app.command("list")
def list_(stale: bool = typer.Option(False, "--stale"),
          dup: bool = typer.Option(False, "--dup"),
          source: str = typer.Option(None, "--source")):
    rules = _rules_with_usage()
    if source:
        rules = [r for r in rules if r.source.scope == source]
    if stale:
        rules = [r for r in rules if r.stale]
    if dup:
        dup_set = {id(r) for d in find_duplicates(rules) for r in d.rules}
        rules = [r for r in rules if id(r) in dup_set]
    for r in rules:
        flag = "STALE" if r.stale else ""
        typer.echo(f"{r.tool:6}  {r.pattern:30}  {r.source.scope:12}  hits90d={r.match_count_90d}  {flag}")

@perms_app.command("dedupe")
def dedupe(dry_run: bool = typer.Option(False, "--dry-run")):
    rules = _rules_with_usage()
    dups = find_duplicates(rules)
    for d in dups:
        typer.echo(f"[{d.kind}] {d.suggestion}")
    if dry_run or not dups:
        return
    # Auto-remove only "exact" (keep first occurrence) and "subsumed" (remove narrow)
    for d in dups:
        try:
            if d.kind == "exact":
                for r in d.rules[1:]:
                    remove_rule(r)
                    typer.echo(f"removed exact dup: {r.raw} from {r.source.path}")
            elif d.kind == "subsumed":
                broad, narrow = d.rules[0], d.rules[1]
                remove_rule(narrow)
                typer.echo(f"removed subsumed: {narrow.raw}")
        except NotConfirmedError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(code=2)

@perms_app.command("prune")
def prune(older_than: str = typer.Option("90d", "--older-than"),
          dry_run: bool = typer.Option(False, "--dry-run")):
    rules = _rules_with_usage()
    stale = [r for r in rules if r.stale]
    typer.echo(f"{len(stale)} stale rules (no match 90d):")
    for r in stale:
        typer.echo(f"  {r.tool}({r.pattern})  in {r.source.path}")
    if dry_run:
        return
    for r in stale:
        try:
            remove_rule(r)
        except NotConfirmedError as e:
            typer.echo(str(e), err=True); raise typer.Exit(code=2)

@perms_app.command("remove")
def remove(raw: str, from_: str = typer.Option(..., "--from")):
    from pathlib import Path
    rules = discover_rules()
    target = next((r for r in rules if r.raw == raw and str(r.source.path) == from_), None)
    if not target:
        raise typer.BadParameter("Rule not found in given source")
    try:
        remove_rule(target)
        typer.echo(f"removed {raw}")
    except NotConfirmedError as e:
        typer.echo(str(e), err=True); raise typer.Exit(code=2)

@perms_app.command("add")
def add(raw: str, to: str = typer.Option(..., "--to"),
        decision: str = typer.Option("allow", "--decision")):
    try:
        add_rule(raw, scope=to, decision=decision)
        typer.echo(f"added {raw} → {to}")
    except NotConfirmedError as e:
        typer.echo(str(e), err=True); raise typer.Exit(code=2)
```

Register in `cli/__init__.py`. **Step 3: PASS, commit.**

```bash
git commit -am "feat(cli): perms subcommands (audit/list/dedupe/prune/remove/add)"
```

---

## Task 20: CLI context subcommands

**Files:**
- Create: `src/cc_janitor/cli/commands/context.py`
- Modify: `cli/__init__.py` — register
- Create: `tests/unit/test_cli_context.py`

**Subcommands:** `show [--project PATH]`, `cost`, `find-duplicates`.

**Step 1: Test.**

```python
def test_context_show(mock_claude_home):
    from typer.testing import CliRunner
    from cc_janitor.cli import app
    project = mock_claude_home / "myproject"
    project.mkdir(exist_ok=True)
    r = CliRunner().invoke(app, ["context", "show", "--project", str(project)])
    assert r.exit_code == 0
    assert "tokens" in r.stdout.lower()

def test_context_cost(mock_claude_home):
    from typer.testing import CliRunner
    from cc_janitor.cli import app
    r = CliRunner().invoke(app, ["context", "cost"])
    assert r.exit_code == 0
```

**Step 2: FAIL. Implement.**

```python
# src/cc_janitor/cli/commands/context.py
from __future__ import annotations
from pathlib import Path
import typer
from ...core.context import context_cost

context_app = typer.Typer(help="Inspect context cost (CLAUDE.md, memory, skills)")

@context_app.command("show")
def show(project: Path = typer.Option(Path.cwd(), "--project")):
    cost = context_cost(starting_from=project)
    for f in sorted(cost.files, key=lambda x: -x.tokens):
        typer.echo(f"{f.kind:10}  {f.size_bytes:>8}b  {f.tokens:>6}tok  {f.path}")
    typer.echo(f"\nTOTAL: {cost.total_bytes}b  {cost.total_tokens} tokens")

@context_app.command("cost")
def cost(project: Path = typer.Option(Path.cwd(), "--project")):
    c = context_cost(starting_from=project)
    typer.echo(f"{c.total_bytes} bytes, {c.total_tokens} tokens")
    # rough Opus rate: $15/1M input
    dollars = c.total_tokens * 15 / 1_000_000
    typer.echo(f"≈ ${dollars:.4f} per request at Opus input rate")

@context_app.command("find-duplicates")
def find_duplicates(project: Path = typer.Option(Path.cwd(), "--project")):
    c = context_cost(starting_from=project)
    seen: dict[str, list[Path]] = {}
    for f in c.files:
        for line in f.path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if len(line) < 40:  # only flag substantial dupes
                continue
            seen.setdefault(line, []).append(f.path)
    dups = {k: v for k, v in seen.items() if len(set(v)) > 1}
    if not dups:
        typer.echo("No duplicate substantial lines.")
        return
    for line, paths in dups.items():
        typer.echo(f"\n{len(set(paths))}× {line[:80]}…")
        for p in set(paths):
            typer.echo(f"  - {p}")
```

**Step 3: PASS, commit.**

```bash
git commit -am "feat(cli): context subcommands (show/cost/find-duplicates)"
```

---

## Task 21: TUI app skeleton

**Files:**
- Create: `src/cc_janitor/tui/app.py`
- Modify: `src/cc_janitor/__main__.py` — launch TUI when no args
- Create: `tests/tui/test_app_smoke.py`

**Goal:** Textual `App` with TabbedContent for 7 tabs (Sessions/Permissions/Context/Memory/Hooks/Schedule/Audit). Tabs are placeholder Static widgets — real content comes in next tasks. Snapshot test verifies it renders.

**Step 1: Implement.**

```python
# src/cc_janitor/tui/app.py
from __future__ import annotations
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, TabbedContent, TabPane, Static
from ..i18n import t, detect_lang, set_lang

class CcJanitorApp(App):
    CSS = "TabbedContent { height: 100%; }"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("f1", "help", "Help"),
        ("f2", "toggle_lang", "Lang"),
    ]

    def __init__(self) -> None:
        super().__init__()
        set_lang(detect_lang())

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with TabbedContent():
            with TabPane(t("sessions.title"), id="sessions"):
                yield Static("Sessions screen — TODO")
            with TabPane(t("perms.title"), id="perms"):
                yield Static("Permissions screen — TODO")
            with TabPane(t("context.title"), id="context"):
                yield Static("Context screen — TODO")
            with TabPane("Memory", id="memory"):
                yield Static("Memory screen — TODO")
            with TabPane("Hooks", id="hooks"):
                yield Static("Hooks screen — TODO")
            with TabPane("Schedule", id="schedule"):
                yield Static("Schedule screen — TODO")
            with TabPane("Audit", id="audit"):
                yield Static("Audit screen — TODO")
        yield Footer()

    def action_toggle_lang(self) -> None:
        from ..i18n import _current_lang
        new = "ru" if _current_lang == "en" else "en"
        set_lang(new)
        self.refresh()

def run() -> None:
    CcJanitorApp().run()
```

Update `__main__.py`:

```python
def main() -> None:
    if len(sys.argv) > 1:
        from .cli import app
        app()
    else:
        from .tui.app import run
        run()
```

**Step 2: Snapshot test.**

```python
# tests/tui/test_app_smoke.py
import pytest

@pytest.mark.asyncio
async def test_app_renders():
    from cc_janitor.tui.app import CcJanitorApp
    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.is_running
```

**Step 3: PASS, commit.**

```bash
git commit -am "feat(tui): app skeleton with 7 tabs and lang switch"
```

---

## Task 22: TUI Sessions screen

**Files:**
- Create: `src/cc_janitor/tui/screens/sessions_screen.py`
- Modify: `src/cc_janitor/tui/app.py` — replace Sessions placeholder with real screen
- Create: `tests/tui/test_sessions_screen.py`

**Goal:** DataTable of sessions, sortable columns, Enter opens preview pane (Static below table), `d` triggers delete confirmation modal.

**Step 1: Implement (essence — full file in cookbook).**

```python
# src/cc_janitor/tui/screens/sessions_screen.py
from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static, Footer, Button, Label
from textual.widget import Widget
from ...core.sessions import discover_sessions, delete_session, enrich_with_indexer_summaries
from ...core.safety import is_confirmed
from ...i18n import t

class DeleteConfirmModal(ModalScreen[bool]):
    def __init__(self, count: int) -> None:
        super().__init__()
        self.count = count

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(t("sessions.delete_confirm", count=self.count)),
            Horizontal(
                Button(t("common.yes"), id="yes", variant="error"),
                Button(t("common.no"), id="no"),
            ),
        )

    def on_button_pressed(self, ev: Button.Pressed) -> None:
        self.dismiss(ev.button.id == "yes")

class SessionsScreen(Widget):
    DEFAULT_CSS = "DataTable { height: 60%; } #preview { height: 40%; border: round; }"

    def compose(self) -> ComposeResult:
        yield DataTable(id="sessions-table")
        yield Static("", id="preview")
        yield Footer()

    def on_mount(self) -> None:
        table: DataTable = self.query_one("#sessions-table", DataTable)
        table.add_columns("ID", "Project", "Date", "Size", "Msgs", "First msg")
        table.cursor_type = "row"
        for s in sorted(discover_sessions(), key=lambda x: x.last_activity, reverse=True):
            table.add_row(
                s.id, s.project, s.last_activity.strftime("%Y-%m-%d %H:%M"),
                f"{s.size_bytes // 1024}KB", str(s.message_count),
                (s.first_user_msg or "")[:50], key=s.id,
            )

    def on_data_table_row_highlighted(self, ev: DataTable.RowHighlighted) -> None:
        sid = ev.row_key.value if ev.row_key else None
        if not sid:
            return
        s = next((x for x in discover_sessions() if x.id == sid), None)
        if not s:
            return
        prv = self.query_one("#preview", Static)
        text = (
            f"[b]{s.id}[/]\n"
            f"Project: {s.project}\n"
            f"Messages: {s.message_count}  Compactions: {s.compactions}\n\n"
            f"[b]{t('sessions.preview_first_msg')}[/]:\n{s.first_user_msg}\n"
        )
        prv.update(text)

    async def action_delete(self) -> None:
        table = self.query_one("#sessions-table", DataTable)
        if table.cursor_row < 0:
            return
        async def _on_dismiss(confirmed: bool):
            if not confirmed:
                return
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            sid = row_key.value if row_key else None
            s = next((x for x in discover_sessions() if x.id == sid), None)
            if not s:
                return
            if not is_confirmed():
                self.notify("Set CC_JANITOR_USER_CONFIRMED=1 to delete from TUI.", severity="error")
                return
            delete_session(s)
            table.remove_row(row_key)
        await self.app.push_screen(DeleteConfirmModal(count=1), _on_dismiss)
```

Wire into app and bind `d` → `action_delete`.

**Step 2: Snapshot test.**

```python
# tests/tui/test_sessions_screen.py
import pytest

@pytest.mark.asyncio
async def test_sessions_screen_lists(mock_claude_home):
    from cc_janitor.tui.app import CcJanitorApp
    app = CcJanitorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # tab into sessions and check table populated
        from textual.widgets import DataTable
        table = app.query_one("#sessions-table", DataTable)
        assert table.row_count >= 2
```

**Step 3: PASS, commit.**

```bash
git commit -am "feat(tui): Sessions screen with table, preview, delete modal"
```

---

## Task 23: TUI Permissions screen

**Files:**
- Create: `src/cc_janitor/tui/screens/perms_screen.py`
- Modify: `tui/app.py`
- Create: `tests/tui/test_perms_screen.py`

**Goal:** DataTable of effective rules with stale/dup flags + sources panel below; `p` triggers `prune` confirm modal.

Implementation mirrors Sessions screen pattern: `DataTable` with columns `Tool/Pattern/Source/Used/Age/Flag`; row-highlight updates a side panel; key bindings invoke the same core functions used by CLI.

Snapshot smoke test verifies table populates from mock fixture (≥4 rules expected).

```bash
git commit -am "feat(tui): Permissions screen with rules table and prune modal"
```

---

## Task 24: TUI Context screen

**Files:**
- Create: `src/cc_janitor/tui/screens/context_screen.py`
- Modify: `tui/app.py`
- Create: `tests/tui/test_context_screen.py`

**Goal:** Tree of files (CLAUDE.md hierarchy → memory → skills) with size/tokens columns; total cost block at bottom.

Use Textual `Tree` widget with three top-level branches; expand on mount; total computed once.

```bash
git commit -am "feat(tui): Context screen with hierarchy tree and cost block"
```

---

## Task 25: Audit log integration in CLI/TUI

**Files:**
- Modify: every `cli/commands/*.py` — wrap mutations with audit.record(...)
- Modify: TUI mutation paths (delete_session, remove_rule) — same
- Create: `tests/unit/test_audit_integration.py`

**Goal:** Every mutating action results in an `AuditEntry` written.

**Step 1: Test.**

```python
def test_delete_writes_audit(mock_claude_home, monkeypatch):
    monkeypatch.setenv("CC_JANITOR_USER_CONFIRMED", "1")
    from typer.testing import CliRunner
    from cc_janitor.cli import app
    from cc_janitor.core.state import get_paths
    from cc_janitor.core.audit import AuditLog
    CliRunner().invoke(app, ["session", "delete", "abc123"])
    log = AuditLog(get_paths().audit_log)
    entries = list(log.read())
    assert any(e.cmd.startswith("session") for e in entries)
```

**Step 2: FAIL. Implement.** Use a small decorator or context-manager `audit_action(cmd, args)` in CLI handlers.

```python
# helper in cli/__init__.py
from contextlib import contextmanager
from .core.audit import AuditLog
from .core.state import get_paths
from .core.safety import is_confirmed

@contextmanager
def audit_action(cmd: str, args: list[str]):
    log = AuditLog(get_paths().audit_log)
    exit_code = 0
    changed: dict | None = None
    try:
        yield (lambda d: globals().__setitem__("_audit_changed", d))  # callback for impl to attach
        changed = globals().get("_audit_changed")
    except SystemExit as e:
        exit_code = int(e.code or 0)
        raise
    finally:
        log.record(mode="cli", user_confirmed=is_confirmed(),
                   cmd=cmd, args=args, exit_code=exit_code, changed=changed)
```

(Note: the decorator pattern is illustrative — the executing engineer should choose the cleanest form for the codebase, e.g. plain function calls instead of stash-globals.)

**Step 3: PASS, commit.**

```bash
git commit -am "feat: audit log integration across CLI mutations"
```

---

## Task 26: README + cookbook stubs

**Files:**
- Create: `README.md` (English, full)
- Create: `README.ru.md` (Russian)
- Create: `docs/cookbook.md` with the 6 recipes from design §9
- Create: `docs/CC_USAGE.md`
- Create: `CHANGELOG.md`

**Step 1: Write `README.md`** following the user's house style (see `portfolio/README.md`):
- Hero block with one-line tagline + live demo placeholder + PyPI link + supported languages
- `## Stack`
- `## Features` (group by phase 1 area)
- `## Install` (`pipx install cc-janitor`, `uv tool install cc-janitor`, dev install)
- `## Quick start` (4-5 commands from cookbook)
- `## How it works` (2 paragraphs)
- `## Safety model` (CC_JANITOR_USER_CONFIRMED, soft-delete, audit log)
- `## Using from inside Claude Code` (link to CC_USAGE.md)
- `## Contributing` (link to architecture.md, CONTRIBUTING when added)
- `## License` (MIT)

**Step 2: Mirror to `README.ru.md`** with same structure, RU prose.

**Step 3: Write `docs/cookbook.md`** — exactly the 6 recipes from design §9, each: problem statement → command(s) → expected output (use real `mock-claude-home` outputs) → next step.

**Step 4: Write `docs/CC_USAGE.md`** — short reference for inclusion in `~/.claude/CLAUDE.md`. Tells Claude Code:
- Read-only commands it may freely call (list/show/cost/...)
- Mutating commands that require explicit user phrase + setting `CC_JANITOR_USER_CONFIRMED=1` for that single invocation
- Example dialogue showing correct usage

**Step 5: `CHANGELOG.md`** with `## [Unreleased]` block listing every commit so far in user's CHANGELOG style.

**Step 6: Commit.**

```bash
git commit -am "docs: README EN/RU, cookbook, CC_USAGE, CHANGELOG"
```

---

## Task 27: CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`
- Create: `.github/ISSUE_TEMPLATE/bug.yml`, `feature.yml`

**Step 1: `ci.yml`** — runs on push & PR: matrix Python 3.11/3.12 × ubuntu/windows, `uv sync`, `uv run ruff check`, `uv run pytest`, snapshot tests.

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
        python: ["3.11", "3.12"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - uses: actions/setup-python@v5
        with: { python-version: "${{ matrix.python }}" }
      - run: uv sync --all-extras
      - run: uv run ruff check src tests
      - run: uv run pytest --cov=cc_janitor
```

**Step 2: `release.yml`** — on tag `v*`, builds wheel via `uv build` and publishes to PyPI via Trusted Publishers (no token).

**Step 3: Issue templates** — minimal YAML forms.

**Step 4: Commit.**

```bash
git commit -am "ci: GitHub Actions for test + release"
```

---

## Task 28: doctor and install-hooks commands

**Files:**
- Create: `src/cc_janitor/cli/commands/doctor.py`
- Create: `src/cc_janitor/cli/commands/install_hooks.py`

**Goal:**
- `cc-janitor doctor` — prints Python version, ~/.claude existence, settings.json validity, sessions count, perms count, audit log size, trash size. Returns non-zero if a critical check fails.
- `cc-janitor install-hooks` — installs the `reinject` PreToolUse hook into `~/.claude/settings.json` (idempotent, requires CC_JANITOR_USER_CONFIRMED=1). Closes the prerequisite for Phase 2 reinject.

Tests: smoke (CliRunner) for both. Commit.

```bash
git commit -am "feat(cli): doctor + install-hooks commands"
```

---

## Phase-1 done — release 0.1.0

**Steps:**

1. `uv build` → wheel + sdist in `dist/`
2. Verify `pipx install ./dist/cc-janitor-0.1.0-py3-none-any.whl` works on a clean venv
3. Update `CHANGELOG.md` with `## [0.1.0] — 2026-XX-XX`
4. Tag: `git tag -a v0.1.0 -m "Phase 1 MVP"`, push tags
5. CI release workflow publishes to PyPI
6. Manual sanity: `pipx install cc-janitor` from PyPI, run a session list against real `~/.claude`

---

## Phase 2 (separate plan)

After 0.1.0 ships and runs against real data without breakage for at least one user-week, write a follow-up plan covering:

- Memory editor screen
- Reinject mechanism (PreToolUse hook + marker file)
- Hooks debugger screen + `simulate` command
- Schedule wrapper (`schtasks` / cron) + 5 pre-built jobs
- Windows hook env-var fix wrapper

That plan goes to `docs/plans/2026-XX-XX-cc-janitor-phase2.md`.

---

## Phase 3 (separate plan)

After Phase 2 stabilizes:

- Monorepo nested `.claude/` discovery (Issue #37344)
- Auto-reinject background watcher (opt-in)
- Stats dashboard with history
- Export/import config bundle
- Shell completions

---

## Plan complete and saved.

**Next step — choose execution mode:**

1. **Subagent-Driven (this session)** — I dispatch a fresh subagent per task,
   review its work between tasks, fast iteration. Stays in this session.
2. **Parallel Session (separate)** — open a new Claude Code session inside the
   `cc-janitor/` worktree, that session uses `superpowers:executing-plans` to
   chew through tasks in batch with checkpoints.

Which approach?
