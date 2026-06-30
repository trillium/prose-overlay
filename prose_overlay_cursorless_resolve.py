"""Cursorless target resolution for the Prose Overlay.

Resolves CursorlessTarget objects (PrimitiveTarget, RangeTarget, ListTarget,
ImplicitTarget) to (start_token_idx, end_token_idx) inclusive ranges over the
prose buffer's token list.

State is injected via the module-level ``_state`` object.  prose_overlay.py
holds a reference to the same object and keeps its fields current whenever
_hat_to_token, _buffer, or _cursor change.
"""

import re

from talon import actions, settings  # noqa: F401  (actions kept for symmetry)


# ---------------------------------------------------------------------------
# Shared-state namespace
# ---------------------------------------------------------------------------

class _ResolveState:
    """Mutable state container shared with prose_overlay.py.

    prose_overlay.py imports this module, then updates these fields in the
    same places it would update its own module globals.  Because the object
    is shared by reference, changes in prose_overlay.py are immediately
    visible to the functions in this module — no circular import required.
    """
    hat_to_token: "dict[tuple[str, str], int]"
    buffer: object  # ProseBuffer — typed as object to avoid import
    cursor: "int | None"

    def __init__(self):
        self.hat_to_token = {}
        self.buffer = None
        self.cursor = None


_state = _ResolveState()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Actions the JS shim can handle.  All others (scroll, fold, etc.) are VS Code
# specific and not meaningful inside the prose overlay.
_SUPPORTED_SIMPLE_ACTIONS = frozenset({
    "remove",
    "setSelection",
    "clearAndSetSelection",
    "setSelectionBefore",
    "setSelectionAfter",
})

# Cursorless uses "default" for the no-color hat; the prose overlay uses "gray".
_CURSORLESS_TO_PROSE_COLOR = {"default": "gray"}


# Scope type values (from spoken_forms.json modifier_scope_types.csv) that
# map to the entire prose buffer, which is a flat single-line document.
_WHOLE_BUFFER_SCOPE_TYPES = frozenset({
    "document",    # spoken "file"
    "line",        # spoken "line"  — prose is single-line, so line == buffer
    "paragraph",   # spoken "block" — block-level scope maps to buffer
    "fullLine",    # spoken "full line"
})

# Scope type values that target the token nearest the cursor.
_WORD_SCOPE_TYPES = frozenset({
    "token",       # spoken "token"
    "word",        # spoken "sub"   — Cursorless "word" is a sub-word token
    "identifier",  # spoken "identifier"
    "character",   # spoken "char"
})

# Regex-based scope types: pattern is applied to the full buffer text and the
# match overlapping the cursor is returned as a token span.
_REGEX_SCOPE_PATTERNS: "dict[str, re.Pattern[str]]" = {
    "nonWhitespaceSequence": re.compile(r"\S+"),
    "url": re.compile(
        r"(http(s)?://.)?(\bwww\.)?[-a-zA-Z0-9@:%._+~#=]{2,256}"
        r"\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_+.~#?&//=]*)"
    ),
    # Tier 1 prose-level scope types
    "sentence": re.compile(r"[^.!?]*[^.!?\s][^.!?]*[.!?]*"),
    "clause": re.compile(r"[^,]*[^,\s][^,]*"),
    # surroundingPair: handled by _resolve_surrounding_pair(); regex fallback
    # kept only for the "string" scope type.
    "string": re.compile(r'"[^"]*"|\'[^\']*\''),
    "number": re.compile(r"\b\d+(?:[.,]\d+)*\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b"),
}


# ---------------------------------------------------------------------------
# Resolution helpers
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


# ---------------------------------------------------------------------------
# Surrounding-pair resolution
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
    else:
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


def _cursorless_symbol_to_token_index(decorated_symbol: dict) -> int:
    """Resolve a cursorless_decorated_symbol dict to a token index.

    Cursorless uses "default" for the no-color case; we store "gray" in the
    hat reverse map. Returns -1 if the symbol is not found.
    """
    character: str = decorated_symbol.get("character", "")
    symbol_color: str = decorated_symbol.get("symbolColor", "default")
    prose_color = _CURSORLESS_TO_PROSE_COLOR.get(symbol_color, symbol_color)
    return _state.hat_to_token.get((character.lower(), prose_color), -1)


def _resolve_mark_to_base_idx(mark, tokens) -> "int | None | str":
    """Resolve a mark dict to a base token index.

    Returns an int index, None (mark absent / unrecognized — caller continues),
    or the sentinel string "error" if a recognized mark failed to resolve.
    """
    if mark is None:
        return None
    mark_type = mark.get("type")
    if mark_type == "decoratedSymbol":
        idx = _cursorless_symbol_to_token_index(mark)
        if idx < 0:
            print(
                f"prose_overlay: decorated symbol not found in hat map: "
                f"{mark.get('character')!r} / {mark.get('symbolColor')!r}"
            )
            return "error"
        return idx
    if mark_type == "cursor":
        if _state.cursor is not None:
            return min(max(_state.cursor, 0), len(tokens) - 1)
        return len(tokens) - 1
    return None


def _cursor_fallback_idx(tokens) -> "int | None":
    """Clamp the active cursor to a valid token index, or None if no cursor."""
    if _state.cursor is None:
        return None
    return min(max(_state.cursor, 0), len(tokens) - 1)


def _apply_extend_through_start_of(tokens, base_idx, _mod) -> "tuple[int, int] | None":
    if base_idx is None:
        base_idx = _cursor_fallback_idx(tokens)
        if base_idx is None:
            print("prose_overlay: extendThroughStartOf requires an active cursor")
            return None
    return (0, base_idx)


def _apply_extend_through_end_of(tokens, base_idx, _mod) -> "tuple[int, int] | None":
    if base_idx is None:
        base_idx = _cursor_fallback_idx(tokens)
        if base_idx is None:
            print("prose_overlay: extendThroughEndOf requires an active cursor")
            return None
    return (base_idx, len(tokens) - 1)


def _apply_every_scope(tokens, _base_idx, _mod) -> "tuple[int, int] | None":
    return (0, len(tokens) - 1)


def _scope_word(tokens, base_idx, scope_type) -> "tuple[int, int] | None":
    if base_idx is not None:
        return (base_idx, base_idx)
    tok_idx = _cursor_fallback_idx(tokens)
    if tok_idx is None:
        print(f"prose_overlay: scope '{scope_type}' requires a mark or active cursor")
        return None
    return (tok_idx, tok_idx)


def _scope_surrounding_pair(tokens, base_idx, mod) -> "tuple[int, int] | None":
    if base_idx is not None:
        anchor_tok_idx = base_idx
    else:
        anchor_tok_idx = _cursor_fallback_idx(tokens)
        if anchor_tok_idx is None:
            print("prose_overlay: scope 'surroundingPair' requires a mark or active cursor")
            return None
    delimiter = mod.get("scopeType", {}).get("delimiter", "any")
    return _resolve_surrounding_pair(tokens, anchor_tok_idx, delimiter)


def _scope_regex(tokens, base_idx, scope_type) -> "tuple[int, int] | None":
    if base_idx is not None:
        anchor_char = _token_idx_to_char_offset(base_idx, tokens)
    elif _state.cursor is not None:
        anchor_char = _cursor_gap_to_char_offset(_state.cursor, tokens)
    else:
        print(f"prose_overlay: scope '{scope_type}' requires a mark or active cursor")
        return None
    text = " ".join(tokens)
    pattern = _REGEX_SCOPE_PATTERNS[scope_type]
    for m in pattern.finditer(text):
        if m.start() <= anchor_char <= m.end():
            result = _char_range_to_token_range(m.start(), m.end(), tokens)
            if result is not None:
                return result
    print(f"prose_overlay: no '{scope_type}' match at anchor position")
    return None


def _apply_containing_scope(tokens, base_idx, mod) -> "tuple[int, int] | None":
    """Handle containingScope / preferredScope by dispatching on scope type.

    Anchor precedence: when the target carries a mark (base_idx is set), the
    scope is computed around that token; otherwise fall back to the cursor.
    """
    scope_type = mod.get("scopeType", {}).get("type", "")
    if scope_type in _WHOLE_BUFFER_SCOPE_TYPES:
        return (0, len(tokens) - 1)
    if scope_type in _WORD_SCOPE_TYPES:
        return _scope_word(tokens, base_idx, scope_type)
    if scope_type == "surroundingPair":
        return _scope_surrounding_pair(tokens, base_idx, mod)
    if scope_type in _REGEX_SCOPE_PATTERNS:
        return _scope_regex(tokens, base_idx, scope_type)
    print(f"prose_overlay: unrecognized scope type '{scope_type}'")
    return None


# Dispatch table: modifier type -> handler. Unrecognized mod_types fall through
# (matches the original chained-if behavior, including the intentional skip of
# relativeScope — see CURSORLESS_REIMPLEMENTATIONS.md §2).
_MODIFIER_HANDLERS = {
    "extendThroughStartOf": _apply_extend_through_start_of,
    "extendThroughEndOf":   _apply_extend_through_end_of,
    "everyScope":           _apply_every_scope,
    "containingScope":      _apply_containing_scope,
    "preferredScope":       _apply_containing_scope,
}


def _resolve_primitive_to_token_range(target) -> "tuple[int, int] | None":
    """Resolve a PrimitiveTarget to (start_token_idx, end_token_idx) inclusive.

    Two-phase:
    1. Resolve the mark to a base token index (decoratedSymbol → hat map,
       no mark → cursor position).
    2. Apply modifiers via _MODIFIER_HANDLERS dispatch. The first handler that
       returns (i.e. matches a known mod_type) terminates the loop. Unknown
       mod_types are skipped — matching the prior chained-if behavior.

    Returns None if the target cannot be resolved, logging the reason.
    """
    tokens = _state.buffer.get_tokens()
    if not tokens:
        print("prose_overlay: buffer is empty — cannot resolve target")
        return None

    mark = target.mark
    modifiers = target.modifiers or []

    base = _resolve_mark_to_base_idx(mark, tokens)
    if base == "error":
        return None
    base_idx: "int | None" = base

    for mod in modifiers:
        handler = _MODIFIER_HANDLERS.get(mod.get("type"))
        if handler is not None:
            return handler(tokens, base_idx, mod)

    if base_idx is not None:
        return (base_idx, base_idx)

    print(
        f"prose_overlay: cannot resolve PrimitiveTarget with mark={mark!r} "
        f"and modifiers={modifiers!r}"
    )
    return None


def _resolve_target_to_token_range(target) -> "list[tuple[int, int]] | None":
    """Resolve any CursorlessTarget to a list of (start, end) inclusive ranges.

    Dispatches by target type:
    - PrimitiveTarget → single-element list from _resolve_primitive_to_token_range
    - RangeTarget     → single-element list spanning anchor..active
    - ListTarget      → list of ranges, one per element
    - ImplicitTarget  → single-element list at cursor position

    When `user.prose_overlay_use_js_resolver` is True, dispatch routes through
    the JS bundle (cursorless's actual processTargets pipeline) instead of
    the Python implementation below. On JS error the bridge raises
    RuntimeError; we log full context and return None — no silent fallback
    to the Python path (constraint 6 / Anti-3).

    Returns None if the target cannot be resolved.
    """
    if settings.get("user.prose_overlay_use_js_resolver", False):
        # Lazy import to avoid circular dependency: prose_overlay_targets_js
        # imports helpers from this module.
        from . import prose_overlay_targets_js
        try:
            return prose_overlay_targets_js.resolve_target(target)
        except RuntimeError as e:
            print(f"prose_overlay: JS resolver failed (no fallback): {e}")
            return None

    target_type = target.type  # class attribute, not instance dict

    if target_type == "primitive":
        r = _resolve_primitive_to_token_range(target)
        return [r] if r is not None else None

    if target_type == "range":
        # anchor may be ImplicitTarget (type == "implicit") when the user says
        # e.g. "chuck past bat" with no explicit anchor.
        anchor = target.anchor
        active = target.active

        if anchor.type == "implicit":
            # Implicit anchor means "from the cursor".  Convert the cursor
            # gap index to the nearest token index.
            if _state.cursor is None:
                print(
                    "prose_overlay: RangeTarget with implicit anchor requires "
                    "an active cursor"
                )
                return None
            tokens = _state.buffer.get_tokens()
            anchor_tok = max(0, _state.cursor - 1) if _state.cursor > 0 else 0
            anchor_tok = min(anchor_tok, len(tokens) - 1) if tokens else 0
            anchor_range = (anchor_tok, anchor_tok)
        else:
            anchor_range = _resolve_primitive_to_token_range(anchor)

        active_range = _resolve_primitive_to_token_range(active)

        if anchor_range is None or active_range is None:
            return None

        first = min(anchor_range[0], active_range[0])
        last = max(anchor_range[1], active_range[1])
        return [(first, last)]

    if target_type == "list":
        ranges: "list[tuple[int, int]]" = []
        for element in target.elements:
            resolved = _resolve_target_to_token_range(element)
            if resolved is None:
                return None
            ranges.extend(resolved)
        return ranges if ranges else None

    if target_type == "implicit":
        # "this" in Cursorless — resolve to the token at the cursor position.
        tokens = _state.buffer.get_tokens()
        if _state.cursor is None:
            print("prose_overlay: ImplicitTarget requires an active cursor (use pre/post <hat> first)")
            return None
        tok_idx = min(_state.cursor, len(tokens) - 1)
        if tok_idx < 0:
            tok_idx = 0
        return [(tok_idx, tok_idx)]

    print(f"prose_overlay: unknown target type '{target_type}'")
    return None
