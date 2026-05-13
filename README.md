# cc-janitor

Tidy up your Claude Code environment — sessions, permissions, context, hooks.

The first unified TUI/CLI that combines session cleanup, permission pruning,
CLAUDE.md/memory inspection, hook debugging (Phase 2), and scheduled
maintenance (Phase 2) — all the chores no one else automates, in one tool.

**Languages:** English / Русский (toggle with F2 in TUI, `--lang ru` in CLI)

## Stack

- **Language:** Python 3.11+
- **TUI:** [Textual](https://textual.textualize.io/) (terminal UI framework)
- **CLI:** [Typer](https://typer.tiangolo.com/)
- **Token estimation:** OpenAI `tiktoken` (cl100k_base, ~5% off for Claude)
- **Tests:** pytest + pytest-asyncio + pytest-textual-snapshot
- **Distribution:** PyPI via `uv tool` / `pipx`

## Features (Phase 1 MVP)

### Sessions
- List, search, preview Claude Code sessions in `~/.claude/projects/`
- Soft-delete to recoverable trash; restore from trash via `cc-janitor trash restore`
- Inspect compact-summaries and your own indexer markdown summaries

### Permissions
- Discover all rules across global / project, settings.json / .local.json, and `~/.claude.json` approvedTools
- Mark stale rules (no match in last 90 days) by scanning your transcripts
- Dedupe (subsumed/exact) and prune (stale) — with backups before write

### Context inspector
- Walk CLAUDE.md hierarchy, list memory files, list enabled skills
- Compute byte/token cost per file + recurring-per-request total
- Show estimated $ at Opus input rate

## Install

```bash
# From PyPI (recommended)
uv tool install cc-janitor
# or
pipx install cc-janitor

# Optional watcher extra (background dream-snapshot daemon)
uv tool install "cc-janitor[watcher]"

# From source for development
git clone https://github.com/CreatmanCEO/cc-janitor && cd cc-janitor
uv sync --all-extras
uv run cc-janitor
```

## Quick start

```bash
# Launch TUI
cc-janitor

# CLI: list sessions
cc-janitor session list

# Audit your permission rules
cc-janitor perms audit

# Inspect what your context costs you per request
cc-janitor context cost

# Mutating commands require explicit confirmation:
CC_JANITOR_USER_CONFIRMED=1 cc-janitor session prune --older-than 90d
```

## Safety model

cc-janitor never silently destroys data:

- **`CC_JANITOR_USER_CONFIRMED=1` gate:** every mutating command refuses to run unless this env var is set. Read-only commands (list, show, audit, cost) are always free to call.
- **Soft-delete:** sessions deleted move to `~/.cc-janitor/.trash/<timestamp>/` for 30 days. Restore via `cc-janitor trash restore <id>`.
- **Backups before write:** every settings.json edit creates a timestamped backup in `~/.cc-janitor/backups/<sha-of-path>/`.
- **Audit log:** every mutating action appends a JSONL record to `~/.cc-janitor/audit.log` (rotates at 10 MB).

> **Windows users:** `cc-janitor install-hooks` writes a POSIX shell snippet (`test -f`, `&&`). On native Windows without Git Bash / WSL the hook will fail silently. Cross-platform PowerShell support lands in 0.2.0 (Phase 2). Use Git Bash or WSL in the meantime.

## Using from inside Claude Code

cc-janitor is designed to be invoked by both you (TUI / CLI) and Claude Code itself (CLI), but only on your explicit request. See [docs/CC_USAGE.md](docs/CC_USAGE.md) for the reference Claude Code reads when deciding whether a subcommand is safe to call.

## Dream safety net (Phase 4)

Snapshot the per-project memory dir before each Auto Dream cycle, diff
afterwards, roll back if needed. Verified against upstream Claude Code
Issues #47959 (silent Auto Dream memory deletion), #50694 (stale
`.consolidate-lock`), #38493 (missing `.dream-log.md`), #38461
(server-gate inference).

```bash
# Opt-in: poll lock files and snapshot around every Auto Dream cycle
CC_JANITOR_USER_CONFIRMED=1 cc-janitor watch start --dream

# Review what each Dream cycle changed
cc-janitor dream history
cc-janitor dream diff <pair_id>

# 10 health checks covering stale locks, autoDream flag, disk, hygiene
cc-janitor dream doctor

# Roll back if Dream rewrote something you wanted
CC_JANITOR_USER_CONFIRMED=1 cc-janitor dream rollback <pair_id> --apply

# And undo the rollback if you change your mind
cc-janitor undo --apply
```

Rollback is reversible via `cc-janitor undo`. Tar-compacted pairs
(weekly `dream-tar-compact` job) remain diffable and rollback-able —
extraction happens transparently. Settings backups and Dream mirrors
live in separate subtrees of `~/.cc-janitor/backups/`; `backups prune`
no longer touches Dream restore points by default.

Tunable thresholds live in `~/.cc-janitor/config.toml`; scaffold one with
`cc-janitor config init`.

## Roadmap

- [x] **Phase 1** — sessions / permissions / context inspector / CLI / TUI / safety primitives
- [x] **Phase 2** — memory editor, reinject hook, hook debugger with simulation, scheduler (cron / Task Scheduler)
- [x] **Phase 3** — monorepo nested `.claude/` discovery, auto-reinject watcher, stats dashboard, export/import config
- [x] **Phase 4** — Dream safety net (snapshot/diff/doctor/rollback), sleep-hygiene metrics, settings audit hook
- [ ] **Phase 5** — cross-platform hook fixers, `dream fix-stale-lock`, mutating Dream TUI actions, full I10/I11 closure

## Contributing

Issues and PRs welcome. See [docs/architecture.md](docs/architecture.md) for the codebase tour.

## License

MIT — see [LICENSE](LICENSE).
