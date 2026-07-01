"""Help panel actions for the prose overlay.

Owns: prose_overlay_help_toggle, prose_overlay_help_visible,
      prose_overlay_help_page, prose_overlay_help_next, prose_overlay_help_back,
      prose_overlay_help_bigger, prose_overlay_help_smaller.

Never imports prose_overlay.py.
"""

from talon import Module

from ..internal.instance import instance

mod = Module()


@mod.action_class
class Actions:
    def prose_overlay_help_toggle():
        """Toggle the help panel visibility."""
        instance.state.help_visible = not instance.state.help_visible
        instance.runtime.canvas.refresh()

    def prose_overlay_help_visible() -> bool:
        """Return whether the help panel is currently visible."""
        return instance.state.help_visible

    def prose_overlay_help_page() -> int:
        """Return the current help page index."""
        return instance.state.help_page

    def prose_overlay_help_next():
        """Advance to next help page (wraps)."""
        from .help import HELP_PAGES
        instance.state.help_page = (instance.state.help_page + 1) % len(HELP_PAGES)
        instance.runtime.canvas.refresh()

    def prose_overlay_help_back():
        """Go to previous help page (wraps)."""
        from .help import HELP_PAGES
        instance.state.help_page = (instance.state.help_page - 1) % len(HELP_PAGES)
        instance.runtime.canvas.refresh()

    def prose_overlay_help_bigger():
        """Increase the help footer font size by 2pt and refresh."""
        draw_mod = instance.runtime.draw_mod
        draw_mod.HINT_FONT_SIZE = min(draw_mod.HINT_FONT_SIZE + 2, 28)
        instance.runtime.canvas.refresh()

    def prose_overlay_help_smaller():
        """Decrease the help footer font size by 2pt and refresh."""
        draw_mod = instance.runtime.draw_mod
        draw_mod.HINT_FONT_SIZE = max(draw_mod.HINT_FONT_SIZE - 2, 8)
        instance.runtime.canvas.refresh()
