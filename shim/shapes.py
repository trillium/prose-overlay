"""Hat-shape vocabulary for homophone-flagged tokens.

Slice 1 of docs/HOMOPHONE_SHAPES_PLAN.md. Vendored from sibling
trillium/mouse-clock (see svg/NOTICE.md). Parses the 11 SVGs from
`svg/` at module-import time and exposes:

- HAT_SHAPES: tuple of 10 spoken-form shape names (Cursorless vocabulary,
  excluding 'dot' which is the existing letter-hat dot).
- shape_pool(): the same tuple — a stable iteration order for Slice 1's
  flagged-rank round-robin.
- draw_hat_shape(c, name, color, cx, cy, scale, alpha): paint one shape
  centered at (cx, cy) on a Skia canvas, FILL+STROKE compositing per
  mouse-clock's two-pass pattern.

Internal:
- _parse_svg_entries(): mirrors mouse-clock's svg_loader._parse_svg_entries
  (xml.etree → list of (key, spoken_name, d, fill_rule)).
- _get_shape_path_cache(): mirrors shapes._get_shape_path_cache — lazy build
  of {spoken_name: skia.Path} keyed by spoken form, called on first paint.

Design notes:
- The 'cross' spoken form maps to filename 'crosshairs.svg' per upstream
  HAT_NAMES (Cursorless vocabulary convention). We preserve that mapping
  inside the loader so callers can use either the spoken name or the file
  stem without caring which is which.
- 'dot' / 'default.svg' is intentionally excluded from HAT_SHAPES — the
  existing letter-hat dot in _draw_token_rows covers that slot. The asset
  is still vendored in svg/ for completeness / future fallback rendering.
- Skia (talon.skia.Path, talon.skia.Paint) is imported lazily inside the
  cache builder so this module can be imported in a headless test context
  without crashing on the missing Skia module.
"""

import os
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Runtime toggle — mirrors the prose_overlay_homophones._hint_enabled pattern
# ---------------------------------------------------------------------------
# Talon DOES have a public live-setter (`ctx.settings["user.foo"] = value`
# on a Context object), but that path is CONTEXT-scoped — the value reverts
# when the owning context deactivates. These toggles want process-global
# session semantics (one toggle persists across overlay show/hide cycles),
# so a module-level flag is the right tool for THIS toggle specifically.
# The voice command `overlay shapes homo on/off` mutates this flag. The draw
# module ORs both (static `user.prose_overlay_homophone_shapes` setting OR
# this runtime flag) so either path turns shapes on.
# Default ON since 2026-06-30 (user keep verdict — mirrors the slice-A
# homophone-hint default flip; rationale per memory
# feedback_overlay_subtle_hints_wrong: must-perceive signals should default
# loud, not subtle). Toggle off via `overlay shapes homo off`.
_shapes_enabled: bool = True


def set_shapes_enabled(v: bool) -> None:
    global _shapes_enabled
    _shapes_enabled = bool(v)


def shapes_enabled() -> bool:
    return _shapes_enabled


# ---------------------------------------------------------------------------
# Public vocabulary
# ---------------------------------------------------------------------------

# Filename stem → Cursorless spoken-form. Mirrors
# mouse-clock/src/core/constants.py:HAT_NAMES verbatim so the vocabulary stays
# voice-compatible. 'default' → 'dot' is the only stem that doesn't echo its
# own name.
_HAT_NAMES: dict[str, str] = {
    "bolt": "bolt",
    "crosshairs": "cross",
    "curve": "curve",
    "default": "dot",
    "ex": "ex",
    "eye": "eye",
    "fox": "fox",
    "frame": "frame",
    "hole": "hole",
    "play": "play",
    "wing": "wing",
}

# Slice 1 shape pool — 10 entries, 'dot' excluded (letter-hat owns dot slot).
# Order is the Slice 1 round-robin order: paint into pool[flagged_rank % 10].
HAT_SHAPES: tuple[str, ...] = (
    "bolt", "curve", "fox", "frame", "play",
    "wing", "hole", "ex", "cross", "eye",
)

# ---------------------------------------------------------------------------
# SVG paths — load from vendored svg/
# ---------------------------------------------------------------------------

_SVG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "svg")

# Parsed once at module import; rebuilt by _get_shape_path_cache() into Skia
# Path objects on first paint.
_svg_entries: list[tuple[str, str, str, str]] = []
_shape_path_cache: dict = {}


def _parse_svg_entries() -> list[tuple[str, str, str, str]]:
    """Parse every svg/*.svg into (stem, spoken_name, d, fill_rule) tuples.

    Mirrors mouse-clock/src/rendering/svg_loader.py:_parse_svg_entries —
    same xml.etree approach, same fill-rule fallback, same namespace handling.
    Returns a list in sorted filename order so the parse is deterministic.
    """
    entries: list[tuple[str, str, str, str]] = []
    try:
        fnames = sorted(os.listdir(_SVG_DIR))
    except OSError as e:
        print(f"prose_overlay_shapes: svg/ dir unreadable ({e}); shapes disabled")
        return entries
    ns = {"svg": "http://www.w3.org/2000/svg"}
    for fname in fnames:
        if not fname.endswith(".svg"):
            continue
        stem = fname.removesuffix(".svg")
        spoken = _HAT_NAMES.get(stem, stem)
        try:
            tree = ET.parse(os.path.join(_SVG_DIR, fname))
        except ET.ParseError as e:
            print(f"prose_overlay_shapes: {fname} parse error ({e}); skipping")
            continue
        root = tree.getroot()
        for path_el in root.findall(".//svg:path", ns):
            d = path_el.get("d", "")
            fill_rule = path_el.get("fill-rule", "nonzero")
            if d:
                entries.append((stem, spoken, d, fill_rule))
    return entries


# Populate at import — cheap, ~10 ms for 11 files.
_svg_entries = _parse_svg_entries()


def _get_shape_path_cache() -> dict:
    """Build (once) and return {spoken_name: skia.Path} for HAT_SHAPES.

    Skia is imported lazily here so this module can be imported in headless
    test runs (no Talon process, no talon.skia available). On import failure
    the cache is left empty and draw_hat_shape becomes a no-op with a single
    warning print.
    """
    global _shape_path_cache
    if _shape_path_cache:
        return _shape_path_cache
    try:
        from talon.skia import Path  # type: ignore
    except ImportError as e:
        print(f"prose_overlay_shapes: talon.skia unavailable ({e}); paint disabled")
        # Sentinel so we don't retry the import on every paint call.
        _shape_path_cache = {"__skia_unavailable__": True}
        return _shape_path_cache
    for _stem, spoken, d, fill_rule in _svg_entries:
        try:
            p = Path.from_svg(d)
        except Exception as e:  # pragma: no cover — defensive against bad SVG
            print(f"prose_overlay_shapes: Path.from_svg failed for {spoken} ({e})")
            continue
        if fill_rule == "evenodd":
            p.fill_type = Path.FillType.EVENODD
        _shape_path_cache[spoken] = p
    return _shape_path_cache


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def shape_pool() -> tuple[str, ...]:
    """Return the Slice 1 round-robin shape pool (HAT_SHAPES verbatim)."""
    return HAT_SHAPES


def shape_char_position(letter_char_idx: int, token_len: int) -> int:
    """Return the char index where the homophone shape hat paints.

    The shape MUST NOT visually overlap the letter-hat dot, so it picks a
    different character in the token. Per user requirement:
      t[h]{e}re  — bracket = letter-hat (idx 1), curly = shape (idx 2).

    A token may therefore have TWO hats: a default letter hat (gray-h) AND
    a shape hat (colored shape on a different char). The two are separate
    addressing namespaces.

    Rules:
      - len(token) <= 1            → return 0 (collision unavoidable; single
                                     char tokens can't host both hats apart)
      - letter_char_idx < 0        → no letter hat assigned, no conflict;
                                     shape goes on char 0
      - otherwise                  → (letter_char_idx + 1) % token_len
    """
    if token_len <= 1:
        return 0
    if letter_char_idx < 0:
        return 0
    return (letter_char_idx + 1) % token_len


# ---------------------------------------------------------------------------
# Slice 2 — deterministic per-flag shape allocator
# ---------------------------------------------------------------------------
# Replaces Slice 1's `flagged_rank % 10` round-robin in ui/draw_tokens.py with
# a stable allocator that survives edits to other tokens. See
# docs/HOMOPHONE_SHAPES_PLAN.md §3 Slice 2.
#
# Stability strategy (per plan):
#   1. Keep each prior assignment whose token-index is still in the flagged
#      set. The shape "follows" the token through buffer edits — adding a new
#      flagged token elsewhere should not re-stamp the shapes already in use.
#   2. Assign shapes to newly-flagged indices from the pool of UNUSED shapes
#      (HAT_SHAPES minus shapes already claimed by surviving prior entries).
#   3. If the unused pool runs out (>10 flagged tokens), OMIT the overflow
#      indices from the output dict. Callers (ui/draw_tokens.py) treat a
#      missing entry as "fall back to underline only" — the underline draw
#      is always-on per HOMOPHONE_SHAPES_PLAN.md §4.8 spillover semantics, so
#      no separate fallback path is needed here.
#
# Memoization keyed on `(rev, frozenset(flagged), tokens-at-flagged-indices)`
# so repeated calls with identical inputs return the same dict reference
# (used by the draw module's no-op short-circuit). Token text at the flagged
# positions is part of the key so an edit that changes a flagged word while
# keeping the flagged set invalidates the cache.

_SHAPE_CACHE: dict[
    tuple[int, frozenset[int], tuple[str, ...]],
    dict[int, str],
] = {}
_CACHE_KEY_LIMIT = 8  # bounded — keep last N cache entries to avoid growth


def _clear_shape_cache() -> None:
    """Reset the memoization cache. Used by instance.reset() and by tests."""
    _SHAPE_CACHE.clear()


def compute_shape_assignments(
    tokens,
    flagged,
    rev: int,
    prior: "dict[int, str] | None" = None,
) -> dict[int, str]:
    """Return ``token_idx -> shape_name`` for the currently flagged tokens.

    Parameters:
        tokens: ordered sequence of buffer tokens (list[str] or tuple[str, ...])
        flagged: set/frozenset of token indices that are flagged homophones
        rev: buffer rev counter — included in the memoization key so the
             cache invalidates on every buffer mutation
        prior: previous assignment dict (typically ``instance.shape_assignments``
               from the last allocator run); shapes for indices still in the
               flagged set are preserved across calls

    Stability strategy (see module-level comment):
      Pass 1 keeps prior assignments where the prior shape is still in
      HAT_SHAPES and the index is still flagged. Pass 2 fills the remaining
      flagged indices from the pool of unused shapes. If the pool exhausts,
      the overflow indices are omitted — the caller falls back to underline.

    Memoization: keyed on ``(rev, frozenset(flagged), tokens-at-flagged)``;
    repeated calls with identical inputs return the same dict reference.
    The cache is bounded at ``_CACHE_KEY_LIMIT`` entries; oldest entries are
    dropped on insert to prevent unbounded growth across a long session.
    """
    flagged_fz = (
        flagged if isinstance(flagged, frozenset) else frozenset(flagged)
    )
    sorted_flagged = sorted(flagged_fz)
    # Include the tokens at the flagged positions in the cache key so that
    # a text change at a flagged index invalidates the cache (otherwise the
    # rev-keyed entry would survive any same-set, different-text edit).
    flagged_tokens = tuple(
        tokens[i] for i in sorted_flagged if 0 <= i < len(tokens)
    )
    cache_key = (rev, flagged_fz, flagged_tokens)
    cached = _SHAPE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    prior_map: dict[int, str] = prior or {}
    result: dict[int, str] = {}
    used_shapes: set[str] = set()

    # Pass 1 — keep prior assignments that are still valid.
    for idx in sorted_flagged:
        if idx in prior_map:
            prior_shape = prior_map[idx]
            if prior_shape in HAT_SHAPES and prior_shape not in used_shapes:
                result[idx] = prior_shape
                used_shapes.add(prior_shape)

    # Pass 2 — assign shapes to newly-flagged indices from the unused pool.
    # Iteration over HAT_SHAPES preserves the canonical pool order; the
    # first not-yet-used shape goes to the lowest unassigned flagged index.
    unused_iter = iter(s for s in HAT_SHAPES if s not in used_shapes)
    for idx in sorted_flagged:
        if idx in result:
            continue
        try:
            result[idx] = next(unused_iter)
        except StopIteration:
            # Pool exhausted — overflow. Omit this and remaining indices
            # per HOMOPHONE_SHAPES_PLAN.md §4.8 (caller falls back to
            # underline, which already paints unconditionally on flagged
            # tokens). Break (rather than continue) so the omitted set is
            # the contiguous tail of the sorted flagged list, which is
            # documented and testable behavior.
            break

    # Bounded cache — drop oldest entry if at limit. Insertion order is
    # preserved by Python's dict so the FIRST key is the oldest.
    if len(_SHAPE_CACHE) >= _CACHE_KEY_LIMIT:
        oldest = next(iter(_SHAPE_CACHE))
        del _SHAPE_CACHE[oldest]
    _SHAPE_CACHE[cache_key] = result
    return result


# Native SVG viewBox is 12 wide × 9 tall — matches mouse-clock.
_SVG_W = 12.0
_SVG_H = 9.0


def draw_hat_shape(
    c,
    shape_name: str,
    color: str,
    cx: float,
    cy: float,
    scale: float = 0.75,
    alpha: int = 255,
    outline: str | None = None,
) -> None:
    """Paint one hat shape centered at (cx, cy) on Skia canvas c.

    Two-pass FILL+STROKE compositing per mouse-clock/src/features/clock_letters/
    shapes.py:114-126:
      1. FILL in `color`
      2. STROKE in `outline` at 0.5 px (defaults to `color` itself — same hue
         as the fill, so the shape reads as a single-color glyph; pass an
         explicit contrasting outline like "000000" if you want the classic
         mouse-clock dark-outline look)

    color and outline must be 6-char hex (no alpha) — alpha is composited
    from the `alpha` argument (0-255). If `shape_name` is not in HAT_SHAPES
    or the Skia cache is unavailable, this is a silent no-op.
    """
    cache = _get_shape_path_cache()
    if cache.get("__skia_unavailable__"):
        return
    path = cache.get(shape_name)
    if path is None:
        return
    try:
        from talon.skia import Paint  # type: ignore
    except ImportError:
        return

    # Clamp alpha to 0..255 and format as 2-char hex.
    a = max(0, min(255, int(alpha)))
    alpha_hex = f"{a:02x}"
    fill_hex = color[:6] if len(color) >= 6 else "999999"
    outline_hex = outline[:6] if (outline is not None and len(outline) >= 6) else fill_hex
    fill_color = fill_hex + alpha_hex
    outline_color = outline_hex + alpha_hex

    draw_x = cx - _SVG_W * scale / 2
    draw_y = cy - _SVG_H * scale / 2

    c.save()
    c.translate(draw_x, draw_y)
    c.scale(scale, scale)

    c.paint.style = Paint.Style.FILL
    c.paint.color = fill_color
    c.draw_path(path)

    c.paint.style = Paint.Style.STROKE
    c.paint.stroke_width = 0.5
    c.paint.color = outline_color
    c.draw_path(path)

    # Reset paint.style to FILL before returning. c.save()/c.restore() saves
    # matrix + clip but NOT the paint object's state — so the STROKE style
    # we just set would leak into the next draw_text call, painting the
    # token glyphs as thin outlined strokes instead of solid fills.
    # Symptom: tokens look "black" / outlined after a shape paints above them.
    c.paint.style = Paint.Style.FILL

    c.restore()
