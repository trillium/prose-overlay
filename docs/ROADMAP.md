# Roadmap — what's shipping, what's queued, what's blocked

> Single-page running scratchpad. Kept small on purpose. Full scope for each
> item lives in the linked doc. When something ships, move it under "Shipped
> — Recent" and add the SHA. When something is truly done, delete the line.
>
> Last touched: 2026-07-02.

## In-flight

- **PR #13 review** — the refactor-completion PR (18 commits: retirement
  steps 6–15 + grammar R1+R2 + three live-bug fixes + three scope docs).
  Awaiting merge. Ready to click through when reviewed.

## Queued — small, ready to ship

- **R3 — color-prefix capture consolidation** —
  `docs/GRAMMAR_STRUCTURE_PARITY.md §5 R3`. Introduce
  `<user.prose_overlay_hat>` capture that folds the optional color
  prefix. Would collapse ~13 more rules (109 → ~96). Zero behavior
  change. Not blocked.
- **Adaptive help zone — Phase 1** — `docs/ADAPTIVE_HELP_ZONE_SCOPE.md`.
  Field-add on `_State` + rename of `hints_hidden_by_overflow`. Unblocked
  now that retirement Forge landed `layout_root.py` + `draw.py`
  consolidation. **Small effort.**
- **Layer 7 top-1 gap fix** — `bring` misses space padding at token
  boundary. Fixture-verified via Layer 7. Likely a one-liner in
  `shim/actions_cursorless.py:prose_overlay_bring_move` or the bundle.

## Queued — medium

- **CodeRabbit findings on PRs #5–#13** — every merged PR gets an
  automated review. Pattern from PR #4 (fixes for PR #2 findings): batch
  each PR's findings into a small standalone PR after merge. **Backlog
  triage needed** — check PR review tabs before spawning.
- **Adaptive help zone — Phase 2** — `docs/ADAPTIVE_HELP_ZONE_SCOPE.md`.
  Extend `build_help_layout` to accept a `mode` param + widened content
  rect. Depends on Phase 1.
- **Layer 7 top-5 gap fixes** —
  `docs/CURSORLESS_ACTIONS_COVERAGE.md`. Landing all five bumps the
  headless pass rate meaningfully:
  1. `bring` space padding (as above)
  2. Clone cursor position (preserve relative in-word offset)
  3. Wrap cursor offset by `left.length`
  4. Bring cursor at "end of inserted content"
  5. `containingScope:character` modifier

## Queued — bigger

- **`glyph` scope** — `docs/CURSORLESS_SCOPE_COVERAGE.md` names it as the
  #1 next-scope-to-ship. Bundle handler already present at
  `js/prose_resolve_targets.js:14756`; only grammar routing missing.
- **`customRegex` scope** — same doc, #2. Bundle handler present; blocked
  on OQ1 (who authors the vocabulary for prose users).
- **Live visual verification of the retirement** — headless can't detect
  visual regressions and the retirement Forge changed the paint path.
  Someone (you) needs to open the overlay in real Talon and confirm
  bubbles / help / shape hats / letter hats / homophone underlines /
  selection / flash all still render pixel-identical. Follow-up sub-move
  candidates already flagged in PR #13 body:
  - Bold title/section header rows in help pager (need `bold: bool` on
    `TextOp`)
  - Close hint composition (would need `overlay_kit.py` internals in the
    pure builder)

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
- After R1 + R2 (2026-07-02, commit `705b5ec`) — **109** across 8 files.
- After R3 (queued): **~96 projected**.
- After R7 (blocked): **~88 projected**.
- Reference (cursorless.talon): 22 rules in 1 file.

## Shipped — recent (rolling; prune when stale)

- **Paint pipeline retirement complete** — PR #13 (2026-07-02). Steps
  6–15 landed: env gate removed (`PROSE_OVERLAY_LAYOUT_MODEL` gone),
  `layout(state) → to_paint_ops → execute` is the only paint path,
  three files deleted (`draw_panels.py`, `panel_layout.py`,
  `draw_from_model.py` = 803 LOC), `draw_tokens.py` shrank 365 → 55
  lines.
- **Cursor mark boundary fix** — PR #13 commit `794e1ef` (2026-07-02).
  `chuck this` after `take air` correctly targets `air` now. Cursor
  gap N resolves to token N-1 (prefer LEFT at boundaries), matching
  cursorless upstream.
- **`this` mark → active selection** — PR #13 commit `8ab582c`
  (2026-07-02). When a selection is present, `this` mark returns the
  full selection range. Complements the cursor boundary fix for
  multi-token selections.
- **Grammar mid-phrase leakage fix** — PR #13 commit `c5465e7`
  (2026-07-02). End-anchor `<user.letters>` and `{user.symbol_key}`
  rules so they don't chew subphrases of a prose utterance
  (`is made of cardboard` → `ism of cardboard` bug).
- **R1 + R2 grammar refactor** — PR #13 commit `705b5ec` (2026-07-02).
  Retire duplicate bring/move rules; 126 → 109 across `.talon` files.
  `prose_overlay_bring_move.talon` deleted.
- **Layer 7 action fixture harness** — PR #11 (2026-07-01). 188 fixtures
  walked; 2 pass, 13 partial, 173 skipped. Coverage doc at
  `docs/CURSORLESS_ACTIONS_COVERAGE.md`.
- **Full pure-function refactor substrate** — PRs #1, #2, #3, #5, #6,
  #7, #8, #9, #10 + PR #12 (partial retirement) + PR #13 (completion).
  Pipeline shape locked in and now the ONLY paint path.
- **Scope docs landed this session**: `ADAPTIVE_HELP_ZONE_SCOPE.md`,
  `CURSORLESS_SCOPE_COVERAGE.md`, `BUNDLE_SHAPE_SCOPE.md`,
  `BUNDLE_REST_SCOPE.md`, `SUBWORD_INVESTIGATION.md`,
  `CURSORLESS_ACTIONS_COVERAGE.md`, `GRAMMAR_STRUCTURE_PARITY.md`
  (+ §5a audit), `CURSORLESS_NEAR_CURSOR_BIAS.md`,
  `GREEDY_HAT_CURSOR_SCOPE.md`, `HOMOPHONE_*.md` (existing),
  `SCENARIOS.md`.

## How to use this file

- Add a queue item when you scope something. Delete/move when it ships.
- Cross-reference the scope doc; don't duplicate its content here.
- Keep sections tight. If a section grows past ~10 items, split by
  size (small/medium/big) not by area.
- Not exhaustive on purpose. If a queued item isn't here, it either
  never got scoped or was worth forgetting.
