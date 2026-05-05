# Cookbook

Six task-oriented recipes for everyday cc-janitor use. Each recipe follows
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
