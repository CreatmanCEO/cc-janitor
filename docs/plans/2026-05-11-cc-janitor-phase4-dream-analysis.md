# cc-janitor Phase 4 — strategic analysis: Auto Dream integration

> **Date:** 2026-05-11
> **Type:** strategic design memo, not yet an implementation plan
> **Audience:** project owner — decide scope, then commission writing-plans pass
> **Status:** Draft for review

## 1. Executive summary

Anthropic shipped **Auto Dream** (LLM-driven memory consolidation in Claude Code) **silently behind a server-side feature flag** as of v2.1.81 (March 2026). The flag `autoDreamEnabled` is in Claude Code's settings schema since at least that release. Users have been hitting it accidentally — one user (issue #47959) had **23 memory files deleted in a single day with no backup, no diff, no audit log**.

cc-janitor's Phase 1-3 primitives — backup-before-write, audit log, soft-delete, USER_CONFIRMED gate, snapshot history — **map exactly onto the verified gaps in Auto Dream's safety story**. This is the strongest positioning opportunity since the project started: not "another Claude Code tool", but the **safety net around Anthropic's own black-box consolidation**.

**Recommendation: Phase 4 = "Sleep safety net".** Six focused features, ~10 TDD tasks, ship as **v0.4.0** in ~1 week. Defer the broader "Dream orchestrator" ideas (pre-Dream cleanup pipeline, headless wrapper, cross-project consolidation) to Phase 5 once Anthropic's API stabilizes.

## 2. What is "Auto Dream", verified

Two distinct features get conflated; only one is relevant for cc-janitor.

| Feature | Where it runs | Status as of 2026-05-11 |
|---------|---------------|--------------------------|
| **Managed Agents "Dreaming"** | Anthropic-hosted Managed Agents (server-side) | Research preview, announced at Code with Claude 2026-05-06. Not relevant — users don't self-host. |
| **Claude Code "Auto Dream"** | Local, in the `claude` CLI | **Shipped silently** behind server-side flag. Not in CHANGELOG. Not in official docs. |

### Confirmed implementation facts

- Setting key **`autoDreamEnabled`** in `~/.claude/settings.json`, boolean, default off. Confirmed in the official JSON schema (visible in cc-janitor's `update-config` skill output).
- Server-side gate. Toggling locally doesn't guarantee execution — many users see `/dream` return "Unknown skill" despite `autoDreamEnabled: true` (issue #38461, still open since 2026-03-24).
- `/dream` is delivered as a **skill**, not a built-in slash command (issue #40244).
- Trigger thresholds: claimed **24 hours AND 5 sessions** (both must hold). Not officially documented; configurability via `minHours` / `minSessions` keys claimed but not verified.
- Paths written: `~/.claude/projects/<slug>/memory/MEMORY.md` (index, capped ~200 lines) and per-topic `*.md` files. Whether the global `~/.claude/CLAUDE.md` is also rewritten is **not verified**.
- Lock file: `~/.claude/projects/<slug>/memory/.consolidate-lock` containing the dream sub-agent PID.
- **Writes back in place. No diff, no preview, no confirmation.** Issue #47959 is the canonical example: 23 files deleted silently.
- **No built-in backup.** Anthropic's own documentation (when it exists) tells users to back up `~/.claude/` manually.
- **No audit log.** Issues #50694 and #38493 explicitly request one.
- **Open lock-file bug (#50694, 2026-05-11):** a stale `.consolidate-lock` after a crash silently disables Auto Dream forever, with no user-visible signal.

### Not verified — community guesswork

- The 4-phase pipeline (Orient → Scan → Consolidate → Prune & Index) is community consensus across claudefa.st, decodethefuture.org, supalaunch.com — but **no Anthropic primary source**. Treat as plausible, not gospel.
- The Stop hook trigger is the third-party `grandamenium/dream-skill` repo's choice. Anthropic's actual scheduler is undocumented (#44820 requests `PreMemoryWrite`/`PostMemoryWrite` events, implying they don't exist).
- Sub-agent model and cost per cycle — undisclosed.

### Strategic read

Anthropic shipped a sharp tool with explicit user warnings to backup, no logging, no diff. **The gap is not "Anthropic forgot" — they're letting community build the safety harness.** That harness is cc-janitor's natural niche.

## 3. The six ideas from the input doc, mapped to current state

The Telegram-doc analysis proposed six integration ideas. Most map onto already-shipped Phase 1-3 primitives. The real Phase 4 work is **wiring + Dream-aware delta**, not new infrastructure.

| # | Idea | Already in cc-janitor (Phase 1-3) | What's missing for Dream integration |
|---|------|----------------------------------|--------------------------------------|
| 1 | **dream snapshot / dream diff** | `~/.cc-janitor/backups/`, soft-delete to `.trash/`, bundle export with SHA-256 manifest | **Dream-triggered snapshot:** watch for `.consolidate-lock` appearing → snapshot. Lock disappears → second snapshot + diff TUI viewer. No such hook today. |
| 2 | **Pre-dream cleanup pipeline** | `perms dedupe`, `perms prune --stale`, `context find-duplicates`, `memory archive` — all CLI subcommands | A single `cc-janitor pre-dream` orchestrator that chains these (and tells you total tokens saved before Dream runs). Trivial, mostly composition. |
| 3 | **Scheduler as Auto-Dream fallback** | Phase 2 scheduler (`schedule add/remove/run`) with cron + schtasks abstraction | A template that runs `claude --headless /dream` from cron (for users whose server-side gate is off). Plus snapshot-around. |
| 4 | **Hook debugger ↔ Dream Stop-hook** | Phase 2 `hooks simulate/validate/enable-logging` | Hook debugger needs a "Dream-mode" payload preset that mimics Anthropic's actual trigger conditions, so users can test their own pre/post hooks. |
| 5 | **Sleep hygiene report** | Phase 3 stats dashboard with daily snapshots + sparklines | New metrics: MEMORY.md size vs 200-line cap, density of relative dates ("yesterday", "недавно"), duplicate fragments across memory files, contradicting feedback pairs. Composes with existing stats. |
| 6 | **Cross-project consolidation** | Phase 3 monorepo discovery + nested .claude scan | "Three projects have the same memory fragment — lift to global" recommender. Deterministic version of what Managed Agents Dream does cross-agentically. |

**Observation:** zero of the six requires net-new infrastructure. All compose on top of shipped primitives. This is the strongest sign that Phase 4 should be tactical (wire + Dream-specific delta) not strategic (build new layer).

## 4. Hypotheses for Phase 4 shape

### Hypothesis A: "Sleep safety net" (recommended for v0.4.0)

Six features, narrow, defensive:

1. **`dream snapshot`** subsystem — file-watcher (extending Phase 3 watcher) keys on `.consolidate-lock` lifecycle. Snapshot to `~/.cc-janitor/backups/dream/<ts>-pre/` when lock appears, `<ts>-post/` when removed.
2. **`dream diff <ts>`** — TUI/CLI showing what Auto Dream changed: file-level (added/removed) + content-level (line diffs with semantic grouping: "this fact was rewritten", "this section was merged from 3 files").
3. **`dream doctor`** — first-class diagnostic: stale `.consolidate-lock` detector (the #50694 silent-killer), last successful dream timestamp, server-side gate inference (heuristic: `/dream` returning "Unknown skill" → flag off).
4. **`dream rollback <ts>`** — restores pre-dream snapshot. Reuses existing trash/restore primitives but with explicit Dream provenance in metadata.
5. **`stats sleep-hygiene`** — new metric subset within the existing stats screen: MEMORY.md size relative to 200-line cap, relative-date density, cross-file duplicate fragment count, contradicting-feedback detection (Phase 1 `context find-duplicates` extended with semantic awareness).
6. **Settings audit hook** — when user toggles `autoDreamEnabled`, write a marker; on next `cc-janitor doctor` run, surface "you enabled Auto Dream on <date>; do you have backups configured?"

Scope: ~10 TDD tasks, ~1 week to ship. All read-mostly except snapshot/rollback. Inherits Phase 1-3 audit + safety patterns.

### Hypothesis B: "Dream orchestrator"

All of A plus:
- **`cc-janitor pre-dream`** pipeline chaining `perms dedupe → perms prune → context find-duplicates → memory archive --stale --older-than 90d` with a "tokens saved" report.
- **`cc-janitor dream --headless`** wrapper that runs `claude --headless --print "/dream"` for users with server gate off. Useful but couples us tightly to Anthropic's command surface.
- **`monorepo lift`** — cross-project duplicate finder with "extract to global" suggestion.

Scope: ~16 tasks, ~2 weeks. More valuable long-term but couples us to Anthropic's behavior in two more places.

### Hypothesis C: "Stay below the API"

Don't integrate with Auto Dream specifically. Just keep building deterministic-auditor features (e.g., better context-cost visualization, faster session search, MCP server inspector). Let users use cc-janitor backup/audit/restore primitives manually around Dream.

Pros: zero coupling risk, no rework when Anthropic changes anything. Cons: forfeits the strongest positioning moment of the year.

### Hypothesis D: Adjacent — "memory layer across coding agents"

Generalize beyond Claude Code: Cursor, Aider, Continue, Cody all develop similar memory features. cc-janitor becomes the tool-agnostic memory janitor.

Too speculative. Cursor's memory model is fundamentally different (project-scoped, no shared global). Aider stores conversation history but doesn't consolidate. Don't bet on convergence.

## 5. Evaluation

| Hypothesis | Effort | Value | Risk | Ship velocity |
|-----------|--------|-------|------|---------------|
| A — Safety net | ~10 tasks | High: addresses verified user pain (#47959, #50694, #38493). All compose on Phase 1-3. | Low: even if Anthropic adds logging + hooks themselves, snapshots and rollback stay valuable. | 1 week |
| B — Orchestrator | ~16 tasks | Very high: full lifecycle ownership. | Medium: couples to `claude --headless /dream` which might change. | 2 weeks |
| C — Stay below | 0 | Low: forfeits positioning. | Zero coupling, but high opportunity cost. | N/A |
| D — Cross-agent | Unknown | Speculative. | High: betting on convergence between non-converging products. | Months |

**Decision: ship A as v0.4.0. Re-evaluate B as v0.5.0 in ~6 weeks after A is in users' hands and Anthropic's API has had time to surface.**

## 6. Positioning — for marketing later

The framing the input doc proposed — "cc-janitor is layer below Dream, the deterministic safety net around the black box" — survives the verification step. Refine to a single sentence:

> **cc-janitor: the deterministic safety harness around Claude Code's Auto Dream — snapshot before, diff after, rollback if needed, audit always.**

Concrete proof points from verified issues:

- "Issue #47959 reports 23 memory files deleted silently. With cc-janitor's `dream snapshot` and `dream rollback`, none of them would have been lost." — proven by `.cc-janitor/backups/dream/<ts>-pre/` semantics.
- "Issue #50694 reports stale `.consolidate-lock` silently disabling Auto Dream forever. `cc-janitor dream doctor` flags it on next run." — proven by lock-file inspector.
- "Issues #38493 and #50694 request an Auto Dream log. `cc-janitor`'s audit log records every snapshot, every rollback, every settings toggle." — proven by Phase 1 audit primitives.

This is positioning by gap, not by hype. Strongest possible angle for a third-party developer tool: solve verified pain that the platform owner has acknowledged but not fixed.

## 7. Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Anthropic ships first-class `PreMemoryWrite`/`PostMemoryWrite` hooks per #44820 | Use those when available; until then, lock-file watching is our hook. Switching is one-file refactor. |
| Anthropic ships built-in logging (`.dream-log.md` per #38493) | Our audit log captures *cc-janitor actions*, not Dream's internals. Complementary, not redundant. |
| Anthropic ships built-in diff/preview UI | Unlikely soon — they explicitly chose silent-write semantics. If they ship one, we collaborate (our diff stays useful for cross-session comparison they don't provide). |
| `/dream` skill changes its file paths | Our snapshot is path-agnostic — copies whatever `~/.claude/projects/*/memory/*.md` exists at moments T0 and T1. |
| Cost: snapshots accumulate disk | Reuse Phase 2 scheduler `trash-cleanup` template extended to `dream-backups`. 30-day retention. |
| Users don't enable Auto Dream → tool seems irrelevant | The same metrics + diagnostics work for users running `/dream` manually. And the **sleep-hygiene report** is useful even without Dream — gives users a why-care reason to look. |

## 8. What I've already verified that lets me write the actual plan

- Auto Dream is real, shipped, server-gated. (Multiple primary sources, GitHub issues.)
- `autoDreamEnabled` is a real setting. (Settings schema.)
- The user's actual environment: 35 memory files / 1124 lines total / global CLAUDE.md = 79 lines / MEMORY.md per-project under 200 lines. Below Anthropic's threshold for "triggers heavy pruning" but enough that Dream-induced loss would hurt.
- Lock file path semantics. (Issue #50694.)
- The community 4-phase model is unverified — so cc-janitor's diff must not assume any specific consolidation logic. Just compare file states at T0 vs T1.

## 9. What's still open before writing the implementation plan

1. **Storage layout for Dream backups.** Proposal: `~/.cc-janitor/backups/dream/<YYYYMMDDTHHMMSSZ>-<phase>/<original-tree>/`. Each backup tarred? Or raw mirror? Tar is smaller but slower to diff. Raw mirror enables `diff -r`. Pick raw mirror; tar in retention cleanup.
2. **Should `dream snapshot` always run, or only when user opts in?** Proposal: opt-in via `cc-janitor watch start --dream` mode. Don't auto-snapshot every memory write — too much noise.
3. **Where does the `dream diff` UI live in TUI?** Proposal: extend existing Memory tab with a "Dream" sub-pane reading from `~/.cc-janitor/backups/dream/`.
4. **Sleep hygiene metric specifications.** Define exactly:
   - "Relative date density" — regex over `вчера|yesterday|recently|недавно|в прошлый раз` and similar?
   - "Contradicting feedback pairs" — semantic? Or keyword-based (e.g. "never use X" + "always use X" in different files)?
   - "Cross-file duplicates" — fuzzy hashing? Or exact line match?
   - First pass: keyword-based + exact line match. LLM-based semantic detection deferred.
5. **`dream doctor` checks list.** Beyond stale `.consolidate-lock`, what else? Server-gate inference, MEMORY.md size, autoDreamEnabled state, last successful dream timestamp. Concrete check matrix needed.

## 10. Recommended next step

1. Discuss Hypothesis A scope with project owner (this doc).
2. If approved → commission a `writing-plans` pass producing `docs/plans/2026-05-XX-cc-janitor-phase4-mvp.md` with ~10 TDD tasks.
3. Then execute via subagent-driven cycle (as Phase 1-3 were executed). Realistic ship: v0.4.0 in ~1 week.

The biggest risk is **decision velocity, not technical complexity** — Auto Dream's user base grows whether cc-janitor responds or not. First-mover advantage on the safety-harness niche is real and time-bounded.

## Appendix A — verified issue references

Direct GitHub Issues anchoring this analysis:

- [#38461 — `/dream` returns "Unknown skill" despite autoDreamEnabled: true](https://github.com/anthropics/claude-code/issues/38461) (open, 17 comments)
- [#38493 — Request: `.dream-log.md` audit trail](https://github.com/anthropics/claude-code/issues/38493) (open)
- [#40244 — `/dream` routed to skills system instead of built-in handler](https://github.com/anthropics/claude-code/issues/40244)
- [#44820 — Request: `PreMemoryWrite` / `PostMemoryWrite` hook events](https://github.com/anthropics/claude-code/issues/44820)
- [#47959 — 23 memory files deleted silently by Auto Dream, no backup](https://github.com/anthropics/claude-code/issues/47959)
- [#50694 — Stale `.consolidate-lock` silently disables Auto Dream forever](https://github.com/anthropics/claude-code/issues/50694) (open, 2026-05-11)

## Appendix B — sources for Auto Dream technical details

- [Simon Willison live blog of Code with Claude 2026](https://simonwillison.net/2026/May/6/code-w-claude-2026/) — confirms Managed Agents Dreaming, mentions but does not confirm Auto Dream
- [Every — Inside Anthropic's 2026 Developer Conference](https://every.to/chain-of-thought/inside-anthropic-s-2026-developer-conference) (2026-05-07) — explicitly notes Auto Dream "has not yet been deployed to Claude Code, despite significant developer interest"
- [claudefa.st auto-dream mechanics guide](https://claudefa.st/blog/guide/mechanics/auto-dream) — community reverse-engineering
- [decodethefuture.org — Claude Code Auto Dream explained](https://decodethefuture.org/en/claude-code-auto-dream-explained/) (2026-03-26) — community write-up
- [VentureBeat — Anthropic introduces dreaming](https://venturebeat.com/technology/anthropic-introduces-dreaming-a-system-that-lets-ai-agents-learn-from-their-own-mistakes)
- [letsdatascience.com — Anthropic introduces dreaming for Claude agent memory consolidation](https://letsdatascience.com/news/anthropic-introduces-dreaming-for-claude-agent-memory-consol-32a279c9) (2026-05-07)
- [grandamenium/dream-skill (community reimplementation of the unreleased Anthropic feature)](https://github.com/grandamenium/dream-skill)
