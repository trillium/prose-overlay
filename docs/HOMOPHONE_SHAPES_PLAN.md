# Homophone Shapes — Exploration Plan

> Source research: [`HOMOPHONE_SHAPES_LOCATION.md`](./HOMOPHONE_SHAPES_LOCATION.md).
> Coordinates with [`HOMOPHONE_UI_PLAN.md`](./HOMOPHONE_UI_PLAN.md).
> Drafted 2026-06-30.
>
> **This is an exploration plan, not a ship plan.** Each slice is a reversible
> keep/kill experiment. We are looking for cheap evidence about whether
> Cursorless-style hat *shapes* (bolt, frame, eye, …) are the right visual
> primitive for distinguishing homophone members, before paying for an
> allocator-state refactor or a chip/HUD layer.

## 1. TL;DR

- We start with **Slice 1: paint a hat shape above any flagged token**, in a
  fixed round-robin over the shape pool. No allocator state, no panel, no swap
  action, no group membership — just "this token is in the homophone CSV, so
  show a shape on it."
- The learning goal is binary and cheap: **do hat shapes carry as well above
  prose tokens as they do over the mouse-clock cursor letters?** Same SVGs,
  same renderer, different context — readability is the open question.
- Slice 2 introduces `instance.shape_assignments` keyed by token index. Learns:
  does shape-stability across edits matter, or is round-robin fine?
- Slice 3 wires shape-per-homophone-group (so all members of `their/there/they're`
  paint the same shape). Learns: does same-group-same-shape help recall?
- Slice 4 adds `phone <shape>` swap grammar. Learns: is voice-addressing by
  shape better than voice-addressing by letter (Slice B of HOMOPHONE_UI_PLAN)?
- Slice 5 (deferred) layers shape onto the existing underline rather than
  alongside it — only if Slice 1 produces "shape kills noise" verdict.
- Each slice is one commit, one feature flag, one `git revert` to undo.

## 2. Decision-tree shape

```
1 — round-robin paint above flagged tokens
    (no allocator, no group, no action — pure visual)
  └─ Shapes READ as signal               → 2
  └─ Shapes feel like noise              → stop. Either back to underline-only
                                            (Slice A is shipped) or rethink.

2 — per-token shape assignment (allocator state)
    (instance.shape_assignments; stable across edits)
  └─ Stability matters                   → 3
  └─ Round-robin was fine                → keep 1, skip 2

3 — same-group-same-shape
    (homophone group → shape assigned per group, not per token)
  └─ Recall improves                     → 4
  └─ No measurable difference            → revert 3, keep 2

4 — phone <shape> swap grammar
    (voice surface — "phone bolt" cycles bolt-marked group)
  └─ Better than phone <letter>          → keep
  └─ Worse                                → revert 4, keep 3

5 — fold shape onto the underline
    (instead of a separate paint above the dot)
  └─ Combined indicator wins             → demote Slice A underline to spillover
  └─ Separate paint reads better         → keep both
```

## 3. Per-slice spec

### Slice 1 — round-robin shape paint (THIS SLICE)

**Goal.** Learn whether Cursorless-style hat shapes carry above flagged prose
tokens. No allocator state, no group membership, no voice surface — pure
read-only paint.

**Files touched** (rough LOC):
- **new** `svg/` directory + 11 vendored SVGs + `svg/NOTICE.md` — see §4.6 / §4.7.
- **new** `prose_overlay_shapes.py` (~80 LOC) — owns the shape vocabulary,
  parses the vendored SVGs at import time, exposes `HAT_SHAPES`,
  `shape_pool()`, and `draw_hat_shape(c, name, color, cx, cy, scale, alpha)`.
- `prose_overlay_draw_tokens.py` (~+15 LOC) — inside `_draw_token_rows`, if
  the token is flagged AND shapes are enabled, paint
  `shape_pool()[flagged_rank % 10]` above the existing letter-hat dot.
- `prose_overlay_draw.py` (~+6 LOC) — pass `shape_enabled` down.
- `prose_overlay_draw_constants.py` (~+2 LOC) — `HOMOPHONE_SHAPE_SCALE`,
  `HOMOPHONE_SHAPE_DEFAULT_COLOR`.
- `prose_overlay.py` (~+6 LOC) — `mod.setting("prose_overlay_homophone_shapes",
  type=bool, default=False, ...)`.
- `prose_overlay_actions_visibility.py` (~+8 LOC) —
  `prose_overlay_set_homophone_shapes(enabled: int)` runtime toggle.
- `prose_overlay.talon` (~+2 LOC) — `overlay shapes homo on/off` voice binds.
- `scripts/headless-verify.py` + `docs/HEADLESS_VERIFY_PLAN.md` — L1.20-L1.23
  cover the new module without Skia (graceful skip if `Path.from_svg`
  unavailable).

**Feature flag.** `user.prose_overlay_homophone_shapes` (bool, default `False`).
Off by default — see §6.1.

**Voice surface (Slice 1 only).**
```talon
overlay shapes homo on:  user.prose_overlay_set_homophone_shapes(1)
overlay shapes homo off: user.prose_overlay_set_homophone_shapes(0)
```

**Keep criterion.** After flipping on for a session of normal dictation, the
user reports the shapes "carry" — they read as cleanly above tokens as they
do above mouse-clock letters, and they don't fight the existing letter-hat dot
for visual real estate.

**Kill criterion.** Shapes feel cluttered, busy, or hard to distinguish from
the letter-hat dot. OR shapes look broken / mis-scaled / off-position at
prose-token scale (~16pt). Either case → revert this slice, keep the
underline-only Slice A from `HOMOPHONE_UI_PLAN.md`.

**Reversibility.** `git revert <slice-1-shas>` removes one new module, 11
SVGs, two constants, one setting, one action, two voice lines, four headless
tests. Zero schema change to ProseBuffer, instance state, or hat allocator.
Underline (Slice A) untouched.

**Non-goals (per parent prompt).**
- No allocator state (Slice 2).
- No group membership (Slice 3).
- No `phone <shape>` grammar or swap action (Slice 4).
- No demotion of the underline (Slice 5).
- No changes to `instance.hat_assignments`.
- No changes to `prose_overlay_homophones.py` exports.

### Slices 2-5

Out of scope for this work. Specifications will be drafted when Slice 1's
keep/kill verdict lands.

## 4. Foundational risks to dodge

### 4.6 SVG vendoring (DECIDED — vendor into `svg/`)

**Risk.** Reading SVGs from `~/.talon/user/trillium/mouse-clock/src/svg/` at
runtime ties prose-overlay to mouse-clock being installed. Mouse-clock is a
sibling Talon plugin that may not be present on every machine prose-overlay
ships to.

**Dodge.** Vendor the 11 SVGs into `prose-overlay/svg/`. Self-contained,
license-clean (MIT, same author — see §4.7). Read paths via
`os.path.dirname(__file__)`. Drift between mouse-clock and prose-overlay is
acceptable — these are static visual assets, not API.

### 4.7 License

Source repo `trillium/mouse-clock` is MIT-licensed and authored by Trillium
Smith. Vendoring is explicitly permitted; `svg/NOTICE.md` documents the
provenance.

### 4.8 Coexistence with the existing underline (Slice A)

**Risk.** The underline (Slice A) and shape (Slice 1) both fire on the same
flagged-index lookup. If they paint at the same time, the visual is double-
encoded ("this token is homophonic" twice).

**Dodge for Slice 1.** Slice 1 ships with no change to the underline paint.
Both indicators paint when both flags are on; default of `homophone_shapes`
is OFF, so default behavior is unchanged (only the underline shows). If
Slice 1 KEEPS, Slice 5 will demote the underline to spillover-only.

## 5. ISA updates

This slice supersedes the old ISC-13 placeholder ("homophone slice B —
`phone <hat>`") because the Cursorless hat-shape primitive is the cleaner
foundation for the homophone-swap surface. ISC-14 expands into four sub-ISCs
per §3:

- ISC-14a: Slice 1 — round-robin shape paint (THIS SLICE)
- ISC-14b: Slice 2 — `instance.shape_assignments` per-token stability
- ISC-14c: Slice 3 — same-group-same-shape allocation
- ISC-14d: Slice 4 — `phone <shape>` swap grammar

## 6. Open questions for Trillium

1. **Default-on or default-off for Slice 1?** DECIDED — default OFF.
   Plan recommendation. The experiment is invisible at the voice layer until
   Trillium opts in via `overlay shapes homo on`.

2. **Vendor SVGs into `prose-overlay/svg/` or read from mouse-clock?** DECIDED
   — vendor. See §4.6. Self-contained, no install-order dependency.

3. **Round-robin keyed by flagged-rank OR by token index?** Slice 1 uses
   flagged-rank (`sorted(flagged_indices).index(idx) % 10`). Simpler — every
   flagged token gets a stable position in the pool given the same token
   stream. Re-shuffles on every edit; that's the experiment.

4. **Default scale?** `HOMOPHONE_SHAPE_SCALE = 0.75` matches mouse-clock's
   default for cursor-letters. Open in Slice 2 if shapes feel too small/big
   at 16pt token text.

5. **Default color?** `HOMOPHONE_SHAPE_DEFAULT_COLOR = "gray"` per
   mouse-clock convention. Open in Slice 3 once group-keyed coloring lands.

---

*Plan ends. Slice 1 ships invisible at the voice layer (default OFF), is
reversible in N reverts (N commits — see implementation), and is decidable
from one session of normal use after `overlay shapes homo on`.*
