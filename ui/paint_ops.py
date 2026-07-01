"""PaintOp union — pure data description of one paint step.

This module is Move 5 of the pure-function refactor. It sits between the
``LayoutModel`` producer (``ui/layout_root.py`` at Move 4e) and the Skia
paint sink (``ui/draw_from_model.py`` after this move). The pipeline
target from ``ui/layout.py``'s module docstring is:

    layout(state, canvas, overlay) -> LayoutModel     # Move 4e
    to_paint_ops(model)            -> list[PaintOp]   # THIS MOVE
    execute(ops, canvas)                              # THIS MOVE
        # thin Skia adapter — the only impure sink

Why a PaintOp layer at all
--------------------------

``LayoutModel`` is a rich tree — nested dataclasses for tokens, hats,
overlays, help pages, cursor. Handing that directly to a Skia sink
would force the sink to know about every field on every node. A flat
``list[PaintOp]`` intermediate:

* Lets the *builder* be pure Python that a headless test can run without
  touching Talon or Skia. The paint plan for any state is inspectable
  as a plain Python list.
* Lets the *sink* be dumb — walk the list, dispatch by type, call one
  Skia method per op. No branching on domain concepts.
* Makes it possible to snapshot-test paint plans: "same state should
  produce the same ops list" is a one-line assertion.
* Opens the door to alternate renderers (SVG dump, JSON export for
  debug snapshots, headless raster) without rebuilding the sink.

Scope for Move 5
----------------

This move's ``to_paint_ops`` covers ONLY what
``ui/draw_from_model.py``'s minimal paint scope covers today (see that
module's docstring for the full deferred list). Namely:

* Listening placeholder text (when the buffer is empty).
* Per-token text (no hats, no shapes, no underlines).
* Cursor rect — with the change-mode insertion zone when applicable.

Deliberately DEFERRED to follow-up sub-moves (fields exist on
``LayoutModel`` but this move does not emit ops for them):

* Panel frame with rounded corners — routed AROUND the PaintOp pipeline
  in ``draw_from_model.py`` via the ``draw_panel_frame`` helper because
  rounded rects need a Skia ``Path``. Introducing a ``PathOp`` or
  ``RoundedRectOp`` is scope creep for this move; the panel frame stays
  direct.
* Overlay close hint — routed AROUND via ``overlay.draw_close_hint``
  because that helper composes text + two line segments in one call.
* Letter hats, shape hats, homophone underlines (``HatMark``,
  ``ShapeMark``, ``UnderlineSegment``).
* Selection overlay, flash overlay (``SelectionOverlay``,
  ``FlashOverlay``).
* Homophone bubbles, help side panel (``BubbleLayout``, ``HelpLayout``).

Every deferred item has a field on ``LayoutModel`` — the future sub-move
just needs to walk it and emit the corresponding ops. The op vocabulary
here (``RectOp`` / ``TextOp`` / ``LineOp`` / ``EllipseOp``) covers those
future cases too; ``GlyphOp`` for SVG shape hats is the one addition
that will be needed.

Purity contract
---------------

``to_paint_ops`` is pure. It:

* Reads only its ``layout`` argument. No module-level state, no globals,
  no ``instance`` reads, no Talon settings, no time.
* Emits a new ``list`` each call. Callers can inspect / diff / snapshot.
* Does NOT mutate ``layout`` or any of its subfields.
* Same input → same output. Enforced by the L1 determinism tests.

``execute`` is the only impure function in this module. It writes to
``canvas.paint`` (color / style / textsize / stroke_width) and calls
``canvas.draw_rect`` / ``canvas.draw_text`` / ``canvas.draw_line`` /
``canvas.draw_circle``. Nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from .layout import LayoutModel


# ---------------------------------------------------------------------------
# PaintOp primitives
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RectOp:
    """A single rectangle paint op.

    Fields:
        x, y  : top-left corner in absolute screen coordinates.
        w, h  : width and height in px.
        color : hex color with alpha (``"rrggbbaa"``) OR without
                (``"rrggbb"``); the sink writes it verbatim to
                ``canvas.paint.color`` which accepts both forms.
        stroke: False → filled rectangle. True → outlined rectangle
                with ``stroke_width`` line thickness.
        stroke_width: line width in px when ``stroke=True``. Ignored
                      when ``stroke=False``.

    Note: rounded corners are NOT expressible via ``RectOp``. Rounded
    rects (panel frame, chip backgrounds) still go through the
    ``draw_panel_frame`` / dedicated helpers in the sink. See module
    docstring "Scope for Move 5" for rationale.
    """

    x: float
    y: float
    w: float
    h: float
    color: str
    stroke: bool = False
    stroke_width: float = 1.0


@dataclass(frozen=True)
class TextOp:
    """A single text paint op.

    Fields:
        x, y      : baseline anchor in absolute screen coordinates.
                    ``y`` is the baseline (matches Skia's
                    ``draw_text(text, x, y)`` where y is the baseline,
                    NOT the top of the glyph box).
        text      : the string to paint.
        font_size : point size, written to ``canvas.paint.textsize``.
        color     : hex color with or without alpha.
    """

    x: float
    y: float
    text: str
    font_size: float
    color: str


@dataclass(frozen=True)
class LineOp:
    """A single line-segment paint op.

    Used for separators, close-hint X marks (when future sub-moves
    inline them), and any hairline geometry.

    Fields:
        x0, y0 : start point in absolute screen coordinates.
        x1, y1 : end point in absolute screen coordinates.
        color  : hex color.
        width  : stroke width in px, written to
                 ``canvas.paint.stroke_width``.
    """

    x0: float
    y0: float
    x1: float
    y1: float
    color: str
    width: float = 1.0


@dataclass(frozen=True)
class EllipseOp:
    """A single ellipse / circle paint op.

    Used for letter-hat dots when the future sub-move wires them
    through ops. Only ``cx``, ``cy`` and a single radius are needed
    for the current use cases (dots are circles); ``rx`` and ``ry``
    are kept distinct so future non-circular use is expressible
    without another op type. The sink uses ``max(rx, ry)`` when
    calling ``canvas.draw_circle`` — sufficient for the equal-radius
    dot use case; a proper ellipse path would go through
    ``canvas.draw_path`` and is deferred.

    Fields:
        cx, cy : center in absolute screen coordinates.
        rx, ry : x-radius and y-radius. Circles: rx == ry.
        color  : hex color.
        stroke : False → filled. True → outlined.
    """

    cx: float
    cy: float
    rx: float
    ry: float
    color: str
    stroke: bool = False


# Union alias. New op types get added here.
PaintOp = Union[RectOp, TextOp, LineOp, EllipseOp]


# ---------------------------------------------------------------------------
# Pure builder — LayoutModel → list[PaintOp]
# ---------------------------------------------------------------------------

# Paint-side constants live in ``internal/draw_constants.py`` and are
# imported inside ``to_paint_ops`` (not at module top level) so this
# module stays cheap to import from headless tests that don't need the
# constants. The constants are pure numeric / string values — no Skia
# or Talon dependency — so the import is safe from any environment;
# the localization is a style choice, not a technical requirement.

def to_paint_ops(layout: LayoutModel) -> list[PaintOp]:
    """Walk ``layout`` and emit paint ops in back-to-front paint order.

    Pure function. Does not read state outside ``layout``. Does not
    mutate ``layout`` (or its subfields, which are frozen dataclasses
    anyway; the ``tokens`` list is read but not modified).

    Returns a fresh ``list`` each call. Same ``LayoutModel`` in ⇒
    same ``list`` out (structural equality).

    Op order (matches ``draw_from_model.py``'s current paint order):

        1. Listening placeholder text (when ``layout.tokens`` is empty).
        2. Per-token text (when ``layout.tokens`` is non-empty).
        3. Cursor change-zone rect (when ``layout.cursor`` is present
           AND ``blink_on=True`` AND ``change_mode=True``).
        4. Cursor rect proper (when ``layout.cursor`` is present AND
           ``blink_on=True``).

    Panel frame + close hint are routed AROUND this pipeline in the
    sink (rounded rects + helper-composed close hint). See module
    docstring.
    """
    # Local import — see module-level note. Keeps this module importable
    # in isolation for the paint-ops-only tests and keeps the constants
    # pipeline explicit.
    from ..internal.draw_constants import (
        CURSOR_CHANGE_ZONE_ALPHA,
        CURSOR_CHANGE_ZONE_WIDTH,
        CURSOR_COLOR_CHANGE,
        CURSOR_COLOR_NAVIGATE,
        CURSOR_WIDTH,
        DOT_GAP_Y,
        DOT_RADIUS,
        LISTENING_COLOR,
        TOKEN_COLOR,
        TOKEN_FONT_SIZE,
    )

    ops: list[PaintOp] = []

    # --- Listening placeholder OR per-token text ---
    if not layout.tokens:
        # Empty buffer: paint the "listening..." affordance at the
        # content area's origin with the same baseline math the current
        # draw_from_model.py uses (content_area.y + hat band + font).
        text_y = (
            layout.content_area.y
            + (DOT_RADIUS * 2)
            + DOT_GAP_Y
            + TOKEN_FONT_SIZE
        )
        ops.append(
            TextOp(
                x=layout.content_area.x,
                y=text_y,
                text="listening...",
                font_size=TOKEN_FONT_SIZE,
                color=LISTENING_COLOR,
            )
        )
    else:
        for tok in layout.tokens:
            # TokenLayout.rect.y is the row top. The token text baseline
            # sits at rect.y + hat band + font size, matching
            # ui/draw_tokens.py:279 and ui/draw_from_model.py:157.
            baseline_y = (
                tok.rect.y
                + (DOT_RADIUS * 2)
                + DOT_GAP_Y
                + TOKEN_FONT_SIZE
            )
            ops.append(
                TextOp(
                    x=tok.rect.x,
                    y=baseline_y,
                    text=tok.text,
                    font_size=TOKEN_FONT_SIZE,
                    color=TOKEN_COLOR,
                )
            )

    # --- Cursor ---
    # Paint-side blink gate: if blink_on is False, emit nothing so the
    # paint sequence is byte-equivalent to the current draw_from_model.
    # Matches ui/layout.py:CursorLayout docstring — the field lives on
    # the model so a debug snapshot can distinguish "no cursor" from
    # "cursor blinking off," but the paint step skips it.
    cursor = layout.cursor
    if cursor is not None and cursor.blink_on:
        if cursor.change_mode:
            # Amber insertion-zone rect BEHIND the cursor line. Matches
            # ui/draw_tokens.py:draw_cursor and ui/draw_from_model.py
            # lines 167-179 verbatim: color is CHANGE hex[:6] + alpha,
            # x offset is `cursor.rect.x + 1 - CURSOR_CHANGE_ZONE_WIDTH/2`.
            ops.append(
                RectOp(
                    x=cursor.rect.x + 1 - CURSOR_CHANGE_ZONE_WIDTH / 2,
                    y=cursor.rect.y,
                    w=CURSOR_CHANGE_ZONE_WIDTH,
                    h=cursor.rect.h,
                    color=CURSOR_COLOR_CHANGE[:6] + CURSOR_CHANGE_ZONE_ALPHA,
                    stroke=False,
                )
            )
            cursor_color = CURSOR_COLOR_CHANGE
        else:
            cursor_color = CURSOR_COLOR_NAVIGATE

        # Cursor line proper — 1-2 px wide vertical rect at the cursor
        # x. Matches draw_from_model.py lines 182-189.
        ops.append(
            RectOp(
                x=cursor.rect.x,
                y=cursor.rect.y,
                w=CURSOR_WIDTH,
                h=cursor.rect.h,
                color=cursor_color,
                stroke=False,
            )
        )

    return ops


# ---------------------------------------------------------------------------
# Side-effecting sink — the only impure function in this module.
# ---------------------------------------------------------------------------


def execute(ops: list[PaintOp], canvas) -> None:
    """Dispatch ``ops`` to Skia calls on ``canvas``.

    ``canvas`` is a ``talon.skia.canvas.Canvas`` (typed loosely to keep
    this module headless-importable — the L1 tests substitute a fake).

    Each op maps to exactly one draw call. Paint attributes
    (``color``, ``style``, ``textsize``, ``stroke_width``) are set
    per-op so ops are independent and reordering does not change the
    result up to paint order semantics.

    Unknown op type ⇒ ``TypeError``. Fail-loud so a future sub-move
    that emits a new op type without extending this sink is caught
    immediately.
    """
    # talon.ui.Rect is only needed inside this function; imported here
    # so ``to_paint_ops`` and the dataclasses above have no Talon
    # dependency (L1 tests import this module with talon stubbed).
    from talon.ui import Rect as _TalonRect

    for op in ops:
        if isinstance(op, RectOp):
            if op.stroke:
                # Outlined rect. Set STROKE style + width, paint, then
                # restore FILL so subsequent ops that don't set style
                # default to fill (matches ui/draw.py idiom at line 287).
                canvas.paint.style = canvas.paint.Style.STROKE
                canvas.paint.stroke_width = op.stroke_width
                canvas.paint.color = op.color
                canvas.draw_rect(_TalonRect(op.x, op.y, op.w, op.h))
                canvas.paint.style = canvas.paint.Style.FILL
            else:
                canvas.paint.style = canvas.paint.Style.FILL
                canvas.paint.color = op.color
                canvas.draw_rect(_TalonRect(op.x, op.y, op.w, op.h))
        elif isinstance(op, TextOp):
            canvas.paint.color = op.color
            canvas.paint.textsize = op.font_size
            canvas.draw_text(op.text, op.x, op.y)
        elif isinstance(op, LineOp):
            canvas.paint.style = canvas.paint.Style.STROKE
            canvas.paint.stroke_width = op.width
            canvas.paint.color = op.color
            canvas.draw_line(op.x0, op.y0, op.x1, op.y1)
            canvas.paint.style = canvas.paint.Style.FILL
        elif isinstance(op, EllipseOp):
            if op.stroke:
                canvas.paint.style = canvas.paint.Style.STROKE
            else:
                canvas.paint.style = canvas.paint.Style.FILL
            canvas.paint.color = op.color
            # Single-radius circle path. Non-circular ellipses would
            # need canvas.draw_path with a Skia Path — deferred.
            canvas.draw_circle(op.cx, op.cy, max(op.rx, op.ry))
            canvas.paint.style = canvas.paint.Style.FILL
        else:
            raise TypeError(
                f"execute(): unknown PaintOp type {type(op).__name__!r}"
            )


__all__ = [
    "RectOp",
    "TextOp",
    "LineOp",
    "EllipseOp",
    "PaintOp",
    "to_paint_ops",
    "execute",
]
