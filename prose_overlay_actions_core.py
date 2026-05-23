"""Core internal helpers for the prose overlay: hat recomputation, tag sync, hat lookup.

Stub file — functions will be migrated here from prose_overlay.py in wave 2.
Each stub is marked with a WAVE 2 comment describing what moves here.

Contains:
  _recompute_hats   — recompute hat assignments from current buffer state
  _sync_tags        — sync context tags to canvas + auto-dictation state
  _hat_to_index     — convert (letter, color) hat reference to token index
"""

# WAVE 2: add imports from talon (Context, Module, actions, etc.) and
# from prose_overlay_instance import instance when migrating state.


def _recompute_hats():
    # WAVE 2: migrate here from prose_overlay.py
    # Recomputes _hat_assignments and _hat_to_token from _buffer, pushes
    # assignments into _canvas, and updates _resolve_state.hat_to_token.
    raise NotImplementedError("_recompute_hats: not yet migrated (wave 2)")


def _sync_tags():
    # WAVE 2: migrate here from prose_overlay.py
    # Syncs _ctx and _ctx_auto tags based on _canvas.is_showing and
    # _auto_dictation. Ground truth is canvas state — tags follow, never lead.
    raise NotImplementedError("_sync_tags: not yet migrated (wave 2)")


def _hat_to_index(letter: str, color: str = "gray") -> int:
    # WAVE 2: migrate here from prose_overlay.py
    # Converts a (letter, color) hat reference to a token index using the
    # reverse assignment map _hat_to_token. Returns -1 if not found.
    raise NotImplementedError("_hat_to_index: not yet migrated (wave 2)")
