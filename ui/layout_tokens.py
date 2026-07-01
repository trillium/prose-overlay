"""Pure per-token layout builder — Move 4a of the pure-function refactor.

Extracts the per-token geometry math currently interleaved in
``ui/draw.py:draw_overlay`` and ``ui/draw_tokens.py:_draw_token_rows``
into a single pure function ``build_token_layouts`` that returns a list
of ``ui.layout.TokenLayout`` records.

Contract
--------

::

    build_token_layouts(
        state,
        tokens,
        token_widths,
        *,
        x_origin, y_start, max_row_w,
        max_visible_rows=None,
        flagged_indices=frozenset(),
        shape_enabled=False,
        hat_assignments=None,
        per_char_widths=None,
    ) -> list[TokenLayout]

The builder is pure:

* No side effects — does NOT mutate ``state`` or any argument, does NOT
  reach into the viewport, does NOT call any Talon or Skia API.
* No Talon imports — the module is safe to import from the L1 headless
  harness. All types come from ``ui.layout`` (frozen dataclasses) plus
  ``internal.draw_constants`` (module of ints/floats/strings).
* Deterministic — same inputs produce byte-equal ``list[TokenLayout]``
  output. Enforced by an L1 determinism test.

Design notes
------------

* **Why the caller passes ``token_widths``.** The current
  ``draw_overlay`` measures token widths via
  ``c.paint.measure_text(tok)[1].width`` on a live SkiaCanvas. Skia
  is not available headlessly; keeping the builder pure means the
  measurement dependency is INJECTED. Move 4e's ``layout(state, canvas)``
  wrapper will call the measurement pass once and hand the results in.

* **Why ``per_char_widths`` is optional.** The hat and shape marks land
  above SPECIFIC characters (e.g. ``t[h]ere`` puts the letter hat on
  index 1, shape on index 2). Positioning them accurately requires
  measuring ``token[:char_idx]``. Live Skia does that today
  (``c.paint.measure_text(token[:char_idx])``); the pure builder
  accepts a pre-computed ``per_char_widths[token_idx] = [w_prefix_0,
  w_prefix_1, ..., w_prefix_len]`` where ``w_prefix_k`` is the pixel
  width of ``token[:k]``. When ``per_char_widths`` is None the builder
  falls back to a proportional estimate ``tw * char_idx / len(token)``
  so callers without measurements still get a plausible mark position.

* **Rows vs flat list.** The return type is a flat ``list[TokenLayout]``
  because ``LayoutModel.tokens`` is flat and Move 4e/5 consume it that
  way. Internally the builder walks rows so each TokenLayout can carry
  its row's y coordinate. Rows scrolled off the top by
  ``max_visible_rows`` are OMITTED entirely (matches the invariant
  documented on ``TokenLayout.on_visible_row``: only surviving tokens
  are in the list, and they always carry ``on_visible_row=True``).

* **Anti-scope.** This module does NOT touch ``ui/draw.py``,
  ``ui/draw_tokens.py``, or ``ui/draw_panels.py``. Move 4e will wire
  the builder into a new ``layout(state, canvas)`` composition; until
  then paint still runs through the imperative ``_draw_token_rows``
  path. Commit 1 of Move 4a ships this file with no consumers.
"""

from __future__ import annotations

from ..internal.draw_constants import (
    DOT_GAP_Y,
    DOT_RADIUS,
    HAT_ALPHABET,
    HAT_COLOR,
    HAT_COLOR_HEX,
    HOMOPHONE_SHAPE_COLOR_HEX,
    HOMOPHONE_SHAPE_SCALE,
    HOMOPHONE_UNDERLINE_ACTIVE_ALPHA,
    HOMOPHONE_UNDERLINE_COLOR,
    HOMOPHONE_UNDERLINE_GAP_W,
    HOMOPHONE_UNDERLINE_INACTIVE_ALPHA,
    HOMOPHONE_UNDERLINE_MIN_SEGMENT_W,
    LINE_HEIGHT,
    TOKEN_FONT_SIZE,
    TOKEN_GAP_X,
)
from .layout import HatMark, Rect, ShapeMark, TokenLayout, UnderlineSegment


# ---------------------------------------------------------------------------
# Row wrap — mirrors ui/draw_tokens.py:_flow_layout but emits (idx, width)
# pairs. We drop the token string since callers already have the token list;
# retaining it here would just force a redundant re-copy through the row grid.
# ---------------------------------------------------------------------------


def _flow_rows(
    token_widths: list[float],
    max_w: float,
) -> list[list[tuple[int, float]]]:
    """Wrap ``token_widths`` into rows that fit ``max_w`` px each.

    Emits one row per line of the paint grid. Each row is a list of
    ``(token_idx, width)`` pairs in left-to-right order.

    Semantics MUST match ``ui/draw_tokens.py:_flow_layout``:

    * A token that alone exceeds ``max_w`` still occupies its own row
      (no truncation, no split). This matches the existing behavior —
      the token overflows the panel horizontally rather than getting
      dropped. The upstream flow-layout has no explicit assertion but
      the ``current_row and current_row_w + needed > max_w`` guard
      only fires when the row is non-empty, so an oversized token on
      an empty row is appended anyway.
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
# Prefix measurement — the pure builder cannot call Skia. Callers with a live
# canvas pass ``per_char_widths[token_idx] = [w0, w1, ..., w_len]`` where
# ``w_k`` is the pixel width of ``token[:k]`` (so ``w_0 == 0``, ``w_len ==
# full token width``). When absent we fall back to a proportional estimate.
# ---------------------------------------------------------------------------


def _measure_prefix(
    token: str,
    char_idx: int,
    tw: float,
    per_char_widths: dict[int, list[float]] | None,
    token_idx: int,
) -> float:
    """Return the pixel width of ``token[:char_idx]``.

    Prefers the exact ``per_char_widths`` measurements when available;
    falls back to a proportional estimate ``tw * char_idx / len(token)``.
    A ``char_idx == 0`` always returns 0.0 (no prefix to measure).
    """
    if char_idx <= 0:
        return 0.0
    if per_char_widths is not None:
        row = per_char_widths.get(token_idx)
        if row is not None and 0 <= char_idx < len(row):
            return float(row[char_idx])
    if not token:
        return 0.0
    # Proportional fallback — the estimate is not accurate for
    # variable-width fonts but keeps the pure builder usable without
    # measurements. Live paint always supplies per_char_widths.
    return tw * (min(char_idx, len(token)) / len(token))


def _measure_char_width(
    token: str,
    char_idx: int,
    tw: float,
    per_char_widths: dict[int, list[float]] | None,
    token_idx: int,
) -> float:
    """Return the pixel width of the single character ``token[char_idx]``.

    Derived from ``per_char_widths`` when present:
    ``w_prefix[char_idx + 1] - w_prefix[char_idx]``. Falls back to
    ``tw / len(token)`` when no measurements exist. Guards against
    empty token and out-of-range indexes so the builder never divides
    by zero.
    """
    if not token:
        return 0.0
    if per_char_widths is not None:
        row = per_char_widths.get(token_idx)
        if row is not None and 0 <= char_idx < len(row) - 1:
            return float(row[char_idx + 1] - row[char_idx])
    return tw / max(1, len(token))


# ---------------------------------------------------------------------------
# Per-token mark builders. All pure — take (token, geometry, state maps),
# return a HatMark / ShapeMark / list[UnderlineSegment] describing what to
# paint. Any absence returns None or an empty list.
# ---------------------------------------------------------------------------


def _hat_for_token(
    idx: int,
    token: str,
    tw: float,
    x: float,
    y_base: float,
    hat_assignments: dict[int, tuple[int, str, str]] | None,
    per_char_widths: dict[int, list[float]] | None,
) -> HatMark | None:
    """Build a HatMark for a token, or return None when no hat applies.

    Mirrors ``ui/draw_tokens.py:_draw_token_rows``'s hat-branch logic:

    * When ``hat_assignments`` is supplied, look up ``assignment =
      hat_assignments.get(idx)``. Absent → no hat.
    * When ``hat_assignments`` is None, fall back to the default
      alphabetic path (``idx < len(HAT_ALPHABET)`` gets a hat on
      char 0 with the default gray color and the letter matching
      ``HAT_ALPHABET[idx]``).
    * Char index and color follow the assignment; letter is
      ``assignment[1]`` (the addressable letter, NOT the underlying
      char at ``char_idx`` — matches how the paint code stores it).
    """
    if hat_assignments is not None:
        assignment = hat_assignments.get(idx)
        if assignment is None:
            return None
        char_idx, letter, color_name = assignment
    else:
        # No live hat_assignments passed — draw_tokens.py's `has_hat`
        # fallback uses `idx < len(HAT_ALPHABET)`. Mirror that so the
        # builder produces the same result the current paint path would.
        if idx >= len(HAT_ALPHABET):
            return None
        char_idx = 0
        letter = HAT_ALPHABET[idx]
        # Default gray — matches draw_tokens.py fallback `HAT_COLOR`.
        color_name = "gray"

    # Position math — mirrors draw_tokens.py: prefix + char_rect/2, y = y_base
    # + DOT_RADIUS. The paint code draws a filled circle; the model records
    # the enclosing 2*DOT_RADIUS square so downstream renderers know the
    # bounding box.
    prefix_w = _measure_prefix(token, char_idx, tw, per_char_widths, idx)
    char_w = _measure_char_width(token, char_idx, tw, per_char_widths, idx)
    dot_cx = x + prefix_w + char_w / 2.0
    dot_cy = y_base + DOT_RADIUS
    pos = Rect(
        x=dot_cx - DOT_RADIUS,
        y=dot_cy - DOT_RADIUS,
        w=DOT_RADIUS * 2.0,
        h=DOT_RADIUS * 2.0,
    )
    # Colour resolution parity: the paint code stores the palette NAME
    # (draw_tokens.py's `assignment[2]` is a name; the hex lookup is
    # applied at paint time via HAT_COLOR_HEX). HatMark.color mirrors
    # that convention — we keep the name here so callers can compare
    # against `hat_assignments` without a hex round-trip. The default
    # fallback path passes "gray" which is a valid palette name.
    _ = HAT_COLOR_HEX.get(color_name, HAT_COLOR)  # kept for grep parity
    return HatMark(
        char_index=char_idx,
        letter=letter,
        color=color_name,
        position=pos,
    )


def _shape_for_token(
    idx: int,
    token: str,
    tw: float,
    x: float,
    y_base: float,
    letter_char_idx: int,
    shape_name: str | None,
    per_char_widths: dict[int, list[float]] | None,
) -> ShapeMark | None:
    """Build a ShapeMark for a token, or None when no shape applies.

    Mirrors ``ui/draw_tokens.py``'s shape branch. Requires a
    resolved ``shape_name`` (already looked up from
    ``state.shape_assignments`` by the caller — the caller decides
    whether ``shape_enabled`` is on). The shape lives on a
    DIFFERENT character than the letter hat per
    ``shim.shapes.shape_char_position`` (t[h]{e}re: bracket = letter
    hat idx 1, curly = shape idx 2).

    ``letter_char_idx`` is the letter-hat's char index (or -1 when
    no letter hat exists). We inline the ``shape_char_position``
    math here rather than importing it — it's four lines and the
    inline copy keeps the builder standalone (no shim import).
    """
    if shape_name is None:
        return None
    token_len = len(token)
    # shape_char_position semantics — see shim/shapes.py:
    #   token_len <= 1        -> 0 (collision unavoidable)
    #   letter_char_idx < 0   -> 0 (no letter hat present)
    #   otherwise             -> (letter_char_idx + 1) % token_len
    if token_len <= 1:
        shape_char_idx = 0
    elif letter_char_idx < 0:
        shape_char_idx = 0
    else:
        shape_char_idx = (letter_char_idx + 1) % token_len

    prefix_w = _measure_prefix(token, shape_char_idx, tw, per_char_widths, idx)
    char_w = _measure_char_width(token, shape_char_idx, tw, per_char_widths, idx)
    shape_cx = x + prefix_w + char_w / 2.0
    shape_cy = y_base + DOT_RADIUS
    # The SVG is scaled and centered on (cx, cy) at paint time. The
    # position rect on the ShapeMark records the 2*DOT_RADIUS square
    # around the anchor so downstream renderers know where to center
    # the glyph; the actual glyph extent depends on the SVG viewBox
    # and the scale factor.
    pos = Rect(
        x=shape_cx - DOT_RADIUS,
        y=shape_cy - DOT_RADIUS,
        w=DOT_RADIUS * 2.0,
        h=DOT_RADIUS * 2.0,
    )
    return ShapeMark(
        shape_name=shape_name,
        position=pos,
        scale=HOMOPHONE_SHAPE_SCALE,
        color=HOMOPHONE_SHAPE_COLOR_HEX,
    )


def _segment_width(tw: float, member_count: int) -> float:
    """Return one segment's pixel width for a segmented underline.

    Mirrors ``ui/draw_tokens.py:homophone_segment_width``. Kept inline
    (instead of imported) so this module has zero cross-import from
    ``draw_tokens.py`` — that keeps the builder importable in the
    headless harness without picking up the Skia imports at the top of
    ``draw_tokens.py``.
    """
    if member_count <= 1:
        return tw
    gap_count = member_count - 1
    return (tw - gap_count * HOMOPHONE_UNDERLINE_GAP_W) / member_count


def _underline_segments_for_token(
    idx: int,
    tw: float,
    x: float,
    y_base: float,
    position_assignments: dict[int, tuple[int, int]],
) -> list[UnderlineSegment]:
    """Build underline segments for a flagged token.

    Mirrors the amber-underline math at the bottom of
    ``_draw_token_rows``:

    * ``pos = position_assignments.get(idx)``. When None OR
      ``pos[1] <= 1`` → SOLID one-segment underline spanning the full
      token width. Color is ``HOMOPHONE_UNDERLINE_COLOR`` (already
      carries its alpha).
    * When ``pos = (active_idx, member_count)`` with
      ``member_count > 1`` AND the computed segment width is
      ``>= HOMOPHONE_UNDERLINE_MIN_SEGMENT_W`` → emit
      ``member_count`` segments, each with the active/inactive alpha
      pre-baked into ``UnderlineSegment.color``. The active segment
      also carries ``active=True`` so downstream renderers know to
      draw it TALLER (paint decision, not a geometry decision — the
      model records the property; the renderer maps to a height).
    * When any segment would be < MIN_SEGMENT_W → fall back to the
      solid one-segment form. Diagnostic logging is a side-effect the
      pure builder doesn't perform; ``draw_tokens.py`` still owns
      that when it runs the same math today.

    ``y`` on the emitted segments is the top edge of the underline
    band. Mirrors the underline_y_base math in ``draw_tokens.py``:
    ``y_base + (DOT_RADIUS * 2) + DOT_GAP_Y + TOKEN_FONT_SIZE + 2``.
    """
    underline_y = y_base + (DOT_RADIUS * 2) + DOT_GAP_Y + TOKEN_FONT_SIZE + 2

    pos = position_assignments.get(idx)
    use_segmented = pos is not None and pos[1] > 1
    seg_w = _segment_width(tw, pos[1]) if use_segmented else tw
    if use_segmented and seg_w < HOMOPHONE_UNDERLINE_MIN_SEGMENT_W:
        use_segmented = False

    if not use_segmented:
        # Solid one-segment form. Full color (already includes alpha).
        return [
            UnderlineSegment(
                x0=x,
                x1=x + tw,
                y=underline_y,
                active=False,
                color=HOMOPHONE_UNDERLINE_COLOR,
            )
        ]

    active_idx, member_count = pos  # type: ignore[misc]
    base_color = HOMOPHONE_UNDERLINE_COLOR[:6]
    active_color = base_color + HOMOPHONE_UNDERLINE_ACTIVE_ALPHA
    inactive_color = base_color + HOMOPHONE_UNDERLINE_INACTIVE_ALPHA
    segs: list[UnderlineSegment] = []
    for seg_idx in range(member_count):
        seg_x = x + seg_idx * (seg_w + HOMOPHONE_UNDERLINE_GAP_W)
        is_active = seg_idx == active_idx
        segs.append(
            UnderlineSegment(
                x0=seg_x,
                x1=seg_x + seg_w,
                y=underline_y,
                active=is_active,
                color=active_color if is_active else inactive_color,
            )
        )
    return segs


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------


def build_token_layouts(
    state,
    tokens: list[str],
    token_widths: list[float],
    *,
    x_origin: float,
    y_start: float,
    max_row_w: float,
    max_visible_rows: int | None = None,
    flagged_indices: "frozenset[int] | set[int]" = frozenset(),
    shape_enabled: bool = False,
    hat_assignments: dict[int, tuple[int, str, str]] | None = None,
    per_char_widths: dict[int, list[float]] | None = None,
) -> list[TokenLayout]:
    """Pure per-token layout builder.

    Consumes pure data (``state``, ``tokens``, ``token_widths``, and the
    scalar geometry args) and returns the per-token paint records that
    Move 4e will assemble into a full ``LayoutModel``.

    Args:
        state: The pure ``_State`` snapshot (see
            ``internal/instance.py``). Read only. Fields consumed:
            ``shape_assignments``, ``position_assignments``. Other
            fields — ``buffer``, ``homophone_hint``, etc. — are the
            caller's responsibility to resolve into ``tokens`` and
            ``flagged_indices``.
        tokens: The token strings in buffer order. One per token.
        token_widths: Pre-measured pixel widths, one per token,
            aligned to ``tokens``. Callers with a live Skia canvas
            compute this via ``c.paint.measure_text(tok)[1].width``;
            headless callers can pass any monotone-nonneg widths.
        x_origin: Absolute x of the first token in each row. Typically
            ``panel_x + PANEL_PAD``.
        y_start: Absolute y at the TOP of the first row (i.e. the top
            of the hat-dot band). Typically ``panel_y + PANEL_PAD``.
        max_row_w: Max row width in pixels — the value passed to
            ``_flow_rows``. Caller decides whether this is the
            content-zone width (hints visible) or the full panel
            width (hints hidden by overflow). Pass the FINAL usable
            width already minus its padding.
        max_visible_rows: When set, drop rows above
            ``len(rows) - max_visible_rows`` (terminal-pinned
            viewport trim). Tokens in trimmed rows are OMITTED from
            the return list. When None, all rows survive.
        flagged_indices: Homophone-flag set. Caller resolves via
            ``internal.homophones.flagged_indices(tokens)`` (or an
            equivalent stub in tests). Absent → no underlines.
        shape_enabled: When True, tokens present in
            ``state.shape_assignments`` also receive a ``ShapeMark``.
            Mirrors the ``shape_enabled`` flag in
            ``_draw_token_rows`` — the resolution of what "enabled"
            means (settings + module flag) happens above the builder.
        hat_assignments: The letter-hat map. ``None`` means "no live
            allocator ran; fall back to alphabetic default"
            (matching ``_draw_token_rows``'s behavior).
        per_char_widths: Optional per-character prefix widths for
            precise hat / shape positioning. ``per_char_widths[i][k]``
            is the pixel width of ``tokens[i][:k]`` so
            ``per_char_widths[i][0] == 0.0`` and
            ``per_char_widths[i][len(tokens[i])] == token_widths[i]``.
            When None, hat / shape positions fall back to a
            proportional estimate; tests supply exact measurements.

    Returns:
        A fresh ``list[TokenLayout]`` — one entry per SURVIVING token
        after the ``max_visible_rows`` trim. Each entry carries its
        row-aware rect and any hat / shape / underline marks. Tokens
        on trimmed rows are omitted (matches the
        ``TokenLayout.on_visible_row=True`` invariant documented on
        the LayoutModel).

    Invariants:
        * No mutation of ``state`` or any input list / dict.
        * No Talon / Skia / shim imports.
        * Deterministic — identical inputs produce dataclass-equal
          output (frozen dataclasses compare structurally).
    """
    if not tokens:
        return []
    if len(tokens) != len(token_widths):
        # Defensive — the caller is responsible for keeping these
        # aligned; a mismatch means the token list changed between
        # measurement and layout. Rather than paint half a row we
        # bail cleanly. draw_overlay never trips this because it
        # measures immediately before wrapping.
        return []

    # State reads. state may be a stub in tests (any object exposing
    # `.shape_assignments` and `.position_assignments`), so we access
    # via getattr with a default rather than assuming _State's shape.
    shape_assignments: dict[int, str] = getattr(state, "shape_assignments", {}) or {}
    position_assignments: dict[int, tuple[int, int]] = (
        getattr(state, "position_assignments", {}) or {}
    )

    rows = _flow_rows(token_widths, max_row_w)

    # Terminal-pinned viewport trim — matches draw_overlay's
    # `rows = rows[len(rows) - max_visible_rows:]`.
    if max_visible_rows is not None and len(rows) > max_visible_rows:
        rows = rows[len(rows) - max_visible_rows :]

    layouts: list[TokenLayout] = []
    y_base = y_start
    for row in rows:
        x = x_origin
        for token_idx, tw in row:
            token = tokens[token_idx]

            # Hat first — the shape needs to know the letter-hat's char
            # index so its own char position falls on a DIFFERENT char.
            hat = _hat_for_token(
                token_idx,
                token,
                tw,
                x,
                y_base,
                hat_assignments,
                per_char_widths,
            )
            letter_char_idx = hat.char_index if hat is not None else -1

            # Shape only if enabled AND this token has an assignment.
            # Also gate on `has_hat` in draw_tokens.py — the current
            # paint code only draws the shape when a letter hat exists
            # (the shape sits on the letter-hat's neighboring char).
            # We mirror that gate exactly.
            shape: ShapeMark | None = None
            if shape_enabled and hat is not None:
                shape_name = shape_assignments.get(token_idx)
                shape = _shape_for_token(
                    token_idx,
                    token,
                    tw,
                    x,
                    y_base,
                    letter_char_idx,
                    shape_name,
                    per_char_widths,
                )

            is_flagged = token_idx in flagged_indices
            underlines = (
                _underline_segments_for_token(
                    token_idx, tw, x, y_base, position_assignments
                )
                if is_flagged
                else []
            )

            # Token paint rect. The token TEXT baseline in draw_tokens.py
            # sits at y_base + (DOT_RADIUS*2) + DOT_GAP_Y + TOKEN_FONT_SIZE
            # so the top of the text band is y_base + (DOT_RADIUS*2) +
            # DOT_GAP_Y. Rect height covers hat dot band + gap + text (a
            # tight bounding box that matches what selection/flash rects
            # cover). Downstream renderers may only need `rect.x` and
            # `rect.w`; the height is retained for hit-testing.
            rect = Rect(
                x=x,
                y=y_base,
                w=tw,
                h=(DOT_RADIUS * 2) + DOT_GAP_Y + TOKEN_FONT_SIZE,
            )

            layouts.append(
                TokenLayout(
                    index=token_idx,
                    text=token,
                    rect=rect,
                    hat=hat,
                    shape=shape,
                    underline_segments=underlines,
                    flagged=is_flagged,
                    on_visible_row=True,
                )
            )

            x += tw + TOKEN_GAP_X
        y_base += LINE_HEIGHT

    return layouts


__all__ = ["build_token_layouts"]
