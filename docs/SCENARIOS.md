# Scenarios — Given / When / Then

> A free-form scratchpad for behavior specs written in narrative given/when/then
> form. Distinct from `MANUAL_VERIFICATION.md` (which is a rigid table for the F9
> JS-resolver migration walkthrough) and from `docs/HEADLESS_VERIFY_PLAN.md`
> (which tracks the test-layer architecture).
>
> Use this file to write a scenario BEFORE the test exists. Once the scenario is
> implemented in one of the test layers (L1/L2/L3/L4/L5) or lands as a
> MANUAL_VERIFICATION row, cross-reference it here and flip status.
>
> **When to use this doc:**
> - A behavior needs to be pinned down but the test scaffolding isn't ready yet.
> - The scenario doesn't fit MANUAL_VERIFICATION's F9-specific table shape.
> - You want to talk through a scenario in prose before deciding which layer owns it.

## Status legend

- `[ ]` — spec-only (behavior described; no test yet)
- `[~]` — partially implemented (some but not all of the scenario is covered)
- `[x]` — implemented; link to the test ID (e.g. `L5.20`, `MV row 21`)
- `[—]` — deprecated or superseded (link to the replacement)

## How to write one

```markdown
### S<N> — one-line title

**Given** [the setup — buffer contents, cursor state, mode, tags, settings].
**When** [the action — spoken form, keystroke, tool call, hook fire].
**Then** [the observable outcome — buffer state, selection, JS-resolver return, log line, side effect].

- **Status:** `[ ]` spec-only
- **Layer:** L1 / L2 / L3 / L4 / L5 / MANUAL_VERIFICATION / live-only
- **Related:** doc references, ISC IDs, prior scenario IDs
```

Number sequentially (`S1`, `S2`, ...). If a scenario splits into sub-cases,
use `S1.1`, `S1.2`. Never re-number on edit — dropped scenarios become
tombstones with a superseded-by pointer.

Group by feature area, not by chronological order.

---

## Cursorless verb parity

### S1 — sub-word ordinal on snake_case identifier

**Given** the buffer contains one token `one_two_three` (a snake_case identifier), with the letter hat `a` (gray) on the first character.
**When** the user speaks `take second word this` (`this` = implicit cursor mark).
**Then** the JS resolver returns a single contentRange covering the sub-word `two` (chars 4..6 inside the token), the buffer's selection state advances to that range, and the Skia render highlights `two` in the selection color.

- **Status:** `[ ]` spec-only
- **Layer:** L5 (parity — JS resolver ↔ expected sub-word range). Corresponding action-level L3 stubbed test and a MANUAL_VERIFICATION row for live confirmation.
- **Related:** `docs/SUBWORD_INVESTIGATION.md` §5 (test design), `docs/FEATURE_PARITY.md §3c`, `docs/GRAMMAR_STRUCTURE_PARITY.md §7a`. Python resolver at `cursorless/resolve.py:108-115` will return token-level; asymmetric-gap expected until ISC-9 lands.

---

## Grammar routing / arbitration

### S2 — compound `change <letter> <raw_prose>` seals a whole utterance

**Given** the overlay is showing, the buffer contains `the fox`, hat `t` on `the` and hat `f` on `fox`, and the user is in dictation mode.
**When** the user speaks the single utterance `change trap word force`.
**Then** the overlay dispatches `prose_overlay_change_hat("t")` followed by `prose_overlay_add_text("word force")` in one action-body block, the buffer becomes `word force fox` (with `word force` where `the` used to be), and nothing leaks to the host window — specifically, no `word` scope fires against the host and no `force` keypress lands in the focused window.

- **Status:** `[ ]` spec-only (behavior shipped; regression coverage missing).
- **Layer:** live-only today (Talon grammar matcher required); could be lifted to L3 with a stubbed-talon grammar simulator (see `docs/FEATURE_PARITY.md §0d` item 3).
- **Related:** `prose_overlay_dictation.talon:30-47`, `docs/GRAMMAR_STRUCTURE_PARITY.md §4c` (the "load-bearing intentional drift" section).

---

## Dictation / formatters

### S7 — symbol form concatenates with immediately-following NATO letters or symbols

**Given** the overlay is showing, the user is in dictation mode, and the buffer is either fresh or has a prior token.
**When** the user speaks one utterance containing a symbol form (e.g. `slash`) IMMEDIATELY followed by NATO letters (e.g. `bravo tango whiskey`) or another symbol form (`slash comma slash`).
**Then** the buffer receives the symbols and letters concatenated with NO whitespace between them: `slash bravo tango whiskey` → `/btw` (one token), `slash comma slash` → `/,/` (one token). The symbol acts like a char, and the following letters extend the same token, not a new one.

- **Status:** `[~]` likely shipped but no dedicated regression test for the symbol+NATO composition path. Related tests L1.11 / L1.12b cover word+chars extension but do NOT start with a `symbol_key`.
- **Layer:** L1 (buffer-side: `add_chars` extending the last token when its trailing char is non-word) + live-verify for the grammar routing.
- **Related:** `prose_overlay.talon:173` (`{user.symbol_key}: user.prose_overlay_add_chars(symbol_key)`), `prose_overlay.talon:197` (`<user.letters>: user.prose_overlay_add_chars(letters)`), `shim/actions_core.py` for the extend-last-token logic.

### S8 — symbol form followed by prose words → falls through as prose

**Given** the overlay is showing, the user is in dictation mode.
**When** the user speaks one utterance whose first word is spelled the same as a symbol form (e.g. `slash`) but whose subsequent words are regular prose (NOT NATO letters or symbol forms) — e.g. `slash the budget`.
**Then** the entire utterance is treated as PROSE: the buffer receives the literal string `slash the budget` (five characters, one token per space-separated word), NOT `/the budget`. The `raw_prose` capture wins over the `symbol_key` capture in this shape because the tail is prose-like, not symbol/NATO-like.

- **Status:** `[ ]` spec-only — user reported the current behavior as `slash the budget` → `/the budget`, which VIOLATES this spec. Bug filed by capture. Follow-up: reproduce with `scripts/test-overlay.sh` and confirm which rule wins today.
- **Layer:** grammar arbitration — Talon rule-specificity between `{user.symbol_key}` (matches `slash` alone) and `<user.raw_prose>` (matches the whole utterance). Fix likely requires a compound rule shape like `<user.raw_prose>` outranking single-word `symbol_key` when the raw_prose contains multiple words, or a Python-side heuristic on `add_chars` that refuses to fire when the utterance had prose-shaped context.
- **Related:** `prose_overlay_dictation.talon:10` (raw_prose route), `prose_overlay.talon:173` (symbol_key route). Adjacent to `docs/GRAMMAR_STRUCTURE_PARITY.md §4c` (arbitration is load-bearing).
- **Coupled to S7:** these two scenarios together define the symbol-form arbitration rule. Any implementation must satisfy BOTH — `slash bravo` → `/b` (S7), `slash the budget` → literal prose (S8). Distinguishing signal: the character class of the words AFTER the symbol.

---

### S3 — auto sentence-case after a "." token

**Given** the overlay is active, the buffer's last token is `.` (a period, produced by the community formatter or a `{user.symbol_key}` insertion), and the user is in dictation mode.
**When** the user speaks the next utterance (e.g. `the quick brown fox`).
**Then** the incoming text is treated as sentence-case: the first character is capitalized (`The quick brown fox`), the rest is left as the user spoke it, and it's appended to the buffer as normal.

- **Status:** `[ ]` spec-only
- **Layer:** L1 (buffer-level: post-`.`-detection + capitalize-first-word helper) + live-verify for the end-to-end path through `insert_formatted` / `add_text`.
- **Related:** existing `sentence` formatter in `prose_overlay_formatter` (community formatter chain), `prose_overlay.talon:179` (`{user.prose_formatter} <user.prose>`), `internal/state.py` (buffer inspection for the last token). Adjacent to §1 of `docs/FEATURE_PARITY.md` "raw prose → tokens" plus a new "auto sentence-case" row that isn't there yet.
- **Notes:** should also fire after `?` and `!` (open question). What about `.` followed by whitespace-only trailing? Whitespace-only tail should probably still trigger. What about a `.` embedded inside a longer token like `e.g.` — that's a false positive we want to skip (heuristic: only trigger when `.` is its OWN token in the buffer, not embedded).

---

## Help panel / UI

### S4 — help panel prefers ONE full rule over multiple truncated rules

**Given** the help panel is showing (e.g. via `overlay help`) and the available horizontal width can fit ONE full rule text OR N truncated rule texts (where the N truncated versions each end in `…` because the rule doesn't fit).
**When** the panel renders.
**Then** the panel shows ONE full rule at its natural width, not N truncated rules. If the pager has more rules than fit in the current row height budget, use `help next` / `help back` pagination to reach them — never truncate to fit-more-in-one-view.

- **Status:** `[ ]` spec-only — CURRENTLY VIOLATED. Screenshot on 2026-07-01 shows five truncated rules (`"overlay an…" full-screen…`, `"move <hat>…" move word t…`, `"pre file" cursor to st…`, `"overlay to…" attach pane…`, `"overlay an…" scope panel …`) instead of fewer full rules with pagination for the rest.
- **Layer:** L1 (help layout math — layout function that decides row count and per-row width) + live-verify (Skia paint at real width). Layout math is in `ui/help.py` or `internal/panel_layout.py` (verify which). No headless test exists for help-panel truncation today.
- **Related:** `ui/help.py`, `ui/actions_help.py`, help voice surface in `prose_overlay.talon:145-148` (`overlay help`, `help next`, `help back`, `help bigger`, `help smaller`).

### S5 — empty content area is a generalized help zone when idle

**Given** the overlay is showing, the buffer is empty (`len(tokens) == 0`), and the buffer has been idle for some threshold (open: 2 seconds? 5 seconds? None — just render immediately on empty?).
**When** the render pass fires.
**Then** the content area (where tokens would normally paint) is used as a generalized help zone: rotating help hints, recent commands, or a contextual "what can I say" surface. Not a modal overlay — an ambient use of otherwise-blank canvas. The zone yields immediately when the buffer transitions from empty → non-empty (first token added).

- **Status:** `[ ]` spec-only
- **Layer:** L1 (empty-buffer detection + zone content selection) + live-verify (Skia paint of the zone, transition-out on first token).
- **Related:** `ui/draw.py`, `ui/help.py`, `internal/state.py` (buffer empty check). Ties into S4 — the same help-content source can populate both the pager and the ambient zone. Open question: does this coexist with the "listening..." placeholder currently rendered on empty (see `POTENTIALLY_MISSED.md §F` "Empty buffer placeholder text customization"), or replace it?

---

## History

### S6 — history select loads content into editable buffer

**Given** the overlay is showing, the history panel is open (via `prose history`), and the panel lists at least one prior confirmed phrase.
**When** the user selects a history item (today's shipping surface: `history pick <N>` where N is the entry number).
**Then** the selected entry's text becomes the buffer content, the buffer is ready to edit (cursor placement + hats reallocated + editing verbs like `chuck`, `pre`, `change` operate on the loaded content), and the history panel dismisses so the user is looking at the buffer. Explicitly NOT `history pick <N> {ender}` behavior — that path pastes directly to the target window and skips the editing step. Selection-for-edit is the default; selection-and-paste is the ender-modified variant.

- **Status:** `[~]` shipped path exists (`history pick <N>` → `prose_overlay_history_pick(number_small)` in `prose_overlay_history.talon:9`, dispatches to action in `ui/actions_history.py`), but no regression test exists for the edit-ready postcondition (hats reallocated, cursor positioned, panel dismissed). Scenario captures the invariant so a test can be written.
- **Layer:** L1 (buffer state + hat reallocation after history load) + L3 (action-dispatch test via test-driver) + live-verify for the pane-dismiss visual.
- **Related:** `prose_overlay_history.talon:9`, `ui/actions_history.py`, `internal/history_persist.py`, README §History panel. Adjacent to `FEATURE_PARITY.md §6` (history row is `[x]` shipped) and `POTENTIALLY_MISSED.md §G` (pin/search/preview affordances not shipped).

---

## Hat allocation

### S9 — hats reallocate on selection/cursor change in the same draw frame

**Given** the buffer contains multiple tokens where one token holds a colored hat because stability inertia kept the default variant on a farther token (e.g. `hey` has `blue-h` because `this` still holds `gray-h`), and the user speaks a hat-targeted verb that moves selection/cursor onto or adjacent to the colored-hat token (e.g. `take blue air`).
**When** the selection updates in response, the target's flash paints, and the buffer state advances by one revision (or by cursor-only change).
**Then** `_recompute_hats` runs in the SAME draw frame as the selection paint — the new near-cursor rank triggers the greedy allocator, the previously-colored near-cursor token grabs a default gray hat (possibly on a different letter), and the just-painted selection sits on top of the already-updated hat map. The user should NEVER see a stale colored hat on the newly-selected token even for one frame.

- **Status:** `[ ]` spec-only. Depends on the `stability="greedy"` allocator fix landed in `74ecf0a` (2026-07-01) but ALSO on the recompute-trigger firing on cursor-only changes, not just buffer mutations. Current trigger sites are `_recompute_hats` after `add_text`/`delete_token`/`commit_end` — a `take` action that only updates cursor/selection may skip recompute, leaving the hat map stale until the next mutation.
- **Layer:** L3 (dispatch — verify `take` / `pre` / `post` actions call `_recompute_hats` in the same tick) + live-verify for single-frame visual consistency.
- **Related:** `shim/actions_core.py:_recompute_hats` (trigger point), `ui/actions_cursor.py` and `shim/actions_cursorless.py` (`take` / `pre` / `post` / `cursor` action call sites), `internal/state.py` (cursor + selection state), `internal/debug.py` (the `draw`-trigger diff snapshot that would show a stale-then-updated hat map if recompute lags). Also depends on `docs/CURSORLESS_NEAR_CURSOR_BIAS.md` findings — greedy stability is what makes the reshuffle possible at all.
- **Test hooks:** the always-on `~/.talon/prose_overlay_debug.jsonl` records `hats` on every recompute; a probe would (1) speak `take blue air`, (2) `jq -c 'select(.trigger=="recompute_hats")' | tail -1` and confirm the diff includes `air` → `gray-*`, (3) confirm the immediately-following `draw` diff shows both selection AND updated hats (no intermediate frame with the stale allocation).

---

## Bundle contents / handlers

<!-- Bundle-side scenarios (once BUNDLE_SHAPE_SCOPE.md and BUNDLE_REST_SCOPE.md land) go here. -->

---

## Observability / debug

<!-- Debug JSONL, faulthandler, test-driver dispatch scenarios go here. -->

---

## Deprecated / superseded

<!-- Tombstones for dropped scenarios. Format: `S<N> — [SUPERSEDED by S<M> because ...]` -->

## Maintenance rule

- When a scenario lands as a test, flip `[ ]` → `[x]` in the same commit that adds the test. Include the test ID (e.g. `L5.20`, `MV row 21`) in the Status line.
- When a scenario gets refined (buffer content changes, expected outcome shifts), edit in place — ID stays stable.
- When a scenario is dropped, move it to Deprecated with a superseded-by pointer. Never delete the number.
- Update the maintenance rule in `docs/FEATURE_PARITY.md` §0d if a scenario surfaces a new coverage-gap category.
