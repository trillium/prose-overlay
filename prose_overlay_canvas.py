"""Prose Overlay Canvas -- lifecycle management for the overlay canvas.

Handles canvas creation, drawing, refresh (freeze), and teardown.
Uses DismissibleOverlay from overlay_kit for shared lifecycle
(click-to-dismiss, escape key handling, X close hint).

Non-interactive by default: blocks_mouse = False so the user can still
click through to underlying windows.
"""

from talon import actions
from talon.skia.canvas import Canvas as SkiaCanvas

from ...utils.overlay_kit import DismissibleOverlay

from .prose_overlay_draw import draw_overlay, draw_help_panel
from .prose_overlay_state import ProseBuffer


class OverlayCanvas:
    """Manages the Talon canvas that renders the prose overlay.

    Wraps DismissibleOverlay for escape-key dismiss, click-outside dismiss,
    and the X close hint — all for free.
    """

    def __init__(self, buffer: ProseBuffer):
        self._buffer = buffer
        self._hat_assignments: dict[int, tuple[int, str]] | None = None
        self._overlay = DismissibleOverlay(
            on_draw=self._on_draw,
            auto_hide=None,
            close_hint_text='"overlay dismiss"',
            close_hint_size=12,
            close_hint_color="888899cc",
            on_hide=self._handle_hide,
            blocks_mouse=False,
        )

    def set_hat_assignments(self, assignments: dict[int, tuple[int, str]]):
        """Update the hat assignments to be used on the next draw."""
        self._hat_assignments = assignments

    @property
    def is_showing(self) -> bool:
        return self._overlay.is_showing

    def show(self):
        """Create and show the canvas overlay."""
        if self._overlay.is_showing:
            self.refresh()
            return
        self._overlay.show()

    def refresh(self):
        """Re-freeze the canvas to trigger a redraw with current buffer state."""
        self._overlay.freeze()

    def hide(self):
        """Tear down the canvas."""
        self._overlay.hide()

    def _handle_hide(self):
        """Called by DismissibleOverlay when dismissed (click-outside or escape).

        Delegates to prose_overlay_hide to clear the tag and buffer.
        """
        actions.user.prose_overlay_hide()

    def _on_draw(self, c: SkiaCanvas, overlay: DismissibleOverlay):
        """Draw callback: delegates to the draw module, reports panel rect(s).

        When the help panel is visible, both rects are reported via
        set_panel_rects so click-outside detection covers both panels.
        """
        # Fetch cursor state via actions to avoid circular imports
        cursor_raw = actions.user.prose_overlay_get_cursor()
        cursor = cursor_raw if cursor_raw >= 0 else None
        change_mode = actions.user.prose_overlay_get_change_mode()
        blink_on = actions.user.prose_overlay_get_blink_on()

        # Fetch flash state
        flash_indices_raw = actions.user.prose_overlay_get_flash_indices()
        flash_color_raw = actions.user.prose_overlay_get_flash_color()
        flash_indices = flash_indices_raw if flash_indices_raw else None
        flash_color = flash_color_raw if flash_color_raw else None

        # Fetch selection state
        sel_raw = actions.user.prose_overlay_get_selection()
        selection = (sel_raw[0], sel_raw[1]) if sel_raw else None

        target_label = actions.user.prose_overlay_get_target_label()

        panel_rect = draw_overlay(
            c, self._buffer.get_tokens(), overlay, self._hat_assignments,
            cursor=cursor, change_mode=change_mode, blink_on=blink_on,
            flash_indices=flash_indices, flash_color=flash_color,
            selection=selection, target_label=target_label,
        )
        if not panel_rect:
            return

        # Check help state via actions to avoid circular imports
        help_visible = actions.user.prose_overlay_help_visible()
        if help_visible:
            help_page = actions.user.prose_overlay_help_page()
            help_rect = draw_help_panel(c, panel_rect, help_page)
            if help_rect:
                overlay.set_panel_rects([panel_rect, help_rect])
                return

        overlay.set_panel_rect(panel_rect)
