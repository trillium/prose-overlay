"""Pure help-panel and cursor layout builders — Move 4d of the pure-function
refactor.

Extracts the paginated help-pager geometry currently interleaved in
``ui/help.py:draw_help_panel`` and the blinking-cursor geometry currently
interleaved in ``ui/draw_tokens.py:_draw_token_rows`` + ``ui/draw.py``'s
empty-buffer branch into two pure builders in this module:

    build_help_layout(state, ...)   -> HelpLayout   | None
    build_cursor_layout(state, ...) -> CursorLayout | None

Neither is wired into ``draw_overlay`` yet — that's Move 4e. This move
ships extraction + tests only.

Contract
--------

Both builders are pure:

* No side effects — do NOT mutate ``state`` or any argument, do NOT
  reach into the viewport, do NOT call any Talon or Skia API.
* No Talon imports — the module is safe to import from the L1 headless
  harness. All types come from ``ui.layout`` (frozen dataclasses) plus
  ``internal.draw_constants`` (module of ints/floats/strings). The
  paginated help data (``HELP_PAGES``) is inlined below to avoid
  importing ``ui/help.py`` — that module top-level imports
  ``talon.skia.canvas`` and ``talon.ui`` which would break headless.
* Deterministic — same inputs produce dataclass-equal output.

Design notes
------------

* **Help pager vs. rotating side hints.** Two "help" surfaces exist in the
  overlay today:

    1. The rotating **side hint column** (``ui/draw.py`` lines ~220-243)
       that lives in the right 20% of the main panel and rotates one hint
       every 5s via ``help.rotate_help_ring_buffer``. This surface is
       driven by wall-clock time and has no "page" concept.
    2. The paginated **help pager** (``ui/help.py:draw_help_panel``) that
       renders BELOW the main panel when the user says ``overlay help``.
       Toggled by ``state.help_visible``; paged via ``state.help_page``;
       content is ``HELP_PAGES`` (list of ``(page_title, entries)``
       tuples).

  This module's ``build_help_layout`` targets surface #2 — the paginated
  pager. The task spec keys off ``state.help_visible`` and
  ``state.help_page``, both of which are pager fields. Surface #1 (the
  rotating ring) is inherently time-dependent and won't move onto the
  pure model without a separate rotation-cursor input; a future move
  will address it.

  The ``ui.layout.HelpLayout`` dataclass docstring mentions the side
  ring, but the FIELDS (``rows``, ``page``, ``total_pages``) fit the
  pager exactly (``page`` + ``total_pages`` are what
  ``draw_help_panel`` computes). We use the schema as-is; the docstring
  will be reconciled in the same future move that lifts the ring buffer
  onto the model.

* **Section headers as rows.** ``HELP_PAGES`` mixes ``(cmd, desc)`` tuples
  and bare ``str`` section headers. The paint code (``ui/help.py`` lines
  ~186-195) draws headers with a leading + trailing ``──`` and a bolder
  color. The builder emits headers as ``HelpRow(left="── name ──",
  right="", y=<y>)`` — the paint layer discriminates by empty ``right``
  (no two-column split) and by the leading ``──`` sentinel (bolder
  color). Keeps the model's schema uniform across row types.

* **Page title as a row.** Every drawn page has a title (``"Basics"``,
  ``"Delete"``, ...) painted at the top. The builder emits it as the
  first ``HelpRow(left=title, right="", y=<y>)`` so the model captures
  every drawn line of text and downstream renderers walk a single list.

* **Navigation footer is out of scope.** ``draw_help_panel`` also paints a
  ``"help next"  ·  "help back"  ·  page N of M`` footer with a
  separator above it. Neither belongs on ``HelpLayout.rows`` because:
  (a) the footer is a compound multi-color multi-x line, not a
  two-column row; (b) ``HelpLayout`` already carries ``page`` +
  ``total_pages`` so a downstream renderer can reconstruct the "page N
  of M" text without the model duplicating it. The model captures WHAT
  belongs on rows (title + entries + section headers); the renderer
  paints the chrome (separator + footer + panel frame) from
  ``page/total_pages`` alone.

* **Cursor rect math parity with the paint code.** ``ui/draw_tokens.py``
  paints the cursor line at ``(x, y_base + (DOT_RADIUS*2) + DOT_GAP_Y)``
  with height ``TOKEN_FONT_SIZE``. The paint function
  ``draw_cursor`` actually draws a ``CURSOR_WIDTH`` rect anchored at
  ``x - 1`` (a single-pixel left shift so the line is centered on the
  gap). We mirror the exact rect the paint code passes to Skia so a
  downstream renderer can draw the rect verbatim:

      Rect(x - 1, y_top, CURSOR_WIDTH, TOKEN_FONT_SIZE)

  In change mode ``draw_cursor`` ALSO paints an amber insertion-zone
  rect (``CURSOR_CHANGE_ZONE_WIDTH`` wide, ``CURSOR_CHANGE_ZONE_ALPHA``
  alpha) BEHIND the cursor line. That amber rect is a paint-time
  decoration keyed on ``change_mode`` — the model's ``rect`` records
  the SLIM cursor line (matching the navigate-mode geometry); paint
  reads ``change_mode`` to decide whether to draw the amber zone
  around it. Keeps the model's ``rect`` field describing "where the
  cursor line is," not "where the cursor and its optional amber halo
  are."

* **Blink phase carried through, not gated.** The paint code
  short-circuits when ``blink_on`` is False (``draw_cursor`` returns
  early). The builder DOES NOT short-circuit — it emits the layout with
  ``blink_on=False`` so downstream debug snapshots can distinguish
  "cursor blinking off" from "no cursor set." The paint layer keeps
  the blink gate.

* **Empty-buffer listening… case.** When ``tokens`` is empty and
  ``state.cursor == 0`` the paint code (``ui/draw.py`` lines ~158-166)
  draws the cursor at ``(panel_x + PANEL_PAD, panel_y + PANEL_PAD +
  DOT_RADIUS*2 + DOT_GAP_Y)`` — same x as where the ``listening...``
  placeholder text sits. The builder mirrors that path: with empty
  tokens and cursor 0, the rect sits at ``(x_origin, y_start +
  DOT_RADIUS*2 + DOT_GAP_Y)``. Any other cursor value with empty
  tokens returns ``None`` — the paint code silently skips it too.

* **Cursor-past-viewport.** When the cursor's gap index falls inside a
  row that got trimmed by the ``max_visible_rows`` viewport pin, the
  cursor is off-screen. The paint code doesn't guard this explicitly —
  ``_draw_token_rows`` only walks the surviving rows, so the cursor is
  simply never drawn. The builder mirrors: cursors on trimmed rows
  return ``None``. Downstream renderers get a clean "no cursor" signal
  rather than a rect at negative y.

* **Anti-scope.** This module does NOT touch ``ui/draw.py``,
  ``ui/draw_tokens.py``, ``ui/draw_panels.py``, ``ui/help.py``,
  ``ui/layout.py``, ``ui/layout_tokens.py``, ``ui/layout_bubbles.py``,
  or ``ui/layout_overlays.py``. Move 4e wires the builders into
  ``draw_overlay``; until then paint runs through the existing
  imperative paths.
"""

from __future__ import annotations

from ..internal.draw_constants import (
    CURSOR_WIDTH,
    DOT_GAP_Y,
    DOT_RADIUS,
    LINE_HEIGHT,
    PANEL_PAD,
    TOKEN_FONT_SIZE,
    TOKEN_GAP_X,
)
from .layout import CursorLayout, HelpLayout, HelpRow, Rect


# ---------------------------------------------------------------------------
# Paginated help pager data — inlined mirror of ui/help.py:HELP_PAGES.
#
# ui/help.py top-level imports talon.skia.canvas and talon.ui, so importing
# it from a pure module would break the L1 headless harness. Rather than
# refactor help.py (that touches the paint layer, out of scope for Move
# 4d), we mirror the data here with a lint-visible comment so any future
# edit to HELP_PAGES lands in both places. The data is short (~5 pages)
# and rarely changes — the cost of duplication is a five-line update
# once every few months; the benefit is a clean import graph.
#
# When HELP_PAGES in ui/help.py changes, mirror the edit here. There is
# no automated cross-check today; a future move can lift the shared
# data into a pure module (e.g. ui/help_content.py) that both this
# builder and the paint layer import. That's a follow-up refactor —
# scope kept tight for Move 4d.
# ---------------------------------------------------------------------------

HelpEntry = tuple[str, str] | str
HelpPage = tuple[str, list[HelpEntry]]

HELP_PAGES: list[HelpPage] = [
    ("Basics", [
        ('"bravely"', "confirm + paste"),
        ('"overlay dismiss"', "dismiss overlay"),
        ('"overlay auto"', "toggle auto-mode"),
        ('"overlay speak"', "read buffer aloud"),
        ('"overlay undo"', "undo last edit"),
        ('"overlay help"', "toggle this panel"),
    ]),
    ("Delete", [
        ('"chuck <hat>"', "delete word at hat"),
        ('"chuck past <hat>"', "delete hat through end"),
        ('"chuck head <hat>"', "delete start through hat"),
        ('"chuck tail <hat>"', "delete hat through end"),
        "hat colors (on any command)",
        ('"chuck blue <hat>"', "target colored hat"),
        ('"chuck red <hat>"', "target colored hat"),
    ]),
    ("Cursor & Edit", [
        ('"pre <hat>"', "cursor before hat"),
        ('"post <hat>"', "cursor after hat"),
        ('"pre file"', "cursor to start"),
        ('"post file"', "cursor to end"),
        ('"change <hat>"', "delete word + insert mode"),
        ('"change head <hat>"', "delete start→hat + insert"),
        ('"change tail <hat>"', "delete hat→end + insert"),
    ]),
    ("Move & History", [
        ('"bring <hat> to <hat>"', "copy word to position"),
        ('"move <hat> to <hat>"', "move word to position"),
        ('"prose history"', "show history panel"),
        ('"history pick <N>"', "reload history entry N"),
        ('"<window> bravely"', "retarget + confirm"),
    ]),
    ("Layout", [
        ('"overlay anchor"', "scope panel to window"),
        ('"overlay anchor clear"', "full-screen panel"),
        ('"overlay top"', "attach panel to top"),
        ('"overlay bottom"', "attach panel to bottom"),
    ]),
]


# ---------------------------------------------------------------------------
# help.py row-height constants — mirror ui/help.py:draw_help_panel exactly.
# Inlined for the same reason as HELP_PAGES: the source module pulls in
# Talon/Skia at import time. When any of these constants change in help.py,
# mirror the edit here. Row heights are pure functions of the caller's
# ``hint_font_size`` argument, so they're computed per-call rather than
# frozen at module load — this way a live update to the font size (via
# ``help_bigger`` / ``help_smaller``) flows into the layout without a
# reload.
# ---------------------------------------------------------------------------


def _row_heights(hint_font_size: int) -> tuple[float, float, float]:
    """Return ``(hint_row_h, section_row_h, title_row_h)`` for the given
    hint font size, mirroring ``ui/help.py:draw_help_panel``:

        hint_row_h    = HINT_FONT_SIZE + 6
        section_row_h = HINT_FONT_SIZE + 4 + 4
        title_row_h   = HINT_FONT_SIZE + 2 + 8

    The paint code advances ``cy`` by ``hint_row_h`` for each entry row,
    by ``section_row_h`` for each section header, and by ``title_row_h``
    once at the top for the page title. We use the SAME three values so
    downstream y-coordinates match the paint pass to the pixel.
    """
    hint_row_h = float(hint_font_size + 6)
    section_row_h = float(hint_font_size + 4 + 4)
    title_row_h = float(hint_font_size + 2 + 8)
    return hint_row_h, section_row_h, title_row_h


# ---------------------------------------------------------------------------
# HELP LAYOUT BUILDER
# ---------------------------------------------------------------------------


def build_help_layout(
    state,
    *,
    panel_rect: Rect,
    hint_font_size: int = 12,
    help_panel_gap: float = 8.0,
) -> HelpLayout | None:
    """Pure paginated-help-pager layout builder.

    Consumes pure data (``state``, plus the main panel's rect and the
    caller-supplied ``hint_font_size``) and returns a fresh ``HelpLayout``
    with one ``HelpRow`` per line of text the pager will paint, in
    top-to-bottom order. Returns ``None`` when the pager is hidden or
    the current page index is out of range.

    Args:
        state: The pure ``_State`` snapshot (see
            ``internal/instance.py``). Read only. Fields consumed:
            ``help_visible`` (bool), ``help_page`` (int). Any object
            exposing these two attributes is accepted — tests use a
            plain namespace.
        panel_rect: The main overlay panel's rect. Used to compute the
            pager's origin: ``pager_x = panel_rect.x + PANEL_PAD``,
            ``pager_y = panel_rect.y + panel_rect.h + help_panel_gap +
            PANEL_PAD`` (mirrors ``ui/help.py:draw_help_panel``'s
            ``panel_y = main_rect.y + main_rect.height + HELP_PANEL_GAP``
            plus its internal ``cy = panel_y + PANEL_PAD``).
        hint_font_size: The current hint font size. Injected rather than
            imported because ``ui/draw.py:HINT_FONT_SIZE`` is a mutable
            module-level global (adjusted by ``help_bigger`` /
            ``help_smaller``). Pure builder gets the CURRENT value from
            the caller. Defaults to 12 to match the current default.
        help_panel_gap: Vertical gap between the main panel's bottom
            edge and the pager's top edge. Mirrors
            ``ui/help.py:HELP_PANEL_GAP`` (default 8.0). Injected so the
            pure module doesn't reach into the paint module for it.

    Returns:
        ``HelpLayout(rows=[...], page=state.help_page,
        total_pages=len(HELP_PAGES))`` when the pager is visible and
        ``state.help_page`` is a valid index. ``None`` when
        ``state.help_visible`` is False or the page index is out of
        range (matches ``ui/help.py:draw_help_panel``'s early return
        for ``page_index < 0 or page_index >= len(HELP_PAGES)``).

        The ``rows`` list is in top-to-bottom paint order:

          1. Page title as ``HelpRow(left=title, right="", y=<title_y>)``.
          2. Each entry from ``HELP_PAGES[page][1]``. Section-header
             entries (bare strings) become
             ``HelpRow(left=f"── {name} ──", right="", y=<y>)``;
             ``(cmd, desc)`` tuples become
             ``HelpRow(left=cmd, right=desc, y=<y>)``.

        The paint-time chrome (panel frame, footer separator, "help
        next · help back · page N of M" line) is NOT in ``rows`` —
        those are reconstructed downstream from ``page`` +
        ``total_pages`` (see the module docstring's "Navigation footer
        is out of scope" note).

    Invariants:
        * No mutation of ``state`` or any input.
        * No Talon / Skia / shim imports.
        * Deterministic — identical inputs produce dataclass-equal
          output.
    """
    if not getattr(state, "help_visible", False):
        return None
    page_index = int(getattr(state, "help_page", 0))
    total_pages = len(HELP_PAGES)
    if page_index < 0 or page_index >= total_pages:
        return None

    page_title, entries = HELP_PAGES[page_index]
    hint_row_h, section_row_h, title_row_h = _row_heights(hint_font_size)

    # Paint-y anchor mirrors ui/help.py:draw_help_panel:
    #   panel_y = main_rect.y + main_rect.height + HELP_PANEL_GAP
    #   cx      = panel_x + PANEL_PAD
    #   cy      = panel_y + PANEL_PAD
    #
    # Title's baseline sits at cy + HINT_FONT_SIZE per the paint code
    # (`c.draw_text(page_title, cx, cy + HINT_FONT_SIZE)`), then cy
    # advances by title_row_h. Subsequent entry rows advance cy by
    # hint_row_h and draw at (cx, cy). Section headers advance by 4,
    # draw, then advance by HINT_FONT_SIZE + 4 (matches
    # section_row_h = HINT_FONT_SIZE + 8).
    pager_y_top = panel_rect.y + panel_rect.h + help_panel_gap
    cy = pager_y_top + PANEL_PAD

    rows: list[HelpRow] = []

    # Page title. Baseline at cy + HINT_FONT_SIZE.
    rows.append(HelpRow(left=page_title, right="", y=cy + float(hint_font_size)))
    cy += title_row_h

    for entry in entries:
        if isinstance(entry, str):
            # Section header. Paint code:
            #   cy += 4
            #   c.draw_text(f"── {entry} ──", cx, cy + HINT_FONT_SIZE)
            #   cy += HINT_FONT_SIZE + 4
            cy += 4
            rows.append(
                HelpRow(
                    left=f"── {entry} ──",
                    right="",
                    y=cy + float(hint_font_size),
                )
            )
            cy += float(hint_font_size) + 4
        else:
            # (cmd, desc) tuple. Paint code:
            #   cy += hint_row_h
            #   c.draw_text(cmd, cx, cy)          # left column
            #   c.draw_text(desc, cx + cmd_col_w, cy)  # right column
            cmd, desc = entry
            cy += hint_row_h
            rows.append(HelpRow(left=cmd, right=desc, y=cy))

    return HelpLayout(rows=rows, page=page_index, total_pages=total_pages)


# ---------------------------------------------------------------------------
# CURSOR LAYOUT BUILDER
# ---------------------------------------------------------------------------


def _flow_rows(
    token_widths: list[float],
    max_w: float,
) -> list[list[tuple[int, float]]]:
    """Wrap ``token_widths`` into rows that fit ``max_w`` px each.

    MUST match ``ui/layout_tokens.py:_flow_rows`` and
    ``ui/draw_tokens.py:_flow_layout`` exactly — the cursor position
    depends on which row each token lands on. Duplicated (not imported)
    to keep this module's import graph clean; a Move 4e follow-up will
    consolidate all callers onto a single ``layout_rowflow`` helper.
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


def build_cursor_layout(
    state,
    tokens: list[str],
    token_widths: list[float],
    *,
    x_origin: float,
    y_start: float,
    max_row_w: float,
    max_visible_rows: int | None = None,
) -> CursorLayout | None:
    """Pure blinking-cursor layout builder.

    Consumes pure data and returns a fresh ``CursorLayout`` describing
    where the cursor line should be painted. Returns ``None`` when no
    cursor is set, when the cursor falls off the visible viewport, or
    when the cursor index is out of range for the current token buffer.

    Args:
        state: The pure ``_State`` snapshot. Read only. Fields consumed:
            ``cursor`` (Optional[int] — the gap index), ``change_mode``
            (bool), ``blink_on`` (bool). Any object exposing these three
            attributes is accepted.
        tokens: The token strings in buffer order.
        token_widths: Pre-measured pixel widths, one per token, aligned
            to ``tokens``. Callers with a live Skia canvas compute this
            via ``c.paint.measure_text(tok)[1].width``; headless callers
            pass any monotone-nonneg widths.
        x_origin: Absolute x of the first token in each row. Typically
            ``panel_x + PANEL_PAD``.
        y_start: Absolute y at the TOP of the first row (the top of the
            hat-dot band). Typically ``panel_y + PANEL_PAD``.
        max_row_w: Max row width in pixels used to wrap tokens. MUST
            match what the token layout pass uses so the cursor lands
            in the same gap the paint code would draw.
        max_visible_rows: When set, drop rows above
            ``len(rows) - max_visible_rows`` (terminal-pinned viewport
            trim). A cursor whose target token was on a trimmed row
            returns ``None``. When None, all rows survive.

    Returns:
        ``CursorLayout(rect=..., change_mode=..., blink_on=...)``
        when the cursor is set and lands on a visible row.

        The rect mirrors the paint pass exactly:
        ``Rect(x - 1, y_top, CURSOR_WIDTH, TOKEN_FONT_SIZE)`` where
        ``y_top = y_base + (DOT_RADIUS * 2) + DOT_GAP_Y``.

        ``change_mode`` and ``blink_on`` are propagated verbatim from
        state so downstream renderers can paint the change-mode amber
        zone / respect the blink gate. The builder does NOT gate on
        ``blink_on`` — a False phase still returns a layout (with
        ``blink_on=False``) so debug snapshots can distinguish
        "cursor blinking off" from "no cursor set."

    Returns ``None`` when:

        * ``state.cursor`` is None (no cursor set).
        * ``tokens`` is empty AND ``state.cursor != 0`` (paint code
          only draws for cursor == 0 in the listening... branch).
        * ``state.cursor`` refers to a gap on a row that got trimmed
          by ``max_visible_rows`` (paint code skips these rows).
        * ``state.cursor`` is out of range (``> len(tokens)``).

    Invariants:
        * No mutation of ``state`` or any input.
        * No Talon / Skia / shim imports.
        * Deterministic — identical inputs produce dataclass-equal
          output.
    """
    cursor = getattr(state, "cursor", None)
    if cursor is None:
        return None
    if not isinstance(cursor, int):
        # Defensive — cursor should always be Optional[int]; anything
        # else is a caller bug. Bail rather than crash on arithmetic.
        return None
    change_mode = bool(getattr(state, "change_mode", False))
    blink_on = bool(getattr(state, "blink_on", True))

    # Empty-buffer listening... branch. ui/draw.py lines ~158-166:
    #   if cursor is not None and cursor == 0:
    #       draw_cursor at (panel_x + PANEL_PAD, panel_y + PANEL_PAD +
    #                       DOT_RADIUS*2 + DOT_GAP_Y)
    # Any other cursor value with empty tokens is silently skipped by
    # the paint code — mirror that with None.
    if not tokens:
        if cursor != 0:
            return None
        y_top = y_start + (DOT_RADIUS * 2) + DOT_GAP_Y
        rect = Rect(
            x=x_origin - 1,
            y=y_top,
            w=float(CURSOR_WIDTH),
            h=float(TOKEN_FONT_SIZE),
        )
        return CursorLayout(rect=rect, change_mode=change_mode, blink_on=blink_on)

    if len(tokens) != len(token_widths):
        # Defensive — mismatch means caller passed unaligned data.
        # Matches the parity check used by the other Move 4 builders.
        return None

    if cursor < 0 or cursor > len(tokens):
        # Out of range. Paint code checks `cursor == idx` and
        # `cursor == last_idx + 1 and cursor == len(tokens)`; anything
        # outside those never renders.
        return None

    # Wrap into rows to find which row hosts the cursor's target gap.
    rows = _flow_rows(token_widths, max_row_w)
    total_rows_before_trim = len(rows)
    if max_visible_rows is not None and len(rows) > max_visible_rows:
        rows = rows[len(rows) - max_visible_rows :]
    trimmed_row_count = total_rows_before_trim - len(rows)

    # Walk the SURVIVING rows to find where the cursor lands. Two paint
    # branches from ui/draw_tokens.py:
    #
    #   (a) Cursor in the gap BEFORE a token: draw at that token's x.
    #       Condition: `cursor is not None and cursor == idx`.
    #       Row check: iterate row's (idx, tw) pairs, matching cursor==idx.
    #   (b) Cursor AFTER the last token in the buffer: draw at
    #       `x - TOKEN_GAP_X` where x has already advanced past the
    #       final token's width and trailing gap. Condition:
    #       `cursor == last_idx + 1 and cursor == len(tokens)`.
    #       Only fires on the FINAL surviving row (last_idx is the
    #       last token in the WHOLE buffer, not the row).

    y_base = y_start
    last_visible_token_idx: int | None = None
    for row_i, row in enumerate(rows):
        x = x_origin
        for token_idx, tw in row:
            # Branch (a) — cursor in the gap before this token.
            if cursor == token_idx:
                y_top = y_base + (DOT_RADIUS * 2) + DOT_GAP_Y
                rect = Rect(
                    x=x - 1,
                    y=y_top,
                    w=float(CURSOR_WIDTH),
                    h=float(TOKEN_FONT_SIZE),
                )
                return CursorLayout(
                    rect=rect, change_mode=change_mode, blink_on=blink_on
                )
            x += tw + TOKEN_GAP_X
        # Track the last token index seen on the final surviving row so
        # branch (b) knows whether the after-last-token cursor lands on
        # this row.
        if row:
            last_visible_token_idx = row[-1][0]
        # Advance y_base only if this is not the last row we'll walk;
        # branch (b) uses the CURRENT y_base for the trailing cursor.
        if row_i < len(rows) - 1:
            y_base += LINE_HEIGHT

    # Branch (b) — cursor sits AFTER the last token in the buffer AND the
    # last token is on a visible row.
    if (
        last_visible_token_idx is not None
        and cursor == last_visible_token_idx + 1
        and cursor == len(tokens)
    ):
        # Recompute x for the final row's trailing edge. x already
        # advanced past each token by (tw + TOKEN_GAP_X) inside the
        # loop; branch (b) subtracts TOKEN_GAP_X back off. Walk the
        # final row again to reconstruct that x.
        final_row = rows[-1]
        x_after_last = x_origin
        for _, tw in final_row:
            x_after_last += tw + TOKEN_GAP_X
        cursor_x = x_after_last - TOKEN_GAP_X
        y_top = y_base + (DOT_RADIUS * 2) + DOT_GAP_Y
        rect = Rect(
            x=cursor_x - 1,
            y=y_top,
            w=float(CURSOR_WIDTH),
            h=float(TOKEN_FONT_SIZE),
        )
        return CursorLayout(rect=rect, change_mode=change_mode, blink_on=blink_on)

    # Cursor target token was on a trimmed row, or the cursor is in an
    # unreachable position (e.g. cursor == 5 but only 3 tokens exist
    # and cursor != len(tokens)). Paint code paints nothing; mirror.
    _ = trimmed_row_count  # kept for debugging; the trim state is
    # implicit in the row-walk failure above. Silence lint.
    return None


__all__ = ["build_help_layout", "build_cursor_layout", "HELP_PAGES"]
