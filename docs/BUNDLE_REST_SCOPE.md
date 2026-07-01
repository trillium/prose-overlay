# Bundle wishlist scope — items #3–#14 (actions + modifiers + inventory test)

> Companion to `docs/BUNDLE_SHAPE_SCOPE.md` (shape/allocation surface — item
> #1, in-flight sibling agent). This doc scopes ACTION + MODIFIER surface +
> the L2 inventory grep test — everything on the corrected bundle wishlist
> EXCEPT shape allocation. See `docs/REBUTTAL_ASSERTIONS.md` and
> `docs/SUBWORD_INVESTIGATION.md` for the audit that produced the wishlist.
>
> Drafted 2026-07-01. Do not implement from this doc without first
> reading the sibling doc — several rebuilds share a bundle entry point.

## §0. Executive summary

12 items scoped. Three natural groupings drive the work:

1. **Actions cluster** (#3 Swap, #4 Paste, #12 Clone, #13 Reverse) → one
   rebuild of `js/prose_actions.js` adds four new action geometries to
   `proseActionsStandalone.ts` + Python dispatchers. Small-to-medium.
2. **Modifiers cluster** (#6 RelativeScope, #7 OrdinalScope, #9 every, #10
   first/last, #11 leading/trailing) → **NO bundle rebuild.** The five
   stages already ship in `js/prose_resolve_targets.js` because
   `proseTargetsStandalone.ts` composes cursorless's `ModifierStageFactoryImpl`
   in full (see §1). Work is grammar routing + Python-fallback parity +
   L5 test rows.
3. **Wrap + inside/outside** (#5 wrap paired, #8 inside/outside on
   surroundingPair) → one action-side rebuild (wrap adds `wrap` geometry)
   plus one modifier wiring (interior — already in resolver bundle, needs
   grammar + Python-fallback handler). Medium.

Item #14 (L2 grep test) is a headless-verify addition. Small; ship first.

Net: **3–5 PRs** cover #3–#14, of which only ONE requires a resolver-bundle
rebuild (never — the resolver is already complete) and TWO require actions-
bundle rebuilds (Cluster A + Wrap). Rest is grammar + Python-parity + tests.

---

## §1. Current-state bundle inventory

Same starting point as `docs/BUNDLE_SHAPE_SCOPE.md §1`; see there for the
top-level view of `scripts/build-js.ts:35-46`. This section covers the
action and modifier surface.

**Actions bundle (`js/prose_actions.js`, 275 lines).** Built from
`proseActionsStandalone.ts` (`scripts/build-js.ts:38`). This bundle is a
**stripped rewrite**, not a cursorless import — seven actions hand-written
as pure-string geometries against `proseShim.ts`
(`proseActionsStandalone.ts:83-194`). Shipped: `remove`, `setSelection`,
`clearAndSetSelection`, `replaceWithTarget`, `moveToTarget`,
`setSelectionBefore`, `setSelectionAfter` (`ActionName` union at
`:200-207`). Python caller: `shim/actions_js.py:82-137`.

**Resolver bundle (`js/prose_resolve_targets.js`, 19 554 lines).** Built
from `proseTargetsStandalone.ts` (`scripts/build-js.ts:43`). Unlike the
actions bundle this is a **cursorless import** — it constructs
`TargetPipelineRunner` with the full `ModifierStageFactoryImpl`
(`proseTargetsStandalone.ts:93-97`). Consequence: the bundle already
ships every stage class the wishlist mentions.

| Stage class | Bundle line |
|---|---|
| `EveryScopeStage` | `js/prose_resolve_targets.js:15505` |
| `HeadStage` / `TailStage` | `:15636`, `:15644` |
| `InteriorOnlyStage` / `ExcludeInteriorStage` | `:15819`, `:15828` |
| `LeadingStage` / `TrailingStage` | `:18845`, `:18860` |
| `OrdinalScopeStage` | `:18899` |
| `RelativeScopeStage` | `:19103` |
| `BoundedNonWhitespaceSequenceStage` | `:19219` |
| `WordScopeHandler` | `:14357` (per `docs/SUBWORD_INVESTIGATION.md §1`) |

The modifier cluster does NOT need a resolver rebuild.

**Python resolver (`cursorless/resolve.py`).** `_MODIFIER_HANDLERS` at
`resolve.py:161-167` only knows about `extendThroughStartOf`,
`extendThroughEndOf`, `everyScope`, `containingScope`/`preferredScope`.
Every wishlist modifier (relativeScope, ordinalScope, leading/trailing,
interior) hits the "unknown mod_type falls through" branch
(`resolve.py:159-160`) and returns `(base_idx, base_idx)`
(`resolve.py:186-187`). Same asymmetric-gap pattern as sub-word per
`docs/SUBWORD_INVESTIGATION.md §3` — JS path works; Python fallback
silently degrades.

---

## §2. Per-item scope table

Effort: **S** <1 day, **M** 1–3 days, **L** >3 days. Cursorless refs are to
`~/code/cursorless/packages/...`.

### #3 — Swap action (`swap air with bat`) [R4]

Upstream at `cursorless-engine/src/actions/BringMoveSwap.ts:363-422`; talon
at `~/.talon/user/cursorless-talon/src/actions/swap.py:37-49` marshalling
`{"name": "swapTargets", "target1", "target2"}`; capture
`cursorless_swap_targets` at `swap.py:23-34`. **Bundle:** add
`actionSwap(source, dest, editor)` to `proseActionsStandalone.ts`
(mirror `actionMoveToTarget:161-175` — two replace ops in one
`editor.edit`) and extend the `ActionName` union + switch. **Python:** new
`prose_overlay_swap(target1, target2)` in `shim/actions_cursorless.py`
(pattern of `prose_overlay_bring_move:166-208` but resolving TWO targets)
+ `action_swap` wrapper in `shim/actions_js.py`. **Grammar:** one new
rule in `prose_overlay_cursorless.talon` after line 52 —
`{user.cursorless_swap_action} <user.cursorless_swap_targets>:
user.prose_overlay_swap(cursorless_swap_targets)`. **Tests:** L1 for the
two-op plan; L5 parity row for the two-primitive swap dict;
MANUAL_VERIFICATION row `swap air with drum`. **Effort:** S (~30 LOC JS +
~30 LOC Python). **Deps:** none.

### #4 — Paste at destination (`paste before air`) [R5]

Upstream at `cursorless-engine/src/actions/PasteFromClipboard.ts` (delegates
to `Bring`); talon at `~/.talon/user/cursorless-talon/src/actions/paste.py`
with command `pasteFromClipboard`. **Bundle:** add
`actionPasteAtDestination(dest, text, editor)` where clipboard read happens
Python-side via `clip.text()` and the bundle receives text as a JSON arg;
extend `proseRunAction` signature at `proseActionsStandalone.ts:223-228`.
**Python:** new `prose_overlay_paste_at_destination(destination)` in
`shim/actions_cursorless.py` — read `clip.text()`, dispatch via
`_js.run_action`; extend `shim/actions_js.py:run_action` with
`paste_text: str | None = None`. **Grammar:** one new rule
`{user.cursorless_paste_action} <user.cursorless_destination>:
user.prose_overlay_paste_at_destination(cursorless_destination)`.
**Tests:** L1 with mocked clipboard; MANUAL row: clip="quick", say
`paste before air`, expect `the quick air ball drum echo`. **Effort:** S
(~20 LOC JS + ~40 LOC Python — destination-target has before/after/
start-of/end-of branches). **Deps:** trillium_talon `clip.text` (per
`docs/REBUTTAL_ASSERTIONS.md #3`).

### #5 — WrapWithPairedDelimiter (`round wrap air`) [R6]

Upstream at `cursorless-engine/src/actions/Wrap.ts:20-145`; talon at
`~/.talon/user/cursorless-talon/src/actions/wrap.py:12-28` with command
`wrapWithPairedDelimiter`; delimiter table at
`paired_delimiter.py:28-42` (12 delimiters); wrapper capture at
`paired_delimiter.py:45-56`. **Bundle:** add `actionWrap(target, left,
right, editor)` (simpler than upstream because our buffer is single-line:
emit two `insert` ops per `Wrap.ts:42-52`); extend `proseRunAction` with
`leftJson`/`rightJson`. **Python:** new
`prose_overlay_wrap_with_paired_delimiter(action_name, target,
paired_delimiter)` in `shim/actions_cursorless.py`; wrap under
`commit_start`/`commit_end` (`state.py:347`) to seal as one STRUCTURAL
undo step. **Grammar:** one new rule mirroring cursorless.talon —
`<user.cursorless_wrapper_paired_delimiter> {user.cursorless_wrap_action}
<user.cursorless_target>: user.prose_overlay_wrap_with_paired_delimiter(...)`.
**Delimiter LIST:** decide subset vs full (OQ1) — recommend prose subset
matching `cursorless/surrounding_pair.py:14-22`. **Tests:** L1 for the
two-insert plan; L5 wrap parity row; MANUAL rows `round wrap air` and
`curly wrap fox past bat`. **Effort:** M (~40 LOC JS + ~60 LOC Python +
delimiter decision). **Deps:** none for the shipped action — range
target (`fox past bat`) already works via the resolver.

### #6 — RelativeScopeStage (`next funk`, `third next word`, `take past next word`)

Upstream at `RelativeScopeStage.ts`; **already in bundle** at
`js/prose_resolve_targets.js:19103`. Talon captures at
`~/.talon/user/cursorless-talon/src/modifiers/relative_scope.py:22-85`.
**Bundle:** NONE (verified per `docs/REBUTTAL_ASSERTIONS.md #10`).
**Python:** JS path Just Works because `shim/targets_js.py` forwards the
target dict verbatim. Python-fallback would need a `relativeScope`
handler in `_MODIFIER_HANDLERS`; recommend document as JS-only per
`docs/SUBWORD_INVESTIGATION.md §Recommendations #3` (matches ISC-9
Python-retirement direction). **Grammar:** ZERO new rules **iff**
`<user.cursorless_target>` at `prose_overlay_cursorless.talon:47` flows
relativeScope modifiers through — see OQ2. Cheap check: dictate `take
next word` with the JS resolver on and read the Talon log. **Tests:**
L5 rows for `next word` and `take past next word`; MANUAL rows.
**Effort:** S–M (bundle-zero, but semantic verification against the
`next / past next` anchor-counting subtleties needs care). **Deps:** OQ2
answer gates.

### #7 — OrdinalScopeStage (`take first word`, `take second word this`)

Upstream at `OrdinalScopeStage.ts`; **already in bundle** at
`:18899`. Talon at `ordinal_scope.py:23-74`. Sub-word ordinal (`take
second word this` inside a camelCase token) is the highest-leverage new
spoken form — rides on the same `WordScopeHandler` chain that
`docs/SUBWORD_INVESTIGATION.md` verified. **Bundle:** NONE. **Python:**
JS path Just Works; Python-fallback would need an `ordinalScope` handler
(~20 LOC — `start=0,length=N` for first, `start=-N` for last). Recommend
JS-only stance. **Grammar:** ZERO new rules (same OQ2). **Tests:** L5 row
for `take first word` on std buffer; L5 row for `take second word this`
on `this camelCaseIdentifier` expecting the "Case" sub-range; MANUAL rows.
**Effort:** S. **Deps:** OQ2.

### #8 — inside / outside modifier (`take inside round air`)

Upstream at `InteriorStage.ts`; `InteriorOnlyStage` at
`:15819`, `ExcludeInteriorStage` at `:15828`. Talon at
`~/.talon/user/cursorless-talon/src/modifiers/interior.py:11-15` returning
`{"type": m.cursorless_interior_modifier}`. **Bundle:** NONE. **Python:**
current `_scope_surrounding_pair` at `cursorless/resolve.py:118-124`
returns the outer pair range (that IS the outside variant). Add
`_apply_interior` handler that TRIMS the first and last tokens for
`interiorOnly` and EXPANDS to include delimiters for `excludeInterior`;
wire into `_MODIFIER_HANDLERS`. ~20 LOC. **Grammar:** rides on the
`cursorless_modifier` composition (OQ2). **Tests:** L5 rows for `take
inside round air` and `take outside round air` on `the ( air ball ) drum`
— inside → tokens 2..3, outside → tokens 1..4. Both resolver paths.
**Effort:** S–M (medium if OQ2 forces a shim capture). **Deps:** existing
surrounding-pair support + delimiter translation at
`shim/targets_js.py:82-90`.

### #9 — every scope modifier (`chuck every line`, `take every word`)

Upstream at `EveryScopeStage.ts`; **already in bundle** at
`:15505`. Talon capture at
`~/.talon/user/cursorless-talon/src/modifiers/simple_scope_modifier.py:31-55`.
**Bundle:** NONE. **Python:** `_MODIFIER_HANDLERS` DOES have
`everyScope: _apply_every_scope` (`resolve.py:104-105`), but the impl
returns `(0, len-1)` — wrong shape for the multi-range every semantics
(each scope becomes a separate range). Fix: return a `list[tuple[int,int]]`
with one entry per token (for `every word`); the return type of
`_resolve_target_to_token_range` at `resolve.py:222` is already the
list shape so no cascading changes. **Grammar:** ZERO new rules. **Tests:**
L5 row for `chuck every word` on std buffer expecting 5 separate ranges;
MANUAL row for `take every word`. **Effort:** S. **Deps:** none, but audit
existing L1 tests for anything relying on single-range return.

### #10 — first / last modifiers (`take first word air`)

Semantically covered by OrdinalScope (`ordinal_scope.py:46-68` handles
`cursorless_first_last`). Same bundle presence as #7. **Bundle:** NONE.
**Python:** ships with the OrdinalScope fallback if we build one; JS-only
otherwise. **Grammar:** ZERO new rules. **Tests:** L5 rows for `take
first word` (token 0) and `take last word` (token N-1); sub-word: `take
first word thisIsCamel` → "this". **Effort:** S. **Deps:** rolls into #7.

### #11 — leading / trailing whitespace modifier (`chuck leading trailing of air`)

Upstream at `LeadingStage`/`TrailingStage` (`:18845`, `:18860`). Talon
LIST `cursorless_simple_modifier` at `modifiers.py:5-16` (spoken-forms
CSV populates it). **Bundle:** NONE. **Python:** semantics on a
space-joined single-line prose buffer are degenerate — see OQ3. Document
as JS-only until the semantics are settled. **Grammar:** ZERO new rules
(OQ2). **Tests:** L5 rows after OQ3 answer; may return zero-length
ranges. **Effort:** S–M. **Deps:** OQ3. Low user-value — see §7.

### #12 — Clone action (`clone air`)

Upstream at `cursorless-engine/src/actions/InsertCopy.ts:19-127` — the
`clone` spoken form maps to `insertCopyAfter` (registered in `Actions.ts`).
**Bundle:** add `actionInsertCopyAfter` (and Before) to
`proseActionsStandalone.ts` — geometry: `insert(range.end, " " + srcText)`
for After, `insert(range.start, srcText + " ")` for Before. Add to
`ActionName` union. **Python:** add `insertCopyBefore` /
`insertCopyAfter` to `_SUPPORTED_SIMPLE_ACTIONS` at
`cursorless/resolve.py:30-33`. **Grammar:** ZERO new rules — the composable
`{user.cursorless_simple_action} <user.cursorless_target>` at
`prose_overlay_cursorless.talon:47` already fires once the action name is
in the LIST + bundle. **Tests:** L1 for the JS action; MANUAL `clone air`
on std → `the air air ball drum echo`. **Effort:** S (~20 LOC JS + ~15
LOC Python + enum entry). **Deps:** none.

### #13 — Reverse action (`reverse air past drum`)

Upstream at `cursorless-engine/src/actions/Sort.ts:58-62` — `class Reverse
extends SortBase { sortTexts(texts) { return texts.reverse(); } }`. Applies
to MULTIPLE targets. Registered as `reverseTargets` (`Actions.ts:132`).
**Bundle:** add `actionReverse(targets, editor)` — extract per-target
texts in document order, reverse, write back. Note the multi-target
signature — either batch calls from Python (one `run_action` per range
followed by a swap) or widen the JS signature. Recommend batched call
per R-6. **Python:** new `prose_overlay_reverse(target)` handling list +
range targets. **Grammar:** ZERO new rules (composable rule). **Tests:**
L1 for multi-range reverse; MANUAL `reverse air past drum` on std →
`the drum ball air echo`. **Effort:** S (~25 LOC JS + ~25 LOC Python).
**Deps:** none — but flagged "niche" in the wishlist; low priority per §7.

---

## §3. Item #14 — L2 bundle-inventory grep test

Goal: turn "what's in the bundle" into a green/red diff. New test block
after L2.5 at `scripts/headless_verify/layer2.py:73-76`.

**Handlers to grep.** From §2:

| Bundle | Expected present |
|---|---|
| `js/prose_actions.js` | `proseRunAction`; every `ActionName` union entry from `proseActionsStandalone.ts:200-207`. After clusters land: `swap`, `pasteAtDestination`, `wrap`, `insertCopyBefore`, `insertCopyAfter`, `reverse`. |
| `js/prose_resolve_targets.js` | `EveryScopeStage`, `HeadStage`, `TailStage`, `InteriorOnlyStage`, `ExcludeInteriorStage`, `LeadingStage`, `TrailingStage`, `OrdinalScopeStage`, `RelativeScopeStage`, `WordScopeHandler`, `WordTokenizer`, `CAMEL_REGEX`, `BoundedNonWhitespaceSequenceStage`. After #1 (shape) lands: `HatStyleName`, `enabledHatStyles`, `HatAllocator` (per `docs/BUNDLE_SHAPE_SCOPE.md`). |
| `js/prose_allocate_hats.js` | `proseAllocateHats` (already validated as L2.1). |

**Assertion shape.** Three columns: `PRESENT` / `ABSENT` / `STATUS`. One
`assert` per must-have identifier so a missing one flips exactly one row
red. Use the raw `var NAME = class` pattern because esbuild's IIFE
elides `class NAME` at the top level — see `js/prose_resolve_targets.js:15505`.

```python
with test("L2", "L2.6", "resolver bundle contains all modifier stages"):
    src = pathlib.Path(RESOLVE_JS).read_text()  # add RESOLVE_JS to common.py
    for name in ("EveryScopeStage", "HeadStage", "TailStage", ...):
        assert f"var {name} = class" in src, f"resolver bundle missing {name}"
```

**Fail-closed vs fail-informational.** Recommend **fail-closed** for the
must-have set. If a rebuild silently drops a handler, the test flips red
and blocks merge. For NEW handlers being added by wishlist items #3–#13,
add the assertion in the SAME PR as the handler — the test grows
alongside the bundle. Turns the grep into a rebuild ratchet.

**One escape hatch.** For genuinely optional entries (e.g. `HatAllocator`
before #1 lands), inventory in a separate `L2.N+1` test that PRINTS
without asserting — heads-up without merge block. Promote to must-have
once the corresponding wishlist item ships.

---

## §4. Cluster analysis

- **Cluster A — Actions rebuild (#3 Swap, #4 Paste, #12 Clone, #13
  Reverse).** All four add action geometries to `proseActionsStandalone.ts`.
  One PR: extend `ActionName` union + switch, add four geometries, add
  Python actions, add grammar rules (or lean on the composable rule for
  Clone/Reverse). One bundle rebuild, one Python file change, one talon
  file change. **M**. High leverage: four verbs, one PR.
- **Cluster B — Wrap (#5).** Separate rebuild because it changes the
  `proseRunAction` signature (`left`/`right` args) and introduces delimiter
  LIST wiring. **M**.
- **Cluster C — Modifier grammar routing (#6, #7, #9, #10, #11).** No
  bundle rebuild. One PR: verify target capture flows all five modifier
  types (OQ2), add MANUAL rows, add L5 parity rows for the JS path.
  Python-fallback stance: JS-only per item recommendations. **S**. Very
  high leverage: five modifiers for one PR.
- **Cluster D — inside/outside (#8).** One PR. Add
  `InteriorOnly`/`ExcludeInterior` handling to Python fallback, add L5
  rows, MANUAL row. Independent because it touches surrounding-pair. **S**.
- **Cluster E — L2 inventory test (#14).** One PR. Ratchet before any
  bundle work. **S**.

**Recommended PR order:** E → C → A → D → B. E first because it locks
current state before we change it. C second because it's cheap and
validates the ISC-9 JS-default direction. A/D/B any order after.

**Total: 5 PRs covers items #3–#14.**

---

## §5. Risk register

- **R-1. Edit-plan multi-op ordering.** #3 Swap and #12 Clone share the
  `_apply_edit_plan` path (`shim/actions_cursorless.py:190-206`) with
  existing bring/move. Adding sibling actions that return multi-op plans
  (Swap = 2 replaces, Clone = 1 insert) may hit ordering edge cases the
  existing two-action surface never triggered. Mitigation: L1 tests for
  each new action's edit-plan shape BEFORE wiring the Python dispatcher.
- **R-2. Bundle size.** Actions bundle grows from 275 → ~450 LOC after
  Cluster A. Resolver bundle unchanged. The 1.5× ratio cap in
  `scripts/build-js.ts:94` is on TARGETS-vs-HATS, so actions growth is
  not gated. Monitor gzip.
- **R-3. Grammar collision.** New verbs (`swap`, `paste`, `wrap`, `clone`,
  `reverse`) must not collide with existing prose-overlay rules across
  the 9 `.talon` files. `grep -nE '^clone |^swap |^paste |^wrap |^reverse '
  prose_overlay*.talon` returns zero hits today — safe. Note that `paste`
  in cursorless.talon is a different context so no runtime collision.
- **R-4. Python-fallback asymmetry.** Same pattern as sub-word per
  `docs/SUBWORD_INVESTIGATION.md §3`: items #6, #7, #9, #10, #11 all work
  JS-side but the Python fallback lacks the handler. Recommend document
  each as JS-only and call out in MANUAL_VERIFICATION that the JS
  resolver flag must be on. Users on the JS default (post 2026-06-30)
  get it for free.
- **R-5. Interior on symmetric delimiters.** For `quad`/`twin`/`skis`
  (symmetric quotes), interior trimming still works, but
  `_scope_surrounding_pair` at `cursorless/resolve.py:118-124` assumes
  stack-matched pairs. For symmetric delimiters that's degenerate. Verify
  against L5 rows before shipping #8.
- **R-6. Multi-target action shape drift.** #13 Reverse takes MULTIPLE
  targets — existing `run_action` at `shim/actions_js.py:82-91` passes
  ONE source range. Extending for list-target actions means batched call
  from Python (one `run_action` per target) OR signature widening.
  Recommend batched call — preserves the single-op contract.
- **R-7. Paste text broadcasting.** Cursorless's `Replace` broadcasts a
  single `replaceWith[0]` across multiple destinations (per
  `docs/REBUTTAL_ASSERTIONS.md #4`). Our paste (#4) should preserve that
  — clipboard text goes to each destination.
- **R-8. Wrap delimiter LIST subset decision.** Full cursorless surface
  imports 12 entries including escaped forms (`escapedDoubleQuotes` etc.)
  that make little sense in a prose buffer. Recommend a prose-friendly
  subset mirroring `_PROSE_TO_BUNDLE_DELIMITER` at `shim/targets_js.py:82-90`.
  See OQ1.

---

## §6. Open questions for the implementer

- **OQ1.** [#5 wrap] Which paired delimiters should prose-overlay expose
  — full 12-entry cursorless surface or the 7-entry prose subset from
  `cursorless/surrounding_pair.py:14-22`? Recommend subset.
- **OQ2.** [#6, #7, #8, #9, #10, #11] Does the `<user.cursorless_target>`
  capture at `prose_overlay_cursorless.talon:47` flow ALL modifier types
  (relativeScope, ordinalScope, everyScope, first/last, leading/trailing,
  interior) through? If yes, ZERO new grammar rules for cluster C. If
  no, shim captures needed. Cheap check: dictate `take next word` with
  JS resolver on and read the Talon log.
- **OQ3.** [#11] Intended semantics of `leading`/`trailing` on a single-
  line, space-joined prose buffer where every token is separated by
  exactly one space? Cursorless's LeadingStage/TrailingStage operate on
  whitespace *within* a scope; our tokens have no interior whitespace.
  Confirm against cursorless test fixtures.
- **OQ4.** [#12 clone] Both `insertCopyBefore` and `insertCopyAfter`, or
  only the After variant that upstream maps `clone` to? Recommend both
  — cheap to add.
- **OQ5.** [#13 reverse] For a range target on the flat buffer, does
  `reverse air past drum` reverse the TOKEN order across the range
  (1,2,3 → 3,2,1) or reverse the concatenated text as a string?
  Cursorless reverses target texts across MULTIPLE targets; mapping onto
  a range target needs an explicit decision.
- **OQ6.** [Python fallback stance] For #6, #7, #9, #10, #11 — (a) add
  Python handlers for parity, (b) document as JS-only with an explicit
  fallback error message, or (c) block on ISC-9 (Python-retirement)?
  Recommend (b), matches sub-word precedent per
  `docs/SUBWORD_INVESTIGATION.md`.
- **OQ7.** [#14] What counts as "must-have" vs "informational" for the
  L2 grep test? Recommend must-have = every stage class a shipped grammar
  rule can reach; informational = shape identifiers (until #1 lands),
  snippet identifiers (permanently OOS per `docs/GRAMMAR_STRUCTURE_PARITY.md
  §3 C8/C9`), IDE-only identifiers.
- **OQ8.** [Actions cluster] Should paste use `pasteFromClipboard` or a
  new `pasteAtDestination` name? Cursorless uses `pasteFromClipboard`.
  Recommend matching upstream for L2 grep parity.

---

## §7. Recommended order

Top-5 (of 12), ranked by user-value × cost-inverse × dependency depth.

1. **#14 L2 inventory grep test** — LAND FIRST. Ratchets current state
   before any bundle rebuild. Independent, small, high leverage. Blocks
   silent-drift regressions across every rebuild that follows.
2. **#7 OrdinalScope (`take second word this` sub-word ordinal)** — Zero
   bundle work, sub-word is the highest-leverage new spoken form (see
   `docs/SUBWORD_INVESTIGATION.md`). Composes with existing captures.
   Answering OQ2 here unblocks the entire modifier cluster.
3. **#3 Swap + #12 Clone + #13 Reverse (Cluster A, bundled)** — One
   rebuild, three verbs, all rely on existing infrastructure. Swap is
   the most requested per `docs/GRAMMAR_STRUCTURE_PARITY.md §3 C3`.
4. **#5 Wrap with paired delimiter** — Highest user-value single action
   (`docs/GRAMMAR_STRUCTURE_PARITY.md §5 R6`). Independent rebuild.
5. **#8 inside/outside modifier** — Small, useful, rides on the
   surrounding-pair work already shipped.

Deferred: #4 Paste (small but depends on clipboard plumbing verification),
#6 RelativeScope (works today via JS default; test-coverage only), #9
every (Python fallback fix is annoying; ship JS-only), #10 first/last
(covered by #7), #11 leading/trailing (semantics unclear per OQ3, low
value).

**Best single first-item to ship:** #14. Green-red diff that protects
everything else you build on top of it, one short PR, no semantic
decisions blocking the modifier cluster.

---

### §7 status log

- **#14 L2 inventory grep test** — ✅ shipped commit `e29fc6a` (2026-07-01).
  L2.6/L2.7 kept as-is (hats-bundle shape probes + 5th-arg round-trip).
  Added L2.8 (resolver bundle: 13 must-have identifiers fail-closed) and
  L2.9 (actions bundle: 7 shipped actions fail-closed, 6 planned actions
  fail-informational). Ratchet: when a wishlist action ships, move its
  entry from `ACTIONS_PLANNED` into `ACTIONS_MUST_HAVE` in the SAME PR.
  Headless: 127 → 129 green.

- **OQ2 resolution log (2026-07-01)** — resolved **YES statically** (no
  live Talon session needed). Static reading of cursorless-talon shows
  `<user.cursorless_target>` composes `cursorless_primitive_or_range_target`,
  which delegates to `cursorless_primitive_target`, whose rule is
  `<user.cursorless_modifier>+ [<user.cursorless_mark>] | <user.cursorless_mark>`
  (`~/.talon/user/cursorless-talon/src/targets/primitive_target.py:8-25`).
  `cursorless_modifier` at `~/.talon/user/cursorless-talon/src/modifiers/modifiers.py:32-44`
  is a union that includes every wishlist modifier: `cursorless_interior_modifier`,
  `cursorless_simple_modifier` (leading/trailing/bounds/just),
  `cursorless_simple_scope_modifier` (every scope),
  `cursorless_ordinal_scope`, `cursorless_relative_scope`. Therefore all
  five modifiers of Cluster C (#6, #7, #9, #10, #11) flow through
  `<user.cursorless_target>` at `prose_overlay_cursorless.talon:47` with
  ZERO new prose-overlay grammar rules. The cluster is grammar routing +
  Python-fallback stance + L5 test rows per item — no shim captures.

- **#7 OrdinalScope** — ✅ shipped commit `08288db` (2026-07-01).
  Zero-grammar rebuild per OQ2=YES. Python-fallback documented as
  JS-only per `§Cluster C` — matches sub-word / ISC-9 direction. L5.20
  added (JS-only shape probe: `ordinalScope start=0 length=1 word` from
  cursor → token 0). MANUAL_VERIFICATION row 21 added
  (`take first word` → "the"). FEATURE_PARITY §3c row added.

- **#10 first/last** — ✅ shipped commit `19624f4` (2026-07-01).
  Semantically covered by OrdinalScopeStage — cursorless-talon's
  `cursorless_first_last` capture returns `{type:"ordinalScope",
  start:-N|0, length:N}`. Same bundle line 18899 + zero-grammar routing
  as #7. L5.21 added (JS-only: `ordinalScope start=-1 length=1 word`
  from cursor-at-end → token 4). MANUAL_VERIFICATION row 22 added.
  FEATURE_PARITY §3c row added.

- **#9 every scope** — ⚠️ **partial** shipped commit `fb09e26`
  (2026-07-01). L5.22 added asserting the composed shape
  `[everyScope word, containingScope document]` returns 5 ranges per
  the multi-range semantics. **Bundle gap uncovered**: the bare shape
  `[everyScope word]` that cursorless-talon's
  `cursorless_simple_scope_modifier` emits returns only 1 range in our
  bundle (the current containing word), not the 5 ranges cursorless
  proper delivers. Root cause: our `EveryScopeStage` (bundle line
  15505) falls back through `getDefaultIterationRange` when
  `hasExplicitRange=false`, but the iteration-scope-handler default
  for our synthetic prose-document isn't returning the whole
  buffer as the iteration scope. Consequence: `take every word` alone
  is user-visible-partial; `take every word file`-style composed shapes
  work. Two future paths to fully close: (a) a shim capture that
  composes `everyScope` with an implicit `containingScope document` (or
  `line` on multi-line), or (b) live-verify the bundle's iteration-
  scope handler and patch the `getDefaultIterationRange` fallback.
  Row #9 in `docs/FEATURE_PARITY.md §3c` flipped `[x]` → `[~]` with
  gap docs. MANUAL_VERIFICATION rows 23 (bare — known partial) and 24
  (composed — 5 ranges) added.

- **#6 RelativeScope** — ✅ shipped commit `f4912cc` (2026-07-01).
  Zero-grammar rebuild per OQ2=YES; `RelativeScopeStage` shipped at
  bundle line 19103; grammar routing free because
  `cursorless_relative_scope` is a `cursorless_modifier` variant.
  L5.23 added (JS-only: `relativeScope offset=1 length=1 forward` from
  mark 'a' → token 2). MANUAL_VERIFICATION row 25 added
  (`take next word air` → "ball"). FEATURE_PARITY §3c row added.
  Python fallback: JS-only per §Cluster C.

- **OQ3 resolution log (2026-07-01)** — resolved **degenerate on prose**.
  Bundle probe confirms `LeadingStage`/`TrailingStage` return a 1-char
  whitespace range (the single space BETWEEN tokens on a space-joined
  prose buffer). Since prose tokens have no interior whitespace and
  our buffer's inter-token whitespace is exactly one space, the
  returned range has no token-level meaning — `_char_range_to_token_range`
  returns `None` on it. Cursorless's LeadingStage/TrailingStage operate
  on whitespace WITHIN a scope; our flat prose buffer has none. Item
  #11 flips to `[—]` in `docs/FEATURE_PARITY.md §3c` and the bundle
  shape is asserted stable in L5.24.

- **#11 leading/trailing** — ✅ shipped 2026-07-01 (SHA recorded in a
  follow-up commit — this is the final Cluster C item).
  Zero-grammar rebuild per OQ2=YES; stages ship in bundle. OQ3 resolved
  degenerate — see log above. L5.24 added (JS-only, raw char-range
  assertion). MANUAL_VERIFICATION rows 26, 27 added. FEATURE_PARITY
  §3c row added marked `[—]` (out-of-scope on prose — no token-level
  semantics).

- **Cluster A — Actions rebuild (#3 Swap, #12 Clone, #13 Reverse)** —
  ✅ shipped 2026-07-01. Six commits across two repos (`~/code/cursorless`
  and `~/code/prose-overlay`). This is the second cross-repo actions-
  bundle shipment (Slice 1 `97215cd` on the shape side was the first).

  **Composable-rule finding (OQ-resolution style):** `#12 Clone`
  (`clone` → `insertCopyAfter`, `clone up` → `insertCopyBefore`) and
  `#13 Reverse` (`reverse` → `reverseTargets`) both live in
  cursorless-talon's `cursorless_simple_action` LIST (see
  `~/.talon/user/cursorless-talon/src/spoken_forms.json`). Both ride
  the existing composable rule at `prose_overlay_cursorless.talon:47`
  — **zero new prose-overlay grammar rules**. Only `#3 Swap` needed
  a new rule because `swapTargets` lives in the dedicated
  `cursorless_swap_action` LIST + `cursorless_swap_targets` two-target
  capture, distinct from the simple-action union.

  **Multi-target ABI:** #13 Reverse is the first multi-target action in
  the bundle. Signature widening kept ABI-clean: the JS bundle's 4-arg
  `proseRunAction` accepts an ARRAY of TargetObj in the source slot
  when the action is `reverseTargets`; the dispatcher branches on
  `Array.isArray(sourceRaw)`. Python side adds
  `shim/actions_js.py:run_action_multi` + a dedicated branch in
  `prose_overlay_run_action`. #3 Swap does NOT need this — two targets
  in source+dest slots (existing two-target ABI).

  **Bundle build:** `scripts/build-js.ts` gained an `actions` target
  entry. `prose_actions.js` was previously hand-maintained (see
  `docs/BUNDLE_SHAPE_DECISIONS.md §OQ7`); now built from
  `packages/cursorless-engine/src/actions/proseActionsStandalone.ts`
  via `bun scripts/build-js.ts actions`. `proseActionsStandalone.ts`
  became a tracked file in the cursorless repo for the first time as
  part of the #12 Clone cursorless commit.

  **§2 #13 OQ resolution (R-6 batched vs widened):** Went with **widened
  signature** (Array in source slot) rather than batched calls per
  range. Batched-call approach can't swap texts BETWEEN ranges — each
  isolated call would extract-and-replace with the same text.

  **Commits (cursorless first, then prose-overlay):**
  - #12 Clone: `c91b00235` (cursorless) → `ee1779e` (prose-overlay). +
    `proseActionsStandalone.ts` became tracked in cursorless.
  - #13 Reverse: `c67da0326` (cursorless) → `129a636` (prose-overlay).
  - #3 Swap: `0dcda38cd` (cursorless) → `dc3f985` (prose-overlay).

  **Headless:** 134 → 138 green (+ L2.10, L2.11, L2.12, L2.13 — one bun
  probe per new action geometry, four total). L2.9 fail-closed set went
  from 7 → 10 must-have actions; `ACTIONS_PLANNED` set went from 6 →
  2 (only pasteAtDestination + wrap remaining).

  **What's next in §7 order after Cluster A:**
  - #5 Wrap with paired delimiter (Cluster B in §4 — separate rebuild
    because it changes `proseRunAction`'s signature and introduces a
    delimiter LIST).
  - #8 inside/outside modifier (Cluster D — small independent PR).
  - #4 Paste at destination (§7 deferred — depends on clipboard
    plumbing verification).

- **2026-07-01 — Cluster B closed — wishlist item #5 Wrap shipped.**
  ABI-widening cross-repo work. `proseRunAction` grew a 5th `options`
  arg for `{left, right}` delimiter strings; the bundle branches on
  `optionsJson === undefined` for backward compat with pre-#5 4-arg
  callers.
  - #5 Wrap: `986554267` (cursorless — `actionWrapWithPairedDelimiter`
    geometry in `proseActionsStandalone.ts`) → prose-overlay commit
    lands the rebuilt bundle + `prose_overlay_wrap_with_paired_delimiter`
    action in `shim/actions_cursorless.py` + `run_action_wrap` helper
    in `shim/actions_js.py` + grammar rule at `prose_overlay_cursorless.talon`
    mirroring cursorless.talon C7 (`<wrapper_paired_delimiter> {wrap_action}
    <target>`). OQ1 resolution: reuse cursorless-talon's existing
    `cursorless_wrapper_paired_delimiter` capture so the full delimiter
    vocabulary flows through unchanged rather than shadowing with a
    prose-side subset. VSCode-only `rewrap` action dispatches back to
    cursorless proper.

  **Headless:** 138 → 139 green (+ L2.14 — the wrap bundle probe emits
  two `insert` ops (`position` + `text`), one for each delimiter, at
  start-of-target and end-of-target). L2.9 must-have set went 10 → 11;
  `ACTIONS_PLANNED` shrank to `pasteAtDestination` only.

  **What's next in §7 order after Cluster B:**
  - #8 inside/outside modifier (Cluster D — small independent PR).
  - #4 Paste at destination (§7 deferred — depends on clipboard
    plumbing verification).

- **2026-07-01 — Cluster D closed — wishlist item #8 inside/outside
  (interior) modifier shipped.** Composable-dispatch route confirmed —
  ZERO new prose-overlay grammar rules, ZERO bundle rebuild.

  **Grammar-audit finding (composable dispatch YES):**
  Static reading of cursorless-talon confirms the interior modifier
  flows through `<user.cursorless_target>` at
  `prose_overlay_cursorless.talon:50` for free — both variants:
    - `inside` → `interiorOnly` is a `cursorless_interior_modifier`
      (`~/.talon/user/cursorless-talon/src/modifiers/interior.py:11-16`),
      which is explicitly listed in `cursorless_modifier` at
      `~/.talon/user/cursorless-talon/src/modifiers/modifiers.py:33`.
    - `bounds` → `excludeInterior` is a `cursorless_simple_modifier`
      (spoken-forms map at
      `~/.talon/user/cursorless-talon/src/spoken_forms.json:86`),
      which is likewise a `cursorless_modifier` variant per
      `modifiers.py:26` → `head_tail_swallowed_modifiers` list.
  Same OQ2=YES pattern as Cluster C. This is the second wishlist item
  after Cluster C to close via composable-dispatch route with zero
  grammar work.

  **Bundle-side (verified, no rebuild):** `InteriorOnlyStage` at
  `js/prose_resolve_targets.js:15819`, `ExcludeInteriorStage` at
  `:15828`. Both are already in L2.8's fail-closed must-have inventory
  (`scripts/headless_verify/layer2_bundle.py:189-190`) — no L2 update
  needed. Bundle behavior confirmed via bun spike on
  `the ( air ball ) drum` with mark 'a' on token 2:
    - `interiorOnly + SP round` → chars [6,14) → tokens (2,3) = `air ball`
    - `excludeInterior + SP round` → chars [4,5) + [15,16) → TWO ranges
      (1,1) + (4,4) = the delimiter tokens themselves — matches
      cursorless's "Bounding paired delimiters" semantics per
      `~/.talon/user/cursorless-talon/src/cheatsheet/sections/modifiers.py:57`.

  **Python-fallback stance:** Asymmetric-gap documented, no impl.
  `cursorless/resolve.py:174-180` has no `interiorOnly` or
  `excludeInterior` handler. Per §Cluster D directive, Python stays
  token-level; JS handles the interior split. Matches sub-word
  precedent per `docs/SUBWORD_INVESTIGATION.md §3` and Cluster C
  Python-fallback stance. Retire-Python (ISC-9) makes the split moot.

  **Tests + docs:** L5.25 (interiorOnly → tokens (2,3)), L5.26
  (excludeInterior → [(1,1),(4,4)]). MANUAL_VERIFICATION rows 37
  (`take inside round air`) and 38 (`take bounds round air`).
  FEATURE_PARITY §3d gains one row marked `[x]` JS-path only.

  **Commits:**
  - `4fdb6bd` (feat) — L5.25/L5.26 + MANUAL rows 37,38 +
    FEATURE_PARITY row.
  - this commit (docs) — §7 status log entry.
  Headless: 139 → 141 green.

  **What's next in §7 order after Cluster D:**
  - #4 Paste at destination (§7 deferred — depends on clipboard
    plumbing verification per `docs/REBUTTAL_ASSERTIONS.md #3`).
