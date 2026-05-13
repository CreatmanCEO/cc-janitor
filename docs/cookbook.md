# Cookbook

Thirteen task-oriented recipes for everyday cc-janitor use. Each recipe follows
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
`enable-logging` wraps the hook in a reversible logger that writes a
per-event file inside `~/.cc-janitor/hooks-log/` (e.g.
`~/.cc-janitor/hooks-log/PreToolUse.log`) for every invocation.

**Next step:** Trigger the matching tool inside Claude Code and `tail
~/.cc-janitor/hooks-log/PreToolUse.log`. When done, run
`cc-janitor hooks disable-logging PreToolUse Bash` — the wrapper unwraps
cleanly via a sentinel marker.

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

## 11. Find every `.claude/` directory on my machine

**Problem:** You want to see every `.claude/` directory anywhere on
disk, including the junk shipped inside `node_modules` of vendored
packages (upstream Issues #37344, #35561, #18192, #40640).

**Commands:**

```bash
cc-janitor monorepo scan --root ~ --include-junk
cc-janitor monorepo scan --root ~ --json  # for piping
```

**Expected output:** Table with kind (real/nested/junk), settings/hooks
flags, and full path.

**Next step:** Filter discovery in other commands via `--scope`, e.g.
`cc-janitor perms list --scope nested`.

---

## 12. Auto-reinject memory after every edit

**Problem:** You keep editing `~/.claude/CLAUDE.md` outside the TUI and
forgetting `cc-janitor context reinject`.

**Commands:**

```bash
CC_JANITOR_USER_CONFIRMED=1 cc-janitor watch start
cc-janitor watch status        # confirm running
cc-janitor doctor              # see "Watcher: running (3 reinjects)"
CC_JANITOR_USER_CONFIRMED=1 cc-janitor watch stop
```

**Expected output:** `watch start` daemonises a polling loop (30 s
interval, mtime-based, no native FS-event API). `watch status` shows the
PID and reinject count.

**Next step:** Pair with `cc-janitor watch start --dream` to also
snapshot around Auto Dream cycles (recipe 11–13).

---

## 13. Track context cost over time

**Problem:** You want a daily trend line for sessions, perm rules,
context tokens, trash size.

**Commands:**

```bash
# The scheduled context-audit job writes ~/.cc-janitor/history/<date>.json
cc-janitor stats --since 30d
cc-janitor stats --since 7d --format csv > /tmp/last-week.csv
```

**Expected output:** Latest row plus ASCII sparklines. CSV format is
ready to feed a spreadsheet.

**Next step:** TUI Audit tab shows the same data as sparklines (toggle
`s`). After `cc-janitor perms prune` you can see the rules count drop in
the very next snapshot.

---

## 14. Move my cc-janitor config from Windows to my Mac

**Problem:** You want to mirror Claude Code settings, hooks, and
optionally memory across machines.

**Commands:**

```bash
# On the source machine
cc-janitor config export ~/Desktop/cc-janitor-bundle.tar.gz --include-memory

# On the destination machine
cc-janitor config import ~/Downloads/cc-janitor-bundle.tar.gz
# DRY RUN: would write 17 files. Re-run with --apply to write.
CC_JANITOR_USER_CONFIRMED=1 \
  cc-janitor config import ~/Downloads/cc-janitor-bundle.tar.gz --apply
```

**Expected output:** Bundle is a tar.gz with a SHA-256 manifest.
`settings.local.json`, `.env`, and `credentials.json` are excluded
unconditionally. Existing destination files that differ are backed up to
`~/.cc-janitor/backups/import-<ts>/` before overwrite.

**Next step:** Scaffold a fresh `~/.cc-janitor/config.toml` on the new
machine via `cc-janitor config init`.

---

## 15. Enable tab completion

**Problem:** You want `<TAB>` to complete subcommands and flags.

**Commands:**

```bash
# Print the script for inspection
cc-janitor completions show bash
cc-janitor completions show zsh
cc-janitor completions show powershell

# Or install in the conventional location
CC_JANITOR_USER_CONFIRMED=1 cc-janitor completions install bash
```

**Expected output:** `install` writes the script to
`~/.bash_completion.d/cc-janitor` / `~/.zfunc/_cc-janitor` / the
PowerShell profile.

**Next step:** Restart your shell or `source` the file.

---

## 16. Auto Dream just rewrote my memory — how do I see what changed?

**Problem:** Anthropic's Auto Dream rewrote `~/.claude/projects/*/memory/`
during your last session. You want to know exactly which lines moved or
disappeared before deciding whether to keep the new version.

**Command:**

```bash
# Find the pair that wraps the most recent Dream cycle
cc-janitor dream history

# Diff pre vs post (unified diff, all files in the pair)
cc-janitor dream diff <pair_id>

# Narrow to a single file
cc-janitor dream diff <pair_id> --file MEMORY.md

# Regret it? Roll back to the pre-snapshot:
CC_JANITOR_USER_CONFIRMED=1 cc-janitor dream rollback <pair_id> --apply
```

**Expected output:** A coloured unified diff. `rollback --apply` restores
the pre-snapshot files in place and writes the displaced post-Dream copy
to `~/.cc-janitor/.trash/<ts>/dream-rollback-<pair_id>/`.

**Next step:** `cc-janitor stats sleep-hygiene` — surface the keyword,
duplicate, and stale-date counts that drove Dream to mutate so much.

---

## 17. Auto Dream is silently disabled — diagnose it

**Problem:** You enabled `autoDreamEnabled` in `~/.claude/settings.json`
but Dream never runs. Most common cause: a leftover `.consolidate-lock`
file from a crashed previous run (upstream Issue #50694).

**Command:**

```bash
cc-janitor dream doctor
```

**Expected output:** Ten check rows. Look for `FAIL` on `stale_lock`. If
present, manually `rm` the listed lock file(s) and rerun
`cc-janitor dream doctor`. Look for `WARN` on `settings autoDream
toggled` — that means the flag flipped since the last check; verify
backups are configured.

**Next step:** `CC_JANITOR_USER_CONFIRMED=1 cc-janitor watch start --dream`
to enable lock-file polling + snapshots, so next time you can diff before
deciding.

---

## 18. Set up scheduled snapshot-around-Dream so I never lose memory again

**Problem:** You want guaranteed pre/post snapshots around every Auto
Dream cycle, with disk usage capped automatically.

**Command:**

```bash
# Start the watcher (polls ~/.claude/projects/*/memory/.consolidate-lock)
CC_JANITOR_USER_CONFIRMED=1 cc-janitor watch start --dream
cc-janitor watch status

# Compact 7-day-old raw snapshot dirs to .tar.gz, purge 30-day-old tars
cc-janitor backups tar-compact --kind dream

# Schedule the compaction nightly via OS-native scheduler
CC_JANITOR_USER_CONFIRMED=1 cc-janitor schedule add dream-tar-compact
cc-janitor schedule list
```

**Expected output:** A `dream-tar-compact` entry in the scheduler list
(cron / Task Scheduler) running nightly. Snapshots accumulate under
`~/.cc-janitor/backups/dream/` and compact themselves.

**Next step:** Override defaults via `~/.cc-janitor/config.toml`:

```toml
[dream_doctor]
disk_warning_mb = 1024
memory_md_line_threshold = 180
memory_file_count_threshold = 200

[backups]
dream_compact_after_days = 14
dream_purge_after_days = 60
```
