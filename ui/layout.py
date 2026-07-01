"""Layout model — pure-data spec for the prose overlay's paint step.

This module defines the ``LayoutModel`` dataclass tree that Move 5 of the
pure-function refactor will consume. The end-state architecture (see the
architectural discussion around ``docs/CURSORLESS_NEAR_CURSOR_BIAS.md``,
which frames the drift toward pure-function boundaries in the hat pipeline)
splits the current monolithic ``ui/draw.py:draw_overlay`` into three
composable stages:

    layout(state)     -> LayoutModel          # this file's target shape
    to_paint_ops(m)   -> list[PaintOp]        # Move 5
    paint(canvas, ops)                        # thin Skia adapter

Today, ``draw_overlay`` interleaves geometry computation, state reads
(``instance.viewport``, ``instance.shape_assignments``,
``instance.position_assignments``, ``instance.homophone_panel_alts``),
Talon setting lookups, and Skia paint calls in one 240-line routine. That
makes it impossible to headless-test the geometry, impossible to snapshot
a paint plan without booting Talon + Skia, and impossible for callers to
inspect what would be drawn without actually drawing it. The refactor
target is a pipeline in which:

  1. All reachable state (tokens, cursor, viewport, hats, shapes,
     homophone group state, help/history pagination, target label,
     fallback flag) is gathered by a caller and passed to
     ``layout(state) -> LayoutModel`` as an explicit argument bundle. No
     module-level reads of ``instance``.

  2. ``LayoutModel`` is an immutable snapshot of "what should appear
     on screen." Every rectangle, every glyph position, every color
     decision is pre-computed. No Skia references anywhere in this
     module — the model is describable to any renderer, including a
     future headless SVG or JSON dump.

  3. ``to_paint_ops(model) -> list[PaintOp]`` (Move 5) walks the model
     and emits a flat, ordered list of paint operations (rects, text,
     circles, lines) with the same paint order as the current
     ``draw_overlay`` produces today. That list is what a thin Skia
     adapter consumes.

This file only ships stage 1's *shape*. It contains zero logic — no
``__post_init__`` bodies, no computed properties, no Talon / Skia
imports. Every class is ``@dataclass(frozen=True)`` so the "model is
immutable" contract is enforced by Python itself. The intent is that
Phase D agents can wire up ``layout(state)`` against these types
without any risk that the model shape shifts under them mid-flight.

Fields on ``LayoutModel`` mirror what ``draw_overlay``'s docstring at
``ui/draw.py:53-79`` already implicitly asks for, plus the derived
values that get computed inline today (``panel_rect``,
``hints_hidden_by_overflow``, per-token positions, help-page state,
selection/flash rects, homophone bubble specs). See the field-level
docstrings for the mapping from today's inline reads to the model
fields.

Note on ``BubbleLayout`` duplication (Move 4b):

    ``internal/panel_layout.py`` already has a class named
    ``BubbleLayout`` used by ``ui/draw_panels.py:_place_bubbles``. That
    class is:

      - a plain ``class`` with ``__slots__``, NOT a dataclass;
      - MUTABLE — the placement helper writes ``x`` and ``band`` back
        into the object in place;
      - designed to be constructed with ``(ideal_x, bubble_w)`` and
        mutated by ``place_bubbles(bubbles, x_origin, outer_gap)``.

    Move 4's ``LayoutModel`` requires an *immutable* record — the
    placement decision must already have been made before the model
    exists. So this module ships its own frozen ``BubbleLayout`` whose
    ``x`` is the final placed x, whose ``band`` is retained at 0 for
    API parity with the v2 placement contract, and which carries the
    fully measured chip + shape geometry the paint step needs. The
    ``internal/panel_layout.py`` version stays as-is because
    ``draw_panels.py`` still calls into it during the transition;
    Move 4b will consolidate the two into one type once the paint
    step is running off the model.

The paint-order contract that Move 5 will honor (matching today's
``draw_overlay`` back-to-front order) is:

    panel frame -> close hint -> token rows (highlight rects before
    token text; token text before homophone underline; hat dot before
    shape hat; cursor drawn during row walk) -> bubble band -> target
    label -> help separator + rows -> history/help overlay (owned by a
    separate model in future).

This module is the schema. Move 4a wires the producer; Move 5 wires the
consumer. Both are out of scope here — this file is the contract they
agree on.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Geometry primitive
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rect:
    """Axis-aligned rectangle in screen-space pixels.

    Mirrors ``talon.ui.Rect``'s (x, y, w, h) shape so the paint adapter
    in Move 5 can trivially convert to Skia's ``Rect`` when handing off
    to the canvas. Kept as a pure dataclass here (no Talon dependency)
    so this module is fully headless-importable — L1 tests exercise
    ``LayoutModel`` without loading ``talon`` at all.

    Fields:
        x, y : top-left corner in absolute screen coordinates
               (matches Talon's Rect: y grows downward).
        w, h : width and height in px. Non-negative by convention;
               this module does not validate — that's the producer's
               job (``layout(state)``) so downstream callers can trust
               the invariant.
    """

    x: float
    y: float
    w: float
    h: float


# ---------------------------------------------------------------------------
# Token-level structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HatMark:
    """One letter-hat dot above a token character.

    Populated from ``instance.hat_assignments[token_idx]`` in the
    producer. The dot is drawn as a filled circle at the center of
    ``position``; ``letter`` is the addressable letter the user speaks
    (e.g. ``"h"`` in ``t[h]ere``); ``color`` is the palette color name
    (``"gray"``, ``"blue"``, ...) that the paint step maps to a hex
    value via ``draw_constants.HAT_COLOR_HEX``.

    Fields:
        char_index : 0-based index into the token's characters. Used
                     by the paint step to compute the dot's x within
                     the token rect (via a text-measurement pass) or,
                     under the model, already baked into ``position``.
        letter     : the character shown / addressable — usually the
                     token character at ``char_index`` but held here
                     explicitly so the model doesn't need to re-slice
                     the source token during paint.
        color      : palette color NAME (not hex). The paint step
                     resolves to hex via ``HAT_COLOR_HEX``. Storing the
                     name (not the hex) keeps the model in the same
                     vocabulary as ``instance.hat_assignments`` and
                     the shape hat, which also live in name-space.
        position   : the dot's bounding rect (typically 2*DOT_RADIUS
                     square, centered on the target character). The
                     paint step draws a filled circle inside.
    """

    char_index: int
    letter: str
    color: str
    position: Rect


@dataclass(frozen=True)
class ShapeMark:
    """One homophone-shape hat above a token character.

    Coexists with ``HatMark`` when both apply — per
    ``docs/HOMOPHONE_SHAPES_PLAN.md``, the letter hat and the shape
    hat live on DIFFERENT characters of the same token to avoid
    visual overlap. Populated from ``instance.shape_assignments`` +
    ``shim/shapes.py:shape_char_position``.

    Fields:
        shape_name : spoken shape name (``"wing"``, ``"frame"``, ...)
                     from ``shim/shapes.py:HAT_SHAPES``. NOT the SVG
                     filename stem — the paint step resolves that
                     through ``_HAT_NAMES``.
        position   : the shape's anchor rect. The SVG is centered on
                     ``(position.x + position.w/2,
                        position.y + position.h/2)`` at the given
                     scale.
        scale      : multiplier applied to the native 12x9 viewBox.
                     Typically ``HOMOPHONE_SHAPE_SCALE``.
        color      : hex color string (with alpha) for the shape fill.
                     Kept as hex here — the shape's color decision
                     lives in a different palette than the letter
                     hats (currently a single amber constant) so name
                     resolution would be misleading.
    """

    shape_name: str
    position: Rect
    scale: float
    color: str


@dataclass(frozen=True)
class UnderlineSegment:
    """One segment of a token's homophone underline.

    A flagged homophone token gets an underline drawn from
    ``docs/PHONES_SPEC.md`` Slice A. When the group has one member,
    the token gets a single-segment solid underline. When it has N
    members, it gets N segments separated by
    ``HOMOPHONE_UNDERLINE_GAP_W`` gaps; the segment at the active
    position is drawn taller and fully opaque, the rest at the base
    height with the inactive alpha.

    The producer emits one ``UnderlineSegment`` per drawn segment,
    already sized and positioned. The paint step just draws each
    rect — no group-size math at paint time.

    Fields:
        x0, x1 : segment x range in absolute screen coords. Width is
                 ``x1 - x0``; kept as (x0, x1) rather than (x, w) so
                 the paint step's rect-construction reads naturally
                 as "from x0 to x1 at y with a computed height."
        y      : segment top y in absolute screen coords.
        active : whether this segment is the currently-active
                 position in its homophone group. Paint step uses
                 this to pick the taller height and higher alpha.
        color  : hex color with alpha for this segment. The producer
                 has already applied the active/inactive alpha
                 (``HOMOPHONE_UNDERLINE_ACTIVE_ALPHA`` /
                 ``HOMOPHONE_UNDERLINE_INACTIVE_ALPHA``) so the paint
                 step doesn't need to know about group state.
    """

    x0: float
    x1: float
    y: float
    active: bool
    color: str


@dataclass(frozen=True)
class TokenLayout:
    """Per-token paint geometry.

    Produced by the future ``layout()`` function from the raw tokens
    list plus the state maps (``hat_assignments``, ``shape_assignments``,
    ``position_assignments``, ``flagged_indices``, and the flow-layout
    row wrap). One ``TokenLayout`` per token that survives the
    overflow-trim step — tokens on rows that got scrolled off the
    top of the panel are NOT included, matching today's behavior
    where ``rows = rows[len(rows) - max_visible_rows:]`` drops them
    before paint.

    Fields:
        index          : the token's ORIGINAL index in the buffer
                         (not the row-visible index). Preserved so
                         callers can correlate model tokens to
                         ``instance.buffer`` entries — needed by
                         debug snapshots and by any future overlay
                         inspector.
        text           : the token string as it will be painted. May
                         differ from the buffer token if a formatter
                         normalized it — the model stores the paint
                         form, not the source form.
        rect           : the token's bounding rect. The paint step
                         draws the token text with its baseline at
                         ``rect.y + rect.h`` (matching today's
                         ``y_base + (DOT_RADIUS*2) + DOT_GAP_Y +
                         TOKEN_FONT_SIZE`` math, pre-baked here).
        hat            : optional letter-hat mark. ``None`` when the
                         token has no ``hat_assignments`` entry (this
                         is more common than it looks — overflow
                         tokens and tokens past ``HAT_ALPHABET``'s
                         limit both fall through).
        shape          : optional shape-hat mark. ``None`` when the
                         token isn't in ``instance.shape_assignments``
                         (unflagged, shape-disabled, or 11th+ group's
                         pool-overflow token).
        underline_segments
                       : list of underline segments, empty when the
                         token is unflagged. For a solid-fallback
                         underline (single-member group or
                         MIN_SEGMENT_W fallback per
                         ``ui/draw_tokens.py:homophone_segment_width``)
                         this list holds exactly ONE segment
                         spanning the full token width.
        flagged        : whether the token is a flagged homophone.
                         Redundant with ``bool(underline_segments)``
                         at the paint level but useful for callers
                         that want to know "is this token part of a
                         group" without walking the segments list.
        on_visible_row : whether this token survived the overflow
                         scroll trim. Always True in this schema —
                         tokens that didn't survive aren't in
                         ``LayoutModel.tokens`` at all. The field is
                         retained for future selective-hiding
                         semantics (e.g. off-viewport tokens that
                         we want to know about but not paint).
    """

    index: int
    text: str
    rect: Rect
    hat: HatMark | None
    shape: ShapeMark | None
    underline_segments: list[UnderlineSegment]
    flagged: bool
    on_visible_row: bool


# ---------------------------------------------------------------------------
# Overlay-level structures (drawn ABOVE or ACROSS the token rows)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SelectionOverlay:
    """The current selection highlight, when any tokens are selected.

    Emitted when ``ui/draw.py``'s ``selection`` argument is not None.
    Under today's implementation the selection is a single (start,
    end) inclusive index range and the rect is drawn per-token; the
    model flattens that into a list of rects so the paint step is
    trivially "for r in rects: draw filled r."

    Fields:
        rects : one rect per selected token, in token order. Colored
                by the paint step with the current selection color
                (``"089ad340"`` today — 25% alpha blue).
    """

    rects: list[Rect]


@dataclass(frozen=True)
class FlashOverlay:
    """A brief highlight over specific tokens (flash actions).

    Emitted when ``ui/draw.py``'s ``flash_indices`` argument is not
    None. Today the flash is a 30% alpha wash of ``flash_color`` over
    each named token; the model bakes the color into this record so
    the paint step doesn't need to pull the constant from a global.

    Fields:
        rects : one rect per flashed token, in token order.
        color : hex color with alpha for the flash. The producer has
                already applied the alpha suffix
                (today's ``flash_color[:6] + "4d"``).
    """

    rects: list[Rect]
    color: str


# ---------------------------------------------------------------------------
# Homophone bubble panel
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BubbleLayout:
    """One homophone-panel bubble's fully placed geometry.

    See the module docstring's "Note on ``BubbleLayout`` duplication"
    for why this class exists alongside
    ``internal/panel_layout.py:BubbleLayout``. Move 4b will
    consolidate the two.

    The fields mirror what ``ui/draw_panels.py:_Bubble`` currently
    holds internally, minus the mutation-in-place ``x`` / ``band`` —
    those are already resolved here. Chip data is expressed as
    (color_name, alt_text, chip_w) triples matching today's
    ``left_chip`` / ``right_chip`` tuples so the paint step can
    consume them without repacking.

    Fields:
        token_idx    : the token this bubble annotates. Preserved for
                       debug snapshots and inspector overlays;
                       geometry is fully baked so the paint step
                       doesn't need it.
        x            : final placed x (post-clamp, post-right-shift).
                       Absolute screen coords.
        y            : bubble band's top y — a single value across
                       all bubbles in a given ``LayoutModel``.
        w            : total bubble width including both chips + gaps
                       + shape footprint. Height is implicit in the
                       chip + shape footprint; the paint step uses
                       the chip height for the visual bounding box
                       and centers the shape vertically.
        h            : bubble height. Baked here so the paint step
                       doesn't have to re-derive from chip font size.
        shape_name   : spoken shape name for the central glyph.
        shape_scale  : scale for the SVG glyph inside the bubble
                       (typically ``BUBBLE_SHAPE_SCALE``).
        left_chip    : ``(color_name, alt_text, chip_w)``. Always
                       present — every bubble has at least one alt.
        right_chip   : optional second chip. ``None`` for
                       2-member groups where only one alt is shown.
        band         : v2 placement contract retains this field for
                       API parity but always sets it to 0. See
                       ``internal/panel_layout.py`` for the v1.5
                       history (multi-row wrap removed 2026-06-30).
    """

    token_idx: int
    x: float
    y: float
    w: float
    h: float
    shape_name: str
    shape_scale: float
    left_chip: tuple[str, str, float]
    right_chip: tuple[str, str, float] | None
    band: int


# ---------------------------------------------------------------------------
# Help side panel
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HelpRow:
    """One row of the rotating help side panel.

    ``left`` is the command (rendered in ``HINT_CMD_COLOR``),
    ``right`` is the description (rendered in ``HINT_COLOR``). The
    producer has already run ``_fit_text`` to truncate long entries
    with an ellipsis — the paint step doesn't need to know the
    column widths.

    Fields:
        left  : the command text, already truncated to fit.
        right : the description text, already truncated to fit.
        y     : the row's baseline y in absolute screen coords.
    """

    left: str
    right: str
    y: float


@dataclass(frozen=True)
class HelpLayout:
    """The help side panel's fully-resolved paint state.

    Emitted when ``_hints_hidden_by_overflow`` is False (today's
    inline global). Under overflow the model just carries ``help =
    None`` and the paint step draws no help zone.

    Fields:
        rows        : help rows in top-to-bottom paint order. The
                      producer has already run
                      ``rotate_help_ring_buffer`` so the paint step
                      doesn't need to know about time or rotation
                      interval.
        page        : the current help page index (0-based). Kept for
                      debug / inspector; the rows are already the
                      correct page's content.
        total_pages : total number of pages available. Same rationale
                      as ``page``.
    """

    rows: list[HelpRow]
    page: int
    total_pages: int


# ---------------------------------------------------------------------------
# Cursor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CursorLayout:
    """The blinking cursor's paint state.

    Emitted when ``ui/draw.py``'s ``cursor`` argument is not None
    AND the cursor's gap index falls somewhere paintable (either in
    the gap before a visible token or in the trailing gap after the
    last token). When the cursor is off-viewport due to overflow
    scroll, the model sets ``cursor = None``.

    Fields:
        rect        : the cursor's paint rect. In navigate mode this
                      is a 1-2 px vertical line; in change mode the
                      producer expands the rect to include the amber
                      change-zone (see ``draw_tokens.py:draw_cursor``).
        change_mode : whether the cursor is in change/replace mode.
                      Selects the CHANGE color vs the NAVIGATE color
                      at paint time.
        blink_on    : current blink phase. When False the paint step
                      skips drawing entirely — the field is kept in
                      the model rather than gating at the producer
                      so a debug snapshot can distinguish "no cursor"
                      from "cursor blinking off."
    """

    rect: Rect
    change_mode: bool
    blink_on: bool


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayoutModel:
    """The full paint plan for one draw of the prose overlay.

    Consumed by Move 5's ``to_paint_ops(model) -> list[PaintOp]``. All
    inputs today's ``draw_overlay`` reads (arguments + ``instance``
    globals + Talon settings) have been resolved by the producer into
    the fields below. The paint step needs nothing else — no Talon,
    no ``instance``, no settings lookups.

    Fields:
        panel               : the outer panel frame's rect
                              (``panel_x, panel_y, panel_w, panel_h``
                              in today's code).
        content_area        : left content zone
                              (``CONTENT_W_FRACTION`` of panel_w).
                              Where token rows are drawn.
        help_area           : right help zone
                              (``HELP_W_FRACTION`` of panel_w). None
                              when hints are hidden by overflow, so
                              the paint step knows to skip the
                              separator + rows entirely.
        tokens              : per-token paint records in ROW-VISIBLE
                              order. Overflow-scrolled tokens are
                              already omitted (see
                              ``TokenLayout.on_visible_row``).
        selection           : selection overlay if any tokens are
                              selected. None otherwise.
        flash               : flash overlay if a flash action is
                              currently painting. None otherwise.
        bubbles             : homophone bubble specs, one per
                              shape-hatted token with a
                              ``homophone_panel_alts`` entry. Empty
                              list when shapes are disabled or no
                              flagged tokens have panel alts.
        help                : help side panel state. None when
                              ``hints_hidden_by_overflow`` is True.
        cursor              : cursor paint state. None when no cursor
                              is set or the cursor is off-viewport.
        target_label        : bottom-left window-target label text.
                              Empty string ``""`` when no label is
                              currently set (today's argument
                              default) — the paint step decides
                              whether to draw based on emptiness
                              plus the ``hints_hidden_by_overflow``
                              flag.
        using_fallback      : True when the JS hat allocator failed
                              and the Python fallback picked
                              assignments. Drives the "orange
                              chrome" color scheme
                              (``BG_COLOR_FALLBACK``,
                              ``BORDER_COLOR_FALLBACK``).
        hints_hidden_by_overflow
                            : True when the content zone doesn't fit
                              on one panel-height, causing the hint
                              column + target label to be dropped and
                              the token rows to use the full panel
                              width. Mirrors today's
                              ``_hints_hidden_by_overflow`` global,
                              lifted into the model so the paint
                              step doesn't reach into ``ui/draw.py``
                              for it.
    """

    panel: Rect
    content_area: Rect
    help_area: Rect | None
    tokens: list[TokenLayout]
    selection: SelectionOverlay | None
    flash: FlashOverlay | None
    bubbles: list[BubbleLayout]
    help: HelpLayout | None
    cursor: CursorLayout | None
    target_label: str
    using_fallback: bool
    hints_hidden_by_overflow: bool


# ---------------------------------------------------------------------------
# Notes for Phase D agents
# ---------------------------------------------------------------------------
#
# 1. Do NOT add computed properties or __post_init__ bodies here. The frozen
#    contract is that the producer bakes every value; the paint step reads
#    without transformation.
#
# 2. Do NOT import from talon, talon.skia, or talon.ui. This module is
#    imported by the L1 headless tests (which run without Talon) and any
#    Talon-side import would break that.
#
# 3. When the producer needs a new geometry primitive that doesn't fit any
#    existing dataclass, add a new frozen dataclass here — do NOT reach
#    for tuples or dicts. Named fields with type annotations are the
#    contract.
#
# 4. ``field`` is imported for future defaults (e.g. ``field(default_factory=list)``)
#    but not currently used — none of the fields need mutable defaults
#    because the producer always supplies concrete values. Kept in the
#    import so future edits don't need to touch the import line.
_ = field  # explicitly acknowledge the unused import for lint/tooling
