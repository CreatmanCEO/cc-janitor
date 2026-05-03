# cc-janitor — Design Document

> **Date:** 2026-05-03
> **Author:** @CreatmanCEO
> **Status:** Approved, ready for implementation planning

## 1. Problem statement

Power users of Claude Code accumulate friction across five areas that no existing
third-party tool addresses together:

1. **Sessions** — dozens of unnamed `.jsonl` transcripts pile up in
   `~/.claude/projects/<project>/`, with no built-in way to list, preview,
   search, or bulk-delete from the CLI. `/resume` shows them but can't remove them.
2. **Permissions** — `.claude/settings.local.json` and `~/.claude.json` grow to
   hundreds of `Bash(...)` allow rules. Stale rules ship in every request,
   silently inflating token cost.
3. **Context** — CLAUDE.md hierarchy + memory files + skills listings all add
   to the recurring per-request payload. Users have no visibility into the byte
   or token cost of what's loaded.
4. **Hooks** — `/hooks` sometimes reports "no hooks configured" despite valid
   config; on Windows, missing env vars (`TOOL_NAME`, `EXIT_CODE`) break logging
   workflows; debugging requires `--debug` flag.
5. **Maintenance** — none of the above is automatable on a schedule.

This document specifies **`cc-janitor`** — an open-source Python TUI/CLI that
unifies all five concerns with hygiene-first defaults (soft-delete, audit log,
backups before write, confirmation gates).

### Reference (popular GitHub issues this addresses)

- [#34318 CLI session naming on startup](https://github.com/anthropics/claude-code/issues/34318)
- [#34157 Expose session management as tools](https://github.com/anthropics/claude-code/issues/34157)
- [#29971 Context bloat](https://github.com/anthropics/claude-code/issues/29971)
- [#29746 Memory not re-read on context continuation](https://github.com/anthropics/claude-code/issues/29746)
- [#11544 Hooks not loading from settings.json](https://github.com/anthropics/claude-code/issues/11544)
- [#10401 Hooks require --debug flag](https://github.com/anthropics/claude-code/issues/10401)
- [#16564 Windows: missing TOOL_NAME / EXIT_CODE env vars in hooks](https://github.com/anthropics/claude-code/issues/16564)
- [#722 CLAUDE.md discovery docs inconsistent](https://github.com/anthropics/claude-code/issues/722)
- [#2766 Large CLAUDE.md performance warning](https://github.com/anthropics/claude-code/issues/2766)

## 2. Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| Language | Python 3.11+ | User has it for tg-promoter, diabot |
| TUI | [Textual](https://textual.textualize.io/) ≥ 0.80 | Most polished TUI in 2026, devtools, snapshot tests |
| CLI | [Typer](https://typer.tiangolo.com/) ≥ 0.12 | Same author as FastAPI; clean argparse-replacement |
| Token counting | [tiktoken](https://github.com/openai/tiktoken) | `cl100k_base` close enough for Claude (±5%) |
| JSON preserving | rapidjson + tomlkit | Don't lose comments/order on settings.json edits |
| Distribution | PyPI via [uv tool](https://docs.astral.sh/uv/) / pipx | Cross-platform, isolated venvs, no npm |
| Test (unit) | pytest | Standard |
| Test (TUI) | [pytest-textual-snapshot](https://github.com/Textualize/pytest-textual-snapshot) | Regression-proof screen rendering |
| Test (property) | hypothesis | For JSON edits — never lose fields |

## 3. Architecture

### 3.1 Repo layout

```
cc-janitor/
├── pyproject.toml
├── README.md                       # English, hero + features + screenshots
├── README.ru.md                    # Russian
├── CHANGELOG.md                    # documents ALL changes (per user policy)
├── LICENSE                         # MIT
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                  # pytest + textual-snapshot + ruff
│   │   └── release.yml             # PyPI + GitHub Release on tag
│   └── ISSUE_TEMPLATE/
├── docs/
│   ├── plans/                      # design docs (this file)
│   ├── cookbook.md                 # recipes per use-case
│   ├── architecture.md             # for contributors
│   ├── CC_USAGE.md                 # for ~/.claude/CLAUDE.md inclusion
│   └── screenshots/
├── src/cc_janitor/
│   ├── __main__.py                 # entry: no args = TUI, args = CLI
│   ├── i18n/
│   │   ├── en.toml
│   │   └── ru.toml
│   ├── core/                       # business logic, no UI
│   │   ├── sessions.py
│   │   ├── permissions.py
│   │   ├── context.py
│   │   ├── hooks.py
│   │   ├── memory.py
│   │   ├── scheduler.py
│   │   ├── audit.py
│   │   └── safety.py               # soft-delete, undo, USER_CONFIRMED guard
│   ├── tui/                        # Textual UI
│   │   ├── app.py
│   │   └── screens/                # one file per top-level screen
│   └── cli/                        # Typer CLI commands
│       └── commands/
└── tests/
    ├── unit/
    ├── tui/
    └── data/                       # mock-claude-home fixture
```

### 3.2 Architectural principles

1. **Single binary, two modes.** Same Python package serves both TUI and CLI.
   Argv-parsing entry decides: no args → Textual app, with args → Typer CLI.
2. **`core/` knows nothing about UI.** Pure functions returning dataclasses.
   Both TUI and CLI consume the same core. Tested independently.
3. **i18n via TOML + `t()` helper.** No Babel/gettext overhead. Auto-detect
   from `LANG` / Windows culture; override via `--lang` or `CC_JANITOR_LANG`.
   F2 hot-switches in TUI. Subcommand names and JSON-output keys stay English
   (stability for scripts and Claude Code).
4. **Safety by default.** Mutations require `CC_JANITOR_USER_CONFIRMED=1`.
   Deletes are soft (move to `~/.cc-janitor/.trash/<ts>/`, 30-day retention).
   Backups before write to `~/.cc-janitor/backups/<file-hash>/<ts>.json`.
5. **Audit log is always on.** Every CLI invocation and every TUI mutation
   appends a JSONL record to `~/.cc-janitor/audit.log` (rotated at 10 MB).
6. **State location:** `~/.cc-janitor/` (cache, trash, backups, audit, config,
   schedule artifacts). Configurable via `CC_JANITOR_HOME`.

### 3.3 Claude Code integration model

`cc-janitor` is meant to be invokable both by the human (TUI) and by Claude
Code from within an active session (CLI), but only on the human's explicit
request.

The boundary:

- **Read-only commands** — `list`, `show`, `audit`, `cost`, `summary`, etc. —
  Claude Code may invoke freely. No mutation possible.
- **Mutating commands** — `delete`, `prune`, `dedupe`, `edit`, `disable`,
  `add` — refuse to run unless `CC_JANITOR_USER_CONFIRMED=1` is set in the
  environment.
- The user grants confirmation by either:
  - typing the literal phrase to Claude (e.g. "yes, prune those"), at which
    point Claude is instructed (via `docs/CC_USAGE.md` injected into
    `~/.claude/CLAUDE.md`) to prefix the next mutating call with
    `CC_JANITOR_USER_CONFIRMED=1`, OR
  - running the command themselves in a separate terminal.
- Every invocation is recorded in audit log with `user_confirmed: bool` and
  `mode: "cli"|"tui"|"scheduled"`.

This combines safety with ergonomics: Claude can clean up stale rules in the
same session it discovered them, but cannot do so silently.

## 4. Feature scope

### 4.1 Phase 1 (MVP, ~5–7 days) — "closes 80% of pain"

**Sessions:**
- TUI list with: ID, project, date, size, message count, first-user-msg
  preview, total tokens estimate.
- Filter/search across project (substring or full-text-FTS opt-in).
- Multi-select delete with soft-delete to `.trash/`.
- Preview pane shows: metadata + summaries (compact-summary from JSONL +
  user-side `index-session.sh` markdown if present + first user message).
- CLI: `cc-janitor session list|show|search|summary|delete|export|prune`.

**Permissions:**
- Effective rules merged across all sources (global + project, settings.json
  + settings.local.json + `~/.claude.json` approvedTools).
- For each rule: source, last-matched timestamp, match count, "stale" flag
  (no matches in last 90 days, threshold configurable).
- Dedupe detection: subsumed (`Bash(git *)` ⊃ `Bash(git status)`),
  exact dups across files, conflicting overlap (warn, do not auto-fix),
  empty/whitespace patterns.
- Diff-preview before write; backup before write.
- CLI: `cc-janitor perms scan|audit|list|dedupe|prune|remove|add|diff`.

**Context inspector:**
- Hierarchy of CLAUDE.md (global + cwd-up walk) with size/token cost.
- Memory files listing with type / description / line count.
- Skills listing from enabled plugins + local + plugin source.
- Permissions cost block (link to perms screen).
- Aggregate "estimated context per request" + dollar estimate at Opus rates.
- CLI: `cc-janitor context show|cost|find-duplicates|disable`.

### 4.2 Phase 2 (~3–5 days) — "comfort + Claude bug-relief"

**CLAUDE.md / Memory editor:**
- Open in `$EDITOR` (Notepad on Windows by default).
- Duplicate-line detection across files.
- "Reinject" mechanism: write a marker to `~/.cc-janitor/reinject-pending`
  → PreToolUse hook (auto-installed by `cc-janitor install-hooks`) reads it
  on next tool call and emits a system-reminder injecting fresh memory.
  Closes Issue #29746.
- Memory move/archive between types (`user`/`feedback`/`project`/`reference`).

**Hooks debugger:**
- Merged view of all hooks from all settings sources.
- Trigger simulation: build realistic stdin payload for tool event, pipe
  to hook command, capture stdout/stderr/exit/duration. No `--debug` needed.
- Optional logging wrapper: `cc-janitor hooks enable-logging <event>` wraps
  the command in `tee ~/.cc-janitor/hooks-log/<event>.log`.
- Schema validation for all `settings.json` files; broken JSON highlighted.
- Windows env-var fix: detect missing `TOOL_NAME`/`EXIT_CODE` and offer to
  generate a wrapper that sets them from stdin JSON. Closes Issue #16564.

**Scheduler:**
- Cross-platform wrapper: Windows `schtasks.exe` / Unix `cron`.
- Pre-built job templates: `perms-prune`, `trash-cleanup`, `session-prune`,
  `context-audit`, `backup-rotate`.
- Each scheduled run sets `CC_JANITOR_USER_CONFIRMED=1` AND
  `CC_JANITOR_SCHEDULED=1`. The latter activates a per-run hard cap (refuse
  to delete more than N items) — protects against runaway scripts.
- First run is `--dry-run` automatically; only after a successful prove run
  does the live mode activate.

### 4.3 Phase 3 (~3–5 days) — "nice-to-have"

- Monorepo nested `.claude/` discovery (Issue #37344, #35561).
- Auto-reinject watcher (background daemon, opt-in).
- Stats dashboard: tokens/cost/time per project, exported as
  `~/.cc-janitor/history/`.
- Export/import config bundle for cross-machine sync (no auto-sync).
- Shell completions: bash, zsh, PowerShell.

## 5. Data model

### 5.1 Sessions

```python
@dataclass
class SessionSummary:
    source: Literal["jsonl_compact", "user_indexer_md", "first_msg"]
    text: str
    timestamp: datetime | None
    md_path: Path | None  # for user_indexer_md

@dataclass
class Session:
    id: str                    # UUID from filename
    project: str               # ~/.claude/projects/<dir>
    jsonl_path: Path
    started_at: datetime
    last_activity: datetime
    size_bytes: int
    message_count: int
    first_user_msg: str
    last_user_msg: str
    tokens_estimate: int       # tiktoken cl100k_base
    compactions: int
    related_dirs: list[Path]   # subagents/, tool-results/, todos/
    summaries: list[SessionSummary]
```

Cache: `~/.cc-janitor/cache/sessions.json`, invalidated per-file by mtime.
Initial scan: <2s for ~50 sessions / 300 MB on a typical SSD after first index.

### 5.2 Permissions

```python
@dataclass
class PermSource:
    path: Path
    scope: Literal["user", "user-local", "project", "project-local",
                   "managed", "approved-tools"]

@dataclass
class PermRule:
    tool: str                  # "Bash", "Edit", "Read", ...
    pattern: str               # raw rule body, e.g. "git *"
    decision: Literal["allow", "deny", "ask"]
    source: PermSource
    last_matched_at: datetime | None
    match_count_30d: int
    match_count_90d: int
    stale: bool                # 0 matches in last 90d (configurable)

@dataclass
class PermDup:
    kind: Literal["subsumed", "exact", "conflict", "empty"]
    rules: list[PermRule]
    suggestion: str            # human-readable action
```

Match algorithm reuses the same glob semantics Claude Code uses (`fnmatch`-
style with `*` wildcard for command-line tail). Reconstruction of usage walks
JSONL transcripts in `~/.claude/projects/*/*.jsonl`, extracts every `tool_input`
for matching tool names, runs match against every rule, accumulates counts.

### 5.3 Audit

```python
@dataclass
class AuditEntry:
    ts: datetime
    mode: Literal["cli", "tui", "scheduled"]
    user_confirmed: bool
    cmd: str
    args: list[str]
    session_id: str | None     # if invoked from a Claude Code session
    exit_code: int
    changed: dict | None       # arbitrary structured "what changed" payload
    backup_path: Path | None
```

Persisted as JSONL to `~/.cc-janitor/audit.log`, rotated at 10 MB.

## 6. CLI surface (full reference)

```bash
# Global
cc-janitor                                  # launch TUI
cc-janitor --version
cc-janitor --help
cc-janitor --lang ru                        # override language

# Sessions
cc-janitor session list [--project P] [--json]
cc-janitor session show <id> [--full]
cc-janitor session search "<query>" [--regex]
cc-janitor session summary <id> [--source jsonl_compact|user_indexer_md|first_msg]
cc-janitor session delete <id>...           # mutation
cc-janitor session export <id> --format md
cc-janitor session prune --older-than 90d [--dry-run]   # mutation

# Permissions
cc-janitor perms scan
cc-janitor perms audit
cc-janitor perms list [--source S] [--stale] [--dup] [--json]
cc-janitor perms dedupe [--dry-run]                     # mutation
cc-janitor perms prune --older-than 90d [--dry-run]     # mutation
cc-janitor perms remove "<rule>" [--from FILE]          # mutation
cc-janitor perms add "<rule>" --to user-local           # mutation
cc-janitor perms diff <commit-sha>          # if file under git

# Context
cc-janitor context show [--project PATH]
cc-janitor context cost
cc-janitor context find-duplicates
cc-janitor context disable <path>                       # mutation
cc-janitor context reinject                             # mutation (writes marker)

# Memory
cc-janitor memory list [--type T] [--stale]
cc-janitor memory show <name>
cc-janitor memory edit <name>                           # mutation (opens $EDITOR)
cc-janitor memory delete <name>                         # mutation
cc-janitor memory archive <name>                        # mutation

# Skills
cc-janitor skills list [--unused]
cc-janitor skills disable <name>                        # mutation

# Hooks
cc-janitor hooks list [--source S] [--event E]
cc-janitor hooks show <event> <matcher>
cc-janitor hooks simulate <event> <matcher> [--input-file F]
cc-janitor hooks enable-logging <event>                 # mutation
cc-janitor hooks disable <event> <matcher>              # mutation
cc-janitor hooks validate

# Schedule
cc-janitor schedule list
cc-janitor schedule add <template> [--cron "<expr>"]    # mutation
cc-janitor schedule remove <name>                       # mutation
cc-janitor schedule run <name>                          # ad-hoc run
cc-janitor schedule audit

# Trash
cc-janitor trash list
cc-janitor trash restore <id>                           # mutation
cc-janitor trash empty                                  # mutation

# Audit
cc-janitor audit list [--since 7d] [--cmd <pattern>] [--failed] [--json]
cc-janitor undo <audit-entry-id>                        # mutation

# Setup
cc-janitor install-hooks                                # mutation (registers reinject hook)
cc-janitor doctor                                       # health check
```

## 7. TUI screens

Top-level navigation tabs:

1. **Sessions** (default) — list + preview pane
2. **Permissions** — effective rules + sources panel
3. **Context** — hierarchy tree + cost block
4. **Memory** — list + edit
5. **Hooks** — list + simulate + history
6. **Schedule** — jobs list + edit
7. **Audit** — log viewer + undo

Common keys: F1 help, F2 lang switch, F10 quit, `/` filter, `?` action menu.

Each screen has its own snapshot test in `tests/tui/`.

## 8. Testing strategy

| Layer | Tool | Target coverage |
|-------|------|-----------------|
| `core/` | pytest unit | 90%+ |
| TUI screens | pytest-textual-snapshot | smoke per screen |
| CLI commands | typer.testing.CliRunner | per subcommand |
| JSON edits | hypothesis property tests | never lose fields |
| Integration | mock-claude-home fixture | happy paths |

Fixtures under `tests/data/mock-claude-home/` mimic a realistic
`~/.claude` tree with multiple projects, varied settings, JSONL samples,
permission rules. Tests use `monkeypatch.setenv("HOME", tmp_path)` and
never touch real user data.

TDD discipline: `core/` always test-first. UI/CLI follow.

## 9. Documentation deliverables (priority for this project)

> User explicitly requested: maximum clarity per use-case.

1. **`README.md` (English)** — hero, install (`pipx install cc-janitor`),
   1-minute getting-started, screenshots/GIFs of each screen, full feature list.
2. **`README.ru.md`** — Russian variant, identical structure.
3. **`docs/cookbook.md`** — task-oriented recipes:
   - "I have 200+ permission rules — clean them up"
   - "I want to see how much my CLAUDE.md hierarchy is costing me"
   - "I want to delete sessions older than 90 days"
   - "My hook isn't firing — debug it"
   - "Schedule weekly cleanup"
   - "Use cc-janitor from inside a Claude Code session"
   - Each recipe: problem → command(s) → expected output → next steps.
4. **`docs/architecture.md`** — for contributors, mirrors §3 of this doc.
5. **`docs/CC_USAGE.md`** — short reference written specifically to be
   appended to `~/.claude/CLAUDE.md`. Tells Claude Code how to use cc-janitor:
   which subcommands are read-only (free to call), which are mutating (require
   user-spoken confirmation), how to set `CC_JANITOR_USER_CONFIRMED=1`.
6. **In-tool help** — `cc-janitor --help` and `cc-janitor <cmd> --help` carry
   the same examples as the cookbook for that recipe.

## 10. Out of scope (YAGNI)

- ❌ Web UI — TUI sufficient.
- ❌ Multi-machine sync — local admin tool only.
- ❌ Telemetry — privacy-first, nothing leaves the machine.
- ❌ Plugin system for cc-janitor itself.
- ❌ Docker image — Python tool, install via uv/pipx.
- ❌ Marketing copy in this design — separate effort.
- ❌ LLM-based memory quality scoring — too expensive, too subjective.
- ❌ Auto-merge of duplicate memory entries — only highlight, never auto-fix.

## 11. Open questions for implementation planning

These are deferred to the writing-plans phase:

1. Exact ordering of phase-1 deliverables (sessions first or permissions
   first — both deliver standalone value).
2. Cache schema versioning strategy (when format changes between releases).
3. Windows-specific paths and behaviors (e.g. `~/.cc-janitor` resolves to
   `%USERPROFILE%\.cc-janitor`; `schtasks.exe` shell-escaping rules).
4. Performance budget per command (target: `cc-janitor session list` < 500 ms
   warm, < 3 s cold on 50 sessions / 300 MB).
5. Localization of error messages (currently planned: yes, via same TOML
   keys, but full key inventory deferred to implementation).

## 12. Approval trail

- Scope: C+E (full unified housekeeping tool covering 5 pain areas)
- Tech stack: Python + Textual
- Languages: English + Russian
- Auth model: read-only free for Claude / mutations require
  `CC_JANITOR_USER_CONFIRMED=1` env + audit log on every action
- Phases: 3 (MVP / comfort+Claude-bug-relief / nice-to-have)
- Name: `cc-janitor` (free on PyPI, npm, no GitHub conflicts)
- Marketing: out of scope for this design (delegated to a different agent)

Each section above (1, 2, 3, 4, 5, 6 of the brainstorming flow) was
explicitly approved by the user before this document was written.

---

**Next step:** invoke the `superpowers:writing-plans` skill to turn this
design into a step-by-step implementation plan with concrete tasks.
