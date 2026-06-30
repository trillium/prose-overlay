"""Core internal helpers for the prose overlay: hat recomputation, tag sync, hat lookup.

Migrated from prose_overlay.py in wave 2. Uses instance.* for all state access.
Never imports prose_overlay.py.

Contains:
  _recompute_hats   — recompute hat assignments from current buffer state
  _sync_tags        — sync context tags to canvas + auto-dictation state
  _hat_to_index     — convert (letter, color) hat reference to token index
"""

from ..internal.instance import instance
from .hats_js import compute_hat_assignments
from . import hats_js as _hats_js_mod
from .shapes import compute_shape_assignments, shapes_enabled
from ..cursorless.resolve import (
    _state as _resolve_state,
)
from ..internal.homophones import flagged_indices


def _recompute_hats():
    """Recompute hat assignments from the current buffer state.

    Updates both the forward map (token_index -> assignment) and the
    reverse map ((letter, color) -> token_index) used for spoken hat lookup.
    Pushes the assignments into the canvas for rendering.
    Syncs _resolve_state.hat_to_token and _resolve_state.buffer from instance.

    Slice 2 addition (HOMOPHONE_SHAPES_PLAN.md §3): when shapes are enabled
    (static setting OR runtime flag), also recompute
    ``instance.shape_assignments`` — the per-token shape mapping for
    flagged homophones. Stable across edits via prior-assignment carryover
    inside ``compute_shape_assignments``.
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

    # Slice 2 — deterministic shape allocator for flagged homophone tokens.
    # Mirrors the letter-hat allocator's lifecycle: runs after every state
    # mutation that calls _recompute_hats, riding the existing redraw
    # debounce. Reads the static setting via talon.settings AND the runtime
    # module flag in shim.shapes — either one true enables shapes. We
    # import talon.settings lazily so this module stays importable in the
    # headless test runner (which does not load Talon).
    shapes_on = shapes_enabled()
    if not shapes_on:
        try:
            from talon import settings  # type: ignore
            shapes_on = bool(settings.get("user.prose_overlay_homophone_shapes"))
        except Exception:
            shapes_on = False
    if shapes_on:
        flagged = frozenset(flagged_indices(tokens))
        rev = getattr(instance.buffer, "rev", 0)
        instance.shape_assignments = compute_shape_assignments(
            tokens=tokens,
            flagged=flagged,
            rev=rev,
            prior=instance.shape_assignments,
        )
    else:
        instance.shape_assignments = {}

    from ..internal.debug import emit_if_changed
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
