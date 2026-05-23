"""Prose Overlay Draw -- rendering logic for the dictation buffer overlay.

Draws word tokens in a horizontal flow layout with small gray Cursorless-style
hat dots above the first letter of each token (up to 26 tokens).
Uses overlay_kit shared primitives for panel frame, separator, and close hint.
"""

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
from .prose_overlay_help import draw_help_panel, rotate_help_ring_buffer, HELP_COMMAND_POOL
from .prose_overlay_history_panel import draw_history_panel, HISTORY_PAGE_SIZE

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

    # === Step 2 — terminal-pinned viewport if still overflowing ===
    # Always show the most recent (bottom) rows. Oldest lines drop off the top silently.
    max_visible_rows = max(1, int(usable_h / LINE_HEIGHT))
    _last_rows = list(rows)  # cache for auto-scroll

    if len(rows) > max_visible_rows:
        rows = rows[len(rows) - max_visible_rows:]

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

        # Help zone: stable rotating display — delegates to rotate_help_ring_buffer().
        hint_pad_x = help_x + PANEL_PAD
        cmd_col_w = (help_w - PANEL_PAD * 2) * 0.48
        max_rows = max(1, int((panel_h - PANEL_PAD * 2) / hint_row_h))
        n = min(max_rows, len(HELP_COMMAND_POOL))

        side_cmds = rotate_help_ring_buffer(n)

        hint_y = panel_y + PANEL_PAD
        for cmd, desc in side_cmds:
            hint_y += hint_row_h
            if hint_y > panel_y + panel_h - PANEL_PAD:
                break
            c.paint.textsize = HINT_FONT_SIZE
            c.paint.color = HINT_CMD_COLOR
            c.draw_text(cmd, hint_pad_x, hint_y)
            c.paint.color = HINT_COLOR
            c.draw_text(desc, hint_pad_x + cmd_col_w, hint_y)

    return panel_rect
