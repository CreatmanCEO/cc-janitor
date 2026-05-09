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
cc-janitor memory list [--type <t>]
cc-janitor memory show <path>
cc-janitor memory find-duplicates
cc-janitor hooks list
cc-janitor hooks show <event> <matcher>
cc-janitor hooks simulate <event> <matcher>
cc-janitor hooks validate
cc-janitor schedule list
cc-janitor schedule audit
cc-janitor audit list [--since][--cmd][--failed][--json]
cc-janitor trash list
```

## Mutating commands (require user confirmation)

```bash
cc-janitor session delete <id>...
cc-janitor session prune --older-than 90d
cc-janitor perms dedupe
cc-janitor perms prune --older-than 90d
cc-janitor perms remove "<rule>" --from <path>
cc-janitor perms add "<rule>" --to <scope>
cc-janitor memory edit <path>
cc-janitor memory archive <path>
cc-janitor memory move-type <path> <type>
cc-janitor memory delete <path>
cc-janitor context reinject [--memory] [--claude-md]
cc-janitor hooks enable-logging <event> <matcher>
cc-janitor hooks disable-logging <event> <matcher>
cc-janitor hooks fix-windows-env
cc-janitor schedule add <template>
cc-janitor schedule remove <name>
cc-janitor schedule run <name>
cc-janitor schedule promote <name>
cc-janitor trash restore <id>
cc-janitor trash empty
```

For each, prefix the command with `CC_JANITOR_USER_CONFIRMED=1 ` ONLY when the
user has explicitly authorized the action in this conversation. Every
invocation is recorded in `~/.cc-janitor/audit.log`.

## Dry-run when in doubt

Most mutating commands accept `--dry-run` to preview without applying.
Prefer dry-run when explaining what cc-janitor would do.
