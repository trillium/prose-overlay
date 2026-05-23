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
        # Manual snapshot + splice instead of replace_token, which splits on
        # whitespace and discards everything after the first word.  This
        # preserves multi-word source text (e.g. when src_text came from a
        # range or was previously inserted as multiple tokens).
        instance.buffer.snapshot()
        instance.buffer._tokens.pop(dst)
        instance.buffer._selection = None
        words = src_text.strip().split()
        for i, w in enumerate(words):
            instance.buffer._tokens.insert(dst + i, w)
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
        # Manual snapshot + splice instead of replace_token (which discards
        # multi-word text).  Remove both tokens and insert src text at dst's
        # original position in a single undo step.
        instance.buffer.snapshot()
        instance.buffer._selection = None
        # Remove higher index first so the lower index stays stable.
        hi, lo = max(src, dst), min(src, dst)
        instance.buffer._tokens.pop(hi)
        instance.buffer._tokens.pop(lo)
        # After removing both, dst's insert position is:
        #   dst == lo → lo (nothing before it was removed)
        #   dst == hi → hi - 1 (lo was removed before it, shifting it left by 1)
        insert_pos = lo if dst <= src else hi - 1
        words = src_text.strip().split()
        for i, w in enumerate(words):
            instance.buffer._tokens.insert(insert_pos + i, w)
        _recompute_hats()
        instance.canvas.refresh()
