# `phone <shape>` — Behavior Specification

> Given-when-then spec for the homophone swap feature (Slice 4 of
> `docs/HOMOPHONE_SHAPES_PLAN.md`). Source of truth for implementation;
> the gherkin scenarios below are the test surface.
>
> Status: **NOT YET BUILT.** Slices 1 + 2 (renderer + allocator) shipped.
> Slice 3 (panels showing alternates) precedes this slice. Slice 4 is
> the actual swap action.
>
> **Model:** cycling IS the behavior. Each `phone <shape>` / `phones <shape>`
> invocation swaps the token to the NEXT group member (CSV row order,
> wrapping). No separate stage-then-commit step. Repeat the verb to keep
> cycling.

## Vocabulary

- **Homophone group** — a CSV row from `~/.talon/user/trillium_talon/core/homophones/homophones.csv`, e.g. `their,there,they're`. The group is the set of words that sound alike.
- **Current word** — the surface text currently in the buffer at the flagged token (e.g. `there`).
- **Next alternate** — the group member immediately after the current word in CSV row order, wrapping at the end. For group `their,there,they're`:
  - current `their` → next `there`
  - current `there` → next `they're`
  - current `they're` → next `their` (wraps)
- **Shape hat** — the colored Cursorless-style glyph painted on a flagged token by Slice 1's renderer, addressable by `shape_pool()` names (`bolt`, `wing`, `frame`, …). Each flagged token has at most one shape (10-shape pool; >10 simultaneous = underline-only spillover).
- **Letter hat** — the gray-letter dot still painted on every token (including flagged ones) by the standard hat allocator. Separate addressing namespace from the shape hat.

## Background

```
Given the overlay is active
And the user has dictated text containing homophones
Then each flagged token has BOTH a letter hat AND a shape hat
And the shape vocabulary identifies which homophones can be swapped
```

The shape hat is one addressing key for the swap. The user-spoken word is another. The letter hat is unchanged from non-flagged tokens and remains addressable by all standard hat-targeted verbs (`chuck`, `take`, `change`, etc.).

## Scenario 1 — Basic swap (shape-addressed)

```
Given a token reads "there" in the buffer
And the token is flagged as a homophone
And the token's shape hat is "wing"
And the group is "their,there,they're"

When the user says `phone wing` OR `phones wing`

Then the token text changes from "there" to "they're" (next member after
    "there" in CSV row order, wrapping)
And the change lands as ONE STRUCTURAL undo step
And the cursor does not move
And the canvas refreshes once
And the new word is re-flagged (still a homophone) — the shape stays
    "wing" per Slice 2's stability rules
```

Singular `phone` and plural `phones` are aliases — both trigger the same swap. Repeat the verb to keep cycling (see Scenario 2).

## Scenario 2 — Cycling through a multi-member group

```
Given a token reads "their" in the buffer
And its shape hat is "wing"
And the group is "their,there,they're"

When the user says `phones wing`
Then the token text changes from "their" to "there"
And this is ONE undo step

When the user says `phones wing` again
Then the token text changes from "there" to "they're"
And this is a SECOND undo step

When the user says `phones wing` a third time
Then the token text changes from "they're" to "their" (wraps to start)
And this is a THIRD undo step

When the user says `overlay undo` three times
Then the token text returns to "their" through the same sequence in
    reverse: they're → there → their
```

Cycling is the behavior — there is no separate "preview the next swap" step. Each utterance commits a swap. For 2-member groups (`your,you're`) cycling toggles. For 3-member groups it rotates.

## Scenario 3 — Word-addressed swap (`phones <word>`)

```
Given two tokens are flagged in the buffer:
    - token A reads "there" with shape hat "wing"
    - token B reads "your"  with shape hat "bolt"

When the user says `phones there`

Then the token currently reading "there" (token A) cycles to its next
    group member ("they're" given group "their,there,they're")
And the buffer at token B is unchanged
And this is ONE undo step

When the user says `phones your`
Then token B's text changes from "your" to "you're" (group "your,you're")
And token A is unchanged
```

`phones <word>` is an alternative addressing path — useful when the user doesn't remember the shape name. Inside the overlay-active context, `phones <user.homophones_canonical>` routes to the same swap action as `phones <shape>`, just looked up by the current surface word instead of by shape hat.

**Conflict with the existing community modal HUD**: when the prose overlay is active, `phones <word>` does **not** open the existing modal HUD at `~/.talon/user/trillium_talon/core/homophones/homophones.talon`. The overlay's grammar (1 mode + 1 tag) wins context specificity, and the swap is performed directly. When the overlay is **not** active, the modal HUD still works as before.

## Scenario 4 — Phone with no matching shape

```
Given the overlay is active
And no token currently has the "bolt" shape hat

When the user says `phone bolt`

Then nothing changes in the buffer
And the action prints a hint to the Talon log
And no undo step is recorded
```

The action is a no-op when the spoken shape is unassigned. Defensive — does not surface user-facing error UI in v1 (TBD whether a brief flash/chrome on the canvas is worth adding).

## Scenario 5 — Phone after surrounding edits

```
Given a token reads "there" at idx 5 in the buffer
And its shape hat is "wing"

When the user dictates additional words BEFORE the flagged token,
shifting it to idx 8

And the user says `phone wing`

Then the shape allocator (Slice 2) has kept the same "wing" assignment
    for the moved token
And the token (now at idx 8) text cycles to the next group member
And the swap targets the same logical token despite the index shift
```

This is the Slice 2 keep-criterion in action — shape identity must be stable across edits so muscle memory works.

## Scenario 6 — Pool overflow (no shape, no shape-addressed swap)

```
Given 11 or more tokens in the buffer are flagged as homophones
And the shape allocator has assigned shapes to the first 10
And the 11th flagged token has NO shape hat (overflow per §4.8)

When the user says `phone <any-shape>`

Then the swap targets one of the 10 shape-assigned tokens
And the 11th flagged token cannot be addressed by `phone <shape>`

When the user instead says `phones <word>` where <word> matches the
overflow token's surface text
Then the overflow token CAN still be cycled — word addressing does not
    depend on the shape pool
```

Word addressing (`phones <word>`) is the recovery path for overflow tokens. Shape addressing is the muscle-memory path.

## Scenario 7 — Letter hat coexistence

```
Given a token "there" has letter hat "blue-h" and shape hat "wing"

When the user says `chuck blue h`
Then the entire token is deleted (letter-hat addressing)
And the shape hat is also gone (the token no longer exists)

When the user instead says `phone wing`
Then the token text cycles to the next group member ("they're")
And the letter hat reallocates per the normal hat allocator (may now
    be "blue-t" or similar)
And the shape hat stays "wing" per Slice 2 stability

When the user instead says `change blue h there`
Then the token is replaced with "there" verbatim (dictation insert at hat)
```

The two namespaces compose freely; user picks the verb that matches intent. `phone` / `phones` is for known-homophone swaps; `change` is for general edits.

## Scenario 8 — Voice grammar specificity

```
Given the overlay is active (tag user.prose_overlay_active set)

When the user says `phone wing`
Then the prose-overlay grammar matches
    `(phone | phones) {user.hat_shape}` and fires
    user.prose_overlay_phone_shape(hat_shape)
And does NOT match `<user.raw_prose>` (literal-word + capture beats
    bare capture)
And the word "phone" does NOT enter the buffer as dictation

When the user says `phones there`
Then the prose-overlay grammar matches
    `phones <user.homophones_canonical>` and fires
    user.prose_overlay_phone_word(homophones_canonical)
And does NOT match `<user.raw_prose>`
And does NOT open the community modal HUD

When the user says `phone` alone (no shape, no word)
Then no rule matches in the overlay context
And falls through to `<user.raw_prose>` → "phone" enters the buffer as
    a regular word (mostly harmless — user notices and undoes)
```

## Scenario 9 — Undo restores prior word

```
Given a token was just swapped from "there" to "they're" via `phone wing`

When the user says `overlay undo` OR `prose undo`

Then the token text reverts from "they're" to "there"
And the swap is a single undo step (per Scenario 1)
And the user can say `phone wing` again to redo the swap

When the user says `overlay redo`
Then the token text returns to "they're"
```

Both `overlay undo` and `prose undo` are accepted aliases for the undo action — `overlay undo` matches the existing convention (`overlay reset`, `overlay dump`, etc.); `prose undo` matches the launch-phrase prefix (`prose overlay`, `prose history`). Same action under the hood; both rules live in `prose_overlay.talon`.

The bracket API from `docs/UNDO_REDO_PLAN.md` Phase 2 (ISC-23) is the substrate. The `phone` action MUST wrap its mutation in `commit_start("phone <shape>", STRUCTURAL) / commit_end()` to satisfy this scenario.

## Scenario 10 — Empty buffer or no homophones present

```
Given the overlay is active
And the buffer is empty (or contains no flagged tokens)

When the user says `phone wing`
Then the action is a no-op (no token has the "wing" shape)
And the action prints a hint to the Talon log

When the user says `phones there`
Then same — no-op (no token reads "there")
```

## Non-goals (explicit out-of-scope for v1)

- `phone <shape> as <word>` — explicit named target ("commit the wing-flagged token to the literal word _they're_"). Reserved for v1.5 if cycling-only doesn't cover real cases.
- `phone every line` / bulk swap — not in scope.
- `phones ignore wing` / dismissal — not in scope.
- TTS confirmation of swap — opt-in, deferred (research §6 OQ6).
- Animation on swap (iOS-17 fade) — nice-to-have, deferred.
- LM-confidence-defaulted next alt — that's Slice 5, a separate slice with its own keep/kill verdict. v1 default is deterministic CSV row order.
- A separate `cycle <shape>` verb — collapsed into `phone` / `phones`; cycling IS the swap.

## Required substrate (already shipped)

- ✅ Slice 1 — shape renderer (`shim/shapes.py:draw_hat_shape`, `svg/`)
- ✅ Slice 2 — deterministic allocator (`shim/shapes.py:compute_shape_assignments`)
- ✅ Undo/redo bracket API (`internal/state.py:commit_start / commit_end`, ISC-23)
- ⏳ Slice 3 — per-token panel showing alternates (optional prerequisite — panel helps the user SEE the next alt before saying `phone`, but cycling works without it)

## Required new surface (this slice — to build)

- `internal/homophones.py` — new exported helper `group_for_word(token: str) -> tuple[str, ...] | None` returning the canonical group for a flagged word (or `None` if unflagged). Plus `next_in_group(current: str) -> str | None` returning the next CSV-row member (wrapping).
- `shim/actions_homophones.py` (new module) — two actions:
  - `prose_overlay_phone_shape(shape_name: str)` — Scenario 1, 2, 4, 5, 6, 7, 9; looks up `instance.shape_assignments` for the token at `shape_name`, calls `next_in_group(current_word)`, brackets the buffer mutation via `commit_start("phone <shape>", STRUCTURAL) / commit_end()`.
  - `prose_overlay_phone_word(word: str)` — Scenario 3, 6; scans the buffer for a flagged token reading `word`, calls `next_in_group(current_word)`, brackets the mutation. If multiple tokens read the same word, swaps the first match (or all matches? — see open question 2).
- `prose_overlay.talon` — new grammar rules (in the overlay-active context):
  ```
  (phone | phones) {user.hat_shape}:
      user.prose_overlay_phone_shape(hat_shape)
  phones <user.homophones_canonical>:
      user.prose_overlay_phone_word(homophones_canonical)
  prose undo: user.prose_overlay_undo()
  ```
  The `(phone | phones) {hat_shape}` rule is one rule with alternation, so both verbs route to the same action.
- `prose_overlay.py` — `mod.list("prose_hat_shape", ...)` with the 10 shape names (decouple from mouse-clock per HOMOPHONE_SHAPES_PLAN.md §4.6). NOTE: `{user.hat_shape}` in the grammar above expects mouse-clock's list; if we declare our own `{user.prose_hat_shape}`, the grammar rule must reference that instead.

## Headless test coverage

Each scenario above maps to a test in `scripts/headless-verify.py`:

- L1.X — `next_in_group("there")` returns "they're" for group `their,there,they're`
- L1.X — `next_in_group("they're")` returns "their" (wraps)
- L1.X — `next_in_group("your")` returns "you're" for 2-member toggle
- L1.X — `next_in_group("not-a-homophone")` returns None
- L1.X — buffer-level swap pattern: `their → there → they're → their` via three commit_start/set_tokens_raw/commit_end cycles produces three undo records
- L1.X — pool overflow leaves overflow tokens unaddressable by phone_shape (no-op when shape not in shape_assignments)
- L1.X — word-addressed swap finds the right token among multiple flagged ones
- L3.X — `prose_overlay_phone_shape` dispatch routes correctly
- L3.X — `prose_overlay_phone_word` dispatch routes correctly

Live-only: the actual voice grammar match for `(phone | phones) {hat_shape}` and `phones <user.homophones_canonical>`.

## Open questions for the implementer

1. **CSV order vs alphabetical** — the spec defaults to "next member in CSV row order, wrapping." This is deterministic and matches how the CSV is read today. Alphabetical would also work; pick one explicitly so cycling is predictable across machines.

2. **Word-addressed swap with multiple matches** — if two tokens in the buffer both read "there", which one does `phones there` cycle? Options: (a) first match by token index, (b) all matches simultaneously (bulk), (c) the most-recently-edited one (rev-tracked). v1 default proposal: first match by token index (simple, deterministic). Surface a TTS hint when there were multiple candidates.

3. **What about a token whose group has only one member** (degenerate 1-word CSV row)? `next_in_group(current)` returns the same word back. `phone` is then a no-op or a no-op-with-hint. Test explicitly.

4. **Hat shape list source — mouse-clock vs in-repo** — HOMOPHONE_SHAPES_PLAN.md §4.6 recommends declaring our own list in `prose_overlay.py` for decoupling. Confirm this still holds when wiring the grammar; the talon rule above shows `{user.hat_shape}` (mouse-clock's list) but we can swap to `{user.prose_hat_shape}` (ours) without changing the action signature.

5. **`prose undo` collision** — verify no existing rule binds `prose undo` (especially in trillium_talon or community). If clean, add it alongside `overlay undo` as documented in Scenario 9.
