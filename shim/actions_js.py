"""Prose Overlay JS Action Runner

Loads the bundled Cursorless action geometry shim into Talon's embedded QuickJS
engine and exposes run_action() for computing declarative edit plans.

The shim implements seven actions as pure string geometry on a flat single-line
document — no VS Code / ide() dependency:
  - remove               → delete target's content range
  - setSelection         → set cursor to target's content range (no edit)
  - clearAndSetSelection → delete content, collapse cursor there (change)
  - replaceWithTarget    → replace destination's range with source's text (bring)
  - moveToTarget         → replace destination + delete source (move)
  - setSelectionBefore   → set cursor to start of target range
  - setSelectionAfter    → set cursor to end of target range

All Python→JS arguments are passed as json.dumps() strings and parsed with
JSON.parse() on the JS side. This avoids the JSException stack overflow bug
that occurs when passing native Python objects across the QuickJS boundary on
the speech event thread.

Pattern: identical to prose_overlay_hats_js.py — module-level context created
once, reused across calls.
"""

import json
import os
import talon.lib.js as js

# ---------------------------------------------------------------------------
# Module-level JS context — created once, reused across calls
# ---------------------------------------------------------------------------

_JS_BUNDLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "js", "prose_actions.js")

_ctx: js.Context | None = None
_fn = None  # js.Object — the proseRunAction function


def _ensure_loaded() -> None:
    global _ctx, _fn
    if _ctx is not None:
        return
    _ctx = js.Context()
    with open(_JS_BUNDLE) as f:
        _ctx.eval(f.read())
    _fn = _ctx.globals.proseRunAction


# ---------------------------------------------------------------------------
# Target / document helpers
# ---------------------------------------------------------------------------

def _make_target(
    start_char: int,
    end_char: int,
    is_reversed: bool = False,
    line: int = 0,
) -> dict:
    """Build a TargetObj dict for the JS shim (single-line document)."""
    return {
        "contentRange": {
            "start": {"line": line, "character": start_char},
            "end":   {"line": line, "character": end_char},
        },
        "isReversed": is_reversed,
    }


def _make_document(text: str, anchor_char: int = 0, active_char: int = 0) -> dict:
    """Build a DocumentObj dict for the JS shim."""
    return {
        "text": text,
        "selectionAnchorChar": anchor_char,
        "selectionActiveChar": active_char,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_action(
    action_name: str,
    source_start_char: int,
    source_end_char: int,
    document_text: str,
    *,
    dest_start_char: int | None = None,
    dest_end_char: int | None = None,
    cursor_anchor_char: int = 0,
    cursor_active_char: int = 0,
    source_is_reversed: bool = False,
    dest_is_reversed: bool = False,
) -> dict:
    """Run a prose shim action and return the edit plan as a Python dict.

    Args:
        action_name:        One of the seven action names (e.g. "remove", "bring").
        source_start_char:  Start character offset of the source target in document_text.
        source_end_char:    End character offset of the source target.
        document_text:      Full text of the prose buffer (single line, space-joined tokens).
        dest_start_char:    Start of destination target (required for replaceWithTarget/move).
        dest_end_char:      End of destination target.
        cursor_anchor_char: Current cursor anchor character offset.
        cursor_active_char: Current cursor active character offset.
        source_is_reversed: Whether the source selection is reversed.
        dest_is_reversed:   Whether the destination selection is reversed.

    Returns:
        dict with keys:
            edits         — list of edit ops (each a dict with 'type' and geometry)
            newSelections — list of selection dicts {anchor: {line,character}, active: ...}
        or on error:
            {"error": str}

    Raises:
        RuntimeError if the JS bundle fails to load.
    """
    _ensure_loaded()

    source = _make_target(source_start_char, source_end_char, source_is_reversed)

    dest: dict | None = None
    if dest_start_char is not None and dest_end_char is not None:
        dest = _make_target(dest_start_char, dest_end_char, dest_is_reversed)

    doc = _make_document(document_text, cursor_anchor_char, cursor_active_char)

    # All args as JSON strings — avoids Python→QuickJS coercion crash
    result_json: str = _fn(
        json.dumps(action_name),
        json.dumps(source),
        json.dumps(dest),
        json.dumps(doc),
    )

    return json.loads(str(result_json))


# ---------------------------------------------------------------------------
# High-level convenience wrappers (mirror prose_overlay.py's action names)
# ---------------------------------------------------------------------------

def action_remove(token_start: int, token_end: int, text: str) -> dict:
    """Delete the character range [token_start, token_end) from text."""
    return run_action("remove", token_start, token_end, text)


def action_set_selection(
    token_start: int, token_end: int, text: str, is_reversed: bool = False
) -> dict:
    """Set cursor to the character range (no edit)."""
    return run_action(
        "setSelection", token_start, token_end, text, source_is_reversed=is_reversed
    )


def action_clear_and_set_selection(token_start: int, token_end: int, text: str) -> dict:
    """Delete the range and collapse cursor there (change mode)."""
    return run_action("clearAndSetSelection", token_start, token_end, text)


def action_replace_with_target(
    src_start: int, src_end: int,
    dst_start: int, dst_end: int,
    text: str,
) -> dict:
    """Replace destination range with source's text (bring)."""
    return run_action(
        "replaceWithTarget", src_start, src_end, text,
        dest_start_char=dst_start, dest_end_char=dst_end,
    )


def action_move_to_target(
    src_start: int, src_end: int,
    dst_start: int, dst_end: int,
    text: str,
) -> dict:
    """Replace destination with source text, then delete source (move).

    Returns two edit ops. Python must apply them in reverse-offset order
    to avoid character-shift errors.
    """
    return run_action(
        "moveToTarget", src_start, src_end, text,
        dest_start_char=dst_start, dest_end_char=dst_end,
    )


def action_set_selection_before(token_start: int, text: str) -> dict:
    """Set cursor to start of target range."""
    return run_action("setSelectionBefore", token_start, token_start, text)


def action_set_selection_after(token_end: int, text: str) -> dict:
    """Set cursor to end of target range."""
    return run_action("setSelectionAfter", token_end, token_end, text)
