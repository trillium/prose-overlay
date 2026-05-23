"""Prose Overlay Draw -- rendering logic for the dictation buffer overlay.

Draws word tokens in a horizontal flow layout with small gray Cursorless-style
hat dots above the first letter of each token (up to 26 tokens).
Uses overlay_kit shared primitives for panel frame, separator, and close hint.
"""

import random
import time
from typing import Optional

from talon import settings, ui
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ...utils.overlay_kit import (
    DismissibleOverlay,
    draw_panel_frame,
    draw_rounded_rect,
    draw_separator,
)

# Hat alphabet: the 26 letter values from user.letter (a-z).
# Tokens beyond index 25 render without hats.
HAT_ALPHABET = "abcdefghijklmnopqrstuvwxyz"

# ---------------------------------------------------------------------------
# Visual constants
# ---------------------------------------------------------------------------
CONTENT_W_FRACTION = 0.80   # content zone: left 80% of screen width
HELP_W_FRACTION    = 0.20   # help zone:    right 20% of screen width
PANEL_H_FRACTION   = 0.10   # total panel height: 10% of screen height
PANEL_RADIUS = 12
PANEL_PAD = 12
PANEL_Y_OFFSET = 0  # flush with top of screen

# Colors
BG_COLOR = "1a1a2add"
BORDER_COLOR = "4488aacc"
TOKEN_COLOR = "eeeeffee"
HINT_COLOR = "888899cc"
HINT_CMD_COLOR = "ccccddee"
LISTENING_COLOR = "666677cc"
SEP_COLOR = "44556688"
HELP_TITLE_COLOR = "66aaccee"  # slightly brighter than BORDER_COLOR for page titles

# Hat dot colors — matches mouse-clock constants and Cursorless palette
HAT_COLOR_HEX: dict[str, str] = {
    "gray":   "999999ff",
    "blue":   "089ad3ff",
    "green":  "36b33fff",
    "red":    "e02d28ff",
    "pink":   "e06caaff",
    "yellow": "e5c02cff",
    "purple": "8e44adff",
    "black":  "000000ff",  # drawn with white border ring
    "white":  "ffffffff",
}
HAT_COLOR = HAT_COLOR_HEX["gray"]  # legacy fallback

# Font sizes
TOKEN_FONT_SIZE = 16
HINT_FONT_SIZE = 12  # mutable — adjusted by help_bigger / help_smaller commands

# Hat dot (Cursorless-style)
DOT_RADIUS = 3       # small filled circle above first letter
DOT_GAP_Y = 2        # gap between dot bottom and token top

# Layout — TOKEN_GAP_X approximates a natural inter-word space at TOKEN_FONT_SIZE
TOKEN_GAP_X = 5   # horizontal gap between tokens (~1 space-char width at 16pt)
TOKEN_GAP_Y = 6   # vertical gap between wrapped rows
LINE_HEIGHT = (DOT_RADIUS * 2) + DOT_GAP_Y + TOKEN_FONT_SIZE + TOKEN_GAP_Y
HELP_PANEL_GAP = 8  # gap between main panel and help panel

# Cursor
CURSOR_COLOR_NAVIGATE = "ffffffff"   # white, navigate mode
CURSOR_COLOR_CHANGE   = "e5a02cff"   # amber, change/replace mode
CURSOR_WIDTH = 2
CURSOR_CHANGE_ZONE_WIDTH = 24        # width of faint amber insertion-zone rect
CURSOR_CHANGE_ZONE_ALPHA = "4d"      # ~30% alpha

# Full command pool — flattened from HELP_PAGES (defined below) after module load.
# Populated by _build_command_pool() at the bottom of this file.
HELP_COMMAND_POOL: list[tuple[str, str]] = []

# Anchor rect — when set, the overlay panel is scoped to this window's
# x/width instead of the full screen. Set by prose_overlay.py on show
# or via the 'overlay anchor' command.
_anchor_rect: Optional[Rect] = None

# Anchor position — where the panel attaches vertically.
# "top"    → panel_y = top of anchor (or screen top)
# "bottom" → panel_y = bottom of anchor (or screen bottom) minus panel height
_anchor_position: str = "top"

# Overflow state — set during each draw, read by auto-scroll helper in prose_overlay.py
_hints_hidden_by_overflow: bool = False
_scroll_offset: int = 0
_last_rows: list = []  # cached row layout from last draw, used by compute_scroll_for_cursor


def set_anchor_rect(rect: Optional[Rect]) -> None:
    """Set (or clear) the anchor window rect used for window-scoped layout."""
    global _anchor_rect
    _anchor_rect = rect


def set_anchor_position(position: str) -> None:
    """Set the vertical attachment point: 'top' or 'bottom'."""
    global _anchor_position
    if position in ("top", "bottom"):
        _anchor_position = position


# Help side panel rotating display.
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


HELP_COMMAND_POOL = _build_command_pool()


def set_scroll_offset(offset: int) -> None:
    """Set the scroll row offset for the token viewport."""
    global _scroll_offset
    _scroll_offset = offset


def get_max_visible_rows() -> int:
    """Return the maximum number of token rows that fit in the panel."""
    screen = ui.main_screen()
    panel_h = screen.rect.height * PANEL_H_FRACTION
    usable_h = panel_h - PANEL_PAD * 2
    return max(1, int(usable_h / LINE_HEIGHT))


def _find_cursor_row(rows: list, cursor: "int | None") -> "int | None":
    """Return the row index that contains the given cursor gap index, or None."""
    if cursor is None:
        return None
    for row_idx, row in enumerate(rows):
        first_tok = row[0][0]
        last_tok = row[-1][0]
        if first_tok <= cursor <= last_tok + 1:
            return row_idx
    return None


def compute_scroll_for_cursor(
    rows: list,
    cursor: "int | None",
    scroll_offset: int,
    max_visible_rows: int,
) -> int:
    """Return the scroll offset needed to keep the cursor row visible."""
    row_idx = _find_cursor_row(rows, cursor)
    if row_idx is None:
        return scroll_offset
    if row_idx < scroll_offset:
        return row_idx
    if row_idx >= scroll_offset + max_visible_rows:
        return row_idx - max_visible_rows + 1
    return scroll_offset


def draw_cursor(c: SkiaCanvas, x: float, y_top: float, height: float, change_mode: bool, blink_on: bool):
    """Draw a blinking cursor line at (x, y_top) with the given height.

    In change mode, also draws a faint amber insertion-zone rectangle.
    """
    if not blink_on:
        return
    c.paint.style = c.paint.Style.FILL
    if change_mode:
        # Faint amber zone behind cursor
        c.paint.color = CURSOR_COLOR_CHANGE[:6] + CURSOR_CHANGE_ZONE_ALPHA
        c.draw_rect(Rect(x - CURSOR_CHANGE_ZONE_WIDTH / 2, y_top, CURSOR_CHANGE_ZONE_WIDTH, height))
        c.paint.color = CURSOR_COLOR_CHANGE
    else:
        c.paint.color = CURSOR_COLOR_NAVIGATE
    c.draw_rect(Rect(x - 1, y_top, CURSOR_WIDTH, height))


def draw_overlay(
    c: SkiaCanvas,
    tokens: list[str],
    overlay: DismissibleOverlay,
    hat_assignments: dict[int, tuple[int, str, str]] | None = None,
    cursor: int | None = None,
    change_mode: bool = False,
    blink_on: bool = True,
    flash_indices: list[int] | None = None,
    flash_color: str | None = None,
    selection: tuple[int, int] | None = None,
    target_label: str = "",
) -> Rect:
    """Main draw routine for the prose overlay.

    Renders a panel with word tokens arranged in a flow layout,
    each with a colored Cursorless-style hat dot above the assigned character.
    Color encodes collision resolution: two tokens sharing the same letter get
    different colors (gray first, then blue, green, red, ...).

    hat_assignments: mapping of token_index -> (char_index_within_word, letter, color).
    If None, falls back to legacy behavior (gray dot above first letter, positional).
    cursor: gap index for the editing cursor (None = no cursor).
    change_mode: True when cursor is in change/replace mode (amber color).
    blink_on: current blink phase for cursor visibility.
    flash_indices: token indices to highlight with a brief flash rect.
    flash_color: 6-char hex color (no alpha) for the flash highlight.
    selection: (start_idx, end_idx) inclusive range of selected tokens, or None.
    """
    screen = ui.main_screen()
    sr = screen.rect

    # Use monospace font for consistent character-width alignment
    c.paint.typeface = "Menlo"

    # Measure all tokens to determine layout
    c.paint.textsize = TOKEN_FONT_SIZE
    token_metrics = []
    for token in tokens:
        text_rect = c.paint.measure_text(token)[1]
        token_metrics.append((token, text_rect.width))

    # Panel geometry — window-scoped or full-screen, top or bottom attachment.
    # x/width come from the anchor window when window_scoped is on.
    # y is computed from _anchor_position ("top" or "bottom") against whichever
    # rect is in use (anchor window or screen).
    window_scoped = (
        settings.get("user.prose_overlay_window_scoped")
        and _anchor_rect is not None
    )
    ref = _anchor_rect if window_scoped else sr

    panel_h = sr.height * PANEL_H_FRACTION
    panel_x = ref.x if window_scoped else sr.left
    panel_w = ref.width if window_scoped else sr.width

    if _anchor_position == "bottom":
        panel_y = ref.y + ref.height - panel_h
    else:  # "top"
        panel_y = ref.y if window_scoped else sr.top + PANEL_Y_OFFSET

    content_w = panel_w * CONTENT_W_FRACTION
    help_x    = panel_x + content_w
    help_w    = panel_w * HELP_W_FRACTION

    # Flow-layout wrap width is the content zone minus padding
    max_content_w = content_w - PANEL_PAD * 2

    rows: list[list[tuple[int, str, float]]] = []  # [(index, token, width), ...]
    current_row: list[tuple[int, str, float]] = []
    current_row_w = 0.0

    for i, (token, tw) in enumerate(token_metrics):
        needed = tw + (TOKEN_GAP_X if current_row else 0)
        if current_row and current_row_w + needed > max_content_w:
            rows.append(current_row)
            current_row = [(i, token, tw)]
            current_row_w = tw
        else:
            current_row.append((i, token, tw))
            current_row_w += needed
    if current_row:
        rows.append(current_row)

    # === Hybrid overflow: Step 1 — auto-hide hints if content overflows ===
    global _hints_hidden_by_overflow, _scroll_offset, _last_rows
    usable_h = panel_h - PANEL_PAD * 2
    content_fits_with_hints = len(rows) * LINE_HEIGHT <= usable_h

    if not content_fits_with_hints:
        # Reflow with full panel width (hints hidden)
        max_content_w_full = panel_w - PANEL_PAD * 2
        rows_full: list[list[tuple[int, str, float]]] = []
        cur_row_f: list[tuple[int, str, float]] = []
        cur_row_w_f = 0.0
        for i, (token, tw) in enumerate(token_metrics):
            needed = tw + (TOKEN_GAP_X if cur_row_f else 0)
            if cur_row_f and cur_row_w_f + needed > max_content_w_full:
                rows_full.append(cur_row_f)
                cur_row_f = [(i, token, tw)]
                cur_row_w_f = tw
            else:
                cur_row_f.append((i, token, tw))
                cur_row_w_f += needed
        if cur_row_f:
            rows_full.append(cur_row_f)
        _hints_hidden_by_overflow = True
        rows = rows_full
        max_content_w = max_content_w_full
    else:
        _hints_hidden_by_overflow = False

    # === Step 2 — scrolling window if still overflowing ===
    max_visible_rows = max(1, int(usable_h / LINE_HEIGHT))
    _last_rows = list(rows)  # cache for auto-scroll

    # Initialize scroll indicator counts — always defined before drawing
    rows_above = 0
    rows_below = 0

    if len(rows) * LINE_HEIGHT > usable_h:
        _scroll_offset = max(0, min(_scroll_offset, len(rows) - max_visible_rows))
        rows_above = _scroll_offset
        rows_below = max(0, len(rows) - (_scroll_offset + max_visible_rows))
        rows = rows[_scroll_offset : _scroll_offset + max_visible_rows]

    panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)
    hint_row_h = HINT_FONT_SIZE + 6

    # Panel background + border via overlay_kit
    draw_panel_frame(c, panel_rect, PANEL_RADIUS, BG_COLOR, BORDER_COLOR)

    # Close hint (X button) in the top-right via overlay
    overlay.draw_close_hint(c, panel_x, panel_y, panel_w, PANEL_PAD)

    if not tokens:
        # Show "listening..." placeholder
        c.paint.textsize = TOKEN_FONT_SIZE
        c.paint.color = LISTENING_COLOR
        c.draw_text(
            "listening...",
            panel_x + PANEL_PAD,
            panel_y + PANEL_PAD + (DOT_RADIUS * 2) + DOT_GAP_Y + TOKEN_FONT_SIZE,
        )
        # Draw cursor at gap 0 even when buffer is empty
        if cursor is not None and cursor == 0:
            cursor_y_top = panel_y + PANEL_PAD + (DOT_RADIUS * 2) + DOT_GAP_Y
            draw_cursor(c, panel_x + PANEL_PAD, cursor_y_top, TOKEN_FONT_SIZE, change_mode, blink_on)
    else:
        # Draw token rows with hats
        y_base = panel_y + PANEL_PAD

        for row in rows:
            x = panel_x + PANEL_PAD

            for idx, token, tw in row:
                # Check if cursor sits in the gap before this token
                if cursor is not None and cursor == idx:
                    cursor_y_top = y_base + (DOT_RADIUS * 2) + DOT_GAP_Y
                    draw_cursor(c, x, cursor_y_top, TOKEN_FONT_SIZE, change_mode, blink_on)

                # Draw hat dot above the assigned character
                assignment = hat_assignments.get(idx) if hat_assignments else None
                has_hat = assignment is not None if hat_assignments else (idx < len(HAT_ALPHABET))

                if has_hat:
                    c.paint.textsize = TOKEN_FONT_SIZE
                    char_idx = assignment[0] if assignment else 0
                    dot_color = HAT_COLOR_HEX.get(assignment[2], HAT_COLOR) if assignment else HAT_COLOR
                    # Measure x offset to the target character
                    prefix_w = 0.0
                    if char_idx > 0:
                        prefix = token[:char_idx]
                        prefix_w = c.paint.measure_text(prefix)[1].width
                    target_char = token[char_idx] if char_idx < len(token) else token[0]
                    char_rect = c.paint.measure_text(target_char)[1]
                    dot_cx = x + prefix_w + char_rect.width / 2
                    dot_cy = y_base + DOT_RADIUS
                    c.paint.style = c.paint.Style.FILL
                    # Black hat: draw white border ring first so it's visible on dark bg
                    if dot_color == HAT_COLOR_HEX["black"]:
                        c.paint.color = "ffffffff"
                        c.draw_circle(dot_cx, dot_cy, DOT_RADIUS + 1)
                    c.paint.color = dot_color
                    c.draw_circle(dot_cx, dot_cy, DOT_RADIUS)

                # Draw highlight rect behind token (flash or selection)
                token_y = y_base + (DOT_RADIUS * 2) + DOT_GAP_Y + TOKEN_FONT_SIZE
                highlight_color: str | None = None
                if flash_indices is not None and flash_color is not None and idx in flash_indices:
                    # Flash highlight: 30% alpha (4d in hex)
                    highlight_color = flash_color[:6] + "4d"
                elif (
                    selection is not None
                    and selection[0] <= idx <= selection[1]
                ):
                    # Selection highlight: 25% alpha (40 in hex), blue
                    highlight_color = "089ad340"

                if highlight_color is not None:
                    hl_y_top = y_base + (DOT_RADIUS * 2) + DOT_GAP_Y
                    hl_pad_x = 2
                    hl_rect = Rect(
                        x - hl_pad_x,
                        hl_y_top,
                        tw + hl_pad_x * 2,
                        TOKEN_FONT_SIZE + 2,
                    )
                    c.paint.style = c.paint.Style.FILL
                    c.paint.color = highlight_color
                    draw_rounded_rect(c, hl_rect, 3)

                # Draw token text
                c.paint.textsize = TOKEN_FONT_SIZE
                c.paint.color = TOKEN_COLOR
                c.draw_text(token, x, token_y)

                x += tw + TOKEN_GAP_X

            # Check if cursor sits after the last token in this row
            # (only relevant for the very last row — cursor == len(tokens))
            if row and cursor is not None:
                last_idx = row[-1][0]
                if cursor == last_idx + 1 and cursor == len(tokens):
                    cursor_y_top = y_base + (DOT_RADIUS * 2) + DOT_GAP_Y
                    # x already advanced past the last token by tw + TOKEN_GAP_X;
                    # subtract only the gap to place cursor at the token's right edge
                    draw_cursor(c, x - TOKEN_GAP_X, cursor_y_top, TOKEN_FONT_SIZE, change_mode, blink_on)

            y_base += LINE_HEIGHT

    # Scroll indicators — drawn over token area when viewport is active
    if rows_above > 0:
        c.paint.textsize = HINT_FONT_SIZE
        c.paint.color = HINT_CMD_COLOR
        c.draw_text(f"↑ {rows_above} more", panel_x + PANEL_PAD, panel_y + PANEL_PAD + HINT_FONT_SIZE)
    if rows_below > 0:
        c.paint.textsize = HINT_FONT_SIZE
        c.paint.color = HINT_CMD_COLOR
        c.draw_text(f"↓ {rows_below} more", panel_x + PANEL_PAD, panel_y + panel_h - PANEL_PAD)

    # Target window label — bottom-left of content zone
    # Hidden when overflow is active (hints already hidden, space is tight)
    if target_label and not _hints_hidden_by_overflow:
        c.paint.textsize = HINT_FONT_SIZE
        c.paint.color = HINT_CMD_COLOR
        label_y = panel_y + panel_h - PANEL_PAD
        c.draw_text(target_label, panel_x + PANEL_PAD, label_y)

    # Vertical separator and help zone — only when hints are not hidden by overflow
    if not _hints_hidden_by_overflow:
        # Vertical separator between content and help zones
        c.paint.style = c.paint.Style.STROKE
        c.paint.stroke_width = 1
        c.paint.color = SEP_COLOR
        c.draw_line(help_x, panel_y + PANEL_PAD, help_x, panel_y + panel_h - PANEL_PAD)
        c.paint.style = c.paint.Style.FILL

        # Help zone: stable rotating display — one entry replaced per render (oldest first).
        # _help_side_cmds is a queue: [oldest, ..., newest]. Each render pops index 0
        # and appends a new random entry not already in the visible set.
        hint_pad_x = help_x + PANEL_PAD
        cmd_col_w = (help_w - PANEL_PAD * 2) * 0.48
        max_rows = max(1, int((panel_h - PANEL_PAD * 2) / hint_row_h))
        n = min(max_rows, len(HELP_COMMAND_POOL))

        global _help_side_head, _help_side_last_replace
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

        hint_y = panel_y + PANEL_PAD
        for cmd, desc in _help_side_cmds:
            hint_y += hint_row_h
            if hint_y > panel_y + panel_h - PANEL_PAD:
                break
            c.paint.textsize = HINT_FONT_SIZE
            c.paint.color = HINT_CMD_COLOR
            c.draw_text(cmd, hint_pad_x, hint_y)
            c.paint.color = HINT_COLOR
            c.draw_text(desc, hint_pad_x + cmd_col_w, hint_y)

    return panel_rect


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
    panel_w = PANEL_WIDTH
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
