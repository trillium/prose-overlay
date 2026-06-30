# Phones — Homophone Swap

> *Cycle or jump a homophone to a different group member. Four addressing paths (shape, color+shape, word, letter) so you can target whichever cue is fastest to read.*

## Voice commands

### Cycle by shape

- `phone <shape>` — swap the token wearing `<shape>` to the next CSV-row member (wraps at end)
- `phones <shape>` — same action, plural alias

Repeating the verb cycles: `phone wing` then `phone wing` again walks two steps through the group.

### Jump by color (read from the bubble panel)

- `<color> <shape>` — swap the token wearing `<shape>` directly to the alt named by the chip with that color

The bubble panel (rendered above or below the buffer) shows each shape-hatted token's alternatives as colored chips, e.g. `[gold] {bolt-glyph} [blue]` where `gold` = `there` and `blue` = `they're`. Saying `gold bolt` swaps that token to `there` directly — no cycling.

### Jump by surface word

- `phones <word>` — find the first flagged token in the buffer matching `<word>` and swap to its next group member

Useful when you can read the word but the shape glyph isn't memorable yet.

### Jump by letter hat

- `phones <letter>` — swap the token at letter hat `<letter>` (gray) to its next group member
- `phones <color> <letter>` — swap the token at colored letter hat `<color> <letter>`

No-op with a log hint if the addressed token isn't a flagged homophone.

### Undo

- `prose undo` — alias for `overlay undo`; one swap = one undo step
- `overlay undo` — same thing

## How it works

The overlay flags tokens whose lowercase form matches a row in `internal/homophones.py`'s CSV. Each flagged token wears a shape hat (see [`homophone_shapes.md`](homophone_shapes.md)). The `phones` verbs swap the flagged token to a different member of its CSV row.

Each swap is wrapped in `commit_start` / `commit_end` so the buffer mutation is **one undo step**. The letter hat at the swapped position is recomputed against the new word — if the prior letter ('r' in `they're`) still appears in the new word ('r' is at idx 4 in `their`), it's preserved at the new position.

Group identity drives the shape hat: when the swap stays within the group (which it always does — that's the whole point), the shape glyph above the token doesn't change.

## Examples

### Example 1: Cycle by shape

```
Buffer: there their they're     [all 3 tokens wear shape "bolt"]
You: phone bolt
Buffer: their their they're     [token 0 cycled to next member]
You: phone bolt
Buffer: they're their they're   [token 0 cycled again]
```

### Example 2: Jump by color via the bubble panel

```
Buffer: their thinks ball
                                [panel shows under "their":
                                 [gold|there] {bolt} [blue|they're]]
You: gold bolt
Buffer: there thinks ball       [direct jump — no cycling]
```

### Example 3: Jump by spoken word

```
Buffer: you might be their soon
You: phones their
Buffer: you might be there soon
```

### Example 4: Jump by letter hat

```
Buffer: their over there
                                [letter hats: 't' on "their", 'o' on "over", 'h' on "there"]
You: phones t
Buffer: there over there        [swapped at letter-t]
```

### Example 5: Undo a swap

```
Buffer: their
You: phones their
Buffer: there
You: prose undo
Buffer: their                   [single undo step]
```

## Caveats

- **`phones <letter>`** can drift across swaps. The letter-hat allocator may reassign the slot after a swap because the new word may not contain the prior letter. Repeated `phones <letter>` calls in a session may target different tokens. Use `phone <shape>` for muscle-memory cycling.
- **Group with only one member** (after dedup) is a no-op with a log hint — there's nothing to cycle to.
- **`phones <word>` ambiguity**: if multiple flagged tokens match the spoken word, the FIRST one (lowest token index) is swapped. Deterministic, but not always what you want — use shape or letter addressing for precision.
- **`gray <shape>` is not bound** — the bubble palette starts at `yellow` (spoken `gold`); the default chip color is the first non-gray Cursorless palette color.
- **4+ member groups** show only the first two alternatives as chips in the panel. The remaining members are reachable only via `phone <shape>` cycling.

## Source

- Actions: `shim/actions_homophones.py` — `prose_overlay_phone_shape`, `prose_overlay_phone_color_shape`, `prose_overlay_phone_word`, `prose_overlay_phone_letter`
- Grammar: `prose_overlay.talon` (overlay-active context)
- Group lookup: `internal/homophones.py` — `next_in_group`, `current_position_in_group`, `group_for_word`
- Panel mapping: `shim/shapes.py:compute_panel_alts`
- Panel render: `ui/draw_panels.py:draw_homophone_panels`
- Spec: `docs/PHONES_SPEC.md`
- ISCs: ISC-14d (PHONES_SPEC slices A, B, C all shipped)
- Related: [`homophone_shapes.md`](homophone_shapes.md), [`undo_redo.md`](undo_redo.md)
