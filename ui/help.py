"""Prose Overlay Help -- help panel rendering and rotating hint ring buffer.

Contains HELP_PAGES data, the paginated draw_help_panel() function,
the rotating side-hint ring buffer globals, and rotate_help_ring_buffer().
"""

import random
import time
from typing import Optional

from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ....utils.overlay_kit import draw_panel_frame, draw_separator

# ---------------------------------------------------------------------------
# Visual constants (mirrored from prose_overlay_draw for standalone use)
# ---------------------------------------------------------------------------
PANEL_RADIUS = 12
PANEL_PAD = 12
HINT_FONT_SIZE = 12
BG_COLOR = "1a1a2add"
BORDER_COLOR = "4488aacc"
HINT_COLOR = "888899cc"
HINT_CMD_COLOR = "ccccddee"
SEP_COLOR = "44556688"
HELP_TITLE_COLOR = "66aaccee"
HELP_PANEL_GAP = 8

# ---------------------------------------------------------------------------
# Help side panel rotating display
# ---------------------------------------------------------------------------
# Ring buffer: _help_side_cmds holds N entries at fixed list indices.
# _help_side_head tracks which slot to replace next (oldest).
# Replacing in-place at _help_side_head keeps all other slots visually stable.
# _help_side_last_replace tracks when the last slot replacement happened (monotonic seconds).
# Only one slot is replaced per HELP_ROTATE_INTERVAL_MS, regardless of draw rate.
HELP_ROTATE_INTERVAL_MS: int = 5000  # ms between hint replacements
_help_side_cmds: list[tuple[str, str]] = []
_help_side_head: int = 0
_help_side_last_replace: float = 0.0

# ---------------------------------------------------------------------------
# Paginated help panel data
# ---------------------------------------------------------------------------
# entries are either section headers (str) or (command, description) tuples
HelpEntry = tuple[str, str] | str
HelpPage = tuple[str, list[HelpEntry]]  # (page_title, entries)

HELP_PAGES: list[HelpPage] = [
    ("Basics", [
        ('"bravely"', "confirm + paste"),
        ('"overlay dismiss"', "dismiss overlay"),
        ('"overlay auto"', "toggle auto-mode"),
        ('"overlay speak"', "read buffer aloud"),
        ('"overlay undo"', "undo last edit"),
        ('"overlay help"', "toggle this panel"),
    ]),
    ("Delete", [
        ('"chuck <hat>"', "delete word at hat"),
        ('"chuck past <hat>"', "delete hat through end"),
        ('"chuck head <hat>"', "delete start through hat"),
        ('"chuck tail <hat>"', "delete hat through end"),
        "hat colors (on any command)",
        ('"chuck blue <hat>"', "target colored hat"),
        ('"chuck red <hat>"', "target colored hat"),
    ]),
    ("Cursor & Edit", [
        ('"pre <hat>"', "cursor before hat"),
        ('"post <hat>"', "cursor after hat"),
        ('"pre file"', "cursor to start"),
        ('"post file"', "cursor to end"),
        ('"change <hat>"', "delete word + insert mode"),
        ('"change head <hat>"', "delete start→hat + insert"),
        ('"change tail <hat>"', "delete hat→end + insert"),
    ]),
    ("Move & History", [
        ('"bring <hat> to <hat>"', "copy word to position"),
        ('"move <hat> to <hat>"', "move word to position"),
        ('"prose history"', "show history panel"),
        ('"history pick <N>"', "reload history entry N"),
        ('"<window> bravely"', "retarget + confirm"),
    ]),
    ("Layout", [
        ('"overlay anchor"', "scope panel to window"),
        ('"overlay anchor clear"', "full-screen panel"),
        ('"overlay top"', "attach panel to top"),
        ('"overlay bottom"', "attach panel to bottom"),
    ]),
]


def _build_command_pool() -> list[tuple[str, str]]:
    """Flatten all (cmd, desc) pairs from HELP_PAGES into one pool."""
    pool = []
    for _, entries in HELP_PAGES:
        for e in entries:
            if isinstance(e, tuple):
                pool.append(e)
    return pool


HELP_COMMAND_POOL: list[tuple[str, str]] = _build_command_pool()


def rotate_help_ring_buffer(n: int) -> list[tuple[str, str]]:
    """Update the help ring buffer for a panel with n visible slots.

    Initializes the buffer on first call or when n changes.
    Rotates one slot per HELP_ROTATE_INTERVAL_MS interval.
    Returns the current _help_side_cmds list.
    """
    global _help_side_cmds, _help_side_head, _help_side_last_replace
    now = time.monotonic()
    if len(_help_side_cmds) != n:
        # First draw or panel resized: initialize with a fresh random sample.
        _help_side_cmds[:] = random.sample(HELP_COMMAND_POOL, n)
        _help_side_head = 0
        _help_side_last_replace = now
    elif (now - _help_side_last_replace) * 1000 >= HELP_ROTATE_INTERVAL_MS:
        # Enough time has passed — rotate one slot in-place (ring buffer).
        # All other indices stay put — no visual shift.
        current_set = set(_help_side_cmds)
        entry_candidates = [e for e in HELP_COMMAND_POOL if e not in current_set]
        if entry_candidates:
            new_entry = random.choice(entry_candidates)
            _help_side_head = (_help_side_head + 1) % n
            _help_side_cmds[_help_side_head] = new_entry
        _help_side_last_replace = now
    return _help_side_cmds


def draw_help_panel(
    c: SkiaCanvas,
    main_rect: Rect,
    page_index: int,
) -> Optional[Rect]:
    """Draw the paginated help panel below the main panel.

    Returns the help panel Rect for click-outside detection, or None if
    page_index is out of range.
    """
    if page_index < 0 or page_index >= len(HELP_PAGES):
        return None

    page_title, entries = HELP_PAGES[page_index]
    total_pages = len(HELP_PAGES)

    # Measure content height
    hint_row_h = HINT_FONT_SIZE + 6
    section_row_h = HINT_FONT_SIZE + 4 + 4  # 4px padding top + bottom around header
    title_row_h = HINT_FONT_SIZE + 2 + 8  # title slightly larger gap below
    footer_h = hint_row_h  # navigation footer: one row

    content_h = title_row_h
    for entry in entries:
        if isinstance(entry, str):
            content_h += section_row_h
        else:
            content_h += hint_row_h

    sep_gap = 12
    panel_h = PANEL_PAD + content_h + sep_gap + footer_h + PANEL_PAD
    panel_w = main_rect.width
    panel_x = main_rect.x  # same x as main panel
    panel_y = main_rect.y + main_rect.height + HELP_PANEL_GAP
    panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)

    # Panel background + border via overlay_kit
    draw_panel_frame(c, panel_rect, PANEL_RADIUS, BG_COLOR, BORDER_COLOR)

    max_content_w = panel_w - PANEL_PAD * 2
    cmd_col_w = max_content_w * 0.55
    cx = panel_x + PANEL_PAD
    cy = panel_y + PANEL_PAD

    # Page title
    c.paint.textsize = HINT_FONT_SIZE
    c.paint.color = HELP_TITLE_COLOR
    c.paint.font.embolden = True
    c.draw_text(page_title, cx, cy + HINT_FONT_SIZE)
    c.paint.font.embolden = False
    cy += title_row_h

    # Entries: section headers (str) or command/description tuples
    for entry in entries:
        if isinstance(entry, str):
            # Section header — same pattern as settings_overlay.py
            cy += 4
            c.paint.textsize = HINT_FONT_SIZE
            c.paint.color = BORDER_COLOR
            c.paint.font.embolden = True
            c.draw_text(f"\u2500\u2500 {entry} \u2500\u2500", cx, cy + HINT_FONT_SIZE)
            c.paint.font.embolden = False
            cy += HINT_FONT_SIZE + 4
        else:
            cmd, desc = entry
            cy += hint_row_h
            c.paint.textsize = HINT_FONT_SIZE
            c.paint.color = HINT_CMD_COLOR
            c.draw_text(cmd, cx, cy)
            c.paint.color = HINT_COLOR
            c.draw_text(desc, cx + cmd_col_w, cy)

    # Separator above navigation footer
    sep_y = panel_y + panel_h - PANEL_PAD - footer_h - sep_gap / 2
    draw_separator(c, cx, cx + max_content_w, sep_y, SEP_COLOR)

    # Navigation footer: "help next"  ·  "help back"  ·  page N of M
    footer_y = sep_y + sep_gap / 2 + hint_row_h
    c.paint.textsize = HINT_FONT_SIZE
    c.paint.color = HINT_CMD_COLOR
    nav_text = '"help next"'
    c.draw_text(nav_text, cx, footer_y)
    nav_w = c.paint.measure_text(nav_text)[1].width

    c.paint.color = HINT_COLOR
    dot1 = "  \u00b7  "
    c.draw_text(dot1, cx + nav_w, footer_y)
    dot1_w = c.paint.measure_text(dot1)[1].width

    c.paint.color = HINT_CMD_COLOR
    back_text = '"help back"'
    c.draw_text(back_text, cx + nav_w + dot1_w, footer_y)
    back_w = c.paint.measure_text(back_text)[1].width

    c.paint.color = HINT_COLOR
    dot2 = "  \u00b7  "
    c.draw_text(dot2, cx + nav_w + dot1_w + back_w, footer_y)
    dot2_w = c.paint.measure_text(dot2)[1].width

    page_text = f"page {page_index + 1} of {total_pages}"
    c.draw_text(page_text, cx + nav_w + dot1_w + back_w + dot2_w, footer_y)

    return panel_rect
