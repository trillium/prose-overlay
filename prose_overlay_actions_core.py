"""Core internal helpers for the prose overlay: hat recomputation, tag sync, hat lookup.

Migrated from prose_overlay.py in wave 2. Uses instance.* for all state access.
Never imports prose_overlay.py.

Contains:
  _recompute_hats   — recompute hat assignments from current buffer state
  _sync_tags        — sync context tags to canvas + auto-dictation state
  _hat_to_index     — convert (letter, color) hat reference to token index
"""

from .prose_overlay_instance import instance
from .prose_overlay_hats_js import compute_hat_assignments
from . import prose_overlay_hats_js as _hats_js_mod
from .prose_overlay_cursorless_resolve import (
    _state as _resolve_state,
)


def _recompute_hats():
    """Recompute hat assignments from the current buffer state.

    Updates both the forward map (token_index -> assignment) and the
    reverse map ((letter, color) -> token_index) used for spoken hat lookup.
    Pushes the assignments into the canvas for rendering.
    Syncs _resolve_state.hat_to_token and _resolve_state.buffer from instance.
    """
    tokens = instance.buffer.get_tokens()
    # When no cursor is set, default proximity to end of buffer (where writing happens).
    cursor_for_hats = instance.cursor if instance.cursor is not None else len(tokens)
    instance.hat_assignments = compute_hat_assignments(
        tokens, old_assignments=instance.hat_assignments, cursor_pos=cursor_for_hats
    )
    instance.hat_js_fallback = _hats_js_mod._using_fallback
    instance.hat_to_token = {
        (letter, color): idx
        for idx, (_, letter, color) in instance.hat_assignments.items()
    }
    _resolve_state.hat_to_token = instance.hat_to_token
    _resolve_state.buffer = instance.buffer
    instance.canvas.set_hat_assignments(instance.hat_assignments)
    from .prose_overlay_debug import emit_if_changed
    emit_if_changed("recompute_hats")


def _sync_tags():
    """Sync context tags to match current canvas + auto-dictation state.

    Ground truth is instance.canvas.is_showing — tags follow canvas state, never the
    reverse. Calling this after any state change keeps tags consistent.
    """
    if instance.canvas.is_showing:
        instance.ctx.tags = ["user.prose_overlay_active"]
        instance.ctx_auto.tags = []  # auto tag off while overlay is open
    else:
        instance.ctx.tags = []
        instance.ctx_auto.tags = ["user.prose_overlay_auto"] if instance.auto_dictation else []


def _hat_to_index(letter: str, color: str = "gray") -> int:
    """Convert a (letter, color) hat reference to a token index.

    Uses the reverse assignment map so the spoken hat name matches the dot
    that's actually visible. Color defaults to "gray" — the no-prefix case.
    Returns -1 if the (letter, color) pair is not currently assigned.
    """
    return instance.hat_to_token.get((letter.lower(), color), -1)
