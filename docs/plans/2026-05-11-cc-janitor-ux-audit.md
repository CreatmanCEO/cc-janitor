# cc-janitor UX audit — pre-Phase-4

**Date:** 2026-05-11
**Version audited:** 0.3.1 (`src/cc_janitor/cli/__init__.py:21`)
**Scope:** all 13 CLI subcommand groups + 2 top-level + 7 TUI tabs
**Method:** static read of every CLI command and TUI screen; cross-check
against `README.md`, `docs/cookbook.md`, `docs/CC_USAGE.md`, and the
Phase 1–3 design/MVP docs.

---

## 1. Journey status table

| # | Journey | Status | Headline finding |
|---|---|---|---|
| A | First-run install + orientation | **Partial** | No first-run welcome; `cc-janitor --help` does not point to `doctor` or cookbook. |
| B | Clean up permissions | **Partial** | Works, but no `undo`, no preview-detail in `dedupe --dry-run` (lists suggestion text only). |
| C | Clean up old sessions | **Works** | `delete_session` moves jsonl + sidecar dirs; trash listing readable. |
| D | Understand context tokens | **Partial** | `context show` lists files sorted by tokens (good), but $-estimate is Opus-only and hardcoded. |
| E | Debug a hook | **Partial** | `hooks log` path documented as singular file in cookbook §9 but is a directory in code. |
| F | Schedule weekly maintenance | **Broken (one template)** | `backup-rotate` template emits unsupported `--backups` flag; `schedule audit` referenced in docs but doesn't exist. |
| G | Sync config to new machine | **Partial** | Cookbook says `--force` but CLI uses `--apply`; no Windows path advice. |
| H | Monorepo discovery | **Works** | `monorepo scan` defaults to `cwd`, excludes junk unless `--include-junk`. |
| I | Disaster — undo last action | **Broken** | `cc-janitor undo` does not exist; design doc §6 lists it; cookbook §1 only suggests "roll back by hand". |
| J | Auto-reinject memory | **Works** | install-hooks now writes PowerShell branch on win32. `doctor` shows watcher health. |
| K | TUI vs CLI parity | **Partial** | Sessions, Perms, Audit tabs are READ-ONLY; mutating TUI screens bypass `CC_JANITOR_USER_CONFIRMED` gate via `setdefault`. |
| L | Claude Code calling cc-janitor | **Partial** | CC_USAGE.md references 4 commands that don't exist; env-prefix syntax `ENV=1 cmd` not valid in PowerShell — no Windows note. |

---

## 2. Findings (by severity)

### Critical (block Phase 4 ship)

**C1. TUI bypasses the `CC_JANITOR_USER_CONFIRMED` safety gate.**
`src/cc_janitor/tui/screens/schedule_screen.py:149,165,190` and
`src/cc_janitor/tui/screens/memory_screen.py:84` all do
`os.environ.setdefault("CC_JANITOR_USER_CONFIRMED", "1")` before invoking
a mutating core function. This silently neutralises the documented
safety primitive that `README.md:79` advertises ("every mutating command
refuses to run unless this env var is set"). The TUI should instead
display a confirm modal and set the env var only for the duration of
the confirmed action (or push it onto an audit-log entry as
`source=tui-user-click`).
*Fix:* introduce a `with confirmed_via_tui(action_label): …` context
manager that sets+pops the env var, records `source` in the audit log,
and refuses to elevate if the user hasn't clicked yes.

**C2. `cc-janitor trash restore` is unguarded.**
`src/cc_janitor/core/safety.py:111` `restore_from_trash` never calls
`require_confirmed()`, and the CLI's `audit_action` context manager
(`src/cc_janitor/cli/_audit.py`) only *records* — it does not enforce.
A scripted attacker who can write `CC_JANITOR_USER_CONFIRMED` to 0 can
still call `trash restore <id>` to clobber pruned files back into place.
Per the safety contract this is a mutation and must require confirm.
*Fix:* add `require_confirmed()` at the top of `restore_from_trash` and
to the `--all` branch of `trash empty` regardless.

**C3. `cc-janitor undo` is referenced everywhere but unimplemented.**
Design doc lists it; cookbook §1 hand-waves rollback ("Inspect
`~/.cc-janitor/backups/` … Roll back by hand"); CC_USAGE.md omits it.
The disaster-recovery story is the weakest user flow in 0.3.1.
Backups exist for settings.json edits and bundle imports; permissions
prune writes audit entries (`audit list`) with the removed rule text;
but no command rehydrates from those.
*Fix:* implement `cc-janitor undo <audit-entry-id>` for the four
reversible operations: perms add/remove/dedupe/prune (via
`changed["removed"]` payload), config import (via backup dir), session
prune (via trash bucket id). Throw for non-reversible (memory edit).

**C4. `backup-rotate` scheduled template is broken.**
`src/cc_janitor/core/schedule.py:53` defines
`"cc-janitor trash empty --older-than 30d --backups"`. `trash empty`
(see `src/cc_janitor/cli/commands/trash.py:46`) accepts only
`--older-than-days` (note the suffix) and `--all`. A weekly invocation
of this template will exit non-zero forever.
*Fix:* either implement `--backups` on `trash empty` or change the
template command to a separate `cc-janitor backups prune` command (and
add it).

**C5. CC_USAGE.md ships commands that don't exist.**
`docs/CC_USAGE.md:33` mentions `cc-janitor schedule audit` — not in
`schedule.py`. Line 50 mentions `cc-janitor memory delete` — not in
`memory.py`. Line 54 mentions `cc-janitor hooks fix-windows-env` — not
in `hooks.py`. Claude Code will hallucinate these as valid and present
them to the user. *Fix:* delete or implement.

### Important (should land before Phase 4)

**I1. Cookbook–CLI flag drift.**
`docs/cookbook.md:283` shows `cc-janitor config import … --force`. CLI
uses `--apply` (`src/cc_janitor/cli/commands/config.py:34`). User
follows cookbook verbatim, gets `No such option: --force`.

**I2. Cookbook–code path drift.**
`docs/cookbook.md:199,202` says hook log is `~/.cc-janitor/hooks.log`
(singular file). `src/cc_janitor/core/state.py:25` returns
`self.home / "hooks-log"` (directory; per-event files inside). `tail`
will fail. Same paragraph says the unwrap is via "sentinel marker" —
need a doc snippet showing the exact wrapper.

**I3. Trash restore collision policy mismatch.**
`docs/cookbook.md:121-122` promises "renames to `<orig>.restored-<ts>`
if a collision occurs". `safety.py:125-128` actually raises
`FileExistsError` and leaves the bucket in place. Either implement the
documented behaviour (probably wanted), or fix the doc.

**I4. CLI `--help` has no on-ramp.**
`src/cc_janitor/cli/__init__.py:23` sets help to `"cc-janitor — Tidy
Claude Code"`. A first-time user typing `cc-janitor` gets the Typer
default subcommand listing, no callout to `cc-janitor doctor`, no
mention of `~/.cc-janitor/` artifacts, no link to cookbook. Add an
epilog with "Try `cc-janitor doctor` first" and the safety-env one-liner.

**I5. Windows env-prefix idiom is broken in PowerShell.**
README.md:72, CC_USAGE.md:63, cookbook everywhere uses
`CC_JANITOR_USER_CONFIRMED=1 cc-janitor …`. On PowerShell this is a
syntax error. Need a `$env:CC_JANITOR_USER_CONFIRMED=1; cc-janitor …`
or a `--yes` flag. Given how visible this gate is, the `--yes` flag is
worth adding (with an audit-log marker `source=--yes-flag`).

**I6. `audit list` cannot filter by entry-id.**
`src/cc_janitor/cli/commands/audit.py:28` exposes `--since/--cmd/--failed`
but no `--id` / `--last`. For an `undo` flow the user needs to discover
the entry-id; today there's no way to copy one cleanly. The JSONL has
no stable id field at all (see `audit.py:50`). *Fix:* add a stable
sha1-of-line id to each `AuditEntry`, surface via `list` and `--json`.

**I7. TUI Audit tab shows ONLY sparklines, no audit entries.**
`src/cc_janitor/tui/screens/audit_screen.py:31-54` renders the stats
panel and nothing else — there is no actual list of audit-log entries
in the Audit tab. The cookbook implies the TUI Audit tab mirrors
`audit list`. Add a DataTable above the sparkline panel showing
recent entries; this is also the natural place to bind `u` → undo
once C3 lands.

**I8. Sessions TUI tab is read-only.**
`src/cc_janitor/tui/screens/sessions_screen.py` has no BINDINGS at all
(only row-highlight preview). README.md:23 lists "Soft-delete to
recoverable trash" as a Sessions feature — implied parity does not
exist in TUI. Either add `d`/`p` bindings or document the TUI as
inspector-only.

**I9. Perms TUI tab is read-only.**
`src/cc_janitor/tui/screens/perms_screen.py` shows table + summary; no
keybindings for remove/dedupe/prune. Compare to Memory screen which at
least has bindings (though half are unwired — see I10).

**I10. Memory TUI bindings are stubs.**
`src/cc_janitor/tui/screens/memory_screen.py:21-27` declares
`("e", "edit"), ("a", "archive"), ("m", "move_type"), ("f", "find_dupes")`
but only `action_reinject` is defined (line 79). Pressing `e` etc.
silently does nothing — Textual swallows the `action_edit not found`
error. Either implement or remove the bindings.

**I11. i18n coverage is ~0% in CLI.**
Only `tui/app.py` and `tui/screens/sessions_screen.py` import `t`.
Every CLI `typer.echo` call is hardcoded English. README.md:9
advertises `--lang ru` for the CLI, but selecting `ru` changes only
TUI tab labels — and even then `app.py:35-46` hardcodes "Memory",
"Hooks", "Schedule", "Audit" tab titles in English. *Fix:* either
demote the i18n promise to "TUI only", or extract the ~120 CLI strings
into `en.toml` / `ru.toml` keys.

**I12. `session prune --older-than` parser is too lax.**
`src/cc_janitor/cli/commands/session.py:92` does
`int(older_than.rstrip("d"))`. Passing `--older-than 90` (no unit) is
silently accepted as 90 days; passing `90h` raises `ValueError: 90h`.
Compare to `audit._parse_since` which uses a proper regex. Unify the
two parsers in a `core/duration.py` helper.

### Minor (defer to Phase 4 / 5)

**M1. Opus rate hardcoded in dollar estimate.**
`src/cc_janitor/cli/commands/context.py:28` uses `15 / 1_000_000`. Not
all users run Opus; Sonnet 4.5 is $3/1M. Add `--model opus|sonnet|haiku`.

**M2. `session search` uses `re.escape` + `IGNORECASE` only.**
`session.py:114` won't honour quoted phrases or `--regex` mode. Power
users will reach for grep.

**M3. `session list` has no sort flag and no `--limit`.**
Default is reverse-chrono in-memory only; piping into `head` works but
a `--limit N` is friendly for `xargs` workflows.

**M4. README.md installation block is stale.**
`README.md:39` says ⚠️ "v0.1.x is not yet on PyPI"; project shipped
0.3.x via pipx per the audit brief. Update or delete the warning.

**M5. README.md references missing `docs/architecture.md`.**
`README.md:98` links to it; file does not exist.

**M6. Memory screen scope filter loads with `_source_filter=None` on
first compose**, then sets to "real" in `on_mount` — first table render
shows nothing on slow systems. Pre-seed via the Select's default.

**M7. `doctor` does not surface platform-specific install-hooks
behaviour.** The brief asks: "your platform is win32; install-hooks
would use PowerShell" — doctor today shows Python version, ~/.claude
existence, watcher status, but no `sys.platform` line. One extra line.

**M8. `audit list` JSON output schema is undocumented.**
CC_USAGE.md tells Claude Code to read `--json` output but doesn't
specify the schema. Pin it in CC_USAGE.md (or add `audit schema`).

---

## 3. Missing commands referenced in docs but NOT implemented

| Command | Referenced in | Where it should live |
|---|---|---|
| `cc-janitor undo <id>` | design §6, implied by cookbook §1 | new `cli/commands/undo.py` |
| `cc-janitor schedule audit` | `docs/CC_USAGE.md:33` | merge into `schedule list --history` |
| `cc-janitor memory delete <path>` | `docs/CC_USAGE.md:50` | `cli/commands/memory.py` |
| `cc-janitor hooks fix-windows-env` | `docs/CC_USAGE.md:54` | `cli/commands/hooks.py` (or delete the line) |
| `cc-janitor backups list/prune` | implied by C4 template | new module |
| `cc-janitor stats snapshot` schedule template | exists, but only as ad-hoc | wire into `TEMPLATES` |

---

## 4. CLI ↔ TUI parity matrix

| Surface / Mutation | CLI | TUI | Notes |
|---|:-:|:-:|---|
| Session delete | yes | **no** | I8 |
| Session prune | yes | **no** | I8 |
| Perms remove | yes | **no** | I9 |
| Perms dedupe | yes | **no** | I9 |
| Perms prune | yes | **no** | I9 |
| Perms add | yes | **no** | — |
| Memory edit | yes | binding declared, **action missing** | I10 |
| Memory archive | yes | binding declared, **action missing** | I10 |
| Memory move-type | yes | binding declared, **action missing** | I10 |
| Memory reinject | yes (`context reinject`) | yes (`r`) | bypasses gate — C1 |
| Hooks enable-logging | yes | yes (`l`) | bypasses gate — C1 |
| Hooks simulate | yes | yes (`t`) | read-only |
| Schedule add/remove/run/promote | yes | yes | bypasses gate — C1 |
| Trash restore | yes | **no** | unguarded — C2 |
| Trash empty | yes | **no** | — |
| Config export/import | yes | **no** | acceptable |
| Audit list | yes | **no** | I7 |
| Undo | **no** | **no** | C3 |
| Watch start/stop | yes | **no** | acceptable (rare) |

Symmetric read-only surfaces (list, show, validate, scan, search,
context show/cost/find-duplicates) all present in CLI; TUI exposes
list+preview for the seven tabs (no monorepo tab — minor).

---

## 5. i18n coverage gaps

| File | Strings | i18n? |
|---|---:|:-:|
| `cli/commands/session.py` | ~22 | hardcoded EN |
| `cli/commands/perms.py` | ~18 | hardcoded EN |
| `cli/commands/trash.py` | ~10 | hardcoded EN |
| `cli/commands/hooks.py` | ~12 | hardcoded EN |
| `cli/commands/memory.py` | ~10 | hardcoded EN |
| `cli/commands/schedule.py` | ~12 | hardcoded EN |
| `cli/commands/audit.py` | ~8 | hardcoded EN |
| `cli/commands/doctor.py` | ~12 | hardcoded EN |
| `cli/commands/context.py` | ~10 | hardcoded EN |
| `cli/commands/watch.py` | ~14 | hardcoded EN |
| `cli/commands/stats.py` | ~6 | hardcoded EN |
| `cli/commands/install_hooks.py` | ~3 | hardcoded EN |
| `cli/commands/monorepo.py` | ~6 | hardcoded EN |
| `cli/commands/completions.py` | ~5 | hardcoded EN |
| `cli/commands/config.py` | ~5 | hardcoded EN |
| `tui/app.py` (tab titles) | 4 of 7 hardcoded | partial |
| `tui/screens/sessions_screen.py` | uses `t()` | yes |
| `tui/screens/perms_screen.py` | static labels in EN | no |
| `tui/screens/memory_screen.py` | static labels in EN | no |
| `tui/screens/hooks_screen.py` | static labels in EN | no |
| `tui/screens/schedule_screen.py` | static labels in EN | no |
| `tui/screens/audit_screen.py` | static labels in EN | no |

Effectively only one TUI screen and zero CLI commands respect
`--lang ru`. The `t()` machinery in `i18n/__init__.py` is fine; only
the call sites are missing.

---

## 6. Discoverability gaps

1. **No first-run welcome.** `cc-janitor` with no args drops the user
   into the TUI — fine, but no toast/banner like "press F1 for help,
   q to quit, run `cc-janitor doctor` in CLI for health-check".
2. **`cc-janitor --help` has no epilog.** No "next: cc-janitor doctor",
   no path to cookbook, no env-var summary.
3. **`doctor` does not name backup or audit-log locations.** It prints
   sizes but not the full path users need to find for manual rollback.
   See `src/cc_janitor/cli/commands/doctor.py:28` (audit log path is
   shown — good) vs. backups path (never shown — bad).
4. **Trash listing prints UUID-like timestamps with no project hint.**
   `cc-janitor trash list` shows `id  deleted_at  original_path` but
   the `original_path` is the only correlation; on bulk prune all 80
   buckets show similar paths. Add a `--columns` flag or `--project`.
5. **No hint that watcher needs `psutil` extra.** CHANGELOG mentions
   it; `cc-janitor watch start` will fail with a stack trace if
   `pip install cc-janitor[watcher]` was skipped.
6. **`hooks log` location is documented twice with different paths**
   (see I2) — user grep'ing for "hooks.log" finds nothing useful.
7. **`schedule add <template>` doesn't show templates on bad input
   until you trigger the error** — could list `TEMPLATES.keys()` in
   `--help`.

---

## 7. Disaster-recovery flow assessment

**Verdict: incomplete.** Today, after an accidental `perms prune`:

1. `cc-janitor audit list --since 1h` shows the entry (no id field).
2. `~/.cc-janitor/backups/<sha-of-path>/` contains a timestamped copy
   of `settings.json` BEFORE the prune — good — but only for hooks/
   settings-json edits; **`perms prune` writes via `remove_rule` which
   does not necessarily backup the source file**. Verify
   `core/permissions.py::remove_rule`.
3. No `undo` command exists (C3).
4. User must manually `cp ~/.cc-janitor/backups/<sha>/<ts>.json
   ~/.claude/settings.json` — assuming they know which sha maps to
   which path; today the sha computation is opaque.
5. After accidental `session prune`: `trash restore` works
   (`safety.py:111`) — but is unguarded (C2) and the doc-promised
   collision rename doesn't happen (I3).

Recommended floor for a safe Phase 4: ship C3 (`undo`), C2 (gate
trash-restore), and a `cc-janitor backups list/restore <sha>` pair.

---

## 8. Recommendations

### Top 5 fixes that should land BEFORE Phase 4 ships

1. **Fix the TUI safety-gate bypass (C1).** This is the single
   highest-impact correctness bug; a TUI click should NOT silently
   set an env var that the CLI uses as the sole permission boundary.
2. **Add `cc-janitor undo <audit-id>` (C3) + stable audit-entry ids
   (I6).** Disaster recovery has no answer today.
3. **Gate `trash restore` (C2)** and implement the collision-rename
   policy the cookbook already promises (I3).
4. **Reconcile docs ↔ code drift in CC_USAGE.md, cookbook §1/§6/§9,
   README install + roadmap (C5, I1, I2, M4, M5).** This is a one-PR
   doc sweep but it's currently the source of the most user
   confusion.
5. **Implement / wire-up the four declared-but-stub Memory TUI
   bindings (I10), or delete them.** Silent no-ops on documented
   keys erode trust in the TUI.

### Defer to Phase 4 / 5

- I7 Audit tab → make it a proper log viewer with undo binding.
- I8/I9 Sessions/Perms TUI mutations.
- M1 multi-model dollar estimate.
- I11 full CLI i18n pass (probably Phase 5 — a lot of strings).
- M3 session-list pagination.
- M8 publish `audit list --json` schema.
- New `backups` command group (covers C4 and disaster-recovery flow).
- PowerShell-friendly `--yes` flag (I5).

---

*Words: ~2,300. Audited 13 CLI groups + 7 TUI screens + 3 doc files
against design intent.*
