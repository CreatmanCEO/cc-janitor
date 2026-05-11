# cc-janitor Phase 4 — Design: Auto Dream safety net

> **Date:** 2026-05-11
> **Author:** @CreatmanCEO
> **Status:** Approved (Hypothesis A scope, 5 open questions resolved). Ready for implementation planning.
> **Predecessor:** `docs/plans/2026-05-11-cc-janitor-phase4-dream-analysis.md`
> **Style mirror:** `docs/plans/2026-05-03-cc-janitor-design.md`, `docs/plans/2026-05-05-cc-janitor-phase2-design.md`, `docs/plans/2026-05-09-cc-janitor-phase3-design.md`

## 1. Problem statement

Anthropic's **Auto Dream** (LLM-driven memory consolidation in Claude Code,
gated behind the server-side `autoDreamEnabled` flag in `~/.claude/settings.json`)
silently rewrites the user's `~/.claude/projects/<slug>/memory/*.md` tree in
place. As verified in Phase 4 analysis:

- **No built-in backup.** Anthropic's documentation tells users to back up
  `~/.claude/` manually.
- **No diff or preview.** Issue #47959 documents the canonical regression: 23
  memory files deleted in a single Auto Dream pass with no recovery path.
- **No audit log.** Issues #38493 and #50694 explicitly request one and remain
  open.
- **Silent failure mode.** A stale `~/.claude/projects/<slug>/memory/.consolidate-lock`
  after a crash silently disables Auto Dream forever with no user-visible
  signal (Issue #50694, open as of 2026-05-11).
- **Server-side gate is inscrutable.** Toggling `autoDreamEnabled: true`
  locally does not guarantee execution. Many users see `/dream` return
  "Unknown skill" (Issue #38461) and have no way to confirm whether the
  feature is active for their account.

cc-janitor's Phase 1–3 primitives (backup-before-write, audit log,
soft-delete, USER_CONFIRMED gate, snapshot history, monorepo walker,
background watcher, stats engine) map exactly onto these gaps. Phase 4 wires
those primitives into a **deterministic safety harness around the Auto Dream
black box**: snapshot before, diff after, rollback if needed, audit always.

This is the project's strongest positioning moment of the year — not "another
Claude Code tool" but the safety net around Anthropic's own undocumented
consolidation. Scope is deliberately defensive (Hypothesis A); the broader
"Dream orchestrator" (Hypothesis B) is deferred to Phase 5.

## 2. Tech stack

No new mandatory dependencies. All new code uses the stdlib + already-present
extras from Phases 1–3.

| Layer | Choice | Why |
|-------|--------|-----|
| TOML config loader | `tomllib` (stdlib, Python 3.11+) | Read `~/.cc-janitor/config.toml`; already required by `pyproject.toml`-parsing tests elsewhere |
| Lock-file polling | extends Phase 3 `core/watcher.py` mtime poller | One more state machine, no new daemon binary |
| Diff engine | `difflib.unified_diff` + custom file-level walker | Stdlib, deterministic, already used by `perms diff` |
| Tar compaction | `tarfile` (stdlib) | Same module Phase 3 `bundle.py` uses |
| TUI new tab | Textual `TabPane` + `DataTable` + `Static` (no new widgets) | Mirrors existing `Audit`, `Schedule` tabs |
| Audit gate | `cli/_audit.py` `audit_action` context manager (Phase 2; gained `mode=` kwarg in 0.3.2) | All Phase 4 mutations use `mode="cli"` or `mode="scheduled"` |
| TUI mutations | `tui/_confirm.py` `ConfirmModal` + `tui_confirmed()` context manager (Phase 2 / 0.3.2 C1 fix) | Any TUI-driven rollback or snapshot-delete passes through this |
| Optional process-alive check | `psutil` (already optional `[watcher]` extra from Phase 3) | Reused by stale-lock PID check in dream doctor |

## 3. Architecture

### 3.1 Five new files; one TUI tab; one config file

```
src/cc_janitor/
├── core/
│   ├── config.py                # NEW — ~/.cc-janitor/config.toml loader
│   ├── dream_snapshot.py        # NEW — lock-file state machine + raw mirror
│   ├── dream_diff.py            # NEW — pre vs post comparison
│   ├── dream_doctor.py          # NEW — 9-check diagnostic matrix
│   ├── sleep_hygiene.py         # NEW — 4 keyword/regex/dup metrics
│   └── watcher.py               # MODIFIED — adds --dream lock-file mode
├── cli/commands/
│   ├── dream.py                 # NEW — snapshot/diff/doctor/rollback/history subapp
│   └── stats.py                 # MODIFIED — adds `stats sleep-hygiene`
└── tui/
    ├── app.py                   # MODIFIED — adds 8th `DreamScreen` tab
    └── screens/
        └── dream_screen.py      # NEW — list pane + diff viewer pane
```

User-visible new state:

```
~/.cc-janitor/
├── config.toml                  # NEW — user-tunable thresholds (optional)
├── backups/dream/
│   ├── <pair_id>-pre/           # raw mirror of ~/.claude/projects/.../memory/
│   ├── <pair_id>-post/          # raw mirror after lock release
│   └── <pair_id>.tar.gz         # archived after raw_retention_days (default 7)
└── dream-snapshots.jsonl        # one record per snapshot pair lifecycle
```

### 3.2 Architectural principles (unchanged from Phase 1)

1. **`core/` knows nothing about UI.** All five new core modules return
   dataclasses; CLI and TUI consume them identically.
2. **Safety by default.** `dream rollback --apply` requires
   `CC_JANITOR_USER_CONFIRMED=1`. Snapshot writes never delete anything in
   `~/.claude/`. Tar compaction never deletes a snapshot the user could still
   need (governed by `raw_retention_days` / `tar_retention_days` thresholds in
   `config.toml`).
3. **Audit log always on.** Every snapshot, rollback, doctor invocation, and
   `autoDreamEnabled` toggle observation gets an `audit_action(...)` entry.
4. **Path-agnostic snapshot semantics.** Phase 4 does not assume Auto Dream's
   internal 4-phase pipeline. It snapshots whatever exists under
   `~/.claude/projects/*/memory/` at moments T0 (lock appears) and T1 (lock
   gone). Whatever Anthropic changes about consolidation logic, the snapshot
   pair is still a valid before/after.
5. **`Path.home()` not `paths.home.parent`.** Phase 1 fixed a latent bug
   where `paths.home.parent` was used to find Claude home; all new modules
   use `Path.home() / ".claude"` directly. (Mentioned again here because
   `core/watcher.py` Phase 3 still uses the older `_default_memory_dirs()`
   helper which must be replaced with the lock-file-aware variant.)

### 3.3 Claude Code integration model

Read-only commands (`dream history`, `dream diff`, `dream doctor`,
`stats sleep-hygiene`) may be invoked freely from inside a Claude Code
session. Mutating commands (`dream rollback --apply`, `dream snapshot prune`)
refuse without `CC_JANITOR_USER_CONFIRMED=1`. Identical to Phases 1–3.

## 4. Feature scope

### 4.1 Dream snapshot subsystem

**Trigger model — Q2 decision = opt-in.** A new flag on the Phase 3 watcher:

```bash
cc-janitor watch start --dream                  # adds lock-file polling
cc-janitor watch start --dream --no-memory      # ONLY lock-file polling
```

When `--dream` is set, the daemon's per-iteration body polls every
`~/.claude/projects/*/memory/.consolidate-lock` file in addition to its
existing mtime watch on `*.md`. Decision rationale: silent universal
snapshotting would generate dozens of unwanted snapshot pairs per day for
users who write to memory manually. Opt-in keeps the noise floor at zero.

**State machine.** Per-project state in memory:

```
NO_LOCK ────lock appears────► LOCK_HELD (snapshot pre written)
   ▲                              │
   │                              │
   └────lock disappears───────────┘ (snapshot post written, pair recorded)
```

State map keyed by `claude_project_dir`. On daemon start, every existing lock
is recorded as a pre-snapshot too (recovery from crash mid-Dream).

**Storage layout — Q1 decision = hybrid (C).** Raw mirror at
`~/.cc-janitor/backups/dream/<pair_id>-pre/<original-tree>/` and
`<pair_id>-post/<original-tree>/`. `pair_id` = `YYYYMMDDTHHMMSSZ-<slug>`.
After `raw_retention_days` (default 7), a scheduled job runs:

```bash
cc-janitor backups tar-compact --kind dream --older-than-days 7
```

which produces `<pair_id>.tar.gz` containing both pre and post trees and
deletes the raw mirrors. The tar is retained for `tar_retention_days`
(default 30) and then purged by the same scheduled job. `dream diff` and
`dream rollback` transparently read either form.

**Lifecycle record (`dream-snapshots.jsonl`):**

```json
{"pair_id": "20260511T143022Z-life-hub-vps",
 "ts_pre":  "2026-05-11T14:30:22Z",
 "ts_post": "2026-05-11T14:32:18Z",
 "project_slug": "life-hub-vps",
 "project_path": "/home/user/life-hub-vps",
 "claude_memory_dir": "/home/user/.claude/projects/-home-user-life-hub-vps/memory",
 "paths_in_pre":  ["MEMORY.md", "project_x.md", "feedback_y.md"],
 "paths_in_post": ["MEMORY.md", "project_x.md"],
 "file_count_delta": -1,
 "line_count_delta": -47,
 "has_diff": true,
 "dream_pid_in_lock": 38249,
 "storage": "raw"}
```

`storage` flips to `"tar"` after compaction.

### 4.2 Dream diff viewer

Pure read-only. Compares the pre- and post-mirrors for a given `pair_id` and
returns a structured `DreamDiff`:

```python
@dataclass
class DreamFileDelta:
    rel_path: Path
    status: Literal["added", "removed", "changed", "unchanged"]
    lines_added: int
    lines_removed: int
    unified_diff: str | None   # None for status == "unchanged"

@dataclass
class DreamDiff:
    pair_id: str
    project_slug: str
    deltas: list[DreamFileDelta]
    summary: dict   # {"files_added": int, "files_removed": int, ...}
```

`unified_diff` is `difflib.unified_diff(pre_lines, post_lines, n=3)` joined
into a single string. No semantic grouping in Phase 4 — that is Phase 5.

CLI:

```bash
cc-janitor dream diff <pair_id>                    # all files
cc-janitor dream diff <pair_id> --file MEMORY.md   # one file
cc-janitor dream diff <pair_id> --json
```

### 4.3 Dream doctor

Diagnostic command running the **9-check matrix (Q5 decision)**:

| # | Check | Default threshold | Severity on fail |
|---|-------|-------------------|-------------------|
| 1 | Stale `.consolidate-lock` (PID dead) | n/a | FAIL |
| 2 | `autoDreamEnabled` state in `~/.claude/settings.json` | `true` recommended | WARN if false |
| 3 | Server-gate inference (`claude --print --headless "/dream"` → "Unknown skill") | n/a | WARN |
| 4 | Last successful dream (mtime of `MEMORY.md` since last paired snapshot) | n/a | informational |
| 5 | Backup directory health (exists, not bloated) | `disk_warning_mb = 100` | WARN |
| 6 | MEMORY.md cap usage per project | `memory_md_line_threshold = 180` | WARN (cap is 200) |
| 7 | Disk usage of `~/.cc-janitor/backups/dream/` | `disk_warning_mb = 100` | WARN |
| 8 | Memory file count per project | `memory_file_count_threshold = 50` | WARN |
| 9 | Cross-project duplicate line count summary | top N most duplicated | informational |

All thresholds are read from `~/.cc-janitor/config.toml` (§4.6). Result type:

```python
@dataclass
class DoctorCheck:
    id: str
    title: str
    severity: Literal["OK", "WARN", "FAIL", "INFO"]
    message: str
    detail: dict | None = None
```

CLI:

```bash
cc-janitor dream doctor          # human-readable
cc-janitor dream doctor --json   # for scripting
```

The existing top-level `cc-janitor doctor` (added in Phase 1) gains a single
line: `Dream:    9 checks — 0 FAIL, 2 WARN (run \`cc-janitor dream doctor\`)`.

### 4.4 Dream rollback

Restores the pre-snapshot mirror back to the original
`~/.claude/projects/<slug>/memory/` tree. Reuses Phase 1's backup/restore
mechanics:

1. Before restoring, the current post-state is itself soft-deleted to
   `~/.cc-janitor/.trash/<ts>/dream-rollback-<pair_id>/` so the rollback is
   itself reversible via `cc-janitor undo`.
2. The pre-mirror is copied back to the original paths.
3. An audit-log entry is written with `cmd: "dream rollback"`,
   `changed: {pair_id, files_restored, trash_path}`.

CLI:

```bash
cc-janitor dream rollback <pair_id>              # dry-run, prints plan
cc-janitor dream rollback <pair_id> --apply      # requires CC_JANITOR_USER_CONFIRMED=1
```

If `storage == "tar"`, the implementation extracts the tar to a temp dir and
proceeds identically.

### 4.5 Sleep hygiene metrics

**Q4 decision = keyword-based / regex / exact match everywhere.** LLM-based
semantic detection is explicitly deferred.

```python
@dataclass
class ProjectHygiene:
    project_slug: str
    memory_md_size_lines: int
    memory_md_cap: int                        # from config.toml
    relative_date_density: float              # matches / total_lines
    relative_date_matches: list[tuple[Path, int, str]]   # (file, line_no, term)
    cross_file_dup_count: int                 # via core.memory.find_duplicate_lines
    contradicting_pairs: list[tuple[str, list[Path]]]    # (subject, files)

@dataclass
class HygieneReport:
    generated_at: datetime
    projects: list[ProjectHygiene]
    totals: dict
```

**Metric algorithms:**

- `memory_md_size_lines` — `len(MEMORY.md.read_text().splitlines())`.
  Threshold from `config.toml [dream_doctor].memory_md_line_threshold`
  (default 180; Anthropic's hard cap is reportedly 200).
- `relative_date_density` — regex
  `\b(yesterday|today|recently|now|last week|вчера|сегодня|недавно|на прошлой неделе|в прошлый раз|в этот раз|на днях)\b`
  (case-insensitive) over every `.md` under the project's memory dir. Density
  = matches / total_lines. Surfaces lines that will go stale on next Dream.
- `cross_file_dup_count` — reuse Phase 1
  `core.memory.find_duplicate_lines(paths, min_length=8)`. Extended to also
  include lines from the `MEMORY.md` index (the index sits one directory up;
  current code excludes it).
- `contradicting_pairs` — for every line matching
  `(?i)\b(never|don'?t|stop|avoid)\b\s+(.+)` extract subject; same for
  `(?i)\b(always|prefer|use)\b\s+(.+)`. If two extracted subjects share ≥4
  tokens (Jaccard), flag as candidate contradiction. Imperfect; the doctor
  output marks these "needs review".

Surface:

- CLI: `cc-janitor stats sleep-hygiene [--project P] [--json]`
- TUI: Audit tab (existing) gains a "Sleep hygiene" sub-pane summary row;
  click-through into the new Dream tab for detail.

### 4.6 Settings audit hook + `config.toml`

**Settings audit hook.** On every `cc-janitor dream doctor` and on every
daemon iteration when `--dream` is set, compute a SHA-256 of
`~/.claude/settings.json`'s `autoDreamEnabled` value. Compare against the
last-seen value cached at `~/.cc-janitor/settings-audit.json`. On change,
append an audit entry:

```json
{"ts": "2026-05-11T15:00:00Z",
 "cmd": "settings-observe",
 "changed": {"key": "autoDreamEnabled",
             "old": false, "new": true,
             "source": "~/.claude/settings.json"}}
```

Surfaced as a `DoctorCheck` INFO row in `dream doctor` output: "Auto Dream
was enabled on <date>. Do you have backups configured? See `cc-janitor watch
start --dream`."

**`~/.cc-janitor/config.toml` — optional, all defaults hardcoded if absent.**

```toml
[dream_doctor]
disk_warning_mb = 100
memory_file_count_threshold = 50
memory_md_line_threshold = 180

[snapshots]
raw_retention_days = 7
tar_retention_days = 30

[hygiene]
relative_date_terms_extra = []       # user can extend the regex term list
contradiction_jaccard_threshold = 0.5
```

Loader API:

```python
# core/config.py
@dataclass
class Config:
    dream_doctor: DreamDoctorConfig
    snapshots: SnapshotsConfig
    hygiene: HygieneConfig

def load_config(path: Path | None = None) -> Config: ...
```

`load_config()` is called once per CLI invocation (and once per daemon poll
iteration, with a 60-second mtime-cached re-read). Missing file → all
defaults. Malformed file → emit warning, fall back to defaults.

## 5. Data model (consolidated)

```python
# core/dream_snapshot.py
@dataclass
class DreamSnapshotPair:
    pair_id: str
    project_slug: str
    project_path: Path
    claude_memory_dir: Path
    ts_pre: datetime
    ts_post: datetime | None       # None while lock still held
    paths_in_pre: list[Path]       # relative
    paths_in_post: list[Path] | None
    file_count_delta: int | None
    line_count_delta: int | None
    has_diff: bool | None
    dream_pid_in_lock: int | None
    storage: Literal["raw", "tar"]

# core/dream_diff.py — see §4.2
# core/dream_doctor.py — see §4.3
# core/sleep_hygiene.py — see §4.5
# core/config.py — see §4.6
```

Persistence:

| Path | Format | Purpose |
|------|--------|---------|
| `~/.cc-janitor/dream-snapshots.jsonl` | JSONL, one record per pair | History |
| `~/.cc-janitor/settings-audit.json` | JSON | Last-seen `autoDreamEnabled` |
| `~/.cc-janitor/backups/dream/<pair_id>-{pre,post}/` | raw tree | First 7 days |
| `~/.cc-janitor/backups/dream/<pair_id>.tar.gz` | tar | Days 7–30 |
| `~/.cc-janitor/config.toml` | TOML | User overrides |

## 6. CLI surface

```bash
# Dream subapp (new top-level)
cc-janitor dream snapshot now                       # mutation (--apply gate)
cc-janitor dream history [--project P] [--json]     # list pairs
cc-janitor dream diff <pair_id> [--file F] [--json] # show diff
cc-janitor dream doctor [--json]                    # diagnostics
cc-janitor dream rollback <pair_id> [--apply]       # mutation
cc-janitor dream prune --older-than-days 30 [--apply]   # mutation

# Watcher extension
cc-janitor watch start --dream [--no-memory]        # mutation
# (existing watch stop/status unchanged)

# Stats extension
cc-janitor stats sleep-hygiene [--project P] [--json]

# Backups extension (Phase 3 backups subapp)
cc-janitor backups tar-compact --kind dream --older-than-days 7 [--apply]
```

Read-only / safe-for-Claude: `dream history`, `dream diff`, `dream doctor`,
`stats sleep-hygiene`, `watch status`. Everything else requires
`CC_JANITOR_USER_CONFIRMED=1`.

## 7. TUI screens

**Q3 decision = new 8th tab.** The TUI's `compose()` (currently 7 tabs) adds:

```python
with TabPane("Dream", id="dream"):
    from .screens.dream_screen import DreamScreen
    yield DreamScreen()
```

`DreamScreen` layout:

```
┌─ Dream snapshots ──────────────┬─ Diff ────────────────────────────────┐
│ Date       Project    Files Δ  │ MEMORY.md                             │
│ ─────────────────────────────  │ - feedback_no_n8n.md                  │
│ 2026-05-11 life-hub   −1 / −47 │ - project_meridian_game.md            │
│ 2026-05-10 vpn-bot    +2 / +18 │ ─────────────────────────────────────│
│ 2026-05-09 diabot      0 / +3  │ @@ -1,7 +1,7 @@                       │
│ ...                            │ -recently we decided ...              │
│                                │ +on 2026-05-09 we decided ...         │
│                                │                                       │
│ [r] rollback  [d] details      │ [/] filter file  [n] next file        │
└────────────────────────────────┴───────────────────────────────────────┘
```

Reuses existing widgets (`DataTable`, `Static`, key bindings). Rollback
invocation passes through `tui/_confirm.py` `ConfirmModal` (introduced in
0.3.2). Audit log entries from the TUI carry `mode="tui"`.

The existing Audit tab gains a one-line summary row: "Sleep hygiene: 3
warnings (1 oversize MEMORY.md, 2 relative-date hotspots)" with a "Details
→ Dream tab" hint.

Common keys preserved: F1 help, F2 lang switch, F10 quit, `/` filter,
`?` action menu.

## 8. Testing strategy

| Layer | Tool | Target |
|-------|------|--------|
| `core/config.py` | pytest, hypothesis | round-trip TOML loader, missing-file defaults |
| `core/dream_snapshot.py` | pytest with `tmp_path` + fake lock file | state machine transitions, raw mirror write, tar storage |
| `core/dream_diff.py` | pytest | added/removed/changed file classification, unified diff content |
| `core/dream_doctor.py` | pytest | all 9 checks against synthetic Claude-home fixture |
| `core/sleep_hygiene.py` | pytest + small `.md` fixtures with known terms | every metric, multilingual (en+ru) regex hits |
| `cli/commands/dream.py` | `typer.testing.CliRunner` | every subcommand happy path + confirm gate |
| `tui/screens/dream_screen.py` | `pytest-textual-snapshot` | rendering with 0/1/many pairs |
| Watcher `--dream` integration | pytest with synthetic lock-file lifecycle | both events fire, jsonl record correct |
| Round-trip rollback | pytest end-to-end | snapshot → mutate → rollback restores byte-identical tree |

All tests use `monkeypatch.setenv("HOME", tmp_path)` and the
`mock-claude-home/` fixture (extended with one project containing a
`.consolidate-lock`).

Phase 3 baseline = ~200 passing. Phase 4 target = +35 → ~235 passing.

## 9. Documentation deliverables

1. **`README.md`** — add "Dream safety net" section to the feature list,
   2-line elevator pitch, one screenshot of `dream doctor` output.
2. **`README.ru.md`** — mirror.
3. **`docs/cookbook.md`** — three new recipes:
   - "Auto Dream just rewrote my memory — how do I see what changed?"
   - "Auto Dream is silently disabled — diagnose it"
   - "Set up scheduled snapshot-around-Dream so I never lose memory again"
4. **`docs/architecture.md`** — append §6 documenting the dream subsystem,
   including the state machine diagram and storage layout.
5. **`docs/CC_USAGE.md`** — append the five new read-only subcommands so
   Claude Code can recommend them in session.
6. **`CHANGELOG.md`** — `[0.4.0]` block.
7. **In-tool help** — every `dream` subcommand carries an example.

## 10. Out of scope (YAGNI for Phase 4)

- ❌ **`cc-janitor pre-dream` orchestrator** — Hypothesis B, deferred to
  Phase 5 once Anthropic's API has stabilized.
- ❌ **`cc-janitor dream --headless` wrapper** for users with the server
  gate off — same reason; would couple us to `claude --headless /dream`
  command surface.
- ❌ **Cross-project consolidation / `monorepo lift`** — Hypothesis B.
- ❌ **LLM-based semantic diff** of memory changes — too expensive, too
  subjective. Phase 5 candidate if user demand is real.
- ❌ **Auto-merge of contradicting feedback pairs** — only flag, never fix.
- ❌ **Real-time UI notifications when Auto Dream fires** — doctor + audit
  log are sufficient.
- ❌ **Telemetry of snapshot frequency to a remote service** — privacy-first.

## 11. Open questions (resolved before this doc)

The five open questions from the strategic analysis are all resolved:

| # | Question | Resolution |
|---|----------|------------|
| 1 | Storage layout (raw / tar / hybrid) | **Hybrid (C):** raw 7 days, tar 23 days more. |
| 2 | Trigger model (always-on / opt-in / hybrid) | **Opt-in (A):** `cc-janitor watch start --dream` flag. |
| 3 | TUI placement | **New 8th tab (B):** `DreamScreen` with list + diff panels. |
| 4 | Sleep-hygiene metric implementations | **Keyword/regex/exact-match (A)** for all four metrics; LLM deferred. |
| 5 | `dream doctor` check list | **Base 6 + 3 additions (disk usage, file count, dup summary), all configurable via `config.toml`.** |

No further open questions; implementer may proceed directly to the MVP plan.

## 12. Approval trail

- Scope: Hypothesis A ("Sleep safety net"), confirmed.
- Five open questions: resolved as above.
- Phases: 4 (this), with B-scope items deferred to Phase 5.
- Tech stack: stdlib + existing extras, no new mandatory deps.
- Auth model: identical to Phases 1–3 — read-only free for Claude,
  mutations gated by `CC_JANITOR_USER_CONFIRMED=1`, every action audit-logged.
- Target version: `v0.4.0`.

---

**Next step:** see `docs/plans/2026-05-11-cc-janitor-phase4-mvp.md` for the
13-task TDD implementation plan.
