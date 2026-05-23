"""Prose Overlay -- main module with actions, settings, and orchestration.

Coordinates the buffer, canvas, and window focus tracking to provide
a voice-first dictation buffer with hat-targeted editing.
"""

import json
import os
import subprocess
from typing import Any, Optional

from talon import Context, Module, actions, cron, settings, ui

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

# History constants
_HISTORY_MAX = 50

# Auto-dictation toggle state — persisted to disk so it survives Talon restarts.
_PREFS_PATH = os.path.join(os.path.dirname(__file__), "prose_overlay_prefs.json")


def _set_cursor(gap: Optional[int], change_mode: bool = False) -> None:
    """Set cursor and sync to resolve state atomically.

    This is the ONLY place that assigns to instance.cursor.
    Also manages change_mode and blink state.
    """
    instance.cursor = gap
    instance.change_mode = change_mode
    _resolve_state.cursor = gap


def _prose_overlay_set_cursor(gap_index: int, change_mode: bool = False):
    """Internal helper: set cursor position and start blink job."""
    _set_cursor(gap_index, change_mode)
    instance.blink_on = True
    if instance.blink_job is None:
        instance.blink_job = cron.interval("500ms", _blink_tick)


def _prose_overlay_clear_cursor():
    """Internal helper: clear cursor and cancel blink job."""
    _set_cursor(None)
    instance.blink_on = True
    if instance.blink_job is not None:
        cron.cancel(instance.blink_job)
        instance.blink_job = None


def _blink_tick():
    """Cron callback: toggle blink state and refresh canvas."""
    instance.blink_on = not instance.blink_on
    instance.canvas.refresh()


def _auto_scroll_to_cursor():
    """Snap the scroll viewport to keep the cursor row visible.

    Reads the cached row layout from the last draw and adjusts _scroll_offset
    in the draw module so the next frame shows the cursor.
    """
    cached_rows = _draw_mod_ref._last_rows
    if not cached_rows:
        return
    max_vis = _draw_mod_ref.get_max_visible_rows()
    new_offset = _draw_mod_ref.compute_scroll_for_cursor(
        cached_rows, instance.cursor, _draw_mod_ref._scroll_offset, max_vis
    )
    _draw_mod_ref.set_scroll_offset(new_offset)


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
# Preferences persistence
# ---------------------------------------------------------------------------

def _save_prefs() -> None:
    """Write current preferences to disk."""
    try:
        with open(_PREFS_PATH, "w") as f:
            json.dump({
                "auto_dictation": instance.auto_dictation,
                "anchor_position": _draw_mod_ref._anchor_position,
            }, f)
    except Exception as e:
        print(f"prose_overlay: could not save prefs: {e}")


def _load_prefs() -> None:
    """Load persisted preferences and apply them (called once at module init)."""
    try:
        with open(_PREFS_PATH) as f:
            prefs = json.load(f)
        instance.auto_dictation = bool(prefs.get("auto_dictation", False))
        _sync_tags()  # canvas is not showing at init, so tags derive cleanly
        print(f"prose_overlay: auto-dictation restored to {'ON' if instance.auto_dictation else 'OFF'}")
        pos = prefs.get("anchor_position", "top")
        _draw_mod_ref.set_anchor_position(pos)
        print(f"prose_overlay: anchor position restored to '{pos}'")
    except FileNotFoundError:
        pass  # first run — no prefs file yet
    except Exception as e:
        print(f"prose_overlay: could not load prefs: {e}")


def _on_draw_history(c, overlay):
    rect = _draw_mod_ref.draw_history_panel(c, overlay, instance.history, instance.history_page)
    if rect:
        overlay.set_panel_rect(rect)


def _on_history_overlay_hide():
    """Called by DismissibleOverlay when dismissed via click-outside or escape."""
    actions.user.prose_overlay_hide_history()


instance.history_overlay = DismissibleOverlay(
    on_draw=_on_draw_history,
    on_hide=_on_history_overlay_hide,
    close_hint_text='"overlay dismiss"',
    close_hint_size=12,
    close_hint_color="888899cc",
    blocks_mouse=False,
)

_ctx_history = Context()
instance.ctx_history = _ctx_history

# ---------------------------------------------------------------------------
# Canvas setup
# ---------------------------------------------------------------------------

instance.canvas = OverlayCanvas(instance.buffer)

# Wire canvas into flash module — flash needs canvas ref for refresh calls.
# (flash module reads from instance.canvas directly)


def _on_win_focus(win):
    """Track active window — updates target label while overlay is open.
    Ignored when a recall window has been explicitly set as target.
    """
    if not instance.canvas.is_showing:
        return
    if instance.target_recall_name is not None:
        return  # explicit recall target — don't override
    try:
        instance.target_window_title = win.title or ""
    except Exception:
        pass
    instance.canvas.refresh()


ui.register("win_focus", _on_win_focus)

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
# Actions
# ---------------------------------------------------------------------------
@mod.action_class
class Actions:
    def prose_overlay_show():
        """Show the prose dictation overlay. Inserts into whatever window is active at confirm time."""
        if not settings.get("user.prose_overlay_enabled"):
            return

        # Record window title and capture anchor rect for window-scoped layout.
        try:
            win = ui.active_window()
            instance.target_window_title = win.title or ""
            _draw_mod_ref.set_anchor_rect(win.rect)
        except Exception:
            instance.target_window_title = ""
            _draw_mod_ref.set_anchor_rect(None)

        instance.buffer.clear()
        instance.target_recall_name = None
        _draw_mod_ref.set_scroll_offset(0)
        _recompute_hats()
        instance.canvas.show()
        _sync_tags()  # canvas.is_showing is now True
        # Auto-enable dictation so <user.raw_prose> routes to the buffer.
        # prose_overlay_dictation.talon requires mode: dictation to fire.
        actions.mode.enable("dictation")

    def prose_overlay_hide():
        """Hide the prose overlay and clear the buffer."""
        _prose_overlay_clear_cursor()
        instance.flash_state = {}
        instance.flash_callback = None
        _draw_mod_ref.set_scroll_offset(0)
        instance.canvas.hide()
        instance.buffer.clear()
        _sync_tags()  # canvas.is_showing is now False
        instance.target_window_title = ""
        instance.target_recall_name = None
        instance.help_visible = False
        instance.help_page = 0
        # Return to command mode — paired with the enable in prose_overlay_show.
        actions.mode.enable("command")
        # In auto mode, keep dictation active so the next phrase routes through
        # the dictation_insert shim and re-opens the overlay automatically.
        # Without this, the hide would drop dictation and the next phrase would
        # land in command mode where the shim never fires.
        if not instance.auto_dictation:
            actions.mode.disable("dictation")

    def prose_overlay_toggle_auto_dictation():
        """Toggle auto-show prose overlay on any dictation phrase."""
        instance.auto_dictation = not instance.auto_dictation
        _sync_tags()  # derives correct tag state from canvas + instance.auto_dictation
        _save_prefs()
        print(f"prose_overlay: auto-dictation {'ON' if instance.auto_dictation else 'OFF'}")

    def prose_overlay_add_text(text: str):
        """Add dictated text to the overlay buffer and refresh display.

        If the cursor is active, inserts at the cursor gap position and
        advances the cursor past the inserted tokens. Otherwise appends.
        """
        if instance.cursor is not None:
            words = text.strip().split()
            instance.buffer.insert_at(instance.cursor, text)
            _set_cursor(instance.cursor + len(words), False)
            _recompute_hats()
            _auto_scroll_to_cursor()
            instance.canvas.refresh()
        else:
            instance.buffer.add_text(text)
            _recompute_hats()
            _auto_scroll_to_cursor()
            instance.canvas.refresh()

    def prose_overlay_confirm():
        """Insert buffer text into the target window (or active window), then hide."""
        if not instance.canvas.is_showing:
            return  # overlay not open — ignore stale ender
        _prose_overlay_clear_cursor()
        instance.flash_state = {}
        instance.flash_callback = None
        text = instance.buffer.get_text()
        if not text:
            actions.user.prose_overlay_hide()
            return

        # Push to history before hide clears the buffer
        instance.history.insert(0, text)
        if len(instance.history) > _HISTORY_MAX:
            instance.history.pop()

        if instance.target_recall_name:
            actions.user.recall_window(instance.target_recall_name)
            actions.sleep("80ms")

        actions.insert(text)
        actions.key("enter")
        actions.user.prose_overlay_hide()

    def prose_overlay_speak():
        """Speak the current buffer contents via the speak TTS tool."""
        text = instance.buffer.get_text()
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
        _draw_mod_ref.HINT_FONT_SIZE = min(_draw_mod_ref.HINT_FONT_SIZE + 2, 28)
        instance.canvas.refresh()

    def prose_overlay_help_smaller():
        """Decrease the help footer font size by 2pt and refresh."""
        _draw_mod_ref.HINT_FONT_SIZE = max(_draw_mod_ref.HINT_FONT_SIZE - 2, 8)
        instance.canvas.refresh()

    def prose_overlay_is_active() -> bool:
        """Check if the prose overlay is currently showing."""
        return instance.canvas.is_showing

    def prose_overlay_help_toggle():
        """Toggle the help panel visibility."""
        instance.help_visible = not instance.help_visible
        instance.canvas.refresh()

    def prose_overlay_help_next():
        """Advance to next help page (wraps)."""
        from .prose_overlay_draw import HELP_PAGES
        instance.help_page = (instance.help_page + 1) % len(HELP_PAGES)
        instance.canvas.refresh()

    def prose_overlay_help_back():
        """Go to previous help page (wraps)."""
        from .prose_overlay_draw import HELP_PAGES
        instance.help_page = (instance.help_page - 1) % len(HELP_PAGES)
        instance.canvas.refresh()

    def prose_overlay_help_visible() -> bool:
        """Return whether the help panel is currently visible."""
        return instance.help_visible

    def prose_overlay_help_page() -> int:
        """Return the current help page index."""
        return instance.help_page

    # ---------------------------------------------------------------------------
    # History panel
    # ---------------------------------------------------------------------------
    def prose_overlay_toggle_history():
        """Toggle the prose history panel."""
        if instance.history_overlay.is_showing:
            actions.user.prose_overlay_hide_history()
        else:
            instance.history_page = 0
            instance.history_overlay.show()
            instance.ctx_history.tags = ["user.prose_history_active"]

    def prose_overlay_hide_history():
        """Hide the prose history panel."""
        instance.history_overlay.hide()
        instance.ctx_history.tags = []

    def prose_overlay_history_next():
        """Advance to the next history page."""
        total_pages = max(1, (len(instance.history) + _draw_mod_ref.HISTORY_PAGE_SIZE - 1) // _draw_mod_ref.HISTORY_PAGE_SIZE)
        instance.history_page = min(instance.history_page + 1, total_pages - 1)
        instance.history_overlay.freeze()

    def prose_overlay_history_back():
        """Go to the previous history page."""
        instance.history_page = max(0, instance.history_page - 1)
        instance.history_overlay.freeze()

    def prose_overlay_history_pick(n: int):
        """Load the nth history entry (1-based) into the overlay buffer."""
        if 1 <= n <= len(instance.history):
            entry = instance.history[n - 1]
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
            _draw_mod_ref.set_anchor_rect(win.rect)
            if instance.canvas.is_showing:
                instance.canvas.refresh()
        except Exception:
            pass

    def prose_overlay_clear_anchor():
        """Remove the window anchor — overlay reverts to full-screen width."""
        _draw_mod_ref.set_anchor_rect(None)
        if instance.canvas.is_showing:
            instance.canvas.refresh()

    def prose_overlay_set_anchor_position(position: str):
        """Set the vertical attachment point: 'top' or 'bottom'. Persisted to prefs."""
        _draw_mod_ref.set_anchor_position(position)
        _save_prefs()
        if instance.canvas.is_showing:
            instance.canvas.refresh()

    def prose_overlay_change_hat(letter: str, color: str = "gray"):
        """Delete the token at the given hat and enter change mode at that position."""
        index = _hat_to_index(letter, color)
        if index < 0:
            return
        instance.buffer.delete_token(index)
        _recompute_hats()
        _prose_overlay_set_cursor(index, change_mode=True)
        _auto_scroll_to_cursor()
        instance.canvas.refresh()

    def prose_overlay_set_cursor_before_hat(letter: str, color: str = "gray"):
        """Set the cursor before the token at the given hat."""
        index = _hat_to_index(letter, color)
        if index < 0:
            return
        _prose_overlay_set_cursor(index, change_mode=False)
        _auto_scroll_to_cursor()
        instance.canvas.refresh()

    def prose_overlay_set_cursor_after_hat(letter: str, color: str = "gray"):
        """Set the cursor after the token at the given hat."""
        index = _hat_to_index(letter, color)
        if index < 0:
            return
        _prose_overlay_set_cursor(index + 1, change_mode=False)
        _auto_scroll_to_cursor()
        instance.canvas.refresh()

    def prose_overlay_get_cursor() -> int:
        """Return the current cursor gap index, or -1 if no cursor."""
        return instance.cursor if instance.cursor is not None else -1

    def prose_overlay_get_change_mode() -> bool:
        """Return whether the cursor is in change (replace) mode."""
        return instance.change_mode

    def prose_overlay_get_blink_on() -> bool:
        """Return the current blink state for cursor rendering."""
        return instance.blink_on

    # ---------------------------------------------------------------------------
    # Cursor navigation — pre/post file
    # ---------------------------------------------------------------------------
    def prose_overlay_cursor_start():
        """Move cursor to before the first token (pre file)."""
        _prose_overlay_set_cursor(0)
        _auto_scroll_to_cursor()
        instance.canvas.refresh()

    def prose_overlay_cursor_end():
        """Move cursor to after the last token (post file)."""
        _prose_overlay_set_cursor(len(instance.buffer))
        _auto_scroll_to_cursor()
        instance.canvas.refresh()

    # ---------------------------------------------------------------------------
    # Head/tail modifiers
    # ---------------------------------------------------------------------------
    def prose_overlay_change_head_hat(letter: str, color: str = "gray"):
        """Delete start through hat, enter change mode at position 0 (change head)."""
        index = _hat_to_index(letter, color)
        if index >= 0:
            instance.buffer.delete_head(index)
            _recompute_hats()
            _prose_overlay_set_cursor(0, change_mode=True)
            instance.canvas.refresh()

    def prose_overlay_change_tail_hat(letter: str, color: str = "gray"):
        """Delete hat through end, enter change mode at hat position (change tail)."""
        index = _hat_to_index(letter, color)
        if index >= 0:
            instance.buffer.delete_through(index)
            _recompute_hats()
            _prose_overlay_set_cursor(index, change_mode=True)
            instance.canvas.refresh()

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
    # Undo
    # ---------------------------------------------------------------------------

    def prose_overlay_undo():
        """Undo the last prose overlay edit."""
        if instance.buffer.undo():
            _draw_mod_ref.set_scroll_offset(0)
            _recompute_hats()
            instance.canvas.refresh()

    def prose_overlay_get_selection() -> list:
        """Return [start, end] selection indices, or [] if no selection."""
        sel = instance.buffer.get_selection()
        if sel is None:
            return []
        return list(sel)
