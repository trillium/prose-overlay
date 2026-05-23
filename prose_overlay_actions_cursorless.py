"""Cursorless dispatch actions for the prose overlay.

Migrated from prose_overlay.py in wave 4.

Contains:
  _token_char_range       — compute (start_char, end_char) for a token index
  _apply_edit_plan        — apply JS shim edit plan to instance.buffer
  prose_overlay_run_action         — action method
  prose_overlay_run_action_range   — action method
  prose_overlay_bring_move         — action method

All state access uses instance.*. Never imports prose_overlay.py.
"""

from typing import Any

from talon import Module, actions

from .prose_overlay_instance import instance
from .prose_overlay_actions_core import _recompute_hats, _hat_to_index  # noqa: F401
from .prose_overlay_actions_flash import _flash_tokens, _action_color
from .prose_overlay_actions_cursor import (
    _prose_overlay_set_cursor,
    _prose_overlay_clear_cursor,
    _auto_scroll_to_cursor,
    _set_cursor,
)
from .prose_overlay_cursorless_resolve import (
    _resolve_target_to_token_range,
    _cursorless_symbol_to_token_index,
    _SUPPORTED_SIMPLE_ACTIONS,
    _WORD_SCOPE_TYPES,
    _WHOLE_BUFFER_SCOPE_TYPES,
)
from . import prose_overlay_actions_js as _js

mod = Module()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

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


def _token_char_range(token_index: int, tokens: list[str]) -> tuple[int, int]:
    """Return (start_char, end_char) for the token at token_index in space-joined text.

    The document text is " ".join(tokens), so each token occupies its own
    character run separated by a single space.  end_char is exclusive.
    """
    start = 0
    for i, tok in enumerate(tokens):
        if i == token_index:
            return start, start + len(tok)
        start += len(tok) + 1  # +1 for the space separator
    return 0, 0


def _apply_edit_plan(plan: dict) -> None:
    """Apply the edit plan returned by the JS shim to instance.buffer and set the cursor.

    Edits are applied in reverse character-offset order to prevent index shift
    errors when multiple edits touch the same buffer string.

    Supported edit types:
      delete  — remove characters in range from the flat string representation,
                then rebuild the token list from the result.
      insert  — insert text at position, then rebuild tokens.
      replace — delete range and insert text, then rebuild tokens.

    After all edits, the buffer is rebuilt from the modified flat string.
    newSelections is used to update the cursor gap position (line=0, char offset).
    """
    if "error" in plan:
        print(f"prose_overlay: JS action error: {plan['error']}")
        return

    edits = plan.get("edits", [])
    new_selections = plan.get("newSelections", [])

    # Snapshot before any mutation so the edit is undoable.
    instance.buffer.snapshot()

    # Work on a mutable flat string (single-line buffer).
    text = instance.buffer.get_text()

    # Sort edits in reverse start-char order so later edits don't shift
    # earlier offsets.  "insert" edits use a "position" key; all others
    # use a "range" key with a "start".
    def _edit_start(edit: dict) -> int:
        if "range" in edit:
            return edit["range"]["start"]["character"]
        if "position" in edit:
            return edit["position"]["character"]
        return 0

    sorted_edits = sorted(edits, key=_edit_start, reverse=True)

    for edit in sorted_edits:
        etype = edit.get("type")
        if etype == "delete":
            r = edit["range"]
            s = r["start"]["character"]
            e = r["end"]["character"]
            text = text[:s] + text[e:]
        elif etype == "insert":
            pos = edit["position"]["character"]
            inserted = edit.get("text", "")
            text = text[:pos] + inserted + text[pos:]
        elif etype == "replace":
            r = edit["range"]
            s = r["start"]["character"]
            e = r["end"]["character"]
            inserted = edit.get("text", "")
            text = text[:s] + inserted + text[e:]

    # Rebuild buffer from the modified flat string.
    # Use set_tokens_raw to avoid a second snapshot (we already snapshotted above)
    # and to avoid clearing _history via clear().
    new_tokens = text.strip().split() if text.strip() else []
    instance.buffer.set_tokens_raw(new_tokens)

    # Update cursor from newSelections (active char offset → gap index).
    if new_selections:
        active_char = new_selections[0].get("active", {}).get("character", None)
        if active_char is not None:
            # Convert character offset to gap index: count how many tokens
            # end before or at active_char.
            tokens = instance.buffer.get_tokens()
            gap = 0
            pos = 0
            for i, tok in enumerate(tokens):
                tok_end = pos + len(tok)
                if active_char <= tok_end:
                    # Cursor is within or at end of this token
                    gap = i if active_char <= pos else i + 1
                    break
                pos = tok_end + 1  # advance past the space
                gap = i + 1
            _prose_overlay_set_cursor(gap)
        else:
            _prose_overlay_clear_cursor()
    _auto_scroll_to_cursor()


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@mod.action_class
class Actions:
    def prose_overlay_run_action(action_name: str, cursorless_target: Any):
        """Run a prose overlay action via the JS shim for any CursorlessTarget.

        Resolves cursorless_target (PrimitiveTarget, RangeTarget, or ListTarget)
        to a (start_token_idx, end_token_idx) inclusive token range using
        _resolve_target_to_token_range, computes the corresponding character
        range in the flat buffer string, calls the JS shim to get an edit plan,
        applies the edits, and redraws.

        Flashes all tokens in the resolved range before executing. Tracks
        selection for setSelection and clearAndSetSelection actions.

        Supported action_names: remove, setSelection, clearAndSetSelection,
        setSelectionBefore, setSelectionAfter.
        """
        if action_name not in _SUPPORTED_SIMPLE_ACTIONS:
            print(f"prose_overlay: unsupported action '{action_name}' (VS Code-only?)")
            return

        token_ranges = _resolve_target_to_token_range(cursorless_target)
        if token_ranges is None:
            print(f"prose_overlay: unresolvable target for action '{action_name}'")
            return

        # Collect all token indices for flashing, then execute each range.
        all_indices: list[int] = []
        for first_idx, last_idx in token_ranges:
            all_indices.extend(range(first_idx, last_idx + 1))

        def _execute():
            # Apply action to each range in reverse order so earlier indices
            # stay valid after edits delete/modify later tokens.
            for first_idx, last_idx in sorted(token_ranges, reverse=True):
                tokens = instance.buffer.get_tokens()
                text = " ".join(tokens)
                src_start, _ = _token_char_range(first_idx, tokens)
                _, src_end = _token_char_range(last_idx, tokens)
                cursor_char = _cursor_to_char(instance.cursor, tokens, text)
                plan = _js.run_action(
                    action_name,
                    src_start,
                    src_end,
                    text,
                    cursor_anchor_char=cursor_char,
                    cursor_active_char=cursor_char,
                )
                _apply_edit_plan(plan)
                if action_name in ("setSelection", "clearAndSetSelection"):
                    instance.buffer.set_selection(first_idx, last_idx)
            _recompute_hats()
            instance.canvas.refresh()

        _flash_tokens(all_indices, _action_color(action_name), _execute)

    def prose_overlay_run_action_range(
        action_name: str, anchor: dict, active: dict
    ):
        """Run a range-target action (anchor past active) via the JS shim.

        Resolves both decorated symbols to token indices and builds a
        character range spanning from anchor token start to active token end.
        The anchor and active ordering follows Cursorless conventions: the
        range runs from whichever is earlier to whichever is later in the
        buffer (selection direction is not reversed here).

        Flashes all tokens in the range before executing.
        """
        if action_name not in _SUPPORTED_SIMPLE_ACTIONS:
            print(f"prose_overlay: unsupported action '{action_name}' (VS Code-only?)")
            return

        anchor_idx = _cursorless_symbol_to_token_index(anchor)
        active_idx = _cursorless_symbol_to_token_index(active)
        if anchor_idx < 0 or active_idx < 0:
            return

        tokens = instance.buffer.get_tokens()
        text = " ".join(tokens)

        # Build the range: earlier token start → later token end.
        first_idx = min(anchor_idx, active_idx)
        last_idx = max(anchor_idx, active_idx)
        src_start, _ = _token_char_range(first_idx, tokens)
        _, src_end = _token_char_range(last_idx, tokens)

        cursor_char = _cursor_to_char(instance.cursor, tokens, text)

        range_indices = list(range(first_idx, last_idx + 1))

        def _execute():
            plan = _js.run_action(
                action_name,
                src_start,
                src_end,
                text,
                cursor_anchor_char=cursor_char,
                cursor_active_char=cursor_char,
            )
            _apply_edit_plan(plan)
            if action_name in ("setSelection", "clearAndSetSelection"):
                instance.buffer.set_selection(first_idx, last_idx)
            _recompute_hats()
            instance.canvas.refresh()

        _flash_tokens(range_indices, _action_color(action_name), _execute)

    def prose_overlay_bring_move(action_name: str, cursorless_target: Any):
        """Bring or move: replaceWithTarget / moveToTarget to the cursor position.

        Source is resolved from cursorless_target (PrimitiveTarget, RangeTarget,
        or ListTarget) via _resolve_target_to_token_range. Destination is the
        current cursor position in the buffer (collapsed selection at the cursor
        gap).

        For 'move' (moveToTarget), the JS shim returns two edits: the
        destination insert and the source delete. _apply_edit_plan applies
        them in reverse character-offset order to avoid shift errors.

        Flashes the source token(s) before executing.
        If no cursor is active, the action is a no-op (nowhere to bring to).
        """
        if instance.cursor is None:
            print("prose_overlay: bring/move requires an active cursor position")
            return

        token_ranges = _resolve_target_to_token_range(cursorless_target)
        if token_ranges is None:
            print(f"prose_overlay: unresolvable target for action '{action_name}'")
            return

        all_indices: list[int] = []
        for first_idx, last_idx in token_ranges:
            all_indices.extend(range(first_idx, last_idx + 1))

        def _execute():
            for first_idx, last_idx in sorted(token_ranges, reverse=True):
                tokens = instance.buffer.get_tokens()
                text = " ".join(tokens)
                src_start, _ = _token_char_range(first_idx, tokens)
                _, src_end = _token_char_range(last_idx, tokens)
                cursor_char = _cursor_to_char(instance.cursor, tokens, text)
                plan = _js.run_action(
                    action_name,
                    src_start,
                    src_end,
                    text,
                    dest_start_char=cursor_char,
                    dest_end_char=cursor_char,
                    cursor_anchor_char=cursor_char,
                    cursor_active_char=cursor_char,
                )
                _apply_edit_plan(plan)
            _recompute_hats()
            instance.canvas.refresh()

        _flash_tokens(all_indices, _action_color(action_name), _execute)
