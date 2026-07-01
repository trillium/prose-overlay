"""Cursorless target resolution: resolves CursorlessTargets to inclusive
(start_token_idx, end_token_idx) ranges over the prose buffer. State injected
via the module-level ``_state``.
"""

import re

from .surrounding_pair import (
    _char_range_to_token_range,
    _cursor_gap_to_char_offset,
    _resolve_surrounding_pair,
    _token_idx_to_char_offset,
)


class _ResolveState:
    """Mutable state container shared by reference with prose_overlay.py."""
    hat_to_token: "dict[tuple[str, str], int]"
    buffer: object
    cursor: "int | None"

    def __init__(self):
        self.hat_to_token = {}
        self.buffer = None
        self.cursor = None


_state = _ResolveState()

_SUPPORTED_SIMPLE_ACTIONS = frozenset({
    "remove", "setSelection", "clearAndSetSelection",
    "setSelectionBefore", "setSelectionAfter",
    # Wishlist #12 Clone — cursorless-talon's spoken_forms.json maps
    # `clone` → insertCopyAfter and `clone up` → insertCopyBefore. Both live
    # in the cursorless_simple_action LIST so the composable rule at
    # prose_overlay_cursorless.talon:47 dispatches them through
    # prose_overlay_run_action. Geometry lives in js/prose_actions.js —
    # see docs/BUNDLE_REST_SCOPE.md §Cluster A / §2 #12.
    "insertCopyBefore", "insertCopyAfter",
})
_CURSORLESS_TO_PROSE_COLOR = {"default": "gray"}
_WHOLE_BUFFER_SCOPE_TYPES = frozenset({"document", "line", "paragraph", "fullLine"})
_WORD_SCOPE_TYPES = frozenset({"token", "word", "identifier", "character"})
_REGEX_SCOPE_PATTERNS: "dict[str, re.Pattern[str]]" = {
    "nonWhitespaceSequence": re.compile(r"\S+"),
    "url": re.compile(
        r"(http(s)?://.)?(\bwww\.)?[-a-zA-Z0-9@:%._+~#=]{2,256}"
        r"\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_+.~#?&//=]*)"
    ),
    "sentence": re.compile(r"[^.!?]*[^.!?\s][^.!?]*[.!?]*"),
    "clause": re.compile(r"[^,]*[^,\s][^,]*"),
    "string": re.compile(r'"[^"]*"|\'[^\']*\''),
    "number": re.compile(r"\b\d+(?:[.,]\d+)*\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b"),
}


def _cursorless_symbol_to_token_index(decorated_symbol: dict) -> int:
    """Resolve a cursorless_decorated_symbol dict to a token index, or -1."""
    character: str = decorated_symbol.get("character", "")
    symbol_color: str = decorated_symbol.get("symbolColor", "default")
    prose_color = _CURSORLESS_TO_PROSE_COLOR.get(symbol_color, symbol_color)
    return _state.hat_to_token.get((character.lower(), prose_color), -1)


def _resolve_mark_to_base_idx(mark, tokens) -> "int | None | str":
    """Returns int index, None (no mark), or "error" if a known mark failed."""
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
    anchor_tok_idx = base_idx if base_idx is not None else _cursor_fallback_idx(tokens)
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
    for m in _REGEX_SCOPE_PATTERNS[scope_type].finditer(text):
        if m.start() <= anchor_char <= m.end():
            result = _char_range_to_token_range(m.start(), m.end(), tokens)
            if result is not None:
                return result
    print(f"prose_overlay: no '{scope_type}' match at anchor position")
    return None


def _apply_containing_scope(tokens, base_idx, mod) -> "tuple[int, int] | None":
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


# Unknown mod_types fall through (relativeScope deferred to JS — see
# CURSORLESS_REIMPLEMENTATIONS.md §2).
_MODIFIER_HANDLERS = {
    "extendThroughStartOf": _apply_extend_through_start_of,
    "extendThroughEndOf":   _apply_extend_through_end_of,
    "everyScope":           _apply_every_scope,
    "containingScope":      _apply_containing_scope,
    "preferredScope":       _apply_containing_scope,
}


def _resolve_primitive_to_token_range(target) -> "tuple[int, int] | None":
    """Resolve mark → base_idx, then dispatch the first known modifier."""
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


def _resolve_range_target(target) -> "list[tuple[int, int]] | None":
    anchor = target.anchor
    if anchor.type == "implicit":
        if _state.cursor is None:
            print("prose_overlay: RangeTarget with implicit anchor requires an active cursor")
            return None
        tokens = _state.buffer.get_tokens()
        anchor_tok = max(0, _state.cursor - 1) if _state.cursor > 0 else 0
        anchor_tok = min(anchor_tok, len(tokens) - 1) if tokens else 0
        anchor_range = (anchor_tok, anchor_tok)
    else:
        anchor_range = _resolve_primitive_to_token_range(anchor)
    active_range = _resolve_primitive_to_token_range(target.active)
    if anchor_range is None or active_range is None:
        return None
    return [(min(anchor_range[0], active_range[0]), max(anchor_range[1], active_range[1]))]


def _resolve_implicit_target() -> "list[tuple[int, int]] | None":
    tokens = _state.buffer.get_tokens()
    if _state.cursor is None:
        print("prose_overlay: ImplicitTarget requires an active cursor (use pre/post <hat> first)")
        return None
    tok_idx = min(_state.cursor, len(tokens) - 1)
    return [(max(tok_idx, 0), max(tok_idx, 0))]


def _resolve_target_to_token_range(target) -> "list[tuple[int, int]] | None":
    """Dispatch any CursorlessTarget; routes through the JS bundle when enabled."""
    from talon import settings  # lazy: keeps top-level CURSORLESS layer talon-free
    if settings.get("user.prose_overlay_use_js_resolver", False):
        from ..shim import targets_js as prose_overlay_targets_js  # lazy: avoids circular dep
        try:
            return prose_overlay_targets_js.resolve_target(target)
        except RuntimeError as e:
            print(f"prose_overlay: JS resolver failed (no fallback): {e}")
            return None
    target_type = target.type
    if target_type == "primitive":
        r = _resolve_primitive_to_token_range(target)
        return [r] if r is not None else None
    if target_type == "range":
        return _resolve_range_target(target)
    if target_type == "implicit":
        return _resolve_implicit_target()
    if target_type == "list":
        ranges: "list[tuple[int, int]]" = []
        for element in target.elements:
            resolved = _resolve_target_to_token_range(element)
            if resolved is None:
                return None
            ranges.extend(resolved)
        return ranges if ranges else None
    print(f"prose_overlay: unknown target type '{target_type}'")
    return None
