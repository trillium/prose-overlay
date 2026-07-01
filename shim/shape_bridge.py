"""Slice 2 of docs/BUNDLE_SHAPE_SCOPE.md — projection wrapper preserving the
ISC-14c per-group-same-shape invariant while consulting the cursorless
bundle for allocation.

Option (b) from docs/BUNDLE_SHAPE_DECISIONS.md OQ3. The Python allocator
in `shim/shapes.py:compute_shape_assignments` is the authoritative
source of the group -> shape mapping (it clusters flagged tokens by
homophone group id first, then assigns one shape per group). Cursorless's
allocator is per-visible-token, not per-group — a naive full replacement
would sometimes hand `frame` to `there` and `bolt` to `their` in the
same buffer, silently regressing ISC-14c.

This module is the projection wrapper: it takes the group->shape output
from `compute_shape_assignments`, constructs a cursorless-native
`enabledHatStyles` map with one style per (color, group_shape) pair,
and calls the bundle for the fine-grained letter+color allocation.
The bundle picks the letter, the shim picks the shape. Same visual
outcome as if cursorless had allocated end-to-end, but ISC-14c holds.

Public surface:
  compute_hat_assignments_with_group_shapes(
      tokens, shape_assignments, old_assignments=None,
      color_for_shape="gray", stability="balanced", cursor_pos=None,
  ) -> dict[int, tuple[int, str, str]]

  Where `shape_assignments` is the group-shape output from
  `shim.shapes.compute_shape_assignments` (dict[int, str] =
  token_idx -> shape_name).

The color slot in the returned tuple carries the fully-qualified
style ('gray-frame' when the token is flagged and shape-assigned,
'gray' when unflagged). Existing readers of `hat_assignments` that
only look at the pre-'-' color get the same value as before; readers
that want the shape can .split('-').

Kept pure-Python (no talon imports) so headless tests can exercise the
projection layer without a Talon process.
"""

from typing import Callable, Optional

from .hats_js import (
    compute_hat_assignments as _bundle_compute_hat_assignments,
    build_enabled_hat_styles,
    _PROSE_COLORS,
    _PROSE_SHAPES,
)


def _validate_shape(name: str) -> bool:
    return name in _PROSE_SHAPES


def build_group_shape_enabled_styles(
    shape_assignments: dict[int, str],
    color_for_shape: str = "gray",
) -> dict[str, dict]:
    """Return a HatStyleMap that pairs one color with every shape in use.

    The returned map has:
      - every plain color name (unflagged tokens keep the classic pool)
      - `color_for_shape` crossed with every unique shape in
        `shape_assignments` (flagged tokens wear the shape their group
        was assigned)

    Design note: the shape-color is the SAME across all flagged groups
    (default `gray`) — the shape carries the group identity; the color
    stays constant so the user doesn't have to disambiguate "was that
    blue-frame or green-frame". Cursorless's allocator still gets to
    pick a distinct grapheme + color for the unflagged tokens.
    """
    styles = build_enabled_hat_styles(include_shapes=False)  # 9 plain colors
    if color_for_shape not in _PROSE_COLORS:
        # Defensive — caller passed a nonsense color; return colors-only.
        return styles
    color_penalty = styles[color_for_shape]["penalty"]
    unique_shapes = {
        s for s in shape_assignments.values() if _validate_shape(s)
    }
    for shape in unique_shapes:
        styles[f"{color_for_shape}-{shape}"] = {"penalty": color_penalty + 1}
    return styles


def project_group_shapes_onto_old_assignments(
    old_assignments: Optional[dict[int, tuple[int, str, str]]],
    shape_assignments: dict[int, str],
    color_for_shape: str = "gray",
) -> dict[int, tuple[int, str, str]]:
    """Rewrite `old_assignments` to carry the shape-suffixed style names
    for shape-assigned tokens.

    Ensures cursorless's stability comparator sees the styleName it will
    be handing back out — otherwise stability would trigger a full
    re-allocate every time a token's shape assignment changed.

    - Tokens present in `shape_assignments` get their color slot rewritten
      to `f"{color_for_shape}-{shape_name}"`.
    - Tokens NOT in `shape_assignments` keep their existing entry (which
      is a bare color, possibly still shape-suffixed if the caller mixed
      pools — we leave that alone).

    Returns a new dict; does not mutate the caller's input.
    """
    if old_assignments is None:
        return {}
    out: dict[int, tuple[int, str, str]] = {}
    for tok_idx, (char_idx, letter, style) in old_assignments.items():
        if tok_idx in shape_assignments:
            shape = shape_assignments[tok_idx]
            if _validate_shape(shape) and color_for_shape in _PROSE_COLORS:
                new_style = f"{color_for_shape}-{shape}"
                out[tok_idx] = (char_idx, letter, new_style)
                continue
        out[tok_idx] = (char_idx, letter, style)
    return out


def compute_hat_assignments_with_group_shapes(
    tokens: list[str],
    shape_assignments: dict[int, str],
    old_assignments: Optional[dict[int, tuple[int, str, str]]] = None,
    color_for_shape: str = "gray",
    stability: str = "balanced",
    cursor_pos: Optional[int] = None,
    _allocator: Callable = _bundle_compute_hat_assignments,
) -> dict[int, tuple[int, str, str]]:
    """Projection-wrapper allocator per docs/BUNDLE_SHAPE_SCOPE.md Slice 2.

    Takes the group->shape output from `shim.shapes.compute_shape_assignments`
    and calls `hats_js.compute_hat_assignments` with an `enabled_styles`
    map that has exactly the shape-suffixed styles the group allocator
    picked. Cursorless picks grapheme + color; we picked the shape.

    Args:
        tokens: buffer tokens.
        shape_assignments: dict[int, str] = token_idx -> shape_name from
            the Python group allocator. Empty dict = no tokens flagged
            (behaves identically to the colors-only path).
        old_assignments: prior tuple map for stability. If any of its
            entries need their color rewritten to a shape-suffixed style
            (because the token's shape assignment changed on this rev),
            we do that projection before calling the bundle.
        color_for_shape: which color name to pair with the shape suffix.
            Default `gray` (matches the existing per-group-shape rendering
            convention where flagged tokens wear a shape on top of a gray
            letter-hat dot).
        stability, cursor_pos: pass-through to the bundle.
        _allocator: dependency-injected bundle call for testing. Defaults
            to the real `hats_js.compute_hat_assignments`.

    Returns:
        The same shape as `hats_js.compute_hat_assignments` — dict[int,
        tuple[int, str, str]] = token_idx -> (char_idx, letter, style)
        where `style` is a fully-qualified style name. Downstream readers
        that only look at the pre-'-' color get the color; readers
        that want the shape can `.split('-')`.
    """
    if not shape_assignments:
        # No flagged tokens with shape assignments — nothing to project.
        # Colors-only pool matches the pre-Slice-2 default exactly.
        return _allocator(
            tokens,
            old_assignments=old_assignments,
            stability=stability,
            cursor_pos=cursor_pos,
        )

    enabled_styles = build_group_shape_enabled_styles(
        shape_assignments, color_for_shape=color_for_shape,
    )
    projected_old = project_group_shapes_onto_old_assignments(
        old_assignments, shape_assignments, color_for_shape=color_for_shape,
    )
    return _allocator(
        tokens,
        old_assignments=projected_old,
        stability=stability,
        cursor_pos=cursor_pos,
        enabled_styles=enabled_styles,
    )
