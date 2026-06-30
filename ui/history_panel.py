"""Prose Overlay History Panel -- rendering logic for the dictation history overlay.

Draws a centered modal panel listing previously confirmed prose phrases,
paginated by HISTORY_PAGE_SIZE, with navigation hints in the footer.
Uses overlay_kit shared primitives for panel frame, separator, and close hint.
"""

from typing import Optional

from talon import ui
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ....utils.overlay_kit import (
    DismissibleOverlay,
    draw_panel_frame,
    draw_separator,
)
from ..internal.draw_constants import (
    PANEL_RADIUS, PANEL_PAD,
    BG_COLOR, BORDER_COLOR, TOKEN_COLOR,
    HINT_COLOR, HINT_CMD_COLOR, SEP_COLOR, HELP_TITLE_COLOR,
    TOKEN_FONT_SIZE,
)

# HINT_FONT_SIZE is mutable state owned by prose_overlay_draw — use a local
# default here for the history panel, which doesn't participate in resize commands.
HINT_FONT_SIZE = 12

# ---------------------------------------------------------------------------
# History panel
# ---------------------------------------------------------------------------

HISTORY_PAGE_SIZE = 10


def draw_history_panel(
    c: SkiaCanvas,
    overlay: DismissibleOverlay,
    history: list[str],
    page_index: int,
) -> Optional[Rect]:
    """Draw the prose history panel centered on screen.

    Shows up to HISTORY_PAGE_SIZE phrases per page, newest first.
    Each entry is numbered for use with 'history pick <N>'.
    """
    screen = ui.main_screen()
    sr = screen.rect

    c.paint.typeface = "Menlo"

    entries = history[page_index * HISTORY_PAGE_SIZE:(page_index + 1) * HISTORY_PAGE_SIZE]
    total_pages = max(1, (len(history) + HISTORY_PAGE_SIZE - 1) // HISTORY_PAGE_SIZE)

    row_h = HINT_FONT_SIZE + 10
    title_h = HINT_FONT_SIZE + 16
    sep_h = 14
    footer_h = row_h

    n_content_rows = max(1, len(entries))
    panel_w = min(int(sr.width * 0.64), 880)
    panel_h = PANEL_PAD + title_h + n_content_rows * row_h + sep_h + footer_h + PANEL_PAD
    panel_x = sr.x + (sr.width - panel_w) / 2
    panel_y = sr.y + (sr.height - panel_h) / 2
    panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)

    draw_panel_frame(c, panel_rect, PANEL_RADIUS, BG_COLOR, BORDER_COLOR)
    overlay.draw_close_hint(c, panel_x, panel_y, panel_w, PANEL_PAD)

    cx = panel_x + PANEL_PAD
    cy = panel_y + PANEL_PAD

    # Title + page info on same row
    c.paint.textsize = HINT_FONT_SIZE + 1
    c.paint.color = HELP_TITLE_COLOR
    c.paint.font.embolden = True
    c.draw_text("Prose History", cx, cy + HINT_FONT_SIZE)
    c.paint.font.embolden = False

    if history:
        page_label = f"page {page_index + 1} of {total_pages}  ·  {len(history)} entr{'y' if len(history) == 1 else 'ies'}"
        c.paint.textsize = HINT_FONT_SIZE
        c.paint.color = HINT_COLOR
        label_w = c.paint.measure_text(page_label)[1].width
        c.draw_text(page_label, panel_x + panel_w - PANEL_PAD - label_w, cy + HINT_FONT_SIZE)

    cy += title_h
    draw_separator(c, cx, panel_x + panel_w - PANEL_PAD, cy - 4, SEP_COLOR)

    if not history:
        c.paint.textsize = HINT_FONT_SIZE
        c.paint.color = HINT_COLOR
        c.draw_text('No history yet. Confirm a phrase with an ender word.', cx, cy + row_h)
    else:
        num_col_w = 32
        # Menlo at HINT_FONT_SIZE ≈ 0.62× font size per character (monospace estimate)
        max_text_w = panel_w - PANEL_PAD * 2 - num_col_w
        approx_char_w = HINT_FONT_SIZE * 0.62
        max_chars = max(10, int(max_text_w / approx_char_w))

        for i, entry in enumerate(entries):
            global_num = page_index * HISTORY_PAGE_SIZE + i + 1
            cy += row_h

            c.paint.textsize = HINT_FONT_SIZE
            c.paint.color = HINT_CMD_COLOR
            c.draw_text(str(global_num), cx, cy)

            display = entry if len(entry) <= max_chars else entry[:max_chars - 1] + "\u2026"
            c.paint.color = TOKEN_COLOR
            c.draw_text(display, cx + num_col_w, cy)

    # Footer
    sep_y = panel_y + panel_h - PANEL_PAD - footer_h - sep_h / 2
    draw_separator(c, cx, panel_x + panel_w - PANEL_PAD, sep_y, SEP_COLOR)

    fy = panel_y + panel_h - PANEL_PAD
    c.paint.textsize = HINT_FONT_SIZE
    fx = cx
    for txt, col in [
        ('"history back"',     HINT_CMD_COLOR),
        ("  \u00b7  ",         HINT_COLOR),
        ('"history next"',     HINT_CMD_COLOR),
        ("  \u00b7  ",         HINT_COLOR),
        ('"history pick <N>"', HINT_CMD_COLOR),
    ]:
        c.paint.color = col
        c.draw_text(txt, fx, fy)
        fx += c.paint.measure_text(txt)[1].width

    return panel_rect
