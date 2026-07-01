# Bundle Shape Scope — restoring cursorless's shape-allocation surface in the JS bundle

> **Tier:** cross-layer (bundle rebuild + shim wiring; render unchanged). **Effort:** ~1 week slice, naturally splits into 3 slices (bundle, shim, homophone-piggyback). **Not implementation.** Scoping only per REBUTTAL_ASSERTIONS.md §5 scope-shift framing.
>
> Companion to [`HOMOPHONE_SHAPES_PLAN.md`](./HOMOPHONE_SHAPES_PLAN.md), which owns the render layer and the homophone-pool repurposing. This doc scopes the *assignment* substrate.

## 1. Current-state bundle inventory

**Build script** — `scripts/build-js.ts:35-46` declares two bundle specs:

- `targets` → `packages/cursorless-engine/src/actions/proseTargetsStandalone.ts` → `js/prose_resolve_targets.js` (718 KB)
- `hats`    → `packages/cursorless-engine/src/util/allocateHats/proseStandalone.ts` → `js/prose_allocate_hats.js` (492 KB)
- `prose_actions.js` (9 KB) is not listed in BUNDLES — it's built separately/hand-maintained.

`CURSORLESS_DIR` defaults to `~/code/cursorless` (`build-js.ts:27`). Confirmed present on disk with the expected `packages/cursorless-engine/` and `packages/common/` layout.

**Explicit shape suppression in the standalone entry** — `proseStandalone.ts:102-114` hard-codes a colors-only `HatStyleMap`:

```ts
const PROSE_HAT_STYLES = {
  gray:{penalty:0}, blue:{penalty:1}, green:{penalty:1}, red:{penalty:1},
  pink:{penalty:2}, yellow:{penalty:2}, purple:{penalty:2},
  black:{penalty:3}, white:{penalty:3},
} as unknown as HatStyleMap;
const ENABLED_HAT_STYLE_NAMES = Object.keys(PROSE_HAT_STYLES) as HatStyleName[];
```

Nine entries, all color-only, `-shape` suffixes absent. The `getRankedTokens` / `getHatRankingContext` / `chooseTokenHat` machinery from `packages/cursorless-engine/src/util/allocateHats/` is imported and used verbatim (`proseStandalone.ts:35-37`), so the allocator *itself* is shape-capable — only the enabled-style constant is stripped.

**Bundle static-string audit** (regex-verified 2026-07-01):
- `prose_allocate_hats.js` — one `wing` substring match, all inside `flowing` from bundled `js-yaml`. Zero real shape identifiers.
- `prose_resolve_targets.js` — 16 `shape`/`HatStyleName` substring hits, all from bundled type-name residues (`HatStyleName` survives as a `string` alias per `packages/common/src/ide/types/hatStyles.types.ts:1`). No `bolt|frame|wing|fox|eye|hole|ex|play|curve|crosshairs` literals.
- `prose_actions.js` — zero shape-related identifiers.

**Bundle public surface** (globalThis exports):
- `proseAllocateHats(tokensJson, oldAssignmentsJson, stability, cursorGapJson)` → `proseStandalone.ts:275`. Returns `{tokenIdx: {charIdx, letter, color}}`. `color` is a bare color name today; extending it to hold `"blue-frame"` etc. is a value-shape change, not a signature change.
- `proseResolveTarget(targetJson, documentJson, hatMapJson, cursorJson)` → `proseTargetsStandalone.ts:234-238`. `hatMapJson` is `HatMapJson.entries[]` with a bare `color` field (`proseTargetsStandalone.ts:206`); shape is implicit-null.

**No conditional shape gating in the bundle.** There is no `if (enabledHatStyles.length > 9)` fork already present but no-op'd — the shape surface is genuinely absent, not silenced.

## 2. Cursorless upstream shape surface

Source paths refer to `~/code/cursorless/`. All refs verified 2026-07-01.

- **`HatStyleName` type** — `packages/common/src/ide/types/hatStyles.types.ts:1`. Deliberately loose: `export type HatStyleName = string;`. All shape/color combinatorics are stringly-typed at the type-level; discipline lives in `HatStyleMap` construction.
- **`HatStyleMap`** — `packages/common/src/ide/types/Hats.ts:28`. `Record<HatStyleName, HatStyleInfo>` where `HatStyleInfo` is `{penalty: number}` (`Hats.ts:13-23`). Doc comment (`Hats.ts:15-22`) explicitly says: "each style is a combination of 0 or more components, the total penalty for a style is the sum of the penalties of its components" — the surface is *designed* for shape × color composition.
- **Shape constants** — `packages/common/src/types/command/legacy/targetDescriptorV2.types.ts:12-23` (also duplicated in `CommandV0V1.types.ts:126` and `PartialTargetDescriptorV3.types.ts:12`):
  ```ts
  const HAT_NON_DEFAULT_SHAPES = ["ex","fox","wing","hole","frame","curve","eye","play","bolt","crosshairs"] as const;
  ```
  10 shapes, matches `HOMOPHONE_SHAPES_PLAN.md §3 Slice 1` `HAT_SHAPES` verbatim (order differs; content identical).
- **Composition type** — `targetDescriptorV2.types.ts:26-27`: `type HatStyleName = HatColor | \`${HatColor}-${HatNonDefaultShape}\``. So legal names are e.g. `"blue"`, `"blue-frame"`, `"yellow-bolt"`. `default` (unstyled) exists as a `HatColor` (`targetDescriptorV2.types.ts:2`) — matches prose-overlay's `gray` alias role.
- **`enabledHatStyles` config read** — `packages/cursorless-engine/src/core/HatAllocator.ts:63`: `this.hats.enabledHatStyles` is read once per debounced allocation and passed to `allocateHats()`. The value is the `HatStyleMap` from `Hats.ts:28`. The debounce triggers are enumerated at `HatAllocator.ts:22-45` — including `onDidChangeEnabledHatStyles` (`:23`) so runtime config flips re-allocate on the next tick.
- **Allocator core** — `packages/cursorless-engine/src/util/allocateHats/allocateHats.ts:46-129`. The style pool is `enabledHatStyleNames = Object.keys(enabledHatStyles)` at `:76`; the `graphemeRemainingHatCandidates: DefaultMap<string, HatStyleName[]>` at `:86-88` seeds each grapheme with a *copy* of the full pool, and per-token pass removes the chosen style from that grapheme's list (`:120-125`). This is exactly the cartesian shape × color × letter partitioning REBUTTAL §5 calls out.
- **`HatCandidate.penalty` sourcing** — `allocateHats.ts:166`: `penalty: enabledHatStyles[style].penalty`. The caller controls total penalty by summing component penalties into the map — shape penalty adds directly to the style entry (`Hats.ts:15-22` doc).
- **`chooseTokenHat`** — `packages/cursorless-engine/src/util/allocateHats/chooseTokenHat.ts` (imported at `proseStandalone.ts:35`). Consumes `HatStability` + prior + candidates, opaque to whether a "style" is `blue` or `blue-frame`.
- **`IndividualHatMap`** — `packages/cursorless-engine/src/core/IndividualHatMap.ts` (imported by `HatAllocator.ts:6`). Per-token tuple representation. Not required for prose-overlay's bundle — the bundle already flattens to `{tokenIdx: {charIdx, letter, color}}` at `proseStandalone.ts:261-265`. Extending `color` → `styleName` (e.g. `"blue-frame"`) keeps the flat shape; Python-side splits on `-` at the boundary.
- **`COLOR_CANONICALIZATION_MAPPING`** — `packages/cursorless-engine/src/core/commandVersionUpgrades/canonicalizeTargetsInPlace.ts:16`. This is a **command-version migrator**, not a spoken-form-to-style lookup. Cursorless's spoken-form-to-style mapping lives in **`cursorless-talon/src/csv_overrides.py`** (not in this repo tree) — it's a Talon-side concern, not a bundle concern. REBUTTAL §5's mention of this is a red herring for our scoping: prose-overlay's spoken-form list is `PANEL_COLOR_PALETTE` in `shim/shapes.py:228-237` plus mouse-clock's `{user.hat_shape}` list; the bundle receives normalized strings.

## 3. Bundle rebuild plan — `scripts/build-js.ts` changes

**Zero changes to `build-js.ts` itself.** The esbuild invocation at `build-js.ts:64-73` is style-agnostic. The tree-shake is not what's stripping shapes — the strip is source-level in `proseStandalone.ts:102-114`.

**Actual edits, all inside `~/code/cursorless/packages/cursorless-engine/src/util/allocateHats/proseStandalone.ts`:**

1. Replace the 9-entry `PROSE_HAT_STYLES` (`:102-114`) with a full color × shape map. New shape: `Record<\`${color}\` | \`${color}-${shape}\`, {penalty}>`. Color penalty as today (0/1/2/3); shape adds `+1` per name (matches Cursorless upstream convention). Total entries: 9 colors × (1 no-shape + 10 shapes) = **99 entries**. Encode as generator, not literal.
2. Signature extension: add an optional 5th arg to `proseAllocateHats` — `enabledStylesJson?: string`. When present, parse it as `HatStyleMap` and use in place of `PROSE_HAT_STYLES`. When absent, keep today's behavior (backward-compatible). This is the **wire for Python-side `enabledHatStyles`**.
3. Change the return-value key from `color` to `styleName` (or add `styleName` alongside `color` for a two-release deprecation window). `styleName` holds `"blue"` or `"blue-frame"`; `color` stays as the pre-`-` split for the current color-only readers in `shim/hats_js.py`.

**Bundle size delta:** small. The 99-entry map is ~2 KB source, ~500 B minified. All the shape *logic* (allocator, chooseTokenHat, ranking) is **already in the bundle** — we're not adding upstream code, just un-stripping a constant. Expect `prose_allocate_hats.js` to grow from 492 KB → ~493 KB. Well under ISC-55's 1.5× ratio cap.

**Standalone-entrypoint updates:**
- `proseStandalone.ts` — above.
- `proseTargetsStandalone.ts` — the `HatMapJson.entries[].color` field (`:206`) needs to become `styleName` (or gain `styleName` alongside). The `ProseHatMap.getToken` lookup at `:210-214` keys on `${hatStyle}:${character}` — already shape-aware since `hatStyle` is `HatStyleName`, so the lookup gains shape support for free once the Python-side passes shape-suffixed style names.
- `proseActionsStandalone.ts` — spot-check for `color`-vs-`styleName` reads. `prose_actions.js` is 9 KB and hand-maintained; likely no changes needed but audit before ship.

**New named exports to Python:** none required. The four-arg → five-arg signature bump on `proseAllocateHats` is the only surface change; Python passes `null` (backward-compat) or a JSON `enabledHatStyles` map (opt-in shape).

## 4. Python-side plumbing

- **`shim/hats_js.py:56-97`** — `compute_hat_assignments` signature keeps `(tokens, old_assignments, stability, cursor_pos)`. Add optional `enabled_styles: dict[str, dict] | None = None`. When passed, JSON-serialize and pass as the new 5th JS arg. `old_assignments[color]` field parsing (`:102-108`) needs to read `styleName` when present, fall back to `color` for pre-bump bundles. The post-validate loop at `:135-159` treats `color` as opaque; extends cleanly to `styleName`.
- **`shim/shapes.py`** — this is the **piggyback question**. Two options:
  - **(a) full replacement.** `compute_shape_assignments` (`shapes.py:361-501`) becomes a thin wrapper: pack the homophone-pool config as an `enabledHatStyles` dict (only shape-suffixed entries for one designated homophone color, e.g. `"gray-bolt"…"gray-eye"`), invoke `hats_js.compute_hat_assignments`, unpack the `styleName` field on flagged indices back into `token_idx → shape_name`. ~50 LOC, deletes the three-pass allocator.
  - **(b) narrow to config only.** Keep `compute_shape_assignments` as-is for **group-anchored** allocation (`shapes.py:392-402` explicit ISC-14c semantic: same group → same shape). Cursorless's allocator is *token-anchored* (per grapheme × visible token), so a full replacement changes ISC-14c semantics unless we pre-project groups → representative tokens. Option (b) keeps `compute_shape_assignments` as the group-projection layer and only uses the bundle for the render-adjacent letter+color allocation.
  - **Recommendation:** (b). See §6 risk 2 and OQ3. `HOMOPHONE_UI.md` §2.C explicitly wants group-stable shapes, which is not what cursorless's per-visible-token allocator produces.
- **`internal/homophones.py`** — no change. `group_id_for_word`, `group_for_word`, `is_flagged`, `flagged_indices` all stay. This is domain logic, unaffected by allocator choice.
- **`internal/instance.py`** — `shape_assignments: dict[int, str]` field (per HOMOPHONE_SHAPES_PLAN.md Slice 2) stays as the render-layer contract. It's the *source* that gets replaced (option a) or the *layer above* (option b), not the field itself.
- **`ui/draw_tokens.py:186-187, 231-247`** — unchanged. Reads `instance.shape_assignments.get(idx)`; agnostic to whether the dict came from the Python allocator or a bundle-unpack.
- **`ui/draw_panels.py`** — unchanged. Renders per-token panels from `instance.homophone_panel_alts` (populated by `compute_panel_alts` at `shim/shapes.py:240-321`). Independent of allocator.
- **`prose_overlay.py`** — new `mod.setting("prose_overlay_bundle_enabled_hat_styles", type=str, default="colors-only")` if we want a voice-facing switch (`"colors-only"` | `"colors-plus-shapes"` | JSON-literal). Alternatively, a boolean `prose_overlay_enable_bundle_shapes: bool` that toggles between shape-off and a hardcoded shape-on default map. Voice: `overlay bundle shapes on/off`.

## 5. Existing homophone-shape system — how it piggybacks

Reading `HOMOPHONE_SHAPES_PLAN.md §3-4`:

**Behavior that survives untouched:**
- **Per-group stability** — `shim/shapes.py:459-467` (Pass 1 harvest by `gid_to_shape`) keeps a group's shape across edits. Cursorless's allocator doesn't have group semantics; it operates on `visible_tokens × graphemes × styles`. Option (b) keeps this layer.
- **Memoization** — `shapes.py:349-353, 419-422` bounded `(rev, frozenset(flagged), tokens-at-flagged)` cache. Bundle round-trip is JSON-serialization-heavy; keep this cache as a JS-call skip.
- **Pool overflow** — `shapes.py:479-487` `break` on `StopIteration`. Cursorless's allocator returns *no hat* for overflowed tokens (`allocateHats.ts:115-117`), which surfaces as a missing dict entry — same fall-back-to-underline semantic per plan §4.8.
- **Spillover semantics** — `ui/draw_tokens.py` treats absent `shape_assignments[idx]` as "underline-only". Bundle's missing-hat = same absence.

**Behavior that collapses / needs reconciliation:**
- **Per-group vs per-visible-token allocation.** Cursorless allocates one style per (grapheme, visible token); prose-overlay's `compute_shape_assignments` allocates one shape per group across all group-member tokens. If we naively call cursorless on the full `tokens` list with `enabledHatStyles = ten shape-suffixed entries for one color`, we get 10 assignments across visible tokens, *not* 10 assignments across groups. **Only option (b) preserves ISC-14c.**
- **Same-group-same-shape semantic (ISC-14c)** — requires pre-projecting each flagged group to a representative token, calling the bundle with that projected list, then fanning the returned shape back across all group members. That's the ~50 LOC option-(b) wrapper.

**New tests (draft names only, not impls):**
- **L1** (Python shim behavior):
  - `L1.28: same-group tokens land on same bundle-assigned shape` — projected-token round-trip preserves ISC-14c.
  - `L1.29: bundle shape overflow falls through to underline` — 11 distinct groups, only 10 get shapes.
  - `L1.30: enabledStyles config passed through hats_js.compute_hat_assignments` — round-trip JSON matches injected map.
  - `L1.31: fallback path returns no shape when bundle unavailable` — mirrors existing `_using_fallback` semantics.
- **L5** (resolver/allocator parity — cross-language contract):
  - `L5.4: python vs js shape allocation identical for a canonical buffer` — build the enabled-styles map by hand, assert bundle result matches option-(b) Python group-projection.
  - `L5.5: shape carryover under buffer edit matches Python allocator` — proves shape stability is preserved when the bundle is the source.

## 6. Risk register

1. **Semantic mismatch — cursorless allocates per visible token, homophones want per group.** This is the load-bearing risk. Full replacement (§4 option a) would silently *degrade* ISC-14c (shipped 2026-06-30, `shim/shapes.py:361-501` allocator is per-group). Option (b) mitigates but introduces a projection layer that must stay in sync with the bundle. See OQ3.
2. **Bundle-size / cold-start.** `proseStandalone.ts:102-114` grows by 99 entries. QuickJS eval cost of the additional map is negligible per `js/prose_allocate_hats.js` load timing (~40 ms cold start today per Talon logs; +99 entries adds <1 ms). But hot-path allocation cost scales with `enabledHatStyleNames.length` per `allocateHats.ts:86-88` (map init) and `:159` (per-grapheme loop) — 11× the pool means 11× the per-grapheme candidate list length. Order-of-magnitude: still sub-ms per allocation for our token counts, but measure before ship.
3. **Identity stability across bundle rebuilds.** `HatStability="balanced"` (default in `shim/hats_js.py:59`) uses stability across `oldAssignments` (`proseStandalone.ts:207-219`). Old assignments carry `color` (bare color); if the bundle bump switches to `styleName` (e.g. `"blue-frame"`), the stability comparator sees a **schema change** on first run and thrashes every hat. Mitigation: version-tag old assignments and have `hats_js.py` migrate `color → styleName` on load (append no shape suffix). One-time thrash on version bump only.
4. **JS-resolver default-on dependency (ISC-8 partial-green, 2026-06-30).** Already flipped; not a blocker. Shape support in the resolver bundle (`proseTargetsStandalone.ts`) rides the same signature change — verify `ProseHatMap.getToken` lookup key (`:211`) with shape-suffixed styles works end-to-end. Slice-independent from `prose_allocate_hats.js` because targets bundle receives its hat map from Python, not from the allocator directly.
5. **ISC-9 (Python resolver retirement) blocker status.** Not a blocker. ISC-9 gates on 3 clean live sessions of ISC-8; independent of shape substrate. Shape work can land while the Python resolver fallback still exists — the fallback path (`prose_overlay_cursorless_resolve.py`) is color-only and stays that way (shape addressing is bundle-only surface, not something the Python re-impl ever needs to replicate).
6. **Voice-grammar coupling.** REBUTTAL §5 mentions `take blue frame air`-style Cursorless grammar could coexist once shapes are in the bundle. `prose_overlay.talon` and `prose_overlay_cursorless.talon` don't currently emit shape-qualified `decoratedSymbol` marks. Enabling that is a separate slice — the substrate lands here, the grammar surface lands after.
7. **`prose_actions.js` (9 KB) is hand-maintained** and not covered by `build-js.ts`. Any shape-suffixed style names flowing through actions need a spot-check. Low probability of breakage (actions consume resolved targets, not raw style names) but worth an audit.

## 7. Tier + rough size

- **Tier:** Cross-layer. **Bundle rebuild (Tier 2 per REBUTTAL §5 refinement) + shim wiring (Tier 2) + optional voice-grammar surface (Tier 3, deferred).** Render layer is Tier 3, already-shipped (mouse-clock SVG lift, `shim/shapes.py:509-576`).
- **Effort:** Week-long slice. ~1 day for the bundle rebuild + local verify, ~2 days for the option-(b) shim wrapper + tests, ~2 days for parity harness (L5.4, L5.5) + live verify + rollback plan.
- **Splits naturally into 3 slices:**
  - **Slice 1 (Bundle):** un-strip `PROSE_HAT_STYLES` in `proseStandalone.ts`, add 5th arg to `proseAllocateHats`, add `styleName` field to the return value, rebuild both bundles, verify no regression under color-only default (backward-compat harness).
  - **Slice 2 (Shim option b):** `hats_js.py` accepts `enabled_styles`, `shapes.py` gains a `compute_shape_assignments_via_bundle` sibling that group-projects → bundle-calls → unpacks. Setting-gated behind `prose_overlay_bundle_shapes`, default OFF. Both allocators live in parallel; instance field unchanged.
  - **Slice 3 (Switch + retire):** flip `prose_overlay_bundle_shapes` default ON after 3 clean sessions, retire the Python group-allocator's Pass-1/Pass-2/Pass-3 body (keep the projection layer). Delete `_SHAPE_CACHE` if the bundle is memoized elsewhere.

## 8. Open questions

- **OQ1 — Style-suffix syntax.** Does the bundle carry style names as `"blue-frame"` (per `targetDescriptorV2.types.ts:27` template-literal type) or a structured object `{color, shape}`? Template-literal is Cursorless's native format and requires the least translation, but adds a `.split("-")` on the Python side of every read. Structured object is cleaner but forks from upstream.
- **OQ2 — Full 99-entry map, or subset?** Cursorless VS Code enables shapes via a user setting (`cursorless.hatStyles`) with subsets like "colors only" or "colors + eye/bolt". Should prose-overlay's bundle default to the full 99, or a config-driven subset? A subset means the map's default is decision-load-bearing.
- **OQ3 — Option (a) full replacement vs option (b) projection wrapper.** §4 recommendation is (b), but (a) becomes viable if we accept relaxing ISC-14c to "same-group-same-shape-usually" (bundle stability across visible tokens is high but not group-perfect). Which semantic wins?
- **OQ4 — Backward-compat window.** Keep `color` alongside `styleName` in the return dict for one release, or hard-cut? Hard-cut simplifies shim code; keep-both survives partial-rebuild states (bundle updated, shim not yet).
- **OQ5 — Enabled-shapes runtime toggle surface.** Voice command `overlay bundle shapes on/off` (boolean), or `overlay bundle shapes {name}` (per-shape flip)? Cursorless VS Code exposes per-shape; prose-overlay's homophone use case wants pool-atomic (all 10 or none).
- **OQ6 — Verify `chooseTokenHat` behavior with shape-suffixed styles.** `chooseTokenHat.ts` treats `HatStyleName` as opaque; expected no-change, but a Slice-1 verify test needs to prove that `"blue-frame"` doesn't lose to `"blue"` in a preference tie because of the sort key.
- **OQ7 — Does `prose_actions.js` need to be brought into `build-js.ts`?** It's 9 KB hand-maintained today; if it ever reads style names it needs the shape suffix. §6 risk 7 is low-prob but worth a one-hour audit before Slice 1 ships.

---

**Summary line:** un-strip cursorless's shape-capable allocator surface into the bundle (source-level, ~2 KB delta), wire an opt-in `enabled_styles` arg through `hats_js.py`, keep `compute_shape_assignments` as a group-projection layer above it, land in 3 slices.
