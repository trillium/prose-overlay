# Homophone Shape Hats

> *Cursorless-style shape glyphs painted above homophone tokens (their/there/they're, your/you're, etc.) as a parallel addressing namespace. Same group = same shape, so the glyph identifies the group at a glance.*

## Voice commands

- `overlay shapes homo on` — enable shape painting at runtime
- `overlay shapes homo off` — disable; shapes disappear but the underline stays

Shapes are an opt-in toggle. The setting `user.prose_overlay_homophone_shapes` controls the default at Talon launch; the runtime toggles above override per-session.

## How it works

When the overlay is active and a token's lowercase form matches the homophone CSV (their/there/they're, your/you're, …), the token gets **two hats**:

1. **Default letter hat** — the normal `gray-h` style dot painted above one character. Used for `chuck`, `take`, `change`, `pre`, `post`, etc.
2. **Shape hat** — a colored Cursorless-style shape (`bolt`, `wing`, `frame`, `eye`, …) painted above a DIFFERENT character of the same token.

The two hats are **separate addressing namespaces** — the letter hat is for general edits; the shape hat is the lookup for homophone-specific swap commands (see [`phones.md`](phones.md)).

The shape position is `(letter_char_idx + 1) % len(token)` — so for `there` with letter hat on `h` (idx 1), the shape paints on `e` (idx 2). Visually: `t[h]{e}re` where `[]` is the dot and `{}` is the shape.

### Same group, same shape (ISC-14c)

Every token that belongs to the same homophone GROUP wears the same shape. If your buffer says `there their they're` — all three are in the `there/their/they're` CSV row — they all get (for example) `bolt`. The user learns the group by its glyph instead of tracking per-occurrence randomness.

The 10-shape pool (`bolt curve fox frame play wing hole ex cross eye`) now bounds the number of distinct **groups** visible in one buffer, not the number of flagged tokens. A buffer with 11 occurrences of `there` uses 1 shape (all `bolt`); a buffer with 11 distinct groups overflows at the 11th group (its tokens fall back to underline-only).

### Shape stability across edits

A group's shape stays put when you edit the buffer. Once the `there/their/they're` group has been assigned `wing`, it keeps `wing` even as other tokens are inserted, deleted, or swapped around it. This is ISC-14b carried through to the per-group allocator: prior assignments are harvested as `(group → shape)` and replayed on the next allocator run.

## Examples

### Example 1: See the group glyphs

Dictate a sentence with mixed homophones:

```
You: their over there they're are too many
       [overlay paints — "their", "there", "they're" all wear the SAME shape
        because they're the same group. "are", "too" wear different shapes
        because they're different groups.]
```

The amber underline also paints under every flagged token regardless of shape.

### Example 2: Group glyph survives a swap

```
You: there their they're
       [3 homophone tokens, all wearing shape "bolt" because they're one group]
You: phones risk
       ["their" (letter hat on 'r') swaps to "they're" — buffer is now
        "there they're they're"; ALL three tokens still wear "bolt"
        because they're still the same group.]
```

The shape identity is the group's identity, not the token's.

### Example 3: Toggle shapes off mid-session

```
You: overlay shapes homo off
       [shapes disappear from the canvas; underline remains]
You: overlay shapes homo on
       [shapes return; same group → shape assignments as before]
```

## Caveats

- **Single-character homophone tokens** (rare) can't host both hats on different chars; the shape and dot coincide. Documented as unavoidable.
- **>10 distinct groups in one buffer**: the 11th group's tokens get only the underline (no shape) until one of the other groups disappears. This is the "spillover" semantic from `docs/HOMOPHONE_SHAPES_PLAN.md §4.8`.
- **Shape color** is amber by default. The bubble panel ([`phones.md`](phones.md)) uses Cursorless palette colors for the alt chips alongside the shape; the shape itself stays amber.

## Source

- Allocator: `shim/shapes.py:compute_shape_assignments` (per-group)
- Group lookup: `internal/homophones.py:group_id_for_word`
- Position: `shim/shapes.py:shape_char_position`
- Render: `ui/draw_tokens.py` (shape paint block, separate `(cx, cy)` from the dot)
- Vocab + assets: `svg/` directory, 10 named SVGs + 1 default
- Plan: `docs/HOMOPHONE_SHAPES_PLAN.md` (Slices 1, 2, 3 shipped)
- ISCs: ISC-14a (renderer), ISC-14b (per-token stability), ISC-14c (per-group allocation)
- Related: [`phones.md`](phones.md) for the swap actions that target these shapes
