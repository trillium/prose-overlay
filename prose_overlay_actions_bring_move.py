"""Bring/move actions for the prose overlay: hat-to-hat copy and cut operations.

Migrated from prose_overlay.py in wave 2. Uses instance.* for all state access.
Never imports prose_overlay.py.

Contains:
  prose_overlay_bring_hat_to_hat — copy src token, replace dst token (bring)
  prose_overlay_move_hat_to_hat  — cut src token, replace dst token (move)
"""

from talon import Module

from .prose_overlay_instance import instance
from .prose_overlay_actions_core import _hat_to_index, _recompute_hats

mod = Module()


@mod.action_class
class Actions:
    def prose_overlay_bring_hat_to_hat(
        src_letter: str, src_color: str,
        dst_letter: str, dst_color: str,
    ):
        """Copy the token at src hat, replace the token at dst hat with it (bring)."""
        src = _hat_to_index(src_letter, src_color)
        dst = _hat_to_index(dst_letter, dst_color)
        if src < 0 or dst < 0 or src == dst:
            return
        tokens = instance.buffer.get_tokens()
        src_text = tokens[src]
        instance.buffer.replace_token(dst, src_text)
        _recompute_hats()
        instance.canvas.refresh()

    def prose_overlay_move_hat_to_hat(
        src_letter: str, src_color: str,
        dst_letter: str, dst_color: str,
    ):
        """Cut the token at src hat and replace the token at dst hat with it (move)."""
        src = _hat_to_index(src_letter, src_color)
        dst = _hat_to_index(dst_letter, dst_color)
        if src < 0 or dst < 0 or src == dst:
            return
        tokens = instance.buffer.get_tokens()
        src_text = tokens[src]
        # Replace dst first (index stable if src != dst), then delete src.
        instance.buffer.replace_token(dst, src_text)
        # After replace, src index unchanged — delete it.
        instance.buffer.delete_token(src)
        _recompute_hats()
        instance.canvas.refresh()
