"""LayoutModel-consuming paint path — Move 4e Commit 2 (side-by-side).

This module ships a NEW paint entrypoint ``draw_from_model(canvas,
overlay, model)`` that reads a fully-baked ``LayoutModel`` and paints
from it. It exists side-by-side with the existing paint code
(``ui/draw_tokens.py:_draw_token_rows``, ``ui/draw_panels.py:
draw_homophone_panels``, ``ui/help.py:draw_help_panel``) which remains
the default paint path.

Gate
----

The env var ``PROSE_OVERLAY_LAYOUT_MODEL`` controls which path
``draw_overlay`` uses:

* unset / empty / ``"0"`` → old paint path (default).
* ``"1"`` (or any truthy value) → this module's ``draw_from_model``.

Rationale for env-gating (from Move 4e commit plan):

    ``ui/draw_tokens.py:_draw_token_rows`` is a 210-line paint routine
    that does per-character measurement for both letter hats AND shape
    hats, plus segmented underlines with active/inactive styles.
    Rebuilding it to consume ``TokenLayout`` alone (instead of iterating
    rows + inline measurement) is a whole additional sub-move — it
    touches every branch of the token paint tree. We keep the old paint
    as the default and ship a MINIMAL new path that demonstrates the
    wire-up; extending the new path to reach paint parity is a future
    sub-move.

What this paint path draws
--------------------------

The minimal-parity path draws:

1. Panel frame (fallback-color-aware).
2. Overlay close hint (via ``overlay.draw_close_hint``).
3. When ``model.tokens`` is empty AND ``model.cursor`` is set: the
   "listening..." placeholder text.
4. Per-token text (no hats, no shapes, no underlines — those live in
   ``TokenLayout.hat`` / ``.shape`` / ``.underline_segments`` and can
   be wired in a follow-up sub-move by walking each ``TokenLayout``
   field).
5. Cursor line (from ``model.cursor``).

Deliberately NOT drawn in this minimal path:

* Letter hats, shape hats, underline segments (fields exist on
  ``TokenLayout`` — future sub-move walks them).
* Selection / flash rects (fields on ``model.selection`` /
  ``model.flash`` — same pattern).
* Homophone bubbles (``model.bubbles`` list is populated by the
  orchestrator; rendering them requires the shape SVG rasterizer at
  paint time).
* Help pager / target label / help side ring (``model.help`` present;
  the rotating side hints are not on the model yet per Move 4d
  docstring — a separate ring-buffer input is needed).

Every one of the un-drawn items is a follow-up sub-move: the field is
on the model, the paint step just needs to read it. Keeping the initial
paint minimal proves the wire-up works without rebuilding the entire
paint tree in one commit.

Why a separate module
---------------------

``ui/draw.py`` orchestrates the two paths (env check → old path or new
path). Splitting the new path into its own file keeps ``draw.py`` from
growing another 200 lines and makes it clear which code path is which
when reading commits.
"""

from __future__ import annotations

from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect as _TalonRect

from ....utils.overlay_kit import DismissibleOverlay, draw_panel_frame
from ..internal.draw_constants import (
    BG_COLOR,
    BG_COLOR_FALLBACK,
    BORDER_COLOR,
    BORDER_COLOR_FALLBACK,
    CURSOR_CHANGE_ZONE_ALPHA,
    CURSOR_CHANGE_ZONE_WIDTH,
    CURSOR_COLOR_CHANGE,
    CURSOR_COLOR_NAVIGATE,
    CURSOR_WIDTH,
    DOT_GAP_Y,
    DOT_RADIUS,
    LISTENING_COLOR,
    PANEL_PAD,
    PANEL_RADIUS,
    TOKEN_COLOR,
    TOKEN_FONT_SIZE,
)
from .layout import LayoutModel


def draw_from_model(
    c: SkiaCanvas,
    overlay: DismissibleOverlay,
    model: LayoutModel,
) -> _TalonRect:
    """Paint the overlay from a ``LayoutModel``.

    Returns the panel rect as a ``talon.ui.Rect`` (converted from the
    model's frozen ``Rect``) so callers observe the same return contract
    as ``draw_overlay``.

    See the module docstring for what this paint path currently draws
    and what it deliberately skips.
    """
    panel_rect = _TalonRect(
        model.panel.x, model.panel.y, model.panel.w, model.panel.h
    )

    # Zero-panel short-circuit — the orchestrator returns a zero rect
    # when state.screen_rect is None. Skip paint entirely.
    if panel_rect.width <= 0 or panel_rect.height <= 0:
        return panel_rect

    # --- Panel frame ---
    c.paint.typeface = "Menlo"
    bg = BG_COLOR_FALLBACK if model.using_fallback else BG_COLOR
    border = BORDER_COLOR_FALLBACK if model.using_fallback else BORDER_COLOR
    draw_panel_frame(c, panel_rect, PANEL_RADIUS, bg, border)
    overlay.draw_close_hint(
        c, panel_rect.x, panel_rect.y, panel_rect.width, PANEL_PAD
    )

    # --- Listening placeholder for the empty-buffer case ---
    # Matches ui/draw.py lines 149-166: when the buffer is empty AND a
    # cursor is set at 0, paint the "listening..." text plus the cursor.
    if not model.tokens:
        c.paint.textsize = TOKEN_FONT_SIZE
        c.paint.color = LISTENING_COLOR
        # Same y anchor draw_overlay uses: content_area.y + hat band +
        # font size. The model's content_area already carries the padded
        # origin; text baseline sits at content_area.y + (DOT_RADIUS *
        # 2) + DOT_GAP_Y + TOKEN_FONT_SIZE.
        text_y = model.content_area.y + (DOT_RADIUS * 2) + DOT_GAP_Y + TOKEN_FONT_SIZE
        c.draw_text("listening...", model.content_area.x, text_y)
    else:
        # --- Token text ---
        # Walk model.tokens and paint text at each token's rect. Hats /
        # shapes / underlines / highlights are deliberately deferred to
        # a follow-up sub-move (see module docstring).
        c.paint.textsize = TOKEN_FONT_SIZE
        c.paint.color = TOKEN_COLOR
        for tok in model.tokens:
            # Token text baseline in the paint code (see
            # ui/draw_tokens.py:279) sits at y_base + (DOT_RADIUS*2) +
            # DOT_GAP_Y + TOKEN_FONT_SIZE where y_base is the row's top
            # (= TokenLayout.rect.y). The rect itself has that height
            # baked in (see ui/layout_tokens.py:588-593).
            baseline_y = tok.rect.y + (DOT_RADIUS * 2) + DOT_GAP_Y + TOKEN_FONT_SIZE
            c.draw_text(tok.text, tok.rect.x, baseline_y)

    # --- Cursor ---
    # Model.cursor is None when the paint code should skip. blink_on is
    # kept on the model rather than gated at composition (see
    # ui/layout.py CursorLayout docstring); paint layer gates.
    if model.cursor is not None and model.cursor.blink_on:
        cursor = model.cursor
        c.paint.style = c.paint.Style.FILL
        if cursor.change_mode:
            # Amber insertion-zone behind the cursor line, then the
            # cursor line proper. Matches ui/draw_tokens.py:draw_cursor.
            c.paint.color = CURSOR_COLOR_CHANGE[:6] + CURSOR_CHANGE_ZONE_ALPHA
            c.draw_rect(
                _TalonRect(
                    cursor.rect.x + 1 - CURSOR_CHANGE_ZONE_WIDTH / 2,
                    cursor.rect.y,
                    CURSOR_CHANGE_ZONE_WIDTH,
                    cursor.rect.h,
                )
            )
            c.paint.color = CURSOR_COLOR_CHANGE
        else:
            c.paint.color = CURSOR_COLOR_NAVIGATE
        c.draw_rect(
            _TalonRect(
                cursor.rect.x,
                cursor.rect.y,
                CURSOR_WIDTH,
                cursor.rect.h,
            )
        )

    return panel_rect


__all__ = ["draw_from_model"]
