"""Edit-plan execution and canvas-closed misfire diagnostics for the cursorless
actions. Split out of prose_overlay_actions_cursorless.py to keep that file
focused on the action method surface.
"""

from typing import Any

from talon import actions

from ..internal.instance import instance
from ..internal.state import EditKind
from ..ui.actions_cursor import (
    _prose_overlay_set_cursor,
    _prose_overlay_clear_cursor,
    _auto_scroll_to_cursor,
)


def _po_matcher_misfire(site: str, action_name: str, target: Any) -> None:
    """Capture registry/scope/grammar state when a PO cursorless rule fires
    despite the canvas being closed.

    prose_overlay_cursorless.talon's header requires `tag: user.prose_overlay_active`,
    set only when the canvas is showing (see `_sync_tags` in
    prose_overlay_actions_core.py). Reaching a PO action body with the canvas
    closed means Talon's matcher bound a rule whose context predicate is
    provably unsatisfied — a routing anomaly that would otherwise swallow the
    user's command instead of letting cursorless handle it. Tracked by #28.
    """
    label = "po_anomaly_canvas_closed"
    extras = {
        "site": site,
        "action_name": action_name,
        "target_type": type(target).__name__,
        "canvas_is_showing": False,
        "ctx_tags": list(getattr(instance.runtime.ctx, "tags", None) or []),
    }
    try:
        actions.user.registry_probe_dump(label, extras)
    except Exception as e:
        print(f"prose_overlay: registry_probe_dump failed ({e})")
    print(
        f"prose_overlay: matcher misfire — canvas closed but PO rule bound; "
        f"re-dispatching to cursorless. site={site} action={action_name} "
        f"label={label}"
    )


def _token_char_range(token_index: int, tokens: list[str]) -> tuple[int, int]:
    """Return (start_char, end_char) for the token at token_index in space-joined text.

    The document text is " ".join(tokens), so each token occupies its own
    character run separated by a single space. end_char is exclusive.
    """
    start = 0
    for i, tok in enumerate(tokens):
        if i == token_index:
            return start, start + len(tok)
        start += len(tok) + 1  # +1 for the space separator
    return 0, 0


def _cursor_to_char(cursor: int | None, tokens: list[str], text: str) -> int:
    """Convert a cursor gap index to a character offset in space-joined text.

    cursor=None or cursor=0 → 0 (before all tokens)
    cursor>=len(tokens) → len(text) (after all tokens)
    otherwise → one past the end of the token left of the gap
    """
    if cursor is None or cursor == 0:
        return 0
    if cursor >= len(tokens):
        return len(text)
    _, tok_end = _token_char_range(cursor - 1, tokens)
    return tok_end + 1  # one past the trailing space of the previous token


def _edit_start(edit: dict) -> int:
    if "range" in edit:
        return edit["range"]["start"]["character"]
    if "position" in edit:
        return edit["position"]["character"]
    return 0


def _apply_one_edit(text: str, edit: dict) -> str:
    etype = edit.get("type")
    if etype == "delete":
        r = edit["range"]
        return text[:r["start"]["character"]] + text[r["end"]["character"]:]
    if etype == "insert":
        pos = edit["position"]["character"]
        return text[:pos] + edit.get("text", "") + text[pos:]
    if etype == "replace":
        r = edit["range"]
        return text[:r["start"]["character"]] + edit.get("text", "") + text[r["end"]["character"]:]
    return text


def _selection_to_gap(active_char: int, tokens: list[str]) -> int:
    """Convert an active char offset to a gap index in the token list."""
    gap = 0
    pos = 0
    for i, tok in enumerate(tokens):
        tok_end = pos + len(tok)
        if active_char <= tok_end:
            return i if active_char <= pos else i + 1
        pos = tok_end + 1
        gap = i + 1
    return gap


def _apply_edit_plan(plan: dict) -> None:
    """Apply the JS-shim edit plan to instance.state.buffer and update the cursor.

    Edits are applied in reverse character-offset order so later edits don't
    shift earlier offsets. Supported edit types: delete, insert, replace.
    Buffer is rebuilt from the modified flat string; newSelections (active
    char offset) becomes the cursor gap position.
    """
    if "error" in plan:
        print(f"prose_overlay: JS action error: {plan['error']}")
        return

    edits = plan.get("edits", [])
    new_selections = plan.get("newSelections", [])

    # Bracket the whole edit-plan application as one undo step. set_tokens_raw
    # records the full-buffer delta into the open group automatically.
    instance.state.buffer.commit_start("cursorless_edit", EditKind.STRUCTURAL)
    try:
        text = instance.state.buffer.get_text()
        for edit in sorted(edits, key=_edit_start, reverse=True):
            text = _apply_one_edit(text, edit)
        new_tokens = text.strip().split() if text.strip() else []
        instance.state.buffer.set_tokens_raw(new_tokens)
    finally:
        instance.state.buffer.commit_end()

    if new_selections:
        active_char = new_selections[0].get("active", {}).get("character", None)
        if active_char is not None:
            gap = _selection_to_gap(active_char, instance.state.buffer.get_tokens())
            _prose_overlay_set_cursor(gap)
        else:
            _prose_overlay_clear_cursor()
    _auto_scroll_to_cursor()
