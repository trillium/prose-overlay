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
) -> None:
    """Paint one hat shape centered at (cx, cy) on Skia canvas c.

    Two-pass FILL+STROKE compositing per mouse-clock/src/features/clock_letters/
    shapes.py:114-126:
      1. FILL in `color`
      2. STROKE in black at 0.5 px for readability on varied backgrounds

    color must be a 6-char hex (no alpha) — alpha is composited from the
    `alpha` argument (0-255). If `shape_name` is not in HAT_SHAPES or the
    Skia cache is unavailable, this is a silent no-op.
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
    fill_color = (color[:6] if len(color) >= 6 else "999999") + alpha_hex
    outline_color = "000000" + alpha_hex

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

    c.restore()
