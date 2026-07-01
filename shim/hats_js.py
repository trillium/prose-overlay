"""Prose Overlay JS Hat Allocator

Loads the bundled Cursorless allocateHats algorithm into Talon's embedded
QuickJS engine and exposes compute_hat_assignments() with the same signature
as the Python version in prose_overlay_state.py.

Drop-in replacement: same input/output contract, better algorithm.
  - Stability: hats don't reshuffle when new words are added
  - Penalty-based scoring: prefers short unambiguous graphemes
  - Proper grapheme normalization: deburr, unicode NFC, accented chars
"""

import json
import os
import talon.lib.js as js

from ..internal.state import compute_hat_assignments as _py_compute_hat_assignments
from ..internal import trail as _trail

# ---------------------------------------------------------------------------
# Module-level JS context — created once, reused across calls
# ---------------------------------------------------------------------------

_JS_BUNDLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "js", "prose_allocate_hats.js")

_ctx: js.Context | None = None
_fn = None  # js.Object — the proseAllocateHats function

# True when JS allocator failed and the Python fallback is being used.
# Read by prose_overlay_actions_core._recompute_hats() to sync instance.hat_js_fallback.
_using_fallback: bool = False

# Repr of the last exception that forced the fallback. Sync'd onto
# instance.hat_js_last_err so the always-on debug JSONL captures WHY the
# fallback fired — the 52-events-in-one-session pattern from 2026-06-30
# had no root-cause data because the exception message only went to
# stdout (Talon log), not to the diff-based observability stream.
# Cleared to "" when a JS call succeeds cleanly.
_last_err: str = ""


def _ensure_loaded() -> None:
    global _ctx, _fn
    if _ctx is not None:
        return
    _ctx = js.Context()
    with open(_JS_BUNDLE) as f:
        _ctx.eval(f.read())
    _fn = _ctx.globals.proseAllocateHats


# ---------------------------------------------------------------------------
# Public API — matches prose_overlay_state.compute_hat_assignments signature
# ---------------------------------------------------------------------------

def compute_hat_assignments(
    tokens: list[str],
    old_assignments: dict[int, tuple[int, str, str]] | None = None,
    stability: str = "balanced",
    cursor_pos: int | None = None,
    enabled_styles: dict[str, dict] | None = None,
) -> dict[int, tuple[int, str, str]]:
    """Assign a unique (letter, color) pair to each token using the Cursorless
    hat allocation algorithm.

    Args:
        tokens: List of word strings from the prose buffer.
        old_assignments: Previous result (token_idx -> (char_idx, letter, color))
                         passed back for hat stability. None on first call.
                         The `color` slot now carries a fully-qualified
                         style name such as ``"blue"`` or ``"blue-frame"``;
                         the bundle receives it as `styleName` so the
                         stability comparator sees the schema change once
                         (on the first call after the Slice 1 bundle bump)
                         and no more. See docs/BUNDLE_SHAPE_SCOPE.md §6 risk 3.
        stability: "greedy" | "balanced" | "stable". Default "balanced".
        cursor_pos: gap index for cursor proximity ranking, or None.
        enabled_styles: opt-in shape-enabled `HatStyleMap`. When ``None``
                        (default), the bundle uses its built-in colors-only
                        default and returns bare color names — matches the
                        pre-2026-07-01 behavior exactly. When set, the map
                        MUST be JSON-serializable and its keys become the
                        legal style names the allocator can hand out.
                        Callers wanting the full 99-entry (color x shape)
                        pool can use `build_enabled_hat_styles(True)` or
                        pass their own subset.

    Returns:
        dict mapping token_index -> (char_index_within_word, letter, color)
        where the third slot carries the fully-qualified style name
        (e.g. ``"blue"`` for a color-only pool, ``"blue-frame"`` for a
        shape-enabled pool). Kept named ``color`` in the tuple for
        compatibility with the many existing readers; when Slice 3 flips
        the default the field will be renamed.
    """
    global _using_fallback, _last_err
    # Empty buffer short-circuit — the JS bundle recursion in
    # getHatRankingContext blows QuickJS's stack on 0-token input (observed
    # 2026-06-30 as `JSException('Maximum call stack size exceeded')`
    # during the recompute that immediately follows `prose_overlay_show()`
    # clearing the buffer). No hats can exist on an empty buffer, so
    # returning {} is the correct answer AND avoids the JS call entirely.
    # Clears the fallback flag + last-err because this path is a clean
    # non-JS success (not a fallback).
    if not tokens:
        _using_fallback = False
        _last_err = ""
        return {}
    try:
        _ensure_loaded()
    except Exception as e:
        print(f"prose_overlay: hat JS load failed ({e}), using Python fallback")
        _using_fallback = True
        _last_err = f"load: {e!r}"
        return _py_compute_hat_assignments(
            tokens,
            cursor_pos=len(tokens) if cursor_pos is None else cursor_pos,
            old_assignments=old_assignments,
        )

    # Convert old_assignments to the JSON shape the JS function expects.
    # Slice 2 migration: emit both `color` (legacy field, bare color) AND
    # `styleName` (fully-qualified) so a pre-2026-07-01 bundle survives
    # (reads `color`), and the post-2026-07-01 bundle preserves the shape
    # suffix on stability round-trips (reads `styleName`). See
    # docs/BUNDLE_SHAPE_SCOPE.md §6 risk 3 and docs/BUNDLE_SHAPE_DECISIONS.md
    # OQ4 for why this dual-write matters — without it the first run after
    # the bundle bump thrashes every hat because the comparator sees a
    # schema change on `oldAssignments[…].styleName`.
    old_list = []
    if old_assignments:
        for token_idx, (char_idx, letter, style) in old_assignments.items():
            # `style` in the tuple may already be a fully-qualified name
            # ("blue-frame") once callers migrate through Slice 3, or
            # the bare color today. Split for the color slot; pass the
            # whole thing as styleName.
            dash = style.find("-")
            color_bare = style if dash < 0 else style[:dash]
            old_list.append({
                "tokenIdx": token_idx,
                "charIdx": char_idx,
                "letter": letter,
                "color": color_bare,
                "styleName": style,
            })

    # Serialize the optional enabled-styles map once. `None` and `{}` both
    # tell the bundle to fall back to its own colors-only default (the
    # Slice-1 backcompat path). A concrete map opts into that pool.
    enabled_styles_json = (
        json.dumps(enabled_styles) if enabled_styles else "null"
    )

    # Call JS — pass everything as JSON strings to avoid Python→JS coercion issues.
    # proseAllocateHats returns the result JSON string directly (no callback / NewProxy):
    # crossing JS→Python via NewProxy blows QuickJS's call stack (confirmed 2026-05-21).
    # Wrapped in begin_command/end_command (paper-trail slice B) so the
    # preamble is on disk before the risky JS call fires.
    corr_id = _trail.begin_command("", "allocate_hats", {"n_tokens": len(tokens)})
    try:
        result_json: str = str(_fn(
            json.dumps(tokens),
            json.dumps(old_list),
            stability,
            json.dumps(cursor_pos if cursor_pos is not None else -1),
            enabled_styles_json,
        ))
        raw: dict[str, dict] = json.loads(result_json)
        # Convert {"0": {charIdx, letter, color}, ...} -> {0: (charIdx, letter, color), ...}
        # POST-VALIDATE char_idx against the live token text. Cursorless's JS
        # allocator preserves prior hats by `tokenIdx` and can return a
        # `charIdx` that referred to the OLD token's letter position — e.g.
        # "they're" had 'r' at idx 5; after "phones risk" swaps it to
        # "their", JS may still report charIdx=5 even though 'r' is now at
        # idx 4. Without this fix the renderer paints the letter dot past
        # the end of the new word ("hat over nothing"). We search for the
        # claimed letter in the current token and rewrite charIdx; if the
        # letter has vanished entirely we drop the assignment so the
        # downstream collision passes can reassign.
        result: dict[int, tuple[int, str, str]] = {}
        for k, v in raw.items():
            tok_idx = int(k)
            char_idx = int(v["charIdx"])
            letter = str(v["letter"]).lower()
            # Slice 2 migration: prefer `styleName` (fully-qualified,
            # possibly shape-suffixed) over `color` (legacy, bare-color).
            # Bundles built before 2026-07-01 don't emit styleName so
            # this falls through to the legacy field. Downstream tuple
            # slot is named `color` for backward compat with the many
            # existing readers.
            style_name = v.get("styleName")
            color = str(style_name) if style_name else str(v["color"])
            if tok_idx >= len(tokens):
                continue
            token = tokens[tok_idx]
            in_range = 0 <= char_idx < len(token)
            matches = in_range and token[char_idx].lower() == letter
            if matches:
                result[tok_idx] = (char_idx, letter, color)
                continue
            # Hunt for the letter in the new token.
            fixed_ci = None
            for ci, ch in enumerate(token):
                if ch.lower() == letter:
                    fixed_ci = ci
                    break
            if fixed_ci is None:
                # Letter vanished from this token entirely — drop, let the
                # next allocator run pick something new for this slot.
                continue
            result[tok_idx] = (fixed_ci, letter, color)
        _using_fallback = False
        _last_err = ""
        _trail.end_command(corr_id, ok=True)
        return result
    except Exception as e:
        _trail.end_command(corr_id, ok=False, err=repr(e))
        print(f"prose_overlay: hat JS call failed ({e}), using Python fallback")
        _using_fallback = True
        _last_err = f"call({len(tokens)} toks): {e!r}"
        return _py_compute_hat_assignments(
            tokens,
            cursor_pos=len(tokens) if cursor_pos is None else cursor_pos,
            old_assignments=old_assignments,
        )


# ---------------------------------------------------------------------------
# Enabled-styles map builder — Slice 2 helper
# ---------------------------------------------------------------------------
# The bundle exports `proseBuildEnabledHatStyles(includeShapes: bool)` on
# globalThis (see cursorless proseStandalone.ts). Calling it from Python
# would require an additional QuickJS round trip; since the palette is
# stable and small we mirror the vocabulary here so callers can build
# maps without invoking the bundle. Kept as a pure Python function for
# headless-test friendliness — the projection wrapper (shape_bridge.py)
# uses this to build the shape-enabled map that gets passed through
# `compute_hat_assignments(enabled_styles=...)`.

_PROSE_COLORS: tuple[str, ...] = (
    "gray", "blue", "green", "red", "pink",
    "yellow", "purple", "black", "white",
)
_PROSE_COLOR_PENALTIES: dict[str, int] = {
    "gray": 0, "blue": 1, "green": 1, "red": 1,
    "pink": 2, "yellow": 2, "purple": 2,
    "black": 3, "white": 3,
}

# Mirrors packages/common/src/types/command/legacy/targetDescriptorV2.types.ts
# HAT_NON_DEFAULT_SHAPES verbatim and cursorless proseStandalone.ts's
# PROSE_SHAPES. Kept in sync manually — a mismatch would only surface if
# someone renames a shape upstream, at which point the L2 grep test would
# fail on the new shape name.
_PROSE_SHAPES: tuple[str, ...] = (
    "ex", "fox", "wing", "hole", "frame",
    "curve", "eye", "play", "bolt", "crosshairs",
)


def build_enabled_hat_styles(include_shapes: bool = False) -> dict[str, dict]:
    """Build a `HatStyleMap`-shaped dict for `compute_hat_assignments`.

    Args:
        include_shapes: When True, returns the full 99-entry (color x
            [no-shape + 10 shapes]) map; when False, returns the 9-entry
            color-only default that matches the pre-2026-07-01 bundle
            behavior exactly.

    The shape penalty adds +1 to the color penalty (matches Cursorless
    upstream convention where each style component contributes to the
    total penalty). Callers that want a narrower pool (e.g. one color
    x all shapes for the homophone use case) can construct the subset
    directly — this is a convenience for the two most common cases.
    """
    out: dict[str, dict] = {}
    for color in _PROSE_COLORS:
        color_penalty = _PROSE_COLOR_PENALTIES[color]
        out[color] = {"penalty": color_penalty}
        if include_shapes:
            for shape in _PROSE_SHAPES:
                out[f"{color}-{shape}"] = {"penalty": color_penalty + 1}
    return out
