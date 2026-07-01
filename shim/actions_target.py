"""Target/retarget actions for the prose overlay: window targeting and label queries.

Migrated from prose_overlay.py in wave 2. Uses instance.* for all state access.
Never imports prose_overlay.py.

Contains:
  prose_overlay_retarget            — retarget overlay to a recall named window
  prose_overlay_retarget_focus      — retarget AND immediately focus named window
  prose_overlay_get_target_label    — return display label for current target window
"""

from talon import Module, actions

from ..internal.instance import instance

mod = Module()


@mod.action_class
class Actions:
    def prose_overlay_retarget(name: str):
        """Retarget the overlay to a recall named window.
        On confirm, that window will be focused before text is inserted.
        """
        instance.state.target_recall_name = name
        instance.state.target_window_title = name
        instance.runtime.canvas.refresh()

    def prose_overlay_retarget_focus(name: str):
        """Retarget AND immediately focus the named recall window.
        Use when the window name leads a phrase: the window is frontmost
        so confirm can insert directly without an extra focus step.
        """
        instance.state.target_recall_name = name
        instance.state.target_window_title = name
        instance.runtime.canvas.refresh()
        actions.user.recall_window(name)

    def prose_overlay_get_target_label() -> str:
        """Return the display label for the current target window."""
        if instance.state.target_recall_name:
            return f"→ {instance.state.target_recall_name}"
        if instance.state.target_window_title:
            t = instance.state.target_window_title
            return f"→ {t[:40]}…" if len(t) > 40 else f"→ {t}"
        return ""
