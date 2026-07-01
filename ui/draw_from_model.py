"""LayoutModel-consuming paint path — Move 4e Commit 2 (side-by-side).

Move 5 update: the token/cursor portion of this module now routes
through ``ui/paint_ops.py``. ``draw_from_model`` builds a
``list[PaintOp]`` via ``to_paint_ops(model)`` and hands it to
``execute(ops, canvas)``. Panel frame + overlay close hint stay direct
(rounded rects + helper-composed hint — see ``paint_ops.py`` module
docstring "Scope for Move 5" for rationale).

This module ships a paint entrypoint ``draw_from_model(canvas,
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

1. Panel frame (fallback-color-aware) — direct via ``draw_panel_frame``
   because rounded corners are not modelable via ``RectOp``.
2. Overlay close hint (via ``overlay.draw_close_hint``) — direct
   because the helper composes text + X-mark lines internally.
3. Routed through the PaintOp pipeline (``to_paint_ops`` +
   ``execute``, Move 5):
     a. When ``model.tokens`` is empty AND ``model.cursor`` is set: the
        "listening..." placeholder text.
     b. Per-token text (no hats, no shapes, no underlines — those live
        in ``TokenLayout.hat`` / ``.shape`` / ``.underline_segments`` and
        can be wired in a follow-up sub-move by walking each
        ``TokenLayout`` field and emitting the corresponding ops).
     c. Cursor line and (in change-mode) the amber insertion zone
        (from ``model.cursor``).

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

from ....utils.overlay_kit import DismissibleOverlay
from ..internal.draw_constants import PANEL_PAD
from .layout import LayoutModel
from .paint_ops import execute, to_paint_ops


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

    # --- Font typeface ---
    # Panel frame + border move into the PaintOp pipeline (Step 10 of
    # paint-pipeline retirement). to_paint_ops emits two RoundedRectOps
    # (filled bg + stroked border) at the top of its op list; the sink's
    # RoundedRectOp dispatch routes through overlay_kit.draw_rounded_rect
    # for byte-equivalent output.
    c.paint.typeface = "Menlo"

    # --- Close hint (direct — helper composes text + X-mark lines) ---
    # overlay.draw_close_hint calls Skia internally to paint text plus
    # two line segments in one call. Expressing that as PaintOps would
    # require pulling overlay_kit internals into the pure builder; the
    # hint stays direct.
    overlay.draw_close_hint(
        c, panel_rect.x, panel_rect.y, panel_rect.width, PANEL_PAD
    )

    # --- Everything else routes through the PaintOp pipeline ---
    # Panel frame, listening placeholder, per-token text, hats, shapes,
    # underlines, cursor, help-zone separator, selection, flash, bubbles
    # — all emitted by to_paint_ops(model) and dispatched by execute().
    execute(to_paint_ops(model), c)

    # --- Target label (bottom-left window-target hint) ---
    # Direct paint — HINT_FONT_SIZE is a mutable module-level global in
    # ui/draw.py adjusted by help_bigger / help_smaller commands. TextOp
    # doesn't carry a mutable font-size handle so this stays outside the
    # pipeline. Mirrors ui/draw.py:draw_overlay lines 275-279 exactly.
    from . import draw as _draw_mod
    from ..internal.draw_constants import HINT_CMD_COLOR as _HINT_CMD_COLOR
    if model.target_label and not model.hints_hidden_by_overflow:
        c.paint.textsize = _draw_mod.HINT_FONT_SIZE
        c.paint.color = _HINT_CMD_COLOR
        c.draw_text(
            model.target_label,
            panel_rect.x + PANEL_PAD,
            panel_rect.y + panel_rect.height - PANEL_PAD,
        )

    # --- Rotating side hints (wall-clock-driven ring buffer) ---
    # Direct paint — rotate_help_ring_buffer is time-dependent (rotates
    # one entry every HELP_ROTATE_INTERVAL_MS). Pure paint_ops can't
    # express time-dependent state without a rotation-cursor input on
    # the model; the rotating side hints stay outside the pipeline like
    # the target label above. Mirrors ui/draw.py:draw_overlay lines
    # 281-304 exactly, keyed off model.help_area (which is None when
    # hints are hidden by overflow — matches the old
    # ``not _hints_hidden_by_overflow`` guard).
    if model.help_area is not None:
        from ..internal.draw_constants import (
            HINT_COLOR as _HINT_COLOR,
            LINE_HEIGHT as _LINE_HEIGHT,
        )
        from .help import rotate_help_ring_buffer, HELP_COMMAND_POOL
        from .draw_tokens import _fit_text
        hint_font_size = _draw_mod.HINT_FONT_SIZE
        hint_row_h = hint_font_size + 6
        # help_area.w already excludes the 2*PANEL_PAD margin per the
        # ui/layout_root.py orchestrator (help_area.w = help_w - PANEL_PAD*2).
        # The old paint code used `help_w` (raw) and subtracted the
        # padding inside the loop. We derive raw help_w by adding the
        # padding back so cmd_col_w = (help_w - PANEL_PAD*2) * 0.48
        # yields the same value as model.help_area.w * 0.48.
        cmd_col_w = model.help_area.w * 0.48
        desc_col_w = model.help_area.w - cmd_col_w
        # hint_pad_x = help_x + PANEL_PAD. The model's help_area.x is
        # already the separator's x (= panel_x + content_w); PANEL_PAD
        # inside sets the first-column x. Matches ui/draw.py line 289.
        hint_pad_x = model.help_area.x + PANEL_PAD
        max_rows = max(1, int((panel_rect.height - PANEL_PAD * 2) / hint_row_h))
        side_cmds = rotate_help_ring_buffer(min(max_rows, len(HELP_COMMAND_POOL)))
        hint_y = panel_rect.y + PANEL_PAD
        for cmd, desc in side_cmds:
            hint_y += hint_row_h
            if hint_y > panel_rect.y + panel_rect.height - PANEL_PAD:
                break
            c.paint.textsize = hint_font_size
            c.paint.color = _HINT_CMD_COLOR
            c.draw_text(_fit_text(c, cmd, cmd_col_w), hint_pad_x, hint_y)
            c.paint.color = _HINT_COLOR
            c.draw_text(_fit_text(c, desc, desc_col_w), hint_pad_x + cmd_col_w, hint_y)
        # Retain _LINE_HEIGHT reference for future use.
        _ = _LINE_HEIGHT

    return panel_rect


__all__ = ["draw_from_model"]
