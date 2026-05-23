"""Flash helpers and flash-state getter actions for the prose overlay.

Extracted from prose_overlay.py. Uses the same module-level globals as
prose_overlay.py — state migration to instance.* happens in wave 2.

Contains:
  _clear_flash              — clear flash state and redraw
  _flash_tokens             — highlight token indices briefly, then callback
  _action_color             — map Cursorless action name to 6-char hex color
  prose_overlay_get_flash_indices — getter action
  prose_overlay_get_flash_color   — getter action
"""

from talon import Module, cron

mod = Module()

# ---------------------------------------------------------------------------
# Module-level globals (mirrors prose_overlay.py — wave 2 migrates to instance)
# ---------------------------------------------------------------------------
_flash_state: dict = {}   # keys: "indices" (list[int]), "color" (str, 6-char hex)
_flash_callback = None    # pending callable to run after flash delay
_canvas = None            # set by prose_overlay.py after canvas is created


def _clear_flash():
    """Clear flash state and trigger a canvas redraw."""
    global _flash_state
    _flash_state = {}
    if _canvas is not None:
        _canvas.refresh()


def _flash_tokens(indices: list, color: str, callback, duration_ms: int = 150):
    """Highlight the given token indices briefly, then call callback.

    Sets _flash_state so draw_overlay renders the colored highlight rect,
    freezes the canvas for an immediate redraw, then schedules a cron job
    to clear the flash and execute the actual action callback.
    """
    global _flash_state, _flash_callback
    _flash_state = {"indices": indices, "color": color}
    _flash_callback = callback
    if _canvas is not None:
        _canvas.refresh()  # redraw with highlight

    def _after_flash():
        global _flash_state, _flash_callback
        _flash_state = {}
        cb = _flash_callback
        _flash_callback = None
        if _canvas is not None:
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
# Getter actions (used by canvas draw callback)
# ---------------------------------------------------------------------------

@mod.action_class
class Actions:
    def prose_overlay_get_flash_indices() -> list:
        """Return the list of token indices currently being flashed (empty if none)."""
        return list(_flash_state.get("indices", []))

    def prose_overlay_get_flash_color() -> str:
        """Return the current flash color hex (6 chars), or '' if no flash."""
        return _flash_state.get("color", "")
