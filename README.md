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
# Recommended — uv tool (isolated, fast)
uv tool install cc-janitor

# Or pipx
pipx install cc-janitor

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

## Using from inside Claude Code

cc-janitor is designed to be invoked by both you (TUI / CLI) and Claude Code itself (CLI), but only on your explicit request. See [docs/CC_USAGE.md](docs/CC_USAGE.md) for the reference Claude Code reads when deciding whether a subcommand is safe to call.

## Roadmap

- [x] **Phase 1** (this release): sessions / permissions / context inspector / CLI / TUI / safety primitives
- [ ] **Phase 2**: memory editor, reinject hook, hook debugger with simulation, scheduler (cron / Task Scheduler)
- [ ] **Phase 3**: monorepo nested .claude/ discovery, auto-reinject watcher, stats dashboard, export/import config

## Contributing

Issues and PRs welcome. See [docs/architecture.md](docs/architecture.md) for the codebase tour.

## License

MIT — see [LICENSE](LICENSE).
