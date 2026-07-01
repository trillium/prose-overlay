# Cursorless fixture-harness scope

Scope-only doc — decides how prose-overlay's headless test suite can borrow cursorless's existing test files to verify our bundled subset of the engine. No implementation, no source edits.

Anchors: bundle allocator = `~/code/cursorless/packages/cursorless-engine/src/util/allocateHats/proseStandalone.ts`, resolver = `~/code/cursorless/packages/cursorless-engine/src/actions/proseTargetsStandalone.ts`, actions = `~/code/cursorless/packages/cursorless-engine/src/actions/proseActionsStandalone.ts`. Prose-overlay test layers live under `~/code/prose-overlay/scripts/headless_verify/`.

## 1. Cursorless test-surface inventory

### 1a. Recorded YAML fixtures (`~/code/cursorless/data/fixtures/recorded/`)

3256 fixture `.yml` files across 30 subdirectories. Distribution by category:

| Category | Count | Plaintext subset (no tree-sitter) |
|---|---:|---:|
| `recorded/actions/` | 172 | 68 |
| `recorded/selectionTypes/` | 114 | 86 |
| `recorded/implicitExpansion/` | 98 | 77 |
| `recorded/relativeScopes/` | 77 | 47 |
| `recorded/compoundTargets/` | 49 | 35 |
| `recorded/subtoken/` | 46 | 15 |
| `recorded/itemTextual/` | 43 | 37 |
| `recorded/inference/` | 36 | — |
| `recorded/updateSelections/` | 35 | 34 |
| `recorded/positions/` | 35 | 28 |
| `recorded/hatTokenMap/` | 35 | 31 |
| `recorded/everyRange/` | 35 | 22 |
| `recorded/queryBasedMatchers/` | 28 | tree-sitter only |
| `recorded/marks/` | 14 | 2 |
| `recorded/headTail/` | 10 | ~all |
| … remaining 15 subdirs | small tails | mixed |
| **languages/*** | 1300+ | 0 (tree-sitter host required) |

Only the `recorded/` tree is candidate material for prose-overlay reuse; `languages/`, `parseTree/`, `surroundingPair/{parseTreeParity,html}/`, `actions/{insertEmptyLines,snippets}/` all depend on the VS Code + tree-sitter host we do not carry.

### 1b. Unit tests (`packages/*/src/**/*.test.ts`)

56 files total across cursorless packages, none of them under `test-harness` (harness only runs mocha + fixtures). Breakdown of the 18 `cursorless-engine` unit-tests (line counts from `find … -exec wc -l`):

- Allocator internals — `util/allocateHats/getRankedTokens.test.ts` (181), `util/allocateHats/maxByFirstDiffering.test.ts` (40). **Directly applicable** — verifies internals our `prose_allocate_hats.js` bundle wraps.
- Tokenizer — `tokenizer/tokenizer.test.ts` (183), `tokenGraphemeSplitter/tokenGraphemeSplitter.test.ts` (312). **Partially applicable** — our bundle re-implements TokenGraphemeSplitter inline with a static config (`proseStandalone.ts:47`).
- Scope-handler base — `processTargets/modifiers/scopeHandlers/BaseScopeHandler.test.ts` (187). **Directly applicable** to the resolver bundle.
- Grammar/lexer — `customCommandGrammar/{lexer,grammarScopeType}.test.ts` (115). **Not applicable** — prose-overlay doesn't parse Talon custom-command grammar.
- Snippet — `snippets/snippetParser.test.ts` (21), `core/mergeSnippets.test.ts` (348). **Not applicable** — snippets not shipped.
- Spoken-form generation — `generateSpokenForm/*.test.ts` (143). **Not applicable** — prose-overlay uses Talon's captured spoken form.
- TreeSitter — `languages/TreeSitterQuery/*.test.ts` (503 total). **Not applicable**.
- Misc — `test/{sentenceSegmenter,subtoken,spokenForms.talon}.test.ts` (186 total). Mixed; `spokenForms.talon.test.ts` needs a Talon file.

`packages/common/` has 7 more unit tests (mostly `Range`/`Position`/`ide-types`), all directly applicable but tiny — we already trust these implicitly via bundle import.

`packages/cursorless-vscode-e2e/` has 25 test files including `recorded.vscode.test.ts` (the harness that loops all recorded fixtures — quoted below in §3). Requires VS Code — **not directly runnable**, but the runner code is the recipe.

### 1c. Test-harness package (`packages/test-harness/`)

Small — `runAllTests.ts` (70 lines) is a mocha driver that globs `**/*.test.cjs`, filters by test type (unit/vscode/talon), and runs them. No fixture-loading code — that lives inline in `recorded.vscode.test.ts` and in `packages/test-case-component/src/loadFixture.ts` (69 lines, generates HTML previews of fixtures for the docs site).

### 1d. `docs/contributing/proposals/`

One proposal — `scope-support-rpc.md` — nothing test-related. Not a source of fixtures.

## 2. Fixture format (verbatim sample)

Fixtures are **pure-data YAML** — no TypeScript imports required. Sample from `data/fixtures/recorded/hatTokenMap/takeHarp.yml`:

```yaml
languageId: plaintext
command:
  version: 1
  spokenForm: take harp
  action: setSelection
  targets:
    - type: primitive
      mark: {type: decoratedSymbol, symbolColor: default, character: h}
initialState:
  documentContents: hello world
  selections:
    - anchor: {line: 0, character: 11}
      active: {line: 0, character: 11}
  marks:
    default.h:
      start: {line: 0, character: 0}
      end: {line: 0, character: 5}
finalState:
  documentContents: hello world
  selections:
    - anchor: {line: 0, character: 0}
      active: {line: 0, character: 5}
```

Every fixture carries: `languageId`, `command` (with `action`, `targets`, `spokenForm`), `initialState` (`documentContents`, `selections`, `marks`, optional `clipboard`, `thatMark`, `sourceMark`), `finalState` (same shape, plus `thatMark`/`sourceMark`/`clipboard` if applicable), optional `thrownError`, `ide` (spy captures), `fallback`, `returnValue`. Per-subdir `config.json` toggles are minimal — `{"isHatTokenMapTest": true}` for hat-only assertions, `{"isDecorationsTest": true}` for the decorations subset.

The rewritten inputs match cursorless's `TestCaseFixtureLegacy` (`packages/common`). Our resolver bundle already speaks the `TargetDescriptor` half of this shape (see `layer5_parity.py:92-101`). The bundle **does not** speak the `finalState` shape — asserting on it requires either a small adapter (translate our `{edits, newSelections}` into a synthetic `finalState`) or a shim that applies the edits to `documentContents` before comparing.

## 3. Runner recipe (from cursorless E2E)

`packages/cursorless-vscode-e2e/src/suite/recorded.vscode.test.ts:70-243` shows the exact replay loop cursorless itself uses:

1. `yaml.load(readFile(fixturePath))` → `TestCaseFixtureLegacy`.
2. Open editor with `fixture.initialState.documentContents` (`languageId` from the fixture).
3. Set `editor.selections` from `fixture.initialState.selections`.
4. `hatTokenMap.allocateHats(getTokenHats(fixture.initialState.marks, editor))` — bootstrap the hat map from recorded coords.
5. `runCursorlessCommand({ ...fixture.command, usePrePhraseSnapshot: false })`.
6. `takeSnapshot()` → compare against `fixture.finalState` via `assert.deepStrictEqual`.

Our shape is smaller — we skip the VS Code editor, skip pre-phrase snapshot, and our bundle emits an edit plan rather than mutating a document. Applying step 6 requires the small edits-to-final-state applier described above.

## 4. Mechanism options

### (A) Copy fixtures + Python fixture loader

Copy (or submodule) `data/fixtures/recorded/` into prose-overlay `tests/cursorless-fixtures/`. Add `scripts/headless_verify/layer6_cursorless_fixtures.py` that walks selected subdirs, spawns bun with our `prose_actions.js` / `prose_resolve_targets.js` bundles, applies the emitted edits to `documentContents`, and asserts on `finalState.documentContents` + `finalState.selections`.

- **Pros:** All-Python driver stays in our existing layer style. Selection is a directory walk with a skip-list. Fixtures are pure YAML → no cursorless TypeScript runtime needed. Diff-friendly — we can commit a `SKIPS.txt` per unshipped-feature reason.
- **Cons:** Copying 500-3000 fixtures is a big commit; we need to pin a cursorless commit and re-copy periodically. PyYAML dep (already available in the parity harness path).

### (B) Bun-side fixture runner, invoked from Python

Add `scripts/headless_verify/cursorless_fixtures.ts` that imports fixtures from `../../cursorless/data/fixtures/recorded/**/*.yml` (relative path to sibling repo), loads our bundle, runs it against each fixture, prints JSON results. `layer6_cursorless.py` shells out to bun and asserts.

- **Pros:** No fixture copy — fixtures always at cursorless HEAD. YAML parsing lives on the JS side where the bundle already runs.
- **Cons:** Hard dependency on the `~/code/cursorless/` checkout existing at a known path. CI would need to clone it. Any cursorless commit that renames `data/fixtures/recorded/` or changes fixture shape silently breaks us.

### (C) Direct import + subprocess

Like (B) but bun `require()`s fixture files individually inside a subprocess call per fixture. Rejected — slower than (B) with no upside; same coupling.

### (D) JSON snapshot emitted at bundle-build time

Extend `scripts/build-js.ts` with `--emit-fixtures` that walks cursorless's fixtures, filters to shipped-action + plaintext subsets, normalizes each into `{ input, expectedFinalState }`, and writes `tests/cursorless-fixtures.json`. Python layer loads that JSON, runs bundle, asserts.

- **Pros:** No YAML dep in Python. Snapshot commit is a single generated file. Selection logic runs at build time — easy to skip actions we don't ship.
- **Cons:** Snapshot goes stale until we re-emit; two build modes (regular + `--emit-fixtures`) to maintain. Hides drift (silent staleness).

### Recommendation: (A) + submodule pin

Copy-in via git submodule pointing at a pinned cursorless commit. Concretely: `git submodule add https://github.com/cursorless-dev/cursorless tests/cursorless-upstream` and access `tests/cursorless-upstream/data/fixtures/recorded/`. Combines (A)'s Python-driver simplicity with (B)'s no-manual-copy. Update ritual is `cd tests/cursorless-upstream && git checkout <newer-sha>` + re-run the layer. Skip-list keyed on feature area lives in `layer6_cursorless_fixtures.py` alongside a per-fixture reason.

## 5. Coverage delta

Per `docs/FEATURE_PARITY.md:82-108`, prose-overlay currently has ~42 live-only rows and ~25 headless-tested. The most substantive live-only bucket the fixture harness can address:

- **§3a–§3f Cursorless verb end-to-end** — 5 rows (chuck/take/pre/post/bring/move/clone/swap/reverse). Any plaintext fixture whose `command.action.name` is in our shipped set (`setSelection`, `insertCopyAfter`, `insertCopyBefore`, `remove`, `replaceWithTarget`, `moveToTarget`, `swapTargets`, `reverseTargets`, `wrapWithPairedDelimiter`, `setSelectionBefore`, `setSelectionAfter`, `clearAndSetSelection`) becomes an integration test we can't write today.
- **§4 token / range selection** — `recorded/hatTokenMap/` (31 plaintext) and `recorded/selectionTypes/` (86 plaintext) exercise resolver + mark bootstrapping. Directly aligns with what Layer 5 does today, but at a much bigger scale (117 fixtures vs. 20 rows).

Ballpark: **meaningful** — from ~37% headless ratio to a plausible **~55-65%** if we wire the plaintext-shipped-action subset (roughly 200 fixtures across `actions`, `selectionTypes`, `hatTokenMap`, `positions`, `headTail`, `implicitExpansion`, `updateSelections`). Not dramatic (we still can't test render / voice / grammar surfaces), but the single biggest headless-coverage jump available.

## 6. Risks

1. **Fixture drift** — cursorless HEAD moves, fixture shape changes silently. Mitigation: pin the submodule; document the update ritual in `HEADLESS_VERIFY_PLAN.md`.
2. **False positives from unshipped features** — a fixture using `sortTargets` or `pasteFromClipboard` fails against our bundle for the right reason but wrong reading. Mitigation: **allow-list, not skip-list.** Only run fixtures whose `command.action.{name}` is in our shipped set AND whose `command.targets[*].modifiers[*].type` is in our shipped modifier set. Everything else is silently excluded, not "failing".
3. **Language-host coupling in "plaintext" fixtures** — some plaintext fixtures still call `containingScope` or `everyScope` with `scopeType: {type: nonWhitespaceSequence}` — needs our resolver to handle that scope. Cursorless's `changeEveryPaint.yml` (§2 style) works today but we should sanity-check a first batch.
4. **`finalState` comparison** — our bundle emits edits, not final documents. Building a small edits-applier is a few dozen lines but non-trivial and needs its own tests; a bug there produces false positives. Mitigation: land it as a separate helper with L1 unit tests.
5. **Setup complexity** — full submodule + allow-list + edits-applier + skip-list is 1-2 days. A 3-hour MVP that only exercises `recorded/hatTokenMap/` plaintext (31 fixtures, no edit-applier needed — assertion is against the hat map, not final state) captures a big chunk of the resolver-parity value.

## 7. Recommended incremental path

1. **MVP (3-4h)** — Wire `recorded/hatTokenMap/` plaintext (~31 fixtures). Straight fit for Layer 5's existing shape (mark lookup + target resolution). No edit-applier needed. Emits `L6.hat.*` test IDs. Directly closes §4 token / range selection headless-only rows.
2. **Small next (1d)** — Add `recorded/selectionTypes/` plaintext subset (~86 fixtures) filtered by allow-list to shipped actions. Same runner; still no edit-applier if we assert on `finalState.selections` only for `setSelection` variants.
3. **Medium (2-3d)** — Add edits-applier helper and open up `recorded/actions/` plaintext (~68 fixtures). This is the biggest cursorless-parity win — covers §3a–§3f end-to-end for every plaintext fixture our shipped action set can execute.
4. **Adjacent value (1-2d each)** — `recorded/positions/` plaintext (28), `recorded/headTail/` plaintext (~10), `recorded/updateSelections/` (34). Reuses everything from step 3.
5. **Ideal end-state** — steps 1-4 plus a per-run report at `MEMORY/STATE/cursorless-fixture-coverage.md` breaking down pass/skip/fail by category. Total ~250 fixtures replayed per Layer 6 run.

Highest ROI: **step 3 (recorded/actions/ plaintext)** — that's the "cursorless verb end-to-end" bucket that today has zero headless coverage. Step 1 is the fastest first bite; step 3 is the biggest single payoff.

## 8. Open questions

- **OQ1** — Do plaintext fixtures use scope-handlers our resolver bundle actually supports? Sampling `changeEveryPaint.yml` uses `everyScope{nonWhitespaceSequence}` — is that handled by our bundled `ScopeHandlerFactoryImpl`? Needs a smoke-run of ~5 fixtures before committing to option (A).
- **OQ2** — Cursor state — fixtures include `initialState.selections`; does our bundle read cursor from that path or from `cursorJson` separately? Layer 5 passes cursor via `cursorJson` (`layer5_parity.py:100`) — a fixture adapter must translate.
- **OQ3** — Multi-selection / list targets — `reverseAirAndBatAndCap.yml` uses `type: list` with N elements. Our `proseRunAction` dispatcher routes list-shape via a JSON array in slot `sourceTargetJson` (per `proseActionsStandalone.ts:28-33`). Does the fixture adapter handle that off the bat, or is it a follow-up?
- **OQ4** — `usePrePhraseSnapshot: true` in fixtures — do we need to synthesize a snapshot, or can we always pass `false` (cursorless's own runner does; `recorded.vscode.test.ts:77`)? Sampling suggests `false` is safe.
- **OQ5** — Fixture `thatMark` / `sourceMark` in `initialState` — some fixtures pre-seed stored targets. Prose-overlay's bundle wires an empty `StoredTargetMap` (`proseTargetsStandalone.ts` docstring). Fixtures needing pre-seeded that/source are unrunnable until we widen the bundle or exclude them via allow-list.
- **OQ6** — Cursorless commit-pin cadence — quarterly? On-demand when we bump the bundle? Needs a documented policy.
- **OQ7** — Cursorless has spec-tests too (`packages/*/src/**/*.test.ts`, mocha `.cjs` builds) — is there value in porting the ~2 allocator unit tests (`getRankedTokens.test.ts`, `maxByFirstDiffering.test.ts`, ~220 lines) into a Layer 1.5 that runs their assertions against our bundled allocator? Small effort, would give allocator regression coverage.
