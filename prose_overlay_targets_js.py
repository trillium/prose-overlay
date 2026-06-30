"""Prose Overlay JS Target Resolver.

Loads prose_resolve_targets.js (cursorless's processTargets pipeline bundled
via esbuild) into Talon's embedded QuickJS engine and exposes resolve_target()
returning the same list[tuple[int, int]] shape as the Python resolver.

Gated by `user.prose_overlay_use_js_resolver` setting. When the flag is on,
`prose_overlay_cursorless_resolve._resolve_target_to_token_range` routes
here. On any JS error (parse fail, no targets, bundle exception), this
module raises RuntimeError — no silent fallback to the Python resolver
(constraint 6 / Anti-3).

Mirrors the JS-bridge pattern from prose_overlay_hats_js.py:
  - module-level js.Context singleton, loaded once
  - JSON-in / JSON-out to avoid Python<->JS coercion overhead
  - bundle exposes a single global function on globalThis
"""

import json
import os

import talon.lib.js as js

from .internal.instance import instance
from .cursorless.resolve import _state
from .cursorless.surrounding_pair import (
    _char_range_to_token_range,
    _cursor_gap_to_char_offset,
)
from .internal import trail as _trail


# ---------------------------------------------------------------------------
# Module-level JS context — created once, reused across calls
# ---------------------------------------------------------------------------

_JS_BUNDLE = os.path.join(os.path.dirname(__file__), "js", "prose_resolve_targets.js")

_ctx: "js.Context | None" = None
_fn = None  # js.Object — globalThis.proseResolveTarget


def _ensure_loaded() -> None:
    global _ctx, _fn
    if _ctx is not None:
        return
    _ctx = js.Context()
    with open(_JS_BUNDLE) as f:
        _ctx.eval(f.read())
    _fn = _ctx.globals.proseResolveTarget


# ---------------------------------------------------------------------------
# Color normalization
# ---------------------------------------------------------------------------

# Prose overlay uses "gray" for the no-color hat; Cursorless uses "default".
# Hat-map entries and decoratedSymbol marks both flow through this map.
_PROSE_TO_CURSORLESS_COLOR = {"gray": "default"}


def _to_cursorless_color(prose_color: str) -> str:
    return _PROSE_TO_CURSORLESS_COLOR.get(prose_color, prose_color)


# ---------------------------------------------------------------------------
# Talon capture → JSON
# ---------------------------------------------------------------------------

def _normalize_mark(mark) -> dict | None:
    """Normalize prose-side mark colors into cursorless-side names.

    Recurses through `range` marks so nested anchor/active decoratedSymbol
    colors also get normalized. Returns a fresh dict — does not mutate input.
    """
    if mark is None:
        return None
    m = dict(mark)
    mtype = m.get("type")
    if mtype == "decoratedSymbol":
        m["symbolColor"] = _to_cursorless_color(m.get("symbolColor", "default"))
    elif mtype == "range":
        m["anchor"] = _normalize_mark(m.get("anchor"))
        m["active"] = _normalize_mark(m.get("active"))
    return m


def _target_to_json(target) -> dict:
    """Walk a Talon CursorlessTarget capture into a JSON-serializable dict.

    Recurses through range / list shapes. Normalizes decoratedSymbol colors
    from prose ("gray") to cursorless ("default") so the bundle's hat lookup
    matches — including nested marks inside a top-level range mark.
    """
    t_type = target.type

    if t_type == "primitive":
        # Cursorless's TargetPipelineRunner expects mark.type to be defined.
        # It accepts the partial-descriptor form ONLY through its inference
        # layer; we're feeding the final form, where mark is required. When
        # no spoken mark is given (e.g. "every token"), cursorless's grammar
        # injects an implicit cursor mark — we mirror that here.
        normalized = _normalize_mark(target.mark) or {"type": "cursor"}
        return {
            "type": "primitive",
            "mark": normalized,
            "modifiers": [dict(m) for m in (target.modifiers or [])],
        }

    if t_type == "range":
        return {
            "type": "range",
            "anchor": _target_to_json(target.anchor),
            "active": _target_to_json(target.active),
            "excludeAnchor": bool(getattr(target, "excludeAnchor", False)),
            "excludeActive": bool(getattr(target, "excludeActive", False)),
            "rangeType": getattr(target, "rangeType", "continuous"),
        }

    if t_type == "list":
        return {
            "type": "list",
            "elements": [_target_to_json(el) for el in target.elements],
        }

    if t_type == "implicit":
        return {"type": "implicit"}

    raise ValueError(f"unknown target type: {t_type!r}")


def _token_start_offset(token_idx: int, tokens: "list[str]") -> int:
    """Return the start char offset of tokens[token_idx] in ' '.join(tokens)."""
    pos = 0
    for i in range(token_idx):
        pos += len(tokens[i]) + 1  # +1 for the space separator
    return pos


def _build_document_json(tokens: "list[str]", cursor: "int | None") -> str:
    text = " ".join(tokens)
    char = 0 if cursor is None else _cursor_gap_to_char_offset(cursor, tokens)
    return json.dumps({
        "text": text,
        "cursorAnchorChar": char,
        "cursorActiveChar": char,
    })


def _build_hat_map_json(tokens: "list[str]", hat_assignments: dict) -> str:
    """Build {entries: [{color, grapheme, startCol, endCol, text}]} for the bundle.

    Each entry covers one hatted token: startCol/endCol delimit the token's
    span in " ".join(tokens). Color is normalized to cursorless's vocabulary.
    """
    entries = []
    for token_idx, (_, letter, color) in hat_assignments.items():
        if token_idx >= len(tokens):
            continue
        token = tokens[token_idx]
        start = _token_start_offset(token_idx, tokens)
        entries.append({
            "color": _to_cursorless_color(color),
            "grapheme": letter,
            "startCol": start,
            "endCol": start + len(token),
            "text": token,
        })
    return json.dumps({"entries": entries})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_target(target) -> "list[tuple[int, int]]":
    """Resolve a Talon CursorlessTarget via the JS pipeline.

    Returns list[(first_token_idx, last_token_idx)] inclusive, matching the
    Python resolver's shape. Raises RuntimeError on any JS-side failure with
    the target + buffer + error string embedded for diagnosis — caller MUST
    NOT silently fall back to the Python resolver (constraint 6 / Anti-3).
    """
    _ensure_loaded()

    buffer = _state.buffer or instance.buffer
    tokens = list(buffer.get_tokens()) if buffer is not None else []
    if not tokens:
        raise RuntimeError("prose overlay buffer is empty; cannot resolve target")

    target_dict = _target_to_json(target)
    target_json = json.dumps(target_dict)
    doc_json = _build_document_json(tokens, _state.cursor)
    hat_map_json = _build_hat_map_json(tokens, instance.hat_assignments)
    cursor_json = json.dumps({
        "gap": _state.cursor if _state.cursor is not None else -1,
    })

    # Wrapped in begin_command/end_command (paper-trail slice B) so the
    # preamble is on disk before the risky JS call fires.
    corr_id = _trail.begin_command("", "resolve_target", {"n_tokens": len(tokens)})
    try:
        # Bundle returns the result JSON string directly. Crossing JS->Python
        # via NewProxy blows QuickJS's call stack (see prose_overlay_hats_js
        # 2026-05-21), so the bundle uses the return-string pattern.
        result_json: str = str(_fn(target_json, doc_json, hat_map_json, cursor_json))
        _trail.end_command(corr_id, ok=True)
    except Exception as e:
        _trail.end_command(corr_id, ok=False, err=repr(e))
        raise RuntimeError(
            f"prose JS resolver call raised: target={target_json} "
            f"buffer={tokens!r} error={e!r}"
        ) from e

    try:
        result = json.loads(result_json)
    except Exception as e:
        raise RuntimeError(
            f"prose JS resolver returned non-JSON: target={target_json} "
            f"buffer={tokens!r} raw={result_json!r}"
        ) from e

    if "error" in result:
        raise RuntimeError(
            f"prose JS resolver error: target={target_json} "
            f"buffer={tokens!r} error={result['error']!r}"
        )

    content_ranges = result.get("contentRanges") or []
    if not content_ranges:
        raise RuntimeError(
            f"prose JS resolver returned no contentRanges: "
            f"target={target_json} buffer={tokens!r}"
        )

    out: "list[tuple[int, int]]" = []
    for r in content_ranges:
        char_start = r["start"]["character"]
        char_end = r["end"]["character"]
        # bundle returns end.character exclusive (cursorless Range semantics);
        # _char_range_to_token_range also treats char_end as exclusive.
        tok_range = _char_range_to_token_range(char_start, char_end, tokens)
        if tok_range is None:
            raise RuntimeError(
                f"prose JS resolver returned a range with no token overlap: "
                f"target={target_json} range=[{char_start},{char_end}) "
                f"buffer={tokens!r}"
            )
        out.append(tok_range)
    return out
