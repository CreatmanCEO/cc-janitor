# cc-janitor Phase 2 — Design Document

> **Date:** 2026-05-05
> **Author:** @CreatmanCEO
> **Status:** Approved, ready for implementation planning
> **Predecessor:** `docs/plans/2026-05-03-cc-janitor-design.md` (master design),
> `docs/plans/2026-05-03-cc-janitor-phase1-mvp.md` (Phase 1 plan, shipped as v0.1.0)

## 1. Problem statement

Phase 1 closed the largest blocks of friction in a Claude Code power-user
environment: stale sessions, ballooning permission rules, and invisible context
cost. Phase 2 closes the remaining four:

1. **Memory drift** — users keep `MEMORY.md`, per-project `project_*.md`,
   and feedback files under `~/.claude/projects/<X>/memory/`. There is no UI
   to list them, see size/freshness, archive obsolete entries, or move an
   entry between types (`user` → `feedback`, `project` → `reference`). Today
   this is a manual `mv` + frontmatter edit.
2. **Memory not re-read after `/compact`** — the well-known
   [Issue #29746](https://github.com/anthropics/claude-code/issues/29746).
   Even after editing memory, Claude Code keeps stale text in context until
   the conversation hard-restarts. Users need a one-shot "re-read this on the
   next tool call" mechanism. Phase 1 already shipped `cc-janitor install-hooks`
   that registers a PreToolUse hook reading `~/.cc-janitor/reinject-pending`
   and emitting a system-reminder; Phase 2 adds the writer side
   (`cc-janitor context reinject`) plus a TUI button, plus a Windows-compat
   branch in `install-hooks` (Phase 1 emitted a POSIX-only shell command).
3. **Hooks are a black box** — Issues
   [#11544](https://github.com/anthropics/claude-code/issues/11544) (hooks
   silently not loaded), [#10401](https://github.com/anthropics/claude-code/issues/10401)
   (must launch with `--debug` to see hook output), and
   [#16564](https://github.com/anthropics/claude-code/issues/16564) (Windows
   missing `TOOL_NAME` / `EXIT_CODE` env vars). Users need a merged view of
   hooks across all settings sources, the ability to simulate a hook with a
   realistic payload, capture stdout/stderr/exit/duration, and toggle a
   logging wrapper without `--debug`.
4. **No automation** — every Phase 1 cleanup is manual. Power users want
   `cc-janitor schedule add perms-prune --cron "0 3 * * 0"` and forget about
   it. The wrapper must be cross-platform (Linux/macOS cron + Windows
   schtasks), must opt-in to live mode only after a successful dry-run, and
   must hard-cap deletions per scheduled run as a runaway-script guard.

These four are intentionally cut from the Phase 1 release: each requires
non-trivial cross-platform plumbing (editor invocation, schtasks XML
generation, hook stdin payload synthesis), and Phase 1 prioritised "closes
80% of pain in 5–7 days" over breadth.

## 2. Tech stack — what's new

Phase 2 reuses the Phase 1 stack (Python 3.11+, Textual ≥0.80, Typer ≥0.12,
tomlkit, rapidjson, pytest, pytest-textual-snapshot) and adds three deps:

| Layer | Choice | Why |
|-------|--------|-----|
| Frontmatter parsing | `python-frontmatter` ≥1.1 | Memory files use YAML frontmatter; we must round-trip without losing keys |
| Cron expression validation | `croniter` ≥2 | Validate `--cron` arguments and compute next-run timestamps for the Schedule TUI |
| Schtasks XML | stdlib `xml.etree.ElementTree` | Windows `schtasks /Create /XML` accepts a Task Scheduler XML; no third-party dep needed |

No new test deps. Snapshot tests for the three new TUI screens use the same
`pytest-textual-snapshot` already in `[dev]`.

## 3. Architecture

Phase 2 is purely additive to the Phase 1 layout — no refactor, no breaking
move of existing modules.

### 3.1 New modules under `src/cc_janitor/`

```
src/cc_janitor/
├── core/
│   ├── memory.py              # NEW — frontmatter parse, list, archive, move-type
│   ├── hooks.py               # NEW — discover, simulate, validate, logging wrapper
│   ├── schedule.py            # NEW — cron + schtasks abstraction, templates
│   └── reinject.py            # NEW — write/clear ~/.cc-janitor/reinject-pending
├── tui/screens/
│   ├── memory_screen.py       # NEW — replaces Phase 1 placeholder
│   ├── hooks_screen.py        # NEW — replaces Phase 1 placeholder
│   └── schedule_screen.py     # NEW — replaces Phase 1 placeholder
└── cli/commands/
    ├── memory.py              # NEW — typer subapp
    ├── hooks.py               # NEW — typer subapp
    ├── schedule.py            # NEW — typer subapp
    └── context.py             # MODIFIED — add `reinject` subcommand
```

Existing files modified:

- `src/cc_janitor/cli/__init__.py` — register three new typer subapps.
- `src/cc_janitor/tui/app.py` — replace placeholder `Static` widgets in tabs
  4/5/6 with the new screens.
- `src/cc_janitor/cli/commands/install_hooks.py` — generate Windows
  PowerShell branch alongside POSIX shell.
- `src/cc_janitor/i18n/{en,ru}.toml` — new keys for memory/hooks/schedule.

### 3.2 Architectural principles (carried from Phase 1)

All six Phase 1 principles still hold and are non-negotiable for Phase 2:

1. Single binary, two modes (TUI + CLI from the same package).
2. `core/` knows nothing about UI. Pure functions returning dataclasses.
3. i18n via TOML + `t()` — three new key namespaces (`memory`, `hooks`,
   `schedule`) added to both `en.toml` and `ru.toml`.
4. Mutations require `CC_JANITOR_USER_CONFIRMED=1`. Every Phase 2 mutating
   CLI command starts with `require_confirmed()`.
5. Audit log is always on. Every mutation appends a JSONL record via
   `core.audit.record(...)` — including `schedule add`, which records the
   template, cron expression, and the dry-run-pending flag.
6. State location: `~/.cc-janitor/`. Phase 2 adds three new locations
   inside it:
   - `~/.cc-janitor/reinject-pending` (single file marker; presence = pending)
   - `~/.cc-janitor/hooks-log/<event>.log` (append-only logging-wrapper output)
   - `~/.cc-janitor/schedule/<job-name>.json` (per-job manifest with
     `dry_run_pending`, `last_run`, `last_status`)

### 3.3 Cross-platform abstraction

The scheduler is the only Phase 2 area with substantive platform branching.
A new helper `core/schedule.py:Scheduler` is an abstract base with two
concrete implementations selected at runtime via `sys.platform`:

```python
class Scheduler(ABC):
    def list_jobs(self) -> list[ScheduledJob]: ...
    def add_job(self, job: ScheduledJob) -> None: ...
    def remove_job(self, name: str) -> None: ...
    def run_now(self, name: str) -> int: ...

class CronScheduler(Scheduler):
    """Linux/macOS — reads `crontab -l`, writes `crontab -` via stdin."""

class SchtasksScheduler(Scheduler):
    """Windows — generates Task Scheduler XML, invokes
    `schtasks /Create /XML <file> /TN cc-janitor-<name>`."""

def get_scheduler() -> Scheduler:
    return SchtasksScheduler() if sys.platform == "win32" else CronScheduler()
```

This same factory pattern is reused, in microcosm, by `install-hooks` to pick
the POSIX or PowerShell hook command body.

## 4. Feature scope (Phase 2)

### 4.1 Memory editor

**Discovery:** Walk `~/.claude/projects/<X>/memory/*.md` (the path used by
Claude Code's auto-memory) plus `~/.claude/CLAUDE.md` (treated as the
"global user" memory). For each file:

- Parse YAML frontmatter (or absence-thereof; both are valid).
- Classify by `type` frontmatter key, falling back to filename heuristic
  (`feedback_*.md` → feedback, `project_*.md` → project, `research_*.md` →
  reference, otherwise `user`).
- Compute size in bytes, line count, last-modified timestamp.

**Operations:**

- `list` — DataTable in TUI / formatted table or JSON in CLI.
- `show` — render the file (rich Markdown in TUI, plain in CLI).
- `edit` — open in `$EDITOR` (POSIX) or `%EDITOR%` / Notepad (Windows).
  TUI uses Textual's `TextArea` widget for inline edit; CLI shells out.
- `archive` — move to `~/.claude/projects/<X>/memory/.archive/<ts>/`.
  Reversible via `cc-janitor trash restore` (the archive uses the same
  underlying soft-delete primitive).
- `move-type <name> <new-type>` — rewrite the `type:` frontmatter key,
  preserving all other keys via `python-frontmatter` round-trip.
- `find-duplicates` — warn-only. Compute SHA-256 of each non-empty,
  non-bullet, non-header line across all memory files; report lines that
  appear in 2+ files. Never auto-merge.

**Out of scope for Phase 2:** LLM-based memory quality scoring, automatic
deduplication, cross-machine memory sync. (Already declared out of scope at
the master-design level; reaffirmed here.)

### 4.2 Reinject hook (closes Issue #29746)

**Phase 1 already shipped** the consumer side: `cc-janitor install-hooks`
registers a PreToolUse hook in `~/.claude/settings.json` that does
(POSIX shell pseudo):

```sh
test -f ~/.cc-janitor/reinject-pending && \
  { rm ~/.cc-janitor/reinject-pending; \
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse",
           "additionalContext":"cc-janitor-reinject: please re-read MEMORY.md and CLAUDE.md"}}'; } \
  || true
```

**Phase 2 ships** three things:

1. `cc-janitor context reinject [--memory] [--claude-md]` — CLI/TUI command
   that creates `~/.cc-janitor/reinject-pending` (an empty file is enough;
   contents reserved for future flag-passing). Records audit entry. Emits
   a confirmation: "Reinject queued — will fire on next Claude Code tool
   call." Idempotent — multiple writes coalesce.
2. **Memory tab `[r]` button** — same effect, surfaced in the TUI so users
   editing a memory file can immediately queue a reinject.
3. **Windows install-hooks branch** — Phase 1's `install_hooks.py` emits
   only a POSIX shell `test -f ... && { ... } || true` command, which fails
   on Windows where Claude Code uses `cmd.exe` / PowerShell. Phase 2 detects
   `sys.platform == "win32"` and emits a PowerShell equivalent:

   ```powershell
   if (Test-Path "$env:USERPROFILE\.cc-janitor\reinject-pending") {
     Remove-Item "$env:USERPROFILE\.cc-janitor\reinject-pending";
     '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"cc-janitor-reinject: please re-read MEMORY.md and CLAUDE.md"}}'
   }
   ```

   The hook entry in `settings.json` uses `"type": "command"` with the
   PowerShell one-liner wrapped via `powershell.exe -NoProfile -Command "..."`.

### 4.3 Hooks debugger (closes Issues #11544, #10401, #16564)

**Discovery:** Read all four standard `settings.json` layers
(`~/.claude/settings.json`, `~/.claude/settings.local.json`,
`<cwd>/.claude/settings.json`, `<cwd>/.claude/settings.local.json`) plus the
managed-policy file. For each `hooks.<event>[*].hooks[*]` entry produce a
`HookEntry` (see §5).

**Merged view:** TUI Hooks tab is a DataTable with columns
`event | matcher | type | command-preview | source-file | source-scope |
last-status`. Selecting a row shows full source on the right pane plus
last-execution log if logging is on.

**Simulate (`[t]` / `cc-janitor hooks simulate <event> <matcher>`):** Build
a realistic stdin payload for the event, pipe it to the hook command via
`subprocess.run(..., input=stdin_bytes, capture_output=True, timeout=...)`,
display stdout/stderr/exit/duration. The realistic payload library lives in
`core/hooks.py:STDIN_TEMPLATES` (one per event: PreToolUse, PostToolUse,
UserPromptSubmit, Stop, SubagentStop, Notification, SessionStart, SessionEnd,
PreCompact). Templates use sample tool names + inputs from the mock-claude-home
fixture.

**Enable logging (`[l]` / `cc-janitor hooks enable-logging <event>`):**
Wrap the existing command in a tee:

- POSIX: `(<cmd>) 2>&1 | tee -a ~/.cc-janitor/hooks-log/<event>.log`
- Windows: `PowerShell ... | Tee-Object -FilePath "$env:USERPROFILE\.cc-janitor\hooks-log\<event>.log" -Append`

Storing the original command in a sentinel comment (`# cc-janitor-original: <b64>`)
so `disable-logging` can restore it.

**Validate (`cc-janitor hooks validate`):** Schema-check every settings.json
against a hand-written JSON Schema for the hooks block. Report:

- Hooks present in `hooks` but with malformed structure (Issue #11544 pattern:
  user wrote `"PreToolUse": [{...}]` directly without the `hooks` array
  wrapper — Claude Code silently ignores such entries).
- Empty matchers, empty commands.
- Type mismatches.

**Windows env-var compat fix (Issue #16564):** Detect commands that reference
`$TOOL_NAME` or `$EXIT_CODE` (or `%TOOL_NAME%` / `%EXIT_CODE%`) and offer to
generate a stdin-parsing wrapper. The wrapper reads stdin JSON and exports
those values before delegating to the original command. Implementation:
short PowerShell preamble that uses `ConvertFrom-Json`. Surfaced in TUI as
a `[w]` action on a hook row; in CLI as `cc-janitor hooks fix-windows-env <event> <matcher>`.

### 4.4 Scheduler

**TUI Schedule tab:** DataTable of jobs with columns
`name | template | cron | next-run | last-run | last-status | dry-run-pending`.
Actions: `[a]` add (opens template picker), `[r]` remove, `[n]` run-now.

**Templates** (in `core/schedule.py:TEMPLATES`):

| Name | Effect | Default cron |
|------|--------|--------------|
| `perms-prune` | `cc-janitor perms prune --older-than 90d` | weekly Sun 03:00 |
| `trash-cleanup` | `cc-janitor trash empty --older-than 30d` | monthly 1st 04:00 |
| `session-prune` | `cc-janitor session prune --older-than 90d` | monthly 15th 04:00 |
| `context-audit` | `cc-janitor context cost --json >> ~/.cc-janitor/history/cost.jsonl` | daily 00:05 |
| `backup-rotate` | rotate `~/.cc-janitor/backups/` keeping 30 days | weekly Sun 04:00 |

**Add flow (`cc-janitor schedule add <template> [--cron <expr>]`):**

1. `require_confirmed()`.
2. Validate cron expression with `croniter`.
3. Pick scheduler (`get_scheduler()`).
4. Compute the actual command line. Crucially the env vars set on the
   scheduled run are:
   - `CC_JANITOR_USER_CONFIRMED=1` — required so the mutation passes.
   - `CC_JANITOR_SCHEDULED=1` — activates a per-run hard cap (default 200
     items deleted) checked inside `core/safety.py`.
5. Write a per-job manifest to `~/.cc-janitor/schedule/<name>.json` with
   `dry_run_pending: true`. The first run after `add` always passes
   `--dry-run` regardless of the user's intent. The job manifest flips
   `dry_run_pending` to `false` only after a successful (exit 0) dry-run.
6. Register with cron (Linux/macOS) or schtasks (Windows).
7. Append audit entry.

**Live-mode promotion:** A `cc-janitor schedule promote <name>` (manual) or
the next scheduled run (automatic, if dry-run came back exit 0) flips
`dry_run_pending: false` and re-registers without `--dry-run`. The user is
notified via stdout in the next interactive `cc-janitor schedule list`.

**Hard cap (`CC_JANITOR_SCHEDULED=1` semantics):** When set, every soft-delete
and prune call in `core/` checks a per-run counter (kept in a thread-local)
and aborts with `RunawayCapError` after the cap. Audit entry records the
abort.

## 5. Data model

### 5.1 MemoryFile

```python
@dataclass
class MemoryFile:
    path: Path
    type: Literal["user", "feedback", "project", "reference", "unknown"]
    title: str | None             # frontmatter title or H1
    description: str | None       # frontmatter description or first paragraph
    frontmatter: dict             # raw round-trippable
    body: str
    size_bytes: int
    line_count: int
    last_modified: datetime
    project: str | None           # owning project dir under .claude/projects
    is_archived: bool
```

### 5.2 HookEntry

```python
@dataclass
class HookEntry:
    event: str                    # PreToolUse, PostToolUse, ...
    matcher: str                  # tool-name pattern; may be "*"
    type: Literal["command", "url", "subagent"]
    command: str | None
    url: str | None
    timeout: int | None
    source_path: Path             # which settings.json
    source_scope: Literal["user", "user-local", "project", "project-local", "managed"]
    has_logging_wrapper: bool
    last_run: HookRun | None      # populated from hooks-log/

@dataclass
class HookRun:
    ts: datetime
    exit_code: int
    duration_ms: int
    stdout_excerpt: str
    stderr_excerpt: str
```

### 5.3 ScheduledJob

```python
@dataclass
class ScheduledJob:
    name: str                     # "cc-janitor-<template>"
    template: str                 # one of TEMPLATES.keys()
    cron_expr: str
    command: str                  # the resolved CLI line
    next_run: datetime | None
    last_run: datetime | None
    last_status: Literal["ok", "fail", "never"] | None
    dry_run_pending: bool
    backend: Literal["cron", "schtasks"]
```

## 6. CLI surface (Phase 2 additions)

```bash
# Memory
cc-janitor memory list [--type T] [--project P] [--json]
cc-janitor memory show <name>
cc-janitor memory edit <name>                              # mutation
cc-janitor memory archive <name>                           # mutation
cc-janitor memory move-type <name> <new-type>              # mutation
cc-janitor memory delete <name>                            # mutation
cc-janitor memory find-duplicates                          # read-only warn

# Context (additions to Phase 1 group)
cc-janitor context reinject [--memory] [--claude-md]       # mutation

# Hooks
cc-janitor hooks list [--event E] [--source S] [--json]
cc-janitor hooks show <event> <matcher>
cc-janitor hooks simulate <event> <matcher> [--input-file F]
cc-janitor hooks enable-logging <event> [<matcher>]        # mutation
cc-janitor hooks disable-logging <event> [<matcher>]       # mutation
cc-janitor hooks fix-windows-env <event> <matcher>         # mutation
cc-janitor hooks validate

# Schedule
cc-janitor schedule list [--json]
cc-janitor schedule add <template> [--cron "<expr>"]       # mutation
cc-janitor schedule remove <name>                          # mutation
cc-janitor schedule run <name>                             # ad-hoc run
cc-janitor schedule promote <name>                         # mutation (flip dry-run-pending)
cc-janitor schedule audit
```

All mutations require `CC_JANITOR_USER_CONFIRMED=1` and append to audit log.
Read-only commands (`list`, `show`, `simulate`, `validate`, `audit`) are free
for Claude Code to invoke from inside a session.

## 7. TUI screens

Phase 2 replaces three placeholder tabs from Phase 1 with real screens.

**Memory tab (#4):** DataTable (`name | type | size | modified | project`)
+ right-pane preview. Footer keys: `e` edit, `m` move-type, `a` archive,
`r` reinject, `f` find-duplicates, `/` filter, `?` actions.

**Hooks tab (#5):** DataTable (`event | matcher | type | command-preview |
source | last-status`) + right pane showing full source + last execution
log if any. Footer: `t` simulate, `l` toggle logging, `v` open source in
$EDITOR, `w` fix-windows-env, `?` actions.

**Schedule tab (#6):** DataTable (`name | template | cron | next-run |
last-run | status | dry-run-pending`). Footer: `a` add (opens modal with
template picker + cron field with live `croniter` validation), `r` remove,
`n` run-now, `p` promote.

Each screen has its own snapshot test in `tests/tui/`.

## 8. Testing strategy

Phase 1 strategy carries over verbatim. Phase 2 additions:

- **Memory tests** use the existing `mock-claude-home` fixture, extended
  with three sample memory files (one per type, one with frontmatter, one
  without) and one `.archive/` subdir.
- **Hooks tests** use a settings.json fixture with five hooks across three
  scope layers, including one malformed-structure entry that
  `validate` must flag (Issue #11544 reproduction).
- **Schedule tests** mock `subprocess.run` for both `crontab` and `schtasks`
  paths. Property tests with hypothesis: any sequence of add/remove/promote
  preserves manifest invariants (no orphan crontab line, no
  `dry_run_pending: false` without a successful dry run record).
- **Reinject test** asserts that `context reinject` writes the marker file
  and is idempotent across multiple invocations.
- **Cross-platform branching** tested via `monkeypatch.setattr("sys.platform", ...)`
  for both `install-hooks` and `get_scheduler()`.

Coverage target unchanged: 90%+ on `core/`.

## 9. Documentation deliverables

- **`docs/cookbook.md`** — append four new recipes:
  - "Memory hygiene — find duplicates, move feedback to user-level"
  - "My memory edits don't take effect — use reinject"
  - "My hook isn't firing — debug it without --debug"
  - "Schedule weekly automatic cleanups"
- **`docs/CC_USAGE.md`** — append the new read-only / mutating subcommand
  list (Memory/Hooks/Schedule) so Claude Code knows which Phase 2 commands
  it can call freely vs which require user confirmation.
- **`README.md` / `README.ru.md`** — feature-list section gains a "Phase 2"
  bullet group with three screenshots (Memory, Hooks, Schedule tabs).
- **`CHANGELOG.md`** — promote `[Unreleased]` Phase 1 block to `[0.1.0]` (if
  not already done) and start a fresh `[0.2.0]` block for Phase 2
  deliverables.

## 10. Out of scope for Phase 2 (deferred to Phase 3)

- ❌ Monorepo nested `.claude/` discovery (Issues #37344, #35561) — Phase 3.
- ❌ Auto-reinject background watcher (file-watch on memory dir, autoqueue
  reinject) — Phase 3, opt-in only.
- ❌ Shell completions (bash, zsh, PowerShell) — Phase 3.
- ❌ Stats dashboard / cross-machine config bundle — Phase 3.
- ❌ TUI in-place memory move-via-drag — keyboard `m` action only.
- ❌ Hook authoring UI — Phase 2 only debugs existing hooks; `cc-janitor
  hooks add` deferred.
- ❌ Schtasks AT-time triggers — Phase 2 supports cron-style only,
  translating to schtasks `/SC` flags. Calendar-based triggers (e.g.
  "first Monday of month") deferred.

## 11. Open questions for implementation planning

1. **Editor invocation on Windows where `EDITOR` is unset** — fall back to
   `notepad.exe` or to Textual's built-in `TextArea`? Tentative decision:
   try `EDITOR`, else `VISUAL`, else `notepad.exe` on Windows /
   `vi` on POSIX. Same heuristic git uses.
2. **Schtasks privilege** — `schtasks /Create` for the current user does
   not require admin; cross-user does. Phase 2 only supports current-user
   tasks. Document this.
3. **Hard-cap default value** — 200 items per scheduled run. Should this be
   per-template-customisable in `~/.cc-janitor/config.toml`? Tentative: yes,
   single global key `[schedule] hard_cap = 200`.
4. **Memory `unknown` type policy** — when a memory file has no frontmatter
   and the filename does not match a known prefix, do we offer to assign a
   type or surface as `unknown` and let the user `move-type`? Tentative:
   surface as `unknown` and rely on the `move-type` flow.
5. **Reinject marker contents** — currently empty file. Should it carry the
   `--memory` / `--claude-md` flags so the consumer hook can build a more
   targeted system-reminder? Deferred to first user feedback.

## 12. Approval trail

- Scope: Phase 2 covers Memory editor, Reinject hook, Hooks debugger,
  Scheduler — explicitly approved as the "comfort + Claude bug-relief"
  block in the master design (§4.2).
- Tech additions: `python-frontmatter`, `croniter` — approved.
- Cross-platform: equal-footing Windows/POSIX support, with one extra
  platform-branch in `install-hooks` and one in `get_scheduler()`.
- Mutation/audit semantics carry from Phase 1 unchanged.
- Dry-run-first guard for scheduled jobs: approved as default-on, no opt-out.
- Hard cap on scheduled deletions (`CC_JANITOR_SCHEDULED=1` activates it):
  approved at 200 items, configurable via `config.toml`.
- Out-of-scope items above are explicitly deferred to Phase 3.

---

**Next step:** invoke the `superpowers:writing-plans` skill to turn this
design into a step-by-step implementation plan with concrete tasks. The
companion document `docs/plans/2026-05-05-cc-janitor-phase2-mvp.md` is the
output of that step.
