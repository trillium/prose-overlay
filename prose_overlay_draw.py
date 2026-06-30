"""Prose Overlay Draw -- panel layout, overflow handling, and main draw routine.

Renders word tokens in a horizontal flow layout with Cursorless-style hat dots.
Delegates token rendering to prose_overlay_draw_tokens, shared constants to
prose_overlay_draw_constants, and viewport state to prose_overlay_viewport
(accessed via `instance.viewport`).
"""

from talon import settings, ui
from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ...utils.overlay_kit import (
    DismissibleOverlay,
    draw_panel_frame,
)
from .internal.draw_constants import (
    PANEL_RADIUS, PANEL_PAD, PANEL_H_FRACTION,
    BG_COLOR, BORDER_COLOR,
    BG_COLOR_FALLBACK, BORDER_COLOR_FALLBACK,
    HINT_COLOR, HINT_CMD_COLOR, LISTENING_COLOR, SEP_COLOR,
    TOKEN_FONT_SIZE, DOT_RADIUS, DOT_GAP_Y, LINE_HEIGHT,
)
from .prose_overlay_draw_tokens import _fit_text, _flow_layout, draw_cursor, _draw_token_rows
from .internal import homophones as _homophones
from .shim import shapes as _shapes_runtime
from .prose_overlay_help import draw_help_panel, rotate_help_ring_buffer, HELP_COMMAND_POOL
from .prose_overlay_history_panel import draw_history_panel, HISTORY_PAGE_SIZE
from .internal.instance import instance

# Re-export for canvas.py which imports draw_help_panel from this module.
__all__ = ["draw_overlay", "draw_help_panel", "draw_history_panel", "HISTORY_PAGE_SIZE"]

# ---------------------------------------------------------------------------
# Layout fractions (draw-specific, not shared with history panel)
# ---------------------------------------------------------------------------
CONTENT_W_FRACTION = 0.80   # content zone: left 80% of screen width
HELP_W_FRACTION    = 0.20   # help zone:    right 20% of screen width
PANEL_Y_OFFSET = 0  # flush with top of screen

# Mutable — adjusted by help_bigger / help_smaller commands via draw_mod.HINT_FONT_SIZE
HINT_FONT_SIZE = 12

# Overflow state — set during each draw, read by debug snapshot.
_hints_hidden_by_overflow: bool = False


# ---------------------------------------------------------------------------
# Main draw routine
# ---------------------------------------------------------------------------

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
    using_fallback: bool = False,
) -> Rect:
    """Main draw routine for the prose overlay.

    Renders a panel with word tokens in a flow layout, each with a colored
    Cursorless-style hat dot above the assigned character.

    hat_assignments: token_index -> (char_index_within_word, letter, color).
    cursor: gap index for the editing cursor (None = no cursor).
    change_mode: True when cursor is in change/replace mode (amber color).
    blink_on: current blink phase for cursor visibility.
    flash_indices: token indices to highlight with a brief flash rect.
    flash_color: 6-char hex color (no alpha) for the flash highlight.
    selection: (start_idx, end_idx) inclusive range of selected tokens.
    """
    global _hints_hidden_by_overflow

    viewport = instance.viewport
    anchor_rect = viewport._anchor_rect
    anchor_position = viewport._anchor_position

    screen = ui.main_screen()
    sr = screen.rect

    c.paint.typeface = "Menlo"

    # Measure tokens
    c.paint.textsize = TOKEN_FONT_SIZE
    token_metrics = [(tok, c.paint.measure_text(tok)[1].width) for tok in tokens]

    # Panel geometry — window-scoped or full-screen, top or bottom attachment.
    window_scoped = settings.get("user.prose_overlay_window_scoped") and anchor_rect is not None
    ref = anchor_rect if window_scoped else sr
    panel_h = max(sr.height * PANEL_H_FRACTION, 3 * LINE_HEIGHT + PANEL_PAD * 2)
    panel_x = ref.x if window_scoped else sr.left
    panel_w = ref.width if window_scoped else sr.width
    panel_y = (
        ref.y + ref.height - panel_h
        if anchor_position == "bottom"
        else (ref.y if window_scoped else sr.top + PANEL_Y_OFFSET)
    )

    content_w = panel_w * CONTENT_W_FRACTION
    help_x    = panel_x + content_w
    help_w    = panel_w * HELP_W_FRACTION

    # === Overflow step 1: auto-hide hints if content overflows content zone ===
    hint_row_h = HINT_FONT_SIZE + 6
    usable_h = panel_h - PANEL_PAD * 2

    # Target label sits at the bottom and steals hint_row_h from usable space.
    label_reserve = hint_row_h if target_label else 0
    rows = _flow_layout(token_metrics, content_w - PANEL_PAD * 2)
    if len(rows) * LINE_HEIGHT <= usable_h - label_reserve:
        _hints_hidden_by_overflow = False
        max_content_w = content_w - PANEL_PAD * 2
    else:
        # Reflow using full panel width (hints hidden)
        rows = _flow_layout(token_metrics, panel_w - PANEL_PAD * 2)
        _hints_hidden_by_overflow = True
        max_content_w = panel_w - PANEL_PAD * 2

    # === Overflow step 2: terminal-pinned viewport if still overflowing ===
    # In overflow mode label is hidden, so full usable_h is available.
    effective_h = usable_h if _hints_hidden_by_overflow else (usable_h - label_reserve)
    max_visible_rows = max(1, int(effective_h / LINE_HEIGHT))
    viewport._last_rows = list(rows)

    if len(rows) > max_visible_rows:
        rows = rows[len(rows) - max_visible_rows:]

    panel_rect = Rect(panel_x, panel_y, panel_w, panel_h)
    bg = BG_COLOR_FALLBACK if using_fallback else BG_COLOR
    border = BORDER_COLOR_FALLBACK if using_fallback else BORDER_COLOR
    draw_panel_frame(c, panel_rect, PANEL_RADIUS, bg, border)
    overlay.draw_close_hint(c, panel_x, panel_y, panel_w, PANEL_PAD)

    if not tokens:
        # "listening..." placeholder
        c.paint.textsize = TOKEN_FONT_SIZE
        c.paint.color = LISTENING_COLOR
        c.draw_text(
            "listening...",
            panel_x + PANEL_PAD,
            panel_y + PANEL_PAD + (DOT_RADIUS * 2) + DOT_GAP_Y + TOKEN_FONT_SIZE,
        )
        if cursor is not None and cursor == 0:
            draw_cursor(
                c,
                panel_x + PANEL_PAD,
                panel_y + PANEL_PAD + (DOT_RADIUS * 2) + DOT_GAP_Y,
                TOKEN_FONT_SIZE,
                change_mode,
                blink_on,
            )
    else:
        flagged = (
            _homophones.flagged_indices(tokens)
            if settings.get("user.prose_overlay_homophone_hint") or _homophones.hint_enabled()
            else frozenset()
        )
        # Slice 1 of HOMOPHONE_SHAPES_PLAN.md — paint hat shape over flagged
        # tokens. Default OFF (per plan §6.1); flip on via the static
        # setting or the runtime `overlay shapes homo on` toggle (which
        # mutates the module flag in prose_overlay_shapes).
        shape_enabled = bool(
            settings.get("user.prose_overlay_homophone_shapes")
            or _shapes_runtime.shapes_enabled()
        )
        _draw_token_rows(
            c, rows,
            x_origin=panel_x + PANEL_PAD,
            y_start=panel_y + PANEL_PAD,
            hat_assignments=hat_assignments,
            cursor=cursor,
            change_mode=change_mode,
            blink_on=blink_on,
            flash_indices=flash_indices,
            flash_color=flash_color,
            selection=selection,
            tokens=tokens,
            flagged_indices=flagged,
            shape_enabled=shape_enabled,
        )

    # Target window label — bottom-left of content zone (hidden during overflow)
    if target_label and not _hints_hidden_by_overflow:
        c.paint.textsize = HINT_FONT_SIZE
        c.paint.color = HINT_CMD_COLOR
        c.draw_text(target_label, panel_x + PANEL_PAD, panel_y + panel_h - PANEL_PAD)

    # Help zone — only when hints are not hidden by overflow
    if not _hints_hidden_by_overflow:
        c.paint.style = c.paint.Style.STROKE
        c.paint.stroke_width = 1
        c.paint.color = SEP_COLOR
        c.draw_line(help_x, panel_y + PANEL_PAD, help_x, panel_y + panel_h - PANEL_PAD)
        c.paint.style = c.paint.Style.FILL

        hint_pad_x = help_x + PANEL_PAD
        cmd_col_w = (help_w - PANEL_PAD * 2) * 0.48
        max_rows = max(1, int((panel_h - PANEL_PAD * 2) / hint_row_h))
        side_cmds = rotate_help_ring_buffer(min(max_rows, len(HELP_COMMAND_POOL)))

        desc_col_w = help_w - PANEL_PAD * 2 - cmd_col_w
        hint_y = panel_y + PANEL_PAD
        for cmd, desc in side_cmds:
            hint_y += hint_row_h
            if hint_y > panel_y + panel_h - PANEL_PAD:
                break
            c.paint.textsize = HINT_FONT_SIZE
            c.paint.color = HINT_CMD_COLOR
            c.draw_text(_fit_text(c, cmd, cmd_col_w), hint_pad_x, hint_y)
            c.paint.color = HINT_COLOR
            c.draw_text(_fit_text(c, desc, desc_col_w), hint_pad_x + cmd_col_w, hint_y)

    # Continuous capture — emit on every draw. emit_if_changed dedupes by
    # snapshot equality so this is a no-op when nothing changed since the
    # last earlier-stage hook fired (set_cursor, recompute_hats, show, hide).
    from .internal import debug as prose_overlay_debug
    prose_overlay_debug.emit_if_changed("draw")

    return panel_rect
