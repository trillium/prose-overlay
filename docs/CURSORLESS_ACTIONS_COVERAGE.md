# Cursorless Actions Coverage (Layer 7)

> Feature-parity report for `scripts/headless_verify/layer7_cursorless_actions.py`.
> Companion to `docs/CURSORLESS_FIXTURE_HARNESS_SCOPE.md` (Layer 6 charter).
> Auto-generatable from the layer's own coverage-summary block — the counts
> at the head of each section are copy-pasted from a fresh run.

## What Layer 7 is (and isn't)

Layer 7 walks every fixture under
`tests/cursorless-upstream/data/fixtures/recorded/actions/*.yml`, filters to
the subset our JS bundle can geometrically process, calls
`globalThis.proseRunAction` from `js/prose_actions.js`, applies the returned
edit plan in pure Python, and asserts the resulting `documentContents` +
cursor active-char match the fixture's `finalState`.

Different scope from Layer 6:

* **Layer 6** (`hatTokenMap/*.yml`) — verifies our hat *allocator* produces
  the same `<color>.<letter>` → token-range map that cursorless does. Reads
  only `initialState.marks`.
* **Layer 7** (`actions/*.yml`) — verifies our *action pipeline*
  (mark → target range → edit plan → applied buffer) produces the same
  `finalState.documentContents` + cursor as cursorless. Reads the full
  command tree plus `initialState` and `finalState`.

Layer 7 is **explicitly MVP-scoped** — feature-parity work on the shim/
resolver is deferred. When a fixture demonstrates a real behavioral gap
(text mismatch, cursor divergence), the row still marks `[x]` with a
`[~ PARTIAL]` prefix + DIM diff line rather than fail-closing. The goal is
"surface every gap in one report," not "block the suite until every gap is
fixed."

## Coverage snapshot (2026-07-01)

```
Total fixtures walked:      188
[x] full pass:              4   (green)
[~] partial (state divergence with diff): 11
[!] bundle-error:           0
[skip] unsupported action:  125
[skip] non-plaintext:       38
[skip] multiline:           9
[skip] complex target/mod:  1
[skip] other:               0
                                     total skipped = 173
```

Runnable = 15 (4 full-pass + 11 partial). Skip = 173.

## What passes today

| Fixture | Action | Notes |
|---|---|---|
| `bringAirAfterAir.yml` | `replaceWithTarget` | `insertionMode: after` — bundle wraps source text with a leading space delimiter and applies closedClosed cursor-shift semantics (cursor at 1 stays at 1 because insert lands at cursor position, not before it). See gap-fix note below. |
| `bringAirBeforeAir.yml` | `replaceWithTarget` | `insertionMode: before` — bundle wraps source text with a trailing space delimiter; cursor at 1 shifts rightwards by insert length (2) to 3. See gap-fix note below. |
| `cloneToken4.yml` | `insertCopyAfter` | Cursor lands in the same char position after `containingScope:token` clone happens to align our end-of-token cursor with cursorless's. |
| `cloneUpToken3.yml` | `insertCopyBefore` | Same alignment coincidence with `containingScope:token` upstream clone. |

Everything else in the runnable set matches `finalState.documentContents`
but diverges on cursor position or delimiter placement — see the gap
sections below.

## Actions currently exercised by Layer 7

| Action | Runnable fixtures | Full pass | Partial |
|---|---|---|---|
| `replaceWithTarget` | 4 | 2 | 2 |
| `insertCopyAfter` | 5 (of 8 plaintext-single-line) | 1 | 4 |
| `insertCopyBefore` | 5 (of 8 plaintext-single-line) | 1 | 4 |
| `wrapWithPairedDelimiter` | 1 | 0 | 1 |

Not yet exercised (either allow-listed as shipped but no simple fixture
survives the MVP filter, or JS bundle lacks the geometry):

| Action | Reason no fixture reaches the executor |
|---|---|
| `remove` | Every plaintext single-line `remove` fixture uses `containingScope:token` + a mark, and marks combined with modifiers land in the "complex target" skip bucket. Trivial to unblock by handling `mark + containingScope:token` (collapse to mark's own range if it already IS a whole token). |
| `setSelection`, `setSelectionBefore`, `setSelectionAfter`, `clearAndSetSelection` | Same as `remove` — every simple plaintext fixture has a modifier chain. |
| `moveToTarget` | All fixtures multiline. |
| `reverseTargets`, `swapTargets` | Fixtures use range-target grammar (`{type: range, ...}`) — MVP resolver skips ranges. |

## Feature gaps identified by the harness (top 5)

Ordered by impact — a gap that unblocks many fixtures ranks higher.

### 1. `bring` does not insert a space padding at token boundaries — FIXED

Fixtures: `bringAirBeforeAir`, `bringAirAfterAir` — previously produced
`"aa"` where cursorless produces `"a a"`.

Root cause: our JS bundle only received the pre-collapsed destination range
from Python and had no way to know whether the collapse came from a
`before` / `after` / `to` `insertionMode`. Upstream `DestinationImpl.
constructChangeEdit` at `packages/cursorless-engine/src/processTargets/
targets/DestinationImpl.ts:87-107` inspects the mode and wraps the text
with `insertionDelimiter` (a single space for plaintext token targets) via
`getEditText` — that's what preserves the token boundary.

Fix (2026-07-01):

* `packages/cursorless-engine/src/actions/proseActionsStandalone.ts` —
  `TargetObj` grows optional `insertionMode` + `insertionDelimiter` fields;
  new `prepareDestChange` helper mirrors upstream's before/after collapse +
  delimiter wrap. `actionReplaceWithTarget` and `actionMoveToTarget` route
  through it. Legacy 4-arg callers (the shim's live `prose_overlay_
  bring_move` path — cursor-gap destination, no mode) get the pre-fix
  behaviour verbatim.
* `scripts/headless_verify/layer7_cursorless_actions.py` —
  `_resolve_destination` now returns `(base_range, insertion_mode)` without
  collapsing; the bundle handles the collapse + wrap. `_target_obj` grows
  a keyword `insertion_mode=` param.
* Cursor semantics for before/after: `actionReplaceWithTarget` now shifts
  the initial cursor through the insert using `closedClosed` selection
  semantics (insert at position P shifts cursor at C rightwards by insert
  length iff P < C). Matches upstream `performEditsAndUpdate
  FullSelectionInfos`. This is what lands `bringAirBeforeAir`'s cursor at
  3 and `bringAirAfterAir`'s at 1.

Related but out of scope for this fix: `bringAirToEndOfAir` and
`bringAirToStartOfAir` still `[~ PARTIAL]` on cursor (text OK) — those use
`insertionMode: to` which takes the range verbatim and lands the cursor at
the leading edge of the replaced range. Upstream leaves the cursor at the
END of the replaced region — a symmetric shift-through-edits calculation
but distinct math from the before/after case. Tracked as gap #5 below.

### 2. Cursor position after `insertCopyAfter/Before` diverges

Fixtures: `cloneToken`, `cloneToken2/3/5`, `cloneHarp`, `cloneUpToken`,
`cloneUpToken2/4/5`, `cloneUpHarp`, `voidWrapAir` — text matches, cursor
lands at bundle-natural position (immediately after the inserted text),
cursorless leaves cursor at fixture-computed position (usually preserving
the character offset within the newly-cloned word).

Concretely for `cloneToken2` (doc `"hello"`, cursor at 3, action clones
whole token): bundle puts cursor at 6 (start of second `hello`), fixture
expects 9 (position 3 in the second `hello`, mirroring the original
in-token offset).

Fix: add a `postAction: preserveCursorRelative` option to the bundle that
carries the relative cursor position across the insert.

### 3. `wrapWithPairedDelimiter` cursor position

Fixture: `voidWrapAir` — text matches (`" aaa "`), cursor at 1 (bundle)
vs 4 (fixture). Cursorless's convention for wrap: cursor lands *inside*
the wrap at the position it was pre-wrap, offset by the left-delimiter
length. Our bundle collapses to the start of the wrapped range.

Fix: adjust bundle's wrap newSelection to `(pre-cursor + left.length)`
instead of `left.length` alone.

### 4. `containingScope:character` modifier not supported

Fixture: `changeNextInstanceChar` (single-fixture bucket). Skips with
`MVP:containing-scope:character`. Would need character-scope reduction
(find the character at cursor). Trivial to add if we ever surface a
per-character action, but no shipped action uses it, so low priority.

### 5. `bring air to end of air` cursor semantics

Fixtures: `bringAirToEndOfAir`, `bringAirToStartOfAir`. Text matches
(`"aa"`), cursor 0 or 1 vs expected 2. Similar to gap #2 — the bundle
places cursor at insertion point rather than at the end of the newly
inserted content.

Fix: same as gap #2 — add relative-cursor preservation to insertion
edits.

## Top unsupported actions (fixture-count order)

These are shipped in cursorless but not in our bundle. Layer 7 silently
DIM-skips them via the allow-list. Landing any of them (in
`js/prose_actions.js` + `cursorless/resolve.py:_SUPPORTED_SIMPLE_ACTIONS`
+ Layer 7's `_SHIPPED_ACTIONS`) unlocks fixtures automatically.

| Fixture count | Action | Notes |
|---|---|---|
| 18 | `deselect` | Selection ops — needs multi-cursor model. Deferred. |
| 18 | `editNewLineAfter` | Prose flat model + newline don't compose. Explicit OOS. |
| 16 | `editNewLineBefore` | Same. |
| 11 | `joinLines` | Same — line concept. |
| 8 | `pasteFromClipboard` | Requires clipboard bridge. Tracked in
`docs/GRAMMAR_STRUCTURE_PARITY.md`. |
| 4 | `rewrapWithPairedDelimiter` | VSCode-only (round-trips current pair). Explicit OOS. |
| 3 | `breakLine` | Line semantics. |
| 2 | `highlight`, `replace`, `editNewLine*`, `addSelection*` | Various. |
| 1 | `outdentLine`, `indentLine`, `flashTargets`, `experimental.*`, `getText`, `findIn*`, `randomizeTargets` | Long tail. |

## How to extend Layer 7

**Adding support for a modifier/target shape** (unblocks fixtures without
touching the bundle): edit `_resolve_primitive_target` /
`_resolve_destination` in `layer7_cursorless_actions.py`. Every failing
resolution raises `_TargetResolveError` with a specific tag — the tag
becomes the DIM skip reason, which becomes the "top feature gaps" bucket
in the coverage report.

**Adding a new shipped action** (unblocks fixtures because the bundle now
handles them): update three lists in lockstep, in this order:

1. `js/prose_actions.js` — ship the action geometry.
2. `cursorless/resolve.py:_SUPPORTED_SIMPLE_ACTIONS` — register in the
   shim's simple-action allow-list.
3. `scripts/headless_verify/layer7_cursorless_actions.py:_SHIPPED_ACTIONS` —
   register in Layer 7's allow-list so fixtures for that action shift
   from `[skip] unsupported action` to `[x]` / `[~ PARTIAL]`.
4. `scripts/headless_verify/layer2_bundle.py:ACTIONS_MUST_HAVE` — this
   is the L2.9 audit that verifies the bundle ships the action.

**Filing a bundle-side bug** discovered by Layer 7: add a section to
`docs/BUNDLE_REST_SCOPE.md` titled "L7 finding: <fixture> <divergence>"
and reference the fixture name. Layer 7's job is to *find* the gaps, not
close them.

## Non-goals

* **`finalState.marks` re-allocation.** Cursorless recomputes hats after
  edits; our bundle does that in a separate path (`proseAllocateHats` —
  Layer 6's territory). Comparing final marks here would double-count
  Layer 6 coverage.
* **Multi-line semantics.** Our JS bundle is line-agnostic — any fixture
  where the fixture's `documentContents` or `finalState.documentContents`
  contain internal newlines DIM-skips. Adding line semantics is a large
  bundle-side effort; Layer 7 will pick up those fixtures for free once
  the bundle catches up.
* **`ide.flashes`.** Fixtures record which ranges cursorless flashed in
  the editor. Prose overlay's flash pipeline (`ui/actions_flash.py`) is
  covered by Layer 3 dispatch and doesn't need per-fixture comparison.

---
*Regenerate the coverage snapshot at the top of this doc by running
`python3 scripts/headless-verify.py 2>&1 | grep -A 30 "L7 fixture-harness"`
and pasting the block.*
