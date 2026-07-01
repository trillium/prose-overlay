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
from ..internal.homophones import is_flagged, next_in_group, normalize_token
from .actions_core import _hat_to_index


mod = Module()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _shape_to_index(shape_name: str) -> int:
    """Return the token_idx currently wearing the given shape hat, or -1.

    Walks instance.state.shape_assignments (set by shim.actions_core._recompute_hats).
    No-op when shapes are disabled or the shape is not assigned to any token
    (Scenarios 7 + 9 + 13 all collapse to this branch).
    """
    for idx, sname in instance.state.shape_assignments.items():
        if sname == shape_name:
            return idx
    return -1


def _swap_token(idx: int, new_word: str, label: str) -> bool:
    """Replace tokens[idx] with new_word inside a STRUCTURAL undo bracket.

    Returns True if the swap happened. False if idx is out of range, the
    old and new words are identical (degenerate 1-member group), or the
    buffer is missing (defensive — shouldn't happen in normal flow).
    """
    buf = instance.state.buffer
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
    if instance.runtime.canvas is not None:
        instance.runtime.canvas.refresh()
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
        new_word = instance.state.next_alt_assignments.get(idx)
        if new_word is None:
            print(
                f"prose_overlay: phone shape {shape_name!r} (idx {idx}) — "
                "no next-alt available (degenerate group or stale state)"
            )
            return
        if not _swap_token(idx, new_word, f"phone {shape_name}"):
            return
        _refresh_after_swap()

    def prose_overlay_phone_word(word: str):
        """Cycle the FIRST flagged token currently reading `word` to its
        next CSV-row member.

        Slice B of docs/PHONES_SPEC.md — Scenario 5. OQ3 resolved:
        FIRST match by token index (simple, deterministic). If multiple
        tokens read the same word, the lower-index one swaps; the others
        are unchanged. Useful when the user doesn't remember the shape
        name OR wants to address an overflow token (Scenario 9).

        No-op with log hint when:
          - the buffer is missing,
          - no token in the buffer matches the spoken word, OR
          - the matching token is unflagged (the word isn't a homophone
            in our CSV; defensive — the grammar uses
            <user.homophones_canonical> so the word IS flagged, but the
            action defends anyway).
        """
        buf = instance.state.buffer
        if buf is None:
            return
        target_key = normalize_token(word)
        tokens = buf.get_tokens()
        target_idx = -1
        for i, tok in enumerate(tokens):
            if normalize_token(tok) == target_key and is_flagged(tok):
                target_idx = i
                break
        if target_idx < 0:
            print(
                f"prose_overlay: phone word {word!r} — "
                "no flagged token in the buffer reads that word"
            )
            return
        new_word = next_in_group(tokens[target_idx])
        if new_word is None or new_word == tokens[target_idx]:
            # next_in_group None should be unreachable given is_flagged
            # check above; equality means a degenerate 1-member row (OQ4).
            print(
                f"prose_overlay: phone word {word!r} (idx {target_idx}) — "
                "degenerate 1-member group; no swap"
            )
            return
        if not _swap_token(target_idx, new_word, f"phone {word}"):
            return
        _refresh_after_swap()

    def prose_overlay_phone_letter(letter: str, color: str = "gray"):
        """Cycle the token at letter hat `(color, letter)` to its next
        CSV-row member, but ONLY if the token is currently flagged.

        Slice B of docs/PHONES_SPEC.md — Scenario 6. The letter hat is
        the existing Cursorless-style gray-letter dot painted on EVERY
        visible token (flagged or not); this action is the
        homophone-aware verb on that same hat. Falls through as a no-op
        with log hint when:
          - the (letter, color) pair isn't currently assigned (no hat),
          - the addressed token is unflagged (per OQ10 default — no-op
            instead of falling through to the modal HUD; iterate later
            if real usage shows surprise),
          - the matching token's group is degenerate (1-member row, OQ4).

        Caveat per Scenario 6: after the swap, the letter-hat allocator
        may reassign the (color, letter) slot to a DIFFERENT token (the
        new word may not have a `letter` character). Repeated
        `phones <letter>` calls may target different tokens session over
        session — `phone <shape>` is the muscle-memory path. The action
        body intentionally does not paper over this — it would require a
        snapshot of the pre-swap hat assignment, which contradicts the
        whole point of the letter-hat allocator being character-derived.
        """
        idx = _hat_to_index(letter, color)
        if idx < 0:
            print(
                f"prose_overlay: phone letter {color}-{letter} — no hat assigned"
            )
            return
        buf = instance.state.buffer
        if buf is None:
            return
        tokens = buf.get_tokens()
        if idx >= len(tokens):
            return
        tok = tokens[idx]
        if not is_flagged(tok):
            print(
                f"prose_overlay: phone letter {color}-{letter} (token "
                f"{tok!r}, idx {idx}) — token is not a flagged homophone"
            )
            return
        new_word = next_in_group(tok)
        if new_word is None or new_word == tok:
            # Defensive — is_flagged is True so the group exists, but
            # a 1-member row would still return the same word (OQ4).
            print(
                f"prose_overlay: phone letter {color}-{letter} — degenerate "
                "1-member group; no swap"
            )
            return
        if not _swap_token(idx, new_word, f"phone {color}-{letter}"):
            return
        _refresh_after_swap()

    def prose_overlay_phone_color_shape(prose_hat_color: str, shape_name: str):
        """Swap the homophone token wearing the given shape hat DIRECTLY to
        the alt currently shown on the given color chip.

        Slice C of docs/PHONES_SPEC.md — Scenario 4. The user reads the
        panel chip ('gold play') and says the matching utterance; the
        action looks up the token by shape, looks up the panel mapping
        for that color, and swaps. Routes through the same _swap_token
        bracket so it's one undo step.

        `prose_hat_color` is the normalised form from prose_hat_color
        capture (gold→yellow, plum→purple). The panel mapping in
        instance.state.homophone_panel_alts is keyed on the same normalised
        form, so the lookup is direct.

        No-ops with log hint when:
          - no token has the spoken shape (Scenario 7),
          - the shape-hatted token has no panel entry (group ≤ 1 or
            shapes off),
          - the color is not in the current panel mapping (stale call —
            user spoke a color that's not currently a slot),
          - the swap would be a no-op (new == old; shouldn't happen
            because the current word is excluded from the panel).
        """
        idx = _shape_to_index(shape_name)
        if idx < 0:
            print(
                f"prose_overlay: {prose_hat_color} {shape_name} — no token has that shape"
            )
            return
        panel_entry = instance.state.homophone_panel_alts.get(idx)
        if not panel_entry:
            print(
                f"prose_overlay: {prose_hat_color} {shape_name} (idx {idx}) — "
                "no panel entry (group is degenerate or shapes off)"
            )
            return
        new_word = panel_entry.get(prose_hat_color)
        if new_word is None:
            print(
                f"prose_overlay: {prose_hat_color} {shape_name} (idx {idx}) — "
                f"color {prose_hat_color!r} not in current panel "
                f"({sorted(panel_entry.keys())})"
            )
            return
        if not _swap_token(idx, new_word, f"phone {prose_hat_color} {shape_name}"):
            return
        _refresh_after_swap()
