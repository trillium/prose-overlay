"""Flash helpers and flash-state getter actions for the prose overlay.

Migrated to use instance.* in wave 2. Never imports prose_overlay.py.

Contains:
  _clear_flash              — clear flash state and redraw
  _flash_tokens             — highlight token indices briefly, then callback
  _action_color             — map Cursorless action name to 6-char hex color
  prose_overlay_get_flash_indices — getter action
  prose_overlay_get_flash_color   — getter action
"""

from talon import Module, cron

from ..internal.instance import instance

mod = Module()


def _clear_flash():
    """Clear flash state + pending callback and trigger a canvas redraw."""
    instance.flash_state = {}
    instance.flash_callback = None
    if instance.canvas is not None:
        instance.canvas.refresh()


def _flash_tokens(indices: list, color: str, callback, duration_ms: int = 150):
    """Highlight the given token indices briefly, then call callback.

    Sets instance.flash_state so draw_overlay renders the colored highlight rect,
    freezes the canvas for an immediate redraw, then schedules a cron job
    to clear the flash and execute the actual action callback.
    """
    instance.flash_state = {"indices": indices, "color": color}
    instance.flash_callback = callback
    if instance.canvas is not None:
        instance.canvas.refresh()  # redraw with highlight

    def _after_flash():
        instance.flash_state = {}
        cb = instance.flash_callback
        instance.flash_callback = None
        if instance.canvas is not None:
            instance.canvas.refresh()  # redraw without highlight
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
        "applyFormatter":       "a855f7",
    }
    return _ACTION_COLORS.get(action_name, "089ad3")


# ---------------------------------------------------------------------------
# Getter actions (used by canvas draw callback)
# ---------------------------------------------------------------------------

@mod.action_class
class Actions:
    def prose_overlay_get_flash_indices() -> list:
        """Return the list of token indices currently being flashed (empty if none)."""
        return list(instance.flash_state.get("indices", []))

    def prose_overlay_get_flash_color() -> str:
        """Return the current flash color hex (6 chars), or '' if no flash."""
        return instance.flash_state.get("color", "")
