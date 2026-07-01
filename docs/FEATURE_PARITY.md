# Feature Parity — Text Editor Mimicry

> prose-overlay is fundamentally a text editor implemented on a Talon canvas.
> This doc enumerates the features we expect to mimic, with status per feature.
> Three primary axes name the section headers (dictation insertion, key-based
> insertion, cursorless parity); each row is one verifiable affordance.

## Status legend

- `[x]` — **shipped**: works today, regression-tested headlessly where possible
- `[~]` — **partial**: works in some cases, gap documented in the row
- `[ ]` — **not started**: planned but not yet implemented
- `[—]` — **out of scope**: intentionally not a goal for this overlay

When a row has a commit SHA or ISC reference, that's the durable record.

---

## 0. Test coverage cross-walk (audit, 2026-06-30)

> Run `python3 scripts/headless-verify.py` to re-run the suite — current state 62/62 (Layer 5 added 2026-06-30 with the F9 default flip; 16 new resolver-parity rows).

### 0a. Headless coverage — what each test proves

| Test ID | Layer | What it proves | Feature row(s) it covers |
|---|---|---|---|
| `L1.1` | pure-python | `ProseBuffer()` constructs | §1 / §7 substrate |
| `L1.2` | pure-python | `add_text("testing testing one two three") → 5 tokens` | §1 raw-prose-to-tokens (buffer half) |
| `L1.3` | pure-python | `undo()` restores prior state | §7 undo |
| `L1.4` | pure-python | `redo()` replays | §7 redo |
| `L1.5` | pure-python | `commit_start + 2× add_text + commit_end = 1 undo step` | §7 commit bracket |
| `L1.6` | pure-python | `rev` advances monotonically | §7 substrate (cache invalidation) |
| `L1.7` | pure-python | `compute_hat_assignments` for letters | §5 letter-hat dot |
| `L1.8` | pure-python | digit token gets hat (Python fallback) | §2 digits get hats, §5 hats on digits/punct |
| `L1.9` | pure-python | punct token gets hat (Python fallback) | §2 punct get hats, §5 hats on digits/punct |
| `L1.10` | pure-python | end-to-end `["testing","testing","123"]` all hatted | §2 digit hats (full repro) |
| `L1.11` | pure-python | "air" + "bat cap" → "abc" (letter extend) | §2 NATO letter extend |
| `L1.12` | pure-python | letter-extend then undo restores prior token | §2 + §7 |
| `L1.12b` | pure-python | "bubble" + "_" + "t" + "o" + "p" → "bubble_top" | §2 word+chars compose, §11 user repro |
| `L1.13` | pure-python | `ProseOverlayState.reset()` wipes data | §8 overlay reset |
| `L1.14` | pure-python | `reset()` preserves object identity | §8 overlay reset safety |
| `L1.15` | pure-python | `hint_enabled()` returns True by default | §5 homophone underline (default-on contract) |
| `L1.16` | pure-python | `is_flagged("their")` / `is_flagged("there")` | §5 homophone CSV load |
| `L1.16b` | pure-python | `shapes_enabled()` returns True by default | §5 shape hats (default-on contract) |
| `L1.17` | pure-python | `add_text("the_quick_brown_fox") → 1 token` | §3e code formatter buffer contract |
| `L1.18` | pure-python | `add_text("theQuickBrownFox") → 1 token` | §3e code formatter buffer contract |
| `L1.19` | pure-python | `add_text("The Quick Brown Fox") → 4 tokens` | §3e title-case splits on spaces |
| `L1.20` | pure-python | `HAT_SHAPES` is 10 strings | §5 shape hats vocab |
| `L1.21` | pure-python | `shape_pool() == HAT_SHAPES` | §5 shape hats public API |
| `L1.22` | pure-python | 10 SVG files exist in `svg/` | §5 shape hats assets |
| `L1.23` | pure-python | `_parse_svg_entries` returns ≥10 entries | §5 shape hats parser |
| `L2.1` | bun | bundle loads | §5 JS allocator alive |
| `L2.2` | bun | `proseAllocateHats(["foo","bar"])` returns hats | §5 letter-hat dot (JS path) |
| `L2.3` | bun | `proseAllocateHats(["123"])` returns hat | §2 digits get hats (JS path) |
| `L2.4` | bun | `proseAllocateHats(["!"])` returns hat | §2 punct get hats (JS path) |
| `L2.5` | bun | end-to-end `["testing","testing","123"]` all hatted (JS path) | §2 digit hats (full repro, JS path) |
| `L2.6` | grep | hats bundle: shape identifiers (`frame`, `crosshairs`) + `styleName` + `proseBuildEnabledHatStyles` survive tree-shake; targets bundle: `WordScopeHandler` present | §5 shape hats (JS un-strip contract, Slice 1) |
| `L2.7` | bun | `proseAllocateHats` accepts 5th `enabledStylesJson` arg + returns `styleName` (backward-compat + shape-enabled paths) | §5 shape hats (Slice 1 5th-arg round-trip) |
| `L2.8` | grep | resolver bundle canonical inventory — 13 must-have identifiers (10 wishlist stages + sub-word substrate) fail-closed | wishlist item #14 (regression guard for silent tree-shake) |
| `L2.9` | grep | actions bundle canonical inventory — 7 shipped actions fail-closed, 6 planned actions (swap / pasteAtDestination / wrap / insertCopyBefore / insertCopyAfter / reverseTargets) fail-informational | wishlist item #14 (ratchet — planned → must-have per shipping PR) |
| `L3.1`–`L3.10` | stubbed-talon | test-driver dispatch routes commands to actions correctly | §8 test driver (all cmds: add, show, hide, dump, delete_hat, add_letters, add_chars, insert_format_code, reset, clear_buffer, bogus, malformed JSON, _pos advance, set on/off) |
| `L4.1` | meta-audit | INTERNAL + CURSORLESS Python layers carry zero talon imports (top-level or lazy) | §3 cursorless portability (substrate ports to non-Talon environments) |
| `L5.1`–`L5.10` | parity | `MANUAL_VERIFICATION.md` rows 1–10 Python ↔ JS resolver agree on token range output for primitive / colored-mark / extendThroughStartOf / extendThroughEndOf / bring-source / move-source target shapes | §3a, §3b, §3e, §3f (F9 default-on parity contract for actions, ranges, lists, bring/move) |
| `L5.11`–`L5.13` | parity | `MANUAL_VERIFICATION.md` rows 13–15 — containingScope document/line whole-buffer resolution | §3c (document/line scopes), §3f |
| `L5.14`–`L5.16` | parity | `MANUAL_VERIFICATION.md` rows 18–20 — range target, list target, range driving applyFormatter | §3b, §3e, §3f |

**Headless coverage by surface:**
- ✅ Buffer state machinery — comprehensive (L1.1–L1.6, L1.11–L1.14)
- ✅ Python hat allocator — comprehensive (L1.7–L1.10)
- ✅ JS hat allocator — comprehensive (L2.1–L2.5)
- ✅ Homophone module data layer — strong (L1.15–L1.16b)
- ✅ Shape module vocab + assets + parser — strong (L1.20–L1.23)
- ✅ Test-driver command dispatch — comprehensive (L3.*)
- ✅ Formatter output buffer contract — adequate (L1.17–L1.19)
- ✅ Codebase layer portability — comprehensive (L4.1)
- ✅ Python ↔ JS resolver parity — strong for 16 of 20 MANUAL_VERIFICATION rows (L5.*); remaining 4 are live-only (cursor placement is action-level, surrounding-pair delimiter names need bundle bridging)

### 0b. Shipped features with NO headless test (live-verify-only)

These are `[x]` in the tables below but the runner does NOT exercise them. Verification depends on running Talon and observing behavior.

| Feature row | Why live-only |
|---|---|
| §1 raw-prose grammar routing | `<user.raw_prose>` requires Talon's grammar matcher |
| §1 number_string routing | same — Talon capture |
| §1 trailing-punct split (talon side) | community grammar; buffer side IS tested via `_split_trailing_punct` |
| §1 phrase-ender insert | community grammar |
| §1 auto-show on dictation toggle | end-to-end mode + tag + canvas hand-off |
| §1 window-name prefix retarget | Talon capture + window switching |
| §1 history recall | action surface; voice rule routing |
| §3a–§3f Cursorless verb end-to-end (action → buffer mutation) | action layer requires Talon's grammar to construct the target dict; resolver parity IS now headless-tested via Layer 5 for 16 of 20 MANUAL_VERIFICATION rows |
| §3d surrounding-pair via JS resolver | bundle expects internal delimiter names; prose grammar emits prose-side names — bridge slice pending |
| §4 token / range selection | depends on cursorless resolver end-to-end |
| §4 selection highlight render | live Skia paint |
| §5 hats on digits/punct rendered visually | live Skia paint (allocator IS tested) |
| §5 homophone underline rendered | live Skia paint (data layer IS tested) |
| §5 pre-execution flash | live timing + paint |
| §5 hat-JS-fallback orange chrome | live; allocator failure path |
| §5 cursor blink / change-mode amber | live render |
| §5 shape hats rendered | live Skia paint (vocab/parser tested) |
| §6 history panel / confirm / auto / retarget / anchor / dismiss / viewport | actions + voice |
| §7 dictation coalescing toggle behavior | timing-dependent; threshold logic isolated but not tested under simulated time |
| §8 always-on JSONL diff + log rotation | live writes |
| §8 draw-time hook coverage | live |
| §8 paper-trail slice A | env-gated faulthandler — needs crash fixture |
| §9 every rule-specificity assertion | Talon grammar matcher — there is no headless grammar simulator |

### 0c. Coverage stats

- **Total shipped features (`[x]`):** ~67 (added: §3f JS resolver default-on)
- **With headless regression tests:** ~25 (added Layer 4 + Layer 5; some tests cover multiple rows)
- **Live-only verification:** ~42
- **Headless coverage ratio:** ~37%

The Layer 5 resolver-parity harness was the highest-leverage gap-2 fill from §0d below — running every headless-expressible MANUAL_VERIFICATION row through BOTH Python AND JS resolvers and asserting agreement closed the §3a–§3f gap by ~16 rows. Remaining live-only coverage in §3 is cursor placement (action-level) and surrounding-pair (bundle delimiter-name bridge). Everything that depends on Talon's grammar matcher, Skia render pipeline, or end-to-end action chain still stays in live-verify until we build harness layers for those (a stubbed action-chain layer would lift this further; a Talon-grammar simulator would lift it further but is expensive).

### 0d. Highest-leverage gaps to consider adding

If we want to push the ratio up cheaply:

1. **Buffer-side trailing punct test** — `ProseBuffer().add_text("hello.") → ["hello", "."]`. Easy add to L1.
2. ~~**Resolver-side scope tests** — feed synthetic target dicts into `_resolve_target_to_token_range` and assert token ranges.~~ **Done 2026-06-30 — Layer 5 parity harness; 16 of 20 MANUAL_VERIFICATION rows headless-tested.**
3. **Action chain stubbed** — stub Talon enough to import `prose_overlay_actions_*` and exercise the action methods. Catches integration bugs the dispatch-routing + resolver-parity tests miss (cursor placement, flash timing, bring/move destination logic).
4. **Underline-default-on assertion at the SETTING level** — currently L1.15 tests the runtime flag; we don't test the `mod.setting(default=True)`. Mostly a doc-vs-code consistency guard.
5. **Coalescing threshold logic** — `_GROUP_DELAY_S` boundary test without actual timing (inject timestamps).

Items 2 ✅ + 3 are the meaningful coverage leaps. Items 1, 4, 5 are quick wins.

---

## 1. Dictation insertion

> Spoken prose becomes tokens in the buffer. The "type continuously" model.

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[x]` | Raw prose → tokens | "the quick brown fox" → 4 tokens | `prose_overlay_dictation.talon:10` |
| `[x]` | Number words → number string | "five hundred twenty three" → "523" | `<user.number_string>` route |
| `[x]` | Trailing punctuation splits to own token | "hello." → ["hello", "."] | `ProseBuffer._split_trailing_punct` |
| `[x]` | Phrase enders insert correctly at end of utterance | "test period" → "test." | community grammar |
| `[x]` | Auto-show overlay on any dictation phrase | tag-gated | `prose_overlay_toggle_auto_dictation` |
| `[x]` | Window-name prefix retargets focus then dictates | "edgar hello world" | `prose_overlay_dictation.talon:23` |
| `[x]` | History recall — last N confirmed prose entries | `overlay history` | `ui/actions_history.py` |
| `[~]` | Insertion at cursor preserves split boundary | dictating mid-buffer w/ cursor active inserts at gap, but doesn't split a token if cursor is mid-token | gap-based; mid-token cursor doesn't exist yet (see §2) |

## 2. Key-based insertion

> Character-at-a-time inputs. The "type one key" model — but voice-driven.
> When a cursor is active, the keystroke goes at the cursor position (even
> mid-token); without a cursor, it extends the last token.

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[x]` | NATO letter forms append as chars (extend last token) | "trap trap trap" → "ttt" | `prose_overlay_add_chars`, `fbb7581` |
| `[x]` | Symbol forms append as chars (extend last token) | "downscore" → "_" extends | `fbb7581` |
| `[x]` | Word + chars compose into one token | "bubble downscore trap odd pit" → "bubble_top" | full repro test L1.12b |
| `[x]` | Digits get visible hats | "123" → gray-1 | `aa2909e`, `39b4cb6` |
| `[x]` | Punct get visible hats | "!" → gray-! | same |
| `[ ]` | Cursor-targeted char insertion **mid-token** | with cursor inside "hello", saying "trap" yields "helxlo" | currently falls back to `add_text` and produces new gap-token |
| `[ ]` | Mid-token char delete (backspace inside a word) | with cursor mid-token, voice "delete left" pops the char to the left | no character-level delete primitive yet |
| `[ ]` | Mid-token cursor positioning | "pre letter X" → cursor before the X in "fox" | cursor model is gap-between-tokens only |
| `[ ]` | Visible character-level cursor inside a token | the cursor draws between characters, not just gap | render is token-gap only |
| `[ ]` | Letter hat addressability for digits/punct | "take 1" hits the digit token | hat painted; voice capture `<user.letter>` only accepts a-z |
| `[ ]` | Number hat namespace | `chuck num 1` deletes a digit token by index | future slice; ISA Decisions 2026-06-30 |

## 3. Cursorless parity

> Cursorless verb surface against the in-window buffer. Many shipped (Phase 2
> of ISA); sub-word handling is the biggest open gap.

### 3a. Simple actions

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[x]` | `chuck` / `take` / `change` / `clear` / `replace` on hat target | "chuck air" deletes token at hat 'a' | ISC-1 |
| `[x]` | `pre`/`post` cursor positioning | "pre air" → cursor before hat 'a' | shipped |
| `[x]` | Change mode (delete + cursor + dictation insert) | "change air the quick" → deletes hat 'a', inserts "the quick" | shipped |
| `[x]` | **Clone: `clone <hat>` / `clone up <hat>`** | `clone air` on std → `the air air ball drum echo` | wishlist item #12 (`docs/BUNDLE_REST_SCOPE.md §Cluster A / §2 #12`). Both `insertCopyAfter` (map for `clone`) and `insertCopyBefore` (map for `clone up`) added to `js/prose_actions.js` via `proseActionsStandalone.ts` (cursorless commit — see BUNDLE_REST_SCOPE §7). Zero new grammar — rides the composable `{user.cursorless_simple_action} <user.cursorless_target>` rule at `prose_overlay_cursorless.talon:47` because cursorless-talon's `spoken_forms.json` puts both names in the `simple_action` LIST. Python: added to `_SUPPORTED_SIMPLE_ACTIONS`. Headless: L2.10 / L2.11 (JS bundle probe — insert-op geometry) + L2.9 must-have (bundle inventory ratchet). |
| `[x]` | **Reverse: `reverse <range-or-list target>`** | `reverse air past drum` on std → `the drum ball air echo` | wishlist item #13 (`docs/BUNDLE_REST_SCOPE.md §Cluster A / §2 #13`). Multi-target action — `reverseTargets` added to `js/prose_actions.js`. Zero new grammar (composable rule) because cursorless-talon's `spoken_forms.json` puts `reverseTargets` in the `simple_action` LIST. Multi-target signature: Python resolves all ranges, packs them into an array in the source slot of the existing 4-arg `proseRunAction` (preserves ABI). The bundle sorts targets by document position, reverses the extracted texts, and emits N replace ops. Python: `shim/actions_js.py:run_action_multi` + dedicated branch in `prose_overlay_run_action`. Headless: L2.12 (multi-range replace geometry) + L2.9 must-have. |

### 3b. Range and list targets

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[x]` | RangeTarget with explicit anchor | "chuck air past drum" | ISC-2 |
| `[x]` | RangeTarget with implicit anchor (cursor) | "chuck past this" | ISC-2 |
| `[x]` | ListTarget multi-target | "chuck air and bat" | ISC-3 |

### 3c. Scopes

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[x]` | sentence | "chuck sentence" | ISC-4 |
| `[x]` | clause | "chuck clause" | ISC-4 |
| `[x]` | string | "chuck string" (delimited) | ISC-4 |
| `[x]` | number | "take number" | ISC-4 |
| `[x]` | email | "take email" | ISC-4 |
| `[x]` | nonWhitespaceSequence | "take funk" | ISC-4 |
| `[x]` | document / line / paragraph | "chuck file" | ISC-4 |
| `[x]` | token / word / identifier / character (at the TOKEN level) | "take word" | ISC-4 |
| `[x]` | **OrdinalScope: `take first/second/... word`** | `take first word` on `the air ball drum echo` → "the" | wishlist item #7 (`docs/BUNDLE_REST_SCOPE.md §2`). **JS path only** — `OrdinalScopeStage` shipped in bundle at `js/prose_resolve_targets.js:18899`; grammar routing already flows through `<user.cursorless_target>` because `cursorless_ordinal_scope` is a `cursorless_modifier` variant (OQ2 resolved YES 2026-07-01, see `docs/BUNDLE_REST_SCOPE.md §7`). Python fallback documented as JS-only per `docs/BUNDLE_REST_SCOPE.md §2 #7` (matches sub-word / ISC-9 direction). Headless: L5.20. |
| `[x]` | **first / last modifiers: `take first/last word`** | `take last word` (cursor at end) → "echo" | wishlist item #10 (`docs/BUNDLE_REST_SCOPE.md §2`). Semantically covered by OrdinalScopeStage (`start=0` for first, `start=-N` for last per `ordinal_scope.py:46-68` `cursorless_first_last` capture); same bundle presence + grammar routing as #7. Python fallback: JS-only. Headless: L5.21. |
| `[~]` | **every scope: `take every word`** | Composed with a containing scope (`take every word file`) → 5 ranges; bare (`take every word`) → 1 range (bundle gap) | wishlist item #9 (`docs/BUNDLE_REST_SCOPE.md §2, §7`). `EveryScopeStage` shipped at `js/prose_resolve_targets.js:15505` + grammar routing free per OQ2. **Working shape**: composed modifier list `[everyScope word, containingScope document]` returns 5 ranges (L5.22). **Bundle gap**: cursorless-talon's `cursorless_simple_scope_modifier` emits the bare shape `[everyScope word]`, which our bundle returns 1 range for (default iteration-scope handling incomplete). Full user-facing `take every word` remains partial until either the shim composes the doc-scope wrap or the bundle picks up cursorless's iteration-scope default. Python fallback: JS-only. |
| `[x]` | **RelativeScope: `take next word air`** | `take next word air` on std → "ball" (token 2, the word after mark 'a') | wishlist item #6 (`docs/BUNDLE_REST_SCOPE.md §2`). **JS path only** — `RelativeScopeStage` shipped in bundle at `js/prose_resolve_targets.js:19103`; grammar routing free per OQ2 (`cursorless_relative_scope` is a `cursorless_modifier` variant). Python fallback: JS-only per `docs/BUNDLE_REST_SCOPE.md §2 #6`. Headless: L5.23. |
| `[—]` | **leading / trailing modifiers** | `chuck leading air` on prose | wishlist item #11 (`docs/BUNDLE_REST_SCOPE.md §2, §7`). **Degenerate on prose** (OQ3 resolved 2026-07-01): `LeadingStage`/`TrailingStage` shipped in bundle at :18845/:18860 and grammar routing is free per OQ2, but the returned range is the 1-char whitespace BETWEEN tokens — prose tokens have no interior whitespace, so there's no token-level semantics to expose. Bundle shape asserted stable in L5.24; user-facing surface is a no-op and should be gated at the grammar/shim layer if ever wired (out of scope for prose overlay per §10 pattern — analogue is C6/C7/C8 which are code-editor primitives). |
| `[~]` | **word scope splits formatted tokens into sub-words** | inside "one_two_three", "take second word this" → selects "two" | **JS resolver ships it** (`js/prose_resolve_targets.js:14342-14380` — `WordScopeHandler` + `WordTokenizer.splitIdentifier` + `CAMEL_REGEX`; default since 2026-06-30 F9 flip). **Python fallback does NOT split** (`cursorless/resolve.py:108-115` returns `(base_idx, base_idx)`). Headless coverage pending (sub-word L5 row). See `docs/SUBWORD_INVESTIGATION.md` for the full audit. |
| `[~]` | sub-word identity preserves joiner under replace | "word changed" on selection {two} in "one_{two}_three" → "one_changed_three" | Same status as row above: JS resolver preserves joiners inherently (engine-side behavior of `WordScopeHandler`); Python fallback can't reach because it doesn't split. Live-verify pending. |

### 3d. Surrounding pairs

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[x]` | round / box / curly / diamond / quad / twin / skis delimiters | "take quotes air" | ISC-5 |
| `[x]` | `any` / `pair` aggregation | "chuck pair" | ISC-5 |
| `[x]` | **inside / bounds modifier on surrounding pair** | `take inside round air` on `the ( air ball ) drum` → tokens 2..3 (`air ball`); `take bounds round air` → the two delimiter tokens as two ranges | wishlist item #8 (`docs/BUNDLE_REST_SCOPE.md §Cluster D / §2 #8`). **JS path only** — `InteriorOnlyStage` shipped at `js/prose_resolve_targets.js:15819`, `ExcludeInteriorStage` at `:15828`; grammar routing free per OQ2 (`cursorless_interior_modifier` is a `cursorless_modifier` variant per `~/.talon/user/cursorless-talon/src/modifiers/modifiers.py:33`, and `bounds` → `excludeInterior` rides `cursorless_simple_modifier` which is likewise a variant). Zero new prose-overlay grammar rules. Python fallback: asymmetric-gap — `cursorless/resolve.py:174-180` has no `interiorOnly`/`excludeInterior` handler; documented as JS-only per `docs/BUNDLE_REST_SCOPE.md §Cluster D` (matches sub-word / ISC-9 direction — retire-Python makes the split moot). Spoken forms per `~/.talon/user/cursorless-talon/src/spoken_forms.json`: `inside` → `interiorOnly`, `bounds` → `excludeInterior`. `excludeInterior` returns TWO ranges (the delimiter tokens themselves) — cursorless's "Bounding paired delimiters" semantics per `~/.talon/user/cursorless-talon/src/cheatsheet/sections/modifiers.py:57`. Headless: L5.25 (interiorOnly), L5.26 (excludeInterior). |

### 3e. Bring / move / formatter

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[x]` | bring (copy src token → dst hat) | "bring air to drum" | ISC-6 |
| `[x]` | move (cut src → dst hat) | "move air to drum" | ISC-6 |
| `[x]` | **swap (exchange src ↔ dst texts)** | `swap air with drum` on std → `the drum ball air echo` | wishlist item #3 (`docs/BUNDLE_REST_SCOPE.md §Cluster A / §2 #3`). `swapTargets` geometry added to `js/prose_actions.js` via cursorless `proseActionsStandalone.ts`. Uses the existing two-target ABI (source + dest slots). Dedicated grammar rule at `prose_overlay_cursorless.talon` after the bring/move rule because `swapTargets` lives in the `cursorless_swap_action` LIST (not `simple_action`) and takes a `cursorless_swap_targets` capture with two targets. Python: `prose_overlay_swap(cursorless_swap_targets)` resolves both sides and calls `_js.run_action('swapTargets', ...)`. Headless: L2.13 (bundle probe — two replace ops) + L2.9 must-have. |
| `[x]` | applyFormatter on a hat target | "format snake at fox past bat" | ISC-7 |
| `[x]` | Prose formatters (say/sentence/title) routed to buffer | "sentence the quick brown fox" → "The quick brown fox" | `5652b0e` |
| `[x]` | Code formatters (snake/camel/dotted/...) routed to buffer | "snake the quick brown fox" → "the_quick_brown_fox" | `31df606` |
| `[x]` | **wrap target with paired delimiter** | `round wrap air` on std → `the (air) ball drum echo`; `curly wrap air past drum` → `the {air ball drum} echo` | wishlist item #5 (`docs/BUNDLE_REST_SCOPE.md §Cluster B`). ABI-widening: `proseRunAction` grew a 5th `options` arg for `{left, right}` delimiter strings; backward-compat preserved via `optionsJson === undefined` branch in the bundle. Cursorless-side geometry: `actionWrapWithPairedDelimiter` in `proseActionsStandalone.ts` (`986554267`). Grammar rule at `prose_overlay_cursorless.talon` mirrors cursorless.talon C7: `<user.cursorless_wrapper_paired_delimiter> {user.cursorless_wrap_action} <user.cursorless_target>` — reuses cursorless-talon's existing paired_delimiter capture so the 12-entry cursorless delimiter vocabulary flows through unchanged. Multi-range targets wrap each resolved range with the same delimiter pair (matches upstream `Wrap.ts`). VSCode-only `rewrap` action dispatches back to cursorless proper. Headless: L2.14 (two insert ops around target range) + L2.9 must-have. |

### 3f. JS resolver migration

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[x]` | JS resolver is the default (F9 migration) | `user.prose_overlay_use_js_resolver = True` (default since 2026-06-30) | flipped default ON 2026-06-30; native cursorless `processTargets` pipeline now drives all target resolution. Headless parity covered by `scripts/headless-verify.py` Layer 5 (16 of 20 MANUAL_VERIFICATION.md rows; remaining 4 are live-only — see ISA-8 partial-green note). |
| `[x]` | Python resolver retained as safety net | `user.prose_overlay_use_js_resolver = False` falls back to `prose_overlay_cursorless_resolve.py` | gated by setting; kept until ISC-9 retires it after 3 clean live sessions. |
| `[ ]` | Python resolver removed once JS holds 3 sessions | grep for imports = 0 | ISC-9 |

## 4. Selection

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[x]` | Token selection via cursorless `setSelection` | "take air" → selection on token | shipped |
| `[x]` | Range selection | "take air past drum" | shipped |
| `[x]` | Selection highlight render | blue 25% alpha | `ui/draw_tokens.py:158` |
| `[~]` | Selection survives surrounding edits | preserved on undo/redo via UndoRecord fields, but currently cleared (Phase 3 work) | UNDO_REDO_PLAN §5 |
| `[ ]` | Replace selection by dictation | with selection {air}, dictating "trap odd pit" → replaces with "top" | not wired |
| `[ ]` | Sub-word selection | "take second word this" inside a snake_case token | depends on §3c sub-word resolver |
| `[ ]` | Selection extension (left/right by word) | "extend right" | no grammar |

## 5. Visual feedback

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[x]` | Letter-hat dot per token | gray + color collision per cursorless | shipped |
| `[x]` | Hats on digits and punct | "123" → gray-1 | recent |
| `[x]` | Homophone underline (always on) | dotted then solid amber after `d633473` | ISC-11 |
| `[x]` | Pre-execution flash on scope verbs | "chuck sentence" flashes before delete | ISC-15 |
| `[x]` | Hat-JS-fallback orange chrome | when JS allocator throws | ISC-10 |
| `[x]` | Cursor blink + change-mode amber zone | visible | shipped |
| `[x]` | Shape hats on flagged tokens | HOMOPHONE_SHAPES_PLAN Slices 1+2+3 all shipped: renderer (ISC-14a), per-token stability (ISC-14b), same-group-same-shape allocation (ISC-14c) |
| `[x]` | Shape panel with alternates | PHONES_SPEC Slice C shipped as ISC-14d — bubble panel with color-coded chips per shape-hatted token, `<color> <shape>` swap grammar wired |
| `[~]` | Cursorless-native shape allocation (opt-in) | 2026-07-01 — Slice 3 of `docs/BUNDLE_SHAPE_SCOPE.md` lands the projection wrapper (`shim/shape_bridge.py`) behind `prose_overlay_use_cursorless_shape_allocator` (default OFF). Python group-allocator remains authoritative for ISC-14c; setting-on routes letter+color allocation through the cursorless bundle with a shape-enabled `enabled_styles` pool. Flip via action `prose_overlay_set_cursorless_shape_allocator(1)`. |
| `[ ]` | Mid-token cursor render | character-level cursor visible inside a word | depends on §2 mid-token cursor |
| `[ ]` | Sub-word highlight | within "one_two_three", just "two" highlighted | depends on sub-word resolver |

## 6. History / window

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[x]` | History panel | `overlay history` | shipped |
| `[x]` | Confirm + paste to target window | `confirm` | shipped |
| `[x]` | Auto-show on dictation toggle | `overlay auto` | shipped |
| `[x]` | Window retargeting by name | `<user.saved_window_names>` capture | shipped |
| `[x]` | Anchor to specific window | `overlay anchor` | shipped |
| `[x]` | Dismiss without paste | `overlay dismiss` | shipped |
| `[x]` | Viewport scroll + align (Helix/Emacs) | `overlay show top` / `overlay center` | ISC-22 |

## 7. Editing primitives

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[x]` | Undo (token-grained) | `overlay undo` | ISC-23 Phase 1+2 |
| `[x]` | Redo | `overlay redo` | ISC-23 Phase 2 |
| `[x]` | commit_start / commit_end bracket (1 utterance = 1 step) | `_apply_edit_plan`, bring/move, formatter | shipped |
| `[x]` | Dictation coalescing toggle (default off) | `overlay undo group on/off` | shipped |
| `[ ]` | N-step undo / redo | `overlay undo five` | UNDO_REDO_PLAN Phase 3 |
| `[ ]` | Selection restore on undo/redo | `selection_before`/`selection_after` UndoRecord fields are populated but not read | UNDO_REDO_PLAN Phase 3 |
| `[ ]` | Cut/copy/paste through system clipboard | `take air` then `paste` | current model is confirm-to-host |

## 8. Observability and debug

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[x]` | Always-on JSONL state diff | `~/.talon/prose_overlay_debug.jsonl` | ISC-16 |
| `[x]` | One draw-time hook covers all mutations + log rotation at 5 MB | `emit_if_changed("draw")` | ISC-17 |
| `[x]` | `overlay dump` action — text snapshot to Talon log | | shipped |
| `[x]` | `overlay reset` — wipe all per-session state | | `39194b8` |
| `[x]` | Headless test driver (file queue, runtime toggle) | `scripts/test-overlay.sh add "x"` | ISC-19, `e979025` |
| `[x]` | Stack-overflow paper trail Slice A (faulthandler) | env-gated | ISC-18 |
| `[~]` | Paper trail Slice B (last_command.json preamble) | infrastructure shipped, needs live HAT_ALLOC repro | ISC-20 |
| `[x]` | Headless verification runner — three-layer | `python3 scripts/headless-verify.py` | `aa2909e` series |

## 9. Voice command vs dictation arbitration

> "When overlay is active, which utterances are commands and which are
> dictation?" Mis-routing here looks like text editor bugs.

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[x]` | Hat-targeted edits (chuck/take/pre/post/change `<user.letter>`) outrank `<user.raw_prose>` | "chuck air" deletes token, not dictates "chuck air" | rule specificity |
| `[x]` | Formatter prefixes (snake/camel/etc.) outrank raw_prose | "snake the quick" → "the_quick" not raw | `31df606` |
| `[x]` | NATO letter sequences outrank raw_prose | "trap trap" → "tt" not "trap trap" | rule specificity |
| `[x]` | Symbol keys outrank raw_prose | "downscore" → "_" not "downscore" | shipped |
| `[x]` | **`^prose overlay$` outranks raw_prose when overlay already active** | "prose overlay" while open clears buffer + keeps canvas showing | `prose_overlay.talon` rule (1 mode + 1 tag, ties context with dictation intercept; literal-anchored rule beats raw_prose capture). Action: `prose_overlay_clear_buffer`. |
| `[x]` | `overlay redo` / `overlay undo` etc. recognized inside the overlay | not consumed as dictation | shipped |
| `[ ]` | Audit: every top-level `^... overlay$` global command works when overlay is active | survey each rule in `prose_overlay_start.talon` | follow-up |

## 10. Out of scope

> These are text-editor-shaped features we are **intentionally not implementing**.

- `[—]` Find / replace dialog — use cursorless to navigate and `change`
- `[—]` Syntax highlighting — this is dictation, not code
- `[—]` Multi-buffer / tabs — single panel, single buffer (Out of Scope in ISA)
- `[—]` File save / load — buffer is ephemeral; confirm-to-host or dismiss
- `[—]` Cross-session buffer persistence — same reason (Out of Scope in ISA)
- `[—]` Autocomplete / IntelliSense — LLM-assisted typing is explicit Out of Scope
- `[—]` Browser-DOM rendering — Talon canvas only (Out of Scope in ISA)
- `[—]` Mobile / non-macOS targets — Out of Scope in ISA
- `[—]` Cursorless C6 `{call_action} <target> on <target>` — code-editor refactor primitive (wrap a target in a function-call at another target); no prose analogue. Decided 2026-07-01 via `docs/GRAMMAR_STRUCTURE_PARITY.md §3`.
- `[—]` Cursorless C8 `{insert_snippet_action} {snippet} <destination>` — language-scoped templates with variable interpolation; no analogue for a prose buffer whose confirm-to-host lands raw text. Decided 2026-07-01.
- `[—]` Cursorless C9 `{snippet_wrapper} {wrap_action} <target>` — same snippet-subsystem bucket as C8. If a prose-side wrap is later wanted, it lives under C7 (paired-delimiter wrap), not snippets. Decided 2026-07-01.
- `[—]` Cursorless C10/C11 scope visualizer — VS Code extension surface; prose-overlay renders on its own Talon canvas.
- `[—]` Cursorless C12–C22 admin (settings, sidebar, stats, tutorial, snippet migration) — all IDE/tutorial subsystem calls with no prose-overlay counterpart. Cursorless owns them outside PO's active context.

## 11. The user's three named requirements — explicit mapping

This doc was prompted by three categories you named. Mapping them to rows above:

1. **Dictation insertion** → §1 (mostly shipped).
2. **Key-based insertion** at cursor, including mid-token → §2 (partially shipped; the **mid-token character insertion** rows are the open gap that turns voice-driven char input into a real text editor).
3. **Cursorless sub-word parity** → §3c "word scope splits formatted tokens into sub-words" — this single row enables your stated example chain:
   ```
   snake one two three   →  "one_two_three|"           (shipped today; cursor mid-buffer needs row 2.cursor-pos)
   take second word this →  "one_{two}_three"          (NOT YET — needs sub-word resolver)
   word changed          →  "one_changed|_three"       (NOT YET — depends on sub-word selection)
   ```

The gap is concentrated in two substrates:
- A **sub-word resolver** that splits a token on `_-./case-boundaries` and exposes those positions to cursorless's word scope.
- A **character-level cursor** that can sit between any two characters in a token (not just gap-between-tokens), so cursor-targeted character insertion can place a char inside a word.

Both are substantial — each warrants its own plan doc (e.g. `docs/SUBWORD_PLAN.md` and `docs/CHAR_CURSOR_PLAN.md`) before implementation.

## Maintenance rule

When a row's status changes (`[ ]` → `[~]` → `[x]`), update this doc in the
same commit that lands the work. Add the commit SHA or ISC reference in the
Notes column. If a feature is removed or descoped, change to `[—]` and add
a one-line reason.
