Shape SVGs adapted from sibling project trillium/mouse-clock (MIT, same author).
Shape-name vocabulary (bolt, frame, eye, ...) follows Cursorless's hat-shape
conventions for voice compatibility.

Files:
- `bolt.svg`, `curve.svg`, `crosshairs.svg`, `default.svg`, `ex.svg`, `eye.svg`,
  `fox.svg`, `frame.svg`, `hole.svg`, `play.svg`, `wing.svg`

All shapes use `viewBox="0 0 12 9"` with a single `<path d="...">` per file. The
canonical Cursorless hat-shape "cross" maps to filename `crosshairs.svg` per
upstream `HAT_NAMES` (mouse-clock `src/core/constants.py:95`). The "default"
file is the dot shape — present for completeness but NOT used by Slice 1 of
the homophone-shapes overlay (the existing letter-hat dot already covers the
dot slot).

Used by `prose_overlay_shapes.py` for the Slice 1 homophone hat-shape paint
(docs/HOMOPHONE_SHAPES_PLAN.md §3).
