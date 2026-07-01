"""Pure homophone-bubble layout builder — Move 4b of the pure-function refactor.

Extracts the bubble-panel geometry math currently interleaved in
``ui/draw_panels.py:draw_homophone_panels`` (measurement pass +
placement pass) into a single pure function ``build_bubble_layouts``
that returns a fresh ``list[ui.layout.BubbleLayout]``. No consumer wires
this in yet — Move 4e will replace the measurement + placement portion
of ``draw_homophone_panels`` with a call to this builder.

Contract
--------

::

    build_bubble_layouts(
        state,
        tokens,
        token_widths,
        *,
        x_origin,
        y_start,
        max_row_w,
        panel_rect_y,
        panel_rect_h,
        anchor_position,
        alt_text_widths=None,
        max_visible_rows=None,
    ) -> list[ui.layout.BubbleLayout]

Pure-function contract (enforced by L1 tests):

* No side effects — does NOT mutate ``state`` or any argument, does NOT
  reach into the viewport, does NOT call any Talon or Skia API.
* No Talon imports — the module is safe to import from the L1 headless
  harness. All types come from ``ui.layout`` (frozen dataclasses) plus
  ``internal.draw_constants`` (module of ints/floats/strings).
* Deterministic — same inputs produce dataclass-equal
  ``list[BubbleLayout]`` output. Enforced by an L1 determinism test.

Design notes
------------

* **Why the caller passes ``alt_text_widths``.** The current
  ``ui/draw_panels.py:_measure_bubble`` measures each chip's text via
  ``c.paint.measure_text(alt)[1].width`` on a live SkiaCanvas at font
  size ``BUBBLE_CHIP_FONT_SIZE``. Skia is not available headlessly;
  keeping the builder pure means the measurement dependency is
  INJECTED. Move 4e's ``layout(state, canvas)`` wrapper will call the
  measurement pass once and hand the results in via
  ``alt_text_widths[alt_text] -> text_pixel_width``. When
  ``alt_text_widths`` is None the builder falls back to a proportional
  estimate ``len(alt) * (BUBBLE_CHIP_FONT_SIZE * 0.6)`` — good enough
  for tests to lock in the placement algebra without booting Skia; live
  paint always supplies measurements.

* **Row wrap parity.** The builder re-derives the same row-wrap that
  ``ui/layout_tokens.py:_flow_rows`` produces (mirroring the paint
  path's ``_flow_layout``). This is required because bubble ideal_x
  positions center on their token's paint x, and that x depends on
  which row the token landed on. ``max_visible_rows`` mirrors
  ``draw_overlay``'s terminal-pinned viewport trim so bubbles for
  scrolled-off tokens are OMITTED entirely (matches the current
  behavior — draw_panels.py walks the SAME ``rows`` list that
  ``_draw_token_rows`` walked, so trimmed rows have no bubbles).

* **Frozen output over mutable placement.** ``ui/layout.py:BubbleLayout``
  is a ``@dataclass(frozen=True)`` — placement decisions must be baked
  in before construction. ``internal/panel_layout.py`` uses a MUTABLE
  ``__slots__`` class ``BubbleLayout`` and mutates ``x`` in place via
  ``place_bubbles``. The two shapes DIVERGE (see the "Note on
  ``BubbleLayout`` duplication" block in ``ui/layout.py``'s module
  docstring). This module resolves the divergence by:

    1. Running the measurement pass into a lightweight private
       ``_PendingBubble`` dataclass (mutable, ``__slots__``) — the
       placement algorithm's natural shape.
    2. Running the SAME horizontal-only placement algorithm from
       ``internal/panel_layout.py:place_bubbles`` on the pending list,
       mutating each ``_PendingBubble.x`` in place.
    3. Materializing each pending record into a frozen
       ``ui.layout.BubbleLayout`` with its final ``x``.

  The ``band`` field is retained on the output at 0 to match the v2
  placement contract (single horizontal row; no vertical wrap). A later
  move will consolidate ``internal/panel_layout.py:BubbleLayout``,
  ``_PendingBubble``, and ``ui/layout.py:BubbleLayout`` into one type;
  this file does NOT touch either upstream to keep the extraction
  additive.

* **Anti-scope.** This module does NOT touch ``ui/draw.py``,
  ``ui/draw_tokens.py``, ``ui/draw_panels.py``, ``ui/layout.py``, or
  ``internal/panel_layout.py``. Move 4e will wire the builder into a
  future ``layout(state, canvas)`` composition and remove the
  measurement+placement responsibility from ``draw_homophone_panels``;
  until then paint still runs through the existing imperative path.
  Commit 1 of Move 4b ships this file with no consumers.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..internal.draw_constants import (
    BUBBLE_CHIP_FONT_SIZE,
    BUBBLE_CHIP_PAD_X,
    BUBBLE_CHIP_PAD_Y,
    BUBBLE_INNER_GAP,
    BUBBLE_OUTER_GAP,
    BUBBLE_ROW_H,
    BUBBLE_SHAPE_SCALE,
    BUBBLE_TOP_GAP,
    TOKEN_GAP_X,
)
from .layout import BubbleLayout

# ---------------------------------------------------------------------------
# Shape footprint — hard-coded to match ui/draw_panels.py's constants. The
# native SVG viewBox is 12x9 (see shim/shapes.py:_SVG_W / _SVG_H). Hard-coded
# here rather than imported because shim/shapes.py guards Skia imports behind
# a try/except and we don't want to entangle the pure builder's import time
# with Skia availability. ui/draw_panels.py already does the same trick.
# ---------------------------------------------------------------------------

_SHAPE_NATIVE_W = 12.0
_SHAPE_NATIVE_H = 9.0


# ---------------------------------------------------------------------------
# Row wrap — must match ui/layout_tokens.py:_flow_rows exactly so bubbles line
# up with the token x positions the paint pass will draw. We deliberately
# duplicate the routine here (instead of importing) so this module can be
# unit-tested standalone with a clean import graph — a Move 4e refactor will
# consolidate both callers onto a single ``layout_rowflow`` helper.
# ---------------------------------------------------------------------------


def _flow_rows(
    token_widths: list[float],
    max_w: float,
) -> list[list[tuple[int, float]]]:
    """Wrap ``token_widths`` into rows that fit ``max_w`` px each.

    Emits one row per line of the paint grid. Each row is a list of
    ``(token_idx, width)`` pairs in left-to-right order.

    Semantics MUST match ``ui/layout_tokens.py:_flow_rows`` and
    ``ui/draw_tokens.py:_flow_layout``:

    * A token that alone exceeds ``max_w`` still occupies its own row
      (no truncation, no split).
    * The between-token gap is ``TOKEN_GAP_X``; ADDED only when the
      row already has a token in it. First-token width is measured
      without a leading gap.
    * A trailing partially-filled row is flushed at the end.
    """
    rows: list[list[tuple[int, float]]] = []
    current: list[tuple[int, float]] = []
    current_w = 0.0
    for i, tw in enumerate(token_widths):
        needed = tw + (TOKEN_GAP_X if current else 0.0)
        if current and current_w + needed > max_w:
            rows.append(current)
            current = [(i, tw)]
            current_w = tw
        else:
            current.append((i, tw))
            current_w += needed
    if current:
        rows.append(current)
    return rows


# ---------------------------------------------------------------------------
# Chip-text width — the pure builder cannot call Skia. Callers with a live
# canvas pass ``alt_text_widths[alt] = pixel_width`` at BUBBLE_CHIP_FONT_SIZE.
# When absent, fall back to a proportional estimate: char count * 0.6 * font
# size. This is not accurate for variable-width fonts but keeps the builder
# usable headless for tests that lock in placement math independently of
# exact chip widths. Live paint always supplies measurements.
# ---------------------------------------------------------------------------


def _measure_chip_text_width(
    alt: str,
    alt_text_widths: dict[str, float] | None,
) -> float:
    """Return the pixel width of ``alt`` at BUBBLE_CHIP_FONT_SIZE.

    Prefers the exact ``alt_text_widths`` measurement when present; falls
    back to a proportional estimate ``len(alt) * BUBBLE_CHIP_FONT_SIZE *
    0.6`` (empirically ~half-width per char for the default Talon font
    at 11pt).
    """
    if alt_text_widths is not None:
        w = alt_text_widths.get(alt)
        if w is not None:
            return float(w)
    return len(alt) * BUBBLE_CHIP_FONT_SIZE * 0.6


# ---------------------------------------------------------------------------
# Placement scratchpad — mirrors internal/panel_layout.py:BubbleLayout's
# shape (ideal_x, bubble_w, x, band) with the extra data we need to
# materialize a final ui.layout.BubbleLayout after placement. Kept private
# (leading underscore, __slots__) because Move 4e / a follow-up will
# consolidate the three BubbleLayout variants into one type; consumers
# outside this module should treat only ui.layout.BubbleLayout as the
# public surface.
# ---------------------------------------------------------------------------


@dataclass
class _PendingBubble:
    """Mutable placement record — merged with final geometry post-placement.

    Fields mirror ``internal/panel_layout.py:BubbleLayout`` (``ideal_x``,
    ``bubble_w``, ``x``, ``band``) plus the trailing paint data
    (``token_idx``, ``bubble_h``, ``shape_name``, chip tuples) that the
    materialization step needs. Instances are discarded after
    ``build_bubble_layouts`` returns — never leak outside this module.
    """

    __slots__ = (
        "token_idx",
        "ideal_x",
        "bubble_w",
        "bubble_h",
        "x",
        "band",
        "shape_name",
        "left_chip",
        "right_chip",
    )

    token_idx: int
    ideal_x: float
    bubble_w: float
    bubble_h: float
    x: float
    band: int
    shape_name: str
    left_chip: tuple[str, str, float]
    right_chip: tuple[str, str, float] | None


# ---------------------------------------------------------------------------
# Measurement pass — build _PendingBubble specs for one row of tokens.
# ---------------------------------------------------------------------------


def _measure_bubble(
    token_idx: int,
    token_x_abs: float,
    token_w: float,
    shape_name: str,
    entry: dict[str, str],
    alt_text_widths: dict[str, float] | None,
) -> _PendingBubble | None:
    """Measure one token's bubble dimensions; return a ``_PendingBubble``.

    Picks the first two color-alt pairs from ``entry`` (the entry is
    keyed in ``PANEL_COLOR_PALETTE`` order — yellow first, blue second
    — per the OQ2 convention enforced by
    ``shim/shapes.py:compute_panel_alts``).

    For 2-member groups (only one alt available) renders ``[chip][shape]``
    with no right chip. For 4+ member groups, the extra alts beyond the
    second slot are dropped — the spec routes them to cycling, not
    additional chips.

    Returns None when ``entry`` is empty (defensive — shouldn't happen
    because ``compute_panel_alts`` only writes non-empty mappings, but
    the nil-check keeps the caller simple).

    Mirrors ``ui/draw_panels.py:_measure_bubble`` exactly, minus the
    Skia measurement call which is INJECTED via ``alt_text_widths``.
    """
    if not entry:
        return None

    # Pull (color, alt) pairs in insertion order. The mapping was built
    # by compute_panel_alts iterating PANEL_COLOR_PALETTE in CSV-row
    # order, so the first two items are yellow + blue for the worked
    # example.
    pairs = list(entry.items())
    if not pairs:
        return None

    # Left chip.
    left_color, left_alt = pairs[0]
    left_text_w = _measure_chip_text_width(left_alt, alt_text_widths)
    left_chip_w = left_text_w + BUBBLE_CHIP_PAD_X * 2
    left_chip: tuple[str, str, float] = (left_color, left_alt, left_chip_w)

    # Right chip (when present — 3+ member groups).
    right_chip: tuple[str, str, float] | None = None
    right_chip_w = 0.0
    if len(pairs) >= 2:
        right_color, right_alt = pairs[1]
        right_text_w = _measure_chip_text_width(right_alt, alt_text_widths)
        right_chip_w = right_text_w + BUBBLE_CHIP_PAD_X * 2
        right_chip = (right_color, right_alt, right_chip_w)

    # Shape footprint at BUBBLE_SHAPE_SCALE.
    shape_w = _SHAPE_NATIVE_W * BUBBLE_SHAPE_SCALE
    shape_h = _SHAPE_NATIVE_H * BUBBLE_SHAPE_SCALE

    # Bubble width: [left_chip][gap][shape][gap][right_chip], or
    # [left_chip][gap][shape] for the 2-member case.
    if right_chip is not None:
        bubble_w = (
            left_chip_w + BUBBLE_INNER_GAP + shape_w
            + BUBBLE_INNER_GAP + right_chip_w
        )
    else:
        bubble_w = left_chip_w + BUBBLE_INNER_GAP + shape_w

    # Bubble height: chip height (chips are the tallest element; the
    # shape at scale ~1.1 stays under a chip's footprint but we take the
    # max defensively so a future scale bump can't clip the shape).
    chip_h = BUBBLE_CHIP_FONT_SIZE + BUBBLE_CHIP_PAD_Y * 2
    bubble_h = max(chip_h, shape_h)

    # Ideal x: bubble centered on the token. ABSOLUTE — caller passed
    # `token_x_abs` including x_origin, so the placement pass can
    # consume `ideal_x` directly.
    ideal_x = token_x_abs + (token_w - bubble_w) / 2.0

    return _PendingBubble(
        token_idx=token_idx,
        ideal_x=ideal_x,
        bubble_w=bubble_w,
        bubble_h=bubble_h,
        x=ideal_x,
        band=0,
        shape_name=shape_name,
        left_chip=left_chip,
        right_chip=right_chip,
    )


def _build_row_bubbles(
    row: list[tuple[int, float]],
    panel_alts: dict[int, dict[str, str]],
    shape_assignments: dict[int, str],
    x_origin: float,
    alt_text_widths: dict[str, float] | None,
) -> list[_PendingBubble]:
    """Walk a single row, measure each panel entry's bubble.

    Mirrors ``ui/draw_panels.py:_build_row_bubbles``.

    Tokens without panel entries are skipped silently. Tokens whose entry
    is in ``panel_alts`` but lack a shape assignment are also skipped —
    the bubble's central anchor is the shape glyph, and a missing shape
    would leave a confusing chip-pair with no glyph between them.

    Bubble ideal_x is set ABSOLUTE (already includes ``x_origin``) so the
    placement pass consumes it directly without an extra translation.
    """
    bubbles: list[_PendingBubble] = []
    x = x_origin  # absolute x of the current token's left edge
    for idx, tw in row:
        entry = panel_alts.get(idx)
        shape_name = shape_assignments.get(idx)
        if entry and shape_name is not None:
            bubble = _measure_bubble(
                idx, x, tw, shape_name, entry, alt_text_widths
            )
            if bubble is not None:
                bubbles.append(bubble)
        x += tw + TOKEN_GAP_X
    return bubbles


# ---------------------------------------------------------------------------
# Placement pass — v2 horizontal-only contract from
# internal/panel_layout.py:place_bubbles. Duplicated here (not imported)
# so the pure builder has zero cross-module dependencies at layer L1 test
# time. The two implementations MUST stay behavior-equivalent; a
# consolidation move will fold them into one when Move 4e wires the
# builder into draw_homophone_panels.
# ---------------------------------------------------------------------------


def _place_bubbles(
    bubbles: list[_PendingBubble],
    x_origin: float,
    outer_gap: float,
) -> None:
    """Place bubbles on a single horizontal row, right-shifting on collision.

    Mirrors ``internal/panel_layout.py:place_bubbles`` exactly:

      1. Soft-clamp each bubble's ``x`` to ``>= x_origin``.
      2. If the clamped ``x`` is closer than ``outer_gap`` to the
         previous bubble's right edge, shift this bubble's ``x``
         rightward to ``prev_right + outer_gap``.
      3. Record this bubble's right edge as the new ``prev_right`` for
         the next iteration.

    Mutates the ``_PendingBubble`` objects in place. ``band`` is always
    left at 0 (v2 contract — single horizontal row, no vertical wrap).
    """
    prev_right: float | None = None
    for b in bubbles:
        abs_x = b.ideal_x
        if abs_x < x_origin:
            abs_x = x_origin
        if prev_right is not None and abs_x < prev_right + outer_gap:
            abs_x = prev_right + outer_gap
        b.x = abs_x
        b.band = 0
        prev_right = abs_x + b.bubble_w


# ---------------------------------------------------------------------------
# Bubble band y — single value shared across all bubbles in a draw.
# Anchor-aware: "top" (default) puts the band BELOW the panel; "bottom"
# puts it ABOVE. Duplicates the two-line derivation from
# ``ui/draw_panels.py:draw_homophone_panels`` so the builder is
# self-contained.
# ---------------------------------------------------------------------------


def _bubble_band_y(
    panel_rect_y: float,
    panel_rect_h: float,
    anchor_position: str,
) -> float:
    """Compute the bubble band's top-y for one draw.

    Mirrors the two-line derivation at the tail of
    ``draw_homophone_panels``:

      anchor_position == "bottom" → band above the panel:
          panel_rect.y - BUBBLE_ROW_H - BUBBLE_TOP_GAP
      anchor_position == "top"    → band below the panel (default):
          panel_rect.y + panel_rect.h + BUBBLE_TOP_GAP

    Any string other than "bottom" is treated as "top" (matches the
    existing else-branch in draw_panels).
    """
    if anchor_position == "bottom":
        return panel_rect_y - BUBBLE_ROW_H - BUBBLE_TOP_GAP
    return panel_rect_y + panel_rect_h + BUBBLE_TOP_GAP


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------


def build_bubble_layouts(
    state,
    tokens: list[str],
    token_widths: list[float],
    *,
    x_origin: float,
    y_start: float,
    max_row_w: float,
    panel_rect_y: float,
    panel_rect_h: float,
    anchor_position: str,
    alt_text_widths: dict[str, float] | None = None,
    max_visible_rows: int | None = None,
) -> list[BubbleLayout]:
    """Pure homophone-bubble layout builder.

    Consumes pure data (``state``, ``tokens``, ``token_widths``, geometry
    scalars, and optional chip-text widths) and returns the fully-placed
    homophone-bubble records Move 4e will splice into a full
    ``LayoutModel.bubbles``. Emits one ``ui.layout.BubbleLayout`` per
    shape-hatted token with a ``homophone_panel_alts`` entry.

    Args:
        state: The pure ``_State`` snapshot (see
            ``internal/instance.py``). Read only. Fields consumed:
            ``homophone_panel_alts``, ``shape_assignments``. Other state
            is ignored; token flagging is already encoded in
            ``homophone_panel_alts`` (populated by
            ``compute_panel_alts``, which itself gates on flag+shape).
        tokens: The token strings in buffer order. Present for symmetry
            with ``build_token_layouts``; the current implementation
            only needs their count via ``token_widths`` but future
            consolidation moves may want the strings for debug
            snapshots.
        token_widths: Pre-measured pixel widths, one per token, aligned
            to ``tokens``. Callers with a live Skia canvas compute this
            via ``c.paint.measure_text(tok)[1].width``; headless callers
            pass any monotone-nonneg widths.
        x_origin: Absolute x of the first token in each row. Typically
            ``panel_x + PANEL_PAD``.
        y_start: Absolute y at the TOP of the first row. Retained for
            row-wrap parity even though the bubble band y is
            independent of the row y — a future consolidation may lift
            row-y computation here.
        max_row_w: Max row width in pixels used to wrap tokens into
            rows. Must match what the token layout pass uses so bubble
            token-centers align with painted token positions.
        panel_rect_y: Absolute y of the panel rect (used to compute the
            bubble-band y outside the panel).
        panel_rect_h: Height of the panel rect (used for the "top"
            anchor case: band sits below panel at ``y + h + gap``).
        anchor_position: Either ``"top"`` (band below panel — default)
            or ``"bottom"`` (band above panel). Any other string is
            treated as ``"top"``.
        alt_text_widths: Optional injected chip-text measurements at
            ``BUBBLE_CHIP_FONT_SIZE``. Keys are the alt words; values
            are pixel widths. When None, chip widths use a proportional
            estimate — good enough for tests but not for live paint.
        max_visible_rows: When set, drop rows above
            ``len(rows) - max_visible_rows`` (matches the terminal-pinned
            viewport trim in ``draw_overlay``). Bubbles for trimmed rows
            are OMITTED. When None, all rows survive.

    Returns:
        A fresh ``list[ui.layout.BubbleLayout]`` — one entry per
        panel-alt-bearing token that survives the viewport trim, in
        left-to-right paint order after the horizontal placement pass.
        Empty list when ``state.homophone_panel_alts`` is empty or all
        candidate tokens are trimmed off.

    Invariants:
        * No mutation of ``state`` or any input list / dict.
        * No Talon / Skia / shim imports.
        * Deterministic — identical inputs produce dataclass-equal
          output (frozen dataclasses compare structurally).
        * Every returned record is a
          ``ui.layout.BubbleLayout`` (NOT
          ``internal.panel_layout.BubbleLayout``).
    """
    if not tokens:
        return []
    if len(tokens) != len(token_widths):
        # Defensive — the caller is responsible for keeping these
        # aligned. Bail cleanly rather than paint half a row.
        return []

    panel_alts: dict[int, dict[str, str]] = (
        getattr(state, "homophone_panel_alts", {}) or {}
    )
    if not panel_alts:
        return []
    shape_assignments: dict[int, str] = (
        getattr(state, "shape_assignments", {}) or {}
    )

    rows = _flow_rows(token_widths, max_row_w)

    # Terminal-pinned viewport trim — matches draw_overlay's
    # `rows = rows[len(rows) - max_visible_rows:]`. Bubbles for tokens
    # on trimmed rows are OMITTED entirely (matches draw_panels which
    # walks the same trimmed rows list).
    if max_visible_rows is not None and len(rows) > max_visible_rows:
        rows = rows[len(rows) - max_visible_rows :]

    # Measurement pass — build one pending bubble per shape-hatted
    # flagged token that has a panel-alt entry. Row order preserves the
    # painted left-to-right sequence because _flow_rows walks tokens
    # left-to-right top-to-bottom.
    pending: list[_PendingBubble] = []
    for row in rows:
        pending.extend(
            _build_row_bubbles(
                row, panel_alts, shape_assignments, x_origin, alt_text_widths
            )
        )

    if not pending:
        return []

    # Placement pass — v2 horizontal-only contract. Mutates pending
    # bubbles' `x` in place; `band` stays at 0.
    _place_bubbles(pending, x_origin, BUBBLE_OUTER_GAP)

    # Materialize the frozen ui.layout.BubbleLayout records with the
    # placed x and the shared bubble-band y. Downstream (Move 4e) drops
    # this list directly into LayoutModel.bubbles.
    y = _bubble_band_y(panel_rect_y, panel_rect_h, anchor_position)
    _ = y_start  # y_start retained for API symmetry; band y is independent
    out: list[BubbleLayout] = []
    for b in pending:
        out.append(
            BubbleLayout(
                token_idx=b.token_idx,
                x=b.x,
                y=y,
                w=b.bubble_w,
                h=b.bubble_h,
                shape_name=b.shape_name,
                shape_scale=BUBBLE_SHAPE_SCALE,
                left_chip=b.left_chip,
                right_chip=b.right_chip,
                band=b.band,
            )
        )
    return out


__all__ = ["build_bubble_layouts"]
