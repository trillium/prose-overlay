# Cursorless scope coverage on prose-overlay

> Doc-only inventory (2026-07-01). Companion to `docs/FEATURE_PARITY.md §3c`
> and `docs/BUNDLE_REST_SCOPE.md §7`. Enumerates every cursorless upstream
> scope type and lands each in exactly one of five buckets against the
> prose buffer model. Do not implement from this doc without cross-reading
> `docs/BUNDLE_REST_SCOPE.md §7` closure log for the shipping SHAs.

## §0. Executive summary

Cursorless upstream defines **~59 scope types** — 55 `simpleScopeTypeTypes`
enumerated at `~/code/cursorless/packages/common/src/types/command/PartialTargetDescriptor.types.ts:113-176`
plus 4 non-simple variants (`surroundingPair`, `customRegex`, `oneOf`,
`glyph`) at `:190-216`. Bucketed against our single-line prose buffer:

- **✅ Shipped + working:** 11 (token/word/identifier/character at token level,
  sentence, nonWhitespaceSequence, url, surroundingPair, string, number,
  email — the last three via `_REGEX_SCOPE_PATTERNS` beyond upstream)
- **🟡 Shipped but degenerate on single-line prose:** 4 (document, line,
  paragraph, boundedNonWhitespaceSequence)
- **🟠 Applicable but not yet shipped:** 4 (glyph, customRegex, character
  sub-token, section)
- **❌ Inapplicable (code/tree-sitter/notebook only):** 37 (all
  argumentOrParameter, class, comment, function*, xml*, latex*, statement,
  branch, etc.)
- **⚠️ Ambiguous / needs decision:** 3 (character mid-token cursor,
  customRegex vocabulary source, paragraph explicit-support gesture)

Split: roughly two-thirds of cursorless's scope surface belongs to code /
tree-sitter / notebook editing and is inapplicable by construction. The
remaining third is either shipped, degenerate-but-honored, or reachable.

## §1. Constraint context — "mostly single-line prose"

Buffer model per `ISA.md §Constraints`: single Python string held by
`ProseBuffer`, whitespace-split into tokens. Newlines CAN appear (paste,
history recall) but the common case is one line. Consequences:

- **`line` ≡ `document` ≡ `paragraph`** most of the time — all three
  return the whole buffer. Handled explicitly by `_WHOLE_BUFFER_SCOPE_TYPES`
  at `cursorless/resolve.py:48`.
- **No syntax tree.** Every tree-sitter-language scope (`argumentOrParameter`,
  `class`, `functionCall`, `xmlElement`, latex `part`, `namedFunction`, …)
  has no meaning against a bag of prose tokens. Cursorless upstream gates
  these on a language ID; our synthetic buffer has none.
- **No notebook.** `notebookCell` requires a Jupyter-style host.
- **Token boundaries = whitespace.** `leading`/`trailing` degenerate to the
  single space BETWEEN tokens (OQ3 resolution in `docs/BUNDLE_REST_SCOPE.md §7`).
- **No mid-token cursor today.** Cursor is `gap-between-tokens` — see
  `docs/POTENTIALLY_MISSED.md §L` — which forecloses `character` scope as
  a first-class primitive until the cursor model widens.

## §2. Scope catalog

Ordered by category. Refs are relative to `~/code/prose-overlay/` unless
prefixed with `~/code/cursorless/`.

| Scope name | Category | Status in prose-overlay | Ref |
|---|---|---|---|
| `token` | ✅ shipped | works at token-level via `_WORD_SCOPE_TYPES` set | `cursorless/resolve.py:49`; JS: `js/prose_resolve_targets.js:14424` |
| `word` | ✅ shipped | JS bundle splits sub-words natively (default since 2026-06-30 F9 flip); Python fallback token-level only | `js/prose_resolve_targets.js:14357`; `docs/FEATURE_PARITY.md §3c` row `[~]`; `docs/SUBWORD_INVESTIGATION.md` |
| `identifier` | ✅ shipped | aliases to token in Python fallback; JS bundle ships full handler | `cursorless/resolve.py:49`; JS: `js/prose_resolve_targets.js:14259` |
| `character` | ✅ shipped (token-level alias) | Python treats character == token; JS handler exists but no shipped action uses it (see §4) | `cursorless/resolve.py:49`; JS: `js/prose_resolve_targets.js:14305`; `docs/CURSORLESS_ACTIONS_COVERAGE.md §4.4` |
| `sentence` | ✅ shipped | regex `[^.!?]*[^.!?\s][^.!?]*[.!?]*` in Python; JS bundle handler at `:14675` | `cursorless/resolve.py:56`; ISC-4 |
| `nonWhitespaceSequence` | ✅ shipped | regex `\S+` | `cursorless/resolve.py:51`; ISC-4 |
| `url` | ✅ shipped | regex-based; JS handler at `:14739` | `cursorless/resolve.py:52-55`; ISC-4 |
| `string` | ✅ shipped (prose extension) | regex-based; NOT a cursorless simple scope in upstream, added prose-side | `cursorless/resolve.py:58`; ISC-4 |
| `number` | ✅ shipped (prose extension) | regex-based; NOT in upstream simple types | `cursorless/resolve.py:59`; ISC-4 |
| `email` | ✅ shipped (prose extension) | regex-based; NOT in upstream | `cursorless/resolve.py:60`; ISC-4 |
| `surroundingPair` | ✅ shipped | 7 delimiters (round/box/curly/diamond/quad/twin/skis); interior/bounds via ISC-34/35 | `cursorless/surrounding_pair.py`; `shim/targets_js.py:82-90`; ISC-5, ISC-34, ISC-35 |
| `line` | 🟡 degenerate | maps to whole buffer (single-line assumption) | `cursorless/resolve.py:48`; JS: `:14062` |
| `document` | 🟡 degenerate | whole buffer by definition | `cursorless/resolve.py:48`; JS: `:14457` |
| `paragraph` | 🟡 degenerate | ≡ document ≡ line on single-line prose | `cursorless/resolve.py:48`; JS: `:14569` |
| `boundedNonWhitespaceSequence` | 🟡 degenerate | JS handler ships (`js/prose_resolve_targets.js:19219`) but on space-joined prose the bounding never differs from `nonWhitespaceSequence` | ref `docs/BUNDLE_REST_SCOPE.md §1` bundle inventory table |
| `glyph` | 🟠 applicable, not shipped | JS handler ships in bundle at `:14756`; no grammar wiring, no Python route; see §4 for decision | `docs/BUNDLE_REST_SCOPE.md` (unmentioned surface) |
| `customRegex` | 🟠 applicable, not shipped | JS handler at `:14747`; no user-facing vocabulary; see §4 | (unmentioned surface) |
| `character` (mid-token) | 🟠 applicable, not shipped as a distinct scope | requires mid-token cursor model per `docs/POTENTIALLY_MISSED.md §L` | see §4 OQ2 |
| `section` (markdown headings) | 🟠 applicable-if-multi-line | requires paragraph structure the buffer lacks in the common case; JS bundle would need `sectionLevelOne`..`Six` too | upstream `PartialTargetDescriptor.types.ts:139-145` |
| Code/tree-sitter: `argumentOrParameter`, `anonymousFunction`, `attribute`, `branch`, `class`, `className`, `collectionItem`, `collectionKey`, `comment`, `private.fieldAccess`, `functionCall`, `functionCallee`, `functionName`, `ifStatement`, `instance`, `list`, `map`, `name`, `namedFunction`, `regularExpression`, `statement`, `type`, `value`, `condition`, `selector`, `private.switchStatementSubject`, `unit` (27 total) | ❌ inapplicable | require language server or tree-sitter grammar; no analogue in prose | upstream `:114-148` |
| `section` / `sectionLevel{One..Six}` | 🟠/❌ mixed | markdown headings — applicable if multi-line paste/recall; degenerate on the common single-line case | upstream `:139-145` |
| XML: `xmlBothTags`, `xmlElement`, `xmlEndTag`, `xmlStartTag` | ❌ inapplicable | no XML/JSX tags in prose | upstream `:149-152` |
| LaTeX: `part`, `chapter`, `subSection`, `subSubSection`, `namedParagraph`, `subParagraph`, `environment` | ❌ inapplicable | LaTeX-only per upstream comment `:153` | upstream `:154-160` |
| `notebookCell` | ❌ inapplicable | Jupyter-host only | upstream `:173` |
| `command` | ❌ inapplicable | talon command scope (host-editor talon files); prose-overlay is called BY talon | upstream `:175` |

## §3. Category rationale

- **✅ shipped:** every entry is wired end-to-end through either
  `cursorless/resolve.py:_scope_regex` / `_scope_word` /
  `_scope_surrounding_pair` (Python fallback) **and** the JS bundle's
  `ScopeHandlerFactoryImpl` (per `docs/BUNDLE_REST_SCOPE.md §1`). The
  three prose extensions (`string`, `number`, `email`) live only in the
  Python `_REGEX_SCOPE_PATTERNS` map and reach the JS bundle via
  `customRegex` translation when JS resolver is on.

- **🟡 degenerate:** `line`, `document`, `paragraph` all collapse to the
  whole buffer via `_WHOLE_BUFFER_SCOPE_TYPES`. Users CAN speak "chuck
  file" and "chuck line" and both work — but the distinction is
  semantically invisible. `boundedNonWhitespaceSequence` behaves
  identically to `nonWhitespaceSequence` on space-joined tokens because
  the bounding whitespace *IS* the token separator; no interior
  whitespace exists to bound against.

- **🟠 applicable, not shipped:** `glyph` (grapheme scope — prose has
  emoji/accented chars; JS handler exists in the bundle already but no
  grammar reaches it), `customRegex` (needs a vocabulary source — see
  §4 OQ1), mid-token `character` (blocked on cursor model — see §4
  OQ2), and multi-line `section` (headings — degenerate on single-line
  prose but reachable on paste/history-recalled multi-line buffers).

- **❌ inapplicable:** these belong to code editing under a language
  server or tree-sitter grammar. Prose has no syntax tree, no XML tags,
  no LaTeX environments, no notebook cells, no function definitions.
  Wiring them would be a category error — the resolver would have
  nothing to return.

- **⚠️ ambiguous:** enumerated in §4 as open decisions.

## §4. Ambiguous / decision-needed scopes

- **`glyph`** — cursorless grapheme scope. Prose has graphemes (emoji,
  accented characters). Bundle handler already ships at
  `js/prose_resolve_targets.js:14756`. The decision is not "can we ship
  it" but "does anyone want it on a token-oriented buffer?" A user
  saying "take glyph a in air" seems niche given `character` already
  aliases to token-level for the common case. **Recommend: defer until
  a user request lands** — the JS surface exists so wiring is a
  grammar-only PR when someone asks.

- **`customRegex`** — spoken via user configuration in cursorless-talon.
  Applicable to prose in principle. The decision is *who authors the
  regex vocabulary* — cursorless-talon reads user-config regex maps,
  and prose-overlay could ride cursorless-talon's plumbing directly
  (same OQ2=YES composable-dispatch pattern as `docs/BUNDLE_REST_SCOPE.md §7`).
  **Recommend: defer; unlock when a user config emerges**. Zero-cost
  once someone has a use case.

- **Mid-token `character` scope** — currently our `character` scope
  aliases to the token containing the anchor (see
  `_WORD_SCOPE_TYPES` at `cursorless/resolve.py:49`). Cursorless's
  `CharacterScopeHandler` (`~/code/cursorless/packages/cursorless-engine/src/processTargets/modifiers/scopeHandlers/CharacterScopeHandler.ts`)
  is character-granular. Wiring mid-token `character` requires a
  mid-token cursor render (`docs/POTENTIALLY_MISSED.md §F` — "mid-
  token cursor render") AND a mid-token gap addressing model on the
  buffer side. **Recommend: block on the cursor-model widening;
  currently returns a working token-level result which is not wrong,
  just coarse.**

- **`paragraph` explicit-support gesture** — should we ship paragraph
  as a *distinct* semantic even though degenerate == document today?
  Argument for: users can speak "paragraph" and it works, no
  surprise, forward-compatible when paste introduces multi-line
  content. Argument against: same runtime path as `document`, so no
  user-visible benefit today. **Recommend: leave it in the shipped
  `_WHOLE_BUFFER_SCOPE_TYPES` set as we do today — no user-visible
  regression, low-effort forward compat.** (This is already how it
  works.)

## §5. Recommended next-step scopes to ship

Ranked by user value × implementation cost:

1. **`glyph`** — **S** effort. JS handler already in the bundle;
   only grammar routing is missing. Would need to confirm the composable
   `<user.cursorless_target>` at `prose_overlay_cursorless.talon:47`
   captures the `{type: "glyph", character: "x"}` variant that
   cursorless-talon emits, same OQ2=YES pattern. Value: modest — enables
   emoji/accent addressing that the token-level model can't reach today.
   Ship trigger: someone asks for it.

2. **`customRegex`** — **S** effort assuming user-config plumbing.
   Composable-dispatch route very likely works (variant of the
   `cursorless_modifier` union). Value: HIGH for the one user who
   wants a custom prose scope; zero for everyone else. Ship trigger:
   user config exists.

3. **Multi-line `section` (markdown headings)** — **M** effort. Would
   need a paragraph-cache aware handler on the JS side and a decision
   on what "section" means when history-recall drops a multi-heading
   blob into the buffer. Value: modest but real for buffer-paste flows.
   Blocked until the cursor model + paragraph-cache design
   (`docs/VIEWPORT_RESEARCH.md`) settles.

Everything else applicable-not-shipped either (a) requires substantial
infrastructure not yet built (mid-token cursor for character scope) or
(b) is inapplicable per §2.

## §6. Non-goals — scopes we explicitly won't ship

Matches `docs/FEATURE_PARITY.md §10` out-of-scope discipline. Every entry
here is `❌ inapplicable` in §2:

- **Tree-sitter code scopes** — `argumentOrParameter`, `anonymousFunction`,
  `attribute`, `branch`, `class`, `className`, `collectionItem`,
  `collectionKey`, `comment`, `functionCall`, `functionCallee`,
  `functionName`, `ifStatement`, `instance`, `list`, `map`, `name`,
  `namedFunction`, `regularExpression`, `statement`, `type`, `value`,
  `condition`, `private.fieldAccess`, `private.switchStatementSubject`,
  `selector`, `unit`. Prose has no syntax tree.
- **XML/JSX scopes** — `xmlBothTags`, `xmlElement`, `xmlEndTag`,
  `xmlStartTag`. No tags.
- **LaTeX scopes** — `part`, `chapter`, `subSection`, `subSubSection`,
  `namedParagraph`, `subParagraph`, `environment`. No LaTeX.
- **Notebook** — `notebookCell`. No notebook host.
- **Talon** — `command`. Prose-overlay is called BY talon; it doesn't
  address other talon files.

## §7. Open questions

- **OQ1.** [customRegex] Who authors the regex vocabulary for prose
  users? Ride cursorless-talon's user-config plumbing, or ship a
  prose-overlay-specific map (e.g. extending
  `_REGEX_SCOPE_PATTERNS` at `cursorless/resolve.py:50`)?
- **OQ2.** [character scope] Does prose need a mid-token character
  scope? The current alias-to-token behavior is not wrong, but it
  blocks cursorless commands like "take second character air" from
  reaching char-granular semantics. Blocked on mid-token cursor render
  per `docs/POTENTIALLY_MISSED.md §F`.
- **OQ3.** [paragraph on multi-line paste] When history-recall lands a
  multi-line buffer, should `paragraph` scope split on blank lines
  (cursorless's `ParagraphScopeHandler` behavior) or keep the
  degenerate whole-buffer behavior for symmetry with the single-line
  case? Behavior differs in JS bundle (splits) vs Python fallback
  (whole buffer) — likely another asymmetric gap per the
  `docs/SUBWORD_INVESTIGATION.md` precedent.
- **OQ4.** [glyph shipping] Does the composable
  `<user.cursorless_target>` capture actually flow the
  `GlyphScopeType` variant end-to-end? OQ2=YES in
  `docs/BUNDLE_REST_SCOPE.md §7` was validated statically for
  SimpleScopeType and SurroundingPair — GlyphScope was not audited.
  Quick static check needed before ranking §5 #1 as shippable-today.
- **OQ5.** [`section` multi-line reachability] What triggers
  paragraph structure to become non-degenerate — only paste/history?
  Or should dictated `\n` (via a future "new line" verb) count?
  Currently no wired path emits multi-line dictation.
