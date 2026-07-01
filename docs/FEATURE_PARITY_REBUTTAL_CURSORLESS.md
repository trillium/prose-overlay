# Feature Parity — Rebuttal: What Cursorless Is Already Responsible For

> Companion to `FEATURE_PARITY.md`. For each open row in that doc, tier how much of the work is already handled by Cursorless's engine (`cursorless-engine`) and its JS bundle (`js/`, accessed via `prose_overlay_targets_js.py` / `prose_overlay_hats_js.py`) so prose-overlay can lift rather than reinvent.
>
> Drafted 2026-06-30. **Revised 2026-06-30 after verification pass (see `REBUTTAL_ASSERTIONS.md`):** §4 replace API names corrected to actual Cursorless surface (`"replace"` action, not the made-up `takeAndReplace`); §5 shape-hats reclassified into assignment (Tier 2, bundle rebuild needed) + render (Tier 3, mouse-clock lift) per Trillium's scope-shift framing; cross-reference filter corrected from "either" → "BOTH"; row count fixed (24, not "~22"); cost-estimate language stripped.

## Lens

Cursorless is a different kind of substrate than community. It ships:
- **Hat allocator** (shape × color × letter assignment over visible tokens — already wired via `prose_overlay_hats_js.py`)
- **Target resolution** (`processTargets` over JSON target descriptors — JS path scaffolded behind `user.prose_overlay_use_js_resolver`)
- **Scope handlers** (sentence, clause, string, number, email, nonWhitespaceSequence, document, line, paragraph, token, word, identifier, character — already wired through `prose_overlay_cursorless_resolve.py`)
- **Word scope sub-token splitting** (snake_case, camelCase, kebab-case, dot.case — handled by the engine's word scope handler)
- **Range / list / surrounding-pair handlers** (already wired)
- **`applyFormatter` action** (already wired via ISC-7)
- **Bring / move / swap actions** (already wired)
- **Pre-execution decoration** (Cursorless's own flash hint; ISC-15 mirrored this on prose-overlay's side)

The question is: for each open row, what fraction is already implemented inside the Cursorless engine and just needs prose-overlay to expose its tokens/buffer in the right shape?

## Tier 1 — Cursorless handles it almost entirely (lift the result, don't rebuild the logic)

These rows have a working implementation **inside the Cursorless engine today**. Prose-overlay's job is to feed Cursorless its tokens in the right shape and consume the resolved ranges. The algorithmic work is done.

| Row | Why Cursorless covers it | Prose-overlay's residual work |
|---|---|---|
| **§3c** Word scope splits formatted tokens into sub-words | Cursorless's word-scope handler (`cursorless-engine/src/processTargets/modifiers/scopeHandlers/`) splits identifiers on `_` / `-` / `.` / case boundaries natively. `take second word this` inside `one_two_three` is a Cursorless primitive, not a feature to build. | Emit identifiers as **single tokens** (not pre-split) to the JS resolver when they have sub-word structure; let the engine's word scope do the split. Today prose-overlay pre-splits, which masks the feature. |
| **§3c** Sub-word identity preserves joiner under replace | Cursorless's word-scope inherently preserves joiners on replacement — `take second word` in `one_two_three` then dictating `changed` produces `one_changed_three`. The engine owns this. | Same — feed the unsplit identifier, accept the joiner-preserving replacement. |
| **§4** Sub-word selection | Direct corollary of §3c word scope. Cursorless resolves the sub-word range; selection just stores it. | Render via existing selection-paint pass (`prose_overlay_draw_tokens.py:158`) — already handles arbitrary ranges. |
| **§5** Sub-word highlight | Selection comes from Cursorless's range resolution; prose-overlay's existing selection painter already handles any range, including ranges narrower than one token. | None beyond §3c hookup — the highlight is automatic once the selection is sub-word-shaped. |

**The takeaway:** four "open" parity rows collapse into one substrate problem — **stop pre-splitting identifiers before handing them to Cursorless's resolver.** Cursorless will then provide sub-word scope, sub-word replace, sub-word selection, and sub-word highlight for free.

## Tier 2 — Cursorless gives you the scaffolding, you wire the endpoint

The engine has the action or capability; prose-overlay has to plumb it into its buffer and render surface.

| Row | What Cursorless provides | What prose-overlay still owns |
|---|---|---|
| **§4** Replace selection by dictation | Cursorless action is `"replace"` (not the made-up `takeAndReplace`). Talon-side entrypoint: `cursorless_replace_action(destination, replace_with)` at `cursorless-talon/src/actions/replace.py:6-16`. Wire shape: `{"name": "replace", "replaceWith": list[str], "destination": CursorlessDestination}`. Engine handler: `cursorless-engine/src/actions/Replace.ts`. Standalone surface emits `{type: "replace", range, text}` per `proseShim.ts:102`. `replaceWithTarget` is a separate action (= `Bring`) for bring/move semantics. | (1) Resolve selection to `CursorlessDestination` via the JS resolver. (2) Call `actions.user.private_cursorless_command_and_wait({"name": "replace", "replaceWith": [text], "destination": dest})`. (3) Handle the emitted `{type: "replace", range, text}` op by calling `buffer.replace_range(range.start, range.end, text)`. (4) Seal as one STRUCTURAL undo step. |
| **§4** Selection extension by word (left/right) | `take past <next word>` composes from `cursorless_relative_scope_singular` at `cursorless-talon/src/modifiers/relative_scope.py:22-23` (`[<ordinal>] <direction> <scope>` — e.g. `next funk`, `third next word`) and the shipped `past <target>` range modifier. | Register a prose-overlay verb (`extend right word`) that constructs the equivalent target and routes through the JS resolver. (Open: confirm `past` accepts a relative-scope on its right side, not just a hat target.) |
| **§5** Shape hats — **assignment** | Cursorless engine's `HatAllocator.ts` does shape-aware allocation (shape × color × letter cartesian product) over visible tokens. `HatStyleName` typed in `IndividualHatMap.ts`; `enabledHatStyles` config the allocator reads at `HatAllocator.ts:63`; `COLOR_CANONICALIZATION_MAPPING: Record<string, HatStyleName>` for spoken-form lookup. **All exists upstream.** The current prose-overlay bundle has it tree-shaken out — `scripts/build-js.ts` builds dot-only `prose_allocate_hats.js`. Restoring shape support is a build-config flip, not a new feature. | Rebuild `js/prose_allocate_hats.js` with shape-aware allocator code included (modify `scripts/build-js.ts` to keep the `HatStyleName` / `enabledHatStyles` path). Configure `enabledHatStyles` from Python to scope the homophone pool. Read per-token shape assignments back from the bundle. |
| **§3f** `[~]` JS resolver behind setting | Cursorless's bundle IS the destination of this migration. Every line of code in `prose_overlay_targets_js.py` is a deliberate handoff to the engine. | Complete the MANUAL_VERIFICATION.md walkthrough; flip the default once parity holds 3 sessions. **Most other Tier-2 rows here are gated behind this** — treat §3f as the precondition, not parallel work. |
| **§3f** `[ ]` Python resolver removed once JS holds 3 sessions | This is the *teardown* phase of the migration — Cursorless's bundle has been doing the work all along. | Delete `prose_overlay_cursorless_resolve.py` and audit imports; the engine owns the resolution by then. |

## Tier 3 — Cursorless cannot help; the work IS the work

These rows are outside Cursorless's responsibility model. Cursorless does target+action; it does not own cursor primitives, undo state, observability, or panel UI.

| Row | Why Cursorless can't cover it |
|---|---|
| **§1** `[~]` Insertion at cursor preserves split boundary | Cursorless doesn't model "type at cursor" — it edits via target+action. The buffer-level split-on-insert is overlay-specific. |
| **§2** Mid-token cursor positioning / char insertion / char delete | Cursorless has the `character` scope for *targeting* a single char but not for cursor placement. Cursor-and-keystroke is a host-editor model that doesn't exist in Cursorless's idiom. |
| **§2** Visible character-level cursor inside a token | Render concern. Cursorless paints hats, not cursors. |
| **§2** Letter hat addressability for digits/punct | Cursorless's hat allocator already hats digits/punct (verified at L1.8/L1.9/L2.3/L2.4). The bottleneck is the prose-overlay-side `<user.letter>` capture (community, letter-only). Cursorless's side: zero work. |
| **§2** Number hat namespace (`chuck num 1`) | Cursorless hats per-token uniformly; it has no "number-only hat space" concept. This is a prose-overlay grammar choice. |
| **§5** Shape hats — **render** | Cursorless engine assigns shapes; VS Code extension renders them. The render path is host-specific and does not ship in the prose-overlay JS bundle. Lift mouse-clock SVG paths instead, per `HOMOPHONE_SHAPES_PLAN.md`. **Two-half feature: assignment is Tier 2 (above), render is here in Tier 3.** |
| **§5** Shape panel with alternates | Custom Skia UI on prose-overlay's canvas. Cursorless paints hats, not floating panels. |
| **§5** Mid-token cursor render | Render concern. |
| **§7** Undo / redo / N-step undo / selection restore on undo | Cursorless does not own undo. Each Cursorless action seals as one host-editor undo step, but the stack and replay are the editor's. Prose-overlay owns its own stack. |
| **§7** Cut/copy/paste through system clipboard | Cursorless has `bring` and `take` that interact with host clipboards in host editors. For prose-overlay's buffer, the wiring is custom (and community provides the primitives — see the community rebuttal). |
| **§8** Observability (paper trail Slice B, JSONL diff, log rotation) | Internal observability is prose-overlay's domain. |
| **§9** Voice arbitration | Talon grammar layer, not Cursorless. |

## Shape of the answer

The parity doc has **24 open rows** (`[ ]` + `[~]`, verified row count). Cursorless-coverage split (per-tier counts are estimates — explicit row-walk pending):

- **Tier 1 (~4 rows, all from §3c/§4/§5 sub-word cluster):** word scope, sub-word identity, sub-word selection, sub-word highlight. **All four are one substrate fix** — verify Cursorless's `WordScopeHandler` is included in the bundle and that the talon-side grammar binds `word` to a sub-token target.
- **Tier 2 (~5 rows):** replace-selection, selection-extension-by-word, shape-hats-assignment, JS resolver finish, Python resolver remove. The JS-resolver migration is itself the meta-Tier-2: it transfers more responsibility to Cursorless with every shipped piece. **Most Tier 2 work is gated behind §3f completing.**
- **Tier 3 (~15 rows):** mid-token cursor, char-cursor, number-hat namespace, shape panel, shape-hats-render, undo/redo internals, observability, arbitration. Cursorless-irrelevant work; this is what `CHAR_CURSOR_PLAN`, parts of `HOMOPHONE_SHAPES_PLAN`, and `UNDO_REDO_PLAN` Phase 3 actually need to build.

## The killer insight

**The sub-word cluster is the highest-leverage single fix on the entire parity doc.** Four open rows collapse to one substrate change: get Cursorless's `WordScopeHandler` doing its job on prose-overlay's identifiers. This is the work `SUBWORD_PLAN.md` should specify, and it's worth pulling in front of the other Tier 1/2 items because:

1. It unlocks the user's stated workflow example from §11 (`take second word this` inside `one_two_three`).
2. It collapses four roadmap rows into one PR.
3. It validates the JS-resolver migration (§3f) by exercising a real engine feature that the Python path can't easily replicate.
4. It defers a meaningful amount of code that prose-overlay would otherwise have to author (a sub-word splitter + joiner-preservation logic + sub-word-aware replacement) — code that already exists, tested, in the Cursorless engine (`WordTokenizer.splitIdentifier()` at `cursorless-engine/src/processTargets/modifiers/scopeHandlers/WordScopeHandler/WordTokenizer.ts:19-27`).

**Note on the root cause.** An earlier framing said the blocker was prose-overlay pre-splitting identifiers on the buffer side. **That's wrong** — test `L1.17` proves `add_text("the_quick_brown_fox") → 1 token`, so the buffer already keeps snake_case whole. The real blocker is downstream — one of: (a) the Python resolver path (default) doesn't bind a sub-word handler, (b) the bundled JS at `js/` is a stripped subset lacking `WordScopeHandler` (likely — see §5 shape-hats note about `scripts/build-js.ts` tree-shaking), or (c) the grammar in `prose_overlay_cursorless.talon` doesn't route `word` to a sub-token target. **Diagnose which before scoping the fix** — it's 10 LOC if (c), more if (a) or (b).

**Pragmatic order:** (1) complete the §3f JS-resolver migration; (2) audit the JS bundle for `WordScopeHandler` and rebuild if absent; (3) wire the sub-word cluster; (4) work the long Tier-3 substrate list. `trillium_talon`-Tier-1 wins (number-hat, digit/punct hat, clipboard — see companion rebuttal) can land in parallel since they don't touch the resolver.

## Cross-reference

- See `FEATURE_PARITY_REBUTTAL_COMMUNITY.md` for `trillium_talon` / stdlib coverage tiers.
- The two rebuttals don't partition cleanly — coverage is a 2D matrix. **The right filter for "true prose-overlay-only work" is rows that are Tier 3 in BOTH rebuttals.** A row that is Tier 3 in just one rebuttal is covered by the other source and should never be reimplemented from scratch.
- See `REBUTTAL_ASSERTIONS.md` for the verification pass that drove the corrections in this revision.
