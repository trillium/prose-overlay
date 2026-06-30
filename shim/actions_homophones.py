"""Homophone swap actions — Slice 4 of docs/HOMOPHONE_SHAPES_PLAN.md /
Slice A of docs/PHONES_SPEC.md.

Owns the four addressing paths that route to the same underlying swap:

  prose_overlay_phone_shape(shape_name)              — Slice A (Scenarios 1, 2, 7)
  prose_overlay_phone_word(word)                     — Slice B (Scenario 5)
  prose_overlay_phone_letter(letter, color)          — Slice B (Scenario 6)
  prose_overlay_phone_color_shape(color, shape_name) — Slice C (Scenario 4)

Each action:
  1. Resolves the target token_idx from its addressing key.
  2. Looks up the target replacement word.
  3. Brackets the buffer mutation with
       commit_start("phone <label>", STRUCTURAL) / commit_end()
     so the swap lands as ONE undo record (Scenario 12).
  4. Refreshes the canvas and calls _recompute_hats so the segmented
     underline + cycle state pick up the new current word.

All resolution failures (no shape, unflagged word, missing letter hat,
panel color not in current mapping, degenerate 1-member group) become
no-ops with a printed log hint per OQ4/OQ10. Defensive — does not
surface error UI in v1.

Layer audit: imports from talon (SHIM is allowed) + instance + internal
helpers. Never imports prose_overlay.py.
"""

from talon import Module

from ..internal.instance import instance
from ..internal.state import EditKind
from ..internal.homophones import next_in_group


mod = Module()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _shape_to_index(shape_name: str) -> int:
    """Return the token_idx currently wearing the given shape hat, or -1.

    Walks instance.shape_assignments (set by shim.actions_core._recompute_hats).
    No-op when shapes are disabled or the shape is not assigned to any token
    (Scenarios 7 + 9 + 13 all collapse to this branch).
    """
    for idx, sname in instance.shape_assignments.items():
        if sname == shape_name:
            return idx
    return -1


def _swap_token(idx: int, new_word: str, label: str) -> bool:
    """Replace tokens[idx] with new_word inside a STRUCTURAL undo bracket.

    Returns True if the swap happened. False if idx is out of range, the
    old and new words are identical (degenerate 1-member group), or the
    buffer is missing (defensive — shouldn't happen in normal flow).
    """
    buf = instance.buffer
    if buf is None:
        return False
    tokens = buf.get_tokens()
    if idx < 0 or idx >= len(tokens):
        return False
    old_word = tokens[idx]
    if old_word == new_word:
        # 1-member-row case (OQ4) — next_in_group returns the same word.
        # Skip the bracket entirely so we don't push an empty undo record.
        return False
    new_tokens = list(tokens)
    new_tokens[idx] = new_word
    buf.commit_start(label, EditKind.STRUCTURAL)
    buf.set_tokens_raw(new_tokens)
    buf.commit_end()
    return True


def _refresh_after_swap() -> None:
    """Refresh canvas + recompute hats after a successful swap.

    Imported lazily so this module stays importable in headless tests
    that load the shim layer without going through prose_overlay.py.
    """
    if instance.canvas is not None:
        instance.canvas.refresh()
    # Recompute happens after the refresh because _recompute_hats pushes
    # the new hat assignments into the canvas, which then refreshes
    # again on the next paint cycle. Two refreshes is fine — the canvas
    # debounces and the second draw sees a stable state.
    from .actions_core import _recompute_hats
    _recompute_hats()


@mod.action_class
class Actions:
    def prose_overlay_phone_shape(shape_name: str):
        """Cycle the homophone token wearing the given shape hat to its
        next CSV-row member, wrapping at the end of the row.

        Slice A of docs/PHONES_SPEC.md — Scenarios 1 (basic), 2 (cycling),
        7 (no matching shape), 8 (post-edit), 9 (pool overflow),
        11 (grammar specificity), 12 (undo), 13 (empty buffer).
        """
        idx = _shape_to_index(shape_name)
        if idx < 0:
            print(f"prose_overlay: phone shape {shape_name!r} — no token has that shape")
            return
        new_word = instance.next_alt_assignments.get(idx)
        if new_word is None:
            print(
                f"prose_overlay: phone shape {shape_name!r} (idx {idx}) — "
                "no next-alt available (degenerate group or stale state)"
            )
            return
        if not _swap_token(idx, new_word, f"phone {shape_name}"):
            return
        _refresh_after_swap()
