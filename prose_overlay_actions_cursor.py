"""Cursor management actions for the prose overlay.

Owns: _blink_tick, _set_cursor, _prose_overlay_set_cursor,
      _prose_overlay_clear_cursor, and all cursor-related action methods.

Never imports prose_overlay.py.
"""

from talon import Module, actions, cron, ui

from .prose_overlay_instance import instance
from .prose_overlay_cursorless_resolve import _state as _resolve_state
from .prose_overlay_actions_core import _recompute_hats, _hat_to_index
from .prose_overlay_actions_flash import _flash_tokens, _action_color

mod = Module()


def _screen_height() -> float:
    """Host-environment adapter for the pure-Python viewport.

    Viewport math is environment-agnostic (INTERNAL layer); "what's the
    screen size?" is a Talon question, so it lives here in the UI layer.
    """
    return ui.main_screen().rect.height


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
    from .prose_overlay_debug import emit_if_changed
    emit_if_changed("set_cursor")


def _prose_overlay_set_cursor(gap_index: int, change_mode: bool = False):
    """Internal helper: set cursor position and start blink job."""
    _set_cursor(gap_index, change_mode)
    instance.blink_on = True
    if instance.blink_job is None:
        instance.blink_job = cron.interval("500ms", _blink_tick)


def _prose_overlay_clear_cursor():
    """Internal helper: clear cursor and cancel blink job."""
    _set_cursor(None)
    instance.blink_on = False
    if instance.blink_job is not None:
        cron.cancel(instance.blink_job)
        instance.blink_job = None


def _blink_tick():
    """Cron callback: toggle blink state and refresh canvas."""
    instance.blink_on = not instance.blink_on
    instance.canvas.refresh()


def _viewport_cursor_row():
    """Return (viewport, cursor_row) or (viewport, None) if not resolvable."""
    viewport = instance.viewport
    if viewport is None or not viewport._last_rows or instance.cursor is None:
        return viewport, None
    return viewport, viewport._find_cursor_row(viewport._last_rows, instance.cursor)


_STRATEGY_TO_ALIGN = {"start": "top", "center": "center", "end": "bottom"}


def _auto_scroll_to_cursor(strategy: str = "nearest") -> None:
    """Snap the scroll viewport to keep the cursor row visible.

    Strategy in {'nearest', 'start', 'end', 'center'} (CodeMirror semantics):
      - 'nearest': minimal scroll to make cursor row visible (default).
      - 'start':   align cursor row to viewport top.
      - 'end':     align cursor row to viewport bottom.
      - 'center':  center cursor row in viewport.
    """
    viewport = instance.viewport
    if viewport is None:
        return
    cached_rows = viewport._last_rows
    if not cached_rows:
        return
    if strategy == "nearest":
        max_vis = viewport.get_max_visible_rows(_screen_height())
        new_offset = viewport.compute_scroll_for_cursor(
            cached_rows, instance.cursor, viewport.get_scroll_offset(), max_vis
        )
        viewport.set_scroll_offset(new_offset)
        return
    align_where = _STRATEGY_TO_ALIGN.get(strategy)
    if align_where is None:
        return
    row = viewport._find_cursor_row(cached_rows, instance.cursor)
    if row is None:
        return
    viewport.align(row, align_where, _screen_height())


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
        _auto_scroll_to_cursor(strategy="start")
        instance.canvas.refresh()

    def prose_overlay_cursor_end():
        """Move cursor to after the last token (post file)."""
        _prose_overlay_set_cursor(len(instance.buffer))
        _auto_scroll_to_cursor(strategy="end")
        instance.canvas.refresh()

    def prose_overlay_change_hat(letter: str, color: str = "gray"):
        """Delete the token at the given hat and enter change mode at that position."""
        index = _hat_to_index(letter, color)
        if index < 0:
            return
        def _do():
            instance.buffer.delete_token(index)
            _recompute_hats()
            _prose_overlay_set_cursor(index, change_mode=True)
            _auto_scroll_to_cursor()
            instance.canvas.refresh()
        _flash_tokens([index], _action_color("clearAndSetSelection"), _do)

    def prose_overlay_change_head_hat(letter: str, color: str = "gray"):
        """Delete start through hat, enter change mode at position 0 (change head)."""
        index = _hat_to_index(letter, color)
        if index < 0:
            return
        flash_indices = list(range(0, index + 1))
        def _do():
            instance.buffer.delete_head(index)
            _recompute_hats()
            _prose_overlay_set_cursor(0, change_mode=True)
            instance.canvas.refresh()
        _flash_tokens(flash_indices, _action_color("clearAndSetSelection"), _do)

    def prose_overlay_change_tail_hat(letter: str, color: str = "gray"):
        """Delete hat through end, enter change mode at hat position (change tail)."""
        index = _hat_to_index(letter, color)
        if index < 0:
            return
        flash_indices = list(range(index, len(instance.buffer.get_tokens())))
        def _do():
            instance.buffer.delete_through(index)
            _recompute_hats()
            _prose_overlay_set_cursor(index, change_mode=True)
            instance.canvas.refresh()
        _flash_tokens(flash_indices, _action_color("clearAndSetSelection"), _do)

    def prose_overlay_align_top():
        """Align the cursor row to the top of the viewport (Helix-style)."""
        viewport, row = _viewport_cursor_row()
        if row is None:
            return
        viewport.align(row, "top", _screen_height())
        instance.canvas.refresh()

    def prose_overlay_align_center():
        """Align the cursor row to the center of the viewport (Helix-style)."""
        viewport, row = _viewport_cursor_row()
        if row is None:
            return
        viewport.align(row, "center", _screen_height())
        instance.canvas.refresh()

    def prose_overlay_align_bottom():
        """Align the cursor row to the bottom of the viewport (Helix-style)."""
        viewport, row = _viewport_cursor_row()
        if row is None:
            return
        viewport.align(row, "bottom", _screen_height())
        instance.canvas.refresh()

    def prose_overlay_recenter():
        """Cycle viewport anchor center -> top -> bottom on repeats (Emacs-style)."""
        viewport, row = _viewport_cursor_row()
        if row is None:
            return
        viewport.recenter(row, _screen_height())
        instance.canvas.refresh()
