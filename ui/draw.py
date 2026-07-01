"""Prose Overlay Draw — main draw entrypoint.

Step 15 of the paint-pipeline retirement (2026-07-01): consolidated
``ui/draw_from_model.py`` into this module. The old file has been
deleted. ``draw_overlay`` now inlines the full compose-and-paint
pipeline: (1) build a ``LayoutModel`` via
``ui/layout_root.py:layout()``; (2) mirror the overflow flag onto the
module-level ``_hints_hidden_by_overflow`` for debug snapshots;
(3) run ``paint_ops.execute(to_paint_ops(model), c)``; (4) emit the
direct-paint concerns (target label, rotating side hints); (5) fire
the debug capture hook.

What still lives outside the pipeline (paint-time-only concerns):

* Panel close hint — composed via ``overlay.draw_close_hint`` (text +
  X-mark line segments in one helper call).
* Target label (bottom-left) — needs the mutable ``HINT_FONT_SIZE``
  module-level global adjusted by ``help_bigger`` / ``help_smaller``.
* Rotating side hints — driven by wall-clock time via
  ``help.rotate_help_ring_buffer``; not expressible on the pure model
  without a rotation-cursor input.

All three are painted directly from ``draw_overlay``. Everything else
is on the model.

Module-level globals retained for debug + tooling:

* ``HINT_FONT_SIZE`` — help panel font size, mutable via
  ``help_bigger`` / ``help_smaller`` commands. Read by ``draw_overlay``
  and by ``draw_help_panel`` for its own font size.
* ``_hints_hidden_by_overflow`` — mirror of
  ``LayoutModel.hints_hidden_by_overflow`` from the most recent draw,
  read by ``internal/debug.py:_snapshot()`` for the debug JSON.
"""

from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ....utils.overlay_kit import DismissibleOverlay
from ..internal.draw_constants import (
    HINT_CMD_COLOR,
    HINT_COLOR,
    PANEL_PAD,
)
from .layout_root import layout as _compose_layout
from .paint_ops import execute as _execute, to_paint_ops as _to_paint_ops
from .help import (
    draw_help_panel,
    rotate_help_ring_buffer,
    HELP_COMMAND_POOL,
)
from .history_panel import draw_history_panel, HISTORY_PAGE_SIZE
from .draw_tokens import _fit_text
from ..internal.instance import instance

# Re-export for canvas.py which imports draw_help_panel + draw_history_panel
# from this module.
__all__ = [
    "draw_overlay",
    "draw_help_panel",
    "draw_history_panel",
    "HISTORY_PAGE_SIZE",
    "HINT_FONT_SIZE",
]

# ---------------------------------------------------------------------------
# Layout fractions (re-exported for external inspection; canonical copy lives
# in ui/layout_root.py which is what actually drives the layout).
# ---------------------------------------------------------------------------
CONTENT_W_FRACTION = 0.80
HELP_W_FRACTION = 0.20
PANEL_Y_OFFSET = 0

# ---------------------------------------------------------------------------
# Mutable font-size — adjusted at runtime by help_bigger / help_smaller.
# Read by draw_overlay (target label + rotating side hints) and by
# draw_help_panel (paginated pager rows).
# ---------------------------------------------------------------------------
HINT_FONT_SIZE = 12

# ---------------------------------------------------------------------------
# Overflow state — set during each draw, read by debug snapshot.
#
# ``internal/debug.py:_snapshot`` reads this to include the overflow state
# in the debug JSON. Set to the LayoutModel's ``hints_hidden_by_overflow``
# each draw so a debug capture between draws reflects the current state.
# ---------------------------------------------------------------------------
_hints_hidden_by_overflow: bool = False


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
    """Compose a LayoutModel + paint from it.

    Builds the model via ``ui.layout_root.layout()`` and dispatches paint
    through the ``paint_ops`` pipeline plus the three direct-paint
    concerns (close hint, target label, rotating side hints).

    The ``tokens`` argument is retained for the current caller contract
    (``ui/canvas.py:draw_overlay`` passes it) even though the
    orchestrator sources tokens from ``state.buffer.get_tokens()``. The
    two agree in practice — canvas.py passes exactly what the buffer
    holds.

    Returns the panel ``Rect`` for click-outside detection in canvas.py.
    """
    global _hints_hidden_by_overflow

    # --- Compose the LayoutModel ---
    model = _compose_layout(
        instance.state,
        c,
        overlay,
        hat_assignments=hat_assignments,
        cursor=cursor,
        change_mode=change_mode,
        blink_on=blink_on,
        flash_indices=flash_indices,
        flash_color=flash_color,
        selection=selection,
        target_label=target_label,
        using_fallback=using_fallback,
        hint_font_size=HINT_FONT_SIZE,
    )
    # Mirror overflow state so debug snapshots pick it up.
    _hints_hidden_by_overflow = model.hints_hidden_by_overflow

    panel_rect = Rect(model.panel.x, model.panel.y, model.panel.w, model.panel.h)

    # Zero-panel short-circuit — the orchestrator returns a zero rect
    # when state.screen_rect is None. Skip paint entirely (matches the
    # historical draw_overlay behavior at line 154 of the pre-Step-11
    # module).
    if panel_rect.width <= 0 or panel_rect.height <= 0:
        return panel_rect

    # --- Font typeface (also inherited by every downstream Skia call) ---
    c.paint.typeface = "Menlo"

    # --- Close hint (direct — helper composes text + X-mark lines) ---
    # overlay.draw_close_hint calls Skia internally to paint text plus
    # two line segments in one call. Expressing that as PaintOps would
    # require pulling overlay_kit internals into the pure builder; the
    # hint stays direct.
    overlay.draw_close_hint(
        c, panel_rect.x, panel_rect.y, panel_rect.width, PANEL_PAD
    )

    # --- PaintOp pipeline ---
    # Panel frame, listening placeholder, per-token text, hats, shapes,
    # underlines, cursor, help-zone separator, selection, flash, bubbles
    # — all emitted by to_paint_ops(model) and dispatched by execute().
    _execute(_to_paint_ops(model), c)

    # --- Target label (bottom-left window-target hint) ---
    # Direct paint — HINT_FONT_SIZE is a mutable module-level global
    # adjusted by help_bigger / help_smaller commands. TextOp doesn't
    # carry a mutable font-size handle so this stays outside the
    # pipeline. Matches the historical draw_overlay behavior at lines
    # 275-279 of the pre-Step-11 module.
    if model.target_label and not model.hints_hidden_by_overflow:
        c.paint.textsize = HINT_FONT_SIZE
        c.paint.color = HINT_CMD_COLOR
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
    # the target label above. Matches historical draw_overlay behavior
    # at lines 281-304 of the pre-Step-11 module.
    if model.help_area is not None:
        hint_row_h = HINT_FONT_SIZE + 6
        # help_area.w on the model already excludes the 2*PANEL_PAD
        # margin (ui/layout_root.py sets help_area.w = help_w -
        # PANEL_PAD*2). The old paint code used the RAW help_w and
        # subtracted padding inside the loop. Both derivations reach
        # the same cmd_col_w value.
        cmd_col_w = model.help_area.w * 0.48
        desc_col_w = model.help_area.w - cmd_col_w
        hint_pad_x = model.help_area.x + PANEL_PAD
        max_rows = max(1, int((panel_rect.height - PANEL_PAD * 2) / hint_row_h))
        side_cmds = rotate_help_ring_buffer(
            min(max_rows, len(HELP_COMMAND_POOL))
        )
        hint_y = panel_rect.y + PANEL_PAD
        for cmd, desc in side_cmds:
            hint_y += hint_row_h
            if hint_y > panel_rect.y + panel_rect.height - PANEL_PAD:
                break
            c.paint.textsize = HINT_FONT_SIZE
            c.paint.color = HINT_CMD_COLOR
            c.draw_text(_fit_text(c, cmd, cmd_col_w), hint_pad_x, hint_y)
            c.paint.color = HINT_COLOR
            c.draw_text(
                _fit_text(c, desc, desc_col_w),
                hint_pad_x + cmd_col_w,
                hint_y,
            )

    # --- Debug capture — emit on every draw ---
    # emit_if_changed dedupes by snapshot equality so this is a no-op
    # when nothing changed since the last earlier-stage hook fired
    # (set_cursor, recompute_hats, show, hide).
    from ..internal import debug as prose_overlay_debug
    prose_overlay_debug.emit_if_changed("draw")

    return panel_rect
