# Cookbook

Ten task-oriented recipes for everyday cc-janitor use. Each recipe follows
the same shape: **Problem → Command → Expected output → Next step.**

---

## 1. Clean up your permission rules

**Problem:** `~/.claude/settings.json` (and friends) have grown to dozens of
rules, many of which are duplicates or haven't matched a tool call in months.

**Command:**

```bash
cc-janitor perms audit
cc-janitor perms list --stale --dup

# Once happy with the preview:
CC_JANITOR_USER_CONFIRMED=1 cc-janitor perms dedupe
CC_JANITOR_USER_CONFIRMED=1 cc-janitor perms prune --older-than 90d
```

**Expected output:** A table of rules with columns for source, scope, decision,
last-seen, and dup-of. Audit prints totals (n rules, n stale, n duplicates).

**Next step:** Inspect `~/.cc-janitor/backups/` — every settings.json edit
left a timestamped copy there. Roll back by hand if anything looks off.

---

## 2. See what your context costs you

**Problem:** Sessions feel slow and expensive. You suspect CLAUDE.md /
memory files have grown beyond what's worth re-reading every request.

**Command:**

```bash
cc-janitor context cost
```

**Expected output:** Per-file table (path, bytes, tokens, $ at Opus rate)
followed by a totals row showing recurring per-request cost.

**Next step:** Open the largest offender in your editor and trim. Re-run
`cc-janitor context cost` to confirm the saving.

---

## 3. Prune old sessions

**Problem:** `~/.claude/projects/` has hundreds of `.jsonl` transcripts,
most older than three months.

**Command:**

```bash
cc-janitor session list
CC_JANITOR_USER_CONFIRMED=1 cc-janitor session prune --older-than 90d
```

**Expected output:** Count of sessions moved to trash and the trash dir path.

**Next step:** Pruned sessions live in `~/.cc-janitor/.trash/<ts>/` for 30 days.
Restore with `cc-janitor trash restore <id>` if you change your mind.

---

## 4. Search across all sessions

**Problem:** You remember talking through a particular bug or design two
weeks ago but can't find which session it was in.

**Command:**

```bash
cc-janitor session search "supabase row level"
```

**Expected output:** Ranked list of sessions with project, mtime, and a
matching snippet from the transcript.

**Next step:** Pipe into `cc-janitor session show <id>` for the full
preview, or open the JSONL by hand.

---

## 5. Use cc-janitor from inside Claude Code

**Problem:** You want Claude Code to call cc-janitor on your behalf during
a chat, but only safely.

**Command:** Append `docs/CC_USAGE.md` to your `~/.claude/CLAUDE.md`:

```bash
cat docs/CC_USAGE.md >> ~/.claude/CLAUDE.md
```

**Expected output:** No output. Claude Code now knows which subcommands
are read-only (free to call) and which require `CC_JANITOR_USER_CONFIRMED=1`
plus your explicit "yes" in chat.

**Next step:** Ask Claude Code: "what does my context cost?" — it should
call `cc-janitor context cost` and summarize. Mutating commands will be
proposed first, then executed only after you confirm.

---

## 6. Restore a session from trash

**Problem:** You pruned too aggressively and want a session back.

**Command:**

```bash
cc-janitor trash list
CC_JANITOR_USER_CONFIRMED=1 cc-janitor trash restore <id>
```

**Expected output:** Path the file was restored to (refuses to overwrite
existing files; renames to `<orig>.restored-<ts>` if a collision occurs).

**Next step:** `cc-janitor session show <id>` to verify content, then
re-open it in Claude Code via the IDE's session picker.

---

## 7. Memory hygiene — promote feedback to user-level

**Problem:** Auto-memory has captured a bunch of `feedback_*.md` files inside
a project that you'd actually like to apply globally as `user`-type memory.

**Command:**

```bash
cc-janitor memory list --type feedback
CC_JANITOR_USER_CONFIRMED=1 cc-janitor memory move-type feedback_no_emojis.md user
```

**Expected output:** Table of feedback files (path, type, size, last-modified),
then a confirmation that the file was moved to the user-level memory dir
with frontmatter `type` rewritten.

**Next step:** Run `cc-janitor memory find-duplicates` afterwards — promoted
feedback can collide with existing user-level memory; the duplicate-line
detector flags overlapping lines across files so you can dedupe by hand.

---

## 8. My memory edits don't take effect (reinject)

**Problem:** You edited `~/.claude/CLAUDE.md` mid-session but Claude Code
keeps quoting the old contents — it doesn't re-read CLAUDE.md until a new
session starts (upstream issue #29746).

**Command:**

```bash
# One-time setup — installs a PreToolUse hook that emits a system-reminder
# whenever the reinject-pending marker exists.
CC_JANITOR_USER_CONFIRMED=1 cc-janitor install-hooks

# Whenever you want Claude to re-read memory in the current session:
CC_JANITOR_USER_CONFIRMED=1 cc-janitor context reinject
```

**Expected output:** `install-hooks` writes a hook entry into
`~/.claude/settings.json` (POSIX shell on Linux/macOS, PowerShell on
Windows). `context reinject` writes `~/.cc-janitor/reinject-pending`. The
next tool call Claude makes triggers the hook, which emits a
`<system-reminder>` block citing the freshly-read memory.

**Next step:** Confirm by asking Claude something that depends on the new
content. For one-shot manual reinjection without the hook, you can also
press `[r]` on the Memory tab in the TUI.

---

## 9. A hook isn't firing — debug it

**Problem:** You configured a `PreToolUse` hook for `Bash` and it doesn't
seem to run. Claude Code's own logs are vague (#11544, #10401, #16564).

**Command:**

```bash
cc-janitor hooks list
cc-janitor hooks validate                 # catches missing-hooks-array, empty command
cc-janitor hooks simulate PreToolUse Bash # runs your hook with a realistic payload
CC_JANITOR_USER_CONFIRMED=1 cc-janitor hooks enable-logging PreToolUse Bash
```

**Expected output:** `list` shows every hook discovered across the 4
settings layers (user, project, project-local, enterprise) with source
attribution. `validate` returns schema errors. `simulate` runs the actual
hook command with a real stdin payload and prints exit code + duration.
`enable-logging` wraps the hook in a reversible logger that writes
`~/.cc-janitor/hooks.log` for every invocation.

**Next step:** Trigger the matching tool inside Claude Code and `tail
~/.cc-janitor/hooks.log`. When done, run `cc-janitor hooks disable-logging
PreToolUse Bash` — the wrapper unwraps cleanly via a sentinel marker.

---

## 10. Schedule a weekly cleanup (dry-run first)

**Problem:** You want `perms-prune` to run weekly without remembering to do
it, but you don't trust an unattended process to delete things on day one.

**Command:**

```bash
CC_JANITOR_USER_CONFIRMED=1 cc-janitor schedule add perms-prune
# wait for the first scheduled run — it executes in --dry-run mode automatically
cc-janitor schedule list                  # status: "dry-run pending"
CC_JANITOR_USER_CONFIRMED=1 cc-janitor schedule promote cc-janitor-perms-prune
```

**Expected output:** `add` registers a cron entry on Linux/macOS or a
schtasks task on Windows, named `cc-janitor-perms-prune`. The first run is
forced to `--dry-run` regardless of template. `promote` flips it to a live
run. Scheduled runs export `CC_JANITOR_USER_CONFIRMED=1` and
`CC_JANITOR_SCHEDULED=1`; the latter activates a hard cap (default 200
items per run) so a runaway template can't wipe a whole tree.

**Next step:** Inspect the dry-run output via the audit log:
`cc-janitor audit list --cmd schedule-run --json`. Adjust `CC_JANITOR_HARD_CAP`
if your project legitimately needs more than 200 deletions per run.
