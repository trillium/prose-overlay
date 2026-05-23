"""Visibility actions and preferences persistence for the prose overlay.

Owns: _save_prefs, _load_prefs, prose_overlay_show, prose_overlay_hide,
      prose_overlay_toggle_auto_dictation, prose_overlay_is_active,
      prose_overlay_get_selection.

Never imports prose_overlay.py.
"""

import json
import os

from talon import Module, actions, settings

from .prose_overlay_instance import instance
from .prose_overlay_actions_core import _recompute_hats, _sync_tags

mod = Module()

_PREFS_PATH = os.path.join(os.path.dirname(__file__), "prose_overlay_prefs.json")


# ---------------------------------------------------------------------------
# Preferences persistence
# ---------------------------------------------------------------------------

def _save_prefs() -> None:
    """Write current preferences to disk."""
    draw_mod = instance.draw_mod
    try:
        with open(_PREFS_PATH, "w") as f:
            json.dump({
                "auto_dictation": instance.auto_dictation,
                "anchor_position": draw_mod._anchor_position,
            }, f)
    except Exception as e:
        print(f"prose_overlay: could not save prefs: {e}")


def _load_prefs() -> None:
    """Load persisted preferences and apply them (called once at module init)."""
    draw_mod = instance.draw_mod
    try:
        with open(_PREFS_PATH) as f:
            prefs = json.load(f)
        instance.auto_dictation = bool(prefs.get("auto_dictation", False))
        _sync_tags()  # canvas is not showing at init, so tags derive cleanly
        print(f"prose_overlay: auto-dictation restored to {'ON' if instance.auto_dictation else 'OFF'}")
        pos = prefs.get("anchor_position", "top")
        draw_mod.set_anchor_position(pos)
        print(f"prose_overlay: anchor position restored to '{pos}'")
    except FileNotFoundError:
        pass  # first run — no prefs file yet
    except Exception as e:
        print(f"prose_overlay: could not load prefs: {e}")


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@mod.action_class
class Actions:
    def prose_overlay_show():
        """Show the prose dictation overlay. Inserts into whatever window is active at confirm time."""
        from talon import ui
        if not settings.get("user.prose_overlay_enabled"):
            return

        draw_mod = instance.draw_mod
        # Record window title and capture anchor rect for window-scoped layout.
        try:
            win = ui.active_window()
            instance.target_window_title = win.title or ""
            draw_mod.set_anchor_rect(win.rect)
        except Exception:
            instance.target_window_title = ""
            draw_mod.set_anchor_rect(None)

        instance.buffer.clear()
        instance.target_recall_name = None
        draw_mod.set_scroll_offset(0)
        _recompute_hats()
        instance.canvas.show()
        _sync_tags()  # canvas.is_showing is now True
        # Auto-enable dictation so <user.raw_prose> routes to the buffer.
        # prose_overlay_dictation.talon requires mode: dictation to fire.
        actions.mode.enable("dictation")

    def prose_overlay_hide():
        """Hide the prose overlay and clear the buffer."""
        from .prose_overlay_actions_cursor import _prose_overlay_clear_cursor
        from .prose_overlay_actions_flash import _clear_flash
        draw_mod = instance.draw_mod
        _prose_overlay_clear_cursor()
        _clear_flash()
        draw_mod.set_scroll_offset(0)
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

    def prose_overlay_is_active() -> bool:
        """Check if the prose overlay is currently showing."""
        return instance.canvas.is_showing

    def prose_overlay_get_selection() -> list:
        """Return [start, end] selection indices, or [] if no selection."""
        sel = instance.buffer.get_selection()
        if sel is None:
            return []
        return list(sel)
