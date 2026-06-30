"""Expanded homophone panel renderer — Slice C of docs/PHONES_SPEC.md.

For every shape-hatted token whose homophone group has > 1 member, paint
a **bubble** OUTSIDE the panel rect (above or below depending on the
panel's anchor position) containing:

  [color-chip-1][homophone-shape-glyph][color-chip-2]

with the homophone shape glyph re-rendered INSIDE the bubble (at reduced
scale) as a visual anchor — so the user can identify which token the
bubble belongs to.

v2 redesign (2026-06-30, PHONES_SPEC commit d535611):

  1. Bubbles sit OUTSIDE the panel rect — never on top of token content.
     Anchor-aware:
       anchor_position == "top"     → band below the panel
       anchor_position == "bottom"  → band above the panel
     The band y is a single value shared by every bubble in the draw.
     No per-row derivation from token geometry — that's what put bubbles
     INSIDE the panel in v1.

  2. SINGLE HORIZONTAL ROW — bubbles never wrap to a second band on
     collision. Adjacent bubbles shift RIGHT to clear; the rightmost
     bubble may extend past the panel's right edge and clip at the
     screen boundary. Horizontal clarity is the user's stated priority.

  3. Black circle backdrop behind the in-bubble shape glyph. The chips
     are bright Cursorless-palette colors; the amber shape glyph
     between them was hard to spot. A near-black disc behind the glyph
     gives it a consistent contrast surface against any chip color.

This replaces the v1 flat chip row (truncation + no-bubble-boundary
bugs, see PHONES_SPEC commit 566143c) and the v1.5 in-panel bubble band
(stacked-vertical + overlap-panel bugs, see d535611).

Layout (per token):

    ┌─────────────────────────┐
    │ ·^                      │ ← letter-hat dot + homophone-shape hat
    │ there                   │ ← token text inside panel
    │ ─────                   │ ← segmented amber underline (Slice A)
    └─────────────────────────┘
    [their][⬤shape][they're]   ← BUBBLE band OUTSIDE panel (single row)

For 2-member groups (e.g. `your,you're`): one chip only —
`[chip][⬤shape]`.

For 4+ member groups: only the first two alts get chips inside the
bubble. Extras are reachable via cycling (`phone <shape>`).

Reads from `instance.homophone_panel_alts` (already populated by
`shim.actions_core._recompute_hats` via `shim.shapes.compute_panel_alts`)
and `instance.shape_assignments` (the per-token shape name). When the
former is empty, this routine returns without painting.

Geometry strategy: walks the same `rows` list that `_draw_token_rows`
consumed, reconstructing each token's x position; flattens all rows'
bubbles into a single left-to-right list because the bubble band is a
single horizontal strip OUTSIDE the panel, irrespective of which
token-row a given flagged token sits on.
"""

from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ....utils.overlay_kit import draw_rounded_rect
from ..internal.draw_constants import (
    TOKEN_GAP_X, LINE_HEIGHT,
    HAT_COLOR_HEX,
    HOMOPHONE_SHAPE_COLOR_HEX,
    BUBBLE_CHIP_FONT_SIZE, BUBBLE_CHIP_PAD_X, BUBBLE_CHIP_PAD_Y,
    BUBBLE_CHIP_RADIUS, BUBBLE_INNER_GAP, BUBBLE_OUTER_GAP,
    BUBBLE_TOP_GAP, BUBBLE_SHAPE_SCALE, BUBBLE_ROW_H,
    BUBBLE_SHAPE_BACKDROP_COLOR, BUBBLE_SHAPE_BACKDROP_FACTOR,
)
from ..internal.instance import instance as _instance
from ..internal.panel_layout import place_bubbles as _place_bubbles
from ..shim import shapes as _shapes


# ---------------------------------------------------------------------------
# Geometry constants — derived
# ---------------------------------------------------------------------------

# Native SVG viewBox is 12 wide × 9 tall (mouse-clock conventions, mirrored
# in shim/shapes.py:_SVG_W / _SVG_H). When the painter draws a hat shape at
# `scale`, the glyph occupies (12*scale) × (9*scale) px centered on (cx, cy).
# We need the same numbers here to know the shape's footprint inside the
# bubble layout math. Hard-coded rather than imported because the shapes
# module guards Skia imports behind a try/except and we don't want to
# entangle the panel renderer's import time with Skia availability.
_SHAPE_NATIVE_W = 12.0
_SHAPE_NATIVE_H = 9.0


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

# Foreground text color picked per chip background. The chip background is a
# saturated Cursorless palette color; the text needs to read against it.
# Light backgrounds (yellow, white) take BLACK; the rest take WHITE.
_LIGHT_BG_COLORS = {"yellow", "white"}


def _chip_fg_for(color_name: str) -> str:
    """Return the chip foreground text color for a given background color."""
    if color_name in _LIGHT_BG_COLORS:
        return "000000ff"
    return "ffffffff"


# ---------------------------------------------------------------------------
# Bubble spec — built once per token in a measurement pass before drawing
# ---------------------------------------------------------------------------

class _Bubble:
    """One token's bubble layout spec.

    Computed by `_measure_bubble` from the panel entry + the shape name.
    Holds chip widths, shape footprint, total bubble width / height, and
    the IDEAL x (centered on the token). The placement pass mutates `x`
    and `band` to handle collisions with adjacent bubbles.
    """

    __slots__ = (
        "token_idx", "token_x", "token_w", "shape_name",
        "left_chip", "right_chip",
        "left_chip_w", "right_chip_w",
        "bubble_w", "bubble_h",
        "ideal_x", "x", "band",
    )

    def __init__(
        self,
        token_idx: int,
        token_x: float,
        token_w: float,
        shape_name: str,
        left_chip: tuple[str, str, float],
        right_chip: tuple[str, str, float] | None,
        bubble_w: float,
        bubble_h: float,
        ideal_x: float,
    ) -> None:
        self.token_idx = token_idx
        self.token_x = token_x
        self.token_w = token_w
        self.shape_name = shape_name
        self.left_chip = left_chip
        self.right_chip = right_chip
        self.left_chip_w = left_chip[2]
        self.right_chip_w = right_chip[2] if right_chip is not None else 0.0
        self.bubble_w = bubble_w
        self.bubble_h = bubble_h
        self.ideal_x = ideal_x
        self.x = ideal_x
        self.band = 0  # row offset from the primary bubble row (0, 1, 2, …)


# ---------------------------------------------------------------------------
# Public draw routine
# ---------------------------------------------------------------------------

def draw_homophone_panels(
    c: SkiaCanvas,
    rows: list[list[tuple[int, str, float]]],
    x_origin: float,
    y_start: float,
    panel_rect: Rect,
    anchor_position: str,
) -> None:
    """Paint the bubble band OUTSIDE the panel rect.

    Reads `_instance.homophone_panel_alts` (token_idx -> {color -> alt})
    and `_instance.shape_assignments` (token_idx -> shape_name). When
    `panel_alts` is empty the function returns without drawing.

    Walks the same `rows` structure that `_draw_token_rows` consumed so
    the per-token x positions match exactly. All bubbles are collected
    into a single left-to-right list and rendered at one shared y
    (`bubble_band_y`) sitting OUTSIDE the panel rect:

        anchor_position == "top"    → band sits just BELOW the panel
        anchor_position == "bottom" → band sits just ABOVE the panel

    The placement pass shifts colliding bubbles RIGHT (never wraps
    vertically and never drops a band). The rightmost bubble may extend
    past `panel_rect.right` and clip at the screen edge — the user's
    stated intent for v2 is that horizontal clarity trumps off-screen
    alts. See the "single horizontal row" note in the module docstring.
    """
    panel_alts = _instance.homophone_panel_alts
    if not panel_alts:
        return
    shape_assignments = _instance.shape_assignments or {}

    # Flatten all rows' bubbles into one left-to-right list. Token order
    # is preserved row-by-row; rows themselves are already in screen
    # order because _flow_layout walks tokens left-to-right top-to-bottom.
    all_bubbles: list[_Bubble] = []
    y_base = y_start
    for row in rows:
        all_bubbles.extend(
            _build_row_bubbles(c, row, panel_alts, shape_assignments, x_origin)
        )
        y_base += LINE_HEIGHT  # kept for symmetry / future per-row math

    if not all_bubbles:
        return

    # Bubble band y — single value for the whole draw, anchored OUTSIDE
    # the panel rect. The top-of-panel layout puts the band BELOW the
    # panel; the bottom-of-panel layout puts it ABOVE so it doesn't run
    # off screen.
    if anchor_position == "bottom":
        bubble_band_y = panel_rect.y - BUBBLE_ROW_H - BUBBLE_TOP_GAP
    else:
        # Default "top" (anchor at the top of the screen): band below.
        bubble_band_y = panel_rect.y + panel_rect.height + BUBBLE_TOP_GAP

    # Place bubbles horizontally. The talon-free helper in
    # internal/panel_layout.py mutates each bubble's `x` in place to
    # honor the OUTER_GAP separation by shifting right on collision.
    _place_bubbles(all_bubbles, x_origin, BUBBLE_OUTER_GAP)

    for b in all_bubbles:
        _draw_one_bubble(c, b, bubble_band_y)


# ---------------------------------------------------------------------------
# Measurement pass — build _Bubble specs for one row of tokens
# ---------------------------------------------------------------------------

def _build_row_bubbles(
    c: SkiaCanvas,
    row: list[tuple[int, str, float]],
    panel_alts: dict[int, dict[str, str]],
    shape_assignments: dict[int, str],
    x_origin: float,
) -> list[_Bubble]:
    """Walk a single row, measure each panel entry's bubble, return specs.

    Tokens without panel entries are skipped silently. Tokens whose entry
    is in `panel_alts` but lack a shape assignment also skipped — the
    bubble's central anchor is the shape glyph, and a missing shape would
    leave a confusing chip-pair with no glyph between them.

    Bubble ideal_x is set ABSOLUTE (already includes `x_origin`) so the
    placement helper in internal/panel_layout.py can be called directly
    without an extra translation pass.
    """
    bubbles: list[_Bubble] = []
    x = x_origin  # absolute x of the current token's left edge
    for idx, _token, tw in row:
        entry = panel_alts.get(idx)
        shape_name = shape_assignments.get(idx)
        if entry and shape_name is not None:
            bubble = _measure_bubble(c, idx, x, tw, shape_name, entry)
            if bubble is not None:
                bubbles.append(bubble)
        x += tw + TOKEN_GAP_X
    return bubbles


def _measure_bubble(
    c: SkiaCanvas,
    token_idx: int,
    token_x_abs: float,
    token_w: float,
    shape_name: str,
    entry: dict[str, str],
) -> _Bubble | None:
    """Measure one token's bubble dimensions; return a _Bubble or None.

    Picks the first two color-alt pairs from `entry` (the entry is keyed
    in PANEL_COLOR_PALETTE order — yellow first, blue second — per the
    OQ2 convention enforced by `shim/shapes.py:compute_panel_alts`).

    For 2-member groups (only one alt available) renders [chip][shape]
    with no right chip. For 4+ member groups, the extra alts beyond the
    second slot are dropped — the spec routes them to cycling, not
    additional chips.

    Returns None when `entry` is empty (defensive — shouldn't happen
    because `compute_panel_alts` only writes non-empty mappings, but the
    nil-check keeps the caller simple).
    """
    if not entry:
        return None

    # Pull (color, alt) pairs in insertion order. The mapping was built by
    # compute_panel_alts iterating PANEL_COLOR_PALETTE in CSV-row order,
    # so the first two items are yellow + blue for the worked example.
    pairs = list(entry.items())
    if not pairs:
        return None

    # Measure each chip's text using the chip's font size (NOT the token
    # font). Skia's measure_text returns (rect_w, glyph_bounds); the
    # glyph_bounds.width is what we want for tight packing.
    c.paint.textsize = BUBBLE_CHIP_FONT_SIZE
    left_color, left_alt = pairs[0]
    left_text_w = c.paint.measure_text(left_alt)[1].width
    left_chip_w = left_text_w + BUBBLE_CHIP_PAD_X * 2
    left_chip = (left_color, left_alt, left_chip_w)

    right_chip: tuple[str, str, float] | None = None
    right_chip_w = 0.0
    if len(pairs) >= 2:
        right_color, right_alt = pairs[1]
        right_text_w = c.paint.measure_text(right_alt)[1].width
        right_chip_w = right_text_w + BUBBLE_CHIP_PAD_X * 2
        right_chip = (right_color, right_alt, right_chip_w)

    # Shape footprint at BUBBLE_SHAPE_SCALE.
    shape_w = _SHAPE_NATIVE_W * BUBBLE_SHAPE_SCALE
    shape_h = _SHAPE_NATIVE_H * BUBBLE_SHAPE_SCALE

    # Bubble width: [left_chip][gap][shape][gap][right_chip], or
    # [left_chip][gap][shape] for the 2-member case.
    if right_chip is not None:
        bubble_w = (
            left_chip_w + BUBBLE_INNER_GAP + shape_w
            + BUBBLE_INNER_GAP + right_chip_w
        )
    else:
        bubble_w = left_chip_w + BUBBLE_INNER_GAP + shape_w

    # Bubble height: chip height (chips are the tallest element; the
    # shape at scale 0.55 is ~5 px tall, smaller than a chip).
    chip_h = BUBBLE_CHIP_FONT_SIZE + BUBBLE_CHIP_PAD_Y * 2
    bubble_h = max(chip_h, shape_h)

    # Ideal x: bubble centered on the token. ABSOLUTE — caller already
    # passed `token_x_abs` including x_origin, so the placement helper
    # can consume `ideal_x` directly.
    ideal_x = token_x_abs + (token_w - bubble_w) / 2.0

    return _Bubble(
        token_idx=token_idx,
        token_x=token_x_abs,
        token_w=token_w,
        shape_name=shape_name,
        left_chip=left_chip,
        right_chip=right_chip,
        bubble_w=bubble_w,
        bubble_h=bubble_h,
        ideal_x=ideal_x,
    )


# ---------------------------------------------------------------------------
# Draw pass — paint one bubble
# ---------------------------------------------------------------------------

def _draw_one_bubble(c: SkiaCanvas, b: _Bubble, y_top: float) -> None:
    """Render one bubble at `(b.x, y_top)`.

    Paint order (back-to-front, so the shape sits ON TOP of BOTH chips):
      1. Left chip (color background, alt text on top)
      2. Right chip (when present; 3-member or 4+ groups)
      3. Homophone shape glyph + black backdrop disc — last so the disc
         covers any chip edge that overlaps the shape footprint. With
         BUBBLE_INNER_GAP=0 the chips are flush against the shape's
         horizontal span; with a backdrop scale > 1 the disc clearly
         overhangs into both chips and reads as "shape in front."
    """
    shape_w = _SHAPE_NATIVE_W * BUBBLE_SHAPE_SCALE
    # shape_h is implicit: shapes.draw_hat_shape centers the glyph on (cx, cy),
    # so we only need shape_w for horizontal layout and chip_mid_y for the
    # vertical anchor. The actual painted height comes from the scaled SVG.
    chip_h = BUBBLE_CHIP_FONT_SIZE + BUBBLE_CHIP_PAD_Y * 2

    # Chip vertical center across the bubble. The shape paints centered on
    # its own (cx, cy); the chips align top so their bounding box matches
    # the chip_h footprint. We anchor chips at y_top and center the shape
    # vertically on chip's mid-line so chips + shape read as one unit.
    chip_y = y_top + (b.bubble_h - chip_h) / 2.0
    chip_mid_y = chip_y + chip_h / 2.0

    # ----- Left chip --------------------------------------------------------
    left_color, left_alt, left_chip_w = b.left_chip
    left_x = b.x
    _draw_chip(c, left_color, left_alt, left_x, chip_y, left_chip_w, chip_h)

    # ----- Right chip (when present) — painted BEFORE the shape so the -----
    # ----- shape's backdrop disc lands on top of the chip's edge. ----------
    shape_x_left = left_x + left_chip_w + BUBBLE_INNER_GAP
    if b.right_chip is not None:
        right_color, right_alt, right_chip_w = b.right_chip
        right_x = shape_x_left + shape_w + BUBBLE_INNER_GAP
        _draw_chip(c, right_color, right_alt, right_x, chip_y, right_chip_w, chip_h)

    # ----- Shape glyph (with backdrop) — LAST so it sits on top of both chips
    shape_cx = shape_x_left + shape_w / 2.0
    shape_cy = chip_mid_y
    _draw_shape_with_backdrop(
        c, shape_name=b.shape_name, cx=shape_cx, cy=shape_cy,
    )


def _draw_shape_with_backdrop(
    c: SkiaCanvas,
    shape_name: str,
    cx: float,
    cy: float,
) -> None:
    """Paint a black disc THEN the homophone shape glyph on top.

    v2 redesign per PHONES_SPEC commit d535611. The chips on either
    side of the shape are bright Cursorless-palette colors (yellow,
    blue, green, …); the amber shape glyph between them was hard to
    spot against any of those backgrounds. A near-black backdrop
    circle (BUBBLE_SHAPE_BACKDROP_COLOR — slightly transparent so it
    doesn't punch a visual hole) gives the glyph a consistent contrast
    surface.

    Backdrop sizing: BUBBLE_SHAPE_BACKDROP_FACTOR scales the circle
    radius relative to the shape's own native radius (_SVG_W *
    BUBBLE_SHAPE_SCALE / 2). The factor lives in
    internal/draw_constants.py so it can be tuned by eye without
    touching this file.

    Kept separate from `shim/shapes.py:draw_hat_shape` (Option B in
    the spec) so the shape painter stays focused on its single
    responsibility — the backdrop is a panel-render concern, not a
    shape-vocabulary concern.
    """
    # Shape native radius at the bubble's scale. Use _SVG_W (the wider
    # of the two viewBox dimensions) so the disc encloses the glyph's
    # widest extent.
    shape_radius = _SHAPE_NATIVE_W * BUBBLE_SHAPE_SCALE / 2.0
    backdrop_radius = shape_radius * BUBBLE_SHAPE_BACKDROP_FACTOR

    # Backdrop disc — filled, no stroke. Save/restore paint state so
    # this routine is composable: it doesn't matter what style/color
    # the caller had set before.
    prev_style = c.paint.style
    prev_color = c.paint.color
    c.paint.style = c.paint.Style.FILL
    c.paint.color = BUBBLE_SHAPE_BACKDROP_COLOR
    c.draw_circle(cx, cy, backdrop_radius)
    c.paint.style = prev_style
    c.paint.color = prev_color

    # Shape glyph on top.
    _shapes.draw_hat_shape(
        c,
        shape_name=shape_name,
        color=HOMOPHONE_SHAPE_COLOR_HEX,
        cx=cx,
        cy=cy,
        scale=BUBBLE_SHAPE_SCALE,
        alpha=255,
    )


def _draw_chip(
    c: SkiaCanvas,
    color_name: str,
    text: str,
    x: float,
    y: float,
    chip_w: float,
    chip_h: float,
) -> None:
    """Paint one chip: rounded-rect background + alt text on top.

    Uses HAT_COLOR_HEX for the background lookup (same palette as the
    letter-hat dot) so color-addressed swap reads consistently — the
    user's `gold play` lands on the alt under the gold/yellow chip.
    """
    bg_color = HAT_COLOR_HEX.get(color_name, "999999ff")
    fg_color = _chip_fg_for(color_name)

    # Background fill.
    c.paint.style = c.paint.Style.FILL
    c.paint.color = bg_color
    draw_rounded_rect(c, Rect(x, y, chip_w, chip_h), BUBBLE_CHIP_RADIUS)

    # Text. Baseline = y + chip_pad_y + font_size (font_size approximates
    # the cap height for small fonts; pad_y sits above and the baseline
    # falls one font-size below the padded top edge).
    c.paint.textsize = BUBBLE_CHIP_FONT_SIZE
    c.paint.color = fg_color
    c.draw_text(text, x + BUBBLE_CHIP_PAD_X, y + BUBBLE_CHIP_PAD_Y + BUBBLE_CHIP_FONT_SIZE)
