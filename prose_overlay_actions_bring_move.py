"""Bring/move actions for the prose overlay: hat-to-hat copy and cut operations.

Migrated from prose_overlay.py in wave 2. Uses instance.* for all state access.
Never imports prose_overlay.py.

Contains:
  prose_overlay_bring_hat_to_hat — copy src token, replace dst token (bring)
  prose_overlay_move_hat_to_hat  — cut src token, replace dst token (move)
"""

from talon import Module

from .internal.instance import instance
from .shim.actions_core import _hat_to_index, _recompute_hats
from .internal.state import EditKind

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
        # Splice locally then commit through the bracket API so rev bumps and
        # the undo record carries the inversion. replace_token would split on
        # whitespace and discard everything after the first word; this
        # preserves multi-word source text.
        words = src_text.strip().split()
        new_tokens = list(tokens)
        new_tokens.pop(dst)
        for i, w in enumerate(words):
            new_tokens.insert(dst + i, w)
        instance.buffer.commit_start("bring_hat_to_hat", EditKind.STRUCTURAL)
        instance.buffer.set_tokens_raw(new_tokens)
        instance.buffer.commit_end()
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
        words = src_text.strip().split()
        new_tokens = list(tokens)
        # Remove higher index first so the lower index stays stable.
        hi, lo = max(src, dst), min(src, dst)
        new_tokens.pop(hi)
        new_tokens.pop(lo)
        # After removing both, dst's insert position is:
        #   dst == lo → lo (nothing before it was removed)
        #   dst == hi → hi - 1 (lo was removed before it, shifting it left by 1)
        insert_pos = lo if dst <= src else hi - 1
        for i, w in enumerate(words):
            new_tokens.insert(insert_pos + i, w)
        instance.buffer.commit_start("move_hat_to_hat", EditKind.STRUCTURAL)
        instance.buffer.set_tokens_raw(new_tokens)
        instance.buffer.commit_end()
        _recompute_hats()
        instance.canvas.refresh()
