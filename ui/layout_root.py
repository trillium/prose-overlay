"""Top-level layout composition — Move 4e of the pure-function refactor.

Composes the four sub-builders shipped in Moves 4a-4d into a single
``layout(state, canvas, overlay) -> LayoutModel`` orchestrator. This is
the load-bearing wire-up: today's ``ui/draw.py:draw_overlay`` interleaves
geometry math, state reads, Talon setting lookups, and Skia paint calls
in ~200 lines. Move 4e splits that into two halves — a composition step
that produces a ``LayoutModel`` and a paint step (side-by-side and
env-gated in Commit 2) that reads from the model.

Contract
--------

::

    layout(state, canvas, overlay) -> LayoutModel

The orchestrator:

1. Reads pure state (``state.buffer.get_tokens()`` for the token list,
   ``state.screen_rect``, ``state.window_scoped``,
   ``state.homophone_hint``, ``state.homophone_shapes``, plus the
   sub-builders' state reads via each sub-builder).
2. Reads live geometry from the ``overlay`` (via its viewport for the
   ``_anchor_rect`` and ``_anchor_position`` — these are updated when
   the user reattaches the overlay, and aren't hoisted onto state yet).
3. Measures token widths via ``canvas.paint.measure_text`` — the ONLY
   impure step. Measurement fundamentally needs a live SkiaCanvas
   (Move 4a's design note: "keeping the builder pure means the
   measurement dependency is INJECTED"). This is the boundary between
   pure geometry and Skia.
4. Computes panel geometry (``panel_rect``, ``content_area``,
   ``help_area``, viewport constraints) using the same math today's
   ``draw_overlay`` uses — panel_h from PANEL_H_FRACTION, content
   fraction from CONTENT_W_FRACTION, terminal-pinned overflow trim.
5. Invokes each sub-builder with the right arguments and stitches the
   results into a ``LayoutModel``.

Why this file exists
--------------------

Sub-builders alone don't compose themselves — the panel geometry,
overflow detection, and hint-hiding logic all sit above them. Rather
than replicate this composition in every consumer (paint, debug
snapshot, headless renderer), we ship it once here. Consumers get a
single call: ``model = layout(state, canvas, overlay)``.

The orchestrator's ONLY impure operation is ``canvas.paint.measure_text``
(reads: token width and per-character prefix widths for hat / shape
positioning). Every other input flows through ``state``. Callers that
already have the panel geometry (e.g. a debug snapshot rebuilding the
model from a captured screen_rect) can bypass this composition and
call the sub-builders directly with their own numbers.

Design notes
------------

* **``canvas`` vs. ``state``.** State is pure-data; canvas is live Skia.
  We keep them separate arguments so a headless test can pass a fake
  canvas with a deterministic ``paint.measure_text`` (mapped from a
  precomputed dict) and get identical output to a live paint. Purity
  is inherited from the sub-builders — this orchestrator adds nothing
  impure beyond measurement.

* **Anchor reads come from ``overlay``.** ``overlay`` is the
  ``DismissibleOverlay`` the top-level ``draw_overlay`` receives from
  its caller. It holds a reference to the viewport (via
  ``instance.runtime.viewport`` today), and the viewport carries the
  live ``_anchor_rect`` / ``_anchor_position``. The window-scoping
  code in ``draw_overlay`` reads these directly; this orchestrator
  mirrors that pattern rather than requiring a separate ``anchor_rect``
  argument. When Move 3 eventually hoists anchor onto state, this
  routine will lose the ``overlay`` argument.

* **What if ``state.screen_rect`` is None?** ``draw_overlay`` returns a
  zero Rect and paints nothing. The orchestrator mirrors that: returns
  a ``LayoutModel`` with a zero panel rect and empty everything, so
  callers can distinguish "empty layout" from "no layout" without a
  None check at every field.

* **What if ``tokens`` is empty?** The `listening…` placeholder case.
  The orchestrator emits a ``LayoutModel`` with empty tokens and,
  when the caller's ``cursor`` is 0, a ``CursorLayout`` at the
  panel's origin. Matches ``draw_overlay``'s empty-buffer branch.

* **Per-character prefix widths.** ``build_token_layouts`` accepts an
  optional ``per_char_widths`` dict for precise hat / shape positioning.
  Live paint calls ``c.paint.measure_text(token[:k])[1].width`` for
  each hat's char index; the orchestrator does the same, batched into
  the ``per_char_widths`` dict once per draw. For tokens without a
  letter-hat assignment we skip the per-char measurement (saves a
  measure call per token) — the builder falls back to a proportional
  estimate for those, and since they don't paint a hat / shape it
  doesn't matter.

* **Homophone flagging.** Same rule as ``draw_overlay``: flags come
  from ``internal/homophones.py:flagged_indices(tokens)`` when
  ``state.homophone_hint`` OR ``_homophones.hint_enabled()`` is True.
  The module-flag path (``hint_enabled()``) is kept for parity with
  the runtime ``overlay homo on/off`` toggle.

* **Shape enable.** Same rule as ``draw_overlay``:
  ``state.homophone_shapes`` OR ``_shapes.shapes_enabled()``. Both
  paths must agree because the runtime toggle sets the module flag
  (see ``shim/shapes.py``); if state disagrees the module flag wins
  by design.

* **Anti-scope.** This module does NOT modify any sub-builder. It does
  NOT modify ``ui/draw.py`` — Commit 2 does that with a side-by-side
  paint path. It does NOT modify the existing paint code
  (``ui/draw_tokens.py``, ``ui/draw_panels.py``, ``ui/help.py``).
"""

from __future__ import annotations

from ..internal.draw_constants import (
    LINE_HEIGHT,
    PANEL_H_FRACTION,
    PANEL_PAD,
)
from ..internal import homophones as _homophones
from ..shim import shapes as _shapes_runtime
from .layout import LayoutModel, Rect
from .layout_bubbles import build_bubble_layouts
from .layout_help_cursor import build_cursor_layout, build_help_layout
from .layout_overlays import build_flash_overlay, build_selection_overlay
from .layout_tokens import build_token_layouts


# ---------------------------------------------------------------------------
# Layout fractions — mirror ui/draw.py. Kept here (not imported from
# ui/draw.py) so the orchestrator can be imported without pulling in
# talon-dependent modules. When these constants change in draw.py, mirror
# the edit here. Same duplication rationale as ui/layout_help_cursor.py's
# HELP_PAGES mirror.
# ---------------------------------------------------------------------------
CONTENT_W_FRACTION = 0.80
HELP_W_FRACTION = 0.20
PANEL_Y_OFFSET = 0


# ---------------------------------------------------------------------------
# Row wrap — must match ui/layout_tokens.py:_flow_rows exactly. Duplicated
# here so the orchestrator can compute the overflow-trim without invoking
# the token builder twice. See ui/layout_tokens.py for the canonical
# implementation and the parity rationale.
# ---------------------------------------------------------------------------


def _flow_rows(
    token_widths: list[float],
    max_w: float,
) -> list[list[tuple[int, float]]]:
    """Wrap ``token_widths`` into rows that fit ``max_w`` px each.

    Mirrors ``ui/layout_tokens.py:_flow_rows`` byte-for-byte. Duplicated
    to avoid an extra indirection through the sub-module for the sole
    purpose of the overflow / hint-hide check.
    """
    from ..internal.draw_constants import TOKEN_GAP_X

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
# Per-character prefix-width measurement helper.
# ---------------------------------------------------------------------------


def _measure_per_char_widths(
    canvas,
    tokens: list[str],
    hat_assignments: dict[int, tuple[int, str, str]] | None,
) -> dict[int, list[float]]:
    """Measure per-character prefix widths for tokens that carry a hat.

    ``build_token_layouts`` uses ``per_char_widths[i][k] = width of
    tokens[i][:k]`` to place the letter-hat dot and (when present) the
    shape hat on the RIGHT character. Live paint measures each prefix
    on demand; the orchestrator does the same up front so the builder
    stays pure.

    We skip tokens without a letter-hat assignment: those don't paint a
    hat or shape, so the proportional-estimate fallback inside the
    builder is fine for them. Saves measurement calls proportional to
    the number of un-hatted tokens (empty buffer, overflow, past
    HAT_ALPHABET, etc.).

    When ``hat_assignments`` is None (allocator hasn't run yet or has
    been cleared), the builder itself falls back to positional hats
    (idx k → HAT_ALPHABET[k]); we still measure prefixes so those
    positional hats land accurately.
    """
    per_char: dict[int, list[float]] = {}
    if not tokens:
        return per_char
    for i, tok in enumerate(tokens):
        # Skip tokens with no hat and no positional hat possibility.
        # When hat_assignments is None, the builder falls back to
        # positional hats for every token idx < HAT_ALPHABET length;
        # measure those. When hat_assignments is a dict, only measure
        # tokens present in it.
        if hat_assignments is not None and i not in hat_assignments:
            continue
        # Prefix widths: [w(''), w(tok[:1]), ..., w(tok)]. That's
        # len(tok) + 1 entries, with prefix_widths[0] == 0.
        widths: list[float] = [0.0]
        for k in range(1, len(tok) + 1):
            widths.append(canvas.paint.measure_text(tok[:k])[1].width)
        per_char[i] = widths
    return per_char


# ---------------------------------------------------------------------------
# Alt-text width measurement for homophone bubbles.
# ---------------------------------------------------------------------------


def _measure_alt_text_widths(
    canvas,
    state,
) -> dict[str, float]:
    """Measure chip alt-text widths at BUBBLE_CHIP_FONT_SIZE.

    ``build_bubble_layouts`` uses ``alt_text_widths[alt] -> pixel_width``
    to size each chip. Live paint measures each alt on demand at the
    bubble's paint font size; the orchestrator does the same up front
    so the builder stays pure.

    We only measure alts referenced by ``state.homophone_panel_alts``.
    The builder falls back to a proportional estimate when a given alt
    isn't in the dict — good enough but not pixel-accurate. Since we
    always have the canvas at orchestrator time, we always measure.

    Font size context: ``BUBBLE_CHIP_FONT_SIZE`` is what
    ``ui/draw_panels.py:_measure_bubble`` sets before measuring. The
    orchestrator saves and restores textsize around the measurement so
    the caller's paint state is preserved.
    """
    from ..internal.draw_constants import BUBBLE_CHIP_FONT_SIZE

    widths: dict[str, float] = {}
    panel_alts = getattr(state, "homophone_panel_alts", None) or {}
    if not panel_alts:
        return widths

    # Save and restore textsize so we don't clobber the caller's paint
    # state. draw_overlay sets textsize = TOKEN_FONT_SIZE right before
    # measuring tokens; if we bump it to BUBBLE_CHIP_FONT_SIZE here and
    # forget to restore, downstream measurement is silently wrong.
    prev_textsize = canvas.paint.textsize
    try:
        canvas.paint.textsize = BUBBLE_CHIP_FONT_SIZE
        for _idx, color_to_alt in panel_alts.items():
            for _color, alt in color_to_alt.items():
                if alt not in widths:
                    widths[alt] = canvas.paint.measure_text(alt)[1].width
    finally:
        canvas.paint.textsize = prev_textsize
    return widths


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------


def layout(
    state,
    canvas,
    overlay,
    *,
    hat_assignments: dict[int, tuple[int, str, str]] | None = None,
    cursor: int | None = None,
    change_mode: bool = False,
    blink_on: bool = True,
    flash_indices: list[int] | None = None,
    flash_color: str | None = None,
    selection: tuple[int, int] | None = None,
    target_label: str = "",
    using_fallback: bool = False,
    hint_font_size: int = 12,
) -> LayoutModel:
    """Compose the full LayoutModel from pure state + canvas measurement.

    Args:
        state: The pure ``_State`` snapshot (see
            ``internal/instance.py``). Fields consumed: ``buffer``,
            ``screen_rect``, ``window_scoped``, ``homophone_hint``,
            ``homophone_shapes``, ``shape_assignments``,
            ``position_assignments``, ``homophone_panel_alts``,
            ``flash_state``. Each sub-builder reads its own required
            fields; consult their docstrings for the full contract.
        canvas: A live ``talon.skia.canvas.Canvas`` or any object
            exposing ``canvas.paint.textsize`` (settable) and
            ``canvas.paint.measure_text(str) -> (unused, obj_with_width)``.
            Tests inject a fake with a deterministic ``measure_text``.
            The orchestrator sets ``paint.typeface = "Menlo"`` and
            ``paint.textsize = TOKEN_FONT_SIZE`` before measuring tokens
            (mirrors ``draw_overlay``). Font settings are NOT restored
            at the end — the caller (paint step) sets them again before
            drawing.
        overlay: The ``DismissibleOverlay`` the caller passed to
            ``draw_overlay``. Consulted for anchor state via
            ``overlay._viewport``-style lookup — today we go through
            ``instance.runtime.viewport`` (which is what draw_overlay
            does today). Kept as an argument so a future move can
            re-parent the viewport to the overlay directly without
            changing this signature.
        hat_assignments: token_index -> (char_index, letter, color).
            None when the JS allocator hasn't run; the builder falls
            back to positional letters. Same contract as
            ``draw_overlay``.
        cursor: gap index for the editing cursor. None = no cursor.
        change_mode: True when cursor is in change/replace mode.
        blink_on: current blink phase.
        flash_indices: token indices to flash.
        flash_color: 6-char hex flash color (no alpha).
        selection: inclusive (start, end) selected-token range or None.
        target_label: bottom-left window-target label. Empty ``""`` when
            no label is set.
        using_fallback: True when the JS hat allocator failed and the
            Python fallback picked assignments. Drives the orange
            chrome color scheme in the paint step.
        hint_font_size: current hint font size (adjusted by
            ``help_bigger`` / ``help_smaller`` in ``ui/draw.py``). Used
            by the help builder for row heights.

    Returns:
        A fully-populated ``LayoutModel``. When ``state.screen_rect`` is
        None (paint fires before the first recompute), returns a
        LayoutModel with a zero panel rect, empty tokens, and every
        optional field set to None or its empty default.

    Purity:
        The orchestrator's ONLY impure operation is
        ``canvas.paint.measure_text`` (and its sister
        ``canvas.paint.textsize`` write). All other reads flow through
        the ``state`` argument and the sub-builders. Sub-builders are
        pure (see their docstrings). No global module-level reads
        beyond ``_homophones.hint_enabled()`` and
        ``_shapes_runtime.shapes_enabled()`` — both mirror what
        ``draw_overlay`` reads today (module flags that runtime
        toggles flip). Both paths are read-only from this
        orchestrator's perspective.
    """
    # --- Screen-rect guard (matches draw_overlay's paint-before-recompute) ---
    sr = getattr(state, "screen_rect", None)
    if sr is None:
        return LayoutModel(
            panel=Rect(0.0, 0.0, 0.0, 0.0),
            content_area=Rect(0.0, 0.0, 0.0, 0.0),
            help_area=None,
            tokens=[],
            selection=None,
            flash=None,
            bubbles=[],
            help=None,
            cursor=None,
            target_label=target_label,
            using_fallback=using_fallback,
            hints_hidden_by_overflow=False,
        )

    # --- Anchor state via the overlay's viewport ---
    # draw_overlay does `viewport = instance.runtime.viewport;
    # anchor_rect = viewport._anchor_rect; anchor_position =
    # viewport._anchor_position`. We mirror that lookup by pulling
    # runtime off of state via the (public) `instance` module — the
    # overlay argument is retained in the signature for a future
    # move that re-parents viewport to the overlay directly.
    #
    # We use getattr to allow tests to pass a stub state that exposes
    # `runtime.viewport` directly (see the L1 orchestrator tests).
    viewport = None
    runtime = getattr(state, "_runtime_for_test", None)
    if runtime is not None:
        viewport = getattr(runtime, "viewport", None)
    if viewport is None:
        # Live path — pull the shared instance's runtime viewport. This
        # is the ONE module-global read the orchestrator does; it's
        # scoped to the anchor state that draw_overlay also reads live.
        try:
            from ..internal.instance import instance as _live_instance
            viewport = _live_instance.runtime.viewport
        except Exception:
            viewport = None
    anchor_rect = getattr(viewport, "_anchor_rect", None) if viewport is not None else None
    anchor_position = (
        getattr(viewport, "_anchor_position", "top") if viewport is not None else "top"
    )

    # --- Tokens from the buffer ---
    # state.buffer is opaque data with .get_tokens() (see instance.py
    # _State docstring — buffer is treated as data even though it's
    # technically a live object). The orchestrator does NOT accept a
    # tokens argument because state.buffer IS the source of truth;
    # draw_overlay's tokens argument is a shortcut for testing that
    # this composition eliminates.
    buffer = getattr(state, "buffer", None)
    if buffer is None:
        tokens: list[str] = []
    else:
        get_tokens = getattr(buffer, "get_tokens", None)
        tokens = list(get_tokens()) if get_tokens is not None else []

    # --- Measure canvas paint state, matching draw_overlay lines 96-100 ---
    from ..internal.draw_constants import TOKEN_FONT_SIZE

    canvas.paint.typeface = "Menlo"
    canvas.paint.textsize = TOKEN_FONT_SIZE
    token_widths: list[float] = [
        canvas.paint.measure_text(tok)[1].width for tok in tokens
    ]

    # --- Panel geometry (mirrors draw_overlay lines 105-118) ---
    window_scoped = bool(getattr(state, "window_scoped", False) and anchor_rect is not None)
    ref = anchor_rect if window_scoped else sr
    # sr.height / sr.width / sr.top / sr.left / ref.x / ref.y / ref.width
    # / ref.height are all live Talon Rect attributes; the pure orchestrator
    # reads them as opaque scalars. When a headless test supplies a stub
    # Rect it must expose the same accessors.
    panel_h = max(sr.height * PANEL_H_FRACTION, 3 * LINE_HEIGHT + PANEL_PAD * 2)
    panel_x = ref.x if window_scoped else sr.left
    panel_w = ref.width if window_scoped else sr.width
    panel_y = (
        ref.y + ref.height - panel_h
        if anchor_position == "bottom"
        else (ref.y if window_scoped else sr.top + PANEL_Y_OFFSET)
    )

    content_w = panel_w * CONTENT_W_FRACTION
    help_x = panel_x + content_w
    help_w = panel_w * HELP_W_FRACTION

    # --- Overflow step 1: auto-hide hints if content overflows content zone ---
    # Mirrors draw_overlay lines 120-132.
    hint_row_h = hint_font_size + 6
    usable_h = panel_h - PANEL_PAD * 2
    label_reserve = hint_row_h if target_label else 0
    rows = _flow_rows(token_widths, content_w - PANEL_PAD * 2)
    hints_hidden = False
    if len(rows) * LINE_HEIGHT > usable_h - label_reserve:
        # Reflow using full panel width (hints hidden).
        rows = _flow_rows(token_widths, panel_w - PANEL_PAD * 2)
        hints_hidden = True

    # --- Overflow step 2: terminal-pinned viewport if still overflowing ---
    # Mirrors draw_overlay lines 134-141.
    effective_h = usable_h if hints_hidden else (usable_h - label_reserve)
    max_visible_rows = max(1, int(effective_h / LINE_HEIGHT))

    # The row wrap the sub-builders will use — matches the SECOND flow
    # step's max_row_w so token positions align.
    max_row_w = (panel_w if hints_hidden else content_w) - PANEL_PAD * 2

    # --- Rects for the model ---
    panel_rect = Rect(x=panel_x, y=panel_y, w=panel_w, h=panel_h)
    content_area = Rect(
        x=panel_x + PANEL_PAD,
        y=panel_y + PANEL_PAD,
        w=(panel_w if hints_hidden else content_w) - PANEL_PAD * 2,
        h=usable_h,
    )
    help_area: Rect | None = (
        None
        if hints_hidden
        else Rect(
            x=help_x,
            y=panel_y + PANEL_PAD,
            w=help_w - PANEL_PAD * 2,
            h=usable_h,
        )
    )

    # --- Homophone flag set ---
    hint_enabled = bool(
        getattr(state, "homophone_hint", False) or _homophones.hint_enabled()
    )
    flagged: "frozenset[int] | set[int]" = (
        _homophones.flagged_indices(tokens) if hint_enabled else frozenset()
    )

    # --- Shape enable ---
    shape_enabled = bool(
        getattr(state, "homophone_shapes", False) or _shapes_runtime.shapes_enabled()
    )

    # --- Per-character prefix widths for hat / shape positioning ---
    per_char_widths = _measure_per_char_widths(canvas, tokens, hat_assignments)

    # --- Sub-builder invocations ---
    x_origin = panel_x + PANEL_PAD
    y_start = panel_y + PANEL_PAD

    token_layouts = build_token_layouts(
        state,
        tokens,
        token_widths,
        x_origin=x_origin,
        y_start=y_start,
        max_row_w=max_row_w,
        max_visible_rows=max_visible_rows,
        flagged_indices=flagged,
        shape_enabled=shape_enabled,
        hat_assignments=hat_assignments,
        per_char_widths=per_char_widths,
    )

    # Selection overlay — reads state.buffer.get_selection() internally.
    # The `selection` argument passed to draw_overlay by the caller is
    # ADVISORY and can override buffer state; we prefer the explicit
    # argument when supplied because paint code today gates on it. When
    # the caller doesn't pass a selection, the builder falls back to
    # state.buffer's own selection. We implement that by wrapping the
    # state in a shim that overrides get_selection when needed.
    if selection is not None:
        # Wrap state so the builder sees the caller's selection.
        selection_state = _SelectionOverrideState(state, selection)
        selection_overlay = build_selection_overlay(
            selection_state,
            tokens,
            token_widths,
            x_origin=x_origin,
            y_start=y_start,
            max_row_w=max_row_w,
            max_visible_rows=max_visible_rows,
        )
    else:
        selection_overlay = build_selection_overlay(
            state,
            tokens,
            token_widths,
            x_origin=x_origin,
            y_start=y_start,
            max_row_w=max_row_w,
            max_visible_rows=max_visible_rows,
        )

    # Flash overlay — build_flash_overlay reads state.flash_state
    # internally, but draw_overlay's flash_indices / flash_color args
    # are the AUTHORITATIVE source at paint time (they come from the
    # flash callback). We synthesize a temporary state.flash_state
    # shim when the args are supplied.
    if flash_indices is not None and flash_color is not None:
        flash_state_shim = _FlashOverrideState(state, flash_indices, flash_color)
        flash_overlay = build_flash_overlay(
            flash_state_shim,
            tokens,
            token_widths,
            x_origin=x_origin,
            y_start=y_start,
            max_row_w=max_row_w,
            max_visible_rows=max_visible_rows,
        )
    else:
        flash_overlay = build_flash_overlay(
            state,
            tokens,
            token_widths,
            x_origin=x_origin,
            y_start=y_start,
            max_row_w=max_row_w,
            max_visible_rows=max_visible_rows,
        )

    # Homophone bubbles — only when shapes are enabled (matches draw.py
    # line 204 gate).
    bubbles: list = []
    if shape_enabled:
        alt_text_widths = _measure_alt_text_widths(canvas, state)
        bubbles = build_bubble_layouts(
            state,
            tokens,
            token_widths,
            x_origin=x_origin,
            y_start=y_start,
            max_row_w=max_row_w,
            panel_rect_y=panel_y,
            panel_rect_h=panel_h,
            anchor_position=anchor_position,
            alt_text_widths=alt_text_widths,
            max_visible_rows=max_visible_rows,
        )

    # Help pager — driven by state.help_visible / state.help_page.
    help_layout = build_help_layout(
        state,
        panel_rect=panel_rect,
        hint_font_size=hint_font_size,
    )

    # Cursor — the builder reads state.cursor / state.change_mode /
    # state.blink_on but draw_overlay's cursor / change_mode / blink_on
    # args are AUTHORITATIVE at paint time. Wrap state to project the
    # caller's values.
    cursor_state = _CursorOverrideState(state, cursor, change_mode, blink_on)
    cursor_layout = build_cursor_layout(
        cursor_state,
        tokens,
        token_widths,
        x_origin=x_origin,
        y_start=y_start,
        max_row_w=max_row_w,
        max_visible_rows=max_visible_rows,
    )

    return LayoutModel(
        panel=panel_rect,
        content_area=content_area,
        help_area=help_area,
        tokens=token_layouts,
        selection=selection_overlay,
        flash=flash_overlay,
        bubbles=bubbles,
        help=help_layout,
        cursor=cursor_layout,
        target_label=target_label,
        using_fallback=using_fallback,
        hints_hidden_by_overflow=hints_hidden,
    )


# ---------------------------------------------------------------------------
# State-override shims — pass-through wrappers used when the caller's
# draw_overlay arguments override the state's fields at paint time. Each
# shim proxies attribute access to the wrapped state, overriding ONLY the
# fields the corresponding sub-builder reads.
#
# These shims are private (leading underscore) and their only purpose is
# to let the orchestrator pass a coherent state view to each pure
# sub-builder without mutating state.
# ---------------------------------------------------------------------------


class _SelectionOverrideState:
    """State proxy that overrides ``buffer.get_selection`` with an arg."""

    __slots__ = ("_wrapped", "_selection")

    def __init__(self, wrapped, selection: tuple[int, int]) -> None:
        object.__setattr__(self, "_wrapped", wrapped)
        object.__setattr__(self, "_selection", selection)

    @property
    def buffer(self):
        # Return a proxy whose get_selection() returns the override.
        return _SelectionBufferProxy(self._selection)

    def __getattr__(self, name: str):
        # Delegate every other attribute to the wrapped state.
        return getattr(self._wrapped, name)


class _SelectionBufferProxy:
    __slots__ = ("_selection",)

    def __init__(self, selection: tuple[int, int]) -> None:
        object.__setattr__(self, "_selection", selection)

    def get_selection(self):
        return self._selection


class _FlashOverrideState:
    """State proxy that overrides ``flash_state`` with (indices, color)."""

    __slots__ = ("_wrapped", "_flash_state")

    def __init__(
        self, wrapped, indices: list[int], color: str
    ) -> None:
        object.__setattr__(self, "_wrapped", wrapped)
        object.__setattr__(
            self,
            "_flash_state",
            {"indices": list(indices), "color": color},
        )

    @property
    def flash_state(self) -> dict:
        return self._flash_state

    def __getattr__(self, name: str):
        return getattr(self._wrapped, name)


class _CursorOverrideState:
    """State proxy that overrides cursor / change_mode / blink_on."""

    __slots__ = ("_wrapped", "_cursor", "_change_mode", "_blink_on")

    def __init__(
        self,
        wrapped,
        cursor: int | None,
        change_mode: bool,
        blink_on: bool,
    ) -> None:
        object.__setattr__(self, "_wrapped", wrapped)
        object.__setattr__(self, "_cursor", cursor)
        object.__setattr__(self, "_change_mode", change_mode)
        object.__setattr__(self, "_blink_on", blink_on)

    @property
    def cursor(self):
        return self._cursor

    @property
    def change_mode(self) -> bool:
        return self._change_mode

    @property
    def blink_on(self) -> bool:
        return self._blink_on

    def __getattr__(self, name: str):
        return getattr(self._wrapped, name)


__all__ = ["layout", "LayoutModel"]
