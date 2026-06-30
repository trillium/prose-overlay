"""Expanded homophone panel renderer — Slice C of docs/PHONES_SPEC.md.

For every shape-hatted token whose homophone group has > 1 member, paint
a **bubble** BELOW the token containing:

  [color-chip-1][homophone-shape-glyph][color-chip-2]

with the homophone shape glyph re-rendered INSIDE the bubble (at reduced
scale) as a visual anchor — so the user can identify which token the
bubble belongs to even when adjacent bubbles wrap to a second row.

This replaces the original flat chip row that packed under each token.
The original layout had two bugs the user reported in the first-paint
verdict (PHONES_SPEC.md commit 566143c):

  1. Truncation — chips were sized to fit under the token's width, not
     the chip's text content, so "they're" rendered as "t".
  2. No bubble boundary — adjacent tokens' chips visually ran together;
     the user could not tell which alt belonged to which token.

Layout (per token):

    ·^                       ← letter-hat dot + homophone-shape hat (above)
    there                    ← token text
    ─────                    ← segmented amber underline (Slice A)
    [their][shape][they're]  ← BUBBLE: chip + small shape glyph + chip

For 2-member groups (e.g. `your,you're`): one chip only —
`[chip][shape]`.

For 4+ member groups: only the first two alts get chips inside the
bubble. Extras are reachable via cycling (`phone <shape>`) per the spec
Non-goal "first two alts; extras via cycling."

Bubble x = `token_x + (token_w - bubble_w) / 2` — centered on the token.
Bubble y = `underline_y + BUBBLE_TOP_GAP`.

When two adjacent bubbles' ideal positions would overlap (closer than
`BUBBLE_OUTER_GAP`), the right-hand bubble shifts DOWN one row instead
of being squeezed horizontally — preserves chip sizing and stays
visually identifiable.

Reads from `instance.homophone_panel_alts` (already populated by
`shim.actions_core._recompute_hats` via `shim.shapes.compute_panel_alts`)
and `instance.shape_assignments` (the per-token shape name). When the
former is empty, this routine returns without painting.

Geometry strategy: walks the same `rows` list that `_draw_token_rows`
consumed, reconstructing each token's x position. The two paint passes
share the layout INPUT (the rows list) — no live state coupling.
"""

from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ....utils.overlay_kit import draw_rounded_rect
from ..internal.draw_constants import (
    DOT_RADIUS, DOT_GAP_Y, TOKEN_FONT_SIZE, TOKEN_GAP_X, LINE_HEIGHT,
    HAT_COLOR_HEX,
    HOMOPHONE_SHAPE_COLOR_HEX,
    BUBBLE_CHIP_FONT_SIZE, BUBBLE_CHIP_PAD_X, BUBBLE_CHIP_PAD_Y,
    BUBBLE_CHIP_RADIUS, BUBBLE_INNER_GAP, BUBBLE_OUTER_GAP,
    BUBBLE_TOP_GAP, BUBBLE_SHAPE_SCALE,
)
from ..internal.instance import instance as _instance
from ..internal.panel_layout import place_bubbles as _place_bubbles
from ..shim import shapes as _shapes


# ---------------------------------------------------------------------------
# Geometry constants — derived
# ---------------------------------------------------------------------------

# Reserve a few pixels for the segmented underline + active-segment height.
# Mirrors the calculation in ui/draw_tokens.py where the underline lives at
# `y_base + (DOT_RADIUS * 2) + DOT_GAP_Y + TOKEN_FONT_SIZE + 2`. We add a
# fixed UNDERLINE_RESERVE on top of that to clear the active segment's
# extra height (HOMOPHONE_UNDERLINE_ACTIVE_HEIGHT can extend down to ~3px).
UNDERLINE_RESERVE = 4

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
) -> None:
    """Paint the bubble panel beneath each shape-hatted token.

    Reads `_instance.homophone_panel_alts` (token_idx -> {color -> alt})
    and `_instance.shape_assignments` (token_idx -> shape_name). When
    `panel_alts` is empty the function returns without drawing.

    Walks the same `rows` structure that `_draw_token_rows` consumed so
    the per-token x positions match exactly. For each row, runs a
    measurement pass (build _Bubble specs) followed by a placement pass
    (assign bands so collisions wrap downward) and a draw pass.
    """
    panel_alts = _instance.homophone_panel_alts
    if not panel_alts:
        return
    shape_assignments = _instance.shape_assignments or {}

    y_base = y_start
    for row in rows:
        bubbles = _build_row_bubbles(
            c, row, panel_alts, shape_assignments, x_origin
        )
        # Delegate the band-assignment math to the talon-free helper in
        # internal/panel_layout.py so the placement contract has a single
        # source of truth and the L1 headless tests can exercise it
        # without importing Skia. _place_bubbles mutates each bubble in
        # place, writing `x` and `band`.
        _place_bubbles(bubbles, x_origin, BUBBLE_OUTER_GAP)
        # Underline_y_base mirrors ui/draw_tokens.py's underline math: the
        # underline sits at `y_base + (DOT_RADIUS * 2) + DOT_GAP_Y +
        # TOKEN_FONT_SIZE + 2`. We then add UNDERLINE_RESERVE (to clear
        # the active segment's extra height) and BUBBLE_TOP_GAP for the
        # visual breathing room called for in the spec.
        underline_y_base = (
            y_base + (DOT_RADIUS * 2) + DOT_GAP_Y + TOKEN_FONT_SIZE + 2
        )
        bubble_top_band_0 = (
            underline_y_base + UNDERLINE_RESERVE + BUBBLE_TOP_GAP
        )
        for b in bubbles:
            band_y = bubble_top_band_0 + b.band * (b.bubble_h + BUBBLE_TOP_GAP)
            _draw_one_bubble(c, b, band_y)
        y_base += LINE_HEIGHT


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

    Pieces, left to right:
      1. Left chip (color background, alt text on top)
      2. Homophone shape glyph (small, amber, centered between gaps)
      3. Right chip (when present; 3-member or 4+ groups)
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

    # ----- Shape glyph ------------------------------------------------------
    shape_x_left = left_x + left_chip_w + BUBBLE_INNER_GAP
    shape_cx = shape_x_left + shape_w / 2.0
    shape_cy = chip_mid_y
    _shapes.draw_hat_shape(
        c,
        shape_name=b.shape_name,
        color=HOMOPHONE_SHAPE_COLOR_HEX,
        cx=shape_cx,
        cy=shape_cy,
        scale=BUBBLE_SHAPE_SCALE,
        alpha=255,
    )

    # ----- Right chip (when present) ---------------------------------------
    if b.right_chip is not None:
        right_color, right_alt, right_chip_w = b.right_chip
        right_x = shape_x_left + shape_w + BUBBLE_INNER_GAP
        _draw_chip(c, right_color, right_alt, right_x, chip_y, right_chip_w, chip_h)


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
