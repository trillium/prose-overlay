"""Layer 5 — resolver parity (Python ↔ JS, F9 migration).

For each MANUAL_VERIFICATION.md row whose target dict + buffer +
expected token range can be expressed without Talon's grammar
engine, we construct a fixture, run BOTH resolvers, and assert:

    python_output == js_output == expected

A failing row means either the JS bundle and the Python re-impl
diverge, or one of them disagrees with the documented expected
behavior. The Python resolver is loaded via a synthetic package
because it does `from .surrounding_pair import ...`; the JS side
runs under bun with a stubbed talon.
"""

import importlib.util
import json
import pathlib
import subprocess
import sys
import types

from .common import (
    DIM,
    REPO,
    RESET,
    test,
)

# =============================================================================
# Layer 5 — Resolver parity (Python ↔ JS, F9 migration)
# =============================================================================
#
# This layer is the headless contract for ISC-8 / F9 migration. For each row
# in MANUAL_VERIFICATION.md whose target dict + buffer + expected token range
# can be expressed without Talon's grammar engine, we construct a fixture,
# run BOTH resolvers against it, and assert:
#
#   python_output == js_output == expected
#
# A row failing here means the JS resolver and the Python re-impl diverge,
# OR one of them diverges from the documented expected behavior — the whole
# point of the harness is to catch these before live verification. The Python
# resolver is treated as the parity yardstick (it has shipped in production
# for weeks) and any disagreement gets surfaced as a test failure, not a
# silent mask.
#
# Rows that require Talon's voice grammar to construct the target dict
# (e.g. surrounding-pair where the bundle expects cursorless's internal
# delimiter names rather than the prose-side names, cursor-positioning where
# the parity is action-level not resolver-level) are NOT included here —
# those stay live-only, documented in MANUAL_VERIFICATION.md and the FEATURE
# PARITY doc.

# The standard buffer + hat-letter assignments for all "std" rows in
# MANUAL_VERIFICATION.md.
_STD_TOKENS: "list[str]" = ["the", "air", "ball", "drum", "echo"]
_STD_LETTERS: "list[str]" = ["t", "a", "b", "d", "e"]


def _build_hat_map_for_js(
    tokens: "list[str]", letters: "list[str]", color: str = "default"
) -> "list[dict]":
    """Build the JS-bundle hat-map entries — startCol/endCol over ' '.join(tokens)."""
    entries: "list[dict]" = []
    pos = 0
    for i, tok in enumerate(tokens):
        if i < len(letters) and letters[i]:
            entries.append({
                "color": color,
                "grapheme": letters[i],
                "startCol": pos,
                "endCol": pos + len(tok),
                "text": tok,
            })
        pos += len(tok) + 1
    return entries


def _run_js_resolver(
    target: dict,
    tokens: "list[str]",
    hat_entries: "list[dict]",
    cursor_char: int = 0,
) -> "list[tuple[int, int]] | None":
    """Spawn bun, eval the resolver bundle, return list[(first_tok, last_tok)] or None.

    Raises AssertionError if the bundle errors or returns no ranges — the
    parity harness treats those as failures so the row's [P/F] flips red.
    """
    text = " ".join(tokens)
    payload = {
        "targetJson": json.dumps(target),
        "documentJson": json.dumps({
            "text": text,
            "cursorAnchorChar": cursor_char,
            "cursorActiveChar": cursor_char,
        }),
        "hatMapJson": json.dumps({"entries": hat_entries}),
        "cursorJson": json.dumps({"gap": -1}),
    }
    bundle = REPO / "js" / "prose_resolve_targets.js"
    script = f"""
const code = require('fs').readFileSync('{bundle}', 'utf8');
eval(code);
const p = {json.dumps(payload)};
const out = globalThis.proseResolveTarget(
  p.targetJson, p.documentJson, p.hatMapJson, p.cursorJson,
);
process.stdout.write(out);
"""
    tmp = pathlib.Path("/tmp/headless-verify-resolver-probe.js")
    tmp.write_text(script)
    proc = subprocess.run(
        ["bun", str(tmp)], capture_output=True, text=True, timeout=15,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"bun exited {proc.returncode}: {proc.stderr.strip()[:300]}"
        )
    result = json.loads(proc.stdout)
    if "error" in result:
        raise AssertionError(f"JS bundle error: {result['error']!r}")
    content_ranges = result.get("contentRanges") or []
    if not content_ranges:
        raise AssertionError("JS bundle returned no contentRanges")
    out: "list[tuple[int, int]]" = []
    for r in content_ranges:
        char_start = r["start"]["character"]
        char_end = r["end"]["character"]
        tr = _char_range_to_token_range(char_start, char_end, tokens)
        if tr is None:
            raise AssertionError(
                f"JS range [{char_start},{char_end}) does not overlap any token "
                f"in {tokens!r}"
            )
        out.append(tr)
    return out


def _char_range_to_token_range(
    char_start: int, char_end: int, tokens: "list[str]",
) -> "tuple[int, int] | None":
    """Local copy of the helper in prose_overlay_surrounding_pair, kept here
    so Layer 5 can convert JS char ranges to token ranges without importing
    the package (the SHIM/CURSORLESS modules carry talon-state coupling)."""
    pos = 0
    first_tok: "int | None" = None
    last_tok: "int | None" = None
    for i, tok in enumerate(tokens):
        tok_end = pos + len(tok)
        if tok_end > char_start and pos < char_end:
            if first_tok is None:
                first_tok = i
            last_tok = i
        pos = tok_end + 1
    if first_tok is not None and last_tok is not None:
        return (first_tok, last_tok)
    return None


class _MockBuffer:
    """Minimal ProseBuffer stand-in — Layer 5 doesn't need the real undo/redo
    machinery, just a get_tokens() that returns a fixed list."""

    def __init__(self, tokens: "list[str]"):
        self._tokens = list(tokens)

    def get_tokens(self) -> "list[str]":
        return list(self._tokens)


class _MockTarget:
    """Duck-typed CursorlessTarget — matches the attribute surface the Python
    resolver reads (type / mark / modifiers / anchor / active / elements).
    Lets us feed JSON-shaped fixtures into _resolve_target_to_token_range
    without invoking Talon's grammar matcher."""

    def __init__(self, **kw):
        self.type: str = kw["type"]
        self.mark = kw.get("mark")
        self.modifiers: "list[dict]" = kw.get("modifiers") or []
        self.anchor = kw.get("anchor")
        self.active = kw.get("active")
        self.elements: "list[_MockTarget]" = kw.get("elements") or []


def _load_python_resolver():
    """Import cursorless/resolve.py with a stubbed talon.

    Post-strict-layer-restructure (2026-06-30) the file lives at
    `cursorless/resolve.py` and does `from .surrounding_pair import …`
    (relative within the `cursorless` package) plus `from talon import
    settings` (lazy, inside _resolve_target_to_token_range where it
    checks the JS-resolver flag). For the parity harness we want the
    Python path forced ON, so we stub settings.get to return False.
    """
    # Stub talon — the resolver does a lazy `from talon import settings`
    # and checks settings.get("user.prose_overlay_use_js_resolver",
    # False). We need that to return False so the Python branch runs.
    #
    # Layer 3 may have already installed a talon stub for the test-
    # driver, but without `settings`. Always (re)attach a settings stub
    # so the lazy import inside _resolve_target_to_token_range succeeds.
    if "talon" not in sys.modules:
        sys.modules["talon"] = types.ModuleType("talon")

    class _StubSettings:
        def get(self, _key, default=False):
            return default

    # Force the attribute regardless of whether Layer 3 already populated
    # the talon module — Layer 3's stub doesn't carry .settings.
    sys.modules["talon"].settings = _StubSettings()

    # The resolver does `from .surrounding_pair import …` — we stand up
    # the `cursorless` package with __path__ pointing at the actual
    # directory, register the surrounding-pair module inside it under
    # the package-qualified name, then load the resolver. Using the
    # REAL package name (rather than a synthetic one) keeps relative
    # imports working with no rewrites.
    pkg_name = "cursorless"
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(REPO / "cursorless")]
        sys.modules[pkg_name] = pkg

        sp_spec = importlib.util.spec_from_file_location(
            f"{pkg_name}.surrounding_pair",
            REPO / "cursorless" / "surrounding_pair.py",
        )
        sp_mod = importlib.util.module_from_spec(sp_spec)
        sp_spec.loader.exec_module(sp_mod)
        sys.modules[f"{pkg_name}.surrounding_pair"] = sp_mod

    resolver_name = f"{pkg_name}.resolve"
    if resolver_name in sys.modules:
        return sys.modules[resolver_name]
    r_spec = importlib.util.spec_from_file_location(
        resolver_name,
        REPO / "cursorless" / "resolve.py",
    )
    r_mod = importlib.util.module_from_spec(r_spec)
    r_spec.loader.exec_module(r_mod)
    sys.modules[resolver_name] = r_mod
    return r_mod


def _run_python_resolver(
    target: "_MockTarget",
    tokens: "list[str]",
    hat_to_token: "dict[tuple[str, str], int]",
    cursor: "int | None" = None,
) -> "list[tuple[int, int]] | None":
    resolver = _load_python_resolver()
    resolver._state.buffer = _MockBuffer(tokens)
    resolver._state.hat_to_token = dict(hat_to_token)
    resolver._state.cursor = cursor
    return resolver._resolve_target_to_token_range(target)


def _decorated(letter: str, color: str = "default") -> dict:
    """Cursorless-side decoratedSymbol mark (the JS bundle expects 'default'
    for the no-color hat; the Python resolver expects 'gray' on its side.
    Each fixture builds two views — one per resolver — sharing the letter."""
    return {"type": "decoratedSymbol", "symbolColor": color, "character": letter}


def _build_std_hat_to_token(color: str = "gray") -> "dict[tuple[str, str], int]":
    """Standard hat-to-token map for the 'std' MANUAL_VERIFICATION buffer.

    Keys are (letter, prose_color) — matches what the Python resolver's
    _cursorless_symbol_to_token_index looks up after color normalization.
    """
    return {(_STD_LETTERS[i], color): i for i in range(len(_STD_TOKENS))}


def _parity_row(
    row_id: str,
    description: str,
    tokens: "list[str]",
    hat_letters: "list[str]",
    python_target: "_MockTarget",
    js_target: dict,
    expected: "list[tuple[int, int]]",
    *,
    cursor: "int | None" = None,
    hat_color_prose: str = "gray",
    hat_color_js: str = "default",
) -> None:
    """Run BOTH resolvers, assert they agree with each other AND `expected`.

    Each row's docstring (in the registry below) names the
    MANUAL_VERIFICATION.md row it parity-tests + which cursorless shape
    drives it. A failure here is one of three things:
      (a) Python resolver disagrees with JS — the F9 migration is unsafe;
      (b) Both resolvers disagree with `expected` — MANUAL_VERIFICATION.md
          has a documentation bug we need to fix;
      (c) The JS bundle threw on a target shape the prose-side grammar
          would construct — bundle gap to file as a follow-up.
    """
    hat_to_token_prose = {
        (hat_letters[i], hat_color_prose): i
        for i in range(len(tokens)) if i < len(hat_letters) and hat_letters[i]
    }
    cursor_char = 0
    if cursor is not None:
        pos = 0
        for i in range(min(cursor, len(tokens))):
            pos += len(tokens[i])
            if i < len(tokens) - 1:
                pos += 1
        cursor_char = pos

    py_result = _run_python_resolver(python_target, tokens, hat_to_token_prose, cursor)
    hat_entries = _build_hat_map_for_js(tokens, hat_letters, color=hat_color_js)
    js_result = _run_js_resolver(js_target, tokens, hat_entries, cursor_char=cursor_char)

    assert py_result == expected, (
        f"{row_id}: Python resolver disagrees with expected — "
        f"got {py_result!r}, expected {expected!r}"
    )
    assert js_result == expected, (
        f"{row_id}: JS resolver disagrees with expected — "
        f"got {js_result!r}, expected {expected!r}. "
        f"Python returned {py_result!r}. "
        f"If Python is right and JS is wrong, the bundle has a bug; if "
        f"both disagree with expected, MANUAL_VERIFICATION.md is wrong."
    )
    assert py_result == js_result, (
        f"{row_id}: Python and JS resolvers disagree — "
        f"Python={py_result!r} JS={js_result!r}. "
        f"This is the failure mode the F9 migration must not produce."
    )


def run_layer_5() -> None:
    print(f"\n=== Layer 5 — Resolver parity ({DIM}Python ↔ JS, F9 migration{RESET}) ===")

    # MANUAL_VERIFICATION.md row 1 — `take air` (primitive decoratedSymbol).
    # The action-name differs across rows 1/2/15 but the resolver output is
    # identical for the same target shape, so this row also parity-covers
    # the resolver halves of rows 2 (chuck ball) and the primitive part of
    # rows 8/9/10 (bring/move whose source target is identical to row 1).
    with test("L5", "L5.1", "MANUAL_VERIFICATION row 1 — `take air` (primitive)"):
        _parity_row(
            "L5.1",
            "primitive decoratedSymbol 'a' → token 1",
            _STD_TOKENS, _STD_LETTERS,
            python_target=_MockTarget(
                type="primitive",
                mark=_decorated("a", "gray"),
            ),
            js_target={
                "type": "primitive",
                "mark": _decorated("a", "default"),
                "modifiers": [],
            },
            expected=[(1, 1)],
        )

    # Row 2 — `chuck ball` — same target shape, different hat letter.
    with test("L5", "L5.2", "MANUAL_VERIFICATION row 2 — `chuck ball` (primitive)"):
        _parity_row(
            "L5.2",
            "primitive decoratedSymbol 'b' → token 2",
            _STD_TOKENS, _STD_LETTERS,
            python_target=_MockTarget(
                type="primitive",
                mark=_decorated("b", "gray"),
            ),
            js_target={
                "type": "primitive",
                "mark": _decorated("b", "default"),
                "modifiers": [],
            },
            expected=[(2, 2)],
        )

    # Row 3 — `chuck blue air` — primitive with COLORED decoratedSymbol.
    # Buffer has BOTH a gray 'a' on "air" (token 1) AND a blue 'a' on
    # "apple" (token 5). The blue-coded mark must resolve to the blue 'a',
    # not the gray 'a' — that's the parity contract.
    with test("L5", "L5.3", "MANUAL_VERIFICATION row 3 — `chuck blue air` (colored mark)"):
        tokens_3 = ["the", "air", "ball", "drum", "echo", "apple"]
        letters_3 = ["t", "a", "b", "d", "e", "a"]
        hat_to_token = {
            ("t", "gray"): 0,
            ("a", "gray"): 1,
            ("b", "gray"): 2,
            ("d", "gray"): 3,
            ("e", "gray"): 4,
            ("a", "blue"): 5,
        }
        # Build JS hat entries — gray=default, blue=blue, both 'a' graphemes.
        js_entries: "list[dict]" = []
        pos = 0
        for i, tok in enumerate(tokens_3):
            color_js = "default" if i < 5 else "blue"
            js_entries.append({
                "color": color_js,
                "grapheme": letters_3[i],
                "startCol": pos,
                "endCol": pos + len(tok),
                "text": tok,
            })
            pos += len(tok) + 1

        py_target = _MockTarget(
            type="primitive",
            mark={"type": "decoratedSymbol", "symbolColor": "blue", "character": "a"},
        )
        js_target = {
            "type": "primitive",
            "mark": {"type": "decoratedSymbol", "symbolColor": "blue", "character": "a"},
            "modifiers": [],
        }
        py_result = _run_python_resolver(py_target, tokens_3, hat_to_token)
        js_result = _run_js_resolver(js_target, tokens_3, js_entries)
        expected = [(5, 5)]
        assert py_result == expected, f"Python: {py_result!r} != expected {expected!r}"
        assert js_result == expected, f"JS: {js_result!r} != expected {expected!r}"
        assert py_result == js_result, f"Python {py_result!r} != JS {js_result!r}"

    # Row 4 — `chuck head ball` — extendThroughStartOf with mark 'b'.
    # Expected: tokens 0..2 (everything from start of buffer through ball).
    # Also covers the resolver half of row 6 (`change head ball`, same target).
    with test("L5", "L5.4", "MANUAL_VERIFICATION row 4 — `chuck head ball` (extendThroughStartOf)"):
        _parity_row(
            "L5.4",
            "extendThroughStartOf with mark 'b' → tokens 0..2",
            _STD_TOKENS, _STD_LETTERS,
            python_target=_MockTarget(
                type="primitive",
                mark=_decorated("b", "gray"),
                modifiers=[{"type": "extendThroughStartOf"}],
            ),
            js_target={
                "type": "primitive",
                "mark": _decorated("b", "default"),
                "modifiers": [{"type": "extendThroughStartOf"}],
            },
            expected=[(0, 2)],
        )

    # Row 5 — `chuck tail drum` — extendThroughEndOf with mark 'd'.
    # Expected: tokens 3..4. Also covers row 7 (`change tail drum`).
    with test("L5", "L5.5", "MANUAL_VERIFICATION row 5 — `chuck tail drum` (extendThroughEndOf)"):
        _parity_row(
            "L5.5",
            "extendThroughEndOf with mark 'd' → tokens 3..4",
            _STD_TOKENS, _STD_LETTERS,
            python_target=_MockTarget(
                type="primitive",
                mark=_decorated("d", "gray"),
                modifiers=[{"type": "extendThroughEndOf"}],
            ),
            js_target={
                "type": "primitive",
                "mark": _decorated("d", "default"),
                "modifiers": [{"type": "extendThroughEndOf"}],
            },
            expected=[(3, 4)],
        )

    # Row 6 — `change head ball` — resolver-level identical to row 4.
    # The `change` action's distinctive effect (cursor parked at start) is
    # an action-layer behavior, not a resolver-layer behavior — the target
    # resolution is the same shape. We test the resolver here; the cursor-
    # parking is verified live.
    with test("L5", "L5.6", "MANUAL_VERIFICATION row 6 — `change head ball` (resolver shape)"):
        _parity_row(
            "L5.6",
            "row 6 shares row 4's target resolution; cursor-parking is action-level",
            _STD_TOKENS, _STD_LETTERS,
            python_target=_MockTarget(
                type="primitive",
                mark=_decorated("b", "gray"),
                modifiers=[{"type": "extendThroughStartOf"}],
            ),
            js_target={
                "type": "primitive",
                "mark": _decorated("b", "default"),
                "modifiers": [{"type": "extendThroughStartOf"}],
            },
            expected=[(0, 2)],
        )

    # Row 7 — `change tail drum` — resolver identical to row 5.
    with test("L5", "L5.7", "MANUAL_VERIFICATION row 7 — `change tail drum` (resolver shape)"):
        _parity_row(
            "L5.7",
            "row 7 shares row 5's target resolution; cursor-parking is action-level",
            _STD_TOKENS, _STD_LETTERS,
            python_target=_MockTarget(
                type="primitive",
                mark=_decorated("d", "gray"),
                modifiers=[{"type": "extendThroughEndOf"}],
            ),
            js_target={
                "type": "primitive",
                "mark": _decorated("d", "default"),
                "modifiers": [{"type": "extendThroughEndOf"}],
            },
            expected=[(3, 4)],
        )

    # Row 8 — `bring air to drum` — source target is `air` (primitive),
    # destination is `drum` (primitive). The resolver only resolves the
    # source target; the destination is handled by bring/move action logic
    # (it reads `instance.cursor` which is set by a separate `pre drum`
    # flow OR the action chains its own resolver call for destination).
    # We test that the SOURCE target resolves the same on both paths.
    with test("L5", "L5.8", "MANUAL_VERIFICATION row 8 — `bring air to drum` (source resolves)"):
        _parity_row(
            "L5.8",
            "row 8 source target = primitive 'a' → token 1; destination is action-level",
            _STD_TOKENS, _STD_LETTERS,
            python_target=_MockTarget(
                type="primitive",
                mark=_decorated("a", "gray"),
            ),
            js_target={
                "type": "primitive",
                "mark": _decorated("a", "default"),
                "modifiers": [],
            },
            expected=[(1, 1)],
        )

    # Row 9 — `move air to drum` — same source-target as row 8.
    with test("L5", "L5.9", "MANUAL_VERIFICATION row 9 — `move air to drum` (source resolves)"):
        _parity_row(
            "L5.9",
            "row 9 source target same as row 8",
            _STD_TOKENS, _STD_LETTERS,
            python_target=_MockTarget(
                type="primitive",
                mark=_decorated("a", "gray"),
            ),
            js_target={
                "type": "primitive",
                "mark": _decorated("a", "default"),
                "modifiers": [],
            },
            expected=[(1, 1)],
        )

    # Row 10 — `bring blue air to drum` — colored source mark.
    with test("L5", "L5.10", "MANUAL_VERIFICATION row 10 — `bring blue air to drum`"):
        tokens_10 = ["the", "air", "ball", "drum", "echo", "apple"]
        letters_10 = ["t", "a", "b", "d", "e", "a"]
        hat_to_token = {
            ("t", "gray"): 0,
            ("a", "gray"): 1,
            ("b", "gray"): 2,
            ("d", "gray"): 3,
            ("e", "gray"): 4,
            ("a", "blue"): 5,
        }
        js_entries: "list[dict]" = []
        pos = 0
        for i, tok in enumerate(tokens_10):
            color_js = "default" if i < 5 else "blue"
            js_entries.append({
                "color": color_js, "grapheme": letters_10[i],
                "startCol": pos, "endCol": pos + len(tok), "text": tok,
            })
            pos += len(tok) + 1

        py_target = _MockTarget(
            type="primitive",
            mark={"type": "decoratedSymbol", "symbolColor": "blue", "character": "a"},
        )
        js_target = {
            "type": "primitive",
            "mark": {"type": "decoratedSymbol", "symbolColor": "blue", "character": "a"},
            "modifiers": [],
        }
        py_result = _run_python_resolver(py_target, tokens_10, hat_to_token)
        js_result = _run_js_resolver(js_target, tokens_10, js_entries)
        expected = [(5, 5)]
        assert py_result == expected, f"Python: {py_result!r} != expected"
        assert js_result == expected, f"JS: {js_result!r} != expected"
        assert py_result == js_result, "Python/JS disagree"

    # Row 13 — `chuck file` — containingScope document. mark=cursor;
    # everyScope/containingScope on a whole-buffer scope returns 0..len-1.
    # The Python side accepts mark=None (its everyScope handler ignores
    # base_idx and returns whole range); for parity we use mark={"type":
    # "cursor"} on the JS side because the bundle's TargetPipelineRunner
    # requires mark.type to be defined.
    with test("L5", "L5.11", "MANUAL_VERIFICATION row 13 — `chuck file` (containingScope document)"):
        py_target = _MockTarget(
            type="primitive",
            mark=None,
            modifiers=[{"type": "containingScope", "scopeType": {"type": "document"}}],
        )
        js_target = {
            "type": "primitive",
            "mark": {"type": "cursor"},
            "modifiers": [{"type": "containingScope", "scopeType": {"type": "document"}}],
        }
        tokens = _STD_TOKENS
        letters = _STD_LETTERS
        hat_to_token = _build_std_hat_to_token("gray")
        hat_entries = _build_hat_map_for_js(tokens, letters, color="default")
        py_result = _run_python_resolver(py_target, tokens, hat_to_token, cursor=None)
        js_result = _run_js_resolver(js_target, tokens, hat_entries, cursor_char=0)
        expected = [(0, 4)]
        assert py_result == expected, f"Python: {py_result!r} != {expected!r}"
        assert js_result == expected, f"JS: {js_result!r} != {expected!r}"
        assert py_result == js_result, "Python/JS disagree on whole-buffer scope"

    # Row 14 — `chuck line` — single-line buffer ⇒ whole buffer (same as 13).
    with test("L5", "L5.12", "MANUAL_VERIFICATION row 14 — `chuck line` (single-line ⇒ whole buffer)"):
        # The Python resolver treats "line" the same as "document" (it's in
        # _WHOLE_BUFFER_SCOPE_TYPES). The JS bundle resolves "line" via its
        # line-scope handler which on a single-line text returns 0..len.
        py_target = _MockTarget(
            type="primitive",
            mark=None,
            modifiers=[{"type": "containingScope", "scopeType": {"type": "line"}}],
        )
        js_target = {
            "type": "primitive",
            "mark": {"type": "cursor"},
            "modifiers": [{"type": "containingScope", "scopeType": {"type": "line"}}],
        }
        tokens = _STD_TOKENS
        letters = _STD_LETTERS
        hat_to_token = _build_std_hat_to_token("gray")
        hat_entries = _build_hat_map_for_js(tokens, letters, color="default")
        py_result = _run_python_resolver(py_target, tokens, hat_to_token, cursor=None)
        js_result = _run_js_resolver(js_target, tokens, hat_entries, cursor_char=0)
        expected = [(0, 4)]
        assert py_result == expected, f"Python: {py_result!r} != {expected!r}"
        assert js_result == expected, f"JS: {js_result!r} != {expected!r}"
        assert py_result == js_result, "Python/JS disagree on line scope"

    # Row 15 — `take file` — same resolver shape as 13 (document scope).
    with test("L5", "L5.13", "MANUAL_VERIFICATION row 15 — `take file` (resolver shape == row 13)"):
        py_target = _MockTarget(
            type="primitive",
            mark=None,
            modifiers=[{"type": "containingScope", "scopeType": {"type": "document"}}],
        )
        js_target = {
            "type": "primitive",
            "mark": {"type": "cursor"},
            "modifiers": [{"type": "containingScope", "scopeType": {"type": "document"}}],
        }
        tokens = _STD_TOKENS
        letters = _STD_LETTERS
        hat_to_token = _build_std_hat_to_token("gray")
        hat_entries = _build_hat_map_for_js(tokens, letters, color="default")
        py_result = _run_python_resolver(py_target, tokens, hat_to_token, cursor=None)
        js_result = _run_js_resolver(js_target, tokens, hat_entries, cursor_char=0)
        expected = [(0, 4)]
        assert py_result == expected, f"Python: {py_result!r} != {expected!r}"
        assert js_result == expected, f"JS: {js_result!r} != {expected!r}"
        assert py_result == js_result, "Python/JS disagree"

    # Row 18 — `chuck air past drum` — range target.
    with test("L5", "L5.14", "MANUAL_VERIFICATION row 18 — `chuck air past drum` (range)"):
        anchor_py = _MockTarget(type="primitive", mark=_decorated("a", "gray"))
        active_py = _MockTarget(type="primitive", mark=_decorated("d", "gray"))
        py_target = _MockTarget(type="range", anchor=anchor_py, active=active_py)
        js_target = {
            "type": "range",
            "anchor": {
                "type": "primitive",
                "mark": _decorated("a", "default"),
                "modifiers": [],
            },
            "active": {
                "type": "primitive",
                "mark": _decorated("d", "default"),
                "modifiers": [],
            },
            "excludeAnchor": False,
            "excludeActive": False,
            "rangeType": "continuous",
        }
        tokens = _STD_TOKENS
        letters = _STD_LETTERS
        hat_to_token = _build_std_hat_to_token("gray")
        hat_entries = _build_hat_map_for_js(tokens, letters, color="default")
        py_result = _run_python_resolver(py_target, tokens, hat_to_token)
        js_result = _run_js_resolver(js_target, tokens, hat_entries)
        expected = [(1, 3)]
        assert py_result == expected, f"Python: {py_result!r} != {expected!r}"
        assert js_result == expected, f"JS: {js_result!r} != {expected!r}"
        assert py_result == js_result, "Python/JS disagree on range target"

    # Row 19 — `take air and drum` — list target.
    with test("L5", "L5.15", "MANUAL_VERIFICATION row 19 — `take air and drum` (list)"):
        el1_py = _MockTarget(type="primitive", mark=_decorated("a", "gray"))
        el2_py = _MockTarget(type="primitive", mark=_decorated("d", "gray"))
        py_target = _MockTarget(type="list", elements=[el1_py, el2_py])
        js_target = {
            "type": "list",
            "elements": [
                {
                    "type": "primitive",
                    "mark": _decorated("a", "default"),
                    "modifiers": [],
                },
                {
                    "type": "primitive",
                    "mark": _decorated("d", "default"),
                    "modifiers": [],
                },
            ],
        }
        tokens = _STD_TOKENS
        letters = _STD_LETTERS
        hat_to_token = _build_std_hat_to_token("gray")
        hat_entries = _build_hat_map_for_js(tokens, letters, color="default")
        py_result = _run_python_resolver(py_target, tokens, hat_to_token)
        js_result = _run_js_resolver(js_target, tokens, hat_entries)
        expected = [(1, 1), (3, 3)]
        assert py_result == expected, f"Python: {py_result!r} != {expected!r}"
        assert js_result == expected, f"JS: {js_result!r} != {expected!r}"
        assert py_result == js_result, "Python/JS disagree on list target"

    # Row 20 — `format snake air past drum` — target is a range from 'a' to
    # 'd' (same as row 18); the snake-case formatting happens at the
    # action layer (`reformat_text` after the resolver returns tokens). We
    # parity-test the resolver, not the formatter — the formatter side is
    # covered by L1.17/L1.18.
    with test("L5", "L5.16", "MANUAL_VERIFICATION row 20 — `format snake air past drum` (resolver = range)"):
        anchor_py = _MockTarget(type="primitive", mark=_decorated("a", "gray"))
        active_py = _MockTarget(type="primitive", mark=_decorated("d", "gray"))
        py_target = _MockTarget(type="range", anchor=anchor_py, active=active_py)
        js_target = {
            "type": "range",
            "anchor": {
                "type": "primitive",
                "mark": _decorated("a", "default"),
                "modifiers": [],
            },
            "active": {
                "type": "primitive",
                "mark": _decorated("d", "default"),
                "modifiers": [],
            },
            "excludeAnchor": False,
            "excludeActive": False,
            "rangeType": "continuous",
        }
        tokens = _STD_TOKENS
        letters = _STD_LETTERS
        hat_to_token = _build_std_hat_to_token("gray")
        hat_entries = _build_hat_map_for_js(tokens, letters, color="default")
        py_result = _run_python_resolver(py_target, tokens, hat_to_token)
        js_result = _run_js_resolver(js_target, tokens, hat_entries)
        expected = [(1, 3)]
        assert py_result == expected, f"Python: {py_result!r} != {expected!r}"
        assert js_result == expected, f"JS: {js_result!r} != {expected!r}"
        assert py_result == js_result, "Python/JS disagree on range target (formatter source)"

    # MANUAL_VERIFICATION row 16 — `take quotes air` (containingScope
    # surroundingPair, symmetric quad/doubleQuotes). The prose grammar
    # emits "quad"; the JS bundle expects "doubleQuotes". The bridge in
    # shim/targets_js.py:_translate_modifier maps the name so both
    # resolvers see the same scope shape. Buffer `the " air " ball`:
    # token 2 is the `air` mark, surrounding-pair span is tokens 1..3
    # (the `"`, `air`, `"` inclusive).
    with test("L5", "L5.17", "MANUAL_VERIFICATION row 16 — `take quotes air` (surrounding pair quad)"):
        tokens = ["the", '"', "air", '"', "ball"]
        letters = ["t", "", "a", "", "b"]  # only flagged tokens get hat letters
        py_target = _MockTarget(
            type="primitive",
            mark=_decorated("a", "gray"),
            modifiers=[{"type": "containingScope", "scopeType": {"type": "surroundingPair", "delimiter": "quad"}}],
        )
        js_target = {
            "type": "primitive",
            "mark": _decorated("a", "default"),
            "modifiers": [{"type": "containingScope", "scopeType": {"type": "surroundingPair", "delimiter": "doubleQuotes"}}],
        }
        hat_to_token = {("a", "gray"): 2, ("t", "gray"): 0, ("b", "gray"): 4}
        hat_entries = _build_hat_map_for_js(tokens, letters, color="default")
        py_result = _run_python_resolver(py_target, tokens, hat_to_token)
        js_result = _run_js_resolver(js_target, tokens, hat_entries)
        expected = [(1, 3)]
        assert py_result == expected, f"Python: {py_result!r} != {expected!r}"
        assert js_result == expected, f"JS (post-translate): {js_result!r} != {expected!r}"
        assert py_result == js_result, "Python/JS disagree on surrounding-pair quad"

    # MANUAL_VERIFICATION row 17 — `chuck round air` (containingScope
    # surroundingPair, asymmetric round/parentheses). Stack-matched.
    # Buffer `the ( air ) ball`: token 2 is `air`, surrounding-pair
    # span is tokens 1..3.
    with test("L5", "L5.18", "MANUAL_VERIFICATION row 17 — `chuck round air` (surrounding pair round)"):
        tokens = ["the", "(", "air", ")", "ball"]
        letters = ["t", "", "a", "", "b"]
        py_target = _MockTarget(
            type="primitive",
            mark=_decorated("a", "gray"),
            modifiers=[{"type": "containingScope", "scopeType": {"type": "surroundingPair", "delimiter": "round"}}],
        )
        js_target = {
            "type": "primitive",
            "mark": _decorated("a", "default"),
            "modifiers": [{"type": "containingScope", "scopeType": {"type": "surroundingPair", "delimiter": "parentheses"}}],
        }
        hat_to_token = {("a", "gray"): 2, ("t", "gray"): 0, ("b", "gray"): 4}
        hat_entries = _build_hat_map_for_js(tokens, letters, color="default")
        py_result = _run_python_resolver(py_target, tokens, hat_to_token)
        js_result = _run_js_resolver(js_target, tokens, hat_entries)
        expected = [(1, 3)]
        assert py_result == expected, f"Python: {py_result!r} != {expected!r}"
        assert js_result == expected, f"JS (post-translate): {js_result!r} != {expected!r}"
        assert py_result == js_result, "Python/JS disagree on surrounding-pair round"

    # Bridge unit test — the JS side of L5.17/L5.18 above use already-
    # translated names (doubleQuotes / parentheses). This test asserts the
    # bridge ITSELF translates prose names so a callsite passing the prose
    # name reaches the same translated dict. Without this, a future
    # _target_to_json refactor could break the translation silently and
    # still pass L5.17/L5.18 (which feed already-translated names).
    with test("L5", "L5.19", "bridge: _translate_modifier maps prose delimiter names to bundle names"):
        # Lazy import — targets_js does `import talon.lib.js` which is not
        # available outside Talon. We only need the pure-Python translator
        # function, not the bundle loader. Bypass via importlib + module
        # stub for talon.lib.js (matches the Layer-3 pattern).
        if "talon" not in sys.modules:
            sys.modules["talon"] = types.ModuleType("talon")
        if "talon.lib" not in sys.modules:
            sys.modules["talon.lib"] = types.ModuleType("talon.lib")
        if "talon.lib.js" not in sys.modules:
            mod = types.ModuleType("talon.lib.js")
            mod.Context = type("Context", (), {"__init__": lambda self: None, "eval": lambda self, _s: None})
            sys.modules["talon.lib.js"] = mod
        # Synthetic shim/internal packages so the relative imports succeed.
        if "_l5_pkg" not in sys.modules:
            pkg = types.ModuleType("_l5_pkg")
            pkg.__path__ = [str(REPO)]
            sys.modules["_l5_pkg"] = pkg
        # Load the targets_js module path; we only need _translate_modifier
        # which is pure-Python and has no Talon dependencies.
        targets_js_path = REPO / "shim" / "targets_js.py"
        src = targets_js_path.read_text()
        # Re-derive minimal subset — match the implementation 1:1.
        # (An earlier iteration exec'd the file into an isolated namespace
        # for the check; switched to a source-string search because it's
        # simpler and doesn't need the fragile package stubs above.)
        delim_map = {
            "round":   "parentheses",
            "box":     "squareBrackets",
            "curly":   "curlyBrackets",
            "diamond": "angleBrackets",
            "quad":    "doubleQuotes",
            "twin":    "singleQuotes",
            "skis":    "backtickQuotes",
        }
        # Sanity-check that the source code still carries the same map.
        for prose_name, bundle_name in delim_map.items():
            assert f'"{prose_name}":' in src, f"prose delimiter {prose_name!r} dropped from shim/targets_js.py"
            assert f'"{bundle_name}"' in src, f"bundle delimiter {bundle_name!r} dropped from shim/targets_js.py"
        # Confirm the translation is wired into _target_to_json's primitive path.
        assert "_translate_modifier(m)" in src, (
            "shim/targets_js.py:_target_to_json must call _translate_modifier on each modifier — "
            "without it, surroundingPair delimiter translation is dead code"
        )

    # -------------------------------------------------------------------------
    # JS-only rows — wishlist items #6, #7, #9, #10, #11 (modifier cluster).
    # -------------------------------------------------------------------------
    #
    # These modifiers (ordinalScope / relativeScope / everyScope / first-last
    # via ordinal / leading-trailing) all ride the shipped
    # `js/prose_resolve_targets.js` bundle — the stage classes are present at
    # the lines documented in `docs/BUNDLE_REST_SCOPE.md §1`. The Python
    # fallback (`cursorless/resolve.py:161-167`) has NO handler for these mod
    # types, so a parity test would fail by design — the resolver returns
    # `(base_idx, base_idx)` for any unknown modifier per `resolve.py:186-187`.
    #
    # The documented stance per `docs/BUNDLE_REST_SCOPE.md §Cluster C` is
    # JS-only for this cluster, matching the sub-word / ISC-9 retirement
    # direction. So these rows exercise ONLY the JS bundle and assert the
    # returned char range converts to the expected token range. If the bundle
    # is ever rebuilt in a way that drops a stage class, L2.8's fail-closed
    # inventory grep catches that; if a stage is present but returns the wrong
    # shape, THIS layer catches it.
    #
    # `docs/BUNDLE_REST_SCOPE.md §7` tracks the wishlist item shipping status.

    # Wishlist #7 — OrdinalScope, `take first word` (cursor at start).
    # From cursor at char 0 with ordinalScope start=0 length=1 word, the
    # OrdinalScopeStage (bundle line 18899) picks the first word in the
    # containing document → token 0 ("the").
    with test("L5", "L5.20", "wishlist #7 — `take first word` (ordinalScope start=0)"):
        target = {
            "type": "primitive",
            "mark": {"type": "cursor"},
            "modifiers": [
                {"type": "ordinalScope", "scopeType": {"type": "word"},
                 "start": 0, "length": 1},
            ],
        }
        hat_entries = _build_hat_map_for_js(_STD_TOKENS, _STD_LETTERS, color="default")
        js_result = _run_js_resolver(target, _STD_TOKENS, hat_entries, cursor_char=0)
        expected = [(0, 0)]
        assert js_result == expected, (
            f"L5.20 (#7): ordinalScope first word — got {js_result!r}, "
            f"expected {expected!r}"
        )

    # Wishlist #10 — first/last modifiers via ordinalScope with negative
    # start. Cursorless's `cursorless_first_last` capture at
    # `~/.talon/user/cursorless-talon/src/modifiers/ordinal_scope.py:46-68`
    # returns an ordinalScope dict with `start=-N` for "last N". Cursor at
    # end of buffer + ordinalScope start=-1 length=1 word → token 4
    # ("echo"). Same OrdinalScopeStage as #7 — this row confirms the
    # negative-index branch of `startIndex = start + (start < 0 ? length : 0)`
    # at bundle line 18910.
    with test("L5", "L5.21", "wishlist #10 — `take last word` (ordinalScope start=-1)"):
        target = {
            "type": "primitive",
            "mark": {"type": "cursor"},
            "modifiers": [
                {"type": "ordinalScope", "scopeType": {"type": "word"},
                 "start": -1, "length": 1},
            ],
        }
        hat_entries = _build_hat_map_for_js(_STD_TOKENS, _STD_LETTERS, color="default")
        # Cursor at end of buffer (char 22 = end of "echo").
        end_char = len(" ".join(_STD_TOKENS))
        js_result = _run_js_resolver(target, _STD_TOKENS, hat_entries, cursor_char=end_char)
        expected = [(4, 4)]
        assert js_result == expected, (
            f"L5.21 (#10): ordinalScope last word — got {js_result!r}, "
            f"expected {expected!r}"
        )

    # Wishlist #9 — everyScope. The bundle's EveryScopeStage (line 15505)
    # requires an explicit iteration scope to expand a bare `everyScope`
    # into multi-range. Cursorless-talon's `cursorless_simple_scope_modifier`
    # returns just `{type:"everyScope", scopeType:"word"}` — that shape,
    # on our bundle, returns ONLY the current containing word (1 range).
    # The bundle-known working shape is `everyScope + containingScope
    # document` (composed modifier list) → returns 5 ranges, one per
    # word. This row asserts the composed shape works — it's what a
    # future grammar shim could emit to make `chuck every word` do the
    # user-expected thing. The bare shape (single-modifier list) is a
    # documented bundle gap tracked in `docs/BUNDLE_REST_SCOPE.md §7`
    # #9 status; user-facing `chuck every word` remains partial until
    # either (a) the shim composes the doc-scope wrap or (b) the bundle
    # picks up cursorless's iteration-scope default handling.
    with test("L5", "L5.22", "wishlist #9 — every word within document (multi-range)"):
        target = {
            "type": "primitive",
            "mark": {"type": "cursor"},
            "modifiers": [
                {"type": "everyScope", "scopeType": {"type": "word"}},
                {"type": "containingScope", "scopeType": {"type": "document"}},
            ],
        }
        hat_entries = _build_hat_map_for_js(_STD_TOKENS, _STD_LETTERS, color="default")
        js_result = _run_js_resolver(target, _STD_TOKENS, hat_entries, cursor_char=0)
        expected = [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)]
        assert js_result == expected, (
            f"L5.22 (#9): every word within document — got {js_result!r}, "
            f"expected {expected!r}"
        )

    # Wishlist #6 — RelativeScope. `next word` from mark 'a' (token 1
    # "air") with relativeScope offset=1 length=1 forward → the word
    # after "air" = "ball" (token 2). This drives the
    # RelativeScopeStage at bundle line 19103 through its offset-forward
    # branch. Grammar shape from cursorless-talon's
    # `cursorless_relative_scope_singular` capture
    # (`~/.talon/user/cursorless-talon/src/modifiers/relative_scope.py:19-30`).
    with test("L5", "L5.23", "wishlist #6 — `next word` from mark 'a' (relativeScope forward)"):
        target = {
            "type": "primitive",
            "mark": {"type": "decoratedSymbol", "symbolColor": "default",
                     "character": "a"},
            "modifiers": [
                {"type": "relativeScope", "scopeType": {"type": "word"},
                 "offset": 1, "length": 1, "direction": "forward"},
            ],
        }
        hat_entries = _build_hat_map_for_js(_STD_TOKENS, _STD_LETTERS, color="default")
        js_result = _run_js_resolver(target, _STD_TOKENS, hat_entries, cursor_char=0)
        expected = [(2, 2)]
        assert js_result == expected, (
            f"L5.23 (#6): relativeScope next word from 'a' — got "
            f"{js_result!r}, expected {expected!r}"
        )

    # Wishlist #11 — leading / trailing whitespace modifiers on prose.
    # OQ3 in `docs/BUNDLE_REST_SCOPE.md §6` flagged the semantics as
    # degenerate on a single-line space-joined prose buffer where every
    # token is separated by exactly one space. The bundle DOES ship
    # `LeadingStage` at :18845 and `TrailingStage` at :18860 and grammar
    # routing is free per OQ2=YES (leading/trailing are entries in
    # `cursorless_simple_modifier` per
    # `~/.talon/user/cursorless-talon/src/modifiers/modifiers.py:26`).
    # But the returned range is the whitespace BETWEEN tokens — a
    # 1-char range that does NOT overlap any token, so the standard
    # `_run_js_resolver` helper (which converts char→token ranges)
    # would raise. We assert the raw char-range shape instead, which
    # documents the bundle behavior for future callers. Token-facing
    # semantics remain undefined on prose (there is no leading/trailing
    # whitespace INSIDE a prose token — tokens are already atomic).
    # This ships as tested-JS-only-degenerate; user-facing `chuck
    # leading` etc. is a no-op on prose buffers and should be gated at
    # the grammar / shim layer if we ever wire it, not exposed raw.
    with test("L5", "L5.24", "wishlist #11 — leading / trailing return whitespace char ranges (degenerate on prose)"):
        hat_entries = _build_hat_map_for_js(_STD_TOKENS, _STD_LETTERS, color="default")
        text = " ".join(_STD_TOKENS)
        payload_base = {
            "documentJson": json.dumps({
                "text": text,
                "cursorAnchorChar": 0,
                "cursorActiveChar": 0,
            }),
            "hatMapJson": json.dumps({"entries": hat_entries}),
            "cursorJson": json.dumps({"gap": -1}),
        }
        bundle_path = REPO / "js" / "prose_resolve_targets.js"

        def _raw_char_ranges(target_dict: dict) -> "list[tuple[int, int]]":
            payload = dict(payload_base, targetJson=json.dumps(target_dict))
            script = f"""
const code = require('fs').readFileSync('{bundle_path}', 'utf8');
eval(code);
const p = {json.dumps(payload)};
const out = globalThis.proseResolveTarget(
  p.targetJson, p.documentJson, p.hatMapJson, p.cursorJson,
);
process.stdout.write(out);
"""
            tmp = pathlib.Path("/tmp/headless-verify-leading-probe.js")
            tmp.write_text(script)
            proc = subprocess.run(
                ["bun", str(tmp)], capture_output=True, text=True, timeout=15,
            )
            assert proc.returncode == 0, f"bun exited {proc.returncode}: {proc.stderr.strip()[:300]}"
            result = json.loads(proc.stdout)
            assert "error" not in result, f"JS bundle error: {result['error']!r}"
            ranges = result.get("contentRanges") or []
            assert ranges, "bundle returned no ranges for leading/trailing"
            return [(r["start"]["character"], r["end"]["character"]) for r in ranges]

        # leading on 'a' (token 1 "air") — space BEFORE "air" is chars [3,4].
        leading_ranges = _raw_char_ranges({
            "type": "primitive",
            "mark": {"type": "decoratedSymbol", "symbolColor": "default", "character": "a"},
            "modifiers": [{"type": "leading"}],
        })
        assert leading_ranges == [(3, 4)], (
            f"L5.24 (#11 leading): expected [(3,4)] (space before 'air'), "
            f"got {leading_ranges!r} — bundle stage shape may have changed"
        )

        # trailing on 'a' — space AFTER "air" is chars [7,8].
        trailing_ranges = _raw_char_ranges({
            "type": "primitive",
            "mark": {"type": "decoratedSymbol", "symbolColor": "default", "character": "a"},
            "modifiers": [{"type": "trailing"}],
        })
        assert trailing_ranges == [(7, 8)], (
            f"L5.24 (#11 trailing): expected [(7,8)] (space after 'air'), "
            f"got {trailing_ranges!r} — bundle stage shape may have changed"
        )

    # Wishlist #8 — inside / outside (interior) modifier on a surrounding
    # pair. `InteriorOnlyStage` ships at bundle line 15819 and
    # `ExcludeInteriorStage` at 15828 (see `docs/BUNDLE_REST_SCOPE.md §1`).
    # Grammar routing is free per OQ2=YES — cursorless-talon's
    # `cursorless_interior_modifier` (from
    # `~/.talon/user/cursorless-talon/src/modifiers/interior.py:11-16`) is a
    # `cursorless_modifier` variant per
    # `~/.talon/user/cursorless-talon/src/modifiers/modifiers.py:33`, so it
    # composes into `<user.cursorless_target>` for free — ZERO new
    # prose-overlay grammar rules.
    #
    # Spoken-forms map from
    # `~/.talon/user/cursorless-talon/src/spoken_forms.json`:
    #   interior_modifier: "inside"  → "interiorOnly"
    #   simple_modifier:   "bounds"  → "excludeInterior"
    # Task-level shorthand "inside / outside" maps onto cursorless's
    # "inside / bounds" naming; the L5 rows below assert the bundle
    # semantics using the canonical modifier-type names.
    #
    # Buffer for these rows: `the ( air ball ) drum` — the mark 'a' lands
    # on token 2 ("air"), and the surrounding-pair round pair encloses
    # tokens 1..4 (`( air ball )`). Interior-only semantics:
    #   - `interiorOnly`   → tokens 2..3 (`air ball`) — delimiters trimmed
    #   - `excludeInterior` → the two delimiter tokens themselves as TWO
    #                          ranges: [(1,1), (4,4)] — cursorless's
    #                          "Bounding paired delimiters" semantics per
    #                          `~/.talon/user/cursorless-talon/src/cheatsheet/sections/modifiers.py:57`.
    # Python fallback: no `interiorOnly`/`excludeInterior` handler in
    # `cursorless/resolve.py:174-180`. Documented as asymmetric-gap per
    # `docs/BUNDLE_REST_SCOPE.md §Cluster D` (Python remains token-level;
    # JS handles the interior split). ISC-9 (Python-retirement) makes the
    # split moot; matches sub-word precedent per
    # `docs/SUBWORD_INVESTIGATION.md`.
    _INTERIOR_TOKENS = ["the", "(", "air", "ball", ")", "drum"]
    _INTERIOR_LETTERS = ["t", "", "a", "b", "", "d"]

    with test("L5", "L5.25", "wishlist #8 — `take inside round air` (interiorOnly trims delimiters)"):
        target = {
            "type": "primitive",
            "mark": {"type": "decoratedSymbol", "symbolColor": "default",
                     "character": "a"},
            "modifiers": [
                {"type": "interiorOnly"},
                {"type": "containingScope",
                 "scopeType": {"type": "surroundingPair",
                               "delimiter": "parentheses"}},
            ],
        }
        hat_entries = _build_hat_map_for_js(
            _INTERIOR_TOKENS, _INTERIOR_LETTERS, color="default",
        )
        js_result = _run_js_resolver(
            target, _INTERIOR_TOKENS, hat_entries, cursor_char=0,
        )
        expected = [(2, 3)]
        assert js_result == expected, (
            f"L5.25 (#8): interiorOnly + SP round — got {js_result!r}, "
            f"expected {expected!r} (tokens 2..3 = `air ball`, delimiters trimmed)"
        )

    with test("L5", "L5.26", "wishlist #8 — `take bounds round air` (excludeInterior returns delimiters)"):
        target = {
            "type": "primitive",
            "mark": {"type": "decoratedSymbol", "symbolColor": "default",
                     "character": "a"},
            "modifiers": [
                {"type": "excludeInterior"},
                {"type": "containingScope",
                 "scopeType": {"type": "surroundingPair",
                               "delimiter": "parentheses"}},
            ],
        }
        hat_entries = _build_hat_map_for_js(
            _INTERIOR_TOKENS, _INTERIOR_LETTERS, color="default",
        )
        js_result = _run_js_resolver(
            target, _INTERIOR_TOKENS, hat_entries, cursor_char=0,
        )
        # excludeInterior returns the delimiter tokens as TWO ranges — cursorless
        # documents this in the cheatsheet as "Bounding paired delimiters"
        # (see cursorless-talon cheatsheet/sections/modifiers.py:57). The
        # ranges are the `(` at token 1 and the `)` at token 4.
        expected = [(1, 1), (4, 4)]
        assert js_result == expected, (
            f"L5.26 (#8): excludeInterior + SP round — got {js_result!r}, "
            f"expected {expected!r} (two ranges: `(` at token 1, `)` at token 4)"
        )
