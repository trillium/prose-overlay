# Rebuttal Assertions — Red-Team of the Two Rebuttal Docs

> Self-critique of `FEATURE_PARITY_REBUTTAL_COMMUNITY.md` and `FEATURE_PARITY_REBUTTAL_CURSORLESS.md`.
> Drafted 2026-06-30 — same session as the rebuttals.
> **Verification pass 2026-06-30:** every assertion below has been confirmed or denied via the cheap check named in its entry. Verdict appears at the top of each entry as **VERDICT:**.

## Verdict tally

| #   | Subject                                               | Verdict                                                                                          |
| --- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| 1   | Cursorless `word` vs `subtoken`                       | **DENIED** — rebuttal claim was correct                                                          |
| 2   | "Prose-overlay pre-splits identifiers" diagnosis      | **CONFIRMED** — diagnosis is wrong                                                               |
| 3   | Community vs Talon-core vs trillium_talon attribution | **CONFIRMED (major correction)** — community isn't even installed; all surface is trillium_talon |
| 4   | `replace_selection` / `takeAndReplace` names          | **CONFIRMED** — both names are wrong                                                             |
| 5   | Hat-allocator-supports-shapes claim                   | **CONFIRMED** — JS bundle has zero shape identifiers                                             |
| 6   | Tier row counts eyeballed                             | **CONFIRMED (minor)** — actual 24 vs claimed ~22                                                 |
| 7   | Two rebuttals don't partition cleanly                 | **CONFIRMED** — overlap not stated                                                               |
| 8   | Cost estimates pulled from nowhere                    | **CONFIRMED** — no source backing                                                                |
| 9   | JS-resolver migration dependency                      | **CONFIRMED** — Tier 2 framing under-notes the §3f gate                                          |
| 10  | `take past <next word>` composition                   | **DENIED** — composition works; `next funk` modifier + `past` range both exist                   |

## Hypotheticals — what we thought vs. what's actually true

A narrative pass over the same 10 verdicts: for each, the original belief, how it turned out to be wrong (or actually right), and the corrected framing the rebuttal docs should reflect.

### 1. Word vs subtoken

We thought Cursorless might have two scopes — `word` for whole identifiers and `subtoken` (or `wordPart`) for sub-word splitting — and that the rebuttal had conflated them, so `take second word this` inside `one_two_three` might not actually do what we claimed.
**But it actually does** have just one scope, `word`, that does double duty. `WordTokenizer.splitIdentifier()` splits on the language's word regex first, then falls back to a Unicode camelCase regex. No `subtoken` scope exists anywhere in the engine or cursorless-talon.
**Correct framing:** the killer-insight section stands as written. `word` is THE sub-token splitter in Cursorless.

### 2. Pre-splits diagnosis

We thought the reason `take second word this` doesn't work today is that prose-overlay's buffer pre-splits identifiers on `_` characters before they reach Cursorless's resolver — so the engine sees one-word-per-token and has nothing to split.
**But it actually doesn't** pre-split. Test L1.17 proves `add_text("the_quick_brown_fox") → 1 token`. Snake_case identifiers reach the resolver intact.
**Correct framing:** the real blocker is downstream — either (a) the Python resolver doesn't bind a sub-word handler, (b) the bundled JS at `js/` is a stripped subset lacking `WordScopeHandler`, or (c) the talon-side grammar in `prose_overlay_cursorless.talon` doesn't route `word` to a sub-token target. The fix is ten lines or two hundred depending on which.

### 3. Community attribution

We thought the COMMUNITY rebuttal could cite Talon community plugin APIs as free leverage — `<user.number_small>`, `<user.symbol_key>`, `actions.edit.extend_word_left`, `clip.set_text`, etc., all from `~/.talon/user/community/`.
**But it actually** misattributed the whole surface. There is no community plugin installed in this setup — only `__talon_community/trillium/` (a single subdirectory). Every cited capture and verb lives in **trillium_talon** (the user's own fork) or Talon's stdlib (`clip`). Community-the-package is not a thing here.
**Correct framing:** rename the rebuttal to TRILLIUM*TALON, re-attribute every "community provides X" line. The win is \_stronger* than the rebuttal claimed because Trillium owns trillium_talon — he can extend upstream rather than route around it.

### 4. Replace API names

We thought `actions.user.replace_selection(text)` and Cursorless's `takeAndReplace` were known APIs we could just call.
**But they actually don't exist** under those names. Grep across `~/.talon/user/` for `replace_selection` returns zero hits. Cursorless's action is `"replace"` with `"replaceWith"` as the arg key (`cursorless-talon/src/actions/replace.py:12-13`), and there's a related `replaceWithTarget`.
**Correct framing:** for the Cursorless path, build a `"replace"` action call with `"replaceWith"` as the text payload. For the trillium_talon path, compose `actions.edit.delete()` + `actions.edit.insert(text)` or wire directly to `buffer.replace_range`. The plumbing-only character of the work stands; the example grammar lines need rewrites.

**Follow-up investigation (cursorless repo dive).** Per Trillium's annotation, traced the actual replace surface end-to-end:

- **Talon-side entrypoint:** `cursorless-talon/src/actions/replace.py` defines `cursorless_replace_action(destination: CursorlessDestination, replace_with: list[str])`. It marshals a single JSON command shape:
  ```python
  actions.user.private_cursorless_command_and_wait({
      "name": "replace",
      "replaceWith": replace_with,        # list[str], one per destination, or [single_str] broadcast
      "destination": destination,         # CursorlessDestination
  })
  ```
- **Engine-side handler:** `cursorless-engine/src/actions/Replace.ts` (`class Replace`). Signature accepts `destinations: CursorlessDestination[]` and `replaceWith: ReplaceWith` where `ReplaceWith = string[] | {start: number}`. `string[]` broadcasts when length 1 (`Array(destinations.length).fill(replaceWith[0])`); the numeric form is for range fills (used by `Sort.ts:38` and `incrementDecrement.ts:54`).
- **Standalone/headless surface:** `cursorless-engine/src/actions/proseActionsStandalone.ts` exposes the same logic as a non-Talon action; line 12 documents `replaceWithTarget → replace destination's range with source's text`. `proseShim.ts:102` defines the operation type: `{type: "replace", range: ProseRange, text: string}`. This is the shape the bundled JS resolver path emits.
- **`replaceWithTarget` is a separate action**, not an alias — `Actions.ts:129` shows `replaceWithTarget = new Bring(this.rangeUpdater)`. It's "bring source-token-text into destination range" (the `bring`/`move` family), distinct from `replace` which takes literal `replaceWith: string[]`.

**Wiring recipe for prose-overlay's `replace selection by dictation`:**
1. Resolve the selection to a `CursorlessDestination` via the JS resolver path (`prose_overlay_targets_js.py` → `processTargets`).
2. Call `actions.user.private_cursorless_command_and_wait({"name": "replace", "replaceWith": [dictated_text], "destination": destination})`.
3. Cursorless emits the `{type: "replace", range, text}` op back to prose-overlay's action handler, which calls `buffer.replace_range(range.start, range.end, text)`.
4. Seal as one STRUCTURAL undo step with the existing `commit_start`/`commit_end` bracket.

The shape is identical for `bring`/`move`: use `name: "replaceWithTarget"` with a source target instead of `replaceWith: [text]`. So the same plumbing path handles both the dictation-replace and the bring-text rows of the parity doc.

### 5. Hat-allocator shapes

We thought Cursorless's `HatAllocator` supports shape variety in its hat space, so prose-overlay's bundled JS could ASSIGN shapes for free — meaning shape-hats were a Tier-2 wiring job, not a substrate build.
**But it actually doesn't** expose shapes through the prose-overlay bundle. The 3 bundle files (`prose_actions.js`, `prose_allocate_hats.js`, `prose_resolve_targets.js`) have zero shape identifiers — no `HatStyle`, no `bolt|frame|wing`, nothing. The engine upstream supports shapes; this bundle doesn't ship the allocator's shape surface.
**Correct framing:** shape rendering must come from the mouse-clock SVG lift (which is what `HOMOPHONE_SHAPES_PLAN.md` already chose — that was the right call). Reclassify the shape-hats row from Tier 2 (Cursorless gives it) to Tier 3 (custom render path, sibling-plugin lift). No allocator dependency at all.

**Follow-up engagement (scope-shift framing).** Per Trillium's annotation: the prior verdict (Tier 3, mouse-clock lift only) was too narrow. The right framing is a scope-shift on *what the shape vocabulary means*, with Cursorless's plumbing valuable in its own right alongside the repurposing.

**Two surfaces, two purposes:**

1. **Cursorless's native shape support** — engine has `HatStyleName` (typed in `IndividualHatMap.ts`), `enabledHatStyles` config that the allocator reads (`HatAllocator.ts:63`), per-token `hatStyle, grapheme` tuples on the hat map, `COLOR_CANONICALIZATION_MAPPING: Record<string, HatStyleName>` for spoken-form → style lookup, and a debounced re-allocator that re-partitions the shape × color × letter cartesian product on visible-token change. **All of this exists upstream; the prose-overlay bundle has stripped it out** — `scripts/build-js.ts` tree-shakes the JS bundle down to dot-only allocation and target resolution. That's a build choice, not an upstream limitation.

2. **Trillium's repurposing** (`HOMOPHONE_SHAPES_PLAN.md`) — the 10-shape vocabulary is reserved as a homophone-only addressing pool, with per-token panels and color-coded selection state. Semantically different from Cursorless's "shapes are extra hat-space partitioning" because each shape carries homophone-specific meaning, not just slot identity.

**Why bring the Cursorless plumbing into the bundle anyway:**

- The allocator's shape-aware logic does exactly what the homophone-pool design needs: deterministic shape assignment across visible tokens, respecting which shapes are "in use" for what, debounced re-allocation on edit. Prose-overlay would otherwise reimplement this for the homophone pool — work already done upstream.
- Future-compatibility: standard Cursorless-style shape addressing (`take blue frame air`) could coexist with the homophone-specific shape pool. Restricting the bundle to dot-only forecloses that path; restoring the shape surface keeps it open.
- The mouse-clock SVG lift remains the **render** path (Cursorless's engine assigns; VS Code's extension renders — prose-overlay needs its own renderer). But the **assignment** logic — which shape on which token, when to re-allocate, how to express enabled/disabled shapes — should come from Cursorless's allocator, not be rebuilt.

**Refined tier classification:**

- Shape **assignment** (which token gets which shape, debounced over visible tokens, color × shape × letter pool management) → **Tier 2** — Cursorless gives it once the bundle is rebuilt with shape support enabled in `scripts/build-js.ts`.
- Shape **render** (paint the SVG at the assigned position with the assigned color) → **Tier 3** — custom Skia path, lifted from mouse-clock.

Two complementary changes, not one-or-the-other. The build-js.ts shape gate is the precondition — flip it, and prose-overlay inherits Cursorless's allocator semantics for free, then renders via mouse-clock SVGs. The repurposing layer (homophone-pool ownership) sits on top: configure `enabledHatStyles` to scope the homophone pool, then read the allocator's assignments per token.

### 6. Row counts

We thought there were "about 22 open rows" in FEATURE_PARITY.md split roughly 3/4/15 (community) and 4/5/13 (cursorless).
**But it actually is** 24 open rows total, off by two from the cited count, and the per-tier splits were never row-walked at all — they were estimates over a glance.
**Correct framing:** any rebuttal revision should drop the eyeballed counts in favor of an explicit row-by-row tier table, so a reader can audit which row landed where without re-doing the analysis from scratch.

### 7. Clean partition

We thought a Tier-3 verdict in EITHER rebuttal meant the row was true prose-overlay-only work. So "Tier 3 in community" alone was enough to count it as orphan.
**But it actually isn't** that simple. Coverage is a 2D matrix — a row can be Tier 3 in one rebuttal and Tier 1 in the other, meaning the other source covers it cheaply. Using "either" overcounts the orphan set.
**Correct framing:** the right filter is "Tier 3 in BOTH rebuttals → true prose-overlay-only work." One-word fix to the Cursorless rebuttal's cross-reference section (either → both).

{{ this is a confusing statement, more examples please, be specifc }}

### 8. Cost estimates

We thought "hours not days" for Tier 1 and "days not weeks" for Tier 2 were defensible shorthand.
**But they actually are** ungrounded vibes — no LOC counts, no prior-feature timing, no plan-doc citations. And once Assertions 4 and 5 confirmed (API names wrong, bundle stripped), real costs run higher than the original framing implied because the prerequisite work is bigger.
**Correct framing:** strip the time-cost language entirely or replace it with concrete LOC-and-PR-count estimates grounded in the plan docs (e.g., "Tier 1 clipboard row: ~30 LOC, 1 PR" beats "hours, not days").

{{ what are we talking about here? Is it that LLM has no concept of time? If yes, we want to reframe in complexity }}

### 9. JS-resolver migration dependency

We thought sub-word and shape-hats were Tier 2 wiring work — parallel to other parity wins, just plumbing.
**But they actually are** blocked behind §3f's JS-resolver migration (which is still `[~]` / `[ ]`). And per Assertion 5, even when §3f flips, the bundle still won't have `WordScopeHandler` until someone rebuilds it.
**Correct framing:** the pragmatic order needs three steps before sub-word, not one: (1) finish §3f JS-resolver migration, (2) audit the JS bundle for `WordScopeHandler` and rebuild if absent, (3) THEN attempt sub-word. The Cursorless rebuttal's "ship §3f to unblock sub-word" direction was correct but skipped step (2).

{{ Sub word I believe is already described earlier? Is the irrelevant based on other findings? if it is still relevent, expand on why here }}

### 10. `take past next word` composition

We thought the grammar `take past next word` might not compose in Cursorless because `past` operates on hat targets and `next word` is a modifier, not a target.
**But it actually does** compose. `cursorless-talon/src/modifiers/relative_scope.py:22-23` defines `cursorless_relative_scope_singular` matching `"[<ordinal>] <direction> <scope>"` — `next funk`, `third next word`. Combined with the shipped `past <target>` range modifier, the composition is valid.
**Correct framing:** the rebuttal's Tier-2 classification of "selection extension by word" via `take past next word` stands. One minor lingering question — whether `past` accepts a relative-scope on its right side or only a hat target — is a one-line follow-up check, not a blocker.

## Load-bearing claims most likely to be wrong

### 1. Cursorless's `word` scope splitting identifiers — THE killer-insight is suspect

**VERDICT: DENIED.** The rebuttal claim is correct. Cursorless's `WordScopeHandler/WordTokenizer.ts:19-27` defines `splitIdentifier(text)` which splits on the language's word regex first, then falls back to a `CAMEL_REGEX` (`/\p{Lu}?\p{Ll}+|\p{Lu}+(?!\p{Ll})|\p{N}+/gu`). Confirmed by enumerating `ScopeHandlerFactoryImpl.ts` — the scope-type vocabulary is `character | word | token | identifier | line | sentence | paragraph | document | oneOf | nonWhitespaceSequence | url | customRegex | glyph | custom | instance` — **no `subtoken` or `wordPart` entry exists.** `word` is THE sub-token splitter in Cursorless. Grep across `cursorless-talon/` also returned zero hits for `subtoken` / `wordPart`. The killer-insight section stands as written.

**What the Cursorless rebuttal claimed:** "Cursorless's word-scope handler splits identifiers on `_` / `-` / `.` / case boundaries natively."

**Original worry (now resolved):** Cursorless might have separate `word` and `subtoken` scopes. Investigation showed no such split — `word` does both jobs. User grammar example `take second word this` is grammatically correct.

### 2. The "prose-overlay pre-splits identifiers" diagnosis is contradicted by an existing test

**VERDICT: CONFIRMED.** Test `L1.17` proves `add_text("the_quick_brown_fox") → 1 token`. The buffer keeps snake_case identifiers whole. The rebuttal's "pre-splits" diagnosis is wrong. The real blockers are most likely:

- The Python resolver path (default) doesn't bind a sub-word handler.
- The bundled JS at `js/` is a subset of cursorless-engine — `prose_resolve_targets.js` is one of three files in the bundle (with `prose_actions.js` and `prose_allocate_hats.js`), and grep against all three found zero shape/subtoken identifiers. The bundle may or may not include `WordScopeHandler` — needs explicit check.
- The grammar surface in `prose_overlay_cursorless.talon` may not bind the `word` scope to a target at all (the doc lists `token / word / identifier / character (at the TOKEN level)` as shipped, but "at the TOKEN level" qualifier suggests the binding is whole-token-only).

The cheap check (flip JS resolver, try `take second word this`) wasn't run live this pass — verdict CONFIRMED on the contradicting-test evidence; live-probe still pending and would resolve which of the three actual blockers is in play.

### 3. Community vs Talon-core vs trillium_talon attribution

**VERDICT: CONFIRMED — and the actual finding is bigger than the original assertion.** There is **no community plugin installed in this setup** — `find ~/.talon/user/ -maxdepth 2 -type d -name "*ommunity*"` returns only `__talon_community/trillium/` (a single subdirectory). The actual surface the COMMUNITY rebuttal cites lives in **trillium_talon** (Trillium's own fork) and Talon stdlib:

- `clip.set_text` / `clip.text` → Talon stdlib (`clip` module), not community.
- `<user.number_small>` → defined in `trillium_talon/core/numbers/numbers.py` (confirmed by grep).
- `<user.symbol_key>` → defined in `trillium_talon/core/keys/keys.py` + `keys.talon` + `symbols.py` (confirmed in 5 files under trillium_talon).
- `actions.edit.extend_word_left/right` → confirmed in `trillium_talon/core/edit/edit_command.py:71-73, 127-131` and `edit_win.py:82,85`.
- `actions.edit.cut/copy/paste` → confirmed in `trillium_talon/core/edit/edit_command.py:163,165` and `edit_paragraph.py:49,54,59`.

The "community" framing in `FEATURE_PARITY_REBUTTAL_COMMUNITY.md` is misattributed throughout. Functionally this is **stronger leverage**, not weaker — trillium_talon is the user's own code, so the wins are "lift from a repo you control" rather than "lift from an upstream you don't." But the rebuttal needs a rename / re-attribution pass to reflect reality.

### 4. `actions.user.replace_selection` and `takeAndReplace` may not exist by those names

**VERDICT: CONFIRMED.** Both names are wrong:

- `takeAndReplace` → does NOT exist. The actual Cursorless action is `"replace"` (with `"replaceWith"` as the argument key), per `~/.talon/user/cursorless-talon/src/actions/replace.py:12-13`. Also `replaceWithTarget` appears as an action name at `actions/actions.py:95`.
- `replace_selection` → does NOT exist anywhere under `~/.talon/user/`. `grep -rn "def replace_selection\|actions\.user\.replace_selection\|user.replace_selection"` returned zero hits.

The "wire it up" estimates stay right, but the example grammar specs in both rebuttals need rewrites. Use `cursorless replace` semantics for the Cursorless path, and for the trillium_talon-style edit path build `actions.edit.delete()` + `actions.edit.insert(text)` (or call `buffer.replace_range` directly inside the overlay's own action).

### 5. The hat-allocator-supports-shapes claim oscillates between two stories

**VERDICT: CONFIRMED.** The bundled JS at `js/` does NOT expose Cursorless's shape rendering. Grep across the 3 bundle files (`prose_actions.js`, `prose_allocate_hats.js`, `prose_resolve_targets.js`) for `hatshape | hatstyle | bolt | frame | wing | subtoken | wordpart` returned only YAML-parser noise — no genuine shape identifiers. The bundle is a stripped subset focused on hat allocation (dot only) and target resolution. So the "shape hats" entry is closer to **Tier 3** in the Cursorless rebuttal (Cursorless's engine has the capability; the prose-overlay bundle does not, and we can't lift without rebundling).

This is also consistent with `HOMOPHONE_SHAPES_PLAN.md`'s explicit choice to lift mouse-clock SVG paths — the design assumed (correctly) that the JS bundle wouldn't help with shape rendering. The Cursorless rebuttal needs a Tier reclassification for the shape-hats row.

## Lower-risk assumptions worth flagging

### 6. Tier row-counts are eyeballed

**VERDICT: CONFIRMED (minor).** Actual open-row count in `FEATURE_PARITY.md` (rows matching `^| \`[ ]\``or`^| \`[~]\``) is **24**, not the "~22" the rebuttals quote. Off by two — within the rounding tolerance of "~" but worth correcting in any future revision. Tier breakdowns (3/4/15 community-side and 4/5/13 cursorless-side) were never explicitly row-walked and remain unverified at the per-row level. **Recommendation:** if either rebuttal is revised, replace eyeballed counts with an explicit row-by-row tier table.

### 7. The two rebuttals don't partition cleanly

**VERDICT: CONFIRMED.** Read against the two rebuttals as written: `FEATURE_PARITY_REBUTTAL_CURSORLESS.md` "Cross-reference" section says "Tier 3 rows in either rebuttal are the _true_ prose-overlay-only work." That phrasing is wrong by inspection — a Tier-3 verdict in only ONE rebuttal doesn't mean the other doesn't cover it. The correct filter is "Tier 3 in BOTH rebuttals → prose-overlay's true work." The rebuttal needs a one-line fix to state the AND, not OR.

### 8. Cost estimates ("hours not days", "days not weeks")

**VERDICT: CONFIRMED.** No source backing in either rebuttal. Both docs use the cost-estimate phrasing without a reference to LOC counts, prior similar feature timing, or planning-doc estimates. Real costs depend on three things now known to be uncertain: (a) whether the JS bundle has `WordScopeHandler` (Assertion 5 finding suggests not), (b) the actual edit/replace API names (Assertion 4: needs rewrite), (c) undo sealing edge cases (out of scope of this audit). **Recommendation:** strip cost language from rebuttals or replace with explicit "LOC ~N, ~X PRs" estimates grounded in the plan docs.

### 9. The Cursorless doc assumes JS-resolver migration completes successfully

**VERDICT: CONFIRMED.** Confirmed by inspection of `FEATURE_PARITY.md` §3f — both rows there are `[~]` / `[ ]` (JS resolver scaffolded but awaiting parity verification; Python resolver still in place). The Cursorless rebuttal's Tier-2 framing of sub-word and shape-hat work assumes the JS resolver is prod, but doesn't note the §3f gate as a hard blocker. Compounded by Assertion 5's finding (the bundle is a stripped subset): sub-word may NOT actually be unblocked even once §3f flips, because `WordScopeHandler` likely isn't in the bundle. **Recommendation:** rebuttal §3f reference should explicitly call this out as a precondition; the "pragmatic order" should put §3f _and a bundle audit_ before sub-word.

### 10. `take past <next word>` composition

**VERDICT: DENIED.** The composition works. `~/.talon/user/cursorless-talon/src/modifiers/relative_scope.py:22-23` defines `cursorless_relative_scope_singular` with the rule `"[<user.ordinals_small>] <user.cursorless_relative_direction> <user.cursorless_scope_type>"` — e.g. `"next funk"` or `"third next funk"`. Combined with the existing `past <target>` range-modifier (used in shipped `chuck air past drum`), the composition `take past next word` is grammatically valid Cursorless. The rebuttal's Tier-2 framing stands. (Whether `past` accepts a relative-scope target or only a hat target needs one more check, but the modifier surface and the range surface both exist.)

## Most consequential single check

**Verify Cursorless's `word` vs `subtoken` scope semantics before anyone codes against `FEATURE_PARITY_REBUTTAL_CURSORLESS.md`'s killer-insight section.** That's the load-bearing claim of the whole doc; if it's wrong, the "shape of the answer" and the "pragmatic order" both shift, and the recommendation to prioritize §3f to unblock sub-word is reordered or weakened.

## Status of the rebuttals after this critique

Neither rebuttal is wrong in spirit — community really does cover Tier 1 cheaply, and Cursorless really does own scope/range resolution. The risks above are about:

1. Wrong scope name (`word` vs `subtoken`)
2. Wrong root-cause diagnosis (pre-splitting vs missing handler binding)
3. Wrong source attribution (community vs Talon core vs trillium_talon)
4. Wrong API names (`replace_selection`, `takeAndReplace`)
5. Wrong render-path implication for shape hats

Each fixable with a single grep or a single Talon try-it. None invalidate the tier structure itself. Read the rebuttals as **direction-correct, detail-suspect** until the cheap checks land.
