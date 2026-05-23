"""Prose Overlay State -- word token buffer for dictation capture.

Pure state management with no Talon dependencies. The buffer stores
individual word tokens and supports indexed deletion for hat-targeted editing.

Hat allocation: assigns a unique (letter, color) pair to each visible token so
that spoken hat names (air/bat/cap/..., optionally prefixed with a color) unambiguously
identify words. Matches Cursorless collision resolution: same letter, different color.
"""

# Color priority order: gray is default (no prefix spoken), then colors in order.
# When two tokens share the same best letter, the second gets the next available color.
HAT_COLOR_PRIORITY = ["gray", "blue", "green", "red", "pink", "yellow", "purple", "black", "white"]


def compute_hat_assignments(
    tokens: list[str],
    cursor_pos: int | None = None,
) -> dict[int, tuple[int, str, str]]:
    """Assign a unique (letter, color) pair to each token for hat identification.

    Returns a mapping of token_index -> (char_index_within_word, letter, color)
    where letter is the lowercase grapheme and color is the hat color name.

    cursor_pos: gap index (0 = before all tokens, N = after all tokens).
    Tokens closest to the cursor get first pick of the best hats. Defaults to
    len(tokens) (end of buffer) when None, matching the writing position.

    Algorithm (Cursorless-style color collision resolution):
    1. Process tokens in proximity order from cursor (closest first).
    2. For each token, iterate its letters left to right.
    3. For each letter, try colors in HAT_COLOR_PRIORITY order.
    4. Assign the first (letter, color) combo not already claimed.
    5. If all combos for all letters are exhausted, the token gets no hat.

    This means two tokens can share the same letter but get different colors,
    matching how Cursorless resolves collisions. "air" = gray-a, "blue air" = blue-a.
    """
    effective_cursor = cursor_pos if cursor_pos is not None else len(tokens)

    def _dist(i: int) -> int:
        return (effective_cursor - i - 1) if i < effective_cursor else (i - effective_cursor)

    priority_order = sorted(range(len(tokens)), key=_dist)

    claimed: set[tuple[str, str]] = set()
    assignments: dict[int, tuple[int, str, str]] = {}

    for token_idx in priority_order:
        token = tokens[token_idx]
        # Build the ordered list of (char_idx, letter) for this token
        candidates = [
            (ci, ch.lower())
            for ci, ch in enumerate(token)
            if ch.lower().isalpha()
        ]
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


class ProseBuffer:
    """Manages a list of word tokens captured from dictation."""

    _HISTORY_MAX = 20

    def __init__(self):
        self._tokens: list[str] = []
        self._history: list[list[str]] = []
        self._selection: tuple[int, int] | None = None  # (start_idx, end_idx) inclusive

    # ---------------------------------------------------------------------------
    # Undo stack
    # ---------------------------------------------------------------------------

    def snapshot(self):
        """Save current state to undo stack (call before any mutation)."""
        self._history.append(list(self._tokens))
        if len(self._history) > self._HISTORY_MAX:
            self._history.pop(0)

    def undo(self) -> bool:
        """Restore previous state. Returns True if undo was available."""
        if not self._history:
            return False
        self._tokens = self._history.pop()
        self._selection = None
        return True

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
    # Mutations (each calls snapshot() first, then clears selection)
    # ---------------------------------------------------------------------------

    def add_text(self, text: str):
        """Split text on whitespace and append each word as a token."""
        self.snapshot()
        self._selection = None
        words = text.strip().split()
        self._tokens.extend(words)

    def delete_token(self, index: int):
        """Delete the token at the given index. No-op if out of range."""
        if 0 <= index < len(self._tokens):
            self.snapshot()
            self._selection = None
            self._tokens.pop(index)

    def delete_through(self, index: int):
        """Delete from the end back through and including the token at index.

        Removes tokens from index to the end inclusive, leaving only tokens
        before the given index. Semantics: "chuck tail <hat>" removes the
        hat's word and everything after it.
        """
        if 0 <= index < len(self._tokens):
            self.snapshot()
            self._selection = None
            self._tokens = self._tokens[:index]

    def delete_head(self, index: int):
        """Delete from the start through and including the token at index.

        Removes tokens 0..index inclusive, leaving only tokens after index.
        Semantics: "chuck head <hat>" removes everything up to and including
        the hat's word.
        """
        if 0 <= index < len(self._tokens):
            self.snapshot()
            self._selection = None
            self._tokens = self._tokens[index + 1:]

    def replace_token(self, index: int, text: str):
        """Replace the token at index with the first word of text."""
        if 0 <= index < len(self._tokens):
            self.snapshot()
            self._selection = None
            words = text.strip().split()
            if words:
                self._tokens[index] = words[0]

    def insert_at(self, index: int, text: str):
        """Insert words from text at gap index (0 = before all, N = after all)."""
        self.snapshot()
        self._selection = None
        words = text.strip().split()
        self._tokens[index:index] = words

    def get_tokens(self) -> list[str]:
        """Return a copy of the current token list."""
        return list(self._tokens)

    def get_text(self) -> str:
        """Return all tokens joined with spaces."""
        return " ".join(self._tokens)

    def set_tokens_raw(self, tokens: list[str]):
        """Overwrite token list directly without snapshotting or clearing history.

        Used by _apply_edit_plan, which takes a manual snapshot before calling this.
        """
        self._tokens = list(tokens)
        self._selection = None

    def clear(self):
        """Remove all tokens."""
        self._tokens.clear()
        self._history.clear()
        self._selection = None

    def __len__(self) -> int:
        return len(self._tokens)

    def __bool__(self) -> bool:
        return bool(self._tokens)
