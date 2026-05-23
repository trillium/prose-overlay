"""Delete actions for the prose overlay: hat deletion with head/tail modifiers.

Stub file — action bodies will be implemented in wave 2.
Type signatures are copied exactly from prose_overlay.py.

Contains:
  prose_overlay_delete_hat        — delete the token at a hat
  prose_overlay_delete_past_hat   — delete from hat through end of buffer
  prose_overlay_delete_head_hat   — delete from start through hat
  prose_overlay_delete_tail_hat   — delete from hat through end of buffer
"""

from talon import Module

mod = Module()


@mod.action_class
class Actions:
    def prose_overlay_delete_hat(letter: str, color: str = "gray"):
        """Delete the token at the given hat (letter + optional color)."""
        pass  # WAVE 2: implement

    def prose_overlay_delete_past_hat(letter: str, color: str = "gray"):
        """Delete from the hat through the end of the buffer (chuck past <hat>)."""
        pass  # WAVE 2: implement

    def prose_overlay_delete_head_hat(letter: str, color: str = "gray"):
        """Delete from start of buffer through the token at the given hat (chuck head)."""
        pass  # WAVE 2: implement

    def prose_overlay_delete_tail_hat(letter: str, color: str = "gray"):
        """Delete from the token at the given hat through end of buffer (chuck tail)."""
        pass  # WAVE 2: implement
