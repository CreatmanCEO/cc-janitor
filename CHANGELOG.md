# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-05-09

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
- i18n keys for memory/hooks/schedule screens (en + ru)

#### Quality
- 50+ new unit and integration tests across memory, hooks, schedule,
  reinject, safety hard cap (152 passing total)
- 3 new TUI snapshot tests
- Cross-platform branching tested via `monkeypatch.setattr("sys.platform", ...)`

## [0.1.1] — 2026-05-05

### Added
- `cc-janitor trash list/restore/empty` subcommands — completes the soft-delete → restore round-trip promised in v0.1.0
- `cc-janitor audit list [--since][--cmd][--failed][--json]` — first user-facing read access to the audit log

### Documentation
- README install instructions now use `git+https://...` since the package isn't on PyPI yet
- README and README.ru add a Windows limitation callout for `install-hooks` (Phase 2 will add PowerShell support)

### Added — Phase 1 MVP

#### Foundation
- State directory resolution with `CC_JANITOR_HOME` override, tilde expansion, whitespace hardening
- Append-only JSONL audit log with rotation and Cyrillic-safe round-trip
- Safety primitives: `CC_JANITOR_USER_CONFIRMED` gate, collision-resistant soft-delete, no-overwrite restore
- TOML-based i18n with English/Russian translations and lang detection
- Mock-claude-home test fixture for downstream tests

#### Sessions
- JSONL parsing with tolerance for truncated lines and content blocks
- Per-project discovery with mtime+size cache invalidation
- Indexer markdown summary linking
- Atomic session deletion with related-dir bundling

#### Permissions
- Discovery across all 5 settings.json layers + `~/.claude.json` approvedTools
- Usage analysis via transcript tool_use scan
- Dedupe detection (subsumed / exact / conflict / empty)
- Write-back with timestamped backups

#### Context inspector
- CLAUDE.md hierarchy walk
- Memory files indexing
- Enabled skills listing
- Token cost aggregation with $ estimate

#### CLI surface
- Typer-based skeleton with `--version`, `--lang`, and 3 subcommand groups
- Session subcommands: list/show/summary/delete/prune/search
- Perms subcommands: audit/list/dedupe/prune/remove/add
- Context subcommands: show/cost/find-duplicates
- Audit-log integration on every mutating subcommand

#### TUI surface
- Textual app skeleton with 7 tabs (3 wired in Phase 1, 4 placeholders for Phase 2)
- Sessions screen: DataTable + preview pane
- Permissions screen: DataTable + summary panel
- Context screen: DataTable + totals panel

#### Documentation
- README in English and Russian
- CHANGELOG following Keep-a-Changelog
- Cookbook with 6 recipes
- CC_USAGE.md for inclusion in user's `~/.claude/CLAUDE.md`

#### Quality
- 90+ unit and integration tests across foundation, sessions, permissions, context, CLI, TUI
- GitHub Actions CI (matrix Python 3.11/3.12 × ubuntu/windows) and release workflows
