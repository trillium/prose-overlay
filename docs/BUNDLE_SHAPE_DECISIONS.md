# Bundle Shape Decisions — resolving BUNDLE_SHAPE_SCOPE.md OQs

> Companion to [`BUNDLE_SHAPE_SCOPE.md`](./BUNDLE_SHAPE_SCOPE.md). Every OQ from §8 gets one section here with the chosen option and the rationale that led to it. Written during Slice 1 implementation and appended by later slices as decisions ossify.
>
> **Doctrine**: when in doubt, favor "option b" projection-layer preservation over "option a" full replacement, so ISC-14c (per-group-same-shape allocator, shipped 2026-06-30) is not silently regressed by the bundle round-trip.

---

## OQ1 — Style-suffix syntax

**Decision:** Template-literal `"blue"` / `"blue-frame"` (Cursorless native).

**Rationale.** This is the native format of `HatStyleName` at `packages/common/src/types/command/legacy/targetDescriptorV2.types.ts:26-27` — `HatColor | \`${HatColor}-${HatNonDefaultShape}\``. Encoding as a structured `{color, shape}` object would fork the bundle's internal representation from every other place cursorless touches style names, breaking `chooseTokenHat` / `getHatRankingContext` / `HatCandidate.penalty` sourcing which all consume `HatStyleName` opaquely. The Python-side `.split("-")` cost is one line at the shim boundary; the return dict grows a `styleName` field alongside the legacy `color` field so the old prose_overlay callers keep working while new callers can read the fully-qualified name.

---

## OQ2 — Full 99-entry map, or subset?

**Decision:** Bundle default stays **backward-compatible** (9-color pool, no shapes). Shapes are opt-in via the new 5th arg `enabledStylesJson`. When caller passes a shape-enabled map, the bundle uses it verbatim.

**Rationale.** The 99-entry map is *available* to the caller but not *forced*. Two reasons: (1) Slice 1 must not regress the color-only default — a 118/118 baseline exists and today's live behavior depends on the 9-entry pool. (2) The homophone use case wants a very small subset — one designated color (e.g. `"gray"`) crossed with the 10 shapes — not the full cartesian product. Default-full would waste hot-path work per §6 risk 2 (allocator cost scales with pool length; 11× the pool = 11× the per-grapheme candidate list). So the bundle exposes the capability but does not decide the policy — the shim layer does.

The 5th arg accepts any `HatStyleMap`-shaped JSON. When omitted, the bundle uses `PROSE_HAT_STYLES` verbatim.

---

## OQ3 — Option (a) full replacement vs option (b) projection wrapper

**Decision:** **Option (b) projection wrapper.**

**Rationale.** ISC-14c ships per-group-same-shape allocation (2026-06-30). The Python allocator `compute_shape_assignments` in `shim/shapes.py` clusters flagged tokens by group id first, then assigns one shape per group. Cursorless's allocator operates on `visible_tokens × graphemes × styles` — it does not have group semantics. A full replacement (option a) would silently degrade ISC-14c to "same-group-usually-same-shape" because the per-visible-token allocation would sometimes hand out `frame` to `there` and `bolt` to `their` in the same buffer.

The projection wrapper keeps `compute_shape_assignments` as the authoritative group-shape source and calls the bundle for the *letter+color* hats (via `compute_hat_assignments` in `hats_js.py`) using the group-level shape as the style suffix on the flagged tokens. This preserves the ISC-14c invariant intact — the bundle never gets to decide which token in a group wears which shape.

Slice 3 gates the projection path behind a new opt-in setting (default OFF) so the Python allocator stays canonical until we have a clean live verdict on the projection.

---

## OQ4 — Backward-compat window

**Decision:** Keep `color` alongside `styleName` in the return dict. Two-release-window; delete `color` only after the shim has fully migrated to `styleName`.

**Rationale.** Existing `shim/hats_js.py:_using_fallback` post-validate loop reads `v["color"]` verbatim at line 140. Hard-cutting the field would break the shim on the first Slice-1 rebuild before the Slice-2 migration lands. The bundle returns both fields; the Python side migrates to reading `styleName` (falling back to `color` for pre-bump bundles) in Slice 2. `color` field carries the pre-`-` split (i.e. `"blue-frame"` → `color: "blue", styleName: "blue-frame"`); consumers that only care about color get the same value they got yesterday.

---

## OQ5 — Enabled-shapes runtime toggle surface

**Decision:** Deferred — no voice command in Slice 3. The Slice 3 flip surface is a static `mod.setting("prose_overlay_use_cursorless_shape_allocator", default=False)`; runtime toggle can be added later once the projection is live-verified.

**Rationale.** The setting exists to gate the projection wrapper, not to expose per-shape configuration to the user. If a per-shape voice toggle is wanted later, it lives in a separate module (like the existing `overlay shapes homo on/off`) and does not need bundle changes — it flips the `enabled_styles` dict that gets passed to `compute_hat_assignments`.

---

## OQ6 — Verify `chooseTokenHat` behavior with shape-suffixed styles

**Decision:** Add an L2 grep-test on the rebuilt bundle asserting shape identifiers survive esbuild.

**Rationale.** `chooseTokenHat` treats `HatStyleName` as opaque; the sort key is `penalty` then `styleName` alphabetical. `"blue"` vs `"blue-frame"` sort deterministically by length-then-lex, matching Cursorless upstream behavior. No source-level change to `chooseTokenHat.ts` is needed. The verification we care about is: the rebuilt bundle CONTAINS the shape identifiers (post-tree-shake) so the enabled-styles arg the shim passes in gets recognized. L2 grep-test on `js/prose_allocate_hats.js` for `frame` / `HatStyleName` covers that.

---

## OQ7 — Does `prose_actions.js` need `build-js.ts` coverage?

**Decision:** Audit only — no change required for Slice 1.

**Rationale.** `prose_actions.js` is 9 KB hand-maintained and consumes *resolved targets* (a hat map keyed by `styleName`), not raw hat allocations. Since Slice 1 does not change the resolver bundle's hat-map input shape (that's a Slice 2 concern via `proseTargetsStandalone.ts`), `prose_actions.js` does not need to change here. When Slice 2 adds `styleName` to the resolver bundle's hat-map lookup key, we audit `prose_actions.js` at that point.

---

## Slice status

- **Slice 1 (bundle un-strip + 5th arg)** — landed.
- **Slice 2 (shim projection wrapper + stability schema migration)** — landed.
- **Slice 3 (opt-in setting + retire Python allocator body)** — landed.
