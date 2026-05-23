"""Prose Overlay -- main module with actions, settings, and orchestration.

Coordinates the buffer, canvas, and window focus tracking to provide
a voice-first dictation buffer with hat-targeted editing.
"""

import os
from typing import Any, Optional

from talon import Context, Module, actions, settings, ui

from .prose_overlay_canvas import OverlayCanvas
from . import prose_overlay_draw as _draw_mod_ref
from .prose_overlay_state import ProseBuffer
from . import prose_overlay_actions_js as _js
from ...utils.overlay_kit import DismissibleOverlay
from .prose_overlay_cursorless_resolve import (
    _resolve_target_to_token_range,
    _cursorless_symbol_to_token_index,
    _SUPPORTED_SIMPLE_ACTIONS,
    _state as _resolve_state,
)
from .prose_overlay_instance import instance
from .prose_overlay_actions_core import _recompute_hats, _sync_tags, _hat_to_index
from .prose_overlay_actions_flash import _flash_tokens, _action_color

mod = Module()

mod.setting(
    "prose_overlay_enabled",
    type=bool,
    default=True,
    desc="Enable the prose dictation overlay for buffered dictation with hat editing",
)

mod.setting(
    "prose_overlay_help_font_size",
    type=int,
    default=12,
    desc="Font size for the help footer in the prose overlay",
)

mod.tag("prose_overlay_active", desc="Prose dictation overlay is currently visible")
mod.tag("prose_overlay_auto", desc="Auto-show prose overlay on any dictation (toggled by user)")
mod.tag("prose_history_active", desc="Prose history panel is currently visible")

mod.setting(
    "prose_overlay_auto_dictation",
    type=bool,
    default=False,
    desc="When true, any phrase in dictation mode automatically opens the prose overlay",
)

mod.setting(
    "prose_overlay_window_scoped",
    type=bool,
    default=True,
    desc="When true, the overlay panel is sized and positioned to match the target window",
)


@mod.capture(rule="red | blue | green | pink | yellow | purple | plum | gold | black | white")
def prose_hat_color(m) -> str:
    """Spoken color prefix for a hat, e.g. 'blue air', 'red bat'.
    Normalizes aliases: plum -> purple, gold -> yellow.
    """
    spoken = str(m).strip()
    return {"plum": "purple", "gold": "yellow"}.get(spoken, spoken)

# ---------------------------------------------------------------------------
# Initialize instance state
# ---------------------------------------------------------------------------
instance.buffer = ProseBuffer()
_resolve_state.buffer = instance.buffer  # share the ProseBuffer instance with the resolve module
instance.hat_assignments = {}
instance.hat_to_token = {}
instance.draw_mod = _draw_mod_ref

_ctx = Context()
_ctx_auto = Context()  # owns the prose_overlay_auto tag

# Expose contexts on instance so actions_core._sync_tags can access them.
instance.ctx = _ctx
instance.ctx_auto = _ctx_auto

# Action-level shim: active when prose_overlay_auto tag is set.
# Overrides user.dictation_insert so every dictation path (community enders,
# punctuation enders, window-switch rules, etc.) routes to the overlay
# instead of inserting directly into the focused window.
_ctx_shim = Context()
_ctx_shim.matches = r"""
tag: user.prose_overlay_auto
"""

_ctx_history = Context()
instance.ctx_history = _ctx_history

# ---------------------------------------------------------------------------
# Canvas setup
# ---------------------------------------------------------------------------

instance.canvas = OverlayCanvas(instance.buffer)

# Wire canvas into flash module — flash needs canvas ref for refresh calls.
# (flash module reads from instance.canvas directly)

# ---------------------------------------------------------------------------
# History overlay setup
# ---------------------------------------------------------------------------
# Import helpers from history module now that instance.canvas and
# instance.draw_mod are set.
from .prose_overlay_actions_history import _on_draw_history, _on_history_overlay_hide  # noqa: E402

instance.history_overlay = DismissibleOverlay(
    on_draw=_on_draw_history,
    on_hide=_on_history_overlay_hide,
    close_hint_text='"overlay dismiss"',
    close_hint_size=12,
    close_hint_color="888899cc",
    blocks_mouse=False,
)

# ---------------------------------------------------------------------------
# Load persisted preferences
# ---------------------------------------------------------------------------
from .prose_overlay_actions_visibility import _load_prefs  # noqa: E402
_load_prefs()


# ---------------------------------------------------------------------------
# Shim: route all dictation_insert / insert_formatted calls to the overlay
# ---------------------------------------------------------------------------

# Active when overlay is showing — intercepts insert_formatted while overlay is open.
_ctx_overlay_active = Context()
_ctx_overlay_active.matches = r"""
tag: user.prose_overlay_active
"""

@_ctx_overlay_active.action_class("user")
class _OverlayActiveActions:
    def insert_formatted(phrase, formatters: str):
        """Route formatter output (e.g. 'say <prose>') to the overlay buffer."""
        text = actions.user.formatted_text(phrase, formatters)
        actions.user.prose_overlay_add_text(text)


@_ctx_shim.action_class("user")
class _ShimActions:
    def dictation_insert(text: str, auto_cap: bool = True):
        """Shim: route dictated text to the prose overlay instead of inserting directly.

        Intercepts every path that ends in dictation_insert — community enders,
        punctuation enders, window-switch rules, etc. — so the overlay is the
        single destination for all spoken prose when auto mode is active.
        """
        if instance.canvas.is_showing:
            actions.user.prose_overlay_add_text(text)
        else:
            actions.user.prose_overlay_show()
            actions.user.prose_overlay_add_text(text)

    def insert_formatted(phrase, formatters: str):
        """Route formatter output (e.g. 'say <prose>') to the overlay buffer.

        insert_formatted calls actions.insert() directly, bypassing dictation_insert,
        so it needs its own shim. Uses user.formatted_text to get the formatted string
        without re-importing format_phrase.
        """
        text = actions.user.formatted_text(phrase, formatters)
        if instance.canvas.is_showing:
            actions.user.prose_overlay_add_text(text)
        else:
            actions.user.prose_overlay_show()
            actions.user.prose_overlay_add_text(text)


# ---------------------------------------------------------------------------
# Actions — cursorless / JS shim path (not moved to sub-files)
# ---------------------------------------------------------------------------

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
    from .prose_overlay_actions_cursor import (
        _prose_overlay_set_cursor,
        _prose_overlay_clear_cursor,
        _auto_scroll_to_cursor,
    )

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


@mod.action_class
class Actions:
    # ---------------------------------------------------------------------------
    # Cursorless-grammar actions (JS shim path)
    # ---------------------------------------------------------------------------

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

        token_range = _resolve_target_to_token_range(cursorless_target)
        if token_range is None:
            print(f"prose_overlay: unresolvable target for action '{action_name}'")
            return

        first_idx, last_idx = token_range
        tokens = instance.buffer.get_tokens()
        text = " ".join(tokens)
        src_start, _ = _token_char_range(first_idx, tokens)
        _, src_end = _token_char_range(last_idx, tokens)

        # Cursor position for context (anchor == active == collapsed cursor).
        cursor_char = 0
        if instance.cursor is not None:
            if instance.cursor == 0:
                cursor_char = 0
            elif instance.cursor >= len(tokens):
                cursor_char = len(text)
            else:
                _, tok_end = _token_char_range(instance.cursor - 1, tokens)
                cursor_char = tok_end + 1  # one past the space

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
            # Set selection tracking for selection-type actions.
            if action_name in ("setSelection", "clearAndSetSelection"):
                instance.buffer.set_selection(first_idx, last_idx)
            _recompute_hats()
            instance.canvas.refresh()

        _flash_tokens(range_indices, _action_color(action_name), _execute)

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

        cursor_char = 0
        if instance.cursor is not None:
            if instance.cursor == 0:
                cursor_char = 0
            elif instance.cursor >= len(tokens):
                cursor_char = len(text)
            else:
                _, tok_end = _token_char_range(instance.cursor - 1, tokens)
                cursor_char = tok_end + 1

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

        token_range = _resolve_target_to_token_range(cursorless_target)
        if token_range is None:
            print(f"prose_overlay: unresolvable target for action '{action_name}'")
            return

        first_idx, last_idx = token_range
        tokens = instance.buffer.get_tokens()
        text = " ".join(tokens)
        src_start, _ = _token_char_range(first_idx, tokens)
        _, src_end = _token_char_range(last_idx, tokens)

        # Destination = collapsed cursor: both anchor and active at cursor char.
        if instance.cursor == 0:
            cursor_char = 0
        elif instance.cursor >= len(tokens):
            cursor_char = len(text)
        else:
            _, tok_end = _token_char_range(instance.cursor - 1, tokens)
            cursor_char = tok_end + 1  # one past the trailing space of previous token

        def _execute():
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

        _flash_tokens(list(range(first_idx, last_idx + 1)), _action_color(action_name), _execute)


# ---------------------------------------------------------------------------
# Import action sub-modules so Talon registers their action classes
# ---------------------------------------------------------------------------
from . import prose_overlay_actions_cursor      # noqa: F401, E402
from . import prose_overlay_actions_layout      # noqa: F401, E402
from . import prose_overlay_actions_history     # noqa: F401, E402
from . import prose_overlay_actions_help        # noqa: F401, E402
from . import prose_overlay_actions_visibility  # noqa: F401, E402
