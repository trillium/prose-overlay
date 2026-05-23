"""Prose Overlay -- main module with actions, settings, and orchestration.

Coordinates the buffer, canvas, and window focus tracking to provide
a voice-first dictation buffer with hat-targeted editing.
"""

import json
import os
import subprocess
from typing import Any

from talon import Context, Module, actions, cron, settings, ui

from .prose_overlay_canvas import OverlayCanvas
from . import prose_overlay_draw as _draw_mod
from .prose_overlay_state import ProseBuffer
from .prose_overlay_hats_js import compute_hat_assignments
from . import prose_overlay_actions_js as _js
from ...utils.overlay_kit import DismissibleOverlay

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
# Global state
# ---------------------------------------------------------------------------
_buffer = ProseBuffer()
_hat_assignments: dict[int, tuple[int, str, str]] = {}
_hat_to_token: dict[tuple[str, str], int] = {}  # reverse map: (letter, color) -> token_index
_canvas: OverlayCanvas  # initialized below after _recompute_hats is defined
_ctx = Context()
_ctx_auto = Context()  # owns the prose_overlay_auto tag

# Action-level shim: active when prose_overlay_auto tag is set.
# Overrides user.dictation_insert so every dictation path (community enders,
# punctuation enders, window-switch rules, etc.) routes to the overlay
# instead of inserting directly into the focused window.
_ctx_shim = Context()
_ctx_shim.matches = r"""
tag: user.prose_overlay_auto
"""
_target_window_title = ""   # fallback display label (active window at open time)
_target_recall_name: str | None = None  # recall window name if retargeted

# Help panel state — read by canvas draw callback via getters
_help_visible: bool = False
_help_page: int = 0

# History state
_HISTORY_MAX = 50
_history: list[str] = []
_history_page: int = 0
_ctx_history = Context()

# Auto-dictation toggle state — persisted to disk so it survives Talon restarts.
_PREFS_PATH = os.path.join(os.path.dirname(__file__), "prose_overlay_prefs.json")
_auto_dictation: bool = False

# Cursor state
_cursor: int | None = None   # gap index: 0=before all tokens, N=after all tokens, None=no cursor
_change_mode: bool = False   # True = awaiting replacement text after "change <hat>"
_blink_on: bool = True       # current blink state, toggled by cron job
_blink_job = None            # cron job handle for cursor blink

# Flash state — set before executing an action, cleared by cron after 150ms
_flash_state: dict = {}  # keys: "indices" (list[int]), "color" (str, 6-char hex)
_flash_callback = None   # pending callable to run after flash delay


def _recompute_hats():
    """Recompute hat assignments from the current buffer state.

    Updates both the forward map (token_index -> assignment) and the
    reverse map ((letter, color) -> token_index) used for spoken hat lookup.
    Pushes the assignments into the canvas for rendering.
    """
    global _hat_assignments, _hat_to_token
    tokens = _buffer.get_tokens()
    # When no cursor is set, default proximity to end of buffer (where writing happens).
    cursor_for_hats = _cursor if _cursor is not None else len(tokens)
    _hat_assignments = compute_hat_assignments(tokens, old_assignments=_hat_assignments, cursor_pos=cursor_for_hats)
    _hat_to_token = {(letter, color): idx for idx, (_, letter, color) in _hat_assignments.items()}
    _canvas.set_hat_assignments(_hat_assignments)


_canvas = OverlayCanvas(_buffer)


def _on_draw_history(c, overlay):
    rect = _draw_mod.draw_history_panel(c, overlay, _history, _history_page)
    if rect:
        overlay.set_panel_rect(rect)


def _on_history_overlay_hide():
    """Called by DismissibleOverlay when dismissed via click-outside or escape."""
    actions.user.prose_overlay_hide_history()


_history_overlay = DismissibleOverlay(
    on_draw=_on_draw_history,
    on_hide=_on_history_overlay_hide,
    close_hint_text='"overlay dismiss"',
    close_hint_size=12,
    close_hint_color="888899cc",
    blocks_mouse=False,
)


def _on_win_focus(win):
    """Track active window — updates target label while overlay is open.
    Ignored when a recall window has been explicitly set as target.
    """
    global _target_window_title
    if not _canvas.is_showing:
        return
    if _target_recall_name is not None:
        return  # explicit recall target — don't override
    try:
        _target_window_title = win.title or ""
    except Exception:
        pass
    _canvas.refresh()


ui.register("win_focus", _on_win_focus)


def _sync_tags():
    """Sync context tags to match current canvas + auto-dictation state.

    Ground truth is _canvas.is_showing — tags follow canvas state, never the
    reverse. Calling this after any state change keeps tags consistent.
    """
    if _canvas.is_showing:
        _ctx.tags = ["user.prose_overlay_active"]
        _ctx_auto.tags = []  # auto tag off while overlay is open
    else:
        _ctx.tags = []
        _ctx_auto.tags = ["user.prose_overlay_auto"] if _auto_dictation else []


def _hat_to_index(letter: str, color: str = "gray") -> int:
    """Convert a (letter, color) hat reference to a token index.

    Uses the reverse assignment map so the spoken hat name matches the dot
    that's actually visible. Color defaults to "gray" — the no-prefix case.
    Returns -1 if the (letter, color) pair is not currently assigned.
    """
    return _hat_to_token.get((letter.lower(), color), -1)


def _blink_tick():
    """Cron callback: toggle blink state and refresh canvas."""
    global _blink_on
    _blink_on = not _blink_on
    _canvas.refresh()


def _auto_scroll_to_cursor():
    """Snap the scroll viewport to keep the cursor row visible.

    Reads the cached row layout from the last draw and adjusts _scroll_offset
    in the draw module so the next frame shows the cursor.
    """
    cached_rows = _draw_mod._last_rows
    if not cached_rows:
        return
    max_vis = _draw_mod.get_max_visible_rows()
    new_offset = _draw_mod.compute_scroll_for_cursor(
        cached_rows, _cursor, _draw_mod._scroll_offset, max_vis
    )
    _draw_mod.set_scroll_offset(new_offset)


def _prose_overlay_set_cursor(gap_index: int, change_mode: bool = False):
    """Internal helper: set cursor position and start blink job."""
    global _cursor, _change_mode, _blink_on, _blink_job
    _cursor = gap_index
    _change_mode = change_mode
    _blink_on = True
    if _blink_job is None:
        _blink_job = cron.interval("500ms", _blink_tick)


def _prose_overlay_clear_cursor():
    """Internal helper: clear cursor and cancel blink job."""
    global _cursor, _change_mode, _blink_on, _blink_job
    _cursor = None
    _change_mode = False
    _blink_on = True
    if _blink_job is not None:
        cron.cancel(_blink_job)
        _blink_job = None


def _clear_flash():
    """Clear flash state and trigger a canvas redraw."""
    global _flash_state
    _flash_state = {}
    _canvas.refresh()


def _flash_tokens(indices: list[int], color: str, callback, duration_ms: int = 150):
    """Highlight the given token indices briefly, then call callback.

    Sets _flash_state so draw_overlay renders the colored highlight rect,
    freezes the canvas for an immediate redraw, then schedules a cron job
    to clear the flash and execute the actual action callback.
    """
    global _flash_state, _flash_callback
    _flash_state = {"indices": indices, "color": color}
    _flash_callback = callback
    _canvas.refresh()  # redraw with highlight

    def _after_flash():
        global _flash_state, _flash_callback
        _flash_state = {}
        cb = _flash_callback
        _flash_callback = None
        _canvas.refresh()  # redraw without highlight
        if cb is not None:
            cb()

    cron.after(f"{duration_ms}ms", _after_flash)


def _action_color(action_name: str) -> str:
    """Return the 6-char hex flash color for a Cursorless action name."""
    _ACTION_COLORS = {
        "remove":               "e02d28",
        "setSelection":         "089ad3",
        "clearAndSetSelection": "e5a02c",
        "replaceWithTarget":    "36b33f",
        "moveToTarget":         "36b33f",
        "setSelectionBefore":   "ffffff",
        "setSelectionAfter":    "ffffff",
    }
    return _ACTION_COLORS.get(action_name, "089ad3")


# ---------------------------------------------------------------------------
# Cursorless-style action support helpers
# ---------------------------------------------------------------------------

# Actions the JS shim can handle. All others (scroll, fold, etc.) are VS Code
# specific and not meaningful inside the prose overlay.
_SUPPORTED_SIMPLE_ACTIONS = frozenset({
    "remove",
    "setSelection",
    "clearAndSetSelection",
    "setSelectionBefore",
    "setSelectionAfter",
})

# Cursorless uses "default" for the no-color hat; the prose overlay uses "gray".
_CURSORLESS_TO_PROSE_COLOR = {"default": "gray"}


def _cursorless_symbol_to_token_index(decorated_symbol: dict) -> int:
    """Resolve a cursorless_decorated_symbol dict to a token index.

    Cursorless uses "default" for the no-color case; we store "gray" in the
    hat reverse map. Returns -1 if the symbol is not found.
    """
    character: str = decorated_symbol.get("character", "")
    symbol_color: str = decorated_symbol.get("symbolColor", "default")
    prose_color = _CURSORLESS_TO_PROSE_COLOR.get(symbol_color, symbol_color)
    return _hat_to_token.get((character.lower(), prose_color), -1)


# Scope type values (from spoken_forms.json modifier_scope_types.csv) that
# map to the entire prose buffer, which is a flat single-line document.
_WHOLE_BUFFER_SCOPE_TYPES = frozenset({
    "document",    # spoken "file"
    "line",        # spoken "line"  — prose is single-line, so line == buffer
    "paragraph",   # spoken "block" — block-level scope maps to buffer
    "fullLine",    # spoken "full line"
})

# Scope type values that target the token nearest the cursor.
_WORD_SCOPE_TYPES = frozenset({
    "token",       # spoken "token"
    "word",        # spoken "sub"   — Cursorless "word" is a sub-word token
    "identifier",  # spoken "identifier"
    "character",   # spoken "char"
})


def _resolve_primitive_to_token_range(target) -> "tuple[int, int] | None":
    """Resolve a PrimitiveTarget to (start_token_idx, end_token_idx) inclusive.

    Two-phase:
    1. Resolve the mark to a base token index (decoratedSymbol → hat map,
       no mark → cursor position).
    2. Apply modifiers to the base index to compute the final range:
       - extendThroughStartOf ("head"): (0, base_idx)
       - extendThroughEndOf  ("tail"): (base_idx, len-1)
       - containingScope/everyScope: whole-buffer or cursor-token range
       - no modifier: (base_idx, base_idx)

    Returns None if the target cannot be resolved, logging the reason.
    """
    tokens = _buffer.get_tokens()
    if not tokens:
        print("prose_overlay: buffer is empty — cannot resolve target")
        return None

    mark = target.mark  # dict or None
    modifiers = target.modifiers or []  # list of dicts

    # --- Step 1: resolve mark to base token index ------------------------------
    base_idx: "int | None" = None

    if mark is not None:
        mark_type = mark.get("type")
        if mark_type == "decoratedSymbol":
            idx = _cursorless_symbol_to_token_index(mark)
            if idx < 0:
                print(
                    f"prose_overlay: decorated symbol not found in hat map: "
                    f"{mark.get('character')!r} / {mark.get('symbolColor')!r}"
                )
                return None
            base_idx = idx
        elif mark_type == "cursor":
            # "this" in Cursorless — currentSelection maps to cursor position.
            # If no editing cursor is set, fall back to the last token (where
            # dictation is currently appending).
            if _cursor is not None:
                base_idx = min(max(_cursor, 0), len(tokens) - 1)
            else:
                base_idx = len(tokens) - 1
    # If mark is None (or unrecognized), base_idx stays None; modifiers may supply the range.

    # --- Step 2: apply modifiers -----------------------------------------------
    for mod in modifiers:
        mod_type = mod.get("type")

        # "chuck head <hat>" / "chuck head this" — from start through base token
        if mod_type == "extendThroughStartOf":
            if base_idx is None:
                if _cursor is None:
                    print("prose_overlay: extendThroughStartOf requires an active cursor")
                    return None
                base_idx = min(max(_cursor, 0), len(tokens) - 1)
            return (0, base_idx)

        # "chuck tail <hat>" / "chuck tail this" — from base token through end
        if mod_type == "extendThroughEndOf":
            if base_idx is None:
                if _cursor is None:
                    print("prose_overlay: extendThroughEndOf requires an active cursor")
                    return None
                base_idx = min(max(_cursor, 0), len(tokens) - 1)
            return (base_idx, len(tokens) - 1)

        # everyScope — "each <scope>" always means the entire buffer in a
        # single-line prose context. Ignore scope type; return full range.
        if mod_type == "everyScope":
            return (0, len(tokens) - 1)

        # containingScope / preferredScope — scope at the cursor position
        if mod_type in ("containingScope", "preferredScope"):
            scope_type = mod.get("scopeType", {}).get("type", "")
            if scope_type in _WHOLE_BUFFER_SCOPE_TYPES:
                return (0, len(tokens) - 1)
            if scope_type in _WORD_SCOPE_TYPES:
                if _cursor is None:
                    print(
                        f"prose_overlay: scope '{scope_type}' requires an active cursor"
                    )
                    return None
                tok_idx = min(max(_cursor, 0), len(tokens) - 1)
                return (tok_idx, tok_idx)
            print(f"prose_overlay: unrecognized scope type '{scope_type}'")
            return None

    # --- Step 3: no modifiers — return base index as single-token range --------
    if base_idx is not None:
        return (base_idx, base_idx)

    print(
        f"prose_overlay: cannot resolve PrimitiveTarget with mark={mark!r} "
        f"and modifiers={modifiers!r}"
    )
    return None


def _resolve_target_to_token_range(target) -> "tuple[int, int] | None":
    """Resolve any CursorlessTarget to (start_token_idx, end_token_idx) inclusive.

    Dispatches by target type:
    - PrimitiveTarget → _resolve_primitive_to_token_range
    - RangeTarget     → resolve anchor + active, return spanning range
    - ListTarget      → not supported (log and return None)
    - ImplicitTarget  → not supported (log and return None)

    Returns None if the target cannot be resolved.
    """
    target_type = target.type  # class attribute, not instance dict

    if target_type == "primitive":
        return _resolve_primitive_to_token_range(target)

    if target_type == "range":
        # anchor may be ImplicitTarget (type == "implicit") when the user says
        # e.g. "chuck past bat" with no explicit anchor.
        anchor = target.anchor
        active = target.active

        if anchor.type == "implicit":
            print(
                "prose_overlay: RangeTarget with implicit anchor is not supported"
            )
            return None

        anchor_range = _resolve_primitive_to_token_range(anchor)
        active_range = _resolve_primitive_to_token_range(active)

        if anchor_range is None or active_range is None:
            return None

        first = min(anchor_range[0], active_range[0])
        last = max(anchor_range[1], active_range[1])
        return (first, last)

    if target_type == "list":
        print(
            "prose_overlay: ListTarget (multi-target 'and' expressions) are not "
            "supported — operate on targets individually"
        )
        return None

    if target_type == "implicit":
        # "this" in Cursorless — resolve to the token at the cursor position.
        if _cursor is None:
            print("prose_overlay: ImplicitTarget requires an active cursor (use pre/post <hat> first)")
            return None
        tok_idx = min(_cursor, len(tokens) - 1)
        if tok_idx < 0:
            tok_idx = 0
        return (tok_idx, tok_idx)

    print(f"prose_overlay: unknown target type '{target_type}'")
    return None


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
    """Apply the edit plan returned by the JS shim to _buffer and set the cursor.

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
    global _cursor

    if "error" in plan:
        print(f"prose_overlay: JS action error: {plan['error']}")
        return

    edits = plan.get("edits", [])
    new_selections = plan.get("newSelections", [])

    # Snapshot before any mutation so the edit is undoable.
    _buffer.snapshot()

    # Work on a mutable flat string (single-line buffer).
    text = _buffer.get_text()

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
    _buffer.set_tokens_raw(new_tokens)

    # Update cursor from newSelections (active char offset → gap index).
    if new_selections:
        active_char = new_selections[0].get("active", {}).get("character", None)
        if active_char is not None:
            # Convert character offset to gap index: count how many tokens
            # end before or at active_char.
            tokens = _buffer.get_tokens()
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
# Preferences persistence
# ---------------------------------------------------------------------------

def _save_prefs() -> None:
    """Write current preferences to disk."""
    try:
        with open(_PREFS_PATH, "w") as f:
            json.dump({
                "auto_dictation": _auto_dictation,
                "anchor_position": _draw_mod._anchor_position,
            }, f)
    except Exception as e:
        print(f"prose_overlay: could not save prefs: {e}")


def _load_prefs() -> None:
    """Load persisted preferences and apply them (called once at module init)."""
    global _auto_dictation
    try:
        with open(_PREFS_PATH) as f:
            prefs = json.load(f)
        _auto_dictation = bool(prefs.get("auto_dictation", False))
        _sync_tags()  # canvas is not showing at init, so tags derive cleanly
        print(f"prose_overlay: auto-dictation restored to {'ON' if _auto_dictation else 'OFF'}")
        pos = prefs.get("anchor_position", "top")
        _draw_mod.set_anchor_position(pos)
        print(f"prose_overlay: anchor position restored to '{pos}'")
    except FileNotFoundError:
        pass  # first run — no prefs file yet
    except Exception as e:
        print(f"prose_overlay: could not load prefs: {e}")


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
        if _canvas.is_showing:
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
        if _canvas.is_showing:
            actions.user.prose_overlay_add_text(text)
        else:
            actions.user.prose_overlay_show()
            actions.user.prose_overlay_add_text(text)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
@mod.action_class
class Actions:
    def prose_overlay_show():
        """Show the prose dictation overlay. Inserts into whatever window is active at confirm time."""
        global _target_window_title, _target_recall_name
        if not settings.get("user.prose_overlay_enabled"):
            return

        # Record window title and capture anchor rect for window-scoped layout.
        try:
            win = ui.active_window()
            _target_window_title = win.title or ""
            _draw_mod.set_anchor_rect(win.rect)
        except Exception:
            _target_window_title = ""
            _draw_mod.set_anchor_rect(None)

        _buffer.clear()
        _target_recall_name = None
        _draw_mod.set_scroll_offset(0)
        _recompute_hats()
        _canvas.show()
        _sync_tags()  # canvas.is_showing is now True
        # Auto-enable dictation so <user.raw_prose> routes to the buffer.
        # prose_overlay_dictation.talon requires mode: dictation to fire.
        actions.mode.enable("dictation")

    def prose_overlay_hide():
        """Hide the prose overlay and clear the buffer."""
        global _target_window_title, _target_recall_name, _help_visible, _help_page, _flash_state, _flash_callback
        _prose_overlay_clear_cursor()
        _flash_state = {}
        _flash_callback = None
        _draw_mod.set_scroll_offset(0)
        _canvas.hide()
        _buffer.clear()
        _sync_tags()  # canvas.is_showing is now False
        _target_window_title = ""
        _target_recall_name = None
        _help_visible = False
        _help_page = 0
        # Return to command mode — paired with the enable in prose_overlay_show.
        actions.mode.enable("command")
        # In auto mode, keep dictation active so the next phrase routes through
        # the dictation_insert shim and re-opens the overlay automatically.
        # Without this, the hide would drop dictation and the next phrase would
        # land in command mode where the shim never fires.
        if not _auto_dictation:
            actions.mode.disable("dictation")

    def prose_overlay_toggle_auto_dictation():
        """Toggle auto-show prose overlay on any dictation phrase."""
        global _auto_dictation
        _auto_dictation = not _auto_dictation
        _sync_tags()  # derives correct tag state from canvas + _auto_dictation
        _save_prefs()
        print(f"prose_overlay: auto-dictation {'ON' if _auto_dictation else 'OFF'}")

    def prose_overlay_add_text(text: str):
        """Add dictated text to the overlay buffer and refresh display.

        If the cursor is active, inserts at the cursor gap position and
        advances the cursor past the inserted tokens. Otherwise appends.
        """
        global _cursor, _change_mode
        if _cursor is not None:
            words = text.strip().split()
            _buffer.insert_at(_cursor, text)
            _cursor += len(words)
            _change_mode = False
            _recompute_hats()
            _auto_scroll_to_cursor()
            _canvas.refresh()
        else:
            _buffer.add_text(text)
            _recompute_hats()
            _auto_scroll_to_cursor()
            _canvas.refresh()

    def prose_overlay_delete_hat(letter: str, color: str = "gray"):
        """Delete the token at the given hat (letter + optional color)."""
        index = _hat_to_index(letter, color)
        if index >= 0:
            def _do():
                _buffer.delete_token(index)
                _recompute_hats()
                _canvas.refresh()
            _flash_tokens([index], _action_color("remove"), _do)

    def prose_overlay_delete_past_hat(letter: str, color: str = "gray"):
        """Delete from the hat through the end of the buffer (chuck past <hat>)."""
        index = _hat_to_index(letter, color)
        if index >= 0:
            flash_indices = list(range(index, len(_buffer.get_tokens())))
            def _do():
                _buffer.delete_through(index)
                _recompute_hats()
                _canvas.refresh()
            _flash_tokens(flash_indices, _action_color("remove"), _do)

    def prose_overlay_retarget(name: str):
        """Retarget the overlay to a recall named window.
        On confirm, that window will be focused before text is inserted.
        """
        global _target_recall_name, _target_window_title
        _target_recall_name = name
        _target_window_title = name
        _canvas.refresh()

    def prose_overlay_retarget_focus(name: str):
        """Retarget AND immediately focus the named recall window.
        Use when the window name leads a phrase: the window is frontmost
        so confirm can insert directly without an extra focus step.
        """
        global _target_recall_name, _target_window_title
        _target_recall_name = name
        _target_window_title = name
        _canvas.refresh()
        actions.user.recall_window(name)

    def prose_overlay_get_target_label() -> str:
        """Return the display label for the current target window."""
        if _target_recall_name:
            return f"→ {_target_recall_name}"
        if _target_window_title:
            # Truncate long titles
            t = _target_window_title
            return f"→ {t[:40]}…" if len(t) > 40 else f"→ {t}"
        return ""

    def prose_overlay_confirm():
        """Insert buffer text into the target window (or active window), then hide."""
        global _flash_state, _flash_callback
        if not _canvas.is_showing:
            return  # overlay not open — ignore stale ender
        _prose_overlay_clear_cursor()
        _flash_state = {}
        _flash_callback = None
        text = _buffer.get_text()
        if not text:
            actions.user.prose_overlay_hide()
            return

        # Push to history before hide clears the buffer
        _history.insert(0, text)
        if len(_history) > _HISTORY_MAX:
            _history.pop()

        if _target_recall_name:
            actions.user.recall_window(_target_recall_name)
            actions.sleep("80ms")

        actions.insert(text)
        actions.key("enter")
        actions.user.prose_overlay_hide()

    def prose_overlay_speak():
        """Speak the current buffer contents via the speak TTS tool."""
        text = _buffer.get_text()
        if not text:
            return
        _speak_env = __import__("os").environ.copy()
        _speak_env["PATH"] = ":".join([
            "/opt/homebrew/bin",
            "/opt/homebrew/sbin",
            "/Users/trilliumsmith/.local/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
            _speak_env.get("PATH", ""),
        ])
        subprocess.Popen(
            ["/Users/trilliumsmith/code/speak/bin/speak", "--caller", "prose-overlay", text],
            start_new_session=True,
            env=_speak_env,
        )

    def prose_overlay_help_bigger():
        """Increase the help footer font size by 2pt and refresh."""
        _draw_mod.HINT_FONT_SIZE = min(_draw_mod.HINT_FONT_SIZE + 2, 28)
        _canvas.refresh()

    def prose_overlay_help_smaller():
        """Decrease the help footer font size by 2pt and refresh."""
        _draw_mod.HINT_FONT_SIZE = max(_draw_mod.HINT_FONT_SIZE - 2, 8)
        _canvas.refresh()

    def prose_overlay_is_active() -> bool:
        """Check if the prose overlay is currently showing."""
        return _canvas.is_showing

    def prose_overlay_help_toggle():
        """Toggle the help panel visibility."""
        global _help_visible
        _help_visible = not _help_visible
        _canvas.refresh()

    def prose_overlay_help_next():
        """Advance to next help page (wraps)."""
        global _help_page
        from .prose_overlay_draw import HELP_PAGES
        _help_page = (_help_page + 1) % len(HELP_PAGES)
        _canvas.refresh()

    def prose_overlay_help_back():
        """Go to previous help page (wraps)."""
        global _help_page
        from .prose_overlay_draw import HELP_PAGES
        _help_page = (_help_page - 1) % len(HELP_PAGES)
        _canvas.refresh()

    def prose_overlay_help_visible() -> bool:
        """Return whether the help panel is currently visible."""
        return _help_visible

    def prose_overlay_help_page() -> int:
        """Return the current help page index."""
        return _help_page

    # ---------------------------------------------------------------------------
    # History panel
    # ---------------------------------------------------------------------------
    def prose_overlay_toggle_history():
        """Toggle the prose history panel."""
        global _history_page
        if _history_overlay.is_showing:
            actions.user.prose_overlay_hide_history()
        else:
            _history_page = 0
            _history_overlay.show()
            _ctx_history.tags = ["user.prose_history_active"]

    def prose_overlay_hide_history():
        """Hide the prose history panel."""
        _history_overlay.hide()
        _ctx_history.tags = []

    def prose_overlay_history_next():
        """Advance to the next history page."""
        global _history_page
        total_pages = max(1, (len(_history) + _draw_mod.HISTORY_PAGE_SIZE - 1) // _draw_mod.HISTORY_PAGE_SIZE)
        _history_page = min(_history_page + 1, total_pages - 1)
        _history_overlay.freeze()

    def prose_overlay_history_back():
        """Go to the previous history page."""
        global _history_page
        _history_page = max(0, _history_page - 1)
        _history_overlay.freeze()

    def prose_overlay_history_pick(n: int):
        """Load the nth history entry (1-based) into the overlay buffer."""
        if 1 <= n <= len(_history):
            entry = _history[n - 1]
            actions.user.prose_overlay_hide_history()
            actions.user.prose_overlay_show()
            actions.user.prose_overlay_add_text(entry)

    # ---------------------------------------------------------------------------
    # Window anchor
    # ---------------------------------------------------------------------------
    def prose_overlay_set_anchor():
        """Anchor the overlay to the currently active window's rect.

        Updates the layout anchor immediately if the overlay is showing.
        """
        try:
            win = ui.active_window()
            _draw_mod.set_anchor_rect(win.rect)
            if _canvas.is_showing:
                _canvas.refresh()
        except Exception:
            pass

    def prose_overlay_clear_anchor():
        """Remove the window anchor — overlay reverts to full-screen width."""
        _draw_mod.set_anchor_rect(None)
        if _canvas.is_showing:
            _canvas.refresh()

    def prose_overlay_set_anchor_position(position: str):
        """Set the vertical attachment point: 'top' or 'bottom'. Persisted to prefs."""
        _draw_mod.set_anchor_position(position)
        _save_prefs()
        if _canvas.is_showing:
            _canvas.refresh()

    def prose_overlay_change_hat(letter: str, color: str = "gray"):
        """Delete the token at the given hat and enter change mode at that position."""
        index = _hat_to_index(letter, color)
        if index < 0:
            return
        _buffer.delete_token(index)
        _recompute_hats()
        _prose_overlay_set_cursor(index, change_mode=True)
        _auto_scroll_to_cursor()
        _canvas.refresh()

    def prose_overlay_set_cursor_before_hat(letter: str, color: str = "gray"):
        """Set the cursor before the token at the given hat."""
        index = _hat_to_index(letter, color)
        if index < 0:
            return
        _prose_overlay_set_cursor(index, change_mode=False)
        _auto_scroll_to_cursor()
        _canvas.refresh()

    def prose_overlay_set_cursor_after_hat(letter: str, color: str = "gray"):
        """Set the cursor after the token at the given hat."""
        index = _hat_to_index(letter, color)
        if index < 0:
            return
        _prose_overlay_set_cursor(index + 1, change_mode=False)
        _auto_scroll_to_cursor()
        _canvas.refresh()

    def prose_overlay_get_cursor() -> int:
        """Return the current cursor gap index, or -1 if no cursor."""
        return _cursor if _cursor is not None else -1

    def prose_overlay_get_change_mode() -> bool:
        """Return whether the cursor is in change (replace) mode."""
        return _change_mode

    def prose_overlay_get_blink_on() -> bool:
        """Return the current blink state for cursor rendering."""
        return _blink_on

    # ---------------------------------------------------------------------------
    # Cursor navigation — pre/post file
    # ---------------------------------------------------------------------------
    def prose_overlay_cursor_start():
        """Move cursor to before the first token (pre file)."""
        _prose_overlay_set_cursor(0)
        _auto_scroll_to_cursor()
        _canvas.refresh()

    def prose_overlay_cursor_end():
        """Move cursor to after the last token (post file)."""
        _prose_overlay_set_cursor(len(_buffer))
        _auto_scroll_to_cursor()
        _canvas.refresh()

    # ---------------------------------------------------------------------------
    # Head/tail modifiers
    # ---------------------------------------------------------------------------
    def prose_overlay_delete_head_hat(letter: str, color: str = "gray"):
        """Delete from start of buffer through the token at the given hat (chuck head)."""
        index = _hat_to_index(letter, color)
        if index >= 0:
            flash_indices = list(range(0, index + 1))
            def _do():
                _buffer.delete_head(index)
                _recompute_hats()
                _canvas.refresh()
            _flash_tokens(flash_indices, _action_color("remove"), _do)

    def prose_overlay_delete_tail_hat(letter: str, color: str = "gray"):
        """Delete from the token at the given hat through end of buffer (chuck tail)."""
        index = _hat_to_index(letter, color)
        if index >= 0:
            flash_indices = list(range(index, len(_buffer.get_tokens())))
            def _do():
                _buffer.delete_through(index)
                _recompute_hats()
                _canvas.refresh()
            _flash_tokens(flash_indices, _action_color("remove"), _do)

    def prose_overlay_change_head_hat(letter: str, color: str = "gray"):
        """Delete start through hat, enter change mode at position 0 (change head)."""
        index = _hat_to_index(letter, color)
        if index >= 0:
            _buffer.delete_head(index)
            _recompute_hats()
            _prose_overlay_set_cursor(0, change_mode=True)
            _canvas.refresh()

    def prose_overlay_change_tail_hat(letter: str, color: str = "gray"):
        """Delete hat through end, enter change mode at hat position (change tail)."""
        index = _hat_to_index(letter, color)
        if index >= 0:
            _buffer.delete_through(index)
            _recompute_hats()
            _prose_overlay_set_cursor(index, change_mode=True)
            _canvas.refresh()

    # ---------------------------------------------------------------------------
    # Bring / move
    # ---------------------------------------------------------------------------
    def prose_overlay_bring_hat_to_hat(
        src_letter: str, src_color: str,
        dst_letter: str, dst_color: str,
    ):
        """Copy the token at src hat, replace the token at dst hat with it (bring)."""
        src = _hat_to_index(src_letter, src_color)
        dst = _hat_to_index(dst_letter, dst_color)
        if src < 0 or dst < 0 or src == dst:
            return
        tokens = _buffer.get_tokens()
        src_text = tokens[src]
        _buffer.replace_token(dst, src_text)
        _recompute_hats()
        _canvas.refresh()

    def prose_overlay_move_hat_to_hat(
        src_letter: str, src_color: str,
        dst_letter: str, dst_color: str,
    ):
        """Cut the token at src hat and replace the token at dst hat with it (move)."""
        src = _hat_to_index(src_letter, src_color)
        dst = _hat_to_index(dst_letter, dst_color)
        if src < 0 or dst < 0 or src == dst:
            return
        tokens = _buffer.get_tokens()
        src_text = tokens[src]
        # Replace dst first (index stable if src != dst), then delete src.
        _buffer.replace_token(dst, src_text)
        # After replace, src index unchanged — delete it.
        _buffer.delete_token(src)
        _recompute_hats()
        _canvas.refresh()

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
        tokens = _buffer.get_tokens()
        text = " ".join(tokens)
        src_start, _ = _token_char_range(first_idx, tokens)
        _, src_end = _token_char_range(last_idx, tokens)

        # Cursor position for context (anchor == active == collapsed cursor).
        cursor_char = 0
        if _cursor is not None:
            if _cursor == 0:
                cursor_char = 0
            elif _cursor >= len(tokens):
                cursor_char = len(text)
            else:
                _, tok_end = _token_char_range(_cursor - 1, tokens)
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
                _buffer.set_selection(first_idx, last_idx)
            _recompute_hats()
            _canvas.refresh()

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

        tokens = _buffer.get_tokens()
        text = " ".join(tokens)

        # Build the range: earlier token start → later token end.
        first_idx = min(anchor_idx, active_idx)
        last_idx = max(anchor_idx, active_idx)
        src_start, _ = _token_char_range(first_idx, tokens)
        _, src_end = _token_char_range(last_idx, tokens)

        cursor_char = 0
        if _cursor is not None:
            if _cursor == 0:
                cursor_char = 0
            elif _cursor >= len(tokens):
                cursor_char = len(text)
            else:
                _, tok_end = _token_char_range(_cursor - 1, tokens)
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
                _buffer.set_selection(first_idx, last_idx)
            _recompute_hats()
            _canvas.refresh()

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
        if _cursor is None:
            print("prose_overlay: bring/move requires an active cursor position")
            return

        token_range = _resolve_target_to_token_range(cursorless_target)
        if token_range is None:
            print(f"prose_overlay: unresolvable target for action '{action_name}'")
            return

        first_idx, last_idx = token_range
        tokens = _buffer.get_tokens()
        text = " ".join(tokens)
        src_start, _ = _token_char_range(first_idx, tokens)
        _, src_end = _token_char_range(last_idx, tokens)

        # Destination = collapsed cursor: both anchor and active at cursor char.
        if _cursor == 0:
            cursor_char = 0
        elif _cursor >= len(tokens):
            cursor_char = len(text)
        else:
            _, tok_end = _token_char_range(_cursor - 1, tokens)
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
            _canvas.refresh()

        _flash_tokens(list(range(first_idx, last_idx + 1)), _action_color(action_name), _execute)

    # ---------------------------------------------------------------------------
    # Undo
    # ---------------------------------------------------------------------------

    def prose_overlay_undo():
        """Undo the last prose overlay edit."""
        if _buffer.undo():
            _draw_mod.set_scroll_offset(0)
            _recompute_hats()
            _canvas.refresh()

    # ---------------------------------------------------------------------------
    # Flash / selection getters (used by canvas draw callback)
    # ---------------------------------------------------------------------------

    def prose_overlay_get_flash_indices() -> list:
        """Return the list of token indices currently being flashed (empty if none)."""
        return list(_flash_state.get("indices", []))

    def prose_overlay_get_flash_color() -> str:
        """Return the current flash color hex (6 chars), or '' if no flash."""
        return _flash_state.get("color", "")

    def prose_overlay_get_selection() -> list:
        """Return [start, end] selection indices, or [] if no selection."""
        sel = _buffer.get_selection()
        if sel is None:
            return []
        return list(sel)
