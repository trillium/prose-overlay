"""Cursor management actions for the prose overlay.

Owns: _blink_tick, _set_cursor, _prose_overlay_set_cursor,
      _prose_overlay_clear_cursor, and all cursor-related action methods.

Never imports prose_overlay.py.
"""

from talon import Module, actions, cron

from .prose_overlay_instance import instance
from .prose_overlay_cursorless_resolve import _state as _resolve_state
from .prose_overlay_actions_core import _recompute_hats, _hat_to_index

mod = Module()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _set_cursor(gap, change_mode: bool = False) -> None:
    """Set cursor and sync to resolve state atomically.

    This is the ONLY place that assigns to instance.cursor.
    Also manages change_mode state.
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

    NOTE: this is also called by prose_overlay_actions_layout and
    prose_overlay.py action implementations that need scroll-after-cursor.
    Kept here because it is tightly coupled to cursor state.
    """
    draw_mod = instance.draw_mod
    if draw_mod is None:
        return
    cached_rows = draw_mod._last_rows
    if not cached_rows:
        return
    max_vis = draw_mod.get_max_visible_rows()
    new_offset = draw_mod.compute_scroll_for_cursor(
        cached_rows, instance.cursor, draw_mod._scroll_offset, max_vis
    )
    draw_mod.set_scroll_offset(new_offset)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@mod.action_class
class Actions:
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
