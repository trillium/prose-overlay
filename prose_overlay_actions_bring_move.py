"""Bring/move actions for the prose overlay: hat-to-hat copy and cut operations.

Stub file — action bodies will be implemented in wave 2.
Type signatures are copied exactly from prose_overlay.py.

Contains:
  prose_overlay_bring_hat_to_hat — copy src token, replace dst token (bring)
  prose_overlay_move_hat_to_hat  — cut src token, replace dst token (move)
"""

from talon import Module

mod = Module()


@mod.action_class
class Actions:
    def prose_overlay_bring_hat_to_hat(
        src_letter: str, src_color: str,
        dst_letter: str, dst_color: str,
    ):
        """Copy the token at src hat, replace the token at dst hat with it (bring)."""
        pass  # WAVE 2: implement

    def prose_overlay_move_hat_to_hat(
        src_letter: str, src_color: str,
        dst_letter: str, dst_color: str,
    ):
        """Cut the token at src hat and replace the token at dst hat with it (move)."""
        pass  # WAVE 2: implement
