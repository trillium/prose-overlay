# Cursorless Hat-Shape Implementation — Location Report

## 1. Verdict

The shape vocabulary lives in the **`mouse-clock`** Talon plugin at
`/Users/trilliumsmith/.talon/user/trillium/mouse-clock/src/`. Authoritative pieces:
SVG assets in `src/svg/*.svg`, parser in `src/rendering/svg_loader.py`,
renderer in `src/features/clock_letters/shapes.py`, registry/spoken-form map
in `src/core/constants.py`, voice list at `src/hat_shape.talon-list`.
This repo (`prose-overlay`) has no shape code — confirmed via grep.

## 2. Architecture at a glance

- **Storage:** Shapes are static SVG files (`viewBox="0 0 12 9"`) with one `<path d=...>`
  per file. `default.svg` (= "dot") plus 10 named shapes. Parsed once with
  `xml.etree.ElementTree`, then converted to `talon.skia.Path` via `Path.from_svg(d)`
  and cached at module level. `fill-rule="evenodd"` is honored
  (`p.fill_type = Path.FillType.EVENODD`).
- **Render API:**
  `draw_shape_icons(canvas, colors, letters, column_types, col_positions, row_positions, elem_alpha)`
  — `shapes.py:39`. Loops every shape × every (row, color-column), `canvas.save();
  translate(); scale(); paint.color = fill; draw_path(path); paint.style = STROKE;
  draw_path(path); restore()`. Lower-level single-shape rendering also appears
  inline in `clock_ring.py:127-141` and `hats_info.py:74-89`.
- **Spoken-form mapping:** `HAT_NAMES` dict in `core/constants.py:95-107` maps
  SVG-filename stem → spoken form (e.g. `crosshairs` → `cross`, `default` → `dot`).
  `mod.list("hat_shape", ...)` declared in `clock_ring.py:19`; entries supplied
  by `hat_shape.talon-list`. `@mod.capture(rule="{user.hat_shape}")` at
  `clock_ring.py:189-192` returns the string. A separate `row_shape` list
  (`talon_integration/row_shape.talon-list`, declared in
  `talon_integration/actions.py:20`) drops `dot` and `cross` — used as a
  sub-row positional modifier.
- **Color compositing:** Two-pass draw — FILL in the column's hex (via
  `rendering/colors.get_color()` → `COLOR_REGISTRY`), then a thin STROKE
  outline (`stroke_width=0.5` in `shapes.py`, `0.4` in `clock_ring.py`) in
  black (or white on dark fills) for readability. Alpha is composited through
  `features/shared/alpha.apply_alpha(color_hex, alpha=...)` which multiplies
  existing alpha by the fade value.

## 3. The shape vocabulary

From `core/constants.py:95-107` (filename → spoken form):

| SVG file | Spoken form |
|---|---|
| `bolt.svg` | `bolt` |
| `crosshairs.svg` | `cross` |
| `curve.svg` | `curve` |
| `default.svg` | `dot` |
| `ex.svg` | `ex` |
| `eye.svg` | `eye` |
| `fox.svg` | `fox` |
| `frame.svg` | `frame` |
| `hole.svg` | `hole` |
| `play.svg` | `play` |
| `wing.svg` | `wing` |

11 shapes total (matches `src/svg/` listing). No `play`/`bolt`/`curve`/`hole` synonyms.

## 4. Key files & line ranges

```
mouse-clock/src/svg/*.svg                                 — 11 shape assets (viewBox 0 0 12 9)
mouse-clock/src/core/constants.py:81-109                  — SHAPE_ROW_OFFSETS, HAT_NAMES, HAT_SHAPES, HAT_SHAPE_LIST
mouse-clock/src/rendering/svg_loader.py:1-78              — _parse_svg_entries / load_svg_paths (cached)
mouse-clock/src/rendering/colors.py:1-78                  — get_color, with_alpha, parse_hex_color, luminance
mouse-clock/src/features/shared/alpha.py:1-46             — apply_alpha (fade compositing)
mouse-clock/src/features/clock_letters/shapes.py:1-127    — draw_shape_icons + _get_shape_path_cache (the reusable renderer)
mouse-clock/src/features/clock_letters/render.py:223-230  — call site for draw_shape_icons in the clock-letters draw pass
mouse-clock/src/clock_ring.py:53-145                      — radial pie-chart of shapes around cursor (inline render)
mouse-clock/src/hats_info.py:18-102                       — grid info panel of every (color, shape) pair (inline render)
mouse-clock/src/circle_info_draw.py:89-117                — circle-info game/learn dispatcher (uses load_svg_paths)
mouse-clock/src/circle_info_draw_learn.py / _game.py      — variant renderers (also call load_svg_paths)
mouse-clock/src/hat_shape.talon-list                      — voice grammar: list user.hat_shape (11 entries)
mouse-clock/src/talon_integration/row_shape.talon-list    — voice grammar: list user.row_shape (9 entries, no dot/cross)
mouse-clock/src/clock_ring.py:19,189-192                  — mod.list("hat_shape") + @mod.capture(rule="{user.hat_shape}")
mouse-clock/src/talon_integration/actions.py:20-24        — mod.list("row_shape") declaration
```

No standalone `.talon` file consumes `hat_shape` directly in `mouse-clock/src/*.talon` —
captures are used programmatically inside Python action classes.

## 5. What's reusable vs. mouse-clock-specific

**Reusable (drop straight into prose-overlay):**
- `src/svg/*.svg` — pure assets, no Talon deps.
- `src/rendering/svg_loader.py` — only deps are `os`, `xml.etree`, and
  `core.constants.HAT_NAMES`. Lift HAT_NAMES with it.
- `src/features/clock_letters/shapes.py:_get_shape_path_cache` — pure
  `talon.skia.Path` work; trivial to extract.
- `src/rendering/colors.py` + `src/features/shared/alpha.py` — small,
  framework-free hex/alpha utilities.
- The two-pass FILL+STROKE compositing pattern (12 lines, `shapes.py:114-126`).

**mouse-clock specific (don't import wholesale):**
- `draw_shape_icons` signature is shaped around the clock-letters grid
  (`colors`/`letters`/`column_types`/`col_positions`/`row_positions` +
  `elem_alpha` sampler). Each loop iteration assumes "one shape × all rows ×
  all columns" — a per-token overlay wants the inverse (one shape × one
  position).
- `SHAPE_ROW_OFFSETS` is a ladder-positioning concept (sub-row vertical
  bands) that only makes sense inside the clock-letters grid; ignore for
  prose-overlay.
- `clock_ring.py` and `hats_info.py` render-loops are tightly coupled to
  `ctrl.mouse_pos()` and `Canvas.from_screen(screen)` — useful as reference
  patterns, not as importable functions.

**Adaptation notes for prose-overlay's flow layout:**
- Want one helper like `draw_hat(canvas, shape_name, color_name, cx, cy, scale=0.75, alpha=255)`.
- Reuse `_get_shape_path_cache` + `get_color` + `apply_alpha` verbatim.
- Replace the `for row × col` nesting with a single `save/translate/scale/draw_path×2/restore`.
- SVG viewBox is 12×9; at `scale=0.75` the icon is 9×6.75 px — line-height should
  reserve ~10-12 px above each token if shapes render above-the-line.
- No mouse-position dependency once you compute `(cx, cy)` from your layout.

## 6. Reproduction recipe

```python
from talon.skia import Path, Paint
# mouse-clock helpers — adapt import paths once lifted:
from mouse_clock.rendering.svg_loader import load_svg_paths

# Build cache once (e.g. at module load):
_paths = {name: Path.from_svg(d) for name, d, _ in load_svg_paths()}

# Render "red wing" centered at (cx, cy) on a Skia canvas inside on_draw():
SCALE = 0.75
canvas.save()
canvas.translate(cx - 12 * SCALE / 2, cy - 9 * SCALE / 2)
canvas.scale(SCALE, SCALE)
canvas.paint.style = Paint.Style.FILL;   canvas.paint.color = "e02d28ff"  # red
canvas.draw_path(_paths["wing"])
canvas.paint.style = Paint.Style.STROKE; canvas.paint.stroke_width = 0.5
canvas.paint.color = "000000ff"
canvas.draw_path(_paths["wing"])
canvas.restore()
```
