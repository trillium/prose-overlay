# Greedy hat allocation + cursor-nearest default-hat bias — scope

## §0. Executive summary

The user wants near-cursor tokens to preferentially wear the **default (gray) hat** so `<hat>` alone works — not `<color> <hat>`. Investigation finding: cursorless already ranks tokens by cursor proximity in `getRankedTokens.ts:43-59` (upstream) and the shim already passes `cursor_pos` through to the bundle at `hats_js.py:165`. In the common case — near-cursor token has a unique letter — the near-cursor token DOES currently get gray, because it's ranked first and gray has penalty=0 (`proseStandalone.ts:155`) so wins `chooseTokenHat` step 4 `negativePenalty` (`chooseTokenHat.ts:72`).

**The real gap is COLLISION handling.** When two tokens share a grapheme, the near-cursor one gets gray-of-that-letter, but if the near-cursor token has multiple grapheme options, cursorless may hand it a colored hat on a "better" grapheme instead of a gray hat on a "worse" grapheme (there's no penalty term for `graphemeIsAlsoWantedByFarToken`). The fix is a small metric injection into `chooseTokenHat`.

**Effort:** one cursorless commit (~40 LOC in `HatMetrics.ts` + wire in `chooseTokenHat.ts`), one prose-overlay commit (bundle rebuild + L2 tests). No new arg surface — `cursorGap` is already plumbed. Cross-repo but small on each side.

## §1. Current-state — what ranking does today

**Ranking (cursorless-engine).**
- `getRankedTokens.ts:43-59` sorts tokens by `getTokenComparator` around the active editor's cursor. Line-distance dominates; character-distance tie-breaks. Result: ranks are `{0, -1, -2, ...}` — nearest-to-cursor is rank 0 (best).
- The pre-tokenized fast path (`getRankedTokens.ts:70-106`) does the same sort using `activeTextEditor.selections[0].active`.
- `getTokenComparator.ts:29-37` uses `Math.abs(token.range.start.character - selectionCharacterIndex)` — token-start-character distance. NOT character-distance to the token body, NOT gap-index distance.

**Per-token hat pick (`chooseTokenHat.ts:59-77`), max-by-first-differing on these metrics:**
1. `penaltyEquivalenceClass(hatStability)` — bucket by penalty (greedy = raw negative penalty, balanced = `penalty<2 ? 0 : -1`, stable = flat).
2. `isOldTokenHat(oldTokenHat)` — keep old hat if still in the running.
3. `hatOldTokenRank(hatOldTokenRanks)` — prefer free hats; otherwise steal from lowest-ranked token.
4. `negativePenalty` — lowest raw penalty wins (`HatMetrics.ts:31`).
5. `minimumTokenRankContainingGrapheme(tokenRank, graphemeTokenRanks)` — prefer hats on graphemes that DON'T appear in any lower-ranked (= farther-from-cursor) token that hasn't picked yet (`HatMetrics.ts:65-76`). This IS a form of near-cursor bias — but it selects **grapheme**, not **color**.

**Prose bundle already accepts cursor.** `proseStandalone.ts:326-356` — `proseAllocateHats(tokensJson, oldAssignmentsJson, stability, cursorGapJson, enabledStylesJson)`. Line 351: `const effectiveCursor = cursorGap >= 0 ? cursorGap : tokens.length;` synthesizes a fake editor with `selections[0].active` at `Position(0, effectiveCursor)`. Line 356 hands it to `getRankedTokens`. **No arg surface widening required.**

**Shim already passes cursor.** `hats_js.py:165` — `json.dumps(cursor_pos if cursor_pos is not None else -1)`. `actions_core.py:57` reads `instance.cursor` (gap index) and defaults to `len(tokens)` (end of buffer) when None. Every mutation path that shifts the cursor already triggers `_recompute_hats`.

**Conclusion.** The near-cursor bias exists at rank-level and at grapheme-level (metric 5), but NOT at color/style-level. The user's ask is a new metric — "prefer default (gray) style when near cursor, even if it means a marginally worse grapheme."

## §2. Semantic clarification — what "cursor-greedy" means concretely

**Scenario A (already works).** Buffer `the air ball drum echo`, cursor gap 3 (between `ball` and `drum`). No color-hat conflicts because every token has a unique letter available. `air` at token 1 gets `gray-a`, `ball` gets `gray-b`, `drum` gets `gray-d`, `echo` gets `gray-e`. No change.

**Scenario B (the ask).** Buffer `air angel apple axe`, cursor gap 1 (right after `air`). All four tokens want an `a` (also `i`, `n`, `g`, `e`, `l`, `p`, `x`). `air` (rank 0) grabs `gray-a`. `angel` (rank ~ -1) — cursorless step 3 (`hatOldTokenRank`) tries a free hat first: `n`, `g`, `e`, `l` are all free with `gray`. Step 4 (`negativePenalty`) picks the lowest-penalty free hat. `apple` and `axe` — `p`, `x`, `l` etc still free with `gray`. **User does not currently need color prefix here.**

**Scenario C (where it likely bites).** Buffer `axe ax bx cx`, cursor gap 1 (after `axe`). Every token has an `x` and an `a`/`b`/`c`. `axe` (rank 0) — candidates include `(a, gray, 0)`, `(x, gray, 0)`, `(e, gray, 0)`. Step 4 ties on penalty. Step 5 `minimumTokenRankContainingGrapheme` breaks the tie: for `a`, only lower-ranked tokens with `a` are `ax` — its minimum rank is `-1`. For `x`, all three lower-ranked have `x` — min rank `-3`. For `e`, no lower-ranked has `e` — `Infinity`. Metric returns higher = better, so `e` wins → `axe` gets `gray-e`. Fine. `ax` (rank -1) — `a` free with gray, `x` free with gray. Step 4 ties, step 5: `a` has no lower rank with `a`, `x` still appears in `bx`, `cx`. `a` wins → `ax` gets `gray-a`. So far so good.

**Scenario D (real bite — colored hat on near-cursor token).** Buffer `apple bat apricot`, cursor gap 0 (before `apple`). All three want `a`. `apple` (rank 0) is nearest — gets `gray-a`. `apricot` (rank -1 or -2 depending on `bat` position) is next-nearest with an `a`. `a` is taken — step 3 forces steal-vs-free: `apricot` has `p`, `r`, `i`, `c`, `o`, `t` free with gray. Step 4 picks lowest penalty = gray. So `apricot` gets `gray-p` or similar. `bat` (rank -1) — `b`, `t` still free. **No color hat needed.**

**Real bite scenario (rare — needs verification against live buffer).** Where DOES a colored hat land on the near-cursor token today? Answer: when the near-cursor token's letters are ALL popular AND the buffer has many tokens sharing every grapheme. Example: buffer of 30 tokens where the nearest-cursor token is `on` and 20 farther-cursor tokens contain `o` or `n`. `on` gets rank 0 → picks `gray-o` (step 5 says both `o` and `n` are contested, roughly equal). Then a farther token like `won` at rank -5 — `w` free, gets `gray-w`. **Still fine.**

**The user is likely reporting an OBSERVED case**, not a theoretical one. **OQ0 (new):** capture a repro from the user before implementing. Add L2.17b probe that reproduces the exact case from the user's session before shipping any allocator change.

**Definition of "closest" (proposed).** Character-distance from cursor gap to the token's start character on the same line. Matches `getTokenComparator.ts:29-37` exactly. Prose-overlay's `cursorGap` maps 1:1 onto `Position.character` inside the synthesized fake editor (`proseStandalone.ts:353`). **OQ1: keep character-distance (yes) or switch to token-index distance? Recommend character-distance for consistency with upstream.**

**Tie-break for equidistant tokens.** Current: comparator returns 0 → JS `Array.sort` is stable, insertion order wins. Insertion order in the bundle is `tokens[i]` iteration order → left-to-right. **OQ2: keep left-to-right as tie-break? Recommend yes; it's the current implicit behavior.**

**Does the policy affect color ordering?** Current gray/blue/green/red penalties (0/1/1/1) already produce color ordering. The ask is only about **default-vs-colored** (gray-vs-anything-else). **OQ3: recommend default-vs-colored only for v1. Color ordering stays cursorless-native.**

## §3. Bundle changes (cursorless-engine)

**Surface:** `chooseTokenHat.ts` gets a new metric between step 4 and step 5. `HatMetrics.ts` gets a new exported metric factory.

**Why `HatMetrics.ts` not `getRankedTokens.ts`.** Reordering `getRankedTokens.ts` would flip ranking of tokens (breaks the many downstream consumers using rank for other purposes: hat stealing, grapheme contention). We want near-cursor tokens to still be RANK-0, but to bias their **hat choice** toward the default style. That's a metric on the candidate, not a re-rank of the token.

**New metric (proposed).** In `HatMetrics.ts`:

```ts
/**
 * @param defaultStyleName Name of the "default" style (penalty 0), e.g. "gray" for prose or "default" for cursorless proper.
 * @param tokenRank Rank of the current token. Near-cursor tokens have rank ~= 0; far tokens have very negative ranks.
 * @param cursorGreedyThreshold How aggressive the bias is. Rank > threshold = near-cursor. Recommend -3 (top 4 tokens).
 * @returns 1 if this candidate is the default style AND the token is near-cursor; 0 otherwise. Higher = better.
 */
export function nearCursorDefaultStyleBonus(
  defaultStyleName: string,
  tokenRank: number,
  cursorGreedyThreshold: number,
): HatMetric { ... }
```

**Wire-in in `chooseTokenHat.ts:59-77`.** Insert between step 4 (`negativePenalty`) and step 5 (`minimumTokenRankContainingGrapheme`):

```ts
// 4.5 If near cursor, prefer the default style even at the cost of a marginally worse grapheme
nearCursorDefaultStyleBonus(defaultStyleName, tokenRank, threshold),
```

**Config plumbing.** `chooseTokenHat` needs `defaultStyleName` and `cursorGreedyThreshold`. Cheapest: thread through as new parameters from `allocateHats.ts:105` and from `proseStandalone.ts:405`. `allocateHats` gets `hatStability` today; can accept a new optional `cursorGreedyConfig?: { defaultStyleName: string; threshold: number }` — `undefined` = current behavior (no bias). Backward-compat preserved.

**Estimated cursorless-source diff:** ~40 LOC. New metric ~15 LOC, wire-in ~5 LOC, `allocateHats` plumbing ~10 LOC, `proseStandalone` plumbing ~10 LOC.

## §4. Prose-overlay side changes

**`shim/hats_js.py`.** Pass a new arg `cursor_greedy: bool = True` through `_fn(...)` call at line 161. Serialize as 6th JSON arg. Bundle default when arg missing = True (matches the user's ask as documented behavior). No new fields in the tuple return.

**`shim/actions_core.py` `_recompute_hats`.** No new logic — cursor is already read.

**Grammar (`.talon`).** Nothing changes. `<hat>` and `<color> <hat>` grammars are unaffected.

**Optional voice toggle.** Add `user.prose_overlay_hat_cursor_greedy` Talon module setting (bool, default True). Expose commands:
- `overlay hat greedy on` → `actions.user.prose_overlay_hat_cursor_greedy_set(True)`
- `overlay hat greedy off` → `actions.user.prose_overlay_hat_cursor_greedy_set(False)`
- Use `ctx.settings["user.prose_overlay_hat_cursor_greedy"] = value` (canonical live-setter per MEMORY.md).

**Threshold surface (OQ5-a).** Recommend hardcode `threshold = -3` in the bundle (top 4 tokens get the bias). If the user wants tunable, add a second setting later. Don't ship two knobs on v1.

## §5. Test plan (L2 layer)

**L2.15 — bundle grep for new symbol.** Grep the built `js/prose_allocate_hats.js` for the string `nearCursorDefaultStyleBonus` (or the mangled equivalent — use unique substring `DefaultStyle` since esbuild preserves object literal keys). Guards against silent tree-shaking.

**L2.16 — bun probe: bias fires on near-cursor.**
- Input: tokens `["axe", "ax", "bx", "cx"]`, cursorGap 0, empty old assignments.
- Assert: token 0 (`axe`) result has `styleName === "gray"`.
- Assert: token 3 (`cx`) result has `styleName === "gray"` too (has free letter `c`).
- Assert: no non-gray style appears on token 0.

**L2.17 — bun probe: reverse cursor.**
- Same tokens, cursorGap 12 (past `cx`).
- Assert: token 3 (`cx`, now rank 0) has `styleName === "gray"`.

**L2.17b — repro probe (once user provides a real case).** Pin a real buffer + cursor pos that CURRENTLY yields a colored hat on the near-cursor token; assert that with the bias enabled, it flips to gray.

**L2.18 — regression: bias-off matches current behavior.**
- Same input as L2.16 but with `cursor_greedy=False`.
- Assert: result matches current bundle output byte-for-byte (snapshot).

**L2.19 — stability preserved.**
- First call with `axe ax bx cx` → get result R1.
- Second call with `axe ax bx cx dx` (appended token) → get result R2.
- Assert: R2 assignments for tokens 0-3 match R1 (stability metric 2 `isOldTokenHat` still wins for existing hats). Bias must not thrash on next call.

## §6. Risk register

**R1 — Semantic surprise (default off vs on).** Users with muscle memory for existing hat allocations will see hats shift on next reload. Mitigation: gate behind `prose_overlay_hat_cursor_greedy` setting. Default recommendation: **True** (matches the ask), CHANGELOG entry + one-liner in `PYTHON_REPORT.md`. If user pushes back on default-True, flip.

**R2 — Cursor invalidation / stale allocation.** `_recompute_hats` fires on every buffer mutation. Cursor moves via `pre <hat>` / `post <hat>` (`shim/actions_target.py`) already trigger recompute per existing tests. Verified path — no new risk.

**R3 — Stacks with Slice 2 `styleName` migration.** The Slice 2 shape-suffix work (see `docs/BUNDLE_SHAPE_SCOPE.md`) means `styleName` may be `"gray-frame"` not `"gray"`. New metric must match on the color prefix, not the full styleName. Concretely: `nearCursorDefaultStyleBonus` compares `style.split("-")[0] === defaultStyleName`, not `style === defaultStyleName`. Otherwise the bias silently disables itself as soon as any shape lands on a near-cursor token.

**R4 — Metric 5 (`minimumTokenRankContainingGrapheme`) fights the new metric.** If both are active at the same tier, step 4.5's default-style win could push us to a grapheme that a farther token also wants — then step 5 becomes unable to change that choice (metric max-by-first-differing eliminates the loser at step 4.5). This is DESIRED behavior (gray-on-worse-grapheme > colored-on-better-grapheme), but note it explicitly so a future maintainer doesn't "fix" the interaction.

**R5 — Downstream cursorless proper regresses.** If we thread `cursorGreedyConfig` through `allocateHats.ts`, cursorless proper's own `allocateHats` caller (`packages/cursorless-engine/src/core/hatAllocator.ts` — verify path) must pass `undefined` to preserve current behavior. Add a unit test on that call site.

## §7. Open questions

- **OQ0 (blocker):** capture a concrete repro from the user (buffer text + cursor gap + assignment that they don't like). Every scenario I traced by hand DOES currently produce `gray` on the near-cursor token. The user is likely seeing something specific — implement against a fixed repro, not against my speculation.
- **OQ1:** character-distance (recommend, matches upstream) vs token-index distance vs gap-index distance?
- **OQ2:** equidistant tie-break — recommend left-to-right (implicit current behavior).
- **OQ3:** does the policy affect color ordering, or only default-vs-colored? **Recommend default-vs-colored only for v1.**
- **OQ4:** does the policy apply to shape allocation (Slice 2's `shape_bridge.py`)? **Recommend no** — shapes are only for flagged-homophone tokens, which are a separate concern. Letter+color bias only for v1.
- **OQ5:** runtime toggle name + default? **Recommend `user.prose_overlay_hat_cursor_greedy`, default True.**
- **OQ5-a:** threshold surface — hardcode top-4 (rank > -3), or add a second setting? **Recommend hardcode for v1.**
- **OQ6:** upstream cursorless — do we PR this to cursorless proper as well, or keep it prose-only? Prose-only means the metric factory lives in cursorless source but only `proseStandalone.ts` wires it in. Cleaner: land in cursorless with `cursorGreedyConfig` opt-in, prose uses it, cursorless proper doesn't (yet). Ask the cursorless maintainers before landing.

## §8. Recommended implementation order

**Phase 0 (blocking):** collect real repro from user. Write L2.17b snapshot test first. Confirms the change actually fixes what the user is complaining about.

**Phase 1:** cursorless-engine — add `nearCursorDefaultStyleBonus` to `HatMetrics.ts`, wire in `chooseTokenHat.ts` between step 4 and step 5, thread `cursorGreedyConfig` through `allocateHats.ts` and `proseStandalone.ts`. Rebuild bundle. One cursorless commit.

**Phase 2:** prose-overlay — pass `cursor_greedy` bool through `hats_js.py:_fn(...)`. Ship the bundle rebuild. Add L2.15/16/17/17b/18/19 tests. One prose-overlay commit.

**Phase 3 (optional):** voice toggle + setting + docs entry in CHANGELOG. Second prose-overlay commit.

**Total:** 2 commits (cursorless + prose-overlay), maybe 3 with the toggle. Roughly 100 LOC production + 60 LOC test.
