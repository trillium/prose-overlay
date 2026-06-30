# Homophone Shape-Coded Swap — Exploration Plan

> Source research: [`HOMOPHONE_UI.md`](./HOMOPHONE_UI.md) §2.C. Substrate scouting: [`HOMOPHONE_SHAPES_LOCATION.md`](./HOMOPHONE_SHAPES_LOCATION.md). Coordinates with [`HOMOPHONE_UI_PLAN.md`](./HOMOPHONE_UI_PLAN.md) (**which this plan supersedes Slice B of**) and [`UNDO_REDO_PLAN.md`](./UNDO_REDO_PLAN.md) Phase 2 (shipped, ISC-23).
> Drafted 2026-06-30.
>
> **This is an exploration plan, not a ship plan.** Each slice is a reversible experiment behind its own setting with explicit kill criteria. We are testing a *stronger* version of research §2.C than the doc proposed: instead of reserving one shape (`frame`) for homophones, we reserve the **entire 10-shape vocabulary** as a homophone-only addressing pool, with a per-token connected panel showing group alternates and a color-coded staged-then-commit selection loop. The shape becomes the visual flag, the panel becomes the answer set, color becomes the staged choice.

## 1. TL;DR

- The research doc's §2.C ("reserve one hat shape for homophones") is the *weak* version. **The user's actual design uses the whole shape pool** — 10 named shapes (`bolt curve fox frame play wing hole ex cross eye`) become exclusively addresses for flagged homophones; the default `dot` stays as the normal hat for everything else. This supports up to 10 simultaneous homophones on screen, each with a unique shape identity.
- **This plan supersedes Slice B (`phone <hat>` cycle on letter-hats) from [`HOMOPHONE_UI_PLAN.md`](./HOMOPHONE_UI_PLAN.md).** Letter-hats stay the universal addressing alphabet for `chuck` / `take` / `pre` / `post` / `change` / `phones`-plural. Shape-hats become the *parallel, homophone-only* addressing space for `phone`-singular and the panel UI.
- **Slice 1: lift the shape renderer** (read-only). Paint one of the 10 shape hats above each flagged token instead of (or above) the existing amber underline. No allocator wiring, no panel, no swap. Learning goal: do shapes-above-tokens read as a *cleaner* flag than the existing underline? (Cheap to roll back; the underline is one if-branch.)
- **Slice 2: deterministic shape allocator.** Replace the round-robin of Slice 1 with a debounced shape-per-flag assignment that's stable across edits within a doc. Mirrors the existing letter-hat allocator's lifecycle. Learning goal: does shape identity remain stable enough under realistic edit traffic to build muscle memory?
- **Slice 3: per-token connected panel** showing the group alternates below each shape-hatted token. No color yet. Learning goal: does seeing the alternates change *which* homophones the user fixes (not just *whether*)?
- **Slice 4: color-coded selection state + `phone <shape>` commit + advance verb.** Each alternate in a panel has a background color; one color marks the staged choice. `phone <shape>` commits the staged alternate as one STRUCTURAL undo step. Some verb (TBD — `cycle <shape>` / `next <shape>` / `phone <shape> <color>`) advances the stage. Learning goal: is staged-then-commit more accurate than implicit cycle?
- **Slice 5 (optional / deferred):** Confidence model from `HOMOPHONE_UI.md` §3 (trigram lookup) feeding the staged-color default — i.e., the model's best guess starts already staged so a confident swap is one utterance.
- Each slice ships behind its own setting, one commit, one `git revert` to undo. Nothing in Slice 1 locks API for 2-5. The 10-shape pool (shared substrate of Slices 2-5) ships with Slice 2; the only earlier coupling is "paint a shape" which falls back to the underline if the pool is empty.
- Foundational dodges in §4: keep the shape SVGs vendored in this repo with attribution (mouse-clock has no LICENSE — see §4.7), keep the shape allocator on `instance.shape_assignments` parallel to `instance.hat_assignments` (don't co-mingle), keep the panel on its own draw pass, and reserve the `phone` singular verb load-bearingly (the existing `phones` plural is already taken — see §4.3).

## 2. Decision-tree shape

```
1 — lift the shape renderer (paint 1 of 10 shapes above flagged tokens)
    (read-only assignment, no panel, no swap, fallback to underline on overflow)
  └─ Shape reads cleaner than the amber underline → 2
  └─ Shape feels noisier / harder to scan than underline → stop. The visual primitive
                                                            is wrong; demote shapes to
                                                            "only when panel is open"
                                                            and keep the underline as
                                                            the always-on signal.

2 — deterministic per-flag shape allocator (stable identity across edits)
    (10-shape pool, debounced like the letter-hat allocator; spills to underline
     when there are >10 flagged tokens on screen)
  └─ Shape identity stays stable under typical edit traffic → 3
  └─ Shape thrash makes muscle memory impossible → stop. Either accept "the shape
                                                    is ephemeral, only relevant when
                                                    you look at the panel" (still
                                                    fine for the voice loop) and skip
                                                    the stability work; or revert.

3 — per-token panel showing the group's alternates (no color yet)
    (panel anchored to the token; renders members joined like "[they're | there]")
  └─ Seeing alternates changes which homophones get fixed → 4
  └─ Panel is in the way / panels-on-every-line overwhelms → revert; keep 1+2 with no
                                                              panel and rely on the
                                                              shape alone for the swap
                                                              ("phone wing" cycles).

4 — color-coded selection + phone <shape> commit + advance-stage verb
    (one alternate in each panel has a tinted background = staged; commit promotes
     it, advance verb moves the stage)
  └─ Two-step (stage + commit) lands the right word more often than implicit cycle
                                                               → consider 5
  └─ Two-step adds friction; one-step cycle would have been faster → revert color +
                                                                     advance; keep
                                                                     phone <shape>
                                                                     as a one-step
                                                                     cycle.

5 — confidence-defaulted staged alternate (trigram model from research §3)
    (the LM's best guess starts staged; confident swaps are one utterance)
  └─ Staged-default matches user intent ≥60% of the time → keep
  └─ Staged-default is wrong often enough to confuse → revert; staged alt defaults
                                                       to "first non-current member
                                                       of the group" (deterministic).
```

Each slice lives behind its own setting (§3 per-slice spec). Reverting 4 does not touch 3. Reverting 3 does not touch 2. The 10-shape pool is the shared substrate of 2-5; the lift of `_get_shape_path_cache` + the shape SVG assets is the shared substrate of 1-5 and lands with Slice 1.

## 3. Per-slice spec

### Slice 1 — lift the shape renderer

**Goal.** Learn whether painting a Cursorless-style shape (one of the 10 named SVGs from mouse-clock) above each flagged token reads as a *cleaner, more visually distinct* flag than the existing amber underline at `prose_overlay_draw_tokens.py:177`. The lift is otherwise pure infra — once it works, Slices 2-5 are about *using* the rendered shape, not building it.

**Files touched** (rough LOC):
- **new** `svg/` directory with the 11 SVGs (`bolt.svg curve.svg crosshairs.svg default.svg ex.svg eye.svg fox.svg frame.svg hole.svg play.svg wing.svg`) **vendored** from `~/.talon/user/trillium/mouse-clock/src/svg/`. ~11 small text files, ~50 bytes each. **See §4.7** for the licensing/attribution dodge.
- **new** `prose_overlay_shapes.py` (~80 LOC) — the lifted renderer. Adapts `~/.talon/user/trillium/mouse-clock/src/rendering/svg_loader.py` and `~/.talon/user/trillium/mouse-clock/src/features/clock_letters/shapes.py:_get_shape_path_cache` per the recipe in `HOMOPHONE_SHAPES_LOCATION.md` §6. Public surface:
  ```python
  HAT_SHAPES: tuple[str, ...] = ("bolt", "curve", "fox", "frame", "play", "wing", "hole", "ex", "cross", "eye")  # 10 named, dot excluded
  def draw_hat_shape(c, shape_name: str, color: str, cx: float, cy: float, scale: float = 0.75, alpha: int = 255) -> None: ...
  def shape_pool() -> tuple[str, ...]: return HAT_SHAPES
  ```
  Internal: `_paths: dict[str, Path]` cached at module import via `Path.from_svg(d)`. Two-pass FILL+STROKE compositing per `HOMOPHONE_SHAPES_LOCATION.md` §6.
- `prose_overlay_draw_tokens.py` (~+15 LOC) — inside `_draw_token_rows` at the point where the existing hat dot is drawn (lines 133-152), check if the token is flagged and Slice 1 is on. If yes, paint a shape above the dot's `(cx, cy)` instead of (or above) the dot. Slice 1's allocation strategy is **round-robin by flagged-index order** (`shape_pool()[flagged_rank % 10]`); replaced in Slice 2.
- `prose_overlay_draw.py` (~+6 LOC) — pass the new shape-assignment dict down to `_draw_token_rows`.
- `prose_overlay.py` (~+6 LOC) — `mod.setting("prose_overlay_homophone_shapes", type=bool, default=False, ...)`.
- `prose_overlay_draw_constants.py` (~+2 LOC) — `HOMOPHONE_SHAPE_SCALE = 0.75`, `HOMOPHONE_SHAPE_DEFAULT_COLOR = "gray"`.

Total: ~110 LOC + 11 vendored SVG assets across 5 files + new `svg/` dir + 1 new module.

**Feature flag.** `user.prose_overlay_homophone_shapes` (bool, default `False`). Off → Slice A underline behavior unchanged (current shipped state). On → flagged tokens get a shape hat instead of (or in addition to — see §5 deprecation question) the underline. Runtime toggle action `prose_overlay_set_homophone_shapes(enabled: int)` mirrors `prose_overlay_set_homophone_hint` at `prose_overlay_actions_visibility.py:161`.

**Voice surface (Slice 1 only).**
```talon
overlay shapes homo on:  user.prose_overlay_set_homophone_shapes(1)
overlay shapes homo off: user.prose_overlay_set_homophone_shapes(0)
```
Two literal toggles. No `phone` grammar yet — that lands in Slice 4. Slice 1 is read-only by design.

**Keep criterion.** After ~3 sessions with shapes on, user reports the shapes are *easier to scan as a flag* than the underline — i.e., "I notice the homophone faster with the shape" — and shape-above-token doesn't visually collide with the existing letter-hat dot below (which it sits above; the dot stays). No regression in flow-layout readability.

**Kill criterion.** User reports "the shapes are noisier than the underline" within first session, OR shape-above-token visually crowds the existing letter-hat dot at standard DPI such that one or both becomes hard to read. In either case revert and stop: the visual primitive is wrong; the underline survives as the always-on flag.

**Reversibility.** `git revert <slice-1-sha>` removes one new module, one new dir of SVGs, one setting, ~20 LOC of draw additions. Zero schema change. Zero coupling to allocator, undo, or panel. The 10-shape pool is constant data; nothing reads it yet outside the draw pass.

**Non-goals.**
- No allocator wiring (round-robin only; Slice 2's job).
- No panel.
- No swap action / no `phone` grammar.
- No interaction with `instance.hat_assignments` (the letter-hat allocator remains untouched; both render layers coexist).
- No deprecation of the underline yet — both render in Slice 1 *if* the setting is on; pick one or the other in Slice 2 once we know which reads better.
- No spill / overflow story — Slice 1's round-robin reuses shapes when >10 flagged; Slice 2's allocator handles real overflow.

---

### Slice 2 — deterministic per-flag shape allocator

**Goal.** Learn whether shape identity stays stable enough across realistic edit traffic that the user can build muscle memory ("the `wing` is always *they're* in this draft, the `frame` is always *there*"). If shapes thrash on every dictation insert, the shape becomes an ephemeral lookup — still fine for `phone <shape>` in Slice 4, but kills the panel-color memory in Slices 3-4.

**Files touched** (rough LOC):
- `prose_overlay_shapes.py` (~+80 LOC) — add `compute_shape_assignments(tokens: list[str], flagged: set[int], rev: int) -> dict[int, str]` that returns `token_idx -> shape_name`. Stability strategy: first-pass keep prior assignments where the token at that index is still flagged and still maps to the same canonical group (re-lookup via the homophone module); second-pass assign new shapes to newly-flagged indices from the unused-shape pool; if pool empty, omit (caller falls back to underline). Mirrors the letter-hat allocator's stability semantics from `prose_overlay_actions_core.py` and `js/prose_allocate_hats.js`. Memoization keyed on `(rev, frozenset(flagged_indices))`.
- `prose_overlay_actions_core.py` (~+15 LOC) — extend `_recompute_hats` to also compute `instance.shape_assignments` when shapes setting is on. Bumped on the same triggers as `hat_assignments` (every mutation chain that goes through `instance.canvas.refresh()`). Debouncing rides on the existing redraw debounce; no new cron.
- `prose_overlay_instance.py` (~+1 LOC) — add `shape_assignments: dict[int, str] = {}` field on `ProseOverlayState`, cleared in `reset()`.
- `prose_overlay_draw_tokens.py` (~+5 LOC) — replace Slice 1's round-robin with `instance.shape_assignments.get(idx)`; fall back to underline if `None`.
- `prose_overlay.py` (~+0 LOC) — reuses Slice 1's setting; the allocator is wired iff that setting is on.

Total: ~100 LOC, no new module, one new field on `instance`.

**Feature flag.** Reuses `user.prose_overlay_homophone_shapes`. Slice 2 is the *implementation upgrade* of Slice 1's stub allocator — no new setting because the behavior visible to the user is "shapes appear more stable across edits." If we need an A/B during the experiment, gate with `user.prose_overlay_homophone_shapes_stable` (bool, default `True`) and let the user toggle back to round-robin.

**Voice surface (Slice 2 adds).** None. Allocator is implementation, not voice.

**Keep criterion.** Across ~3 sessions of normal dictation, the user reports that the shape for a given homophone token "stayed the same long enough to be addressable by shape" — i.e., the user can speak `phone wing` (Slice 4) and expect to land on the same token he saw a moment ago. Edits to *other* tokens do not visually thrash the shapes on unrelated flagged tokens.

**Kill criterion.** Shape assignments visibly re-shuffle after every word inserted, OR the memoization breaks (shapes re-paint on every keystroke) creating visual flicker, OR the user reports "I can't remember which shape is which by the time I look up to swap." Indicates either the allocator is wrong (fix) or the substrate is wrong — shape identity is too volatile to depend on, so Slice 4 should fall back to a single shape per panel and the addressing should be via panel ordinal not shape name.

**Reversibility.** `git revert <slice-2-sha>` returns to Slice 1's round-robin. Setting and SVG assets stay. Slice 3 still works (the panel doesn't depend on shape stability, only on flagged-token presence).

**Non-goals.**
- No persistence of shape assignments across overlay show/hide cycles. Cleared by `instance.reset()` and on every new buffer.
- No user-specified pinning ("`pin wing to they're` for this session"). That's a v2 affordance.
- No spill-to-letter-hat strategy for >10 flagged tokens. Spillover gets the underline only. Open question §6.4.

---

### Slice 3 — per-token connected panel

**Goal.** Learn whether seeing each flagged token's alternate set *in context, anchored to the token itself* changes which homophones the user fixes (not just whether). Hypothesis: a token with `wing` shape and a panel reading `[they're | there]` directly below it converts "I see a flag, don't know what's wrong" into "I see what I meant vs. what I typed."

**Files touched** (rough LOC):
- **new** `prose_overlay_draw_panels.py` (~120 LOC) — separate draw pass for the per-token panels. Public entry: `draw_homophone_panels(c, rows, x_origin, y_base, shape_assignments, tokens, anchor: str = "below")`. For each `(idx, shape)` in `shape_assignments`, look up the group via `prose_overlay_homophones.group_for_word(tokens[idx])`, render a faint background pill below the token containing `[alt1 | alt2 | ...]` joined by ` | `. Layout: panel y_top = token's `y_base + LINE_HEIGHT` (one line below the token). Panel width = sum of alt-text widths + separators + padding. Panels are independent rectangles — they do NOT share a row; overlapping panels for adjacent flagged tokens stack vertically with a 2-px gap. **Anchor variants** (open question §6.5): `"below"`, `"right"`, `"eol"`. Default `"below"`.
- `prose_overlay_homophones.py` (~+15 LOC) — add `group_for_word(token: str) -> tuple[str, ...] | None` that returns the full group (all members in CSV row order) for a flagged token, or `None` if unflagged. Sibling to `is_flagged`. Reads the CSV once at import (already happens in `_load()`); the only new state is the surface-word → group lookup table.
- `prose_overlay_draw.py` (~+8 LOC) — after `_draw_token_rows` (line ~177), if `settings.get("user.prose_overlay_homophone_panels")`, call `draw_homophone_panels(...)`.
- `prose_overlay.py` (~+6 LOC) — `mod.setting("prose_overlay_homophone_panels", type=bool, default=False, ...)`.
- `prose_overlay_draw_constants.py` (~+5 LOC) — panel-specific colors and metrics: `PANEL_HOMO_BG = "1a1a2acc"`, `PANEL_HOMO_TEXT = "ccccddee"`, `PANEL_HOMO_PAD = 4`, `PANEL_HOMO_FONT_SIZE = 11`, `PANEL_HOMO_RADIUS = 3`.

Total: ~155 LOC, one new module, no schema change.

**Feature flag.** `user.prose_overlay_homophone_panels` (bool, default `False`). Independent of `prose_overlay_homophone_shapes` (but the panel only makes sense if shapes are also on — when panels=on, shapes=off, the panel anchors to the underline-only flag and looks orphaned). The setting **registers** the draw pass unconditionally; the panel only renders if shapes are also on, with a debug-log line when this mismatch happens.

**Voice surface (Slice 3 adds).**
```talon
overlay panels homo on:  user.prose_overlay_set_homophone_panels(1)
overlay panels homo off: user.prose_overlay_set_homophone_panels(0)
```

**Keep criterion.** User reports across ~3 sessions that the panels surface alternates that he *would have missed* without the visible list — i.e., the panel changes the swap target, not just confirms it. Layout collisions (panels overflowing the panel rect, overlapping help zone, going under the cursor row) are rare enough to be fixable.

**Kill criterion.** "Too many panels, can't focus" — visual overload from N panels on screen. OR panels for adjacent flagged tokens collide so badly there's no reading order. OR the panel layout breaks the existing flow layout (`_flow_layout` in `prose_overlay_draw_tokens.py:45`) by pushing content out of the panel rect. Revert: shapes alone (Slice 1+2) still tell you a token is flagged; you just don't see the alternates inline.

**Reversibility.** `git revert <slice-3-sha>` removes one new module, one setting, ~13 LOC across `draw.py` and `homophones.py`, 5 new constants. Slices 1+2 unaffected.

**Non-goals.**
- No color (Slice 4's job).
- No interactivity / no addressing the panel by ordinal (Slice 4 adds shape-addressing only, no `panel <n>` grammar).
- No "ghost chip past EOL" variant from `HOMOPHONE_UI.md` §2.B — panels are anchored *below* each token by default, not appended to line-end. The chip variant is a Slice 3.5 if the panel-per-token anchor reads worse.
- No scroll-aware hiding — panels for tokens in the visible viewport draw; panels for tokens scrolled out simply don't render because their tokens aren't in `rows`.

---

### Slice 4 — color-coded selection + commit + advance verb

**Goal.** Learn whether a *staged-then-commit* two-step swap loop ("I see `wing` panel reading `[they're | there]` with `there` highlighted blue; I say `phone wing` and `there` lands") is more accurate than implicit cycle ("I say `phone wing` and *something* lands; I undo if wrong"). The hypothesis: the staged-color preview lets the user see-before-commit, which converts a coin-flip into a verified action.

**Files touched** (rough LOC):
- `prose_overlay_shapes.py` (~+30 LOC) — extend `compute_shape_assignments` to also return per-token *staged-alternate index*: `dict[int, tuple[str, int]]` = `token_idx -> (shape_name, staged_alt_idx)`. Default `staged_alt_idx` for a freshly-flagged token = the first alternate in the group that is NOT the current surface word (deterministic; not LM-based — Slice 5 makes it LM-based).
- `prose_overlay_draw_panels.py` (~+25 LOC) — render the staged alternate with a tinted background. Color choice deterministic per shape — pull from `HAT_COLOR_HEX` palette (re-use Cursorless colors so the user already knows them): `bolt→blue, curve→green, fox→red, frame→pink, play→yellow, wing→purple, hole→gray-2, ex→black, cross→white, eye→blue-2`. Open question §6.3: are there enough distinct colors? (Palette has 9 entries, 10 shapes; either repeat one or add the 10th from a new desaturated slot.)
- **new** `prose_overlay_actions_homophones.py` (~80 LOC) — three actions:
  - `prose_overlay_phone_shape(shape_name: str)` — looks up `instance.shape_assignments[idx_for_shape]`, reads the staged alt, brackets in `instance.buffer.commit_start(label=f"phone {shape_name}", kind=EditKind.STRUCTURAL)` / `commit_end()` (from `prose_overlay_state.py:303-338`, Phase 2 of UNDO_REDO_PLAN is shipped per ISC-23), calls `instance.buffer.replace_token(idx, new_word)`, refreshes canvas. One STRUCTURAL undo step per the undo plan §5 contract.
  - `prose_overlay_phone_advance(shape_name: str)` — rotates the staged-alt-index forward by one in the panel for that shape; pure draw-state change, no buffer mutation, no undo step.
  - `prose_overlay_set_homophone_swap(enabled: int)` — runtime toggle mirroring the existing visibility action pattern.
- `prose_overlay.talon` (~+8 LOC) — append:
  ```talon
  # Homophone shape-coded swap (slice 4 — docs/HOMOPHONE_SHAPES_PLAN.md)
  phone {user.hat_shape}: user.prose_overlay_phone_shape(hat_shape)
  cycle {user.hat_shape}: user.prose_overlay_phone_advance(hat_shape)
  overlay swap homo on:  user.prose_overlay_set_homophone_swap(1)
  overlay swap homo off: user.prose_overlay_set_homophone_swap(0)
  ```
  Uses the `{user.hat_shape}` Talon list declared by mouse-clock at `~/.talon/user/trillium/mouse-clock/src/clock_ring.py:19` (and supplied by `~/.talon/user/trillium/mouse-clock/src/hat_shape.talon-list`). **Dependency note**: this couples prose-overlay's voice grammar to mouse-clock being installed. See §4.6.
- `prose_overlay.py` (~+6 LOC) — `mod.setting("prose_overlay_homophone_swap", type=bool, default=False, ...)`. The `phone <user.hat_shape>` grammar registers unconditionally; the action body short-circuits with `app.notify` if the setting is off.

Total: ~155 LOC, one new module, no schema change.

**Feature flag.** `user.prose_overlay_homophone_swap` (bool, default `False`). Independent of Slices 1-3. Practically the user wants all four on; the flag exists so a kill verdict on Slice 4 reverts only the swap.

**Voice surface (Slice 4 adds).**
```talon
phone {user.hat_shape}
cycle {user.hat_shape}
overlay swap homo on
overlay swap homo off
```

The `cycle <shape>` advance verb is the **recommended** choice from §6.3 — short, distinct from `phone` (commit), doesn't collide with existing grammar (audit `rg '^cycle\s' ~/.talon`). Alternatives `next <shape>` / `phone <shape> <color>` discussed in §6.3.

**Keep criterion.** Across ~3 sessions, two-step swap accuracy beats implicit-cycle accuracy on the user's real dictation — i.e., the user lands the right word on first commit ≥75% of the time vs. Slice B's coin-flip baseline (~50% for 2-member groups). User reports the staged preview "tells me what's about to happen" in a way the underline never did.

**Kill criterion.** User reports the two-step loop feels *slower* than just dictating the right word, OR the advance verb (`cycle <shape>`) misfires often enough that one-utterance commit is impossible to achieve, OR the color-coded staging visually overwhelms the panel and reading order breaks. Revert color + advance; keep `phone <shape>` as a one-step cycle that just advances and commits in one verb.

**Reversibility.** `git revert <slice-4-sha>` removes one new module, one setting, ~10 LOC of talon grammar, ~55 LOC of panel/shape changes. Slices 1-3 unaffected — panels still render, just without color and without addressable commit.

**Non-goals.**
- No bulk swap (`phone every line`) — research §4 "Bulk operations" is a v2 affordance.
- No dismiss / ignore (`phones ignore wing` — research §4.Dismissal scope, v2).
- No `phone <shape> as <word>` named-target variant — Slice 4 leans on the staged-preview to disambiguate; named-targets are a fallback if the staged-preview turns out to be wrong often.
- No TTS confirmation loop (research §4 final paragraph, opt-in, deferred per `HOMOPHONE_UI.md` §6 OQ6).
- No animation on the swap (research §5c iOS-17 fade-on-change — nice but not load-bearing).

---

### Slice 5 — confidence-defaulted staged alternate

**Goal.** Learn whether a local trigram-confidence model (per `HOMOPHONE_UI.md` §3) can default the staged alternate to the LM's best guess such that a confident `phone <shape>` becomes a one-utterance correct swap. Tests the "always-on but model-guided" hypothesis. Only enters the tree if Slice 4 kept and the deterministic default ("first alt other than current") wins less than ~60% of the time.

**Files touched** (rough LOC):
- **new** `prose_overlay_homophone_model.py` (~120 LOC) — module owns the precomputed `(prev, current, next) -> log_prob` lookup table loaded lazily on first `confidence_score()` call. Exposes `best_alt(prev: str, current: str, next: str, group: tuple[str, ...]) -> str` and `confidence(prev: str, current: str, next: str, group: tuple[str, ...]) -> float`. Falls back to "first alt other than current" if the trigram context is OOV.
- **new** `data/homophone_trigrams.bin` (~5-20 MB after pruning) checked into repo if under 10 MB, otherwise built on first run (Open question §6 OQ3 from `HOMOPHONE_UI.md`).
- `prose_overlay_shapes.py` (~+15 LOC) — `compute_shape_assignments` calls `best_alt` instead of the deterministic default when the model setting is on.
- `prose_overlay_draw_panels.py` (~+0 LOC) — no draw change; same staged-color, just smarter default.

Total: ~135 LOC, one new module, one new data file, no API change to Slices 1-4.

**Feature flag.** `user.prose_overlay_homophone_confidence` (bool, default `False`). Off → deterministic default. On → LM-guided default.

**Voice surface.** None. Slice 5 only changes what alt is pre-staged in the panel.

**Keep criterion.** Staged-default matches user intent on ≥60% of homophone-swap utterances (measurable: count `phone <shape>` followed by `cycle <shape> phone <shape>` within 3 seconds = wrong default + retry; vs. clean `phone <shape>` = correct default). Model load doesn't push overlay startup past 100 ms.

**Kill criterion.** Model load adds noticeable cold-start lag, OR table is too coarse to outperform deterministic default, OR the staged-alt thrashes as the user edits surrounding tokens (every keystroke re-scores and re-stages, breaking visual stability). Revert to Slice 4's deterministic default.

**Reversibility.** `git revert <slice-5-sha>` removes one module, one data file, ~15 LOC in shapes.py. Slices 1-4 unaffected because they read `compute_shape_assignments` returns unchanged.

**Non-goals.**
- No neural LM. Same posture as `HOMOPHONE_UI_PLAN.md` Slice D.
- No GloVe cosine fallback in v1 of Slice 5.
- No per-doc adaptation. Table is precomputed and frozen.

## 4. Foundational risks to dodge

These are the choices that, if made wrong in Slice 1, would make 2-5 expensive to undo.

### 4.1 Shape allocator coupling — HIGH RISK

**Risk.** Trying to share `instance.hat_assignments` for both letter-hats and shape-hats. Today `hat_assignments: dict[int, tuple[int, str, str]]` = `token_idx -> (char_idx, letter, color)` (one mark per token). Adding "and sometimes a shape" overloads the dict and forces every reader (`prose_overlay_draw_tokens.py` line 133, `_hat_to_index` at `prose_overlay_actions_core.py:60`, the JS allocator in `js/prose_allocate_hats.js`) to grow a branch.

**Dodge.** **Shape state lives in its own field**: `instance.shape_assignments: dict[int, str]` (Slice 2) or `dict[int, tuple[str, int]]` (Slice 4 with staged-alt-index). Co-located on `ProseOverlayState` but never merged into `hat_assignments`. The two allocators run independently; the letter-hat allocator is unchanged; shape allocator runs only when `prose_overlay_homophone_shapes` is on and reads from `prose_overlay_homophones.flagged_indices(tokens)`. Render layer is the integration point — both fields are read in the same draw pass.

This also means: letter-hats remain the universal addressing space (`chuck wing` still deletes the letter `w` token, regardless of homophone state). Shape-hats are a *parallel*, opt-in addressing pool used only by `phone <shape>` in Slice 4. No collision.

### 4.2 Render-layer coupling — MEDIUM RISK

**Risk.** Painting the shape inside `_draw_token_rows` per-token tightly couples the inner loop to homophone awareness. Adding panels (Slice 3) in the same loop further bloats it. Adding color staging (Slice 4) means the inner loop reads a third field. By Slice 5 the function is unrecognizable.

**Dodge.**
- **Slice 1's shape draw lives in the inner loop** (alongside the existing letter-hat dot) because both are per-token, both render above the token, both are trivial — one optional shape paint added to the existing `if has_hat` block.
- **Slice 3's panel draw lives in its own pass**: `draw_homophone_panels` in `prose_overlay_draw_panels.py`, called from `draw_overlay` *after* `_draw_token_rows`. Mirrors the existing pattern of `draw_help_panel` / `draw_history_panel`. Panels read row geometry from the `rows` parameter (already passed to `_draw_token_rows`) so they can anchor to token positions, but they don't share a render call.
- **Slice 4's staged-color** is a panel-internal concern — the panel rendering knows which alt is staged and tints its background. The inner loop is untouched.
- **Slice 5** doesn't touch render at all; it only changes what `compute_shape_assignments` returns.

This mirrors `HOMOPHONE_UI_PLAN.md` §4.3.

### 4.3 Voice grammar choice (`phone` vs `phones` vs anything else) — MEDIUM RISK

**Risk.** The user already speaks `phones <word>` to the existing modal HUD at `~/.talon/user/trillium_talon/core/homophones/homophones.talon:1-15` (six rules: `phones <homophones_canonical>`, `phones that`, `phones force`, `phones hide`, etc.). Cursorless also binds `phones` as `nextHomophone` in `~/.talon/user/trillium_talon/cursorless-settings/actions.csv:31` and `~/.talon/user/cursorless-settings/actions.csv:31`. Plus `~/.talon/user/talon-gaze-ocr/gaze_ocr.talon:106` binds `phones [word] (seen | scene) <user.timestamped_prose>$`. **All of these are plural `phones`**. Audit via `rg '^phone\b' ~/.talon` (excluding `.sys/blob/*`) returns zero user-space rules on singular `phone`. So the singular is free.

**Dodge.** **Reserve singular `phone` for per-shape commit (Slice 4)** and never touch the plural `phones` namespace. The existing modal HUD stays as the user's known-good fallback. The new grammar `phone {user.hat_shape}` reads as "swap the homophone token wearing the named hat shape" — distinct verb, distinct capture (shape list, not letter capture, not hat color), no collision possible.

`{user.hat_shape}` is the mouse-clock-declared list at `~/.talon/user/trillium/mouse-clock/src/clock_ring.py:19`. Its members (`bolt curve fox frame play wing hole ex cross eye dot`) do not collide with `<user.letter>` (letters), `<user.prose_hat_color>` (color names), or any prose-overlay verb. **Verified.**

**Backup verb if mouse-clock isn't installed**: `phone {user.prose_hat_shape}` where `prose_hat_shape` is a list declared in *this* repo (`prose_overlay.py` adds `mod.list("prose_hat_shape", ...)` with the 10 shape names). Independent from mouse-clock's list — same vocabulary, isolated namespace. See §4.6.

### 4.4 Color-as-selection vs color-as-confidence — MEDIUM RISK

**Risk.** The companion plan `HOMOPHONE_UI_PLAN.md` Slice D wanted to use *color/opacity* as the confidence channel ("low confidence = solid amber, high confidence = barely visible amber"). This plan repurposes color as the *selection* channel ("the staged alternate has a colored background"). If both planned uses ship, color is overloaded and the user can't tell whether a blue panel means "staged alternate" or "high LM confidence."

**Dodge.** **Color belongs to selection in this plan.** Confidence modulates `shape opacity` (Slice 5 implementation note: scale the shape's stroke/fill alpha by `min(1.0, max(0.3, 1.0 - confidence(current_word)))`, never the panel color). The amber underline from `HOMOPHONE_UI_PLAN.md` Slice A stays available as a fallback layer (when shapes exhaust the pool — §5) but always paints at fixed alpha; it has no confidence channel. The two color channels are: (a) per-shape **identity color** (deterministic, matches Cursorless hat color palette, identifies which shape this is); (b) per-alternate **staging color** inside the panel (a single tint applied to the staged member's background, same tint used across all panels — high salience for one selection per panel).

Document this on Slice 4's commit and in `prose_overlay_draw_panels.py` docstring.

### 4.5 Panel layout — anchor, stacking, scroll — MEDIUM RISK

**Risk.** Per-token panels can collide. 10 panels stacked vertically blow the panel's height budget. Tokens at end-of-row need panels that don't run off the right edge. Tokens at the bottom of the visible content have panels that fall off the panel rect.

**Dodge.** **Slice 3 anchor strategy** (default `"below"`):
- Each panel anchors directly below its token's render position: `panel_y = token_y_base + LINE_HEIGHT` (one full LINE_HEIGHT below).
- Panel x = `token_x` (left-aligned to the token); if `panel_x + panel_w > panel_right_edge`, right-align instead (`panel_x = panel_right_edge - panel_w`).
- Adjacent flagged tokens on the same row whose panels would overlap: stagger vertically by a second LINE_HEIGHT. Effective max-stack = `panel_h // LINE_HEIGHT - 2` panels per row before overflow. With `PANEL_H_FRACTION = 0.10` (currently 10% of screen height) and `LINE_HEIGHT = 27px`, that's about 2-3 visible panel rows on a 1080p display — enough for the typical "one or two homophones per line of dictation" case.
- Tokens whose panels would land off the panel rect bottom: panel doesn't render. Open question §6.4 covers the "more than visible-panel-slots flagged tokens" case.

**Slice 3 ships `anchor="below"` only.** `"right"` and `"eol"` variants are research-doc options reserved for a v2 if `"below"` doesn't read.

### 4.6 The lift from mouse-clock — copy vs import — HIGH RISK

**Risk.** Importing from `~/.talon/user/trillium/mouse-clock/src/...` couples prose-overlay to mouse-clock being installed on the user's machine. Talon imports across user-plugin boundaries are technically possible but fragile (the import path becomes `user.trillium.mouse_clock.src.rendering.svg_loader`, depends on mouse-clock's package structure, breaks if mouse-clock is renamed or removed). Copying the assets and code makes prose-overlay self-contained but creates a drift point.

**Dodge.** **Copy, don't import.** Vendor the 11 SVG files into `prose-overlay/svg/` (Slice 1). Lift `_get_shape_path_cache` (the 12-line FILL+STROKE compositing pattern from `~/.talon/user/trillium/mouse-clock/src/features/clock_letters/shapes.py:114-126`) into `prose_overlay_shapes.py` directly. Lift `_parse_svg_entries` from `~/.talon/user/trillium/mouse-clock/src/rendering/svg_loader.py:20-40` similarly, adapted to read from prose-overlay's own `svg/` dir. **All adaptation per `HOMOPHONE_SHAPES_LOCATION.md` §5 ("Adaptation notes for prose-overlay's flow layout") and §6 (the reproduction recipe).**

Also: **declare prose-overlay's own `mod.list("prose_hat_shape", ...)`** in `prose_overlay.py` rather than relying on mouse-clock's `{user.hat_shape}`. This is a small duplication (the same 10 string entries) for full namespace isolation. Confirm before Slice 4 — see §6 OQ2.

### 4.7 SVG asset licensing — RESOLVED 2026-06-30

**Risk (closed).** `~/.talon/user/trillium/mouse-clock/README.md` already declared MIT but the LICENSE file was missing.

**Resolution.**
1. **MIT LICENSE added** to `~/.talon/user/trillium/mouse-clock/LICENSE` (Copyright 2026 Trillium Smith) — matches the README's declared intent.
2. Slice 1 vendoring will **copy the 11 SVGs into `prose-overlay/svg/`** and drop a one-line `prose-overlay/svg/NOTICE.md`: "Shape SVGs adapted from sibling project trillium/mouse-clock (MIT, same author). Shape-name vocabulary (bolt, frame, eye, ...) follows Cursorless's hat-shape conventions for voice compatibility."
3. **No upstream Cursorless attribution required** for the SVG path data — the mouse-clock assets are independently authored. The shape-name vocabulary is a naming convention shared with Cursorless for voice-grammar compatibility, not a copyrightable lift.

### 4.8 Existing underline coexistence (HOMOPHONE_UI_PLAN.md Slice A) — DECIDE IN SLICE 1

**Risk.** Slice A's amber underline (`HOMOPHONE_UNDERLINE_COLOR = "ffb74dee"`, drawn at `prose_overlay_draw_tokens.py:177-181`) is currently the always-on signal, default ON per the user's keep verdict on 2026-06-30 (ISC-11). Shapes painted above the token are a *different* signal channel. Painting both on every flagged token is visually loud and conceptually redundant ("you've already told me with the shape that this is a homophone; the underline says it again").

**Dodge.** **The shape IS the visual flag once Slice 1+2 land**. Underline gets demoted to a **fallback layer**: paint the underline only when the token is flagged but has no shape assignment (the >10-flagged-tokens overflow case from §6.4). Concretely, in `_draw_token_rows`: `if idx in flagged_indices and instance.shape_assignments.get(idx) is None: paint underline`. This makes the underline the "spillover indicator" and the shape the "primary indicator." Implements §5's "demote, do not remove" answer to the existing-Slice-A coexistence question.

**Open question §6.5 covers** "should we be more aggressive and remove the underline entirely once shapes ship?" — the spillover dodge is the conservative answer; the aggressive answer is "remove; if shape pool overflows, the overflow tokens are just regular tokens with no flag indicator at all, and we live with that until a v2 spillover strategy ships."

## 5. Integration touchpoints with in-flight work

### Existing Slice A underline — `prose_overlay_draw_tokens.py:177`, `prose_overlay_draw_constants.py:37`

- Slice 1 + 2 ship with the underline still default-on (via the existing `user.prose_overlay_homophone_hint` setting from `prose_overlay.py:73-83`). Underline and shape both render when both settings are on; the user is the judge of which to keep visible.
- Slice 2's allocator returns `dict[int, str]` of shape assignments. The underline draw check becomes: `if idx in flagged_indices and idx not in shape_assignments: paint underline` — i.e., underline becomes the **spillover indicator** for >10 flagged tokens, per §4.8.
- **Decision point in Slice 2**: do we make this spillover-only behavior the *default* (the new code path) or keep "both render unconditionally" as a setting (`prose_overlay_homophone_underline_when_shape: bool, default=False`)? Recommended: spillover-only as the default once shapes are on; let the user toggle back if shapes alone don't read.
- ISC update: ISC-11 stays green (the underline still works). ISC-13 from `HOMOPHONE_UI_PLAN.md` is **superseded** by ISC-14a-d below.

### Undo/redo (`docs/UNDO_REDO_PLAN.md`, ISC-23 shipped)

- Phase 2 of the undo plan has landed (commits `ec52d32`, `7eb3e56`, `1a618a3`). The bracket API is live:
  ```python
  # From prose_overlay_state.py:303-338 (verified read).
  instance.buffer.commit_start(label="phone wing", kind=EditKind.STRUCTURAL)
  instance.buffer.replace_token(idx, new_word)
  instance.buffer.commit_end()
  ```
- Slice 4's `prose_overlay_phone_shape(shape_name)` action uses this bracket exactly. One utterance → one undo step (the `STRUCTURAL` invariant). The `label` becomes load-bearing if `overlay undo what` ever ships per UNDO_REDO_PLAN §7 Phase 3.
- `prose_overlay_phone_advance(shape_name)` does **not** mutate the buffer (only the panel's staged-index state), so it does not call `commit_start` / `commit_end`. It's a pure draw-state update — refresh canvas, no undo entry. **This is load-bearing**: the user can `cycle wing` repeatedly without polluting undo history, then `phone wing` once to commit a single undo step.
- Coalescing toggle (`overlay undo group on/off`) is irrelevant to shape-swap because `STRUCTURAL` records never coalesce (per the kind-discriminator in `ProseBuffer._record`).

### Buffer rev counter (`prose_overlay_state.py:117`, ISC-21 shipped)

- `buffer.rev` is the memoization key for the shape allocator in Slice 2 (`compute_shape_assignments(tokens, flagged, rev)` caches on `(rev, frozenset(flagged))`).
- `buffer.rev` is also the cache key for panel layout in Slice 3 (panels re-flow on every rev bump because token x/y positions can shift).
- This is the same use case `rev` was added for; no new state needed.

### Viewport — shape pool release on scroll-out

- Slices 1+2 paint shapes only for tokens that appear in `rows` after the viewport truncates them (`prose_overlay_draw.py:131-132`). A scrolled-out flagged token has no shape painted (good — saves shape pool slots for visible flagged tokens).
- **Slice 2 implication**: the shape allocator should consider "visible flagged tokens" only, not "all flagged tokens." This means as the user scrolls, shapes can re-assign — but only when the visible set changes, which is by definition a viewport event the user just triggered. Acceptable thrash; mention in Slice 2 docstring.
- No new viewport API needed. Read `instance.viewport._last_rows` if the allocator needs to know what's visible (set during `draw_overlay`).

### Existing modal `phones <word>` HUD — `~/.talon/user/trillium_talon/core/homophones/homophones.py`

- **Cite, do not modify.** Same posture as `HOMOPHONE_UI_PLAN.md` §5. This module is the user's known-good explicit-name fallback. Its grammar lives in `homophones.talon` (six `phones ...` rules), all plural.
- Document the coexistence in `prose_overlay_actions_homophones.py` docstring: "this module owns the *passive shape-coded* homophone surface — flag-by-shape and swap-by-shape. The active modal HUD at trillium_talon/core/homophones/homophones.py remains the explicit `phones <word>` fallback, untouched."
- The shape surface and the modal HUD address different muscle-memory paths: shape = "I see it on screen, I have a hat, I commit"; modal = "I know what I want, list me the options."

### ISA updates (`/Users/trilliumsmith/code/prose-overlay/ISA.md`)

Propose these ISC edits when the plan is approved:
- **ISC-13** (HOMOPHONE_UI_PLAN.md Slice B `phone <hat>` cycle on letter-hats): mark **superseded by ISC-14a-d** below. Strike-through, keep in the file for history.
- **ISC-14** (current single-line "Hat shape vocabulary integrated for shape-coded homophone swap"): expand into four sub-ISCs:
  - **ISC-14a**: Slice 1 — shape renderer lifted from mouse-clock, painted above flagged tokens behind `prose_overlay_homophone_shapes` setting.
  - **ISC-14b**: Slice 2 — deterministic 10-shape allocator with rev-keyed memoization on `instance.shape_assignments`.
  - **ISC-14c**: Slice 3 — per-token panels rendering group alternates behind `prose_overlay_homophone_panels` setting.
  - **ISC-14d**: Slice 4 — color-coded staging + `phone {user.prose_hat_shape}` commit + `cycle {user.prose_hat_shape}` advance behind `prose_overlay_homophone_swap` setting, one STRUCTURAL undo step per commit.
- ISC-14e (Slice 5 trigram confidence) is **optional** and ships only if 14a-d clear their keep criteria.

Update the Test Strategy table: ISC-14a-d entries point at this plan (`docs/HOMOPHONE_SHAPES_PLAN.md`) the same way ISC-13 used to point at `docs/HOMOPHONE_UI_PLAN.md`.

## 6. Open questions for Trillium

1. **Default-on or default-off for Slice 1?** Plan defaults `prose_overlay_homophone_shapes` to `False` so the experiment is opt-in. Counter-case (mirrors the existing Slice A keep verdict): default-on so the "shapes feel cleaner than underline" question is *actually tested*. Lean toward default-off for Slice 1 (the underline is the shipped baseline; don't ship past two competing always-on flags), flip to default-on after one session of "yeah leave it on" feedback. Worth a one-line confirm before merging Slice 1.

2. **SVG asset placement — vendor into `prose-overlay/svg/` or read from `~/.talon/user/trillium/mouse-clock/src/svg/` at startup?** Vendor (recommended): prose-overlay is self-contained, ships independent of mouse-clock, but creates a drift point if mouse-clock's SVGs change. Read-from-mouse-clock: single source of truth, but couples prose-overlay to mouse-clock being installed. Plan picks **vendor** per §4.6, conditional on §4.7 licensing being clean. Confirm before Slice 1 ships and assets are copied.

3. **Advance-selection grammar — `cycle <shape>` vs `next <shape>` vs `phone <shape> <color>` vs something else?**
   - **`cycle <shape>`** (recommended): short, action-verb, distinct from `phone` (commit). Cheap to add `cycle previous <shape>` and `cycle reset <shape>` later. Audit: `rg '^cycle\s' ~/.talon` returns no user-space rules. No collision.
   - **`next <shape>`**: read as "advance to the next member of this shape's group." But `next` is a heavy-traffic word in voice editors generally (Cursorless `next funk`, community `next word`), risk of mis-recognition or future collision.
   - **`phone <shape> <color>`**: directly addresses the staged alternate by its panel color (`phone wing blue` = "commit the blue-tinted alternative on the `wing` panel"). More explicit but four-word utterance, and depends on the user remembering panel colors. Higher cognitive load.
   - **`phone <shape> as <word>`**: explicit-name like research §4 — "commit the `wing`-flagged token to the literal word *they're*." Most precise, most verbose, never wrong. Could ship alongside `cycle` as the high-stakes backup.
   - **Recommendation: `cycle <shape>` as advance, `phone <shape>` as commit, with `phone <shape> as <word>` as a Slice 4.5 backup if `cycle` thrashes.** Confirm the verb choice before Slice 4 lands.

4. **Behavior when there are more than 10 flagged tokens on screen — silently truncate, paginate, fall back to underline for the overflow, or something else?**
   - **Fall back to underline** (recommended, default): the >10th flagged token reverts to the amber underline from Slice A. Underline-flagged tokens are not addressable by shape (no `phone` works on them) but are still visible. The user can scroll or fix some of the visible ones to free a shape slot. Mirrors how the letter-hat allocator handles overflow today (Cursorless's gray-default-fallback pattern from `proseStandalone.ts`).
   - **Paginate**: shapes only address tokens in the "page" the cursor is in; 10 nearest. More complex, requires a "page" concept that doesn't exist.
   - **Silently truncate**: 11th+ flagged tokens get neither shape nor underline. Bad — invisible failure.
   - Plan defaults to **fall back to underline**, which means §4.8 dodge is the implementation. Confirm.

5. **Keep the existing Slice A underline as a fallback layer (when shape pool exhausted) — or remove it entirely once shapes ship?**
   - **Keep as fallback** (recommended, §4.8 dodge): spillover-only when shape pool runs out. Conservative, doesn't regress the existing always-on signal.
   - **Remove entirely**: shape-or-nothing. Simpler mental model ("if it has a shape, it's flagged; if not, it's not"); but loses the spillover indicator and >10 flagged tokens become invisible.
   - **Configurable**: `user.prose_overlay_homophone_underline_when_shape: bool, default=True` lets the user pick. Adds a setting, but a 3-line change.
   - Recommendation: **keep as fallback, default-on**. Confirm before Slice 2 ships (the spillover logic lives in Slice 2's allocator, so the decision is needed by then).

---

*Plan ends. First commit (Slice 1) should be invisible at the voice layer (off by default), reversible in one revert, and decidable from one session of normal use with the setting flipped on.*
