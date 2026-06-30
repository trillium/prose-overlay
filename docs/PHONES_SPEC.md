# `phone <shape>` — Behavior Specification

> Given-when-then spec for the homophone swap feature (Slice 4 of
> `docs/HOMOPHONE_SHAPES_PLAN.md`). Source of truth for implementation;
> the gherkin scenarios below are the test surface.
>
> Status: **NOT YET BUILT.** Slices 1 + 2 (renderer + allocator) shipped.
> Slice 3 (panels showing alternates) precedes this slice. Slice 4 is
> the actual swap action.

## Vocabulary

- **Homophone group** — a CSV row from `~/.talon/user/trillium_talon/core/homophones/homophones.csv`, e.g. `their,there,they're`. The group is the set of words that sound alike.
- **Current word** — the surface text currently in the buffer at the flagged token (e.g. `there`).
- **Staged alternate** — the group member that `phone <shape>` would swap TO if invoked right now. Default for a freshly-flagged token: first group member that is NOT the current word.
- **Shape hat** — the colored Cursorless-style glyph painted on a flagged token by Slice 1's renderer, addressable by `shape_pool()` names (`bolt`, `wing`, `frame`, …). Each flagged token has at most one shape (10-shape pool; >10 simultaneous = underline-only spillover).
- **Letter hat** — the gray-letter dot still painted on every token (including flagged ones) by the standard hat allocator. Separate addressing namespace from the shape hat.

## Background

```
Given the overlay is active
And the user has dictated text containing homophones
Then each flagged token has BOTH a letter hat AND a shape hat
And the shape vocabulary identifies which homophones can be swapped
```

The shape hat is the addressing key for the swap. The letter hat is unchanged from non-flagged tokens and remains addressable by all standard hat-targeted verbs (`chuck`, `take`, `change`, etc.).

## Scenario 1 — Basic two-step swap

```
Given a token reads "there" in the buffer
And the token is flagged as a homophone
And the token's shape hat is "wing"
And the staged alternate for this token is "their"

When the user says `phone wing`

Then the token text changes from "there" to "their"
And the change lands as ONE STRUCTURAL undo step
And the cursor does not move
And the canvas refreshes once
And the new word is re-flagged (still a homophone) — the shape may
    re-allocate per Slice 2's stability rules
```

## Scenario 2 — Cycling the staged alternate

```
Given a token reads "there" in the buffer
And its shape hat is "wing"
And the homophone group is "their, there, they're"
And the staged alternate is "their" (default — first non-current)

When the user says `cycle wing`

Then the staged alternate advances to "they're"
And the buffer text DOES NOT change
And no undo step is recorded
And the panel (Slice 3) re-renders to show "they're" as the staged member
And the canvas refreshes

When the user says `cycle wing` again
Then the staged alternate advances to "their" (wraps around)
And the buffer text still has not changed

When the user says `phone wing`
Then the token text changes from "there" to "their"
And the change is one STRUCTURAL undo step
```

## Scenario 3 — Phone with no matching shape

```
Given the overlay is active
And no token currently has the "bolt" shape hat

When the user says `phone bolt`

Then nothing changes in the buffer
And the action prints a hint to the Talon log
And no undo step is recorded
```

The action is a no-op when the spoken shape is unassigned. Defensive — does not surface user-facing error UI in v1 (TBD whether a brief flash/chrome on the canvas is worth adding).

## Scenario 4 — Phone after surrounding edits

```
Given a token reads "there" at idx 5 in the buffer
And its shape hat is "wing"

When the user dictates additional words BEFORE the flagged token,
shifting it to idx 8

And the user says `phone wing`

Then the shape allocator (Slice 2) has kept the same "wing" assignment
    for the moved token
And the token (now at idx 8) text changes from "there" to its staged alternate
And the swap targets the same logical token despite the index shift
```

This is the Slice 2 keep-criterion in action — shape identity must be stable across edits so muscle memory works.

## Scenario 5 — Pool overflow (no shape, no swap)

```
Given 11 or more tokens in the buffer are flagged as homophones
And the shape allocator has assigned shapes to the first 10
And the 11th flagged token has NO shape hat (overflow per §4.8)

When the user says `phone <any-shape>`

Then the swap targets one of the 10 shape-assigned tokens
And the 11th flagged token cannot be addressed by `phone`
And the user must either:
  - resolve one of the visible homophones first to free a shape slot, OR
  - address the overflow token via its letter hat + `change` verb
```

## Scenario 6 — Letter hat coexistence

```
Given a token "there" has letter hat "blue-h" and shape hat "wing"

When the user says `chuck blue h`
Then the entire token is deleted (letter-hat addressing)
And the shape hat is also gone (the token no longer exists)

When the user instead says `phone wing`
Then the token text is swapped to the staged alternate (e.g. "their")
And the letter hat reallocates per the normal hat allocator (may now be "blue-t" or similar)
And the shape hat may persist or reallocate per Slice 2 stability rules

When the user instead says `change blue h there`
Then the token is replaced with "there" verbatim (dictation insert at hat)
And the staged-alt state of the shape (if any) is reset for the new token
```

The two namespaces compose freely; user picks the verb that matches intent. `phone` is for known-homophone swaps; `change` is for general edits.

## Scenario 7 — Voice grammar specificity

```
Given the overlay is active (tag user.prose_overlay_active set)

When the user says `phone wing`
Then the prose-overlay grammar matches `phone {user.hat_shape}` and fires
    user.prose_overlay_phone_shape(hat_shape)
And does NOT match `<user.raw_prose>` (literal-word + capture beats bare capture)
And the word "phone" does NOT enter the buffer as dictation

When the user says `cycle wing`
Then `cycle {user.hat_shape}` fires user.prose_overlay_phone_advance(hat_shape)
And the word "cycle" does NOT enter the buffer

When the user says `phone` alone (no shape)
Then no rule matches (specificity requires a shape token)
And falls through to `<user.raw_prose>` → "phone" enters the buffer
    as a regular word (mostly harmless — user notices the typo and undoes)
```

## Scenario 8 — Conflict with existing `phones` plural

```
Given the existing trillium_talon community grammar binds `phones <word>`
    to open a modal homophone HUD

When the user says `phones there`
Then the EXISTING modal HUD opens (unchanged behavior)

When the user says `phone wing`
Then the NEW prose-overlay swap action fires
And the modal HUD does NOT open
```

Singular `phone` and plural `phones` are distinct verbs. The new feature reserves only the singular; the plural's modal flow remains the user's known-good explicit-name fallback.

## Scenario 9 — Undo restores prior word

```
Given a token was just swapped from "there" to "their" via `phone wing`

When the user says `overlay undo`

Then the token text reverts from "their" to "there"
And the swap is a single undo step (per Scenario 1)
And the staged alternate state restores to what it was pre-swap
And the user can say `phone wing` again to redo the swap
```

The bracket API from `docs/UNDO_REDO_PLAN.md` Phase 2 (ISC-23) is the substrate. `phone` MUST wrap its mutation in `commit_start("phone <shape>", STRUCTURAL) / commit_end()` to satisfy this scenario.

## Scenario 10 — Empty buffer or no homophones present

```
Given the overlay is active
And the buffer is empty (or contains no flagged tokens)

When the user says `phone wing`
Then the action is a no-op (no token has the "wing" shape)
And the action prints a hint to the Talon log

When the user says `cycle wing`
Then same — no-op
```

## Non-goals (explicit out-of-scope for v1)

- `phone <shape> as <word>` — explicit named target ("commit the wing-flagged token to the literal word *they're*"). Reserved for v1.5 if `cycle` thrashes.
- `phone every line` / bulk swap — not in scope.
- `phones ignore wing` / dismissal — not in scope.
- TTS confirmation of swap — opt-in, deferred (research §6 OQ6).
- Animation on swap (iOS-17 fade) — nice-to-have, deferred.
- LM-confidence-defaulted staged alt — that's Slice 5, a separate slice with its own keep/kill verdict.

## Required substrate (already shipped)

- ✅ Slice 1 — shape renderer (`shim/shapes.py:draw_hat_shape`, `svg/`)
- ✅ Slice 2 — deterministic allocator (`shim/shapes.py:compute_shape_assignments`)
- ✅ Undo/redo bracket API (`internal/state.py:commit_start / commit_end`, ISC-23)
- ⏳ Slice 3 — per-token panel showing alternates (this slice's prerequisite for color-coded staged display; scenarios above mention "panel re-renders" — that's Slice 3's job)

## Required new surface (this slice — to build)

- `shim/shapes.py` — extend `compute_shape_assignments` return type to also carry the staged-alt index per token: `dict[int, tuple[str, int]]` or add a parallel `staged_alt_assignments` dict.
- `shim/actions_homophones.py` (new module) — three actions:
  - `prose_overlay_phone_shape(shape_name: str)` — commit (Scenario 1, 4, 9)
  - `prose_overlay_phone_advance(shape_name: str)` — cycle (Scenario 2)
  - `prose_overlay_set_homophone_swap(enabled: int)` — feature toggle
- `prose_overlay.talon` — new grammar rules:
  - `phone {user.hat_shape}: user.prose_overlay_phone_shape(hat_shape)`
  - `cycle {user.hat_shape}: user.prose_overlay_phone_advance(hat_shape)`
  - `overlay swap homo on/off: ...`
- `prose_overlay.py` — `mod.list("prose_hat_shape", ...)` with the 10 shape names (decouple from mouse-clock per HOMOPHONE_SHAPES_PLAN.md §4.6).
- `internal/homophones.py` — new exported helper `group_for_word(token: str) -> tuple[str, ...] | None` returning the canonical group for a flagged word (or `None` if unflagged). Required by the staged-alt computation. Adds it once for Slice 3 — Slice 4 reuses.

## Headless test coverage

Each scenario above maps to a test in `scripts/headless-verify.py` (Layer 1 for pure-state, Layer 3 for action dispatch):

- L1.X — `compute_staged_alt` returns first-non-current group member
- L1.X — `commit_phone` mutates buffer to staged word + bumps rev once + creates one undo record
- L1.X — `cycle_staged` advances the index without mutating buffer
- L1.X — pool overflow leaves overflow tokens unaddressable by phone (no-op)
- L3.X — `prose_overlay_phone_shape` dispatch routes correctly
- L3.X — `prose_overlay_phone_advance` dispatch routes correctly

Live-only: the actual voice grammar match for `phone {user.hat_shape}` and the panel re-render after `cycle`.

## Open questions for the implementer

1. **Default staged-alt rule** — "first non-current group member" is the spec default. For 2-member groups (your/you're, their/there) this is deterministic. For 3-member groups (their/there/they're) the first non-current is ambiguous in ordering — pin on CSV row order? Alphabetical? Pick one explicitly.

2. **Staged-alt state lifecycle** — when a token is freshly flagged, its staged_alt_idx is reset to 0. When `cycle` advances, the index lives WHERE? On `instance.shape_assignments` (extend to a tuple) or a parallel `instance.staged_alt_assignments`? The plan §3 Slice 4 implies the former. Build it that way unless something else surfaces.

3. **Cursor behavior on swap** — Scenario 1 says cursor doesn't move. Verify against the existing change/replace flow's cursor behavior; pick the one that feels most natural.

4. **What if the buffer contains a token whose group has only one member** (e.g. a homophone CSV entry with just one word — degenerate)? Probably `phone` is a no-op since there's no alternate. Test explicitly.

5. **Hat shape list source — `mouse-clock` vs in-repo** — HOMOPHONE_SHAPES_PLAN.md §4.6 recommends declaring our own list in `prose_overlay.py` for decoupling. Confirm this still holds when wiring Slice 4.
