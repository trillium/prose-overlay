"""Target/retarget actions for the prose overlay: window targeting and label queries.

Stub file — action bodies will be implemented in wave 2.
Type signatures are copied exactly from prose_overlay.py.

Contains:
  prose_overlay_retarget            — retarget overlay to a recall named window
  prose_overlay_retarget_focus      — retarget AND immediately focus named window
  prose_overlay_get_target_label    — return display label for current target window
"""

from talon import Module

mod = Module()


@mod.action_class
class Actions:
    def prose_overlay_retarget(name: str):
        """Retarget the overlay to a recall named window.
        On confirm, that window will be focused before text is inserted.
        """
        pass  # WAVE 2: implement

    def prose_overlay_retarget_focus(name: str):
        """Retarget AND immediately focus the named recall window.
        Use when the window name leads a phrase: the window is frontmost
        so confirm can insert directly without an extra focus step.
        """
        pass  # WAVE 2: implement

    def prose_overlay_get_target_label() -> str:
        """Return the display label for the current target window."""
        pass  # WAVE 2: implement
