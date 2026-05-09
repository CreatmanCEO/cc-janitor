# cc-janitor Phase 3 — Design Document

> **Date:** 2026-05-09
> **Author:** @CreatmanCEO
> **Status:** Approved, ready for implementation planning
> **Predecessors:**
> `docs/plans/2026-05-03-cc-janitor-design.md` (master design),
> `docs/plans/2026-05-03-cc-janitor-phase1-mvp.md` (Phase 1 plan, shipped as v0.1.0/0.1.1),
> `docs/plans/2026-05-05-cc-janitor-phase2-design.md` (Phase 2 design),
> `docs/plans/2026-05-05-cc-janitor-phase2-mvp.md` (Phase 2 plan, shipped as v0.2.0)

## 1. Problem statement

Phase 1 closed the three biggest pain points (sessions, permissions, context).
Phase 2 closed the next four (memory editor, reinject hook, hooks debugger,
scheduler). Phase 3 closes the final five items on the master-design
roadmap (§4.3) — items deferred from earlier phases because they are either
nice-to-have, opt-in, cross-platform-divergent, or required two prior phases
of foundations to land first:

1. **Monorepo nested `.claude/` discovery.** Power users routinely have
   dozens of stray `.claude/` directories scattered across their disk —
   typically inside `node_modules/` (vendored from third-party packages),
   inside `.venv/site-packages/`, or inside scratch sub-projects. A real
   case from the user's machine: `~/portfolio/node_modules/es-abstract/.claude/settings.local.json`
   was discovered during a routine audit. Today, `cc-janitor` only sees the
   four canonical locations (`~/.claude`, `~/.claude/settings.local.json`,
   `<cwd>/.claude/settings.json`, `<cwd>/.claude/settings.local.json`).
   This blind spot directly maps to upstream Claude Code issues
   [#37344](https://github.com/anthropics/claude-code/issues/37344),
   [#35561](https://github.com/anthropics/claude-code/issues/35561),
   [#18192](https://github.com/anthropics/claude-code/issues/18192),
   [#40640](https://github.com/anthropics/claude-code/issues/40640) — all
   variations of "Claude Code finds/respects/ignores nested `.claude/`
   inconsistently across monorepos". Phase 3 ships a discovery layer that
   walks a configurable root, classifies every `.claude/` directory as
   `real | nested | junk`, and surfaces them in both CLI and TUI for
   inspection and cleanup.

2. **Auto-reinject background watcher.** Phase 2 shipped the manual writer
   side of the reinject mechanism (`cc-janitor context reinject` writes
   `~/.cc-janitor/reinject-pending`; the PreToolUse hook installed by
   `install-hooks` reads it on the next tool call). For users who edit
   memory files frequently — typically via `$EDITOR` outside the TUI — the
   manual `reinject` call is a step they keep forgetting. A small,
   opt-in background daemon polls `~/.claude/projects/*/memory/` mtimes and
   touches the marker automatically when memory files change. The watcher
   is opt-in (never auto-started), uses mtime polling (not platform-native
   FS-events), and stops cleanly via PID file.

3. **Stats dashboard with history.** Right now, every `cc-janitor` run is
   point-in-time: the user sees their current 234 perm rules, 42k context
   tokens, 18 stale sessions — but has no idea whether last week's prune
   helped or hurt. A daily snapshot stored at `~/.cc-janitor/history/<date>.json`,
   plus a `cc-janitor stats [--since 30d]` reader with simple ASCII
   sparkline rendering in the TUI Audit tab, gives users a feedback loop:
   "I ran perms prune on Monday and my context cost dropped from 12k to 6k
   tokens". The Phase 2 `context-audit` scheduled job already writes
   `cost.jsonl` daily; Phase 3 generalises that to a richer snapshot
   format and adds a reader.

4. **Export/import config bundle.** Users who work across multiple machines
   (Windows desktop + Linux/macOS work laptop) currently have no portable
   way to sync their hand-curated `~/.claude/CLAUDE.md`, skills directory,
   memory files, and settings.json without doing a manual copy or a
   half-baked `git` setup. A `cc-janitor config export <bundle.tar.gz>` /
   `cc-janitor config import <bundle.tar.gz>` pair gives explicit,
   intent-driven sync — never automatic. Secrets-bearing files
   (`settings.local.json`) are explicitly excluded from the export. Import
   defaults to dry-run, requires `CC_JANITOR_USER_CONFIRMED=1`, and backs
   up every file it overwrites.

5. **Shell completions.** Power users running cc-janitor as a CLI deserve
   tab completion. Typer (which wraps Click) ships built-in completion
   generators for bash/zsh/fish/PowerShell. Phase 3 surfaces these via a
   `cc-janitor completions install [shell]` / `cc-janitor completions
   show <shell>` pair so users can either drop the snippet into their
   shell rc or pipe to a file themselves.

These five items finish the master roadmap. After Phase 3 ships as v0.3.0,
the project moves into bug-fix-and-polish mode rather than feature growth.

## 2. Tech stack — what's new

Phase 3 reuses the Phase 1+2 stack with **no new mandatory dependencies**.
The watcher uses `subprocess.Popen` from the stdlib for daemon spawn; the
config bundle uses stdlib `tarfile` and `hashlib`; stats uses stdlib `json`;
shell completions use Typer's built-in `--show-completion` and
`--install-completion` hooks (already present in any Typer app).

| Layer | Choice | Why |
|-------|--------|-----|
| Background daemon | stdlib `subprocess.Popen` + `os.kill` | No `psutil` dependency by default; cross-platform via `start_new_session` (POSIX) / `CREATE_NEW_PROCESS_GROUP` (Windows) |
| Tar bundle | stdlib `tarfile` (gzip mode) | Portable; manifest goes in as `manifest.json` first member |
| Bundle hashing | stdlib `hashlib.sha256` | Detect tampering, surface in import dry-run |
| Sparkline rendering | hand-rolled ASCII (Unicode block elements `▁▂▃▄▅▆▇█`) | No new dep; works in Textual `Static` and plain CLI |
| Optional process mgmt | `psutil>=5.9` | **Optional** extra (`pip install cc-janitor[watcher]`); when present, gives accurate process-alive checks; absent — fall back to `os.kill(pid, 0)` |

`psutil` is the only new dependency and it is opt-in via `[project.optional-dependencies] watcher = ["psutil>=5.9"]`. Users who never run the
watcher never need to install it.

## 3. Architecture

Phase 3 is purely additive to the Phase 1+2 layout. No existing module is
moved or refactored.

### 3.1 New modules under `src/cc_janitor/`

```
src/cc_janitor/
├── core/
│   ├── monorepo.py            # NEW — walk-and-classify .claude/ dirs
│   ├── watcher.py             # NEW — daemon spawn, mtime poll loop
│   ├── stats.py               # NEW — snapshot writer + reader + sparkline
│   ├── bundle.py              # NEW — export tar.gz with manifest, import
│   │                          #       with dry-run + backup-before-overwrite
│   └── completions.py         # NEW — thin shim around Typer's built-in
└── cli/commands/
    ├── monorepo.py            # NEW — typer subapp
    ├── watch.py               # NEW — typer subapp (start/stop/status)
    ├── stats.py               # NEW — typer subapp
    ├── config.py              # NEW — typer subapp (export/import)
    └── completions.py         # NEW — typer subapp (install/show)
```

Existing files modified:

- `src/cc_janitor/cli/__init__.py` — register five new typer subapps.
- `src/cc_janitor/cli/commands/doctor.py` — add `Watcher: <status>` line
  reading the PID file when present.
- `src/cc_janitor/tui/screens/audit_screen.py` — add stats sub-pane
  (sparklines for tokens / perm-rule count / trash size over the last 30
  days).
- `src/cc_janitor/tui/screens/permissions_screen.py`,
  `hooks_screen.py`, `memory_screen.py` — add a "Source: <path>" filter
  dropdown that includes nested `.claude/` discovered via `monorepo.py`.
- `src/cc_janitor/i18n/{en,ru}.toml` — new keys for monorepo / watcher /
  stats / bundle / completions.
- `pyproject.toml` — add `[project.optional-dependencies] watcher` extra,
  bump version to `0.3.0.dev0`.

### 3.2 Architectural principles (carried unchanged)

All six Phase 1 principles still hold:

1. Single binary, two modes (TUI + CLI from the same package).
2. `core/` knows nothing about UI. Pure functions returning dataclasses.
3. i18n via TOML + `t()`. Five new key namespaces (`monorepo`, `watcher`,
   `stats`, `bundle`, `completions`) added to both `en.toml` and `ru.toml`.
4. Mutations require `CC_JANITOR_USER_CONFIRMED=1`. Phase 3 mutating
   commands: `watch start`, `watch stop`, `config import`. (The watcher
   itself, once running, writes the reinject marker as a low-privilege
   side-effect that is not an audit-log mutation; the daemon's startup
   *is* the audited mutation.)
5. Audit log is always on. Phase 3 adds three new audit verbs:
   `watch.start`, `watch.stop`, `config.export`, `config.import`.
6. State location: `~/.cc-janitor/`. Phase 3 adds three new locations:
   - `~/.cc-janitor/watcher.pid` — single line, the daemon's PID.
   - `~/.cc-janitor/watcher.log` — append-only, mtime-poll diagnostic
     output (rotated at 1 MB).
   - `~/.cc-janitor/history/<YYYY-MM-DD>.json` — daily snapshots
     (Phase 2 already created the directory; Phase 3 standardises the
     filename and schema).

### 3.3 Cross-platform abstractions

The watcher is the only Phase 3 area with substantive platform branching.
A new helper `core/watcher.py:spawn_daemon(args, cwd, log_path)` handles
the difference:

```python
def spawn_daemon(args: list[str], cwd: Path, log_path: Path) -> int:
    log = log_path.open("ab")
    if sys.platform == "win32":
        # CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
        flags = 0x00000200 | 0x00000008
        proc = subprocess.Popen(
            args, cwd=cwd, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
            creationflags=flags, close_fds=True,
        )
    else:
        proc = subprocess.Popen(
            args, cwd=cwd, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
            start_new_session=True, close_fds=True,
        )
    return proc.pid
```

Stop is symmetric: `os.kill(pid, signal.SIGTERM)` on POSIX, the same on
Windows where Python translates to `TerminateProcess`. If `psutil` is
installed, `psutil.Process(pid).is_running()` is preferred over
`os.kill(pid, 0)` for the status check (Windows raises a generic OSError
on a closed PID, which is hard to disambiguate from "PID does not exist").

The bundle exporter and stats reader are platform-agnostic: only the path
manipulations matter, and `pathlib` already abstracts those.

## 4. Feature scope (Phase 3)

### 4.1 Monorepo nested `.claude/` discovery

**Discovery walk.** Starting from a configurable root (`--root`, default
`Path.cwd()`), walk the file tree and yield every `.claude/` directory.
The walk must skip standard noise directories by default — `node_modules`,
`.venv`, `venv`, `.git`, `__pycache__`, `dist`, `build`, `.next`,
`.tox` — unless `--include-junk` is passed. This is implemented as a
`SKIP_DIRS` set inside `core/monorepo.py`; users can extend it via
`~/.cc-janitor/config.toml` `[monorepo] skip_dirs = ["..."]`.

**Classification.** For each discovered `.claude/` directory, classify into
one of three buckets:

- **`real`** — the parent is a project root (contains `pyproject.toml`,
  `package.json`, `Cargo.toml`, `go.mod`, `pom.xml`, `Gemfile`, `.git/`)
  *and* the path is not under any of the `SKIP_DIRS`. These show up in
  the TUI as live alternative sources.
- **`nested`** — the parent contains one of the markers above but the path
  *is* under a `SKIP_DIRS` (e.g. a vendored dep with its own
  `package.json`). These are surfaced informationally.
- **`junk`** — no project-root marker in the parent, and either it is
  inside a SKIP_DIR or has no settings/skills/hooks/MCP content of its
  own. Candidate for cleanup. Only surfaced when `--include-junk` is set.

**Inspection.** For each location, populate a `MonorepoLocation`
(see §5) with booleans for `has_settings`, `has_skills`, `has_hooks`,
`has_mcp`, plus `last_modified` (max mtime of any file inside).

**TUI integration.** Permissions / Hooks / Memory tabs gain a "Source"
filter dropdown. By default it shows only `real` locations. Selecting
`<all real>`, `<include nested>`, or a specific path filters the table
accordingly. The dropdown is populated by `core.monorepo.discover_locations(scope_filter=("real", "nested"))`.

**CLI:**

```bash
cc-janitor monorepo scan [--root PATH] [--include-junk] [--json]
cc-janitor monorepo show <path>          # inspect one location in detail
```

Both are read-only — Claude Code may invoke freely.

**No mutation in Phase 3.** Phase 3 surfaces but does not delete junk
locations. Cleanup is a future feature (`cc-janitor monorepo clean`,
deferred to Phase 4 / patch release).

### 4.2 Auto-reinject background watcher

**Design.** The watcher is a separate Python process spawned via
`subprocess.Popen` with detached/new-session flags. Its body
(`cc_janitor.core.watcher:run_watcher`) is a simple polling loop:

```python
def run_watcher(memory_dirs: list[Path], interval: int) -> None:
    last_mtimes: dict[Path, float] = {p: p.stat().st_mtime for p in _iter(memory_dirs)}
    while True:
        time.sleep(interval)
        changed = False
        for f in _iter(memory_dirs):
            mt = f.stat().st_mtime
            if last_mtimes.get(f, 0) < mt:
                last_mtimes[f] = mt
                changed = True
        if changed:
            (get_paths().home / "reinject-pending").touch()
            _bump_status_marker_writes()
```

**Lifecycle.**

- `cc-janitor watch start [--interval 30]` — spawn daemon; write PID to
  `~/.cc-janitor/watcher.pid` and a JSON status to `watcher-status.json`
  (started_at, watching_paths, marker_writes_count). Audit-log entry
  recorded. Refuse if PID file already exists *and* the recorded PID is
  alive.
- `cc-janitor watch stop` — read PID, send SIGTERM, wait up to 5 seconds,
  fall back to SIGKILL on POSIX (`signal.SIGKILL`) or `subprocess.run(["taskkill", "/F", "/PID", pid])` on Windows. Remove PID file. Audit entry.
- `cc-janitor watch status` — read PID file, check liveness, print
  `{started_at, watching_paths, interval, marker_writes_count, last_change_at}`.

**Doctor integration.** `cc-janitor doctor` adds one line:

```
Watcher:    running (pid 4711, since 2026-05-09T08:14:00Z, 12 reinjects)
```

or `not running` when no PID file / dead PID.

**Opt-in.** Never auto-started. README and cookbook recipe explicitly
explain how to enable.

**Out of scope for Phase 3:** native FS-events (`watchdog` package, FSEvents
on macOS, inotify on Linux, ReadDirectoryChangesW on Windows). Polling at
30 s is sufficient for the use case (memory edits are infrequent) and
saves a non-trivial dependency stack with platform-divergent quirks.

### 4.3 Stats dashboard with history

**Snapshot schema.** `~/.cc-janitor/history/<YYYY-MM-DD>.json`:

```json
{
  "date": "2026-05-09",
  "sessions_count": 42,
  "perm_rules_count": 234,
  "context_tokens": 12450,
  "trash_bytes": 1245678,
  "audit_entries_since_last": 17
}
```

One file per day. Existing `context-audit` scheduled job (Phase 2) is
generalised to write this richer schema; `cost.jsonl` becomes legacy and
is read for backwards compat by the stats reader.

**Reader.** `cc-janitor stats [--since 30d] [--format text|json|csv]`
loads files in the date window, prints a tabular or JSON summary plus
sparklines per metric:

```
cc-janitor stats --since 30d

Sessions:       42  ▃▄▄▅▅▅▆▆▆▇▇▇▇▇▇▇▆▆▆▆▆▆▆▆▆▆▅▅▄▄
Perm rules:    234  ████▇▇▆▆▆▅▅▅▄▄▄▄▄▃▃▃▃▃▃▃▂▂▂▂▂▂   (-118 since prune)
Context tokens: 12k ▆▆▆▆▆▆▆▆▆▆▅▄▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃   (-49% since prune)
Trash:         1.2M ▁▁▁▁▂▂▃▃▄▄▅▆▆▇▇▇▇▇▆▅▅▄▃▂▂▁▁▁▁▁
```

**TUI integration.** Audit tab gains a stats sub-pane (right-side panel)
that renders the same sparklines using Textual's `Static` widget plus the
hand-rolled ASCII renderer in `core/stats.py:render_sparkline(values, width)`.
No new chart dependency.

### 4.4 Export/import config bundle

**Export.** `cc-janitor config export <bundle.tar.gz> [--include-memory]`:

1. Read-only. Does not require `CC_JANITOR_USER_CONFIRMED=1`.
2. Walk a fixed allowlist of source paths:
   - `~/.claude/CLAUDE.md`
   - `~/.claude/skills/**/*` (recursive, excluding `__pycache__`)
   - `~/.claude/settings.json` (settings, not settings.local.json)
   - `<cwd>/.claude/settings.json` (project, not project-local)
   - `~/.claude/projects/*/memory/*.md` (only if `--include-memory`)
3. **Hard exclusions.** `*settings.local.json` (may contain hard-coded
   secrets; user explicitly excluded). `*.env`, `credentials.json`,
   anything matching a regex of common secret-file names.
4. For each included file: SHA-256 it, add to a `manifest.json` with
   `{path, sha256, kind, size}`. Manifest is the first member of the tar.
5. Tar everything together with gzip compression. Default permissions
   normalised to 0644 (no exec bits).
6. Append audit-log entry: `cmd=config export, exit_code=0,
   changed={"files": <count>, "bytes": <total>}`.

**Import.** `cc-janitor config import <bundle.tar.gz> [--dry-run] [--force]`:

1. Mutating. Requires `CC_JANITOR_USER_CONFIRMED=1`.
2. **Dry-run by default**: if `--dry-run` is omitted, the first invocation
   still runs in dry-run mode and prints "Would write N files. Re-run with
   `--force` to apply." This mirrors the scheduler's dry-run-first guard.
3. Extract tar to a staging directory `~/.cc-janitor/staging/<ts>/`.
4. Parse manifest. Verify SHA-256 of every member.
5. For each file: compute the destination path from `manifest.path`. If
   the destination exists *and* its SHA-256 differs from the bundle's,
   back it up to `~/.cc-janitor/backups/import-<ts>/<original-name>`.
6. With `--force`: write each file to its destination atomically (write
   to `<dest>.cc-janitor-tmp`, then `os.replace`).
7. Append audit-log entry with full file list and per-file
   `before_sha256 / after_sha256 / backup_path`.

**Safety guarantees.**

- Dry-run by default (no `--force` = no writes).
- `CC_JANITOR_USER_CONFIRMED=1` required even for `--force`.
- Backup of existing file before overwrite, every time.
- Audit entry per import lists every file written.
- Hard-coded secret allowlist enforced on export side (cannot opt-in to
  exporting `settings.local.json` even with a flag — the user must
  manually copy if they really want).

### 4.5 Shell completions

**Install.** `cc-janitor completions install [bash|zsh|fish|powershell]`
delegates to Typer's built-in `_install_completion` callback. Typer
detects the current shell from `$SHELL` if no explicit shell is passed.
The installed snippet goes into the standard location for each shell:

- bash: `~/.bash_completion.d/cc-janitor` (or fallback `~/.bashrc` source line)
- zsh: `~/.zfunc/_cc-janitor` (autoload setup)
- fish: `~/.config/fish/completions/cc-janitor.fish`
- powershell: `Microsoft.PowerShell_profile.ps1` source line

**Show.** `cc-janitor completions show <shell>` prints the snippet to
stdout for piping. README documents `cc-janitor completions show bash > ~/.bash_completion.d/cc-janitor`
as the manual install pattern.

**Implementation.** Typer already exposes `--show-completion` and
`--install-completion` at the top level (Click backend). The Phase 3
subapp is a thin wrapper that calls the underlying mechanism with the
right shell argument, plus a friendly success/error message and an audit
entry on install.

## 5. Data model

### 5.1 MonorepoLocation

```python
ScopeKind = Literal["real", "nested", "junk"]

@dataclass
class MonorepoLocation:
    path: Path                    # the .claude/ directory itself
    parent: Path                  # path.parent, the would-be project root
    has_settings: bool            # settings.json present
    has_skills: bool              # skills/ subdir present
    has_hooks: bool               # any hooks.* in settings.json
    has_mcp: bool                 # mcp.json or .mcp.json present
    scope_kind: ScopeKind
    last_modified: datetime       # max mtime of any descendant
    size_bytes: int               # sum of descendant file sizes
    project_marker: str | None    # which marker classified the parent
                                  # ("pyproject.toml", "package.json", ...)
```

### 5.2 WatcherStatus

```python
@dataclass
class WatcherStatus:
    pid: int
    started_at: datetime
    watching_paths: list[Path]
    interval_seconds: int
    marker_writes_count: int
    last_change_at: datetime | None
    is_alive: bool                # checked at read time via os.kill(pid, 0)
```

Persisted as `~/.cc-janitor/watcher-status.json` (JSON, not JSONL — single
record overwritten on every state change).

### 5.3 StatsSnapshot

```python
@dataclass
class StatsSnapshot:
    date: date                    # snapshot date (UTC)
    sessions_count: int
    perm_rules_count: int
    context_tokens: int
    trash_bytes: int
    audit_entries_since_last: int
```

Persisted one-file-per-day as
`~/.cc-janitor/history/<YYYY-MM-DD>.json`. Reader function
`load_snapshots(since: timedelta) -> list[StatsSnapshot]` returns sorted
by date ascending.

### 5.4 ConfigBundle manifest

```json
{
  "version": 1,
  "exported_at": "2026-05-09T12:00:00Z",
  "host": "windows-desktop",
  "cc_janitor_version": "0.3.0",
  "files": [
    {
      "path": "~/.claude/CLAUDE.md",
      "sha256": "abc123...",
      "kind": "claude_md",
      "size": 4321
    },
    {
      "path": "~/.claude/skills/foo/SKILL.md",
      "sha256": "def456...",
      "kind": "skill",
      "size": 1234
    }
  ]
}
```

`kind` is one of: `claude_md`, `skill`, `settings`, `memory`,
`mcp_config`. Used by import to apply per-kind handling (e.g. skills
preserve directory structure, memory files preserve project ownership).

## 6. CLI surface (Phase 3 additions)

```bash
# Monorepo
cc-janitor monorepo scan [--root PATH] [--include-junk] [--json]
cc-janitor monorepo show <path>

# Watcher
cc-janitor watch start [--interval 30]                     # mutation
cc-janitor watch stop                                      # mutation
cc-janitor watch status [--json]

# Stats
cc-janitor stats [--since 30d] [--format text|json|csv]
cc-janitor stats snapshot                                  # write today's snapshot now

# Config bundle
cc-janitor config export <bundle.tar.gz> [--include-memory]
cc-janitor config import <bundle.tar.gz> [--dry-run] [--force]   # mutation

# Completions
cc-janitor completions install [bash|zsh|fish|powershell]  # mutation (writes to shell rc)
cc-janitor completions show <shell>
```

Read-only commands (`monorepo scan/show`, `watch status`, `stats`,
`config export`, `completions show`) are free for Claude Code to invoke
from inside a session. Mutations (`watch start/stop`, `config import`,
`completions install`) require `CC_JANITOR_USER_CONFIRMED=1`.

## 7. TUI screens

Phase 3 adds **no new tabs** — instead it extends three existing tabs:

- **Permissions / Hooks / Memory tabs** gain a "Source" filter dropdown
  in the header bar. Default = `<real only>`. Other options:
  `<real + nested>`, `<all incl. junk>`, plus per-path entries for every
  discovered `.claude/` directory. Filter is applied client-side after
  the existing discovery merges Phase 1+2's canonical sources with the
  Phase 3 discovery.
- **Audit tab** gains a stats sub-pane on the right side rendering the
  four sparklines (sessions / perm rules / context tokens / trash bytes)
  for the last 30 days. Footer key `s` toggles stats sub-pane visibility.

Snapshot tests for each modified tab live alongside Phase 1+2 snapshots
in `tests/tui/`.

## 8. Testing strategy

Phase 1+2 strategy carries forward verbatim. Phase 3 additions:

- **Monorepo tests** extend `mock-claude-home` with a `node_modules/foo/.claude/`
  dir (junk), a `subproject/.claude/` with a `package.json` sibling
  (real), and a `.venv/site-packages/bar/.claude/` (junk). Assertions
  cover classification correctness for each.
- **Watcher tests** spawn the daemon as a subprocess inside `tmp_path`
  with a 1-second interval, touch a memory file, sleep 2 seconds, and
  assert the marker file appeared. PID file lifecycle tested separately
  with `monkeypatch` of `subprocess.Popen` and `os.kill`. Cross-platform
  branching tested via `monkeypatch.setattr("sys.platform", ...)`.
- **Stats tests** seed a `history/` directory with a synthetic 7-day
  series and assert the reader returns sorted snapshots, sparkline
  output is the right width, and missing-day gaps are filled with
  the last-known value (or zero for the first day).
- **Bundle tests** round-trip an export + import in a `tmp_path`
  isolated `CC_JANITOR_HOME`. Property test (hypothesis): for any
  set of source files, export then import produces byte-identical
  destination files. Manifest tampering test: corrupt one byte of
  one tar member, expect import to refuse with a clear SHA-mismatch
  error.
- **Completions tests** assert that `install bash` writes the right
  snippet, `show zsh` prints to stdout, and unknown shell returns
  exit 2 with a helpful message. Underlying Typer behaviour is
  trusted (already tested upstream).
- **Doctor integration test** runs `doctor` with a live PID file
  pointing at `os.getpid()` and asserts the "Watcher: running" line
  is present; with no PID file, asserts "Watcher: not running".

Coverage target unchanged: 90%+ on `core/`. Total expected pytest count
after Phase 3: ~210 (152 from Phase 2 + ~55 new).

## 9. Documentation deliverables

- **`docs/cookbook.md`** — append five new recipes:
  - "Find every `.claude/` directory on my machine — including the
    junk inside `node_modules`"
  - "Auto-reinject memory after every edit (background watcher)"
  - "See how my context cost has changed over the last month"
  - "Move my cc-janitor config from Windows to my Mac"
  - "Enable tab completion for cc-janitor in bash/zsh/PowerShell"
- **`docs/CC_USAGE.md`** — append the Phase 3 read-only / mutating
  subcommand list so Claude Code knows which Phase 3 commands it can call
  freely vs which require user confirmation.
- **`README.md` / `README.ru.md`** — feature-list section gains a "Phase 3"
  bullet group with two screenshots (monorepo scan output, stats sparklines).
- **`CHANGELOG.md`** — start a fresh `[0.3.0]` block for Phase 3
  deliverables.

## 10. Out of scope for Phase 3

- ❌ **Auto-sync of config bundles** — too risky. Sync is explicit:
  user runs export on machine A, manually copies the tar.gz to machine
  B (USB / scp / cloud drive), runs import. No background sync, no cloud
  hosting.
- ❌ **Cloud upload of bundles** — deferred. `config export` writes a
  local file; users wishing to share via S3 / Dropbox can do so manually.
- ❌ **Native FS-events watcher** — FSEvents on macOS, inotify on Linux,
  ReadDirectoryChangesW on Windows. Three different APIs, three different
  failure modes (rename-vs-modify, recursive-watch limits, network-mount
  caveats). mtime polling at 30 s is good enough for the memory-edit
  use case and avoids the dep stack entirely. If a user really wants
  sub-second latency they can drop the interval to 1 s.
- ❌ **Monorepo cleanup (delete junk)** — surfacing only in Phase 3.
  Deletion of nested `.claude/` directories is deferred to a future
  patch release once the classification has been validated against
  real-world fixtures.
- ❌ **Stats per-project breakdown** — Phase 3 stats are global only
  (total tokens across all CLAUDE.md hierarchies, total perm rules across
  all sources). Per-project drill-down deferred.
- ❌ **Bundle import merge mode** — Phase 3 import is "replace if
  different, with backup". A merge mode (e.g. union of permission rules)
  is deferred — it would need conflict-resolution UX that exceeds the
  Phase 3 budget.
- ❌ **Watcher writing other markers** — Phase 3 watcher only writes the
  reinject marker on memory changes. Reacting to settings.json changes
  (e.g. notifying the user "you added a permission rule") is deferred.

## 11. Open questions for implementation planning

1. **Default polling interval for watcher.** Proposal: 30 seconds.
   Rationale: human-perceived "almost immediate" for memory edits which
   happen at most every few minutes. CPU cost is negligible (one stat
   call per file). Open: should we expose `--interval` per `watch start`
   invocation (yes, already in CLI) and persist to status file (yes)?
2. **Junk-detection allowlist source.** Proposal: read a list from
   `~/.cc-janitor/config.toml` `[monorepo] skip_dirs = [...]` if present;
   else hard-coded default. Open: should the default include `target/`
   (Rust) and `out/` (general)? Tentative: yes, both.
3. **Bundle import dry-run-first behaviour.** Proposal: mirror the Phase 2
   scheduler dry-run-pending pattern — the *first* `config import` call
   without `--force` always exits dry-run, even if the user passed
   `--dry-run` explicitly (it's a no-op). Subsequent calls with `--force`
   apply for real. Open: do we cache the "this bundle was just dry-run-ed"
   state to make `--force` more permissive on re-run? Tentative: no —
   simpler to require explicit `--force` every time and trust the audit
   log for accountability.
4. **Stats snapshot trigger.** Proposal: the existing Phase 2
   `context-audit` scheduled job is rewritten to call
   `cc-janitor stats snapshot` instead of the legacy `context cost --json`.
   Backwards compat: legacy `cost.jsonl` still read by `stats` reader.
   Users with the old job in their crontab keep working; `cc-janitor schedule promote context-audit` is the migration nudge.
5. **Watcher restart on settings.json changes.** Proposal: out of scope.
   If the user adds a new project's memory/ dir, they need to `watch stop`
   and `watch start` again. Documented in cookbook recipe.
6. **Shell completion dynamic values.** Typer's completion can be
   dynamic (e.g. tab-complete session IDs). Proposal: Phase 3 ships
   static completions only. Dynamic completions deferred — they would
   need careful audit against the read-only/mutating boundary.

## 12. Approval trail

- Scope: Phase 3 covers Monorepo discovery, Auto-reinject watcher,
  Stats dashboard, Export/import bundle, Shell completions —
  explicitly approved as the "nice-to-have" block in the master design
  (§4.3).
- Tech additions: zero mandatory, one optional (`psutil` under
  `[watcher]` extra) — approved.
- Cross-platform: Windows + POSIX, with one platform-branch in
  `core/watcher.py:spawn_daemon()` and one in `core/watcher.py:_kill_pid()`.
- Mutation/audit semantics carry from Phase 1 unchanged: every write
  gates on `CC_JANITOR_USER_CONFIRMED=1` and appends to audit log.
- Bundle import dry-run-first guard: approved as default-on, opt-out via
  `--force` only after explicit user intent.
- Bundle export hard exclusion of `*settings.local.json` and other
  secret-file patterns: approved, no opt-out flag.
- Watcher opt-in: approved, never auto-started.
- Out-of-scope items above are explicitly deferred to Phase 4 (or
  declared YAGNI permanently in the case of auto-sync and cloud upload).

---

**Next step:** invoke the `superpowers:writing-plans` skill to turn this
design into a step-by-step implementation plan with concrete tasks. The
companion document `docs/plans/2026-05-09-cc-janitor-phase3-mvp.md` is
the output of that step.
