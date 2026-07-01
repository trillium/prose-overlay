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
from .shape_bridge import compute_hat_assignments_with_group_shapes
from .shapes import compute_shape_assignments, shapes_enabled, compute_panel_alts
from ..cursorless.resolve import (
    _state as _resolve_state,
)
from ..internal.homophones import (
    flagged_indices,
    next_in_group,
    current_position_in_group,
)


def _cursorless_shape_allocator_enabled() -> bool:
    """Return True when the Slice 3 opt-in setting is flipped ON.

    Read via talon.settings when available (live Talon process); returns
    False in the headless harness (talon module absent). Wrapped so the
    check is a single lazy read per _recompute_hats call.
    """
    try:
        from talon import settings  # type: ignore
        return bool(settings.get("user.prose_overlay_use_cursorless_shape_allocator"))
    except Exception:
        return False


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

    # Shape allocator runs FIRST (before letter-hat allocator) when the
    # Slice 3 opt-in setting is on, so the projection wrapper can pass a
    # shape-enabled pool to the bundle. When the setting is off, the shape
    # allocator still runs — but AFTER the letter-hat allocator — matching
    # the pre-Slice-3 order exactly.
    shapes_on = shapes_enabled()
    if not shapes_on:
        try:
            from talon import settings  # type: ignore
            shapes_on = bool(settings.get("user.prose_overlay_homophone_shapes"))
        except Exception:
            shapes_on = False

    use_bridge = shapes_on and _cursorless_shape_allocator_enabled()

    if use_bridge:
        # Slice 3 path: compute shape assignments first, then call the bridge.
        flagged = frozenset(flagged_indices(tokens))
        rev = getattr(instance.buffer, "rev", 0)
        instance.shape_assignments = compute_shape_assignments(
            tokens=tokens,
            flagged=flagged,
            rev=rev,
            prior=instance.shape_assignments,
        )
        instance.hat_assignments = compute_hat_assignments_with_group_shapes(
            tokens=tokens,
            shape_assignments=instance.shape_assignments,
            old_assignments=instance.hat_assignments,
            cursor_pos=cursor_for_hats,
        )
    else:
        # Pre-Slice-3 default path: letter-hat allocator first (colors-only
        # pool), then the deterministic shape allocator runs independently.
        instance.hat_assignments = compute_hat_assignments(
            tokens, old_assignments=instance.hat_assignments, cursor_pos=cursor_for_hats
        )
    instance.hat_js_fallback = _hats_js_mod._using_fallback
    instance.hat_js_last_err = _hats_js_mod._last_err
    # The tuple's third slot is `styleName` in the Slice-2+ world — may be
    # bare color ('gray') OR shape-suffixed ('gray-frame'). The hat_to_token
    # reverse map keys on BOTH the fully-qualified styleName AND the pre-'-'
    # bare color so:
    #   - `chuck blue air` continues to resolve when the pool is colors-only.
    #   - `chuck gray air` continues to resolve on a token whose bundle-
    #     assigned style is `gray-frame` (backcompat during Slice 3 bake).
    #   - A future grammar surface for shape-qualified marks can look up
    #     the full `gray-frame` styleName directly.
    # If the bare-color slot collides across two shape-suffixed styles (e.g.
    # `gray-frame` and `gray-bolt` on the same letter), the last write wins
    # — same collision semantics as pre-Slice-3 when a letter had two hats.
    _reverse: dict[tuple[str, str], int] = {}
    for idx, (_, letter, style) in instance.hat_assignments.items():
        _reverse[(letter, style)] = idx
        dash = style.find("-")
        if dash > 0:
            _reverse[(letter, style[:dash])] = idx
    instance.hat_to_token = _reverse
    _resolve_state.hat_to_token = instance.hat_to_token
    _resolve_state.buffer = instance.buffer
    instance.canvas.set_hat_assignments(instance.hat_assignments)

    # When the bridge path already computed shape_assignments above, skip
    # the second call. Otherwise fall through to the classic post-hat
    # allocator invocation for shapes.
    if not use_bridge:
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

    # Slice A of docs/PHONES_SPEC.md — per-flagged-token cycle state.
    # next_alt_assignments + position_assignments are recomputed on every
    # _recompute_hats call so the segmented underline and the cycling swap
    # always see consistent state. Both are cheap (one dict lookup per
    # flagged token); skipping the memoization that shape_assignments uses
    # because these maps are O(flagged_count) per call and the action only
    # reads from them at swap time, not on every paint.
    #
    # We compute these unconditionally (not gated on shapes_on) because
    # word-addressed cycling (`phones <word>`, Scenario 5) and letter-hat
    # cycling (`phones <letter>`, Scenario 6) work without shapes painted.
    # The shape paint and the cycle data are orthogonal addressing axes.
    flagged_for_cycle = (
        flagged
        if shapes_on
        else frozenset(flagged_indices(tokens))
    )
    new_next_alt: dict[int, str] = {}
    new_positions: dict[int, tuple[int, int]] = {}
    for idx in flagged_for_cycle:
        if idx < 0 or idx >= len(tokens):
            continue
        word = tokens[idx]
        nxt = next_in_group(word)
        if nxt is not None:
            new_next_alt[idx] = nxt
        pos = current_position_in_group(word)
        if pos is not None:
            new_positions[idx] = pos
    instance.next_alt_assignments = new_next_alt
    instance.position_assignments = new_positions

    # Slice C of docs/PHONES_SPEC.md — per-shape-hatted-token panel.
    # compute_panel_alts walks instance.shape_assignments and builds the
    # color → alt_word mapping that the panel renderer paints and the
    # color-addressed swap action looks up. Cheap (O(shape_count) with
    # small constants); no memoization needed for the same reason as
    # next_alt_assignments above.
    if shapes_on and instance.shape_assignments:
        instance.homophone_panel_alts = compute_panel_alts(
            tokens=tokens,
            flagged=flagged_for_cycle,
            shape_assignments=instance.shape_assignments,
        )
    else:
        instance.homophone_panel_alts = {}

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
