"""Prose Overlay draw helper — text truncation.

Step 12 of the paint-pipeline retirement: this module used to hold the
imperative token/hat/shape/underline paint routines
(``_flow_layout``, ``draw_cursor``, ``_draw_token_rows``,
``_maybe_log_segment_fallback``, ``homophone_segment_width``,
``_LOGGED_SEGMENT_FALLBACKS``). All of that has been retired —
composition lives in ``ui/layout_root.py`` + the sub-builders, paint
lives in ``ui/paint_ops.py``, and dispatch lives in
``ui/draw_from_model.py``.

Only ``_fit_text`` survives here: it's used by ``draw_from_model.py``
for the rotating side hints (which stay outside the pure pipeline
because they depend on wall-clock time via
``rotate_help_ring_buffer``). Text-truncation-with-ellipsis is a pure
Skia-canvas measurement helper that doesn't fit the ``TextOp`` schema
today — the ops pipeline pre-bakes text content, and truncation is a
runtime decision keyed on the caller's column width.

A future move could either:
  * Move ``_fit_text`` next to its sole caller (``draw_from_model.py``)
    and delete this file entirely.
  * Extend ``TextOp`` with a ``max_width`` field and have the sink
    truncate at paint time, letting the whole rotating-side-hints
    branch flow through the pipeline once time-dependent inputs are
    modelable.

Neither is in scope for the retirement — keeping the file alive at
minimum footprint keeps callers working with no behavior change.
"""

from talon.skia.canvas import Canvas as SkiaCanvas


def _fit_text(c: SkiaCanvas, text: str, max_w: float) -> str:
    """Truncate ``text`` with an ellipsis so it fits within ``max_w`` px.

    Measures via ``c.paint.measure_text``. Returns the full string when
    it already fits; walks the string end-to-start otherwise, appending
    ``…`` until the truncated form fits. When even the ellipsis alone
    doesn't fit, returns the empty string.

    Used by ``draw_from_model.py`` for the rotating side-hints column
    (each row's cmd + desc text is truncated to fit its column width).
    """
    if c.paint.measure_text(text)[1].width <= max_w:
        return text
    ellipsis = "…"
    ellipsis_w = c.paint.measure_text(ellipsis)[1].width
    for end in range(len(text) - 1, 0, -1):
        candidate = text[:end] + ellipsis
        if c.paint.measure_text(candidate)[1].width <= max_w:
            return candidate
    return ellipsis if ellipsis_w <= max_w else ""


__all__ = ["_fit_text"]
