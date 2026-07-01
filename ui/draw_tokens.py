"""Token rendering helpers for the prose overlay.

Extracted from prose_overlay_draw.py to keep that file under the line limit.

Contains:
  _fit_text         — truncate a string to fit a max pixel width
  _flow_layout      — wrap token metrics into rows that fit a given width
  draw_cursor       — draw a blinking cursor line (optionally with amber zone)
  _draw_token_rows  — render all token rows with hats, highlights, and cursor
"""

from talon.skia.canvas import Canvas as SkiaCanvas
from talon.ui import Rect

from ....utils.overlay_kit import draw_rounded_rect
from ..internal.draw_constants import (
    DOT_RADIUS, DOT_GAP_Y, TOKEN_FONT_SIZE, TOKEN_GAP_X, LINE_HEIGHT,
    TOKEN_COLOR, HAT_COLOR, HAT_COLOR_HEX, HAT_ALPHABET,
    CURSOR_COLOR_NAVIGATE, CURSOR_COLOR_CHANGE,
    CURSOR_WIDTH, CURSOR_CHANGE_ZONE_WIDTH, CURSOR_CHANGE_ZONE_ALPHA,
    HOMOPHONE_UNDERLINE_COLOR, HOMOPHONE_UNDERLINE_HEIGHT,
    HOMOPHONE_UNDERLINE_GAP_W, HOMOPHONE_UNDERLINE_ACTIVE_HEIGHT,
    HOMOPHONE_UNDERLINE_MIN_SEGMENT_W,
    HOMOPHONE_UNDERLINE_ACTIVE_ALPHA, HOMOPHONE_UNDERLINE_INACTIVE_ALPHA,
    HOMOPHONE_SHAPE_SCALE, HOMOPHONE_SHAPE_COLOR_HEX,
)
from ..shim import shapes as _shapes
from ..internal.instance import instance as _instance


# ---------------------------------------------------------------------------
# Slice A of docs/PHONES_SPEC.md — segmented underline math
# ---------------------------------------------------------------------------


# Track (idx, member_count, tw_bucket) tuples we've already logged so the
# diagnostic prints once per regime instead of on every paint. Buckets the
# float width to 1px so trivial subpixel jitter doesn't re-trigger.
_LOGGED_SEGMENT_FALLBACKS: set[tuple[int, int, int]] = set()


def _maybe_log_segment_fallback(idx: int, tw: float, member_count: int) -> None:
    """Print a one-shot hint when a segmented underline falls back to solid
    because a segment would be narrower than MIN_SEGMENT_W. Deduplicated
    by (idx, member_count, int(tw)) so the log isn't spammed every paint.
    """
    key = (idx, member_count, int(tw))
    if key in _LOGGED_SEGMENT_FALLBACKS:
        return
    _LOGGED_SEGMENT_FALLBACKS.add(key)
    print(
        f"prose_overlay: segmented underline fell back to solid for "
        f"token idx={idx} (width={tw:.1f}px, members={member_count}; "
        f"each segment would be < {HOMOPHONE_UNDERLINE_MIN_SEGMENT_W}px)"
    )


def homophone_segment_width(tw: float, member_count: int) -> float:
    """Return the width of one segment when the underline splits into
    ``member_count`` parts with HOMOPHONE_UNDERLINE_GAP_W gaps between.

    Pure function — called both from the draw routine and from the L1
    headless tests so the math has a single source of truth. Returns the
    raw segment width even when it falls below MIN_SEGMENT_W; the caller
    decides whether to render or fall back to the solid underline.
    """
    if member_count <= 1:
        return tw
    gap_count = member_count - 1
    return (tw - gap_count * HOMOPHONE_UNDERLINE_GAP_W) / member_count


# ---------------------------------------------------------------------------
# Text fitting
# ---------------------------------------------------------------------------

def _fit_text(c: SkiaCanvas, text: str, max_w: float) -> str:
    if c.paint.measure_text(text)[1].width <= max_w:
        return text
    ellipsis = "…"
    ellipsis_w = c.paint.measure_text(ellipsis)[1].width
    for end in range(len(text) - 1, 0, -1):
        candidate = text[:end] + ellipsis
        if c.paint.measure_text(candidate)[1].width <= max_w:
            return candidate
    return ellipsis if ellipsis_w <= max_w else ""


# ---------------------------------------------------------------------------
# Flow layout
# ---------------------------------------------------------------------------

def _flow_layout(
    token_metrics: list[tuple[str, float]],
    max_w: float,
) -> list[list[tuple[int, str, float]]]:
    """Wrap (token, width) pairs into rows that fit within max_w.

    Returns a list of rows, each row a list of (token_index, token, width) tuples.
    """
    rows: list[list[tuple[int, str, float]]] = []
    current_row: list[tuple[int, str, float]] = []
    current_row_w = 0.0
    for i, (token, tw) in enumerate(token_metrics):
        needed = tw + (TOKEN_GAP_X if current_row else 0)
        if current_row and current_row_w + needed > max_w:
            rows.append(current_row)
            current_row = [(i, token, tw)]
            current_row_w = tw
        else:
            current_row.append((i, token, tw))
            current_row_w += needed
    if current_row:
        rows.append(current_row)
    return rows


# ---------------------------------------------------------------------------
# Cursor rendering
# ---------------------------------------------------------------------------

def draw_cursor(
    c: SkiaCanvas,
    x: float,
    y_top: float,
    height: float,
    change_mode: bool,
    blink_on: bool,
) -> None:
    """Draw a blinking cursor line at (x, y_top) with the given height.

    In change mode, also draws a faint amber insertion-zone rectangle.
    """
    if not blink_on:
        return
    c.paint.style = c.paint.Style.FILL
    if change_mode:
        c.paint.color = CURSOR_COLOR_CHANGE[:6] + CURSOR_CHANGE_ZONE_ALPHA
        c.draw_rect(Rect(x - CURSOR_CHANGE_ZONE_WIDTH / 2, y_top, CURSOR_CHANGE_ZONE_WIDTH, height))
        c.paint.color = CURSOR_COLOR_CHANGE
    else:
        c.paint.color = CURSOR_COLOR_NAVIGATE
    c.draw_rect(Rect(x - 1, y_top, CURSOR_WIDTH, height))


# ---------------------------------------------------------------------------
# Token row rendering
# ---------------------------------------------------------------------------

def _draw_token_rows(
    c: SkiaCanvas,
    rows: list[list[tuple[int, str, float]]],
    x_origin: float,
    y_start: float,
    hat_assignments: dict[int, tuple[int, str, str]] | None,
    cursor: int | None,
    change_mode: bool,
    blink_on: bool,
    flash_indices: list[int] | None,
    flash_color: str | None,
    selection: tuple[int, int] | None,
    tokens: list[str],
    flagged_indices: "set[int] | frozenset[int]" = frozenset(),
    shape_enabled: bool = False,
) -> None:
    """Render token rows with hat dots, flash/selection highlights, and cursor.

    x_origin  — leftmost x for each row (typically panel_x + PANEL_PAD)
    y_start   — top of the first row (typically panel_y + PANEL_PAD)
    shape_enabled — when True, paint a Cursorless-style hat shape above each
                    flagged token (Slices 1+2 of HOMOPHONE_SHAPES_PLAN.md).
                    Shape selection comes from ``instance.state.shape_assignments``
                    (Slice 2's deterministic per-flag allocator). Tokens
                    that are flagged but absent from ``shape_assignments``
                    (pool-overflow case >10 flagged tokens) get no shape;
                    they still receive the always-on underline at the
                    bottom of this function per §4.8 spillover semantics.
    """
    # Slice 2 of HOMOPHONE_SHAPES_PLAN.md — read pre-computed assignments
    # from instance.state.shape_assignments (populated by
    # shim.actions_core._recompute_hats). Slice 1's round-robin
    # `flagged_rank % 10` has been retired — stable identity across edits
    # is the whole point of this slice. Look up via .get(idx) so the
    # overflow case (>10 flagged tokens, idx omitted from the dict)
    # falls through cleanly with no shape paint.
    shape_for_idx: dict[int, str] = (
        _instance.state.shape_assignments if shape_enabled else {}
    )

    y_base = y_start
    for row in rows:
        x = x_origin

        for idx, token, tw in row:
            # Cursor in the gap before this token
            if cursor is not None and cursor == idx:
                cursor_y_top = y_base + (DOT_RADIUS * 2) + DOT_GAP_Y
                draw_cursor(c, x, cursor_y_top, TOKEN_FONT_SIZE, change_mode, blink_on)

            # Hat dot above the assigned character
            assignment = hat_assignments.get(idx) if hat_assignments else None
            has_hat = assignment is not None if hat_assignments else (idx < len(HAT_ALPHABET))

            if has_hat:
                c.paint.textsize = TOKEN_FONT_SIZE
                char_idx = assignment[0] if assignment else 0
                dot_color = HAT_COLOR_HEX.get(assignment[2], HAT_COLOR) if assignment else HAT_COLOR
                prefix_w = 0.0
                if char_idx > 0:
                    prefix_w = c.paint.measure_text(token[:char_idx])[1].width
                target_char = token[char_idx] if char_idx < len(token) else token[0]
                char_rect = c.paint.measure_text(target_char)[1]
                dot_cx = x + prefix_w + char_rect.width / 2
                dot_cy = y_base + DOT_RADIUS
                c.paint.style = c.paint.Style.FILL
                if dot_color == HAT_COLOR_HEX["black"]:
                    c.paint.color = "ffffffff"
                    c.draw_circle(dot_cx, dot_cy, DOT_RADIUS + 1)
                c.paint.color = dot_color
                c.draw_circle(dot_cx, dot_cy, DOT_RADIUS)

            # Homophone hat shape (Slice 2 — HOMOPHONE_SHAPES_PLAN.md §3)
            # Paint above the existing letter-hat dot when the token has a
            # shape assignment in instance.state.shape_assignments AND shape_enabled
            # is on. Coexists with the underline (Slice A) — both paint when
            # both flags fire; spillover tokens (idx flagged but missing
            # from shape_assignments because the 10-shape pool exhausted)
            # get only the underline, no shape. Anchored to the dot's
            # (dot_cx, dot_cy) so the shape tracks the hat character; the
            # SVG renderer centers against its own viewBox.
            shape_name = shape_for_idx.get(idx) if shape_enabled else None
            if has_hat and shape_name is not None:
                # Place the shape on a DIFFERENT character than the letter-hat
                # dot so a single token can host BOTH hats without visual
                # overlap. Per user requirement: t[h]{e}re — bracket is the
                # default letter hat (gray-h on idx 1), curly is the shape hat
                # (colored shape on idx 2). Two addressing namespaces, one
                # token, no collision.
                letter_char_idx = assignment[0] if assignment is not None else -1
                shape_char_idx = _shapes.shape_char_position(letter_char_idx, len(token))
                shape_prefix_w = 0.0
                if shape_char_idx > 0:
                    shape_prefix_w = c.paint.measure_text(token[:shape_char_idx])[1].width
                shape_target_char = token[shape_char_idx] if shape_char_idx < len(token) else token[0]
                shape_char_rect = c.paint.measure_text(shape_target_char)[1]
                shape_cx = x + shape_prefix_w + shape_char_rect.width / 2
                shape_cy = y_base + DOT_RADIUS
                _shapes.draw_hat_shape(
                    c,
                    shape_name=shape_name,
                    color=HOMOPHONE_SHAPE_COLOR_HEX,
                    cx=shape_cx,
                    cy=shape_cy,
                    scale=HOMOPHONE_SHAPE_SCALE,
                    alpha=255,
                )

            # Highlight rect (flash or selection)
            highlight_color: str | None = None
            if flash_indices is not None and flash_color is not None and idx in flash_indices:
                highlight_color = flash_color[:6] + "4d"  # 30% alpha
            elif selection is not None and selection[0] <= idx <= selection[1]:
                highlight_color = "089ad340"  # blue 25% alpha

            if highlight_color is not None:
                hl_y_top = y_base + (DOT_RADIUS * 2) + DOT_GAP_Y
                hl_pad_x = 2
                c.paint.style = c.paint.Style.FILL
                c.paint.color = highlight_color
                draw_rounded_rect(
                    c,
                    Rect(x - hl_pad_x, hl_y_top, tw + hl_pad_x * 2, TOKEN_FONT_SIZE + 2),
                    3,
                )

            # Token text
            c.paint.textsize = TOKEN_FONT_SIZE
            c.paint.color = TOKEN_COLOR
            c.draw_text(token, x, y_base + (DOT_RADIUS * 2) + DOT_GAP_Y + TOKEN_FONT_SIZE)

            if idx in flagged_indices:
                # Slice A of docs/PHONES_SPEC.md — Scenario 3.
                # If we have cycle-position info (instance.state.position_assignments
                # populated by shim.actions_core._recompute_hats) AND the group
                # has multiple members, paint a SEGMENTED underline: N
                # contiguous segments separated by HOMOPHONE_UNDERLINE_GAP_W
                # gaps. The segment whose index matches active_idx is rendered
                # taller (HOMOPHONE_UNDERLINE_ACTIVE_HEIGHT) AND fully opaque
                # (HOMOPHONE_UNDERLINE_ACTIVE_ALPHA), the others stay at the
                # base HOMOPHONE_UNDERLINE_HEIGHT with the inactive alpha.
                #
                # Falls back to the solid bar when:
                #   - no cycle info available (degraded import / pre-Slice-A
                #     state)
                #   - group_size == 1 (degenerate 1-member CSV row, OQ4)
                #   - any segment would be < HOMOPHONE_UNDERLINE_MIN_SEGMENT_W
                #     (OQ11 — render an unreadably narrow segmented bar as
                #     solid + log hint once)
                pos = _instance.state.position_assignments.get(idx)
                underline_y_base = (
                    y_base + (DOT_RADIUS * 2) + DOT_GAP_Y + TOKEN_FONT_SIZE + 2
                )
                use_segmented = pos is not None and pos[1] > 1
                seg_w = (
                    homophone_segment_width(tw, pos[1])
                    if use_segmented
                    else tw
                )
                if use_segmented and seg_w < HOMOPHONE_UNDERLINE_MIN_SEGMENT_W:
                    use_segmented = False
                    # One-shot diagnostic per token width so the log isn't
                    # spammed every paint. Inexpensive — Python ints are
                    # interned, comparison is O(1).
                    _maybe_log_segment_fallback(idx, tw, pos[1] if pos else 0)

                c.paint.style = c.paint.Style.FILL
                if not use_segmented:
                    c.paint.color = HOMOPHONE_UNDERLINE_COLOR
                    c.draw_rect(Rect(x, underline_y_base, tw, HOMOPHONE_UNDERLINE_HEIGHT))
                else:
                    active_idx, member_count = pos  # type: ignore[misc]
                    base_color = HOMOPHONE_UNDERLINE_COLOR[:6]
                    active_color = base_color + HOMOPHONE_UNDERLINE_ACTIVE_ALPHA
                    inactive_color = base_color + HOMOPHONE_UNDERLINE_INACTIVE_ALPHA
                    # The active segment renders TALLER than the base, anchored
                    # at the same TOP edge — so it visually extends DOWN past
                    # the row baseline. This keeps the row-grid stable and
                    # avoids a vertical-shift jiggle when the active position
                    # changes between paints (cycling lands on a different
                    # segment but doesn't reflow the rows).
                    for seg_idx in range(member_count):
                        seg_x = x + seg_idx * (seg_w + HOMOPHONE_UNDERLINE_GAP_W)
                        if seg_idx == active_idx:
                            c.paint.color = active_color
                            c.draw_rect(
                                Rect(
                                    seg_x,
                                    underline_y_base,
                                    seg_w,
                                    HOMOPHONE_UNDERLINE_ACTIVE_HEIGHT,
                                )
                            )
                        else:
                            c.paint.color = inactive_color
                            c.draw_rect(
                                Rect(
                                    seg_x,
                                    underline_y_base,
                                    seg_w,
                                    HOMOPHONE_UNDERLINE_HEIGHT,
                                )
                            )

            x += tw + TOKEN_GAP_X

        # Cursor after the last token in the buffer (only on the final row)
        if row and cursor is not None:
            last_idx = row[-1][0]
            if cursor == last_idx + 1 and cursor == len(tokens):
                cursor_y_top = y_base + (DOT_RADIUS * 2) + DOT_GAP_Y
                # x already advanced past last token; step back the trailing gap
                draw_cursor(c, x - TOKEN_GAP_X, cursor_y_top, TOKEN_FONT_SIZE, change_mode, blink_on)

        y_base += LINE_HEIGHT
