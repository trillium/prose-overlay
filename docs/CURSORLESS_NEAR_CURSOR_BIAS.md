# Cursorless Near-Cursor Bias: Current Implementation vs. Upstream

## §1: Current bundled behavior

The prose-overlay bundle (`js/prose_allocate_hats.js`, lines 12777–12825) implements a simplified version of the Cursorless hat allocator. The `proseAllocateHats` function accepts five arguments:

```typescript
function proseAllocateHats(
  tokensJson: string,
  oldAssignmentsJson: string,
  stability: string,          // "greedy" | "balanced" | "stable"
  cursorGapJson: string = "-1", // gap index for cursor position
  enabledStylesJson?: string,
)
```

The bundle:
1. Parses tokens and converts them to Token objects (lines 12779–12787)
2. Ranks tokens via `getRankedTokens()` using cursor proximity from `cursorGap` (line 12788)
3. Processes ranked tokens in descending-rank order (line 12807) via `chooseTokenHat()` (line 12815)
4. **Never dislodges a default-hat allocation from a farther token for a nearer-cursor token**

The stability enforcement happens in `HatMetrics.ts` (lines 99–108): `penaltyEquivalenceClass()` returns different equivalence classes based on the `hatStability` enum:
- `greedy`: only identical penalties (`penalty => -penalty`)
- `balanced`: penalty < 2 → 0, else 1
- `stable`: all → 0 (no differentiation)

In `chooseTokenHat.ts` (line 59–77), the selection order is:
1. Apply penalty equivalence class (line 62)
2. **Prefer existing hat** (`isOldTokenHat`, line 65)
3. Steal from lowest-ranked token only if no free hats
4. Minimize additional penalties

**The issue**: Even with `stability="greedy"`, step 2 (`isOldTokenHat`) returns 1 (prefer) vs. 0 (don't prefer) *before* considering rank distance. The old hat wins purely on the equivalence-class and existing-hat preference, regardless of whether a higher-ranked (closer-to-cursor) token needs the hat.

## §2: Upstream capability

Cursorless upstream (`~/code/cursorless/packages/cursorless-engine/src/util/allocateHats/`) **already has the exact behavior the user desires**. The mechanism is the **ranking system** in `getRankedTokens.ts` (lines 22–106), not a separate metric.

Key upstream code:

**`getRankedTokens.ts:68–72` (preTokenizedInput fast path):**
```typescript
// Fast path for callers that already have tokens in hand. Skips the editor
// visibleRanges walk and the language tokenizer entirely; ranks the supplied
// tokens by closeness to the active editor's cursor (or origin if absent).
function rankPreTokenizedInput(
  preTokenizedInput: readonly Token[],
  activeTextEditor: TextEditor | undefined,
): RankedToken[]
```

**`getTokenComparator.ts`** (sorting rule—not shown but evident from test at `getRankedTokens.test.ts:153–159`) ranks tokens by distance to cursor: closer tokens get **higher rank** (less negative).

**`allocateHats.ts:90–129` (main loop):**
```typescript
return rankedTokens
  .map<TokenHat | undefined>(({ token, rank: tokenRank }) => {
    const chosenHat = chooseTokenHat(
      context,
      hatStability,
      tokenRank,           // <-- rank passed to every decision
      tokenOldHatMap.get(token),
      tokenRemainingHatCandidates,
    );
```

**`HatMetrics.ts:40–53` (`hatOldTokenRank` function):**
```typescript
export function hatOldTokenRank(
  hatOldTokenRanks: CompositeKeyMap<...>,
): HatMetric {
  return ({ grapheme: { text: grapheme }, style }) => {
    const hatOldTokenRank = hatOldTokenRanks.get({
      grapheme,
      hatStyle: style,
    });
    return hatOldTokenRank == null ? Infinity : -hatOldTokenRank;
  };
}
```

When a higher-ranked token steals a hat that was assigned to a lower-ranked token in the previous allocation, **the logic checks if the hat is "free" (Infinity) vs. "stolen" (-lowerRank)**. For colored hats (penalty > 0), `hatOldTokenRank` returns `-lowerRank` (worse than Infinity, so the hat CAN be stolen). But the **preference for the old hat** (`isOldTokenHat`, line 65 in `chooseTokenHat.ts`) still competes via the metric cascade.

**The upstream trick is that with `stability="greedy"`, the equivalence class (step 1) is `x => -x` (every distinct penalty is a distinct class), so the penalty-based tie-breaking (steps 4–5) can distinguish hats stolen from nearer vs. farther tokens**. However, this still requires the token to first get into the candidate pool, which depends on both tokens being ranked.

**Reality check:** Upstream cursorless works because tokens are **already ranked at allocation time**. The user's repro shows `this` at index 6 kept gray (penalty 0) while the newly-appended `hey` at index 11 was assigned blue (penalty 1). With cursor at gap 12 (past index 11), `hey` should rank higher than `this`, but cursorless upstream's ranker WILL place `hey` first because:
- Cursor at gap 12 = character position 12
- `hey` token at offset 11 (distance = 1)
- `this` token at offset 6 (distance = 6)

So `hey` ranks higher and processes first in the allocation loop. When it encounters candidates including gray (its default hat), the old gray assignment from `this` is already recorded, and `hatOldTokenRank` returns `-6` (rank of `this`), meaning gray is **available to steal from a farther token**.

**The upstream implementation does NOT have a separate `nearCursorDefaultStyleBonus` metric in HatMetrics.ts.** The behavior emerges from:
1. Higher rank → processes first → gets first pick of hats
2. `hatOldTokenRank` metric returns Infinity for free hats, `-oldRank` for stolen
3. With greedy equivalence class, penalty tiebreakers can prefer low-penalty stolen hats over higher-penalty free hats

## §3: The gap

**Prose-overlay's bundled version IS functionally identical to upstream** (both files are in `proseStandalone.ts`), so the gap is NOT in the algorithm logic. The issue is in how **prose-overlay's shim** (`shim/hats_js.py`) calls the allocator.

**The shim's bug (line 56–59):**
```python
def compute_hat_assignments(
    tokens: list[str],
    old_assignments: dict[int, tuple[int, str, str]] | None = None,
    stability: str = "balanced",  # <-- DEFAULT IS "balanced", NOT "greedy"
    cursor_pos: int | None = None,
```

The default is `stability="balanced"`, which corresponds to `HatStability.balanced` (penalty < 2 → 0, else 1; see `HatMetrics.ts:103–104`). This equivalence class collapses gray (penalty 0) and blue (penalty 1) into the same equivalence class `0`, so the tiebreaker at step 4 (`negativePenalty`) cannot distinguish them by penalty alone. The allocation then falls back to later metrics (`minimumTokenRankContainingGrapheme`), which do not prioritize stealing from farther tokens.

**With `stability="greedy"**, the equivalence class is `x => -x`, so gray (0) and blue (1) are in different classes: step 2 (`isOldTokenHat`) tries to keep the old hat, but step 1 (`penaltyEquivalenceClass`) already filtered out blue if gray is in the candidate pool, allowing gray to be stolen from `this` (index 6) and reassigned to `hey` (index 11).

**The fix is one-line shim change**: change the default from `"balanced"` to `"greedy"`.

## §4: Fix plan

### Cursorless-side changes
**NONE.** The upstream allocator already does what the user wants. No changes to `HatMetrics.ts`, no new metric, no bundler changes.

### Prose-overlay-side changes
**File: `shim/hats_js.py`, line 59**

Change:
```python
stability: str = "balanced",
```

To:
```python
stability: str = "greedy",
```

**Estimated LOC:** 1 line in prose-overlay.

### Estimated total LOC
**1 line** across both repos.

## §5: Verify plan

Use `bun run` to run the exact repro from the debug JSONL:

```javascript
// repro.js
import("./js/prose_allocate_hats.js").then(() => {
  const tokens = JSON.stringify([
    "testing", "testing", "testing", "discord", "questions",
    "in", "this", "discord", "server", "hay", "hey", "hey"
  ]);
  const oldAssignments = JSON.stringify([
    { tokenIdx: 6, charIdx: 0, letter: "t", color: "gray", styleName: "gray" }
  ]);
  
  // Before fix: stability="balanced" (default)
  const beforeBalanced = globalThis.proseAllocateHats(
    tokens, oldAssignments, "balanced", JSON.stringify(12), null
  );
  console.log("balanced:", beforeBalanced);
  
  // After fix: stability="greedy"
  const afterGreedy = globalThis.proseAllocateHats(
    tokens, oldAssignments, "greedy", JSON.stringify(12), null
  );
  console.log("greedy:", afterGreedy);
});
```

**Expected output after fix:**
- `balanced`: `this` (index 6) keeps gray; `hey` (index 11) gets a colored hat (blue, green, etc.)
- `greedy`: `hey` (index 11) gets gray (stolen from `this`); `this` (index 6) gets a colored hat

The tuple result format is `{ "11": { charIdx: X, letter: "h", color: "gray", styleName: "gray" }, "6": { charIdx: Y, letter: "t", color: "blue", styleName: "blue" }, ... }`.

