"""Prose Overlay Draw -- main draw entrypoint.

Step 11 of the paint-pipeline retirement: the env-gated old paint path
has been removed. ``draw_overlay`` now unconditionally composes a
``LayoutModel`` via ``ui/layout_root.py:layout()`` and paints from it via
``ui/draw_from_model.py:draw_from_model``. Panel frame, per-token text,
hats, shapes, underlines, cursor, selection, flash, bubbles, and the
help-zone separator all flow through the pure ``paint_ops`` pipeline.

What still lives outside the pipeline (paint-time-only concerns):

* Panel close hint — composed via ``overlay.draw_close_hint`` (text +
  X-mark line segments in one helper call).
* Target label (bottom-left) — needs the mutable ``HINT_FONT_SIZE``
  module-level global adjusted by ``help_bigger`` / ``help_smaller``.
* Rotating side hints — driven by wall-clock time via
  ``help.rotate_help_ring_buffer``; not expressible on the pure model
  without a rotation-cursor input.

All three are painted directly from ``draw_from_model``. Everything else
is on the model.

Module-level globals retained for debug + tooling:

* ``HINT_FONT_SIZE`` — help panel font size, mutable via
  ``help_bigger`` / ``help_smaller`` commands. Read by
  ``draw_from_model`` and by ``draw_help_panel``.
* ``_hints_hidden_by_overflow`` — mirror of
  ``LayoutModel.hints_hidden_by_overflow`` from the most recent draw,
  read by ``internal/debug.py:_snapshot()`` for the debug JSON.
"""

from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ....utils.overlay_kit import DismissibleOverlay
from .draw_from_model import draw_from_model as _draw_from_model
from .layout_root import layout as _compose_layout
from .help import draw_help_panel
from .history_panel import draw_history_panel, HISTORY_PAGE_SIZE
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
# Read by ui/draw_from_model.py (target label + rotating side hints) and
# ui/help.py (draw_help_panel).
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

    Thin wrapper: builds the model via ``ui.layout_root.layout()`` and
    delegates paint to ``ui.draw_from_model.draw_from_model``. The
    ``tokens`` argument is retained for the current caller contract
    (``ui/canvas.py:draw_overlay`` passes it) even though the
    orchestrator sources tokens from ``state.buffer.get_tokens()``. The
    two agree in practice — canvas.py passes exactly what the buffer
    holds.

    Returns the panel ``Rect`` for click-outside detection in canvas.py.
    """
    global _hints_hidden_by_overflow

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

    panel_rect = _draw_from_model(c, overlay, model)

    # Continuous capture — emit on every draw. emit_if_changed dedupes by
    # snapshot equality so this is a no-op when nothing changed since the
    # last earlier-stage hook fired (set_cursor, recompute_hats, show,
    # hide).
    from ..internal import debug as prose_overlay_debug
    prose_overlay_debug.emit_if_changed("draw")

    return panel_rect
