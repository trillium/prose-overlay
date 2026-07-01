"""Prose Overlay Help — help panel rendering and rotating hint ring buffer.

Contains ``HELP_PAGES`` data, the paginated ``draw_help_panel`` function,
the rotating side-hint ring buffer globals, and
``rotate_help_ring_buffer``.

Step 14 of the paint-pipeline retirement:

  * The paginated pager's ROW y-coordinates now source from
    ``ui/layout_help_cursor.py:build_help_layout`` — the single source of
    truth for row-y math. The duplicated content-height loop that used
    to compute ``panel_h`` from HELP_PAGES entry-by-entry has been
    retired.
  * Entry-row emission (two-column ``cmd`` + ``desc`` text) now flows
    through the ops pipeline via ``paint_ops.to_help_pager_entry_ops`` +
    ``paint_ops.execute`` — landed in step 9.
  * Title + section headers still paint directly (they need
    ``c.paint.font.embolden`` which isn't on ``TextOp``).
  * Panel frame / separator / footer nav still paint directly (composed
    helpers + runtime ``c.paint.measure_text``).

Everything else in the module — ``HELP_PAGES`` data, the rotating side-
hint ring buffer state, ``rotate_help_ring_buffer`` — is unchanged.
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
# _help_side_last_replace tracks when the last slot replacement happened
# (monotonic seconds). Only one slot is replaced per
# HELP_ROTATE_INTERVAL_MS, regardless of draw rate.
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
        ('"change head <hat>"', "delete start->hat + insert"),
        ('"change tail <hat>"', "delete hat->end + insert"),
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

    Returns the help panel Rect for click-outside detection, or None
    if page_index is out of range.

    Step 14 of the paint-pipeline retirement — the duplicated content-
    height loop that used to walk HELP_PAGES entry-by-entry inside
    ``draw_help_panel`` has been retired. Row y-coordinates now come
    directly from ``ui/layout_help_cursor.py:build_help_layout`` (the
    single source of truth for row-y math). What still lives here:

      * Panel frame — direct via ``draw_panel_frame`` (composed Skia
        Path helper).
      * Title + section headers — direct because they need
        ``c.paint.font.embolden = True`` which isn't on ``TextOp``.
      * Panel-height derivation — computed from the last row's y +
        trailing padding + separator + footer.
      * Separator + footer nav — direct because the footer's inter-
        column x placement needs runtime ``c.paint.measure_text`` (not
        modelable on ``TextOp`` without pre-measured widths).

    Entry rows (two-column ``cmd`` + ``desc``) route through the ops
    pipeline via ``paint_ops.to_help_pager_entry_ops`` — landed in
    step 9.
    """
    if page_index < 0 or page_index >= len(HELP_PAGES):
        return None

    total_pages = len(HELP_PAGES)

    # --- Build the HelpLayout via the pure builder ---
    # build_help_layout walks HELP_PAGES and computes the y for every
    # drawn row (title + section headers + entry rows) using
    # _row_heights(HINT_FONT_SIZE). Sourcing row y-positions from here
    # means the local math previously duplicated in this function is
    # gone.
    from types import SimpleNamespace
    from .layout import Rect as _LayoutRect
    from .layout_help_cursor import build_help_layout
    from .paint_ops import execute as _execute
    from .paint_ops import to_help_pager_entry_ops
    help_state = SimpleNamespace(help_visible=True, help_page=page_index)
    help_layout = build_help_layout(
        help_state,
        panel_rect=_LayoutRect(
            x=main_rect.x, y=main_rect.y,
            w=main_rect.width, h=main_rect.height,
        ),
        hint_font_size=HINT_FONT_SIZE,
        help_panel_gap=float(HELP_PANEL_GAP),
    )
    if help_layout is None:
        return None

    # --- Derive panel geometry from the built layout ---
    # The pager panel top is fixed: main_rect.y + main_rect.height +
    # HELP_PANEL_GAP (mirrors build_help_layout's pager_y_top math).
    # The pager panel bottom is: last_row_y + trailing pad (4) +
    # sep_gap (12) + footer_h + trailing PANEL_PAD. Row y in the
    # HelpLayout is:
    #   * title row     — baseline (drawn at row.y directly)
    #   * section header — baseline (drawn at row.y directly)
    #   * entry row     — baseline (drawn at row.y directly)
    # For section headers the trailing gap is HINT_FONT_SIZE + 4
    # (section_row_h - hint_font_size); for other rows there's no
    # trailing gap. The last row's bottom edge is:
    #   * if header/title: row.y + 4 (trailing pad only)
    #   * if entry: row.y (baseline is the row's bottom)
    # Use the max-safe formula: last_row.y + 4 for section headers,
    # last_row.y for entries. Since HELP_PAGES ends with entries, the
    # last row is always an entry in the current data. We compute the
    # bottom conservatively as max(row.y) + 4 to leave a small gap
    # regardless of the last row's type.
    hint_row_h = HINT_FONT_SIZE + 6
    footer_h = hint_row_h
    sep_gap = 12
    # last_row.y for entries is the drawn baseline (= final_cy after
    # the last hint_row_h advancement). For section headers, cy has
    # advanced by an extra HINT_FONT_SIZE + 4 after the last section.
    # In HELP_PAGES today every page ends with an entry tuple, so
    # last_row.y equals the equivalent of pager_y_top + PANEL_PAD +
    # content_h in the OLD formula (where content_h was the sum of all
    # row heights). That preserves pixel parity with the old panel_h
    # computation: PANEL_PAD + content_h + sep_gap + footer_h +
    # PANEL_PAD == (last_row.y - panel_y) + sep_gap + footer_h +
    # PANEL_PAD.
    last_row_y = max((r.y for r in help_layout.rows), default=0.0)
    panel_x = main_rect.x
    panel_y = main_rect.y + main_rect.height + HELP_PANEL_GAP
    panel_w = main_rect.width
    panel_h = (last_row_y - panel_y) + sep_gap + footer_h + PANEL_PAD
    panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)

    # --- Panel background + border (direct — composed Skia Path) ---
    draw_panel_frame(c, panel_rect, PANEL_RADIUS, BG_COLOR, BORDER_COLOR)

    max_content_w = panel_w - PANEL_PAD * 2
    cx = panel_x + PANEL_PAD

    # --- Title + section header rows (direct — need embolden) ---
    # Walk help_layout.rows; identify title (FIRST row) and section
    # headers (rows with an empty ``right``). Entry rows have a non-
    # empty ``right`` and are emitted by the ops pipeline below.
    for i, row in enumerate(help_layout.rows):
        if row.right != "":
            # Entry row — handled by ops.
            continue
        c.paint.textsize = HINT_FONT_SIZE
        if i == 0:
            # Title row (first in the list per build_help_layout).
            c.paint.color = HELP_TITLE_COLOR
        else:
            # Section header (row.left starts with the box-drawing
            # dashes baked in by build_help_layout).
            c.paint.color = BORDER_COLOR
        c.paint.font.embolden = True
        c.draw_text(row.left, cx, row.y)
        c.paint.font.embolden = False

    # --- Entry rows via ops pipeline (Step 9 of paint retirement) ---
    entry_ops = to_help_pager_entry_ops(help_layout, panel_x, panel_w)
    _execute(entry_ops, c)

    # --- Separator above navigation footer (direct — composed helper) ---
    sep_y = panel_y + panel_h - PANEL_PAD - footer_h - sep_gap / 2
    draw_separator(c, cx, cx + max_content_w, sep_y, SEP_COLOR)

    # --- Navigation footer (direct — needs runtime measurement) ---
    footer_y = sep_y + sep_gap / 2 + hint_row_h
    c.paint.textsize = HINT_FONT_SIZE
    c.paint.color = HINT_CMD_COLOR
    nav_text = '"help next"'
    c.draw_text(nav_text, cx, footer_y)
    nav_w = c.paint.measure_text(nav_text)[1].width

    c.paint.color = HINT_COLOR
    dot1 = "  ·  "
    c.draw_text(dot1, cx + nav_w, footer_y)
    dot1_w = c.paint.measure_text(dot1)[1].width

    c.paint.color = HINT_CMD_COLOR
    back_text = '"help back"'
    c.draw_text(back_text, cx + nav_w + dot1_w, footer_y)
    back_w = c.paint.measure_text(back_text)[1].width

    c.paint.color = HINT_COLOR
    dot2 = "  ·  "
    c.draw_text(dot2, cx + nav_w + dot1_w + back_w, footer_y)
    dot2_w = c.paint.measure_text(dot2)[1].width

    page_text = f"page {page_index + 1} of {total_pages}"
    c.draw_text(page_text, cx + nav_w + dot1_w + back_w + dot2_w, footer_y)

    return panel_rect
