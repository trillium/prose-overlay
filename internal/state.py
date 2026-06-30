"""Prose Overlay State -- word token buffer for dictation capture.

Pure state management with no Talon dependencies. The buffer stores
individual word tokens and supports indexed deletion for hat-targeted editing.

Hat allocation: assigns a unique (letter, color) pair to each visible token so
that spoken hat names (air/bat/cap/..., optionally prefixed with a color) unambiguously
identify words. Matches Cursorless collision resolution: same letter, different color.
"""

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time

# Color priority order: gray is default (no prefix spoken), then colors in order.
# When two tokens share the same best letter, the second gets the next available color.
HAT_COLOR_PRIORITY = ["gray", "blue", "green", "red", "pink", "yellow", "purple", "black", "white"]


# Module-level coalescing window. Default 0.0 (OFF — every mutation outside a
# commit_start/commit_end bracket becomes its own undo record, matching the
# pre-refactor behavior). Flip to a positive value (CM6 uses 0.400) via
# prose_overlay_undo_group_set(True) to opt into dictation merging.
_GROUP_DELAY_S: float = 0.0


def compute_hat_assignments(
    tokens: list[str],
    cursor_pos: int | None = None,
    old_assignments: dict[int, tuple[int, str, str]] | None = None,
) -> dict[int, tuple[int, str, str]]:
    """Assign a unique (letter, color) pair to each token for hat identification.

    Returns a mapping of token_index -> (char_index_within_word, letter, color)
    where letter is the lowercase grapheme and color is the hat color name.

    cursor_pos: gap index (0 = before all tokens, N = after all tokens).
    Tokens closest to the cursor get first pick of the best hats. Defaults to
    len(tokens) (end of buffer) when None, matching the writing position.

    old_assignments: prior result for stability across edits. When provided,
    each token's prior (letter, color) is preferred IF the letter is still
    alpha-present in the new token at SOME char_idx. The char_idx is always
    recomputed from the new token's text — the prior (5, 'r', 'gray') for
    "they're" becomes (4, 'r', 'gray') for "their" because 'r' is now at
    idx 4. This stops the user-visible "phones <shape>" bug where a swap
    leaves the letter hat painting past the end of the new word.

    Algorithm (Cursorless-style color collision resolution):
    1. Process tokens in proximity order from cursor (closest first).
    2. PRE-PASS: if old_assignments present, try to honor prior (letter, color)
       for the same token_idx — repositioning char_idx in the new token.
    3. For tokens without an honored prior, iterate letters left to right.
    4. For each letter, try colors in HAT_COLOR_PRIORITY order.
    5. Assign the first (letter, color) combo not already claimed.
    6. If all combos for all letters are exhausted, the token gets no hat.

    Two tokens can share the same letter but get different colors, matching
    how Cursorless resolves collisions. "air" = gray-a, "blue air" = blue-a.
    """
    effective_cursor = cursor_pos if cursor_pos is not None else len(tokens)

    def _dist(i: int) -> int:
        return (effective_cursor - i - 1) if i < effective_cursor else (i - effective_cursor)

    priority_order = sorted(range(len(tokens)), key=_dist)

    claimed: set[tuple[str, str]] = set()
    assignments: dict[int, tuple[int, str, str]] = {}

    def _find_letter_idx(token: str, letter: str) -> int | None:
        """Return the first char_idx of `letter` in `token`, or None."""
        for ci, ch in enumerate(token):
            if ch.lower() == letter:
                return ci
        return None

    # PRE-PASS: honor prior assignments where possible.
    # Walks priority_order (cursor-closest first) so prior conflicts resolve
    # in proximity preference rather than first-token-wins.
    honored: set[int] = set()
    if old_assignments:
        for token_idx in priority_order:
            if token_idx >= len(tokens):
                continue
            prior = old_assignments.get(token_idx)
            if not prior:
                continue
            _old_ci, letter, color = prior
            token = tokens[token_idx]
            new_ci = _find_letter_idx(token, letter)
            if new_ci is None:
                # Prior letter not in new token — drop it, let normal pass handle.
                continue
            if (letter, color) in claimed:
                # Prior (letter, color) taken by a closer token — drop it.
                continue
            claimed.add((letter, color))
            assignments[token_idx] = (new_ci, letter, color)
            honored.add(token_idx)

    for token_idx in priority_order:
        if token_idx in honored:
            continue
        token = tokens[token_idx]
        # Build the ordered list of (char_idx, letter) for this token
        candidates = [
            (ci, ch.lower())
            for ci, ch in enumerate(token)
            if ch.lower().isalpha()
        ]
        if not candidates and token:
            # Non-letter token (digits like "123", pure punctuation like "!").
            # Paint a hat anyway so the user can SEE the token. Addressability
            # for digits/punct is a separate future slice — `<user.letter>`
            # currently only binds a-z, so "take 1" won't bind today, but the
            # visible hat is the load-bearing signal that the token exists.
            candidates = [(0, token[0].lower())]
        if not candidates:
            continue

        # Pass 1: try every letter in the word with gray.
        # This ensures "the the the" gets gray-t, gray-h, gray-e before
        # any token ever needs a color.
        assigned = False
        for char_idx, letter in candidates:
            if (letter, "gray") not in claimed:
                claimed.add((letter, "gray"))
                assignments[token_idx] = (char_idx, letter, "gray")
                assigned = True
                break

        if assigned:
            continue

        # Pass 2: all letters in this word are already claimed with gray.
        # Now try non-gray colors, still preferring earlier letters in the word.
        for color in HAT_COLOR_PRIORITY[1:]:  # skip "gray"
            for char_idx, letter in candidates:
                if (letter, color) not in claimed:
                    claimed.add((letter, color))
                    assignments[token_idx] = (char_idx, letter, color)
                    assigned = True
                    break
            if assigned:
                break

    return assignments


class EditKind(Enum):
    """Classification of an undo record's originating edit."""
    DICTATION = "dictation"        # add_text / insert_at from voice dictation
    STRUCTURAL = "structural"      # Cursorless edit-plan, formatter, bring/move
    EXPLICIT = "explicit"          # named voice command (delete_hat, change_hat, etc.)
    PROGRAMMATIC = "programmatic"  # internal — reserved


@dataclass
class TokenDelta:
    """One contiguous token-range replacement."""
    start: int                     # token index where replacement begins
    old_tokens: list[str]          # displaced tokens (needed for inverse)
    new_tokens: Optional[list[str]]  # tokens inserted in place; None = full-buffer snapshot resolved at undo


@dataclass
class UndoRecord:
    """One undoable group. Holds deltas in apply order plus selection."""
    deltas: list[TokenDelta]
    kind: EditKind
    label: str
    timestamp: float
    selection_before: Optional[tuple[int, int]]
    selection_after: Optional[tuple[int, int]]
    sealed: bool = False


class ProseBuffer:
    """Manages a list of word tokens captured from dictation."""

    _HISTORY_MAX = 200
    _MAX_COMPOSED_DELTAS = 64
    TRAILING_PUNCT = ".?!,;:)"

    def _split_trailing_punct(self, word: str) -> list[str]:
        """Split trailing punctuation off a word into a separate token.

        e.g. "hello." -> ["hello", "."]
             "wait!" -> ["wait", "!"]
             "..." -> ["..."]  # pure punctuation, kept as-is
        """
        if not word or word[-1] not in self.TRAILING_PUNCT:
            return [word]
        i = len(word) - 1
        while i >= 0 and word[i] in self.TRAILING_PUNCT:
            i -= 1
        root = word[:i + 1]
        punct = word[i + 1:]
        if not root:
            return [word]  # pure punctuation, keep as-is
        return [root, punct]

    def __init__(self):
        self._tokens: list[str] = []
        self._done: deque[UndoRecord] = deque(maxlen=self._HISTORY_MAX)
        self._undone: deque[UndoRecord] = deque(maxlen=self._HISTORY_MAX)
        self._open_group: Optional[UndoRecord] = None
        self._selection: tuple[int, int] | None = None  # (start_idx, end_idx) inclusive
        self.rev: int = 0

    # ---------------------------------------------------------------------------
    # Undo / redo
    # ---------------------------------------------------------------------------

    def snapshot(self):
        """Save current state to undo stack (call before any mutation).

        Phase 1 shim: records a full-buffer snapshot as a single UndoRecord whose
        sole delta has new_tokens=None — meaning "the post-state is whatever the
        buffer currently holds when undo() is invoked." This preserves the
        behavior of legacy callers that mutate _tokens directly after snapshot()
        (e.g. prose_overlay_actions_bring_move) and of callers that subsequently
        invoke set_tokens_raw() (e.g. _apply_edit_plan).
        """
        # If a group is open, the snapshot is implicit in that group — no-op.
        if self._open_group is not None:
            return
        delta = TokenDelta(start=0, old_tokens=list(self._tokens), new_tokens=None)
        record = UndoRecord(
            deltas=[delta],
            kind=EditKind.PROGRAMMATIC,
            label="snapshot",
            timestamp=time.monotonic(),
            selection_before=self._selection,
            selection_after=None,
            sealed=True,
        )
        self._done.append(record)
        self._undone.clear()
        self.rev += 1

    def undo(self) -> bool:
        """Restore previous state. Returns True if undo was available."""
        if not self._done:
            return False
        # If a group is currently open, seal it first so commit_start work that
        # never reached commit_end is still undoable as a unit.
        if self._open_group is not None:
            self._open_group.sealed = True
            self._open_group.selection_after = self._selection
            self._done.append(self._open_group)
            self._open_group = None
        record = self._done.pop()
        # Capture current tokens to build the redo-record before mutating.
        current = list(self._tokens)
        # Apply inverse: walk deltas in reverse order, replacing new with old.
        # Snapshot-style deltas (new_tokens=None) are full-buffer restores.
        for delta in reversed(record.deltas):
            if delta.new_tokens is None:
                # Full-buffer restore.
                self._tokens = list(delta.old_tokens)
            else:
                # Splice: replace tokens[start:start+len(new)] with old.
                end = delta.start + len(delta.new_tokens)
                self._tokens[delta.start:end] = list(delta.old_tokens)
        # Build redo record. For snapshot-style records, capture the full current.
        # For delta records, we already know forward shape, so reuse it.
        redo_deltas: list[TokenDelta] = []
        for delta in record.deltas:
            if delta.new_tokens is None:
                redo_deltas.append(TokenDelta(
                    start=0,
                    old_tokens=list(delta.old_tokens),
                    new_tokens=list(current),
                ))
            else:
                redo_deltas.append(TokenDelta(
                    start=delta.start,
                    old_tokens=list(delta.old_tokens),
                    new_tokens=list(delta.new_tokens),
                ))
        redo_record = UndoRecord(
            deltas=redo_deltas,
            kind=record.kind,
            label=record.label,
            timestamp=record.timestamp,
            selection_before=record.selection_before,
            selection_after=record.selection_after,
            sealed=True,
        )
        self._undone.append(redo_record)
        self._selection = None
        self.rev += 1
        return True

    def redo(self) -> bool:
        """Re-apply the most recently undone record. Returns True if redo available."""
        if not self._undone:
            return False
        record = self._undone.pop()
        # Apply forward deltas in original order.
        for delta in record.deltas:
            if delta.new_tokens is None:
                # Defensive: redo records should always have concrete new_tokens.
                continue
            end = delta.start + len(delta.old_tokens)
            self._tokens[delta.start:end] = list(delta.new_tokens)
        # Build the inverse record for the next undo. Mirror old/new.
        undo_deltas: list[TokenDelta] = []
        for delta in record.deltas:
            if delta.new_tokens is None:
                continue
            undo_deltas.append(TokenDelta(
                start=delta.start,
                old_tokens=list(delta.old_tokens),
                new_tokens=list(delta.new_tokens),
            ))
        undo_record = UndoRecord(
            deltas=undo_deltas,
            kind=record.kind,
            label=record.label,
            timestamp=record.timestamp,
            selection_before=record.selection_before,
            selection_after=record.selection_after,
            sealed=True,
        )
        self._done.append(undo_record)
        self._selection = None
        self.rev += 1
        return True

    def can_undo(self) -> bool:
        """Whether there is at least one record available to undo."""
        return bool(self._done) or self._open_group is not None

    def can_redo(self) -> bool:
        """Whether there is at least one record available to redo."""
        return bool(self._undone)

    # ---------------------------------------------------------------------------
    # Explicit boundary API -- multi-delta group as one undo step
    # ---------------------------------------------------------------------------

    def commit_start(self, label: str, kind: EditKind = EditKind.STRUCTURAL) -> None:
        """Open a multi-delta group. Mutations between start/end land in one record.

        Nested-safe: calling commit_start while a group is already open is a no-op
        (the outer bracket wins).
        """
        if self._open_group is not None:
            return
        self._open_group = UndoRecord(
            deltas=[],
            kind=kind,
            label=label,
            timestamp=time.monotonic(),
            selection_before=self._selection,
            selection_after=None,
            sealed=False,
        )

    def commit_end(self) -> None:
        """Seal the open group, push to done, clear undone, bump rev.

        If no group is open, this is a no-op. If the open group received zero
        deltas (the bracketed code did not mutate the buffer), the empty record
        is dropped rather than pushed -- nothing to undo.
        """
        if self._open_group is None:
            return
        group = self._open_group
        self._open_group = None
        group.selection_after = self._selection
        group.sealed = True
        if not group.deltas:
            return
        self._done.append(group)
        # _record already bumped rev + cleared _undone for each delta inside
        # the group, so commit_end itself is purely structural.

    # ---------------------------------------------------------------------------
    # Selection tracking
    # ---------------------------------------------------------------------------

    def set_selection(self, start: int, end: int):
        """Set selection span to [start, end] (inclusive token indices)."""
        self._selection = (start, end)

    def clear_selection(self):
        """Clear the current selection."""
        self._selection = None

    def get_selection(self) -> tuple[int, int] | None:
        """Return current selection as (start, end) or None."""
        return self._selection

    # ---------------------------------------------------------------------------
    # Internal: delta recording with CM6-style coalescing
    # ---------------------------------------------------------------------------

    def _record(self, delta: TokenDelta, kind: EditKind, label: str) -> None:
        """Append delta to open group, or open + close a new group.

        Honors CM6-style time+adjacency coalescing when _GROUP_DELAY_S > 0.
        Always clears _undone (CM6 linear-redo rule). Bumps rev.
        """
        now = time.monotonic()

        # Inside an open commit_start/commit_end group: append, with cap split.
        if self._open_group is not None:
            if len(self._open_group.deltas) >= self._MAX_COMPOSED_DELTAS:
                # Cap reached. Close the current group and open a fresh one with
                # the same kind/label so the bracket stays semantically intact.
                self._open_group.sealed = True
                self._open_group.selection_after = self._selection
                self._done.append(self._open_group)
                self._open_group = UndoRecord(
                    deltas=[delta],
                    kind=self._open_group.kind,
                    label=self._open_group.label,
                    timestamp=now,
                    selection_before=self._selection,
                    selection_after=None,
                )
            else:
                self._open_group.deltas.append(delta)
            self._undone.clear()
            self.rev += 1
            return

        # Outside any bracket: maybe coalesce into the previous record.
        merged = False
        if (
            _GROUP_DELAY_S > 0.0
            and self._done
            and not self._done[-1].sealed
            and self._done[-1].kind == EditKind.DICTATION
            and kind == EditKind.DICTATION
            and (now - self._done[-1].timestamp) < _GROUP_DELAY_S
            and len(self._done[-1].deltas) < self._MAX_COMPOSED_DELTAS
            and self._touches_previous(self._done[-1], delta)
        ):
            self._done[-1].deltas.append(delta)
            self._done[-1].timestamp = now
            self._done[-1].selection_after = self._selection
            merged = True

        if not merged:
            record = UndoRecord(
                deltas=[delta],
                kind=kind,
                label=label,
                timestamp=now,
                selection_before=self._selection,
                selection_after=self._selection,
                sealed=False,
            )
            self._done.append(record)

        self._undone.clear()
        self.rev += 1

    def _touches_previous(self, prev: UndoRecord, new_delta: TokenDelta) -> bool:
        """CM6 adjacency rule: new delta's start touches the previous delta's range.

        For token-grained edits, "touches" means the new delta begins at or
        one past the end of the previous delta's affected forward range.
        """
        if not prev.deltas:
            return False
        last = prev.deltas[-1]
        if last.new_tokens is None:
            return False
        last_end = last.start + len(last.new_tokens)
        return last.start <= new_delta.start <= last_end

    # ---------------------------------------------------------------------------
    # Mutations -- each builds a TokenDelta and routes through _record
    # ---------------------------------------------------------------------------

    def add_text(self, text: str):
        """Split text on whitespace and append each word as a token.

        Trailing punctuation is split off each word into its own token,
        e.g. "hello world." -> ["hello", "world", "."].
        """
        self._selection = None
        words = text.strip().split()
        split_tokens: list[str] = []
        for word in words:
            if word:
                split_tokens.extend(self._split_trailing_punct(word))
        if not split_tokens:
            return
        start = len(self._tokens)
        delta = TokenDelta(start=start, old_tokens=[], new_tokens=list(split_tokens))
        self._tokens.extend(split_tokens)
        self._record(delta, EditKind.DICTATION, "add_text")

    def delete_token(self, index: int):
        """Delete the token at the given index. No-op if out of range."""
        if 0 <= index < len(self._tokens):
            self._selection = None
            old = [self._tokens[index]]
            delta = TokenDelta(start=index, old_tokens=old, new_tokens=[])
            self._tokens.pop(index)
            self._record(delta, EditKind.EXPLICIT, "delete_token")

    def delete_through(self, index: int):
        """Delete from the end back through and including the token at index.

        Removes tokens from index to the end inclusive, leaving only tokens
        before the given index. Semantics: "chuck tail <hat>" removes the
        hat's word and everything after it.
        """
        if 0 <= index < len(self._tokens):
            self._selection = None
            old = list(self._tokens[index:])
            delta = TokenDelta(start=index, old_tokens=old, new_tokens=[])
            self._tokens = self._tokens[:index]
            self._record(delta, EditKind.EXPLICIT, "delete_through")

    def delete_head(self, index: int):
        """Delete from the start through and including the token at index.

        Removes tokens 0..index inclusive, leaving only tokens after index.
        Semantics: "chuck head <hat>" removes everything up to and including
        the hat's word.
        """
        if 0 <= index < len(self._tokens):
            self._selection = None
            old = list(self._tokens[:index + 1])
            delta = TokenDelta(start=0, old_tokens=old, new_tokens=[])
            self._tokens = self._tokens[index + 1:]
            self._record(delta, EditKind.EXPLICIT, "delete_head")

    def replace_token(self, index: int, text: str):
        """Replace the token at index with the first word of text."""
        if 0 <= index < len(self._tokens):
            self._selection = None
            words = text.strip().split()
            if words:
                old = [self._tokens[index]]
                new = [words[0]]
                delta = TokenDelta(start=index, old_tokens=old, new_tokens=new)
                self._tokens[index] = words[0]
                self._record(delta, EditKind.EXPLICIT, "replace_token")

    def insert_at(self, index: int, text: str):
        """Insert words from text at gap index (0 = before all, N = after all)."""
        self._selection = None
        words = text.strip().split()
        if not words:
            return
        delta = TokenDelta(start=index, old_tokens=[], new_tokens=list(words))
        self._tokens[index:index] = words
        self._record(delta, EditKind.DICTATION, "insert_at")

    def get_tokens(self) -> list[str]:
        """Return a copy of the current token list."""
        return list(self._tokens)

    def get_text(self) -> str:
        """Return all tokens joined with spaces."""
        return " ".join(self._tokens)

    def set_tokens_raw(self, tokens: list[str]):
        """Overwrite token list directly.

        Behavior depends on context:
          - Inside a commit_start/commit_end bracket: records a full-buffer
            TokenDelta into the open group so the change is undoable.
          - Outside any bracket: bypasses history entirely. Callers that need
            undo support should call snapshot() first (legacy) or wrap in
            commit_start/commit_end (preferred).
        """
        new_tokens = list(tokens)
        if self._open_group is not None:
            pre = list(self._tokens)
            self._tokens = new_tokens
            self._selection = None
            delta = TokenDelta(start=0, old_tokens=pre, new_tokens=list(new_tokens))
            self._record(delta, self._open_group.kind, self._open_group.label)
            return
        self.rev += 1
        self._tokens = new_tokens
        self._selection = None

    def clear(self):
        """Remove all tokens and clear history."""
        self.rev += 1
        self._tokens.clear()
        self._done.clear()
        self._undone.clear()
        self._open_group = None
        self._selection = None

    def __len__(self) -> int:
        return len(self._tokens)

    def __bool__(self) -> bool:
        return bool(self._tokens)
