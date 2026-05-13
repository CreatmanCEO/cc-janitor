# cc-janitor UX audit — post-Phase-4 + 0.4.1

**Date:** 2026-05-13
**Version audited:** 0.4.1 (Phase 4 shipped; `dream`/`backups`/`stats sleep-hygiene` + 8th TUI tab; Windows UTF-8 stdout fix)
**Method:** real execution of every CLI command on Windows 11 + cp1251 console via `uv run cc-janitor …` from
`C:\Users\creat\OneDrive\Рабочий стол\CREATMAN\Tools\cc-janitor` (Cyrillic path on purpose), plus static
read of every command module and the 8 TUI screens. Outputs captured against the live `~/.claude/` (49
sessions, 218 perm rules, real Russian session previews).

Distinguishing executed vs. static-read for each finding is noted inline.

---

## 1. Re-verification of previous audit C1–C5

| ID | Original finding | Fix landed? | Evidence |
|----|------------------|-------------|----------|
| **C1** | TUI bypassed `CC_JANITOR_USER_CONFIRMED` via `setdefault` | **PARTIAL** | `tui/_confirm.py:13` ships `ConfirmModal` + `tui_confirmed()`. Wired in `memory_screen.py:97`, `schedule_screen.py:164/188/224`. **NOT wired in `hooks_screen.py` (no import of ConfirmModal at all).** `action_toggle_logging` calls `enable_logging`/`disable_logging` directly; `core/hooks.py:346` still calls `require_confirmed()`, so the toggle now silently fails (caught by `self.notify("Failed: …", severity="error")`) — old bypass replaced by a broken UX. |
| **C2** | `restore_from_trash` unguarded | **FIXED** | `core/safety.py:123` calls `require_confirmed()` at top of `restore_from_trash`. |
| **C3** | `cc-janitor undo` unimplemented | **FIXED (scope-narrow)** | `cli/commands/undo.py:36-44` covers session delete/prune, perms remove/prune/dedupe, memory archive, config import. **`config import` branch raises `NotImplementedError` (line 168-170)** — partial. **`dream rollback` not in REVERSIBLE_CMDS** — see Journey W. |
| **C4** | `backup-rotate` template broken | **FIXED** | `core/schedule.py:53` now emits `cc-janitor backups prune --older-than-days 30`; `backups prune` command exists. |
| **C5** | CC_USAGE.md phantom commands | **FIXED** | `docs/CC_USAGE.md` no longer references `schedule audit` / `memory delete` / `hooks fix-windows-env`. Line 64-66 documents `hooks fix-windows-env` as not-yet-implemented (acceptable). |

Score: 4/5 fully closed, C1 regressed in `hooks_screen.py`.

---

## 2. Previous audit I1–I12 + M1–M8 — status sweep

| ID | Headline | Status | Note |
|----|----------|:------:|------|
| I1 | cookbook `config import --force` vs CLI `--apply` | OPEN | `cli/commands/config.py:34` still `--apply`; cookbook unchanged. |
| I2 | hook log path drift (file vs dir) | OPEN (assumed) | `state.py:25` still `hooks-log` directory. |
| I3 | trash collision rename | OPEN | `safety.py:131` still raises `FileExistsError`; cookbook still promises rename. |
| I4 | `cc-janitor --help` no on-ramp | OPEN | `cli/__init__.py` help string unchanged; no epilog. |
| I5 | `ENV=1 cmd` broken in PowerShell | OPEN | No `--yes` flag anywhere; README still uses bash idiom. |
| I6 | `audit list` no `--id` / `--last` | OPEN | undo.py uses ts-prefix matching as workaround. |
| I7 | TUI Audit tab is sparklines-only | OPEN | `audit_screen.py` unchanged; no DataTable of entries. |
| I8 | Sessions TUI read-only | OPEN | No BINDINGS in `sessions_screen.py`. |
| I9 | Perms TUI read-only | OPEN | `grep -c "action_" perms_screen.py` = 0. |
| I10 | Memory TUI bindings half-stub | **STILL BROKEN** | `memory_screen.py:23-29` declares `e`/`a`/`m`/`f`; only `action_reinject` (line 81) is defined. `action_edit`/`action_archive`/`action_move_type`/`action_find_dupes` missing → silent no-op when user presses those keys. |
| I11 | i18n ~0% in CLI | OPEN | Spot-check: `cli/commands/dream.py`/`backups.py`/`stats.py` (all Phase-4 modules) — zero `t()` calls. Phase 4 widened the gap. |
| I12 | duration parser lax | OPEN (presumed) | No `core/duration.py` exists. |
| M1 | Opus rate hardcoded | OPEN | `context.py:28` still `15/1_000_000`. |
| M2 | `session search` regex | OPEN | unchanged. |
| M3 | `session list --limit` | OPEN | unchanged. |
| M4 | README "not on PyPI" warning | OPEN (urgent) | Pkg is on PyPI as of 0.4.1 — outdated warning blocks marketing. |
| M5 | missing `docs/architecture.md` | OPEN (assumed). |
| M6 | Memory screen scope filter race | likely OPEN (untested). |
| M7 | doctor lacks platform-specific row | OPEN | `cli/commands/doctor.py:18-49` has no `sys.platform` line, no config.toml location. |
| M8 | audit JSON schema undocumented | OPEN. |

**Carry-over: 1 critical (I10 truly broken bindings) + 8 important + 4 minor still open from previous audit.**

---

## 3. New journey table (M–W, Phase 4)

| Jrn | Status | Headline |
|----|:--:|---|
| M | **PARTIAL** | `dream doctor` works first-run; output mentions disabled flag but doesn't tell user to run `watch start --dream`. Discoverability gap. |
| N | **BROKEN** | `dream rollback --apply` exists, but it (a) does **not** warn user that previously-applied dreams since the snapshot will be undone, (b) cannot be `cc-janitor undo`-ed (see W), (c) fails entirely if pair is in tar storage (see R). |
| O | **BROKEN** | `~/.cc-janitor/config.toml` parses, but: (1) no `config init` command exists; (2) malformed TOML silently falls back to defaults — user gets no warning their override didn't take (`core/config.py:49`); (3) `doctor` doesn't surface the file's location or status; (4) `dream doctor` re-reads on every call (good) but there's no `config validate`. |
| P | **WORKS-PARTIAL** | `stats sleep-hygiene` runs cleanly. Identifies 3 contradicting pairs in `C--Users-creat`. **But neither text nor JSON output reveals WHICH pairs.** `core/sleep_hygiene.py:29` computes `contradicting_pairs: list[tuple[str, list[Path]]]`, then `_to_dict` discards them. User sees count, can't act. |
| Q | **WORKS** | 8 tabs render in TUI; "Dream" tab on screen 8 visible without scroll on 100-col. Empty state: `_show_diff_for(None)` shows "Select a snapshot pair on the left." (good). Works without `dream-snapshots.jsonl`. |
| R | **BROKEN** | After `backups tar-compact`, `dream history` still lists the pair (it reads `dream-snapshots.jsonl`, not mirrors). **But `dream diff` exits 1** with "Snapshot mirrors missing (tar storage not yet supported in dry-run)" (`dream.py:73-75`). **`dream rollback` will also fail** — it iterates `pre.rglob("*")` on a directory that no longer exists (`dream.py:153`). The entire tar-compact lifecycle is therefore one-way: compact → unrecoverable. |
| S | **BROKEN** | `backups list` (executed: "No backup buckets.") lists ONLY `~/.cc-janitor/backups/*/` (settings snapshots). Dream `pre`/`post` mirrors live under `~/.cc-janitor/backups/dream/` so they DO appear — but **`backups prune --older-than-days 30` will recurse into `dream/` and delete pair mirrors that are still referenced by `dream-snapshots.jsonl`**. No safeguard. `backups.py:76-83` iterates the top-level only — currently the `dream` subdir is treated as a single bucket with its own mtime; the entire dream tree could be wiped in one call. |
| T | **PARTIAL — see §5** | Real Windows console execution of all 10 commands succeeded. Cyrillic renders correctly (e.g. `session list` shows `Прочитай LANDING_IMPLEMENTATION_PLAN.md`). UTF-8 fix in `__main__.py:11-18` confirmed in place. No raw `sys.stdout.write` outside the reconfigure block. |
| U | **PARTIAL** | ConfirmModal wired in memory + schedule. **NOT in `hooks_screen.py` (silent failure when toggling logging — see C1)**. **NOT in `dream_screen.py`** — that screen is read-only and has no rollback/prune binding at all (header docstring claims "Future mutations … will route through ConfirmModal"). TUI Dream tab is therefore an inspector; CLI is the only path to rollback. |
| V | **FIXED** | `docs/CC_USAGE.md:78-95` has full Phase 4 section. Lists read-only (`dream history/diff/doctor`, `stats sleep-hygiene`, `watch status`) and mutating (`dream rollback/prune`, `watch start --dream`, `backups tar-compact`, `schedule add dream-tar-compact`) correctly. No new phantom commands. |
| W | **GAP** | `dream rollback` audits with `cmd="dream rollback"`, `args=[pair_id, "--apply"]`, `changed={"pair_id", "files_restored", "trash_path"}`. **But `REVERSIBLE_CMDS` in `undo.py:36-44` does NOT include `"dream rollback"`.** Trash bucket name is recorded — could be wired to `restore_from_trash`, but isn't. |

---

## 4. Findings by severity

### Critical (block marketing/raskrutka)

1. **C1-regression: TUI hook-logging toggle silently fails.** `tui/screens/hooks_screen.py:100-114` calls `enable_logging`/`disable_logging` with no `tui_confirmed()` context; the core function raises `NotConfirmedError`, caught and reported as "Failed: CC_JANITOR_USER_CONFIRMED…" via `self.notify`. Users cannot toggle hook logging from the TUI at all.
   *Fix:* mirror memory_screen pattern — push `ConfirmModal`, then `with tui_confirmed(): enable_logging(…)`.

2. **Tar storage = data loss.** `dream diff` and `dream rollback` both read `pre/` and `post/` directories directly; after `backups tar-compact --apply`, those dirs are gone (`backups.py:184-185 shutil.rmtree(d)`). Pair becomes inspectable (history) but un-diffable and un-rollbackable.
   `cli/commands/dream.py:72-75, 153`.
   *Fix:* in `dream_diff`/`dream rollback`, transparently extract `<pair_id>.tar.gz` to a temp directory; do not enable tar-compact scheduler template until this is implemented.

3. **`backups prune` will eat dream mirror data.** `cli/commands/backups.py:76-83` walks `paths.backups.iterdir()` and considers any sub-bucket prunable by newest-mtime. Dream pre/post mirrors are exactly such buckets. A user running the weekly `backup-rotate` scheduled job (default 30d cutoff) will lose Dream restore points without warning.
   *Fix:* skip `dream/` subtree in `backups prune`, or cross-check against `dream-snapshots.jsonl` and refuse to delete referenced pairs.

4. **I10 still broken — TUI Memory bindings 4-of-5 are silent no-ops.** Pressing `e`/`a`/`m`/`f` in Memory tab does nothing visible; user thinks the keystroke was dropped. `memory_screen.py:23-29` declares; no `action_*` exists.
   *Fix:* implement or remove. At minimum delete the bindings until implemented.

### Important

5. **Sleep-hygiene doesn't surface contradiction PAIRS.** Both text (`stats.py:sleep_hygiene`) and JSON output drop `contradicting_pairs` content, only showing count. Persona 9 (Diagnostician) is stuck. `core/sleep_hygiene.py:29, 127, 145` already compute the pairs.
   *Fix:* add `--show-pairs` flag that prints `subject : [path1, path2, …]` per pair; emit in JSON too.

6. **`dream rollback` lacks a "you will lose dreams since this snapshot" warning.** Output is `[dry-run] Would restore {pre} -> {target}` followed by "Current target post-state would be soft-deleted to trash." That's it. No mention that intermediate dream cycles will be discarded.
   `dream.py:130-134`.

7. **`dream rollback` not reversible via `cc-janitor undo`.** Trash bucket is recorded but `REVERSIBLE_CMDS` (`undo.py:36-44`) omits `"dream rollback"`. Persona 8 (Auto Dream user) who rolls back, then regrets, has no recovery path.

8. **No `cc-janitor config init` / `config validate`.** Persona 10 (long-time user with bloated state) wants a discoverable way to scaffold + tune `~/.cc-janitor/config.toml`. Malformed TOML silently falls back to defaults (`core/config.py:49`) — even more dangerous. Add `config init` + `config validate`; on parse failure, emit `WARN: config.toml at <path> failed to parse (<error>); using defaults` to stderr in `load_config`.

9. **`doctor` doesn't mention Dream / config.toml / platform.** `cli/commands/doctor.py:13-49` shows 7 facts; none of: `sys.platform`, `~/.cc-janitor/config.toml` (exists/parse status), Auto Dream snapshot count, dream backup size. After Phase 4 this is incomplete. M7 from previous audit, now also Dream-related.

10. **TUI `app.py` still hardcodes 5 of 8 tab labels.** `tui/app.py:35-49` — `"Memory"`, `"Hooks"`, `"Schedule"`, `"Audit"`, `"Dream"` are English literals; only first 3 use `t()`. I11 not advanced; in fact regressed by adding "Dream".

11. **`dream history` table has no timestamp + no storage indicator.** Columns: `PAIR_ID PROJECT DFILES DLINES`. After tar-compact, user can't tell which pairs survive `dream diff`. Add `STORAGE` column (`dir`/`tar`) and `WHEN` column (the `ts_pre[:10]` already used in TUI).
   `cli/commands/dream.py:44-50`.

12. **`watch start --dream` doesn't tell user what happens next.** Output: `Watcher started (pid 1234, interval 30s, 3 memory dirs)`. No mention of the dream-lock detection loop, no pointer to `cc-janitor dream doctor`. Persona 8 has no feedback that the safety net is now armed.
   `cli/commands/watch.py:105-108`.

### Minor

13. `dream prune` default is 30 days; `tar-compact` default is 7 days. Order matters — if a user runs prune first they wipe pairs that should have been compacted. Document or interlock.
14. `backups list` shows no Phase-4 dream pairs in dry environment ("No backup buckets") — confirms separation works on this machine, but on a populated machine they would mix without a label. Add a `KIND` column (`settings` / `dream`).
15. `dream doctor` "Cross-file duplicates: 15 duplicated lines" — info severity but no `--fix` pointer (could suggest `memory find-duplicates`).
16. README install block still warns "not on PyPI" (M4, urgent for marketing).
17. `cli/commands/stats.py` callback collides — `stats --since 30d` is the default callback but `stats sleep-hygiene` (subcommand) ignores it. Surprising.
18. `dream` subapp registered as `no_args_is_help=True` is fine, but `dream` group's `--help` shows commands without one-line descriptions (each row blank). `cli/commands/dream.py:33,60,104,116,169` — none use `help="…"` on the decorator.

---

## 5. Windows console re-check (Journey T) — what was actually run

Real PowerShell on Windows 11 (cp1251 console host), via `uv run cc-janitor <cmd>` against the live
`C:\Users\creat\.claude` (49 sessions, 218 perm rules, Cyrillic memory files, Cyrillic OneDrive path with
spaces). Each row below is from actual stdout capture:

| Command | Executed | Exit | Cyrillic rendered? |
|---------|:--------:|:----:|:------------------:|
| `cc-janitor doctor` | yes | 0 | n/a (ASCII-only output) |
| `cc-janitor session list` | yes | 0 | **yes** ("Прочитай LANDING_IMPLEMENTATION_PLAN.md", "мама хочет оформить") |
| `cc-janitor perms audit` | yes | 0 | yes (paths include "Рабочий стол") |
| `cc-janitor perms list --stale` | yes | 0 | n/a |
| `cc-janitor context show` | yes | 0 | yes ("Рабочий стол\CREATMAN\CLAUDE.md") |
| `cc-janitor monorepo scan` | yes | 0 | n/a |
| `cc-janitor stats sleep-hygiene` | yes | 0 | n/a (slugs ASCII) |
| `cc-janitor dream doctor` | yes | 0 | n/a |
| `cc-janitor hooks list` | yes | 0 | yes ("for d in . \"$HOME/OneDrive/Рабочий стол/…") |
| `cc-janitor memory list` | yes | 0 | yes (file names) |
| `cc-janitor audit list --since 7d` | yes | 0 | n/a |
| `cc-janitor backups list` | yes | 0 | n/a |
| `cc-janitor dream history` | yes | 0 | n/a (empty) |

**Code-static verification of the 0.4.1 fix:**
- `src/cc_janitor/__main__.py:11-18` `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` is present and runs before any subcommand.
- Grep for raw `sys.stdout.write(` in `src/cc_janitor/cli/commands/`: **0 hits.** All output goes through `typer.echo`.
- Grep for `print(` in `src/cc_janitor/cli/commands/`: **0 hits.**
- TUI is Textual; renders its own buffer — not affected by the stdout reconfigure.

Verdict: 0.4.1 Windows fix is real and complete. The previous audit's blind spot is closed.

---

## 6. CLI ↔ TUI parity table for Phase 4

| Phase-4 surface | CLI | TUI (Dream tab) | Notes |
|---|:--:|:--:|---|
| `dream history` | yes | yes (DataTable) | — |
| `dream diff <pair>` | yes | yes (Static panel) | both fail on tar-storage |
| `dream doctor` | yes | **no** | finding 9 |
| `dream rollback` | yes (CLI) | **no** | header docstring says "future" |
| `dream prune` | yes | **no** | — |
| `backups list/prune/tar-compact` | yes | **no** | acceptable (admin-y) |
| `stats sleep-hygiene` | yes | **no** | could live in Audit tab |
| `watch start --dream` | yes | **no** | acceptable |

The Dream TUI tab is strictly inferior to the CLI — pure inspector. Acceptable for 0.4.x; should add at
minimum a rollback action with ConfirmModal before promoting to marketed feature.

---

## 7. Discoverability gaps (new in Phase 4)

1. `cc-janitor doctor` doesn't surface the Dream safety net at all.
2. `dream doctor` WARN row "Auto Dream is disabled" doesn't link to `cc-janitor watch start --dream`.
3. No README mention that flipping `autoDreamEnabled` is detected by `settings_observer`; users won't know audit log is recording the flip.
4. `backups tar-compact` "Nothing to compact" gives no hint that this is the right state — could say "(no `<pair_id>-pre/post` dirs found under ~/.cc-janitor/backups/dream/)".
5. `stats sleep-hygiene` totals omit a "what to do" suggestion (e.g. "run `memory find-duplicates` to inspect dup_count > 0").
6. `config.toml` is undocumented in README/cookbook. Only mentioned implicitly via `dream doctor` reading thresholds.

---

## 8. Recommendations — top 5 must-fix before marketing push

1. **Fix tar-storage read paths (critical #2).** Without it, `backups tar-compact` is a footgun and the
   `dream-tar-compact` template should not ship as a default. Implement transparent tar-extract in
   `dream.py` for `diff` and `rollback`.

2. **Guard `backups prune` from dream/ subtree (critical #3).** Either skip the dir or cross-reference
   `dream-snapshots.jsonl`. Currently the documented Phase-4 maintenance flow eats its own backups.

3. **Wire ConfirmModal in `hooks_screen.py` (critical #1).** The 0.3.2 fix shipped half-done — toggling
   hook logging from the TUI is now broken (silent failure). Five lines + an import.

4. **Delete or implement Memory TUI `e/a/m/f` bindings (critical #4 / previous I10).** Either land the
   four actions or remove them from `BINDINGS`. Today they are silent no-ops on documented keys.

5. **Add `dream rollback` to `undo`-reversibility set (important #7) + add `--undo-warning` text
   (important #6).** Trash bucket is already recorded. Wire `restore_from_trash(trash_id)` for the
   `dream rollback` audit entry; print "this rollback can be undone with `cc-janitor undo`" on success.

**Nice to have (before raskrutka but not blocking):**
- README M4 (drop "not on PyPI" warning).
- `stats sleep-hygiene --show-pairs` (Diagnostician persona).
- `config init` / `config validate`.
- `doctor` to surface Dream + config.toml + `sys.platform`.

---

*Words: ~2,540. Real execution: 13 commands on Windows 11 PowerShell. Static read: every Phase-4
module + 4 TUI screens + `_confirm.py` + `safety.py` + `undo.py` + schedule templates. Previous-audit
blind spot (Windows console) explicitly re-verified by running on the real machine.*
