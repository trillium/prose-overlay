# Homophone Shape Hats

> *Cursorless-style shape glyphs painted above homophone tokens (their/there/they're, your/you're, etc.) as a second hat in a parallel addressing namespace.*

## Voice commands

- `overlay shapes homo on` — enable shape painting at runtime (default ON)
- `overlay shapes homo off` — disable; shapes disappear but the underline stays

## How it works

When the overlay is active and a token's lowercase form matches the pimentel homophone CSV (their/there/they're, …), the token gets **two hats**:

1. **Default letter hat** — the normal `gray-h` style dot painted above one character. Used for `chuck`, `take`, `change`, `pre`, `post`, etc.
2. **Shape hat** — a colored Cursorless-style shape (`bolt`, `wing`, `frame`, `eye`, …) painted above a DIFFERENT character of the same token.

The two hats are **separate addressing namespaces** — the letter hat is for general edits; the shape hat will be the lookup for homophone-specific swap commands (planned: `phone <shape>` in Slice 4 of `docs/HOMOPHONE_SHAPES_PLAN.md`).

The shape position is `(letter_char_idx + 1) % len(token)` — so for `there` with letter hat on `h` (idx 1), the shape paints on `e` (idx 2). Visually: `t[h]{e}re` where `[]` is the dot and `{}` is the shape.

Slice 2 makes the shape identity **stable across edits**: once a token has been assigned `wing`, it keeps `wing` even as other tokens are inserted/deleted around it. Pool is 10 shapes (`bolt curve fox frame play wing hole ex cross eye`); on the 11th simultaneously-flagged token, the shape pool overflows and that token gets only its underline.

## Examples

### Example 1: See the shape on a homophone

Dictate a sentence with a homophone:

```
You: their over there they're are too many
       [overlay shows the tokens, each homophone has both a dot and a shape]
       [e.g. "there" displays as: t[h]{e}re — gray-h dot above 'h', colored shape above 'e']
```

The underline (amber) also paints under every flagged token regardless of shape.

### Example 2: Toggle shapes off mid-session

```
You: overlay shapes homo off
       [shapes disappear from the canvas; underline remains]
You: overlay shapes homo on
       [shapes return; same shape assignments as before (stable across toggle)]
```

### Example 3: Shape identity persists across edits

```
You: there their they're
       [3 homophone tokens, e.g. shapes: wing, bolt, frame]
You: chuck blue h
       [deletes "their" token (assuming blue-h was its letter hat)]
       [remaining tokens KEEP their shape identities — "there" still wing, "they're" still frame]
```

Shapes don't reshuffle on every edit — that's the whole point of Slice 2's allocator.

## Caveats

- **Single-character homophone tokens** (rare) can't host both hats on different chars; the shape and dot coincide. Documented as unavoidable.
- **>10 simultaneous homophones**: 11th and beyond get only the underline (no shape) until one is resolved. This is the "spillover" semantic from `docs/HOMOPHONE_SHAPES_PLAN.md §4.8`.
- **No swap action yet** — Slice 4 will add `phone <shape>` to commit a swap; today the shapes are purely visual indicators of which homophones the overlay flagged.
- **Color is currently gray** — Slice 4 introduces per-shape colors matching the cursorless palette.

## Source

- Allocator: `shim/shapes.py:compute_shape_assignments` + `shape_char_position`
- Render: `ui/draw_tokens.py` (shape paint block, separate `(cx, cy)` from the dot)
- Vocab + assets: `svg/` directory, 10 named SVGs + 1 default
- Plan: `docs/HOMOPHONE_SHAPES_PLAN.md` (Slice 1 + Slice 2 shipped; Slices 3+ in plan)
- ISC: ISC-14a (shape renderer), ISC-14b (allocator stability)
- Related: [`homophone_underline.md`](homophone_underline.md)
