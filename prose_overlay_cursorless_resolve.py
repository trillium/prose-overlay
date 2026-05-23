"""Cursorless target resolution for the Prose Overlay.

Resolves CursorlessTarget objects (PrimitiveTarget, RangeTarget, ListTarget,
ImplicitTarget) to (start_token_idx, end_token_idx) inclusive ranges over the
prose buffer's token list.

State is injected via the module-level ``_state`` object.  prose_overlay.py
holds a reference to the same object and keeps its fields current whenever
_hat_to_token, _buffer, or _cursor change.
"""

from talon import actions  # noqa: F401  (available for future use; kept for symmetry)


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


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------

def _cursorless_symbol_to_token_index(decorated_symbol: dict) -> int:
    """Resolve a cursorless_decorated_symbol dict to a token index.

    Cursorless uses "default" for the no-color case; we store "gray" in the
    hat reverse map. Returns -1 if the symbol is not found.
    """
    character: str = decorated_symbol.get("character", "")
    symbol_color: str = decorated_symbol.get("symbolColor", "default")
    prose_color = _CURSORLESS_TO_PROSE_COLOR.get(symbol_color, symbol_color)
    return _state.hat_to_token.get((character.lower(), prose_color), -1)


def _resolve_primitive_to_token_range(target) -> "tuple[int, int] | None":
    """Resolve a PrimitiveTarget to (start_token_idx, end_token_idx) inclusive.

    Two-phase:
    1. Resolve the mark to a base token index (decoratedSymbol → hat map,
       no mark → cursor position).
    2. Apply modifiers to the base index to compute the final range:
       - extendThroughStartOf ("head"): (0, base_idx)
       - extendThroughEndOf  ("tail"): (base_idx, len-1)
       - containingScope/everyScope: whole-buffer or cursor-token range
       - no modifier: (base_idx, base_idx)

    Returns None if the target cannot be resolved, logging the reason.
    """
    tokens = _state.buffer.get_tokens()
    if not tokens:
        print("prose_overlay: buffer is empty — cannot resolve target")
        return None

    mark = target.mark  # dict or None
    modifiers = target.modifiers or []  # list of dicts

    # --- Step 1: resolve mark to base token index ------------------------------
    base_idx: "int | None" = None

    if mark is not None:
        mark_type = mark.get("type")
        if mark_type == "decoratedSymbol":
            idx = _cursorless_symbol_to_token_index(mark)
            if idx < 0:
                print(
                    f"prose_overlay: decorated symbol not found in hat map: "
                    f"{mark.get('character')!r} / {mark.get('symbolColor')!r}"
                )
                return None
            base_idx = idx
        elif mark_type == "cursor":
            # "this" in Cursorless — currentSelection maps to cursor position.
            # If no editing cursor is set, fall back to the last token (where
            # dictation is currently appending).
            if _state.cursor is not None:
                base_idx = min(max(_state.cursor, 0), len(tokens) - 1)
            else:
                base_idx = len(tokens) - 1
    # If mark is None (or unrecognized), base_idx stays None; modifiers may supply the range.

    # --- Step 2: apply modifiers -----------------------------------------------
    for mod in modifiers:
        mod_type = mod.get("type")

        # "chuck head <hat>" / "chuck head this" — from start through base token
        if mod_type == "extendThroughStartOf":
            if base_idx is None:
                if _state.cursor is None:
                    print("prose_overlay: extendThroughStartOf requires an active cursor")
                    return None
                base_idx = min(max(_state.cursor, 0), len(tokens) - 1)
            return (0, base_idx)

        # "chuck tail <hat>" / "chuck tail this" — from base token through end
        if mod_type == "extendThroughEndOf":
            if base_idx is None:
                if _state.cursor is None:
                    print("prose_overlay: extendThroughEndOf requires an active cursor")
                    return None
                base_idx = min(max(_state.cursor, 0), len(tokens) - 1)
            return (base_idx, len(tokens) - 1)

        # everyScope — "each <scope>" always means the entire buffer in a
        # single-line prose context. Ignore scope type; return full range.
        if mod_type == "everyScope":
            return (0, len(tokens) - 1)

        # containingScope / preferredScope — scope at the cursor position
        if mod_type in ("containingScope", "preferredScope"):
            scope_type = mod.get("scopeType", {}).get("type", "")
            if scope_type in _WHOLE_BUFFER_SCOPE_TYPES:
                return (0, len(tokens) - 1)
            if scope_type in _WORD_SCOPE_TYPES:
                if _state.cursor is None:
                    print(
                        f"prose_overlay: scope '{scope_type}' requires an active cursor"
                    )
                    return None
                tok_idx = min(max(_state.cursor, 0), len(tokens) - 1)
                return (tok_idx, tok_idx)
            print(f"prose_overlay: unrecognized scope type '{scope_type}'")
            return None

    # --- Step 3: no modifiers — return base index as single-token range --------
    if base_idx is not None:
        return (base_idx, base_idx)

    print(
        f"prose_overlay: cannot resolve PrimitiveTarget with mark={mark!r} "
        f"and modifiers={modifiers!r}"
    )
    return None


def _resolve_target_to_token_range(target) -> "tuple[int, int] | None":
    """Resolve any CursorlessTarget to (start_token_idx, end_token_idx) inclusive.

    Dispatches by target type:
    - PrimitiveTarget → _resolve_primitive_to_token_range
    - RangeTarget     → resolve anchor + active, return spanning range
    - ListTarget      → not supported (log and return None)
    - ImplicitTarget  → not supported (log and return None)

    Returns None if the target cannot be resolved.
    """
    target_type = target.type  # class attribute, not instance dict

    if target_type == "primitive":
        return _resolve_primitive_to_token_range(target)

    if target_type == "range":
        # anchor may be ImplicitTarget (type == "implicit") when the user says
        # e.g. "chuck past bat" with no explicit anchor.
        anchor = target.anchor
        active = target.active

        if anchor.type == "implicit":
            print(
                "prose_overlay: RangeTarget with implicit anchor is not supported"
            )
            return None

        anchor_range = _resolve_primitive_to_token_range(anchor)
        active_range = _resolve_primitive_to_token_range(active)

        if anchor_range is None or active_range is None:
            return None

        first = min(anchor_range[0], active_range[0])
        last = max(anchor_range[1], active_range[1])
        return (first, last)

    if target_type == "list":
        print(
            "prose_overlay: ListTarget (multi-target 'and' expressions) are not "
            "supported — operate on targets individually"
        )
        return None

    if target_type == "implicit":
        # "this" in Cursorless — resolve to the token at the cursor position.
        tokens = _state.buffer.get_tokens()
        if _state.cursor is None:
            print("prose_overlay: ImplicitTarget requires an active cursor (use pre/post <hat> first)")
            return None
        tok_idx = min(_state.cursor, len(tokens) - 1)
        if tok_idx < 0:
            tok_idx = 0
        return (tok_idx, tok_idx)

    print(f"prose_overlay: unknown target type '{target_type}'")
    return None
