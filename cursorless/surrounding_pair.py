"""Surrounding-pair resolution for the Prose Overlay.

Handles Cursorless's `surroundingPair` scope type: given a cursor position and
a delimiter name, returns the inclusive (first_tok, last_tok) range of the
innermost enclosing pair. Also exposes the low-level char-range/cursor-gap
helpers that the broader resolver depends on.
"""


# ---------------------------------------------------------------------------
# Delimiter table
# ---------------------------------------------------------------------------

DELIMITER_PAIRS = {
    "round":   ("(", ")"),
    "box":     ("[", "]"),
    "curly":   ("{", "}"),
    "diamond": ("<", ">"),
    "quad":    ('"', '"'),
    "twin":    ("'", "'"),
    "skis":    ("`", "`"),
}

# Delimiters where the open and close characters are identical.
_SYMMETRIC_DELIMITERS = frozenset({"quad", "twin", "skis"})


# ---------------------------------------------------------------------------
# Char/token offset helpers
# ---------------------------------------------------------------------------

def _char_range_to_token_range(
    char_start: int, char_end: int, tokens: "list[str]"
) -> "tuple[int, int] | None":
    """Convert a character range in space-joined text to (first_token, last_token).

    char_start and char_end are offsets into ``" ".join(tokens)``.
    Returns the inclusive token index range covering those characters,
    or None if the range doesn't overlap any token.
    """
    pos = 0
    first_tok: "int | None" = None
    last_tok: "int | None" = None
    for i, tok in enumerate(tokens):
        tok_end = pos + len(tok)
        # Token occupies [pos, tok_end) in the joined string.
        if tok_end > char_start and pos < char_end:
            if first_tok is None:
                first_tok = i
            last_tok = i
        pos = tok_end + 1  # +1 for space separator
    if first_tok is not None and last_tok is not None:
        return (first_tok, last_tok)
    return None


def _cursor_gap_to_char_offset(cursor: int, tokens: "list[str]") -> int:
    """Convert a cursor gap index to a character offset in ``" ".join(tokens)``."""
    offset = 0
    for i in range(min(cursor, len(tokens))):
        offset += len(tokens[i])
        if i < len(tokens) - 1:
            offset += 1  # space separator
    return offset


def _token_idx_to_char_offset(tok_idx: int, tokens: "list[str]") -> int:
    """Return a char offset pointing *inside* tokens[tok_idx].

    Used as a scope anchor when the target carries a mark: the mark resolves
    to a token, and downstream regex / pair lookups need a character position
    that overlaps that token's span in the joined buffer text.
    """
    start = sum(len(tokens[i]) + 1 for i in range(tok_idx))  # +1 for spaces
    # Point at the middle of the token so boundary characters don't cause
    # regex inclusive-end checks to miss.
    return start + max(0, len(tokens[tok_idx]) // 2)


# ---------------------------------------------------------------------------
# Surrounding-pair resolver
# ---------------------------------------------------------------------------

def _resolve_surrounding_pair(
    tokens: "list[str]",
    cursor: int,
    delimiter: str,
) -> "tuple[int, int] | None":
    """Find the innermost surrounding pair that contains the cursor.

    For asymmetric delimiters (round, box, curly, diamond): uses a stack to
    find the correctly nested open/close pair enclosing the cursor.

    For symmetric delimiters (quad, twin, skis): scans left for the nearest
    opening occurrence and right for the nearest closing occurrence.

    If *delimiter* is ``"any"`` or ``"pair"``, tries all delimiter types and
    returns the tightest (smallest span) match.

    Returns ``(first_token_idx, last_token_idx)`` inclusive, or ``None``.
    """
    text = " ".join(tokens)
    cursor_char = _cursor_gap_to_char_offset(cursor, tokens)

    if delimiter in ("any", "pair"):
        best: "tuple[int, int] | None" = None
        best_span = len(text) + 1
        for name in DELIMITER_PAIRS:
            result = _resolve_surrounding_pair(tokens, cursor, name)
            if result is not None:
                span = result[1] - result[0]
                if span < best_span:
                    best = result
                    best_span = span
        return best

    pair = DELIMITER_PAIRS.get(delimiter)
    if pair is None:
        print(f"prose_overlay: unknown delimiter '{delimiter}'")
        return None

    open_ch, close_ch = pair

    if delimiter in _SYMMETRIC_DELIMITERS:
        # Symmetric: find the nearest occurrence to the left (inclusive) and
        # to the right (inclusive) of cursor_char.
        left = text.rfind(open_ch, 0, cursor_char + 1)
        if left == -1:
            return None
        right = text.find(close_ch, max(cursor_char, left + 1))
        if right == -1:
            return None
        return _char_range_to_token_range(left, right + 1, tokens)

    # Asymmetric: stack-based matching.
    # Collect all matching pairs with proper nesting, then find the
    # tightest one containing cursor_char.
    pairs: "list[tuple[int, int]]" = []
    stack: "list[int]" = []
    for i, ch in enumerate(text):
        if ch == open_ch:
            stack.append(i)
        elif ch == close_ch and stack:
            start = stack.pop()
            pairs.append((start, i))

    # Find the tightest pair enclosing the cursor.
    best_pair: "tuple[int, int] | None" = None
    best_span_size = len(text) + 1
    for start, end in pairs:
        if start <= cursor_char <= end:
            span_size = end - start
            if span_size < best_span_size:
                best_pair = (start, end)
                best_span_size = span_size

    if best_pair is None:
        return None
    return _char_range_to_token_range(best_pair[0], best_pair[1] + 1, tokens)
