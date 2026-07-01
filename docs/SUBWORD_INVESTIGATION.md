# Sub-Word `word` Scope Investigation — JS bundle contents vs Python resolver gap

> Investigation prompted by uncertainty in `docs/GRAMMAR_STRUCTURE_PARITY.md` about
> whether cursorless's sub-word `word` scope actually reaches prose-overlay through
> the JS resolver bundle.
>
> Investigation completed 2026-07-01. Verdict below.

## Verdict

**(a) `WordScopeHandler` IS in the JS bundle and sub-word splitting IS available via the JS resolver (default since 2026-06-30).** The blocker for `take second word this` inside `one_two_three` is NOT the bundle — it's the Python resolver fallback + zero test coverage.

## Evidence

### 1. Bundle audit — WordScopeHandler present

`js/prose_resolve_targets.js` contains all necessary sub-word components:

- **Line 14342** — `CAMEL_REGEX = /\p{Lu}?\p{Ll}+|\p{Lu}+(?!\p{Ll})|\p{N}+/gu` (Unicode regex for case-based word boundaries).
- **Lines 14343–14353** — `WordTokenizer` class with `splitIdentifier(text)`: splits on the language's word regex first, falls back to `CAMEL_REGEX`.
- **Lines 14357–14380** — `WordScopeHandler` class instantiating `WordTokenizer` and calling `splitIdentifier()` to return multiple sub-word ranges.

All 8 search terms (`WordScopeHandler`, `WordTokenizer`, `splitIdentifier`, `CAMEL_REGEX`, `identifierWord`, `subtoken`, `wordPart`, `word_part`) — only the identifier-family ones match; the `subtoken`/`wordPart` alternatives correctly do not appear (they aren't cursorless's naming per `REBUTTAL_ASSERTIONS.md #1`).

### 2. Bundle build source

`scripts/build-js.ts:38` — the targets bundle is built from `packages/cursorless-engine/src/actions/proseTargetsStandalone.ts`. That entry point imports `ScopeHandlerFactoryImpl` directly (line 45) without tree-shaking the scope handlers. `WordScopeHandler` is included by construction.

### 3. Python resolver — the actual gap

`cursorless/resolve.py:108-115`:

```python
def _scope_word(tokens, base_idx, scope_type) -> "tuple[int, int] | None":
    if base_idx is not None:
        return (base_idx, base_idx)  # ← always one token, no splitting
    tok_idx = _cursor_fallback_idx(tokens)
    if tok_idx is None:
        print(f"prose_overlay: scope '{scope_type}' requires a mark or active cursor")
        return None
    return (tok_idx, tok_idx)
```

No call to `splitIdentifier()`. All five scope types in `_WORD_SCOPE_TYPES` are treated identically at token-level. **The Python fallback does NOT support sub-word splitting.**

### 4. MANUAL_VERIFICATION coverage — zero sub-word rows

- Rows 1–10: token-level targets
- Rows 13–15: whole-buffer scopes (document/line)
- Rows 16–17: surrounding-pair scopes
- Rows 18–20: range/list/format targets

Every test buffer uses space-separated tokens (`"the air ball drum echo"`). No row contains a single token with internal `_-./` delimiters or camelCase boundaries. Sub-word behavior is untested headlessly and untested manually.

### 5. Live probe — easy to build with existing helpers

Layer 5 style, using `_run_js_resolver()` / `_MockBuffer` / `_MockTarget` from `scripts/headless_verify/layer5.py:80-138`:

- **Buffer:** `["one_two_three"]` (single snake_case token).
- **Target:** `{"type": "primitive", "mark": {"type": "cursor"}, "modifiers": [{"type": "containingScope", "scopeType": {"type": "word"}}]}`.
- **Expected JS result:** multiple `contentRanges` entries (one per sub-word: `one`, `two`, `three`).
- **Expected Python result:** single token range (whole `one_two_three`).

No new plumbing needed. Add as `L5.20` — the row that surfaces the Python ↔ JS divergence and locks the JS-side behavior.

## Recommendations

1. **Upgrade `FEATURE_PARITY.md §3c`** — the row "word scope splits formatted tokens into sub-words" moves from `[ ]` to `[~]`: "JS resolver splits sub-words natively (default since 2026-06-30 F9 flip); Python fallback is token-level; headless coverage pending."
2. **Add `L5.20`** to `scripts/headless_verify/layer5.py` — surfaces the divergence and pins JS-side behavior against regression.
3. **Note in ISC-9** (Python resolver retirement) — sub-word on the Python path would require implementing `splitIdentifier()` locally. Since ISC-9 is the retirement of that path, the sub-word gap becomes moot as soon as ISC-9 lands.
4. **Update `docs/FEATURE_PARITY_REBUTTAL_CURSORLESS.md`** — sub-word `word` scope is Tier 1 on the JS resolver (cursorless already provides it in the bundle), Tier 3 on the Python resolver (would be pure prose-overlay work). Since §3f defaults JS-side, users have it.
5. **Update `docs/GRAMMAR_STRUCTURE_PARITY.md`** — the drift summary implied sub-word was "wantable but not shipped." Reframe as "shipped via JS resolver; blocked on Python resolver retirement; needs a headless row."

## What this refutes / confirms in adjacent docs

- **`REBUTTAL_ASSERTIONS.md #1`** (killer-insight: `word` is THE sub-token splitter in Cursorless) — CONFIRMED further. The bundle actually ships it.
- **`REBUTTAL_ASSERTIONS.md #2`** (prose-overlay pre-splits identifiers — diagnosis wrong; buffer keeps identifiers whole per L1.17) — CONFIRMED. Buffer holds `one_two_three` as one token; the JS resolver's `WordScopeHandler` can then split it.
- **`REBUTTAL_ASSERTIONS.md #5`** (shape identifiers absent from bundle) — orthogonal, still stands. Shapes and sub-word are separate bundle contents.
- **`REBUTTAL_ASSERTIONS.md #9`** (JS-resolver migration is a hard gate for sub-word) — PARTIALLY REFUTED. The migration has already flipped default-on (2026-06-30). Sub-word is unblocked at the JS path today; only the Python fallback is stuck.
