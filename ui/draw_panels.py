"""Expanded homophone panel renderer — Slice C of docs/PHONES_SPEC.md.

For every shape-hatted token whose homophone group has > 1 member, paint
a small panel BELOW the token with one chip per alt member. Each chip's
background is the Cursorless palette color that addresses that alt; the
chip's foreground text is the alt word itself. The user can then say
`<color> <shape>` to swap directly to that alt (Scenario 4).

Layout (default per OQ5 — "below" the token):

    t[h]{e}re               <- the token, with letter hat + shape hat
    [ their ] [ they're ]   <- the panel chips, below
       gold      blue

The panel reads from `instance.homophone_panel_alts` (populated by
`shim.actions_core._recompute_hats` from `shim.shapes.compute_panel_alts`).
When the dict is empty, this routine paints nothing — zero overhead when
shapes are off or no flagged token has > 1 member.

Geometry strategy: walk the same `rows` list that `_draw_token_rows` used,
reconstructing each token's x/y/tw. We don't share live state with the
token renderer — the two paint passes share the layout INPUT (the rows
list) and recompute identical x positions. This keeps the modules
loosely coupled and headless-test friendly.
"""

from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ....utils.overlay_kit import draw_rounded_rect
from ..internal.draw_constants import (
    DOT_RADIUS, DOT_GAP_Y, TOKEN_FONT_SIZE, TOKEN_GAP_X, LINE_HEIGHT,
    HAT_COLOR_HEX,
)
from ..internal.instance import instance as _instance


# ---------------------------------------------------------------------------
# Constants — geometry of the panel + chips
# ---------------------------------------------------------------------------

# Panel sits below the token's underline, with this much vertical gap.
# Underline lives ~2 px below the token text bottom, so the chip top is
# token_text_bottom + UNDERLINE_RESERVE + PANEL_GAP_Y.
PANEL_GAP_Y = 4
UNDERLINE_RESERVE = 4  # px reserved for the segmented underline

# Per-chip geometry. Chips are sized to fit their alt word plus padding.
CHIP_PAD_X = 4         # px horizontal padding inside a chip
CHIP_PAD_Y = 2         # px vertical padding inside a chip
CHIP_RADIUS = 2        # px corner radius
CHIP_GAP_X = 3         # px horizontal gap between adjacent chips on the same panel
CHIP_FONT_SIZE = 10    # px — smaller than the token font so the panel is unmistakably
                       # a secondary UI element, not another token row.

# Foreground text colors per background color. The chip background is a
# saturated Cursorless palette color; the text needs to read against it.
# We pick BLACK for light backgrounds (yellow, white) and WHITE for the
# rest. Matches the existing HAT_COLOR_HEX black-circle-on-white-ring
# treatment used by the letter hat dot.
_LIGHT_BG_COLORS = {"yellow", "white"}


def _chip_fg_for(color_name: str) -> str:
    """Return the chip foreground text color for a given background color."""
    if color_name in _LIGHT_BG_COLORS:
        return "000000ff"
    return "ffffffff"


# ---------------------------------------------------------------------------
# Public draw routine
# ---------------------------------------------------------------------------

def draw_homophone_panels(
    c: SkiaCanvas,
    rows: list[list[tuple[int, str, float]]],
    x_origin: float,
    y_start: float,
) -> None:
    """Paint the expanded homophone panel beneath each shape-hatted token.

    Reads `_instance.homophone_panel_alts` (token_idx -> {color -> alt}).
    When the dict is empty, the function returns without drawing anything.

    Walks the same `rows` structure that `_draw_token_rows` consumed so
    the per-token x positions match exactly. The vertical offset to the
    chip row matches the underline_y in draw_tokens plus a small gap.
    """
    panel_alts = _instance.homophone_panel_alts
    if not panel_alts:
        return

    y_base = y_start
    for row in rows:
        x = x_origin
        for idx, token, tw in row:
            entry = panel_alts.get(idx)
            if not entry:
                x += tw + TOKEN_GAP_X
                continue
            _draw_one_panel(c, entry, x, y_base, tw)
            x += tw + TOKEN_GAP_X
        y_base += LINE_HEIGHT


def _draw_one_panel(
    c: SkiaCanvas,
    entry: dict[str, str],
    token_x: float,
    y_base: float,
    tw: float,
) -> None:
    """Paint one token's panel as a row of color-coded chips.

    Chips are positioned left-aligned with the token. They flow
    horizontally; if they overflow the token's width budget, they still
    paint — the overflow is acceptable since panels are an addressing
    affordance, not a strict layout obligation. The first viable shape
    can iterate (OQ5).
    """
    # Measure each chip's text to determine widths.
    c.paint.textsize = CHIP_FONT_SIZE
    chips: list[tuple[str, str, float]] = []  # (color, alt, text_w)
    for color, alt in entry.items():
        text_w = c.paint.measure_text(alt)[1].width
        chips.append((color, alt, text_w))

    # Anchor chip row top below the underline.
    underline_bottom = y_base + (DOT_RADIUS * 2) + DOT_GAP_Y + TOKEN_FONT_SIZE + UNDERLINE_RESERVE
    chip_top = underline_bottom + PANEL_GAP_Y
    chip_h = CHIP_FONT_SIZE + CHIP_PAD_Y * 2

    chip_x = token_x
    for color, alt, text_w in chips:
        chip_w = text_w + CHIP_PAD_X * 2
        bg_color = HAT_COLOR_HEX.get(color, "999999ff")
        fg_color = _chip_fg_for(color)

        # Chip background.
        c.paint.style = c.paint.Style.FILL
        c.paint.color = bg_color
        draw_rounded_rect(
            c,
            Rect(chip_x, chip_top, chip_w, chip_h),
            CHIP_RADIUS,
        )

        # Chip foreground (the alt word).
        c.paint.textsize = CHIP_FONT_SIZE
        c.paint.color = fg_color
        # Baseline: chip_top + CHIP_PAD_Y + font_size (text draws above
        # baseline; the +font_size shifts the baseline to the bottom of
        # the text area).
        c.draw_text(alt, chip_x + CHIP_PAD_X, chip_top + CHIP_PAD_Y + CHIP_FONT_SIZE)

        chip_x += chip_w + CHIP_GAP_X
