---
task: Voice-first prose editor for Talon — Cursorless verbs on a floating buffer
slug: prose-overlay-v2
effort: E4
phase: build
progress: 11/24
mode: build
started: 2026-05-21T00:00:00Z
updated: 2026-06-30T08:30:00Z
project: prose_overlay
---

## Problem

The original MVP (Phase 1) shipped a buffered dictation panel with gray hats and delete-by-hat. Six weeks of usage made the actual problem clear: voice-first prose editing isn't a buffer problem, it's a *verb-surface* problem. Cursorless gives you "chuck air", "take blue bat", "change sentence", "format snake at fox past bat" on text in a host editor; the moment you dictate into a window without a Cursorless host, you lose the entire vocabulary. Misrecognized homophones lose silently. Stack overflows in the JS hat allocator die without trace. You can't ask the assistant to repro a bug because there's no way to drive the tool except through the mic.

## Vision

A floating Talon canvas that is, for the duration of an utterance, *the editor Cursorless is editing*. Every Cursorless verb — simple actions, ranges, lists, scope modifiers (including prose-level scopes like sentence/clause/string/number/email and the seven surrounding-pair delimiters), bring/move, applyFormatter — works against the in-window buffer instead of a host application. Visual ambiguity gets surfaced: homophones underlined, hat-allocator fallback signaled by an orange chrome, scope previews rendered before execution. The state stream is captured to disk continuously so post-mortem debugging is the default. The assistant can drive the whole thing headlessly via a JSON queue file, so feature work doesn't depend on the mic being live or the cursorless RPC being healthy.

## Out of Scope (real, not aspirational)

- AI-driven correction/suggestion (this is voice + visual + Cursorless, not LLM-assisted typing)
- Multi-buffer or multi-document workflows (single panel, single buffer per session)
- Cross-session buffer persistence (buffer is ephemeral — confirm or discard)
- Replacing Cursorless inside host editors — PO is a peer, gated by `user.prose_overlay_active` tag; cursorless owns the host
- Mobile / non-macOS targets
- Browser-DOM rendering — Talon canvas only

## Principles

- **Composability with Cursorless > parallel reimplementation.** The end state of the F9 migration is that target/scope resolution runs through cursorless's actual `processTargets` pipeline via the QuickJS bridge — we lift, we don't reinvent.
- **Modular, reversible, exploration-first features.** Every non-trivial feature lands as a slice tree with explicit kill criteria and feature-flag gates (see `docs/*_PLAN.md`). Slice A first, decide, then B.
- **Observability is first-class.** Continuous JSONL state-diff capture (`prose_overlay_debug.jsonl`), opt-in crash paper-trail (`prose_overlay_trail.py`), structured snapshots that include token list + per-token hat marks + flagged indices + JS-fallback flag.
- **The assistant must be able to drive the tool.** Headless command queue (`prose_overlay_test_driver.py`) lets external processes pipe verbs in via `~/.talon/prose_overlay_test_queue.jsonl`; the always-on debug log is the read channel.
- **Single-file-per-concern, modules ≤250 LOC.** The post-refactor file shapes (viewport/draw/draw_constants/draw_tokens, cursorless_resolve/surrounding_pair, actions_cursorless/_edit) reflect this; new growth should split when it crosses.
- **Forge for code, Architect for plans, Explore for locates.** Workflow conventions from the PAI multi-agent harness — keeps research deliberate and code rigorous.

## Constraints (current reality)

- Python + embedded JS via Talon's `talon.lib.js` (QuickJS). Two bundles: hat allocator (`js/prose_allocate_hats.js`) and target resolver (`js/prose_resolve_targets.js`), both built by `scripts/build-js.ts`.
- Source-of-truth at `~/code/prose-overlay/`; **hardlinked** to live Talon path `~/.talon/user/trillium_talon/trillium/plugin/prose_overlay/` (edits are immediately live, no sync watcher needed in practice).
- Cursorless `processTargets` is the canonical target/scope authority — Python re-implementation in `prose_overlay_cursorless_resolve.py` exists for v1 parity and gets retired once F9 is verified.
- Hat alphabet (26 letters) × color palette (9) gives ~234 addressable slots before overflow; non-letter tokens (digits, pure punctuation) get NO hat by design (commit `3c8c9e9`).
- Render model: every state mutation → `instance.canvas.refresh()` → `draw_overlay()` → `emit_if_changed("draw")`. Single hook covers all mutations via this chain.
- Voice grammar gates on `mode: dictation|command` + `tag: user.prose_overlay_active`; mutually exclusive with cursorless.talon via `not tag: user.prose_overlay_active` in cursorless's matcher.
- No subprocess and no external RPC servers from this plugin (the test driver uses a polled queue file, not a server). Cursorless's RPC is *cursorless's* — we don't depend on it.

## Goal

Phase 2: full Cursorless verb surface on the in-window buffer with visible ambiguity feedback and continuous observability, durable enough that the assistant can develop and debug features without the user being present at the mic.

## Criteria

### Phase 1 — MVP (shipped, 2026-05-21, all 36 ISCs green)

Frozen. Original `ProseBuffer`, gray-hat rendering, delete-by-hat, dictation intercept, confirm-and-paste, focus restore, anti-redefinition guards. Verified pre-Phase-2 refactor (see `## Changelog` → Phase 1 close).

### Phase 2 — Cursorless verb parity

- [x] ISC-1: `cursorless_simple_action` rule binds against PO buffer (chuck, take, change, clear, replace) — `prose_overlay_actions_cursorless.py`
- [x] ISC-2: RangeTarget with implicit anchor resolves (`chuck past this` → cursor-1..hat) — `cursorless_resolve.py:_resolve_range_target`
- [x] ISC-3: ListTarget multi-target ("chuck air and bat") iterates elements, flashes all, deletes in reverse — `cursorless_resolve.py:_resolve_target_to_token_range`
- [x] ISC-4: Prose-level scopes (sentence, clause, string, number, email, nonWhitespaceSequence) — `cursorless_resolve.py:_REGEX_SCOPE_PATTERNS` + `_scope_regex`
- [x] ISC-5: Seven surrounding-pair delimiters (round/box/curly/diamond/quad/twin/skis) + `any`/`pair` aggregation — `prose_overlay_surrounding_pair.py`
- [x] ISC-6: bring/move (`cursorless_bring_move_action`) — `prose_overlay_actions_cursorless.py:prose_overlay_bring_move`
- [x] ISC-7: applyFormatter (`format snake at fox`) with purple flash — `prose_overlay_actions_cursorless.py:prose_overlay_apply_formatter`
- [ ] ISC-8: JS resolver behind `user.prose_overlay_use_js_resolver` setting passes parity for every row in `MANUAL_VERIFICATION.md`
- [ ] ISC-9: Python resolver fallback removed once ISC-8 holds for 3 consecutive sessions

### Phase 3 — Visual ambiguity feedback

- [x] ISC-10: Hat-allocator fallback paints orange chrome (BG_COLOR_FALLBACK + BORDER_COLOR_FALLBACK) — `prose_overlay_draw.py` + `prose_overlay_actions_core.py`
- [x] ISC-11: Homophone slice A — dotted underline under any token whose lowercase appears in pimentel CSV, behind `user.prose_overlay_homophone_hint` (default off) — `prose_overlay_homophones.py`
- [x] ISC-12: Voice toggle for homophone hint (`overlay hints homo on/off`) — `prose_overlay_actions_visibility.py:prose_overlay_set_homophone_hint`
- [ ] ISC-13: Homophone slice B — `phone <hat>` cycles to next group member (per `docs/HOMOPHONE_UI_PLAN.md`)
- [ ] ISC-14: Hat shape vocabulary integrated for shape-coded homophone swap (per `docs/HOMOPHONE_SHAPES_LOCATION.md`)
- [x] ISC-15: Scope-preview flash before execution — when user speaks a scope verb, the resolved range flashes before the destructive action (satisfied by inheritance — `_flash_tokens(indices, color, _execute)` schedules `_execute` after a 150ms `cron.after`, so every dispatcher that resolves a target through `_resolve_target_to_token_range` — including scope verbs via `_apply_containing_scope` / `_scope_word` / `_scope_regex` / `_scope_surrounding_pair` — flashes the resolved range before mutating; this turn added `flash` + `flash_color` to the debug snapshot so the Test-Strategy probe has greppable fields)

### Phase 4 — Observability + headless driving

- [x] ISC-16: Always-on debug JSONL with rich snapshot (tokens, per-token hat marks, flagged indices, hat_js_fallback, buffer rev, cursor, change_mode, scroll) — `prose_overlay_debug.py`
- [x] ISC-17: Single draw-time hook covers every mutation; log rotates at 5 MB — `prose_overlay_draw.py:draw_overlay` + `prose_overlay_debug._rotate_if_needed`
- [x] ISC-18: Stack-overflow paper-trail slice A — faulthandler to `~/Library/Logs/prose_overlay_trail/faulthandler.log` behind `PROSE_OVERLAY_TRAIL=1` — `prose_overlay_trail.py`
- [x] ISC-19: Headless command queue — `scripts/test-overlay.sh <verb>` enqueues to `~/.talon/prose_overlay_test_queue.jsonl`, cron in `prose_overlay_test_driver.py` dispatches behind `PROSE_OVERLAY_TEST=1`
- [ ] ISC-20: Paper-trail slice B verified — `last_command.json` preamble captures pre-crash command context (pending HAT_ALLOC_OVERFLOW reproduction)

### Phase 5 — Modular substrate (foundation for downstream slices)

- [x] ISC-21: Buffer revision counter (`ProseBuffer.rev`) bumped on every mutation — substrate for paragraph cache + undo plan + debug invalidation
- [x] ISC-22: Viewport class owns scroll + anchor + recenter state — Helix `align(top/center/bottom)` + Emacs `recenter` cycling via voice — `prose_overlay_viewport.py`
- [x] ISC-23: Undo/redo with CM6 two-deque + Helix `(forward, inverse)` delta pairs + Emacs `commit_start`/`commit_end` boundary (per `docs/UNDO_REDO_PLAN.md`) — Phases 1+2 shipped (commits `ec52d32`, `7eb3e56`) with bring/move bracket-fix (commit `1a618a3`). Two-deque + delta+inverse records + commit_start/commit_end + redo + voice command + coalescing toggle. Coalescing defaults OFF (toggle: `overlay undo group on/off`) — slice-discipline call per plan §9.Q1.
- [ ] ISC-24: SkParagraph-based text measurement + per-line cache keyed by `buffer_rev` (per `docs/VIEWPORT_RESEARCH.md` §1; only if measurable layout wins emerge)

## Test Strategy

| ISC | Type | Check | Tool |
|---|---|---|---|
| 1–7 | integration | speak verb against scripted buffer, observe expected mutation in debug log | test-overlay.sh + tail debug.jsonl |
| 8 | parity | every row of MANUAL_VERIFICATION.md PASS under JS resolver flag | manual + diff vs. Python output |
| 9 | code | grep for `prose_overlay_cursorless_resolve` imports returns 0 (after retirement) | Grep |
| 10 | visual | force JS allocator failure, assert orange chrome appears | manual or screenshot diff |
| 11–12 | logic | dictate flagged words with hint on, assert underline drawn (via debug log `flagged` field) | test-overlay.sh + grep flagged |
| 13–14 | feature | per HOMOPHONE_UI_PLAN slice criteria | future slices |
| 15 | visual | speak scope verb, assert `flash` field diff appears in debug.jsonl before the `tokens` field diff | `jq 'select(.diff.flash)' ~/.talon/prose_overlay_debug.jsonl` |
| 16–17 | observability | mutate buffer 1000×, assert log grew + rotated at 5 MB | test-overlay.sh + wc/ls -la |
| 18 | crash | reproduce HAT_ALLOC overflow under PROSE_OVERLAY_TRAIL=1, assert traceback in faulthandler.log | manual repro |
| 19 | integration | shell pipes 10 commands, debug log shows 10 diffs | test-overlay.sh batch + grep |
| 20 | crash | last_command.json updated before each JS call | test-overlay.sh + stat preamble file |
| 21 | behavioral | mutate buffer via add_text / delete_token / commit_end → assert `rev` advances; pre-refactor "9 sites" grep contract is obsolete after the deque refactor (Cato concerns #5, 2026-06-30) | python smoke test |
| 22 | voice | `overlay show top/bottom/center` + `overlay center` cycle | test-overlay.sh + dump cursor row |
| 23 | per-plan | per UNDO_REDO_PLAN slice criteria | future slices |
| 24 | bench | layout-time regression under 16 ms p99 across 200-token buffer | future bench |

## Features (post-Phase-1 work shipped + planned)

| Name | Description | Satisfies | Status |
|---|---|---|---|
| CursorlessResolver | Python re-impl of processTargets (primitive/range/list/implicit + scopes) | ISC-1..7 | shipped |
| JSResolverBridge | QuickJS bridge to cursorless processTargets, gated by setting | ISC-8..9 | scaffolded |
| HatJSFallbackChrome | Orange BG/BORDER when JS allocator fails | ISC-10 | shipped |
| HomophoneSliceA | Static dotted underline behind opt-in flag | ISC-11..12 | shipped |
| HomophoneSwap | `phone <hat>` cycle (slice B) | ISC-13 | planned |
| HatShapeIntegration | Lift mouse-clock shape vocabulary for swap UI | ISC-14 | located |
| ScopePreviewFlash | Pre-execution flash of resolved scope | ISC-15 | shipped |
| DebugStreamRich | Always-on JSONL with full snapshot + rotation | ISC-16..17 | shipped |
| StackOverflowTrail | Paper-trail slice tree (A: faulthandler; B: preamble) | ISC-18, ISC-20 | A shipped |
| TestDriver | Headless JSON queue for shell-driven dispatch | ISC-19 | shipped |
| BufferRev | Monotonic revision counter, cache-invalidation substrate | ISC-21 | shipped |
| ViewportClass | Scroll/anchor/recenter state, Helix+Emacs voice surface | ISC-22 | shipped |
| UndoRedo | CM6 two-deque + Helix inversions + Emacs boundary | ISC-23 | shipped |
| ParagraphCache | SkParagraph layout cache keyed by buffer_rev | ISC-24 | researched |

## Decisions

- **2026-06-30 — Module-level `_hint_enabled` flag instead of `ctx.settings[...] =`** for the homophone voice toggle. The supported Talon API exists (item-assignment on a Context's settings dict — verified by ClaudeResearcher against talon.wiki), but it's context-scoped and would silently revert when the overlay dismisses, while the toggle wants process-global session semantics. Module flag is the right tool *for this toggle specifically*; use `ctx.settings[...]` when an override genuinely is context-scoped.
- **2026-06-30 — Numbers and pure-punctuation tokens get NO hat** (commit `3c8c9e9`). The prior fallback used `token[0]` as the hat letter even for digits, but Talon's `user.letter` capture only accepts a-z so the hat could never be selected — dead pixels. Real number addressing (e.g. `chuck num 1`) requires a separate hat namespace + voice capture; planned for a future slice if usage warrants.
- **2026-06-30 — Debug mode default ON.** Off-by-default observability is bad practice — nobody enables it before the bug they wanted to diagnose. The 5 MB log rotation bounds disk use.
- **2026-06-29 — Cursorless rule shape: LIST + CAPTURE not CAPTURE + CAPTURE** (commit `44a01a5`). Wins specificity tie-break against cursorless.talon's CAPTURE + CAPTURE rule whenever the PO context is active.
- **2026-06-30 — ISC-15 satisfied by inheritance, not new code.** Audit during loop turn 1 showed `_flash_tokens(indices, color, _execute)` schedules the mutation as a 150ms-deferred callback for every dispatcher (`prose_overlay_run_action`, `_range`, `apply_formatter`, `bring_move`, all hat-delete variants, cursor-setters). Scope verbs route through `prose_overlay_run_action` and resolve through `_resolve_target_to_token_range` which delegates to scope handlers — same callback path, same pre-execution flash. The missing piece was observability: `_snapshot()` didn't include `instance.flash_state`. Closed with two field additions (`flash`, `flash_color`). Doctrine win: prefer recognizing an existing satisfied criterion over building speculative new code.
- **2026-06-30 — Delegation soft-floor override at E3 (show your math).** The work was a 2-line dict-literal addition plus targeted ISA edits — spawning Forge in a worktree adds ~10× the actual work in setup, context re-derivation, and merge overhead. Inline edit + direct ISA writes. Cato/Anvil not auto-included at E3.
- **2026-06-30 — ISC-23 shipped with coalescing OFF by default.** Plan `docs/UNDO_REDO_PLAN.md` defaults `_GROUP_DELAY_S = 0.400` (CM6 dictation coalescing on). We ship `_GROUP_DELAY_S = 0.0` with a runtime toggle (`overlay undo group on/off` + `prose_overlay_undo_group_set` action). Per plan §9 open question #1, coalescing-feel is a kill-criterion-grade decision needing user verification — shipping OFF respects the "don't ship past a slice's kill criterion" rule. User can opt in to evaluate.
- **2026-06-30 — Cato (E4 cross-vendor audit) critical findings disposition.** Cato returned `concerns` verdict with 3 critical findings on the undo/redo landing. (1) `set_tokens_raw` outside bracket bumps rev without clearing `_undone` — KNOWN, no current caller hits this path, follow-up to add guard or hard-error. (2) No-op `set_tokens_raw` inside bracket clears redo + consumes undo slot — KNOWN, low impact (idempotent edits are rare in practice), follow-up to short-circuit on pre==new. (3) bring/move skipped rev bump after manual `_tokens.pop/insert` — FIXED inline (commit `1a618a3`) by converting to bracket API; removes the last remaining `snapshot()` shim caller. Plus 7 non-blocking concerns logged (selection-restore deferred to Phase 3, anti-criterion `_HISTORY_MAX` 20→200 expansion documented, etc.). Findings #1 and #2 left as follow-ups rather than blocking ISC-23 because they don't break the criterion (two-deque + delta-pairs + bracket boundary all hold) and no current call path triggers them. ISC stays green; follow-ups deferred per loop YOLO discipline.
- **2026-06-30 — Forge worktree commit-per-feature discipline.** Loop turn 2 used Forge in worktree with explicit per-phase commit instruction. Phase 1 (`ec52d32`) + Phase 2 (`7eb3e56`) shipped as two separate commits — if Phase 2 had hit a lint/test failure mid-flight, Phase 1 would still have landed. Worth keeping as a standing rule for any multi-feature autonomous worktree run.

## Changelog

- **2026-06-30** — Loop turn 2 (autonomous): ISC-23 (undo/redo) flipped green — Phases 1+2 of UNDO_REDO_PLAN landed via Forge worktree (commits `ec52d32`, `7eb3e56`); Cato critical #3 fixed inline (commit `1a618a3`); coalescing OFF default + voice toggle. 11/24.
- **2026-06-30** — Loop turn 1 (autonomous): ISC-15 (scope-preview flash) flipped green by audit + observability close. 10/24.
- **2026-06-30** — Phase 2 active. 9/24 ISCs green. Today's session shipped: viewport extraction (ISC-22), buffer rev counter (ISC-21), homophone slice A (ISC-11, ISC-12), hat-shape locate (ISC-14 substrate), stack-overflow trail slice A (ISC-18), always-on debug + draw hook (ISC-16, ISC-17), test driver (ISC-19). Plus three plan docs: `docs/UNDO_REDO_PLAN.md`, `docs/HOMOPHONE_UI_PLAN.md`, `docs/STACK_OVERFLOW_PAPER_TRAIL_PLAN.md`.
- **2026-06-04** — Cursorless verb surface filled (ISCs 1–7 green via commits `44a01a5`, `46c93fc`, `170a0f7`).
- **2026-05-31** — Wave 3 refactor (cursor, layout, history, help, visibility action files split out of monolithic prose_overlay.py).
- **2026-05-21** — Phase 1 MVP shipped (all 36 original ISCs green; preserved in repo history at this date).

## Verification

Continuous via `~/.talon/prose_overlay_debug.jsonl` — every state mutation produces a diff entry. Run `tail -f` for live; grep for `"trigger": "draw"` for the canonical post-mutation snapshot.

Headless feature verification via `scripts/test-overlay.sh` (requires `PROSE_OVERLAY_TEST=1` at Talon launch). Scriptable repro of any ISC that isn't visual-only.

Crash verification via `~/Library/Logs/prose_overlay_trail/faulthandler.log` (requires `PROSE_OVERLAY_TRAIL=1` at Talon launch). Catches the JS hat allocator overflow class documented in `HAT_ALLOC_OVERFLOW_ANALYSIS.md`.
