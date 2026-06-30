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
) -> dict[int, tuple[int, str, str]]:
    """Assign a unique (letter, color) pair to each token using the Cursorless
    hat allocation algorithm.

    Args:
        tokens: List of word strings from the prose buffer.
        old_assignments: Previous result (token_idx -> (char_idx, letter, color))
                         passed back for hat stability. None on first call.
        stability: "greedy" | "balanced" | "stable". Default "balanced".

    Returns:
        dict mapping token_index -> (char_index_within_word, letter, color)
    """
    global _using_fallback
    try:
        _ensure_loaded()
    except Exception as e:
        print(f"prose_overlay: hat JS load failed ({e}), using Python fallback")
        _using_fallback = True
        return _py_compute_hat_assignments(tokens, cursor_pos=len(tokens) if cursor_pos is None else cursor_pos)

    # Convert old_assignments to the JSON shape the JS function expects
    old_list = []
    if old_assignments:
        for token_idx, (char_idx, letter, color) in old_assignments.items():
            old_list.append({
                "tokenIdx": token_idx,
                "charIdx": char_idx,
                "letter": letter,
                "color": color,
            })

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
        ))
        raw: dict[str, dict] = json.loads(result_json)
        # Convert {"0": {charIdx, letter, color}, ...} -> {0: (charIdx, letter, color), ...}
        result = {
            int(k): (v["charIdx"], v["letter"], v["color"])
            for k, v in raw.items()
        }
        _using_fallback = False
        _trail.end_command(corr_id, ok=True)
        return result
    except Exception as e:
        _trail.end_command(corr_id, ok=False, err=repr(e))
        print(f"prose_overlay: hat JS call failed ({e}), using Python fallback")
        _using_fallback = True
        return _py_compute_hat_assignments(tokens, cursor_pos=len(tokens) if cursor_pos is None else cursor_pos)
