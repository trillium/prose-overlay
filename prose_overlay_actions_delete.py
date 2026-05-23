"""Delete actions for the prose overlay: hat deletion with head/tail modifiers.

Migrated from prose_overlay.py in wave 2. Uses instance.* for all state access.
Never imports prose_overlay.py.

Contains:
  prose_overlay_delete_hat        — delete the token at a hat
  prose_overlay_delete_past_hat   — delete from hat through end of buffer
  prose_overlay_delete_head_hat   — delete from start through hat
  prose_overlay_delete_tail_hat   — delete from hat through end of buffer
"""

from talon import Module, actions

from .prose_overlay_instance import instance
from .prose_overlay_actions_core import _hat_to_index, _recompute_hats
from .prose_overlay_actions_flash import _flash_tokens, _action_color

mod = Module()


@mod.action_class
class Actions:
    def prose_overlay_delete_hat(letter: str, color: str = "gray"):
        """Delete the token at the given hat (letter + optional color)."""
        index = _hat_to_index(letter, color)
        if index >= 0:
            def _do():
                instance.buffer.delete_token(index)
                _recompute_hats()
                instance.canvas.refresh()
            _flash_tokens([index], _action_color("remove"), _do)

    def prose_overlay_delete_past_hat(letter: str, color: str = "gray"):
        """Delete from the hat through the end of the buffer (chuck past <hat>)."""
        index = _hat_to_index(letter, color)
        if index >= 0:
            flash_indices = list(range(index, len(instance.buffer.get_tokens())))
            def _do():
                instance.buffer.delete_through(index)
                _recompute_hats()
                instance.canvas.refresh()
            _flash_tokens(flash_indices, _action_color("remove"), _do)

    def prose_overlay_delete_head_hat(letter: str, color: str = "gray"):
        """Delete from start of buffer through the token at the given hat (chuck head)."""
        index = _hat_to_index(letter, color)
        if index >= 0:
            flash_indices = list(range(0, index + 1))
            def _do():
                instance.buffer.delete_head(index)
                _recompute_hats()
                instance.canvas.refresh()
            _flash_tokens(flash_indices, _action_color("remove"), _do)

    def prose_overlay_delete_tail_hat(letter: str, color: str = "gray"):
        """Delete from the token at the given hat through end of buffer (chuck tail)."""
        actions.user.prose_overlay_delete_past_hat(letter, color)
