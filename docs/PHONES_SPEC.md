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
- **Segmented underline** — the amber underline below each flagged token, segmented into N parts (one per group member) with a brief gap between segments. The segment whose position corresponds to the **current word's index in the group's CSV row order** is rendered with a slight highlight (thicker / brighter / different alpha). Updates on every swap to reflect the new active position. Compact, always-on indicator of cycle position.
- **Expanded panel** — a larger in-canvas widget rendered alongside each shape-hatted token, listing every group member with a color-coded background per member. The colors are the familiar Cursorless palette (`red blue green pink yellow purple plum gold black white`, where `plum→purple` and `gold→yellow` are aliases). The panel doubles as the legend for color-addressed direct swap (Scenario 4). Complementary to the segmented underline — underline shows POSITION, panel shows ALTERNATES with color address keys.
- **Color-addressed alt** — a group member identified by a Cursorless color name in the expanded panel, so the user can say `<color> <shape>` and land directly on that alt without cycling through siblings.

## Background

```
Given the overlay is active
And the user has dictated text containing homophones
Then each flagged token has BOTH a letter hat AND a shape hat
And the shape vocabulary identifies which homophones can be swapped
```

A flagged token can be addressed for swap by any of four keys:

1. **Shape hat** — `phone <shape>` / `phones <shape>` (Scenarios 1, 2)
2. **Color + shape** — `<color> <shape>` (Scenario 4)
3. **Current word** — `phones <word>` (Scenario 5)
4. **Letter hat** — `phones <letter>` / `phones <color> <letter>` (Scenario 6)

The letter hat is unchanged from non-flagged tokens and remains addressable by all standard hat-targeted verbs (`chuck`, `take`, `change`, etc.). The new addressing path adds `phones <letter>` to that same hat without breaking existing verbs.

```
Given the overlay is active
And the buffer contains tokens flagged as homophones
And each flagged token has a shape hat
Then the canvas renders an expanded panel per homophone token,
    anchored near the token
And each panel lists the group members with color-coded backgrounds
And each color-to-member mapping is stable so long as the group is stable
```

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

## Scenario 3 — Segmented amber underline shows cycle position

```
Given a token reads "there" in the buffer
And the group is "their,there,they're"

Then the amber underline beneath the token is rendered as THREE
    segments, one per group member, ordered left-to-right by CSV row:
        their       there      they're
        _____   ____[____]____  _____
                     ^^^^^^
                     active segment highlighted
And the highlighted segment is the SECOND one (position 2 of 3 — "there")
And the segments are separated by brief gaps (2 px gap between bars)
And each segment is the existing HOMOPHONE_UNDERLINE_HEIGHT (1.5 px tall)
And the active segment is THICKER (e.g. 2.5 px) or BRIGHTER (e.g. alpha
    ramps from cc to ff)

When the user says `phones air` OR `phone wing` OR `phones there`
    (any addressing path triggering a cycle)

Then the buffer text cycles to "they're" (next CSV member after "there")
And the underline re-renders with the THIRD segment highlighted instead
    of the second
And the segment count stays 3 (group is unchanged)
And the user can SEE the position update on the same draw cycle as the
    swap
```

### Example layouts

```
2-member group ("your,you're"), current "your":
    your    you're
    [____]   ____
     ^^^
     position 1

After "phones <X>" → current "you're":
    your    you're
    _____  [____]
            ^^^
            position 2

3-member group ("their,there,they're"), current "their":
    their      there      they're
    [____]      ____       ____
     ^^^^
     position 1

After "phones <X>" → current "there":
    their      there      they're
    _____     [____]       ____
                ^^^^
                position 2

After "phones <X>" again → current "they're":
    their      there      they're
    _____      ____      [____]
                          ^^^^
                          position 3

After "phones <X>" again → wraps to "their":
    their      there      they're
    [____]      ____       ____
     ^^^^
     position 1 (wrapped)
```

The segmented underline is the compact always-on indicator of where in the cycle the user is. It complements the expanded panel (Scenario 4) — the panel shows the full alternate words with color addressing; the underline shows position with minimal pixel cost.

### Token-width budgeting

Segments split the token's underline rect equally with a fixed gap:
```
segment_width = (tw - gap_count * GAP_W) / member_count
gap_count     = member_count - 1
GAP_W         = 2 px (constant)
```

For short tokens with many group members (e.g. "I" with a 4-member group), individual segments may compress to sub-pixel. **Open question 11**: minimum segment width? If `segment_width < 1.5 px`, options are (a) suppress the underline and fall back to solid amber, (b) skip the gaps and render as a single bar with a highlight marker, (c) extend the underline width slightly past the token. v1 proposal: (a) fall back to solid for unreadably narrow segments, log a hint.

## Scenario 4 — Color-addressed direct swap (`<color> <shape>`)

> **Panel layout — REDESIGN per user 2026-06-30 PM after first impl shipped.**
> The first implementation rendered alts as flat color chips packed under each
> token, with truncation when chip width was less than the alt text width
> ("they're" truncated to "t"). The redesign anchors each token's alts in a
> distinct **bubble** with the homophone shape glyph in the middle as a visual
> anchor, color-coded chips flanking it:
>
> ```
> Visual layout per token:
>
>            ·^                                ← shape hat + letter hat (above token)
>          there                               ← token text
>          ─────                               ← segmented amber underline
>     [their][shape][they're]                  ← BUBBLE: gold chip | shape | blue chip
>
> For 3 adjacent tokens, 3 distinct bubbles:
>
>            ·^             ·^             ·^
>          there          there         they're
>          ─────          ─────          ─────
>     [their][shape][they're] | [their][shape][they're] | [their][shape][there]
>     ←   token 1 bubble   →    ←   token 2 bubble   →    ←   token 3 bubble   →
>
> The `|` between bubbles is conceptual — render as whitespace separation
> (no literal pipe glyph) so adjacent bubbles read as distinct units.
> ```
>
> **Why the shape glyph inside the bubble**: visually anchors which token the
> bubble belongs to. Without it, when bubbles wrap or float below the token
> row, the user has to infer the mapping from horizontal position. With the
> shape inside, "the wing-shape's bubble" is unambiguous.
>
> **Chip sizing**: each chip sizes to fit its full alt text (no truncation).
> Use a small chip font (~11px) and pad ~4px each side. Bubble total width
> is the sum of left chip + shape + right chip + 2 gaps. Bubble height is
> chip height (~14px).
>
> **Bubble anchor — REVISED 2026-06-30 PM/2 after second user verdict.** Bubbles must sit COMPLETELY OUTSIDE the prose-overlay panel rect, on a single horizontal band:
>
> - If `viewport._anchor_position == "top"` (panel anchored to screen top): bubbles render in a band **BELOW** the panel's bottom edge.
> - If `viewport._anchor_position == "bottom"` (panel anchored to screen bottom): bubbles render in a band **ABOVE** the panel's top edge.
>
> All bubbles share a single y coordinate — **NO vertical stacking** when bubbles overlap horizontally. If the total bubble row exceeds the screen width, bubbles clip at the screen edge (acceptable failure mode); the visual clarity of a single horizontal row beats the loss of off-screen alts. The prior collision-band-wrap behavior (commits `cf5f492` + `44bf2d8`) is removed.
>
> **Horizontal alignment per bubble** stays centered on its token's x position when possible, but constrained to keep the row contiguous: if two adjacent tokens would have overlapping centered bubbles, the bubbles either shift apart (preferred) or the second one shifts right until clear. No vertical collision logic; only horizontal nudging on the band.
>
> **Shape glyph inside the bubble needs a black circle background** so it reads against the chip's color background AND against the dark surroundings outside the panel. Render a small filled black (or near-black, `000000cc` for slight softness) circle at the shape's center, slightly larger than the shape's bounding box (e.g. `shape_radius * 1.15`), then paint the amber shape on top.
>
> **For 2-member groups** (e.g. `your,you're`): only one alt — render as
> `[chip][shape]` (one chip + shape, no right side). Or `[shape][chip]` —
> pick one and document. v1 default: `[chip][shape]` (left-side).
>
> **For 4+ member groups** (rare): more colors. Extend the color palette
> `[yellow, blue, green, pink, red, purple, black, white]` and lay out
> as `[chip1][shape][chip2]` for the first two, or wrap to a second row
> `[chip1][shape][chip2] / [chip3][chip4]`. v1 proposal: render only the
> first two alts; extras are reachable via cycling (`phones <shape>`).
>

```
Given a token reads "there" in the buffer
And its shape hat is "play"
And the group is "their,there,they're"
And the expanded panel for this token shows:
    - "their"    on a GOLD background
    - "they're"  on a BLUE background
    (current word "there" is the buffer text; rendered as the token itself)

The full visual layout for that token area:
    t[h]{e}re
    [ their ] [ they're ]
       gold      blue
    where [h] is the letter hat (gray-h) and {e} is the shape hat (play)

When the user says `gold play`

Then the token text changes from "there" to "their" in one STRUCTURAL
    undo step
And the buffer reads "it was their car" (was "it was there car")
And the expanded panel re-renders against the new current word:
    - "there"    on GOLD
    - "they're"  on BLUE
    (current word now "their")
And the color-to-alt assignment is recomputed for the new group state
    (the gold slot now points at "there", which used to be the current
    word and so wasn't in the panel)

When the user says `blue play` from the new state
Then the token text changes from "their" to "they're"
And the panel re-renders with the new current word excluded
```

Color-addressed swap is the direct-address path — useful when the user can see the panel and wants a specific alt without cycling. The color-to-alt mapping is per-panel (each shape's panel has its own mapping) and computed from the panel's local group at draw time. See open question 2 for the assignment rule.

### Concrete worked example from the spec author

> buffer: it was t[h]{e}re car (normal hat h on idx 1, shaped play on idx 2)
> gold play: their
> "gold play"
> buffer: it was t[h]{e}ir car

The shape stays `play` per Slice 2 stability. The letter hat reallocates per the normal hat allocator (may become a different letter or color). The expanded panel re-renders with `there` now in the gold slot (was hidden as current) and `they're` still in blue.

## Scenario 5 — Word-addressed swap (`phones <word>`)

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

## Scenario 6 — Letter-hat-addressed swap (`phones <letter>`)

```
Given a token reads "there" in the buffer
And its letter hat is "gray-a" (spoken as "air")
And its shape hat is "wing"
And the group is "their,there,they're"

When the user says `phones air`

Then the token text cycles to its next group member ("they're")
And this is ONE STRUCTURAL undo step
And the letter hat may reallocate per the normal hat allocator
And the shape hat stays "wing" per Slice 2 stability

When the user says `phones air` again
Then the token text cycles to "their" (or whatever the new letter hat
    addresses — see caveat below)
```

`phones <letter>` is the fourth addressing path. Useful when the shape isn't memorable, the panel isn't visible, AND the user already knows the letter hat (because they've been using `chuck`/`take`/`change` on it).

### Color-prefixed letter

```
Given a token "there" has letter hat "blue-h" (spoken "blue hospitality"
    or "blue hotel" depending on alphabet)
And its shape hat is "wing"

When the user says `phones blue h`

Then the same swap happens as `phones air` would for a gray-a hat —
    cycles to the next group member
```

`phones <color> <letter>` addresses tokens whose letter hats have a color prefix (because the gray slot was already taken).

### Caveat: letter-hat reallocation across swaps

```
Given a token "there" has letter hat "gray-a"

When the user says `phones air`
Then the token swaps to "they're"
And the letter-hat allocator may reassign the gray-a slot to a different
    token (since "they're" has no 'a' character to host the hat)
And the swapped token may now wear a different letter hat (e.g. gray-t)

When the user says `phones air` immediately afterward expecting it to
    re-cycle the same homophone
Then it may swap a DIFFERENT token now wearing the gray-a hat

```

This is a known footgun of letter-hat addressing — the hat is character-derived and reshuffles on text change. **Recommendation: use shape-hat addressing (`phones wing`) for repeated cycling of the same logical token, since shape stability is the whole point of Slice 2.** `phones <letter>` is best for one-shot swaps where the next utterance is not another swap of the same token.

## Scenario 7 — Phone with no matching shape

```
Given the overlay is active
And no token currently has the "bolt" shape hat

When the user says `phone bolt`

Then nothing changes in the buffer
And the action prints a hint to the Talon log
And no undo step is recorded
```

The action is a no-op when the spoken shape is unassigned. Defensive — does not surface user-facing error UI in v1 (TBD whether a brief flash/chrome on the canvas is worth adding).

## Scenario 8 — Phone after surrounding edits

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

## Scenario 9 — Pool overflow (no shape, no shape-addressed swap)

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

## Scenario 10 — Letter hat coexistence

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

## Scenario 11 — Voice grammar specificity

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

## Scenario 12 — Undo restores prior word

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

## Scenario 13 — Empty buffer or no homophones present

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
- ⏳ Slice 3 — per-token expanded panel showing alternates. **No longer optional**: Scenario 3 (color-addressed swap) requires the panel to render so the user knows which color points at which alt. Cycling-only (Scenarios 1-2) still works without it, but the full feature surface needs the panel.

## Required new surface (this slice — to build)

- `internal/homophones.py` — new exported helper `group_for_word(token: str) -> tuple[str, ...] | None` returning the canonical group for a flagged word (or `None` if unflagged). Plus `next_in_group(current: str) -> str | None` returning the next CSV-row member (wrapping).
- `shim/actions_homophones.py` (new module) — three actions:
  - `prose_overlay_phone_shape(shape_name: str)` — Scenarios 1, 2, 6, 7, 8, 9, 11; looks up `instance.shape_assignments` for the token with `shape_name`, calls `next_in_group(current_word)`, brackets the buffer mutation via `commit_start("phone <shape>", STRUCTURAL) / commit_end()`.
  - `prose_overlay_phone_color_shape(prose_hat_color: str, shape_name: str)` — Scenario 4; looks up the token by `shape_name`, looks up its panel's color-to-alt mapping for `prose_hat_color`, swaps to that specific alt. Brackets the mutation.
  - `prose_overlay_phone_word(word: str)` — Scenarios 5, 9; scans the buffer for a flagged token reading `word`, calls `next_in_group(current_word)`, brackets the mutation. If multiple tokens read the same word, swaps the first match (or all matches? — see open question 3).
  - `prose_overlay_phone_letter(letter: str, color: str = "gray")` — Scenario 6; looks up the token at letter hat `(color, letter)` via the existing `_hat_to_index` helper, checks if it's flagged (homophone), calls `next_in_group(current_word)`, brackets the mutation. No-op if the token is not flagged.
- `shim/shapes.py` (extend) or new `shim/homophone_panel.py` — compute `dict[int, dict[str, str]]` = `token_idx -> {color_name -> alt_word}` from each shape-hatted token's group, excluding the current word. Re-computed when `_recompute_hats` runs and stored on `instance.homophone_panel_alts` (parallel to `instance.shape_assignments`).
- `internal/homophones.py` (extend) — new helper `current_position_in_group(current_word: str) -> tuple[int, int] | None` returning `(active_idx, group_size)` for a flagged token's current word in its group's CSV row order. Returns `None` for unflagged tokens. Required by the segmented underline render to know which segment to highlight.
- `ui/draw_tokens.py` (extend the existing homophone underline draw block, lines ~177-184) — when `flagged_indices` contains `idx`, look up `group_size` from `current_position_in_group(token)`:
  - If `group_size == 1` or `group_size is None`, paint the existing solid amber underline (back-compat for degenerate or unflagged).
  - Otherwise paint N segments via the budget formula (`segment_width = (tw - (N-1) * GAP_W) / N` with `GAP_W = 2`), and render the segment at `active_idx` with a thicker / brighter style (e.g. height `2.5` px instead of `1.5`, or alpha `ff` instead of `cc`).
  - If a segment would compute to a width less than `MIN_SEGMENT_W` (e.g. 1.5 px), fall back to the solid underline + log hint (open question 11).
- `internal/draw_constants.py` — add `HOMOPHONE_UNDERLINE_GAP_W = 2`, `HOMOPHONE_UNDERLINE_ACTIVE_HEIGHT = 2.5`, `HOMOPHONE_UNDERLINE_MIN_SEGMENT_W = 1.5` (configurable thresholds for the segmented render).
- `ui/draw_panels.py` (new) — render the expanded panel per shape-hatted token. Reads `instance.homophone_panel_alts`. Anchors panel near the token (TBD: below, beside, or floating — see open question 5). Each alt rendered as a small chip with its color as the background, the word as foreground text.
- `prose_overlay.talon` — new grammar rules (in the overlay-active context):
  ```
  (phone | phones) {user.hat_shape}:
      user.prose_overlay_phone_shape(hat_shape)
  <user.prose_hat_color> {user.hat_shape}:
      user.prose_overlay_phone_color_shape(prose_hat_color, hat_shape)
  phones <user.homophones_canonical>:
      user.prose_overlay_phone_word(homophones_canonical)
  phones <user.letter>:
      user.prose_overlay_phone_letter(letter)
  phones <user.prose_hat_color> <user.letter>:
      user.prose_overlay_phone_letter(letter, prose_hat_color)
  prose undo: user.prose_overlay_undo()
  ```
  The `(phone | phones) {hat_shape}` rule is one rule with alternation, so both verbs route to the same action. The `<user.prose_hat_color> {user.hat_shape}` rule reuses the existing `prose_hat_color` capture from `prose_overlay.py` (already normalizes `plum→purple`, `gold→yellow`).
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
- L1.X — `compute_homophone_panel_alts(tokens, shape_assignments)` returns the expected `{token_idx → {color → alt_word}}` mapping for a 2-member group (one color, one alt) and a 3-member group (two colors, two alts)
- L1.X — color-addressed swap: given a panel mapping `{gold: "their", blue: "they're"}` on the "play" shape, calling `phone_color_shape("gold", "play")` swaps the buffer text to "their"
- L1.X — color-addressed swap with stale color (color not in current panel mapping) is a no-op
- L3.X — `prose_overlay_phone_shape` dispatch routes correctly
- L3.X — `prose_overlay_phone_color_shape` dispatch routes correctly with both args
- L3.X — `prose_overlay_phone_word` dispatch routes correctly
- L1.X — `phone_letter("a", "gray")` swaps the token at gray-a if it's flagged; no-op if not flagged
- L1.X — `phone_letter("h", "blue")` swaps the token at blue-h if it's flagged
- L3.X — `prose_overlay_phone_letter` dispatch routes correctly with and without color arg
- L1.X — `current_position_in_group("there")` returns `(1, 3)` for CSV row "their,there,they're" (0-indexed) — active is idx 1, total members 3
- L1.X — `current_position_in_group("they're")` returns `(2, 3)`
- L1.X — `current_position_in_group("your")` returns `(0, 2)` for "your,you're"
- L1.X — `current_position_in_group("not-a-homophone")` returns None
- L1.X — segment width budget: `segment_width(tw=40, gap=2, members=3)` returns `12` ((40 - 4) / 3)
- L1.X — segment width below MIN_SEGMENT_W returns the fall-back signal (e.g., 0 or sentinel) so the renderer can downgrade to solid

Live-only: the actual voice grammar match for `(phone | phones) {hat_shape}`, `<user.prose_hat_color> {user.hat_shape}`, `phones <user.homophones_canonical>`, `phones <user.letter>`, `phones <user.prose_hat_color> <user.letter>`; and the Skia canvas paint for both the expanded panel AND the segmented amber underline (segment count, active highlight, gap rendering).

## Open questions for the implementer

1. **CSV order vs alphabetical for cycling** — the spec defaults to "next member in CSV row order, wrapping." This is deterministic and matches how the CSV is read today. Alphabetical would also work; pick one explicitly so cycling is predictable across machines.

2. **Color-to-alt mapping rule** — Scenario 3 requires deterministic per-panel mapping. Default proposal: alts ordered by CSV row (excluding the current word), mapped in order to a fixed palette `[gold, blue, green, pink, red, purple, black, white, gray]`. For 2-member group with current excluded: 1 alt → gold. For 3-member with current excluded: 2 alts → gold, blue. Verify this matches the user's mental model (the worked example "gold play: their" implies `gold` is the first slot). Alternative: alphabetical order, or some other deterministic rule. Pick one explicitly and document on the panel.

3. **Word-addressed swap with multiple matches** — if two tokens in the buffer both read "there", which one does `phones there` cycle? Options: (a) first match by token index, (b) all matches simultaneously (bulk), (c) the most-recently-edited one (rev-tracked). v1 default proposal: first match by token index (simple, deterministic). Surface a TTS hint when there were multiple candidates.

4. **What about a token whose group has only one member** (degenerate 1-word CSV row)? `next_in_group(current)` returns the same word back; the panel renders empty (no alts other than current); both `phone <shape>` and `<color> <shape>` are no-ops. Test explicitly.

5. **Panel anchor and layout** — Scenario 3's worked example shows the panel below the token. Alternatives: beside (right of token), floating (overlay-level chip), inline (interspersed with tokens). Pick one and verify it doesn't break the flow layout on small buffers. The first viable shape can iterate.

6. **Hat shape list source — mouse-clock vs in-repo** — HOMOPHONE_SHAPES_PLAN.md §4.6 recommends declaring our own list in `prose_overlay.py` for decoupling. Confirm this still holds when wiring the grammar; the talon rules above show `{user.hat_shape}` (mouse-clock's list) but we can swap to `{user.prose_hat_shape}` (ours) without changing the action signature.

7. **Color grammar collision** — `<user.prose_hat_color> {user.hat_shape}` reuses the existing `prose_hat_color` capture which is also used as a hat prefix elsewhere (e.g. `chuck blue h`). Verify the new rule doesn't shadow or conflict with `chuck`-class rules in the overlay-active context. Talon's rule specificity (literal + literal vs capture + capture) should resolve cleanly, but worth a regression sweep.

8. **`prose undo` collision** — verify no existing rule binds `prose undo` (especially in trillium_talon or community). If clean, add it alongside `overlay undo` as documented in Scenario 11.

9. **`phones <word>` vs `phones <letter>` capture disambiguation** — both rules sit in the overlay-active context. When the user says `phones air`, Talon's matcher must pick between `<user.homophones_canonical>` (does "air" appear in the homophone CSV? probably not, but verify) and `<user.letter>` (yes, "air" is the NATO 'a'). For words that ARE both homophones AND NATO letter names (unlikely but possible — e.g. "you" if the alphabet includes it), the matcher's tie-break behavior determines what happens. Document the resolution rule; recommend preferring the letter capture for ambiguous cases (more specific list).

10. **`phones <letter>` on non-flagged tokens** — Scenario 6 says the action is a no-op for non-flagged letter hats. But should it instead fall through to something useful (e.g. open the modal HUD)? v1 default proposal: no-op with log hint. Iterate if real usage shows surprise.

11. **Minimum segmented-underline segment width** — Scenario 3 covers tokens where group_size is small enough that segments stay readable. For short tokens with large groups, individual segments may compute below readable thresholds. v1 proposal: fall back to solid amber underline (existing behavior) when any segment would be < 1.5 px. Alternatives: extend the underline past the token's text width, or render the highlight as a marker dot rather than a thicker bar. Pick one and document.

12. **Segmented-underline active-segment style** — "slightly highlighted" can mean: (a) taller (2.5 px vs 1.5 px), (b) brighter alpha (ff vs cc), (c) different shade (a more saturated amber), (d) outlined with a dot above. v1 proposal: taller AND brighter (both axes for clear contrast). Verify by eye that the active segment is unmistakable on the dark BG without being garish.
