"""Layout and window-anchor actions for the prose overlay.

Owns: _on_win_focus, prose_overlay_set_anchor, prose_overlay_clear_anchor,
      prose_overlay_set_anchor_position.

Registers the win_focus event here.

Never imports prose_overlay.py.
"""

from talon import Module, actions, ui

from ..internal.instance import instance

mod = Module()

_anchor_win = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

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


def _on_win_move(win):
    if not instance.canvas.is_showing:
        return
    if _anchor_win is None:
        return
    try:
        if win.id != _anchor_win.id:
            return
        instance.viewport.set_anchor_rect(win.rect)
        instance.canvas.refresh()
    except Exception:
        pass


ui.register("win_focus", _on_win_focus)
ui.register("win_move", _on_win_move)


def _save_prefs_from_layout():
    """Delegate to visibility module's _save_prefs without circular import."""
    from .actions_visibility import _save_prefs
    _save_prefs()


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@mod.action_class
class Actions:
    def prose_overlay_set_anchor():
        """Anchor the overlay to the currently active window's rect.

        Updates the layout anchor immediately if the overlay is showing.
        """
        global _anchor_win
        viewport = instance.viewport
        try:
            win = ui.active_window()
            _anchor_win = win
            viewport.set_anchor_rect(win.rect)
            if instance.canvas.is_showing:
                instance.canvas.refresh()
        except Exception:
            pass

    def prose_overlay_clear_anchor():
        """Remove the window anchor — overlay reverts to full-screen width."""
        global _anchor_win
        _anchor_win = None
        instance.viewport.set_anchor_rect(None)
        if instance.canvas.is_showing:
            instance.canvas.refresh()

    def prose_overlay_set_anchor_position(position: str):
        """Set the vertical attachment point: 'top' or 'bottom'. Persisted to prefs."""
        viewport = instance.viewport
        try:
            win = ui.active_window()
            viewport.set_anchor_rect(win.rect)
        except Exception:
            pass
        viewport.set_anchor_position(position)
        _save_prefs_from_layout()
        if instance.canvas.is_showing:
            instance.canvas.refresh()
