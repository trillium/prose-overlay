# prose-overlay — Changelog

## 2026-07-01 — Phase 6 wishlist bundle expansion (28 commits + 2 regression heals)

Files: prose_overlay_cursorless.talon, prose_overlay.py, shim/actions_cursorless.py, shim/actions_core.py, shim/actions_js.py, shim/hats_js.py, shim/shape_bridge.py, shim/shapes.py, ui/actions_history.py, js/prose_actions.js, js/prose_allocate_hats.js, scripts/build-js.ts, scripts/headless-verify.py, scripts/headless_verify/{common,layer1,layer1_python,layer2,layer2_bundle,layer3_dispatch,layer4_audit,layer5,layer5_parity}.py, cursorless/resolve.py, docs/BUNDLE_REST_SCOPE.md, docs/BUNDLE_SHAPE_DECISIONS.md, docs/BUNDLE_SHAPE_SCOPE.md, docs/FEATURE_PARITY.md, docs/GRAMMAR_STRUCTURE_PARITY.md, docs/HISTORY_HIDE_RECURSION.md, docs/SCENARIOS.md, MANUAL_VERIFICATION.md, README.md, ISA.md

> **Cluster A — Rearrange actions.** `swap <hat> with <hat>` (wishlist #3, commits `c67da0326`+`129a636`+`dc3f985`), `clone <hat>` / `clone up <hat>` (wishlist #12, commit `ee1779e`), `reverse <hat> past <hat>` / `reverse <hat> and <hat>` (wishlist #13, commit `129a636`, atomic-swap semantics). Grammar rides cursorless-talon's composable-target captures; special-case reverseTargets aggregates all indices and swaps in ONE JS call. Cluster A close SHA `7f3d7f0`.
>
> **Cluster B — Wrap with paired delimiter.** `round wrap <hat>`, `curly wrap <hat>`, `quad wrap <hat>` + 9 other delimiters (wishlist #5, commits `986554267`+`3a90365`+`a0fa574`). Reuses cursorless-talon's existing `cursorless_wrapper_paired_delimiter` capture — 12-entry delimiter vocabulary flows through unchanged.
>
> **Cluster C — Modifier grammar routing (JS-only).** `take first / last / next / every`, `chuck leading / trailing` (wishlist #6/7/9/10/11, commits `08288db`, `19624f4`, `f4912cc`, `fb09e26`, `ad0736b`). All modifiers ride the composable `<user.cursorless_target>` capture through cursorless-talon's own modifier vocabulary — no new prose_overlay grammar rules. Python-fallback is asymmetric (JS-only); leading/trailing are degenerate on flat prose per `docs/BUNDLE_REST_SCOPE.md §7` (OQ3).
>
> **Cluster D — Interior / bounds.** `take inside round <hat>` (interiorOnly) + `take bounds round <hat>` (excludeInterior) close wishlist #8 (commits `4fdb6bd`+`dd68006`).
>
> **Shape allocator restoration (3 slices).** Bundle rebuild with shape-enabled cursorless allocator + 5th-arg `hatShapes` accept (commit `97215cd`); shim projection wrapper preserving per-group-shape invariant over the cursorless-native output (commit `e7322f3`); opt-in setting `user.prose_overlay_use_cursorless_shape_allocator` (default OFF, commits `c6c735c`, `b5e3c4c`). Python allocator remains primary until opt-in flip.
>
> **Bundle inventory ratchet.** L2 grep-test now covers must-have + planned actions and modifier handlers (commits `e29fc6a`, `b195562`, `d82b361`, `894d65f`, `83444463`).
>
> **Regression heals.** `dictation_insert` accepts `auto_cap` kwarg to match community prototype (commit `e4841b5`). `_shapes_enabled` runtime default flipped True → False to match `mod.setting(default=False)` (commit `2afc173`).
>
> **Layer file rename.** `layerN.py` → `layerN_scope.py` with import-path fix (commits `32c2a34`, `c722b1c`).
>
> **Docs.** README command table regenerated + shape-allocator setting row (commits `2033625`, `124c78d`). ISA.md Phase 6 opened, 18 new ISCs (ISC-25 through ISC-42), progress 26/30 → 44/48 (commit `1db2145`). This CHANGELOG entry.
>
> Headless verify: 141/141 pass (was 121/121 pre-session). Layer audit: 0 fail (2 pre-existing WARNs unchanged).

## 2026-07-01 — session 9162b0ec

Files: docs/HOMOPHONE_SHAPES_PLAN.md, docs/FEATURE_PARITY_REBUTTAL_COMMUNITY.md, docs/FEATURE_PARITY_REBUTTAL_CURSORLESS.md, docs/REBUTTAL_ASSERTIONS.md

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-06-30 — session 6766b4a1

Files: prose_overlay_canvas.py, prose_overlay_actions_cursor.py, prose_overlay_actions_core.py, prose_overlay_cursorless.talon, FALLOW_REPORT.md, PYTHON_REPORT.md, scripts/python-report.sh, prose_overlay_homophones.py, prose_overlay_draw_constants.py, prose_overlay.py

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-06-03 — session d3895255

Files: .talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay_start.talon, .talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay.py, .talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay.talon, .talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay_dictation.talon, .talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay_draw.py, .talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay_history.talon, .gitignore, scripts/gen-command-table.ts, README.md, prose_overlay_draw.py

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-05-27 — session d3895255

Files: .talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay_start.talon, .talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay.py, .talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay.talon, .talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay_dictation.talon, .talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay_draw.py, .talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay_history.talon, .gitignore, scripts/gen-command-table.ts, README.md, prose_overlay_draw.py

> AI summary pending — check ProjectDocs Handover in next session.
## 2026-05-25 — session 926e5b8a

Files: .talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay_state.py, .talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay_hats_js.py, .talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay.py

> AI summary pending — check ProjectDocs Handover in next session.
