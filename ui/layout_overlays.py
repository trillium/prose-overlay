"""Pure selection- and flash-overlay layout builders — Move 4c of the
pure-function refactor.

Extracts the selection-highlight and flash-highlight geometry currently
interleaved in ``ui/draw_tokens.py:_draw_token_rows`` (the "Highlight
rect (flash or selection)" branch around line 258) into two pure
builders in this module:

    build_selection_overlay(state, tokens, token_widths, *, ...) -> SelectionOverlay | None
    build_flash_overlay(state, tokens, token_widths, *, ...) -> FlashOverlay | None

Neither is wired into ``draw_overlay`` yet — that's Move 4e. This move
ships extraction + tests only.

Contract
--------

Both builders are pure:

* No side effects — does NOT mutate ``state`` or any argument, does NOT
  reach into the viewport, does NOT call any Talon or Skia API.
* No Talon imports — the module is safe to import from the L1 headless
  harness. All types come from ``ui.layout`` (frozen dataclasses) plus
  ``internal.draw_constants`` (module of ints/floats/strings).
* Deterministic — same inputs produce dataclass-equal output.

Design notes
------------

* **Row wrap parity.** Both builders re-derive the same row-wrap
  ``ui/layout_tokens.py:_flow_rows`` produces (mirroring the paint
  path's ``ui/draw_tokens.py:_flow_layout``). Highlight rects must land
  under the SAME token x/y positions the paint pass will draw, so
  the wrap algorithm has to match exactly. ``max_visible_rows`` mirrors
  ``draw_overlay``'s terminal-pinned viewport trim so highlights for
  scrolled-off tokens are OMITTED entirely (matches the current
  behavior — ``_draw_token_rows`` walks the trimmed rows list).

* **Row-visible order.** The returned ``rects`` list is in row-visible
  paint order: left-to-right within a row, top-to-bottom across rows.
  This matches how the paint code emits rects today when it walks
  ``for row in rows: for idx, token, tw in row: ...``.

* **Multi-row selection spans.** A selection ``(start, end)`` inclusive
  that straddles a row wrap emits ONE rect per selected token on ITS
  row. Callers that expect a merged-per-row rect can coalesce contiguous
  same-y rects downstream; the paint pass today draws per-token rects
  so this module preserves that behavior exactly.

* **Highlight rect geometry.** Mirrors ``ui/draw_tokens.py`` exactly:

      hl_pad_x = 2
      Rect(
          x - hl_pad_x,
          y_base + (DOT_RADIUS * 2) + DOT_GAP_Y,
          tw + hl_pad_x * 2,
          TOKEN_FONT_SIZE + 2,
      )

  Baked here as ``_HL_PAD_X = 2`` (no other paint code touches this
  constant so it doesn't belong in ``draw_constants``).

* **Flash color alpha rewrite.** The paint code rewrites the caller's
  6-char hex color to 30% alpha (``flash_color[:6] + "4d"``). The
  builder mirrors that rewrite so the FlashOverlay carries the paint
  color, not the source color.

* **Selection color.** Hardcoded ``"089ad340"`` (blue 25% alpha) in
  today's paint code. The builder doesn't emit a selection color — the
  ``SelectionOverlay`` schema in ``ui/layout.py`` stores rects only, per
  its field docstring ("Colored by the paint step with the current
  selection color"). Preserving that split so the palette decision
  stays in the paint layer.

* **Anti-scope.** This module does NOT touch ``ui/draw.py``,
  ``ui/draw_tokens.py``, ``ui/draw_panels.py``, ``ui/layout.py``,
  ``ui/layout_tokens.py``, or ``ui/layout_bubbles.py``. Move 4e will
  wire the builders into ``draw_overlay`` (or the future
  ``layout(state, canvas)`` composition); until then paint still runs
  through the imperative ``_draw_token_rows`` path.
"""

from __future__ import annotations

from ..internal.draw_constants import (
    DOT_GAP_Y,
    DOT_RADIUS,
    LINE_HEIGHT,
    TOKEN_FONT_SIZE,
    TOKEN_GAP_X,
)
from .layout import FlashOverlay, Rect, SelectionOverlay


# ---------------------------------------------------------------------------
# Highlight rect padding — matches ui/draw_tokens.py's `hl_pad_x = 2`. Kept
# local to this module because no other draw code references it; the paint
# layer inlines the same literal today. When Move 4e consolidates, this can
# migrate to draw_constants if it grows a second caller.
# ---------------------------------------------------------------------------

_HL_PAD_X = 2


# ---------------------------------------------------------------------------
# Row wrap — must match ui/layout_tokens.py:_flow_rows and
# ui/draw_tokens.py:_flow_layout exactly so highlights land under the SAME
# token positions the paint pass will draw. Duplicated (not imported) so
# this module has a clean import graph — a Move 4e refactor will consolidate
# all three callers onto a single ``layout_rowflow`` helper.
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
# Highlight-rect geometry — the SAME rect shape both flash and selection
# paint today. Split out so both builders share one formula and one place
# to change if the paint geometry ever shifts.
# ---------------------------------------------------------------------------


def _highlight_rect(x: float, y_base: float, tw: float) -> Rect:
    """Build the highlight rect for a single token at (x, y_base).

    Mirrors the highlight branch of ``ui/draw_tokens.py:_draw_token_rows``:

        hl_y_top = y_base + (DOT_RADIUS * 2) + DOT_GAP_Y
        Rect(x - hl_pad_x, hl_y_top, tw + hl_pad_x * 2, TOKEN_FONT_SIZE + 2)

    The paint code passes this through ``draw_rounded_rect`` with corner
    radius 3; the LayoutModel records the AABB and lets the renderer
    decide whether to round the corners. That preserves the "model
    describes what, paint describes how" split from ``ui/layout.py``'s
    module docstring.
    """
    hl_y_top = y_base + (DOT_RADIUS * 2) + DOT_GAP_Y
    return Rect(
        x=x - _HL_PAD_X,
        y=hl_y_top,
        w=tw + _HL_PAD_X * 2,
        h=TOKEN_FONT_SIZE + 2,
    )


# ---------------------------------------------------------------------------
# Shared row walker — turns a set of token indices into a list of highlight
# rects in row-visible paint order. Both builders route through this so
# the row-wrap semantics stay in one place.
# ---------------------------------------------------------------------------


def _build_index_rects(
    token_widths: list[float],
    hit_indices: "frozenset[int] | set[int]",
    *,
    x_origin: float,
    y_start: float,
    max_row_w: float,
    max_visible_rows: int | None,
) -> list[Rect]:
    """Walk the wrapped rows; emit one highlight Rect per hit token.

    ``hit_indices`` is the set of TOKEN INDEXES to highlight. Selection
    passes ``set(range(start, end + 1))``; flash passes the raw
    ``flash_indices`` set. Tokens not in ``hit_indices`` are stepped
    over (their x still advances so subsequent tokens land in the right
    place). Tokens on trimmed rows (viewport overflow) are dropped
    entirely — they weren't painted, so they don't emit a highlight
    either. Matches the existing paint contract in ``_draw_token_rows``.

    Returns rects in row-visible paint order:
      left-to-right within a row, top-to-bottom across rows.

    Empty return when ``hit_indices`` is empty OR no hit token survives
    the ``max_visible_rows`` trim.
    """
    if not hit_indices:
        return []

    rows = _flow_rows(token_widths, max_row_w)
    if max_visible_rows is not None and len(rows) > max_visible_rows:
        rows = rows[len(rows) - max_visible_rows :]

    rects: list[Rect] = []
    y_base = y_start
    for row in rows:
        x = x_origin
        for token_idx, tw in row:
            if token_idx in hit_indices:
                rects.append(_highlight_rect(x, y_base, tw))
            x += tw + TOKEN_GAP_X
        y_base += LINE_HEIGHT

    return rects


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------


def build_selection_overlay(
    state,
    tokens: list[str],
    token_widths: list[float],
    *,
    x_origin: float,
    y_start: float,
    max_row_w: float,
    max_visible_rows: int | None = None,
) -> SelectionOverlay | None:
    """Pure selection-highlight overlay builder.

    Consumes pure data (``state``, ``tokens``, ``token_widths``, scalar
    geometry) and returns a fresh ``SelectionOverlay`` covering every
    token in ``state.buffer.get_selection()``'s inclusive range, or
    ``None`` when no selection is set.

    Args:
        state: The pure ``_State`` snapshot (see
            ``internal/instance.py``). Read only. Fields consumed:
            ``buffer.get_selection()`` — returns ``(start, end)`` inclusive
            or ``None``. State stubs in tests can expose any object with
            a ``buffer.get_selection()`` accessor.
        tokens: The token strings in buffer order. Present for symmetry
            with the other Move 4 builders and for future extensions
            (e.g. debug snapshots keyed by token text). Not read
            directly by the geometry math.
        token_widths: Pre-measured pixel widths, one per token, aligned
            to ``tokens``. Callers with a live Skia canvas compute this
            via ``c.paint.measure_text(tok)[1].width``; headless callers
            pass any monotone-nonneg widths.
        x_origin: Absolute x of the first token in each row. Typically
            ``panel_x + PANEL_PAD``.
        y_start: Absolute y at the TOP of the first row (the top of
            the hat-dot band). Typically ``panel_y + PANEL_PAD``.
        max_row_w: Max row width in pixels used to wrap tokens into
            rows. MUST match what the token layout pass uses so
            highlight rects land under painted tokens.
        max_visible_rows: When set, drop rows above
            ``len(rows) - max_visible_rows`` (matches the terminal-pinned
            viewport trim in ``draw_overlay``). Selection rects for
            trimmed rows are OMITTED. When None, all rows survive.

    Returns:
        ``SelectionOverlay(rects=[...])`` when a selection is set and
        at least one selected token survives the viewport trim. ``None``
        when ``state.buffer.get_selection()`` is None. Also ``None``
        when the selection references tokens that are all off the
        visible viewport (nothing to paint).

    Invariants:
        * No mutation of ``state`` or any input list / dict.
        * No Talon / Skia / shim imports.
        * Deterministic — identical inputs produce dataclass-equal
          output.
    """
    if not tokens or len(tokens) != len(token_widths):
        # Defensive — matches the parity check used by build_token_layouts /
        # build_bubble_layouts. Bail cleanly rather than paint half a row.
        return None

    # State read — buffer.get_selection() returns (start, end) inclusive.
    # Access via getattr chain so a test stub can expose a lightweight
    # `buffer` object without implementing the full ProseBuffer contract.
    buffer = getattr(state, "buffer", None)
    if buffer is None:
        return None
    get_sel = getattr(buffer, "get_selection", None)
    if get_sel is None:
        return None
    sel = get_sel()
    if sel is None:
        return None
    start, end = sel

    # Normalize — some tests / edge cases may pass reversed ranges
    # ((5, 2) instead of (2, 5)). The paint code today uses
    # `selection[0] <= idx <= selection[1]` so a reversed range paints
    # NOTHING (idx satisfies neither inequality). Mirror that: reversed
    # range emits an empty hit set. When start > end the range object is
    # empty, so `set(range(start, end + 1))` is empty and the builder
    # short-circuits.
    hit = set(range(start, end + 1))
    if not hit:
        return None

    rects = _build_index_rects(
        token_widths,
        hit,
        x_origin=x_origin,
        y_start=y_start,
        max_row_w=max_row_w,
        max_visible_rows=max_visible_rows,
    )
    if not rects:
        return None
    return SelectionOverlay(rects=rects)


def build_flash_overlay(
    state,
    tokens: list[str],
    token_widths: list[float],
    *,
    x_origin: float,
    y_start: float,
    max_row_w: float,
    max_visible_rows: int | None = None,
) -> FlashOverlay | None:
    """Pure flash-highlight overlay builder.

    Consumes pure data and returns a fresh ``FlashOverlay`` covering
    every token in ``state.flash_state["indices"]``, or ``None`` when
    no flash is active.

    Args:
        state: The pure ``_State`` snapshot. Read only. Fields consumed:
            ``flash_state`` — a dict with keys ``"indices"`` (iterable
            of token indexes) and ``"color"`` (6-char hex color, no
            alpha). See ``ui/actions_flash.py`` for the producer.
        tokens: The token strings in buffer order. Present for symmetry
            with the other Move 4 builders. Not read directly.
        token_widths: Pre-measured pixel widths, one per token.
        x_origin: Absolute x of the first token in each row.
        y_start: Absolute y at the TOP of the first row.
        max_row_w: Max row width in pixels used to wrap tokens.
        max_visible_rows: When set, drop rows above
            ``len(rows) - max_visible_rows``. Flash rects for trimmed
            rows are OMITTED. When None, all rows survive.

    Returns:
        ``FlashOverlay(rects=[...], color=<hex+alpha>)`` when a flash
        is active AND at least one flashed token survives the viewport
        trim. ``None`` when ``flash_state`` is missing / empty, when
        ``indices`` is empty, or when every flashed token is off the
        visible viewport.

        The returned ``color`` is the paint color: the caller's 6-char
        hex color rewritten with the fixed 30% alpha suffix ``"4d"``
        (matches ``ui/draw_tokens.py``'s ``flash_color[:6] + "4d"``).

    Invariants:
        * No mutation of ``state`` or any input list / dict.
        * No Talon / Skia / shim imports.
        * Deterministic — identical inputs produce dataclass-equal
          output.
    """
    if not tokens or len(tokens) != len(token_widths):
        return None

    flash_state = getattr(state, "flash_state", None) or {}
    if not flash_state:
        return None

    # `indices` may be a list / set / tuple / frozenset — normalize to a
    # set for O(1) membership in the row walker. Empty / missing → no
    # flash.
    raw_indices = flash_state.get("indices")
    if not raw_indices:
        return None
    hit: set[int] = set(raw_indices)
    if not hit:
        return None

    # Color rewrite — ui/draw_tokens.py:_draw_token_rows does
    # `highlight_color = flash_color[:6] + "4d"`. Mirror exactly. Missing
    # / short colors fall back to a default so the model always carries
    # a valid 8-char hex; the default matches today's paint pass, which
    # would raise on `None[:6]` today — so an empty color is treated as
    # "no flash" (returns None below).
    raw_color = flash_state.get("color")
    if not raw_color:
        return None
    paint_color = raw_color[:6] + "4d"

    rects = _build_index_rects(
        token_widths,
        hit,
        x_origin=x_origin,
        y_start=y_start,
        max_row_w=max_row_w,
        max_visible_rows=max_visible_rows,
    )
    if not rects:
        return None
    return FlashOverlay(rects=rects, color=paint_color)


__all__ = ["build_selection_overlay", "build_flash_overlay"]
