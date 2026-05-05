# cc-janitor — usage reference for Claude Code

This file is meant to be appended to your `~/.claude/CLAUDE.md` so Claude Code
knows when and how to invoke cc-janitor.

## When to use cc-janitor

If the user mentions cleaning up sessions, permissions, CLAUDE.md, memory
files, or "context cost" — cc-janitor's read-only commands can be called
freely. Mutating commands require the user to set
`CC_JANITOR_USER_CONFIRMED=1` and explicitly say "yes" / "do it" / "proceed".

## Read-only commands (call freely)

```bash
cc-janitor session list [--project P]
cc-janitor session show <id>
cc-janitor session summary <id>
cc-janitor session search "<query>"
cc-janitor perms audit
cc-janitor perms list [--stale] [--dup]
cc-janitor context show
cc-janitor context cost
cc-janitor context find-duplicates
```

## Mutating commands (require user confirmation)

```bash
cc-janitor session delete <id>...
cc-janitor session prune --older-than 90d
cc-janitor perms dedupe
cc-janitor perms prune --older-than 90d
cc-janitor perms remove "<rule>" --from <path>
cc-janitor perms add "<rule>" --to <scope>
```

For each, prefix the command with `CC_JANITOR_USER_CONFIRMED=1 ` ONLY when the
user has explicitly authorized the action in this conversation. Every
invocation is recorded in `~/.cc-janitor/audit.log`.

## Dry-run when in doubt

Most mutating commands accept `--dry-run` to preview without applying.
Prefer dry-run when explaining what cc-janitor would do.
