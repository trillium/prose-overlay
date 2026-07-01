# Roadmap — what's shipping, what's queued, what's blocked

> Single-page running scratchpad. Kept small on purpose. Full scope for each
> item lives in the linked doc. When something ships, move it under "Shipped
> — Recent" and add the SHA. When something is truly done, delete the line.
>
> Last touched: 2026-07-02.

## In-flight (agents running on your local main right now)

- **Paint-pipeline retirement** (steps 6–15) — Forge `a1b26949119830985`.
  Bringing `to_paint_ops` to full paint parity (bubbles, help, selection,
  flash, panel frame), then removing the `PROSE_OVERLAY_LAYOUT_MODEL` env
  gate, then deleting `ui/draw_tokens.py`, `ui/draw_panels.py`,
  `ui/help.py`, `internal/panel_layout.py`. Currently around step 12 of
  ~15 (draw_tokens strip). Scope in commit log — no dedicated doc.

## Queued — small, ready to ship

- **Adaptive help zone** — `docs/ADAPTIVE_HELP_ZONE_SCOPE.md`.
  Three-state help surface (empty→full, non-empty→side, overflow→hidden).
  Phase 1 is a field-add on `_State` + rename of `hints_hidden_by_overflow`.
  **Blocked on**: retirement Forge merging its `layout_root.py` +
  `draw_from_model.py` work first.
- **R3 — color-prefix capture consolidation** —
  `docs/GRAMMAR_STRUCTURE_PARITY.md §5`. Introduce
  `<user.prose_overlay_hat>` capture that folds the optional color
  prefix. Would collapse ~13 more rules (109 → ~96). Zero behavior
  change. Not blocked.

## Queued — medium

- **Sub-move continuation for retirement** — the retirement Forge might
  not finish all 15 steps in one run. Whatever's still on the plan when
  it lands is queued for the next Forge spawn.
- **CodeRabbit findings on subsequent PRs** — every PR gets a review; roll
  the fixes into small standalone PRs like `#4` for PR `#2`.

## Queued — bigger

- **Cursorless action fixture parity work** —
  `docs/CURSORLESS_ACTIONS_COVERAGE.md`. Layer 7 walks 188 fixtures; 2
  full pass today, 13 partial. Top 5 gaps:
  1. `bring` misses space padding at token boundary
  2. Clone cursor position
  3. Wrap cursor offset by `left.length`
  4. Bring cursor semantics for "end of inserted content"
  5. `containingScope:character` unsupported
- **`glyph` scope** — `docs/CURSORLESS_SCOPE_COVERAGE.md` names it as the
  #1 next-scope-to-ship. Bundle handler already present at
  `js/prose_resolve_targets.js:14756`; only grammar routing missing.
- **`customRegex` scope** — same doc, #2. Bundle handler present; blocked
  on OQ1 (who authors the vocabulary).
- **Paint parity of legitimate paint code deletion** — after retirement
  Forge finishes, verify visual behavior against a live overlay before
  merging. Headless can't detect visual regressions.

## Queued — R7 (gated on ISC-8)

- **Route range verbs through composable dispatcher** —
  `docs/GRAMMAR_STRUCTURE_PARITY.md §5 R7`. Delete ~8 more rules
  (109 → ~101) by folding `chuck head/tail/past` and `change head/tail`
  into the composable `{simple_action} <cursorless_target>` rule.
  **Blocked on**: JS resolver fully-green on the range shapes (ISC-8
  live-only rows 11/12/16/17).

## Refactor scoreboard

- Baseline (session start): **123 rules** across 9 `.talon` files.
- After R4 (swap) + R6 (wrap) — grew to **126**.
- After R1 + R2 (2026-07-01, commit `705b5ec`) — **109** across 8 files.
- After R3 (queued): **~96 projected**.
- After R7 (blocked): **~88 projected**.
- Reference (cursorless.talon): 22 rules in 1 file.

## Shipped — recent (rolling; prune when stale)

- **R1 + R2 grammar refactor** — commit `705b5ec` (2026-07-01). Retire
  duplicate bring/move rules; 126 → 109 across `.talon` files.
- **Grammar mid-phrase leakage fix** — commit `c5465e7` (2026-07-01).
  End-anchor `<user.letters>` and `{user.symbol_key}` rules so they
  don't chew subphrases of a prose utterance
  (`is made of cardboard` → `ism of cardboard` bug).
- **Layer 7 action fixture harness** — PR #11 (2026-07-01). 188 fixtures
  walked; 2 pass, 13 partial, 173 skipped. Coverage doc at
  `docs/CURSORLESS_ACTIONS_COVERAGE.md`.
- **Full pure-function refactor substrate** — PRs #1, #2, #3, #5, #6,
  #7, #8, #9, #10 + PR #12 (partial retirement). State →
  LayoutModel → PaintOps → Skia pipeline shape locked in. Env-gated
  today; retirement Forge is currently removing the gate.
- **Scope docs landed this session**: `ADAPTIVE_HELP_ZONE_SCOPE.md`,
  `CURSORLESS_SCOPE_COVERAGE.md`, `BUNDLE_SHAPE_SCOPE.md`,
  `BUNDLE_REST_SCOPE.md`, `SUBWORD_INVESTIGATION.md`,
  `CURSORLESS_ACTIONS_COVERAGE.md`, `GRAMMAR_STRUCTURE_PARITY.md`,
  `CURSORLESS_NEAR_CURSOR_BIAS.md`, `GREEDY_HAT_CURSOR_SCOPE.md`,
  `HOMOPHONE_*.md` (existing), `SCENARIOS.md`.

## How to use this file

- Add a queue item when you scope something. Delete/move when it ships.
- Cross-reference the scope doc; don't duplicate its content here.
- Keep sections tight. If a section grows past ~10 items, split by
  size (small/medium/big) not by area.
- Not exhaustive on purpose. If a queued item isn't here, it either
  never got scoped or was worth forgetting.
