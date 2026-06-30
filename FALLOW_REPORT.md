# Fallow Report — prose-overlay

> Generated 2026-06-29 by `bunx fallow --format markdown` from repo root.
> Regenerate with: `bunx fallow --format markdown > FALLOW_REPORT.md`

## Scope note

Fallow only analyzes TypeScript / JavaScript. The prose-overlay codebase is
**mostly Python (`.py` + `.talon`)**, none of which is in this report — for
Python-side health, use a Python-aware tool (e.g. radon, ruff, mypy).

The 6 files fallow saw:
- `js/prose_allocate_hats.js`, `js/prose_resolve_targets.js` — **vendored**
  esbuild bundles of cursorless-engine. Not our code; fix is upstream.
- `js/prose_actions.js` — appears unused (verify; if dead, delete).
- `scripts/build-js.ts`, `scripts/sync-to-talon.ts`,
  `scripts/gen-command-table.ts` — CLI entry points run via `bun`; flagged
  "unused file" only because nothing imports them.

## TL;DR (our code only — 8 of 510 complexity findings)

| File:Line | Function | Severity | Cyclomatic | Cognitive | Lines |
|:----------|:---------|:---------|-----------:|----------:|------:|
| `scripts/sync-to-talon.ts:43` | `isExcluded` | high | 9 | 1 | 13 |
| `scripts/build-js.ts:101` | `main` | moderate | 5 | 4 | 21 |
| `scripts/sync-to-talon.ts:90` | `<arrow>` | moderate | 5 | 4 | 6 |
| `scripts/sync-to-talon.ts:99` | `<arrow>` | moderate | 5 | 4 | 6 |

Hotspot (last 6 months): `scripts/sync-to-talon.ts` — 3 commits, 112 line
churn, *accelerating* trend. Worth a once-over.

Everything else in the report below is vendored cursorless code.

---

## Fallow: 6 issues found

### Unused files (6)

- `js/prose_actions.js`
- `js/prose_allocate_hats.js`
- `js/prose_resolve_targets.js`
- `scripts/build-js.ts`
- `scripts/gen-command-table.ts`
- `scripts/sync-to-talon.ts`


note: module wiring excluded from clone detection (--no-ignore-imports to include it)
## Fallow: 1 clone group found (9.4% duplication)

### Duplicates

**Clone group 1** (1541 lines, 2 instances)

- `js/prose_allocate_hats.js:1-1541`
- `js/prose_resolve_targets.js:1-1541`

### Clone Families

**Family 1** (1 group, 1541 lines across `js/prose_allocate_hats.js`, `js/prose_resolve_targets.js`)

- Extract 1 shared clone group (1541 lines) from prose_allocate_hats.js, prose_resolve_targets.js into js (~1541 lines saved)

**Summary:** 3082 duplicated lines (9.4%) across 2 files

## Vital Signs

| Metric | Value |
|:-------|------:|
| Total LOC | 32960 |
| Avg Cyclomatic | 3.3 |
| P90 Cyclomatic | 6 |
| Dead Files | 100.0% |
| Dead Exports | 0.0% |
| Maintainability (avg) | 73.7 |
| Hotspots (since 6 months) | 1 |
| Circular Deps | 0 |
| Unused Deps | 0 |

## Fallow: 510 high complexity functions

| File | Function | Severity | Cyclomatic | Cognitive | CRAP | Lines |
|:-----|:---------|:---------|:-----------|:----------|:-----|:------|
| `js/prose_allocate_hats.js:7276` | `composeNode` | critical | 61 **!** | 109 **!** | 3782.0 **!** | 126 |
| `js/prose_resolve_targets.js:7740` | `composeNode` | critical | 61 **!** | 109 **!** | 3782.0 **!** | 126 |
| `js/prose_allocate_hats.js:723` | `runInContext2` | critical | 46 **!** | 41 **!** | 2162.0 **!** | 4775 |
| `js/prose_resolve_targets.js:723` | `runInContext2` | critical | 46 **!** | 41 **!** | 2162.0 **!** | 4775 |
| `js/prose_resolve_targets.js:5743` | `<anonymous>` | critical | 45 **!** | 101 **!** | 2070.0 **!** | 160 |
| `js/prose_allocate_hats.js:8036` | `writeNode` | critical | 38 **!** | 70 **!** | 1482.0 **!** | 81 |
| `js/prose_resolve_targets.js:8500` | `writeNode` | critical | 38 **!** | 70 **!** | 1482.0 **!** | 81 |
| `js/prose_allocate_hats.js:6909` | `readBlockScalar` | critical | 37 **!** | 78 **!** | 1406.0 **!** | 96 |
| `js/prose_resolve_targets.js:7373` | `readBlockScalar` | critical | 37 **!** | 78 **!** | 1406.0 **!** | 96 |
| `js/prose_allocate_hats.js:6681` | `readPlainScalar` | critical | 35 **!** | 34 **!** | 1260.0 **!** | 65 |
| `js/prose_resolve_targets.js:7145` | `readPlainScalar` | critical | 35 **!** | 34 **!** | 1260.0 **!** | 65 |
| `js/prose_allocate_hats.js:2062` | `compareAscending` | critical | 32 **!** | 15 | 1056.0 **!** | 13 |
| `js/prose_allocate_hats.js:7054` | `readBlockMapping` | critical | 32 **!** | 72 **!** | 1056.0 **!** | 110 |
| `js/prose_resolve_targets.js:2062` | `compareAscending` | critical | 32 **!** | 15 | 1056.0 **!** | 13 |
| `js/prose_resolve_targets.js:7518` | `readBlockMapping` | critical | 32 **!** | 72 **!** | 1056.0 **!** | 110 |
| `js/prose_allocate_hats.js:7730` | `chooseScalarStyle` | critical | 30 **!** | 42 **!** | 930.0 **!** | 50 |
| `js/prose_resolve_targets.js:8194` | `chooseScalarStyle` | critical | 30 **!** | 42 **!** | 930.0 **!** | 50 |
| `js/prose_allocate_hats.js:5918` | `resolveYamlInteger` | critical | 29 **!** | 58 **!** | 870.0 **!** | 66 |
| `js/prose_resolve_targets.js:6382` | `resolveYamlInteger` | critical | 29 **!** | 58 **!** | 870.0 **!** | 66 |
| `js/prose_allocate_hats.js:1166` | `baseClone` | critical | 28 **!** | 46 **!** | 812.0 **!** | 60 |
| `js/prose_allocate_hats.js:37` | `<anonymous>` | critical | 28 **!** | 17 **!** | 812.0 **!** | 5474 |
| `js/prose_allocate_hats.js:7402` | `readDocument` | critical | 28 **!** | 45 **!** | 812.0 **!** | 75 |
| `js/prose_resolve_targets.js:1166` | `baseClone` | critical | 28 **!** | 46 **!** | 812.0 **!** | 60 |
| `js/prose_resolve_targets.js:37` | `<anonymous>` | critical | 28 **!** | 17 **!** | 812.0 **!** | 5474 |
| `js/prose_resolve_targets.js:7866` | `readDocument` | critical | 28 **!** | 45 **!** | 812.0 **!** | 75 |
| `js/prose_allocate_hats.js:2684` | `equalObjects` | critical | 25 **!** | 28 **!** | 650.0 **!** | 43 |
| `js/prose_resolve_targets.js:2684` | `equalObjects` | critical | 25 **!** | 28 **!** | 650.0 **!** | 43 |
| `js/prose_allocate_hats.js:1081` | `arrayLikeKeys` | critical | 24 **!** | 16 **!** | 600.0 **!** | 13 |
| `js/prose_allocate_hats.js:8339` | `toString2` | critical | 24 **!** | 19 **!** | 600.0 **!** | 41 |
| `js/prose_resolve_targets.js:1081` | `arrayLikeKeys` | critical | 24 **!** | 16 **!** | 600.0 **!** | 13 |
| `js/prose_resolve_targets.js:8803` | `toString2` | critical | 24 **!** | 19 **!** | 600.0 **!** | 41 |
| `js/prose_resolve_targets.js:13579` | `getInsertionDelimiter` | critical | 24 **!** | 1 | 600.0 **!** | 31 |
| `js/prose_resolve_targets.js:19288` | `create` | critical | 24 **!** | 7 | 600.0 **!** | 59 |
| `js/prose_allocate_hats.js:1456` | `baseIsEqualDeep` | critical | 23 **!** | 29 **!** | 552.0 **!** | 30 |
| `js/prose_allocate_hats.js:2524` | `createWrap` | critical | 23 **!** | 24 **!** | 552.0 **!** | 54 |
| `js/prose_allocate_hats.js:7705` | `isPlainSafeFirst` | critical | 23 **!** | 1 | 552.0 **!** | 3 |
| `js/prose_resolve_targets.js:1456` | `baseIsEqualDeep` | critical | 23 **!** | 29 **!** | 552.0 **!** | 30 |
| `js/prose_resolve_targets.js:2524` | `createWrap` | critical | 23 **!** | 24 **!** | 552.0 **!** | 54 |
| `js/prose_resolve_targets.js:8169` | `isPlainSafeFirst` | critical | 23 **!** | 1 | 552.0 **!** | 3 |
| `js/prose_allocate_hats.js:1862` | `baseSortedIndexBy` | critical | 22 **!** | 24 **!** | 506.0 **!** | 30 |
| `js/prose_allocate_hats.js:2638` | `equalByTag` | critical | 22 **!** | 16 **!** | 506.0 **!** | 46 |
| `js/prose_allocate_hats.js:2996` | `mergeData` | critical | 22 **!** | 24 **!** | 506.0 **!** | 36 |
| `js/prose_allocate_hats.js:7164` | `readTagProperty` | critical | 22 **!** | 39 **!** | 506.0 **!** | 72 |
| `js/prose_resolve_targets.js:1862` | `baseSortedIndexBy` | critical | 22 **!** | 24 **!** | 506.0 **!** | 30 |
| `js/prose_resolve_targets.js:2638` | `equalByTag` | critical | 22 **!** | 16 **!** | 506.0 **!** | 46 |
| `js/prose_resolve_targets.js:2996` | `mergeData` | critical | 22 **!** | 24 **!** | 506.0 **!** | 36 |
| `js/prose_resolve_targets.js:7628` | `readTagProperty` | critical | 22 **!** | 39 **!** | 506.0 **!** | 72 |
| `js/prose_allocate_hats.js:1394` | `baseIntersection` | critical | 21 **!** | 37 **!** | 462.0 **!** | 32 |
| `js/prose_resolve_targets.js:1394` | `baseIntersection` | critical | 21 **!** | 37 **!** | 462.0 **!** | 32 |
| `js/prose_allocate_hats.js:1617` | `baseMergeDeep` | critical | 20 | 24 **!** | 420.0 **!** | 43 |
| `js/prose_allocate_hats.js:7957` | `writeBlockMapping` | critical | 20 | 30 **!** | 420.0 **!** | 48 |
| `js/prose_resolve_targets.js:1617` | `baseMergeDeep` | critical | 20 | 24 **!** | 420.0 **!** | 43 |
| `js/prose_resolve_targets.js:8421` | `writeBlockMapping` | critical | 20 | 30 **!** | 420.0 **!** | 48 |
| `js/prose_allocate_hats.js:2881` | `initCloneByTag` | critical | 20 | 1 | 420.0 **!** | 33 |
| `js/prose_resolve_targets.js:2881` | `initCloneByTag` | critical | 20 | 1 | 420.0 **!** | 33 |
| `js/prose_allocate_hats.js:6428` | `simpleEscapeSequence` | critical | 19 | 171 **!** | 380.0 **!** | 3 |
| `js/prose_allocate_hats.js:6564` | `storeMappingPair` | critical | 19 | 30 **!** | 380.0 **!** | 49 |
| `js/prose_resolve_targets.js:6892` | `simpleEscapeSequence` | critical | 19 | 171 **!** | 380.0 **!** | 3 |
| `js/prose_resolve_targets.js:7028` | `storeMappingPair` | critical | 19 | 30 **!** | 380.0 **!** | 49 |
| `js/prose_allocate_hats.js:2334` | `wrapper` | critical | 18 | 16 **!** | 342.0 **!** | 45 |
| `js/prose_allocate_hats.js:4761` | `truncate` | critical | 18 | 28 **!** | 342.0 **!** | 47 |
| `js/prose_resolve_targets.js:2334` | `wrapper` | critical | 18 | 16 **!** | 342.0 **!** | 45 |
| `js/prose_resolve_targets.js:4761` | `truncate` | critical | 18 | 28 **!** | 342.0 **!** | 47 |
| `js/prose_allocate_hats.js:1925` | `baseUniq` | critical | 17 | 33 **!** | 306.0 **!** | 40 |
| `js/prose_allocate_hats.js:2295` | `<anonymous>` | critical | 17 | 19 **!** | 306.0 **!** | 36 |
| `js/prose_allocate_hats.js:2595` | `equalArrays` | critical | 17 | 24 **!** | 306.0 **!** | 43 |
| `js/prose_allocate_hats.js:4673` | `template` | critical | 17 | 16 **!** | 306.0 **!** | 49 |
| `js/prose_allocate_hats.js:6833` | `readFlowCollection` | critical | 17 | 28 **!** | 306.0 **!** | 76 |
| `js/prose_allocate_hats.js:8005` | `detectType` | critical | 17 | 29 **!** | 306.0 **!** | 31 |
| `js/prose_allocate_hats.js:9043` | `stringInputToObject` | critical | 17 | 20 **!** | 306.0 **!** | 97 |
| `js/prose_resolve_targets.js:1925` | `baseUniq` | critical | 17 | 33 **!** | 306.0 **!** | 40 |
| `js/prose_resolve_targets.js:2295` | `<anonymous>` | critical | 17 | 19 **!** | 306.0 **!** | 36 |
| `js/prose_resolve_targets.js:2595` | `equalArrays` | critical | 17 | 24 **!** | 306.0 **!** | 43 |
| `js/prose_resolve_targets.js:4673` | `template` | critical | 17 | 16 **!** | 306.0 **!** | 49 |
| `js/prose_resolve_targets.js:7297` | `readFlowCollection` | critical | 17 | 28 **!** | 306.0 **!** | 76 |
| `js/prose_resolve_targets.js:8469` | `detectType` | critical | 17 | 29 **!** | 306.0 **!** | 31 |
| `js/prose_resolve_targets.js:9507` | `stringInputToObject` | critical | 17 | 20 **!** | 306.0 **!** | 97 |
| `js/prose_allocate_hats.js:5432` | `<anonymous>` | critical | 16 | 15 | 272.0 **!** | 22 |
| `js/prose_allocate_hats.js:7694` | `isPlainSafe` | critical | 16 | 7 | 272.0 **!** | 11 |
| `js/prose_allocate_hats.js:7781` | `<anonymous>` | critical | 16 | 15 | 272.0 **!** | 39 |
| `js/prose_resolve_targets.js:5432` | `<anonymous>` | critical | 16 | 15 | 272.0 **!** | 22 |
| `js/prose_resolve_targets.js:8158` | `isPlainSafe` | critical | 16 | 7 | 272.0 **!** | 11 |
| `js/prose_resolve_targets.js:8245` | `<anonymous>` | critical | 16 | 15 | 272.0 **!** | 39 |
| `js/prose_resolve_targets.js:14772` | `create` | critical | 16 | 1 | 272.0 **!** | 40 |
| `js/prose_allocate_hats.js:5621` | `makeSnippet` | critical | 15 | 17 **!** | 240.0 **!** | 58 |
| `js/prose_allocate_hats.js:6630` | `skipSeparationSpace` | critical | 15 | 22 **!** | 240.0 **!** | 32 |
| `js/prose_resolve_targets.js:6085` | `makeSnippet` | critical | 15 | 17 **!** | 240.0 **!** | 58 |
| `js/prose_resolve_targets.js:7094` | `skipSeparationSpace` | critical | 15 | 22 **!** | 240.0 **!** | 32 |
| `js/prose_allocate_hats.js:6068` | `representYamlFloat` | critical | 15 | 11 | 240.0 **!** | 35 |
| `js/prose_allocate_hats.js:7633` | `State` | critical | 15 | 14 | 240.0 **!** | 22 |
| `js/prose_allocate_hats.js:8454` | `inputToRGB` | critical | 15 | 15 | 240.0 **!** | 47 |
| `js/prose_resolve_targets.js:6532` | `representYamlFloat` | critical | 15 | 11 | 240.0 **!** | 35 |
| `js/prose_resolve_targets.js:8097` | `State` | critical | 15 | 14 | 240.0 **!** | 22 |
| `js/prose_resolve_targets.js:8918` | `inputToRGB` | critical | 15 | 15 | 240.0 **!** | 47 |
| `js/prose_allocate_hats.js:1254` | `baseDifference` | critical | 14 | 22 **!** | 210.0 **!** | 34 |
| `js/prose_allocate_hats.js:1489` | `baseIsMatch` | critical | 14 | 25 **!** | 210.0 **!** | 31 |
| `js/prose_allocate_hats.js:6780` | `readDoubleQuotedScalar` | critical | 14 | 26 **!** | 210.0 **!** | 53 |
| `js/prose_allocate_hats.js:7005` | `readBlockSequence` | critical | 14 | 20 **!** | 210.0 **!** | 49 |
| `js/prose_resolve_targets.js:1254` | `baseDifference` | critical | 14 | 22 **!** | 210.0 **!** | 34 |
| `js/prose_resolve_targets.js:1489` | `baseIsMatch` | critical | 14 | 25 **!** | 210.0 **!** | 31 |
| `js/prose_resolve_targets.js:7244` | `readDoubleQuotedScalar` | critical | 14 | 26 **!** | 210.0 **!** | 53 |
| `js/prose_resolve_targets.js:7469` | `readBlockSequence` | critical | 14 | 20 **!** | 210.0 **!** | 49 |
| `js/prose_allocate_hats.js:4096` | `isEmpty` | critical | 14 | 10 | 210.0 **!** | 21 |
| `js/prose_allocate_hats.js:4531` | `random` | critical | 14 | 15 | 210.0 **!** | 36 |
| `js/prose_resolve_targets.js:4096` | `isEmpty` | critical | 14 | 10 | 210.0 **!** | 21 |
| `js/prose_resolve_targets.js:4531` | `random` | critical | 14 | 15 | 210.0 **!** | 36 |
| `js/prose_allocate_hats.js:872` | `lazyValue` | critical | 13 | 20 **!** | 182.0 **!** | 26 |
| `js/prose_resolve_targets.js:872` | `lazyValue` | critical | 13 | 20 **!** | 182.0 **!** | 26 |
| `js/prose_resolve_targets.js:13859` | `compareTargetScopesForward` | critical | 13 | 18 **!** | 182.0 **!** | 18 |
| `js/prose_resolve_targets.js:13877` | `compareTargetScopesBackward` | critical | 13 | 18 **!** | 182.0 **!** | 18 |
| `js/prose_resolve_targets.js:18561` | `useInteriorOfSurroundingTarget` | critical | 13 | 18 **!** | 182.0 **!** | 35 |
| `js/prose_resolve_targets.js:18680` | `<arrow>` | critical | 13 | 16 **!** | 182.0 **!** | 27 |
| `js/prose_allocate_hats.js:5708` | `Type$1` | critical | 13 | 12 | 182.0 **!** | 27 |
| `js/prose_resolve_targets.js:6172` | `Type$1` | critical | 13 | 12 | 182.0 **!** | 27 |
| `js/prose_resolve_targets.js:13459` | `getTokenRemovalRange` | critical | 13 | 11 | 182.0 **!** | 22 |
| `js/prose_allocate_hats.js:1784` | `baseSet` | critical | 12 | 23 **!** | 156.0 **!** | 23 |
| `js/prose_allocate_hats.js:4248` | `toNumber` | critical | 12 | 16 **!** | 156.0 **!** | 18 |
| `js/prose_resolve_targets.js:1784` | `baseSet` | critical | 12 | 23 **!** | 156.0 **!** | 23 |
| `js/prose_resolve_targets.js:4248` | `toNumber` | critical | 12 | 16 **!** | 156.0 **!** | 18 |
| `js/prose_resolve_targets.js:5945` | `islice` | critical | 12 | 16 **!** | 156.0 **!** | 32 |
| `js/prose_resolve_targets.js:15898` | `<arrow>` | critical | 12 | 18 **!** | 156.0 **!** | 32 |
| `js/prose_actions.js:231` | `proseRunAction` | critical | 12 | 8 | 156.0 **!** | 43 |
| `js/prose_allocate_hats.js:4647` | `split` | critical | 12 | 11 | 156.0 **!** | 17 |
| `js/prose_resolve_targets.js:4647` | `split` | critical | 12 | 11 | 156.0 **!** | 17 |
| `js/prose_allocate_hats.js:7907` | `writeBlockSequence` | critical | 11 | 17 **!** | 132.0 **!** | 22 |
| `js/prose_resolve_targets.js:8371` | `writeBlockSequence` | critical | 11 | 17 **!** | 132.0 **!** | 22 |
| `js/prose_allocate_hats.js:2854` | `hasPath` | critical | 11 | 9 | 132.0 **!** | 16 |
| `js/prose_allocate_hats.js:7688` | `isPrintable` | critical | 11 | 5 | 132.0 **!** | 3 |
| `js/prose_resolve_targets.js:2854` | `hasPath` | critical | 11 | 9 | 132.0 **!** | 16 |
| `js/prose_resolve_targets.js:8152` | `isPrintable` | critical | 11 | 5 | 132.0 **!** | 3 |
| `js/prose_resolve_targets.js:13993` | `canStopEarly` | critical | 11 | 10 | 132.0 **!** | 17 |
| `js/prose_resolve_targets.js:15304` | `create` | critical | 11 | 1 | 132.0 **!** | 22 |
| `js/prose_resolve_targets.js:18804` | `<arrow>` | critical | 11 | 6 | 132.0 **!** | 31 |
| `js/prose_allocate_hats.js:7929` | `writeFlowMapping` | critical | 10 | 17 **!** | 110.0 **!** | 28 |
| `js/prose_resolve_targets.js:8393` | `writeFlowMapping` | critical | 10 | 17 **!** | 110.0 **!** | 28 |
| `js/prose_resolve_targets.js:14833` | `getLineNumber` | critical | 10 | 17 **!** | 110.0 **!** | 40 |
| `js/prose_resolve_targets.js:18081` | `findDelimiterPairAdjacentToSelection` | critical | 10 | 19 **!** | 110.0 **!** | 29 |
| `js/prose_allocate_hats.js:1847` | `baseSortedIndex` | critical | 10 | 13 | 110.0 **!** | 15 |
| `js/prose_allocate_hats.js:1973` | `baseWhile` | critical | 10 | 13 | 110.0 **!** | 6 |
| `js/prose_allocate_hats.js:2159` | `<anonymous>` | critical | 10 | 11 | 110.0 **!** | 16 |
| `js/prose_allocate_hats.js:2228` | `<anonymous>` | critical | 10 | 2 | 110.0 **!** | 23 |
| `js/prose_allocate_hats.js:2942` | `isKey` | critical | 10 | 5 | 110.0 **!** | 10 |
| `js/prose_allocate_hats.js:4471` | `transform` | critical | 10 | 14 | 110.0 **!** | 18 |
| `js/prose_allocate_hats.js:5778` | `extend2` | critical | 10 | 12 | 110.0 **!** | 39 |
| `js/prose_allocate_hats.js:5984` | `constructYamlInteger` | critical | 10 | 13 | 110.0 **!** | 24 |
| `js/prose_allocate_hats.js:6138` | `constructYamlTimestamp` | critical | 10 | 11 | 110.0 **!** | 35 |
| `js/prose_resolve_targets.js:1847` | `baseSortedIndex` | critical | 10 | 13 | 110.0 **!** | 15 |
| `js/prose_resolve_targets.js:1973` | `baseWhile` | critical | 10 | 13 | 110.0 **!** | 6 |
| `js/prose_resolve_targets.js:2159` | `<anonymous>` | critical | 10 | 11 | 110.0 **!** | 16 |
| `js/prose_resolve_targets.js:2228` | `<anonymous>` | critical | 10 | 2 | 110.0 **!** | 23 |
| `js/prose_resolve_targets.js:2942` | `isKey` | critical | 10 | 5 | 110.0 **!** | 10 |
| `js/prose_resolve_targets.js:4471` | `transform` | critical | 10 | 14 | 110.0 **!** | 18 |
| `js/prose_resolve_targets.js:6242` | `extend2` | critical | 10 | 12 | 110.0 **!** | 39 |
| `js/prose_resolve_targets.js:6448` | `constructYamlInteger` | critical | 10 | 13 | 110.0 **!** | 24 |
| `js/prose_resolve_targets.js:6602` | `constructYamlTimestamp` | critical | 10 | 11 | 110.0 **!** | 35 |
| `js/prose_resolve_targets.js:13909` | `checkRequirements` | critical | 10 | 9 | 110.0 **!** | 34 |
| `js/prose_resolve_targets.js:14893` | `createContinuousRangeTarget` | critical | 10 | 7 | 110.0 **!** | 35 |
| `js/prose_resolve_targets.js:15511` | `run` | critical | 10 | 14 | 110.0 **!** | 45 |
| `js/prose_resolve_targets.js:19040` | `computeProximalIndex` | critical | 10 | 15 | 110.0 **!** | 32 |
| `js/prose_allocate_hats.js:6270` | `resolveYamlOmap` | high | 9 | 19 **!** | 90.0 **!** | 26 |
| `js/prose_resolve_targets.js:6734` | `resolveYamlOmap` | high | 9 | 19 **!** | 90.0 **!** | 26 |
| `scripts/sync-to-talon.ts:43` | `isExcluded` | high | 9 | 1 | 90.0 **!** | 13 |
| `js/prose_allocate_hats.js:2254` | `wrapper` | high | 9 | 6 | 90.0 **!** | 24 |
| `js/prose_allocate_hats.js:2470` | `createRecurry` | high | 9 | 8 | 90.0 **!** | 26 |
| `js/prose_allocate_hats.js:2810` | `<anonymous>` | high | 9 | 5 | 90.0 **!** | 18 |
| `js/prose_allocate_hats.js:4300` | `defaults` | high | 9 | 11 | 90.0 **!** | 23 |
| `js/prose_allocate_hats.js:5879` | `resolveYamlBoolean` | high | 9 | 6 | 90.0 **!** | 6 |
| `js/prose_allocate_hats.js:7477` | `loadDocuments` | high | 9 | 10 | 90.0 **!** | 27 |
| `js/prose_allocate_hats.js:8190` | `tinycolor` | high | 9 | 8 | 90.0 **!** | 20 |
| `js/prose_resolve_targets.js:2254` | `wrapper` | high | 9 | 6 | 90.0 **!** | 24 |
| `js/prose_resolve_targets.js:2470` | `createRecurry` | high | 9 | 8 | 90.0 **!** | 26 |
| `js/prose_resolve_targets.js:2810` | `<anonymous>` | high | 9 | 5 | 90.0 **!** | 18 |
| `js/prose_resolve_targets.js:4300` | `defaults` | high | 9 | 11 | 90.0 **!** | 23 |
| `js/prose_resolve_targets.js:6343` | `resolveYamlBoolean` | high | 9 | 6 | 90.0 **!** | 6 |
| `js/prose_resolve_targets.js:7941` | `loadDocuments` | high | 9 | 10 | 90.0 **!** | 27 |
| `js/prose_resolve_targets.js:8654` | `tinycolor` | high | 9 | 8 | 90.0 **!** | 20 |
| `js/prose_resolve_targets.js:15376` | `getPreferredScopeTouchingPosition` | high | 9 | 8 | 90.0 **!** | 30 |
| `js/prose_resolve_targets.js:15983` | `searchNodeDescending` | high | 9 | 15 | 90.0 **!** | 23 |
| `js/prose_resolve_targets.js:16115` | `<arrow>` | high | 9 | 1 | 90.0 **!** | 1 |
| `js/prose_resolve_targets.js:17231` | `blockFinder` | high | 9 | 5 | 90.0 **!** | 12 |
| `js/prose_resolve_targets.js:18002` | `generateUnmatchedDelimiters` | high | 9 | 10 | 90.0 **!** | 31 |
| `js/prose_allocate_hats.js:8125` | `inspectNode` | high | 8 | 20 **!** | 72.0 **!** | 23 |
| `js/prose_resolve_targets.js:8589` | `inspectNode` | high | 8 | 20 **!** | 72.0 **!** | 23 |
| `js/prose_allocate_hats.js:13` | `__copyProps` | high | 8 | 10 | 72.0 **!** | 8 |
| `js/prose_allocate_hats.js:1308` | `baseFill` | high | 8 | 8 | 72.0 **!** | 16 |
| `js/prose_allocate_hats.js:1333` | `baseFlatten` | high | 8 | 11 | 72.0 **!** | 18 |
| `js/prose_allocate_hats.js:1713` | `basePullAll` | high | 8 | 11 | 72.0 **!** | 19 |
| `js/prose_allocate_hats.js:2387` | `<anonymous>` | high | 8 | 10 | 72.0 **!** | 23 |
| `js/prose_allocate_hats.js:2927` | `isIndex` | high | 8 | 5 | 72.0 **!** | 5 |
| `js/prose_allocate_hats.js:3397` | `slice` | high | 8 | 9 | 72.0 **!** | 14 |
| `js/prose_allocate_hats.js:3687` | `includes` | high | 8 | 7 | 72.0 **!** | 9 |
| `js/prose_allocate_hats.js:4217` | `toArray2` | high | 8 | 9 | 72.0 **!** | 13 |
| `js/prose_allocate_hats.js:5404` | `<anonymous>` | high | 8 | 8 | 72.0 **!** | 17 |
| `js/prose_allocate_hats.js:6533` | `captureSegment` | high | 8 | 13 | 72.0 **!** | 17 |
| `js/prose_allocate_hats.js:6746` | `readSingleQuotedScalar` | high | 8 | 12 | 72.0 **!** | 34 |
| `js/prose_allocate_hats.js:7850` | `foldLine` | high | 8 | 11 | 72.0 **!** | 24 |
| `js/prose_allocate_hats.js:7891` | `writeFlowSequence` | high | 8 | 14 | 72.0 **!** | 16 |
| `js/prose_allocate_hats.js:9140` | `validateWCAG2Parms` | high | 8 | 7 | 72.0 **!** | 19 |
| `js/prose_resolve_targets.js:13` | `__copyProps` | high | 8 | 10 | 72.0 **!** | 8 |
| `js/prose_resolve_targets.js:1308` | `baseFill` | high | 8 | 8 | 72.0 **!** | 16 |
| `js/prose_resolve_targets.js:1333` | `baseFlatten` | high | 8 | 11 | 72.0 **!** | 18 |
| `js/prose_resolve_targets.js:1713` | `basePullAll` | high | 8 | 11 | 72.0 **!** | 19 |
| `js/prose_resolve_targets.js:2387` | `<anonymous>` | high | 8 | 10 | 72.0 **!** | 23 |
| `js/prose_resolve_targets.js:2927` | `isIndex` | high | 8 | 5 | 72.0 **!** | 5 |
| `js/prose_resolve_targets.js:3397` | `slice` | high | 8 | 9 | 72.0 **!** | 14 |
| `js/prose_resolve_targets.js:3687` | `includes` | high | 8 | 7 | 72.0 **!** | 9 |
| `js/prose_resolve_targets.js:4217` | `toArray2` | high | 8 | 9 | 72.0 **!** | 13 |
| `js/prose_resolve_targets.js:5404` | `<anonymous>` | high | 8 | 8 | 72.0 **!** | 17 |
| `js/prose_resolve_targets.js:5517` | `sanitizeHtml` | high | 8 | 7 | 72.0 **!** | 10 |
| `js/prose_resolve_targets.js:6997` | `captureSegment` | high | 8 | 13 | 72.0 **!** | 17 |
| `js/prose_resolve_targets.js:7210` | `readSingleQuotedScalar` | high | 8 | 12 | 72.0 **!** | 34 |
| `js/prose_resolve_targets.js:8314` | `foldLine` | high | 8 | 11 | 72.0 **!** | 24 |
| `js/prose_resolve_targets.js:8355` | `writeFlowSequence` | high | 8 | 14 | 72.0 **!** | 16 |
| `js/prose_resolve_targets.js:9604` | `validateWCAG2Parms` | high | 8 | 7 | 72.0 **!** | 19 |
| `js/prose_resolve_targets.js:14405` | `constructTarget` | high | 8 | 7 | 72.0 **!** | 16 |
| `js/prose_resolve_targets.js:14576` | `generateScopeCandidates` | high | 8 | 10 | 72.0 **!** | 22 |
| `js/prose_resolve_targets.js:15213` | `targetsToVerticalTarget` | high | 8 | 8 | 72.0 **!** | 29 |
| `js/prose_resolve_targets.js:15408` | `getContainingScopeTarget` | high | 8 | 10 | 72.0 **!** | 51 |
| `js/prose_resolve_targets.js:18112` | `findDelimiterPairContainingSelection` | high | 8 | 11 | 72.0 **!** | 40 |
| `js/prose_allocate_hats.js:368` | `nodeUtil` | high | 7 | 4 | 56.0 **!** | 10 |
| `js/prose_allocate_hats.js:1447` | `baseIsEqual` | high | 7 | 5 | 56.0 **!** | 9 |
| `js/prose_allocate_hats.js:1758` | `baseRepeat` | high | 7 | 7 | 56.0 **!** | 16 |
| `js/prose_allocate_hats.js:1822` | `baseSlice` | high | 7 | 7 | 56.0 **!** | 17 |
| `js/prose_allocate_hats.js:1912` | `baseToString` | high | 7 | 7 | 56.0 **!** | 13 |
| `js/prose_allocate_hats.js:1988` | `baseXor` | high | 7 | 10 | 56.0 **!** | 16 |
| `js/prose_allocate_hats.js:2177` | `<anonymous>` | high | 7 | 7 | 56.0 **!** | 15 |
| `js/prose_allocate_hats.js:2433` | `wrapper` | high | 7 | 5 | 56.0 **!** | 10 |
| `js/prose_allocate_hats.js:2446` | `<anonymous>` | high | 7 | 7 | 56.0 **!** | 14 |
| `js/prose_allocate_hats.js:3164` | `chunk` | high | 7 | 7 | 56.0 **!** | 16 |
| `js/prose_allocate_hats.js:3569` | `wrapperAt` | high | 7 | 4 | 56.0 **!** | 20 |
| `js/prose_allocate_hats.js:3710` | `orderBy` | high | 7 | 8 | 56.0 **!** | 13 |
| `js/prose_allocate_hats.js:3852` | `debounce` | high | 7 | 8 | 56.0 **!** | 81 |
| `js/prose_allocate_hats.js:4181` | `isPlainObject2` | high | 7 | 5 | 56.0 **!** | 11 |
| `js/prose_allocate_hats.js:4230` | `toFinite` | high | 7 | 8 | 56.0 **!** | 11 |
| `js/prose_allocate_hats.js:4891` | `mixin` | high | 7 | 5 | 56.0 **!** | 27 |
| `js/prose_allocate_hats.js:5843` | `resolveYamlNull` | high | 7 | 5 | 56.0 **!** | 6 |
| `js/prose_allocate_hats.js:6205` | `constructYamlBinary` | high | 7 | 7 | 56.0 **!** | 23 |
| `js/prose_allocate_hats.js:6228` | `representYamlBinary` | high | 7 | 7 | 56.0 **!** | 30 |
| `js/prose_allocate_hats.js:6447` | `State$1` | high | 7 | 6 | 56.0 **!** | 18 |
| `js/prose_allocate_hats.js:6486` | `handleYamlDirective` | high | 7 | 6 | 56.0 **!** | 23 |
| `js/prose_allocate_hats.js:6662` | `testDocumentSeparator` | high | 7 | 6 | 56.0 **!** | 12 |
| `js/prose_allocate_hats.js:7236` | `readAnchorProperty` | high | 7 | 5 | 56.0 **!** | 19 |
| `js/prose_allocate_hats.js:7255` | `readAlias` | high | 7 | 5 | 56.0 **!** | 21 |
| `js/prose_allocate_hats.js:7874` | `escapeString` | high | 7 | 10 | 56.0 **!** | 17 |
| `js/prose_allocate_hats.js:8508` | `rgbToHsl` | high | 7 | 9 | 56.0 **!** | 30 |
| `js/prose_allocate_hats.js:8571` | `rgbToHsv` | high | 7 | 8 | 56.0 **!** | 30 |
| `js/prose_allocate_hats.js:12710` | `proseAllocateHats` | high | 7 | 8 | 56.0 **!** | 67 |
| `js/prose_resolve_targets.js:368` | `nodeUtil` | high | 7 | 4 | 56.0 **!** | 10 |
| `js/prose_resolve_targets.js:1447` | `baseIsEqual` | high | 7 | 5 | 56.0 **!** | 9 |
| `js/prose_resolve_targets.js:1758` | `baseRepeat` | high | 7 | 7 | 56.0 **!** | 16 |
| `js/prose_resolve_targets.js:1822` | `baseSlice` | high | 7 | 7 | 56.0 **!** | 17 |
| `js/prose_resolve_targets.js:1912` | `baseToString` | high | 7 | 7 | 56.0 **!** | 13 |
| `js/prose_resolve_targets.js:1988` | `baseXor` | high | 7 | 10 | 56.0 **!** | 16 |
| `js/prose_resolve_targets.js:2177` | `<anonymous>` | high | 7 | 7 | 56.0 **!** | 15 |
| `js/prose_resolve_targets.js:2433` | `wrapper` | high | 7 | 5 | 56.0 **!** | 10 |
| `js/prose_resolve_targets.js:2446` | `<anonymous>` | high | 7 | 7 | 56.0 **!** | 14 |
| `js/prose_resolve_targets.js:3164` | `chunk` | high | 7 | 7 | 56.0 **!** | 16 |
| `js/prose_resolve_targets.js:3569` | `wrapperAt` | high | 7 | 4 | 56.0 **!** | 20 |
| `js/prose_resolve_targets.js:3710` | `orderBy` | high | 7 | 8 | 56.0 **!** | 13 |
| `js/prose_resolve_targets.js:3852` | `debounce` | high | 7 | 8 | 56.0 **!** | 81 |
| `js/prose_resolve_targets.js:4181` | `isPlainObject2` | high | 7 | 5 | 56.0 **!** | 11 |
| `js/prose_resolve_targets.js:4230` | `toFinite` | high | 7 | 8 | 56.0 **!** | 11 |
| `js/prose_resolve_targets.js:4891` | `mixin` | high | 7 | 5 | 56.0 **!** | 27 |
| `js/prose_resolve_targets.js:6307` | `resolveYamlNull` | high | 7 | 5 | 56.0 **!** | 6 |
| `js/prose_resolve_targets.js:6669` | `constructYamlBinary` | high | 7 | 7 | 56.0 **!** | 23 |
| `js/prose_resolve_targets.js:6692` | `representYamlBinary` | high | 7 | 7 | 56.0 **!** | 30 |
| `js/prose_resolve_targets.js:6911` | `State$1` | high | 7 | 6 | 56.0 **!** | 18 |
| `js/prose_resolve_targets.js:6950` | `handleYamlDirective` | high | 7 | 6 | 56.0 **!** | 23 |
| `js/prose_resolve_targets.js:7126` | `testDocumentSeparator` | high | 7 | 6 | 56.0 **!** | 12 |
| `js/prose_resolve_targets.js:7700` | `readAnchorProperty` | high | 7 | 5 | 56.0 **!** | 19 |
| `js/prose_resolve_targets.js:7719` | `readAlias` | high | 7 | 5 | 56.0 **!** | 21 |
| `js/prose_resolve_targets.js:8338` | `escapeString` | high | 7 | 10 | 56.0 **!** | 17 |
| `js/prose_resolve_targets.js:8972` | `rgbToHsl` | high | 7 | 9 | 56.0 **!** | 30 |
| `js/prose_resolve_targets.js:9035` | `rgbToHsv` | high | 7 | 8 | 56.0 **!** | 30 |
| `js/prose_resolve_targets.js:13962` | `generateScopes` | high | 7 | 10 | 56.0 **!** | 31 |
| `js/prose_resolve_targets.js:15948` | `tryPatternMatch` | high | 7 | 5 | 56.0 **!** | 17 |
| `js/prose_resolve_targets.js:15965` | `searchNodeAscending` | high | 7 | 10 | 56.0 **!** | 18 |
| `js/prose_resolve_targets.js:17378` | `returnValueFinder` | high | 7 | 7 | 56.0 **!** | 23 |
| `js/prose_resolve_targets.js:18366` | `getDelimiterPairOffsets` | high | 7 | 5 | 56.0 **!** | 53 |
| `js/prose_resolve_targets.js:18447` | `processSurroundingPairCore` | high | 7 | 9 | 56.0 **!** | 72 |
| `js/prose_allocate_hats.js:757` | `lodash` | moderate | 6 | 6 | 42.0 **!** | 11 |
| `js/prose_allocate_hats.js:1155` | `baseClamp` | moderate | 6 | 11 | 42.0 **!** | 11 |
| `js/prose_allocate_hats.js:1232` | `baseConformsTo` | moderate | 6 | 6 | 42.0 **!** | 14 |
| `js/prose_allocate_hats.js:1298` | `baseExtremum` | moderate | 6 | 6 | 42.0 **!** | 10 |
| `js/prose_allocate_hats.js:1560` | `baseKeysIn` | moderate | 6 | 6 | 42.0 **!** | 12 |
| `js/prose_allocate_hats.js:1732` | `basePullAt` | moderate | 6 | 9 | 42.0 **!** | 15 |
| `js/prose_allocate_hats.js:1892` | `baseSortedUniq` | moderate | 6 | 9 | 42.0 **!** | 11 |
| `js/prose_allocate_hats.js:2089` | `composeArgs` | moderate | 6 | 6 | 42.0 **!** | 15 |
| `js/prose_allocate_hats.js:2104` | `composeArgsRight` | moderate | 6 | 6 | 42.0 **!** | 16 |
| `js/prose_allocate_hats.js:2128` | `copyObject` | moderate | 6 | 9 | 42.0 **!** | 18 |
| `js/prose_allocate_hats.js:2319` | `<anonymous>` | moderate | 6 | 4 | 42.0 **!** | 11 |
| `js/prose_allocate_hats.js:2829` | `getView` | moderate | 6 | 3 | 42.0 **!** | 21 |
| `js/prose_allocate_hats.js:2932` | `isIterateeCall` | moderate | 6 | 5 | 42.0 **!** | 10 |
| `js/prose_allocate_hats.js:3218` | `drop` | moderate | 6 | 5 | 42.0 **!** | 8 |
| `js/prose_allocate_hats.js:3226` | `dropRight` | moderate | 6 | 5 | 42.0 **!** | 9 |
| `js/prose_allocate_hats.js:3241` | `fill` | moderate | 6 | 4 | 42.0 **!** | 11 |
| `js/prose_allocate_hats.js:3345` | `lastIndexOf` | moderate | 6 | 6 | 42.0 **!** | 12 |
| `js/prose_allocate_hats.js:3453` | `take` | moderate | 6 | 5 | 42.0 **!** | 7 |
| `js/prose_allocate_hats.js:3460` | `takeRight` | moderate | 6 | 5 | 42.0 **!** | 9 |
| `js/prose_allocate_hats.js:3757` | `size` | moderate | 6 | 6 | 42.0 **!** | 13 |
| `js/prose_allocate_hats.js:3777` | `sortBy` | moderate | 6 | 5 | 42.0 **!** | 12 |
| `js/prose_allocate_hats.js:4125` | `isError` | moderate | 6 | 3 | 42.0 **!** | 7 |
| `js/prose_allocate_hats.js:4445` | `result` | moderate | 6 | 8 | 42.0 **!** | 17 |
| `js/prose_allocate_hats.js:4505` | `clamp` | moderate | 6 | 7 | 42.0 **!** | 15 |
| `js/prose_allocate_hats.js:4728` | `trim` | moderate | 6 | 5 | 42.0 **!** | 11 |
| `js/prose_allocate_hats.js:4739` | `trimEnd` | moderate | 6 | 5 | 42.0 **!** | 11 |
| `js/prose_allocate_hats.js:4750` | `trimStart` | moderate | 6 | 5 | 42.0 **!** | 11 |
| `js/prose_allocate_hats.js:5343` | `<anonymous>` | moderate | 6 | 7 | 42.0 **!** | 13 |
| `js/prose_allocate_hats.js:5569` | `formatError` | moderate | 6 | 5 | 42.0 **!** | 13 |
| `js/prose_allocate_hats.js:5909` | `isHexCode` | moderate | 6 | 4 | 42.0 **!** | 3 |
| `js/prose_allocate_hats.js:6053` | `constructYamlFloat` | moderate | 6 | 6 | 42.0 **!** | 14 |
| `js/prose_allocate_hats.js:6509` | `handleTagDirective` | moderate | 6 | 5 | 42.0 **!** | 23 |
| `js/prose_allocate_hats.js:7504` | `loadAll$1` | moderate | 6 | 4 | 42.0 **!** | 13 |
| `js/prose_allocate_hats.js:7594` | `compileStyleMap` | moderate | 6 | 7 | 42.0 **!** | 20 |
| `js/prose_allocate_hats.js:7711` | `codePointAt` | moderate | 6 | 5 | 42.0 **!** | 10 |
| `js/prose_allocate_hats.js:7821` | `blockHeader` | moderate | 6 | 6 | 42.0 **!** | 7 |
| `js/prose_allocate_hats.js:7831` | `foldString` | moderate | 6 | 5 | 42.0 **!** | 19 |
| `js/prose_allocate_hats.js:8543` | `hue2rgb` | moderate | 6 | 5 | 42.0 **!** | 13 |
| `js/prose_allocate_hats.js:8619` | `rgbaToHex` | moderate | 6 | 2 | 42.0 **!** | 7 |
| `js/prose_allocate_hats.js:8786` | `<anonymous>` | moderate | 6 | 7 | 42.0 **!** | 26 |
| `js/prose_resolve_targets.js:757` | `lodash` | moderate | 6 | 6 | 42.0 **!** | 11 |
| `js/prose_resolve_targets.js:1155` | `baseClamp` | moderate | 6 | 11 | 42.0 **!** | 11 |
| `js/prose_resolve_targets.js:1232` | `baseConformsTo` | moderate | 6 | 6 | 42.0 **!** | 14 |
| `js/prose_resolve_targets.js:1298` | `baseExtremum` | moderate | 6 | 6 | 42.0 **!** | 10 |
| `js/prose_resolve_targets.js:1560` | `baseKeysIn` | moderate | 6 | 6 | 42.0 **!** | 12 |
| `js/prose_resolve_targets.js:1732` | `basePullAt` | moderate | 6 | 9 | 42.0 **!** | 15 |
| `js/prose_resolve_targets.js:1892` | `baseSortedUniq` | moderate | 6 | 9 | 42.0 **!** | 11 |
| `js/prose_resolve_targets.js:2089` | `composeArgs` | moderate | 6 | 6 | 42.0 **!** | 15 |
| `js/prose_resolve_targets.js:2104` | `composeArgsRight` | moderate | 6 | 6 | 42.0 **!** | 16 |
| `js/prose_resolve_targets.js:2128` | `copyObject` | moderate | 6 | 9 | 42.0 **!** | 18 |
| `js/prose_resolve_targets.js:2319` | `<anonymous>` | moderate | 6 | 4 | 42.0 **!** | 11 |
| `js/prose_resolve_targets.js:2829` | `getView` | moderate | 6 | 3 | 42.0 **!** | 21 |
| `js/prose_resolve_targets.js:2932` | `isIterateeCall` | moderate | 6 | 5 | 42.0 **!** | 10 |
| `js/prose_resolve_targets.js:3218` | `drop` | moderate | 6 | 5 | 42.0 **!** | 8 |
| `js/prose_resolve_targets.js:3226` | `dropRight` | moderate | 6 | 5 | 42.0 **!** | 9 |
| `js/prose_resolve_targets.js:3241` | `fill` | moderate | 6 | 4 | 42.0 **!** | 11 |
| `js/prose_resolve_targets.js:3345` | `lastIndexOf` | moderate | 6 | 6 | 42.0 **!** | 12 |
| `js/prose_resolve_targets.js:3453` | `take` | moderate | 6 | 5 | 42.0 **!** | 7 |
| `js/prose_resolve_targets.js:3460` | `takeRight` | moderate | 6 | 5 | 42.0 **!** | 9 |
| `js/prose_resolve_targets.js:3757` | `size` | moderate | 6 | 6 | 42.0 **!** | 13 |
| `js/prose_resolve_targets.js:3777` | `sortBy` | moderate | 6 | 5 | 42.0 **!** | 12 |
| `js/prose_resolve_targets.js:4125` | `isError` | moderate | 6 | 3 | 42.0 **!** | 7 |
| `js/prose_resolve_targets.js:4445` | `result` | moderate | 6 | 8 | 42.0 **!** | 17 |
| `js/prose_resolve_targets.js:4505` | `clamp` | moderate | 6 | 7 | 42.0 **!** | 15 |
| `js/prose_resolve_targets.js:4728` | `trim` | moderate | 6 | 5 | 42.0 **!** | 11 |
| `js/prose_resolve_targets.js:4739` | `trimEnd` | moderate | 6 | 5 | 42.0 **!** | 11 |
| `js/prose_resolve_targets.js:4750` | `trimStart` | moderate | 6 | 5 | 42.0 **!** | 11 |
| `js/prose_resolve_targets.js:5343` | `<anonymous>` | moderate | 6 | 7 | 42.0 **!** | 13 |
| `js/prose_resolve_targets.js:6033` | `formatError` | moderate | 6 | 5 | 42.0 **!** | 13 |
| `js/prose_resolve_targets.js:6373` | `isHexCode` | moderate | 6 | 4 | 42.0 **!** | 3 |
| `js/prose_resolve_targets.js:6517` | `constructYamlFloat` | moderate | 6 | 6 | 42.0 **!** | 14 |
| `js/prose_resolve_targets.js:6973` | `handleTagDirective` | moderate | 6 | 5 | 42.0 **!** | 23 |
| `js/prose_resolve_targets.js:7968` | `loadAll$1` | moderate | 6 | 4 | 42.0 **!** | 13 |
| `js/prose_resolve_targets.js:8058` | `compileStyleMap` | moderate | 6 | 7 | 42.0 **!** | 20 |
| `js/prose_resolve_targets.js:8175` | `codePointAt` | moderate | 6 | 5 | 42.0 **!** | 10 |
| `js/prose_resolve_targets.js:8285` | `blockHeader` | moderate | 6 | 6 | 42.0 **!** | 7 |
| `js/prose_resolve_targets.js:8295` | `foldString` | moderate | 6 | 5 | 42.0 **!** | 19 |
| `js/prose_resolve_targets.js:9007` | `hue2rgb` | moderate | 6 | 5 | 42.0 **!** | 13 |
| `js/prose_resolve_targets.js:9083` | `rgbaToHex` | moderate | 6 | 2 | 42.0 **!** | 7 |
| `js/prose_resolve_targets.js:9250` | `<anonymous>` | moderate | 6 | 7 | 42.0 **!** | 26 |
| `js/prose_resolve_targets.js:12862` | `position` | moderate | 6 | 9 | 42.0 **!** | 11 |
| `js/prose_resolve_targets.js:13547` | `maybeCreateRichRangeTarget` | moderate | 6 | 5 | 42.0 **!** | 19 |
| `js/prose_resolve_targets.js:14285` | `isPreferredOverHelper` | moderate | 6 | 7 | 42.0 **!** | 15 |
| `js/prose_resolve_targets.js:14599` | `getStartLine` | moderate | 6 | 6 | 42.0 **!** | 16 |
| `js/prose_resolve_targets.js:15085` | `processContinuousRangeTarget` | moderate | 6 | 7 | 42.0 **!** | 31 |
| `js/prose_resolve_targets.js:17097` | `<arrow>` | moderate | 6 | 3 | 42.0 **!** | 7 |
| `js/prose_resolve_targets.js:18257` | `delimiterInfo` | moderate | 6 | 4 | 42.0 **!** | 11 |
| `js/prose_resolve_targets.js:18293` | `findSurroundingPairTextBased` | moderate | 6 | 8 | 42.0 **!** | 67 |
| `scripts/build-js.ts:101` | `main` | moderate | 5 | 4 | 30.0 **!** | 21 |
| `scripts/sync-to-talon.ts:90` | `<arrow>` | moderate | 5 | 4 | 30.0 **!** | 6 |
| `scripts/sync-to-talon.ts:99` | `<arrow>` | moderate | 5 | 4 | 30.0 **!** | 6 |
| `js/prose_allocate_hats.js:21` | `__toESM` | moderate | 5 | 3 | 30.0 **!** | 8 |
| `js/prose_allocate_hats.js:379` | `apply` | moderate | 5 | 1 | 30.0 **!** | 13 |
| `js/prose_allocate_hats.js:464` | `arrayReduce` | moderate | 5 | 4 | 30.0 **!** | 10 |
| `js/prose_allocate_hats.js:474` | `arrayReduceRight` | moderate | 5 | 4 | 30.0 **!** | 10 |
| `js/prose_allocate_hats.js:510` | `baseFindIndex` | moderate | 5 | 5 | 30.0 **!** | 9 |
| `js/prose_allocate_hats.js:731` | `maskSrcKey` | moderate | 5 | 3 | 30.0 **!** | 4 |
| `js/prose_allocate_hats.js:1104` | `assignMergeValue` | moderate | 5 | 4 | 30.0 **!** | 5 |
| `js/prose_allocate_hats.js:1109` | `assignValue` | moderate | 5 | 4 | 30.0 **!** | 6 |
| `js/prose_allocate_hats.js:1364` | `baseGet` | moderate | 5 | 4 | 30.0 **!** | 8 |
| `js/prose_allocate_hats.js:1376` | `baseGetTag` | moderate | 5 | 5 | 30.0 **!** | 6 |
| `js/prose_allocate_hats.js:1536` | `baseIteratee` | moderate | 5 | 5 | 30.0 **!** | 12 |
| `js/prose_allocate_hats.js:1548` | `baseKeys` | moderate | 5 | 5 | 30.0 **!** | 12 |
| `js/prose_allocate_hats.js:1604` | `<anonymous>` | moderate | 5 | 7 | 30.0 **!** | 12 |
| `js/prose_allocate_hats.js:2075` | `compareMultiple` | moderate | 5 | 9 | 30.0 **!** | 14 |
| `js/prose_allocate_hats.js:2207` | `wrapper` | moderate | 5 | 3 | 30.0 **!** | 4 |
| `js/prose_allocate_hats.js:2422` | `createPadding` | moderate | 5 | 5 | 30.0 **!** | 9 |
| `js/prose_allocate_hats.js:2739` | `getFuncName` | moderate | 5 | 5 | 30.0 **!** | 10 |
| `js/prose_allocate_hats.js:2924` | `isFlattenable` | moderate | 5 | 2 | 30.0 **!** | 3 |
| `js/prose_allocate_hats.js:2952` | `isKeyable` | moderate | 5 | 2 | 30.0 **!** | 4 |
| `js/prose_allocate_hats.js:2956` | `isLaziable` | moderate | 5 | 4 | 30.0 **!** | 11 |
| `js/prose_allocate_hats.js:3125` | `toKey` | moderate | 5 | 4 | 30.0 **!** | 7 |
| `js/prose_allocate_hats.js:3252` | `findIndex` | moderate | 5 | 4 | 30.0 **!** | 11 |
| `js/prose_allocate_hats.js:3263` | `findLastIndex` | moderate | 5 | 5 | 30.0 **!** | 12 |
| `js/prose_allocate_hats.js:3302` | `indexOf` | moderate | 5 | 4 | 30.0 **!** | 11 |
| `js/prose_allocate_hats.js:3330` | `intersectionWith` | moderate | 5 | 4 | 30.0 **!** | 8 |
| `js/prose_allocate_hats.js:3361` | `pullAll` | moderate | 5 | 2 | 30.0 **!** | 3 |
| `js/prose_allocate_hats.js:3364` | `pullAllBy` | moderate | 5 | 2 | 30.0 **!** | 3 |
| `js/prose_allocate_hats.js:3367` | `pullAllWith` | moderate | 5 | 2 | 30.0 **!** | 3 |
| `js/prose_allocate_hats.js:3377` | `remove` | moderate | 5 | 5 | 30.0 **!** | 17 |
| `js/prose_allocate_hats.js:3417` | `sortedIndexOf` | moderate | 5 | 5 | 30.0 **!** | 10 |
| `js/prose_allocate_hats.js:3880` | `shouldInvoke` | moderate | 5 | 2 | 30.0 **!** | 4 |
| `js/prose_allocate_hats.js:3909` | `debounced` | moderate | 5 | 6 | 30.0 **!** | 20 |
| `js/prose_allocate_hats.js:3942` | `memoize2` | moderate | 5 | 4 | 30.0 **!** | 16 |
| `js/prose_allocate_hats.js:3963` | `<anonymous>` | moderate | 5 | 1 | 30.0 **!** | 14 |
| `js/prose_allocate_hats.js:4023` | `throttle` | moderate | 5 | 6 | 30.0 **!** | 15 |
| `js/prose_allocate_hats.js:4135` | `isFunction` | moderate | 5 | 2 | 30.0 **!** | 7 |
| `js/prose_allocate_hats.js:4275` | `assign` | moderate | 5 | 5 | 30.0 **!** | 11 |
| `js/prose_allocate_hats.js:4624` | `parseInt2` | moderate | 5 | 4 | 30.0 **!** | 8 |
| `js/prose_allocate_hats.js:4687` | `<anonymous>` | moderate | 5 | 4 | 30.0 **!** | 17 |
| `js/prose_allocate_hats.js:4816` | `words` | moderate | 5 | 5 | 30.0 **!** | 8 |
| `js/prose_allocate_hats.js:5427` | `<anonymous>` | moderate | 5 | 5 | 30.0 **!** | 28 |
| `js/prose_allocate_hats.js:5793` | `<anonymous>` | moderate | 5 | 4 | 30.0 **!** | 11 |
| `js/prose_allocate_hats.js:6191` | `resolveYamlBinary` | moderate | 5 | 6 | 30.0 **!** | 14 |
| `js/prose_allocate_hats.js:6305` | `resolveYamlPairs` | moderate | 5 | 6 | 30.0 **!** | 16 |
| `js/prose_allocate_hats.js:6339` | `resolveYamlSet` | moderate | 5 | 7 | 30.0 **!** | 12 |
| `js/prose_allocate_hats.js:6396` | `is_FLOW_INDICATOR` | moderate | 5 | 1 | 30.0 **!** | 3 |
| `js/prose_allocate_hats.js:6399` | `fromHexCode` | moderate | 5 | 4 | 30.0 **!** | 11 |
| `js/prose_allocate_hats.js:7655` | `indentString` | moderate | 5 | 7 | 30.0 **!** | 17 |
| `js/prose_allocate_hats.js:8148` | `dump$1` | moderate | 5 | 4 | 30.0 **!** | 13 |
| `js/prose_allocate_hats.js:8184` | `<anonymous>` | moderate | 5 | 2 | 30.0 **!** | 3 |
| `js/prose_allocate_hats.js:8438` | `<anonymous>` | moderate | 5 | 11 | 30.0 **!** | 16 |
| `js/prose_allocate_hats.js:8612` | `rgbToHex` | moderate | 5 | 2 | 30.0 **!** | 7 |
| `js/prose_allocate_hats.js:8767` | `<anonymous>` | moderate | 5 | 1 | 30.0 **!** | 19 |
| `js/prose_allocate_hats.js:12248` | `<arrow>` | moderate | 5 | 2 | 30.0 **!** | 1 |
| `js/prose_allocate_hats.js:12563` | `rankPreTokenizedInput` | moderate | 5 | 3 | 30.0 **!** | 25 |
| `js/prose_allocate_hats.js:12696` | `getTokenRemainingHatCandidates` | moderate | 5 | 4 | 30.0 **!** | 14 |
| `js/prose_allocate_hats.js:2` | `<arrow>` | moderate | 5 | 5 | 30.0 **!** | 12777 |
| `js/prose_resolve_targets.js:21` | `__toESM` | moderate | 5 | 3 | 30.0 **!** | 8 |
| `js/prose_resolve_targets.js:379` | `apply` | moderate | 5 | 1 | 30.0 **!** | 13 |
| `js/prose_resolve_targets.js:464` | `arrayReduce` | moderate | 5 | 4 | 30.0 **!** | 10 |
| `js/prose_resolve_targets.js:474` | `arrayReduceRight` | moderate | 5 | 4 | 30.0 **!** | 10 |
| `js/prose_resolve_targets.js:510` | `baseFindIndex` | moderate | 5 | 5 | 30.0 **!** | 9 |
| `js/prose_resolve_targets.js:731` | `maskSrcKey` | moderate | 5 | 3 | 30.0 **!** | 4 |
| `js/prose_resolve_targets.js:1104` | `assignMergeValue` | moderate | 5 | 4 | 30.0 **!** | 5 |
| `js/prose_resolve_targets.js:1109` | `assignValue` | moderate | 5 | 4 | 30.0 **!** | 6 |
| `js/prose_resolve_targets.js:1364` | `baseGet` | moderate | 5 | 4 | 30.0 **!** | 8 |
| `js/prose_resolve_targets.js:1376` | `baseGetTag` | moderate | 5 | 5 | 30.0 **!** | 6 |
| `js/prose_resolve_targets.js:1536` | `baseIteratee` | moderate | 5 | 5 | 30.0 **!** | 12 |
| `js/prose_resolve_targets.js:1548` | `baseKeys` | moderate | 5 | 5 | 30.0 **!** | 12 |
| `js/prose_resolve_targets.js:1604` | `<anonymous>` | moderate | 5 | 7 | 30.0 **!** | 12 |
| `js/prose_resolve_targets.js:2075` | `compareMultiple` | moderate | 5 | 9 | 30.0 **!** | 14 |
| `js/prose_resolve_targets.js:2207` | `wrapper` | moderate | 5 | 3 | 30.0 **!** | 4 |
| `js/prose_resolve_targets.js:2422` | `createPadding` | moderate | 5 | 5 | 30.0 **!** | 9 |
| `js/prose_resolve_targets.js:2739` | `getFuncName` | moderate | 5 | 5 | 30.0 **!** | 10 |
| `js/prose_resolve_targets.js:2924` | `isFlattenable` | moderate | 5 | 2 | 30.0 **!** | 3 |
| `js/prose_resolve_targets.js:2952` | `isKeyable` | moderate | 5 | 2 | 30.0 **!** | 4 |
| `js/prose_resolve_targets.js:2956` | `isLaziable` | moderate | 5 | 4 | 30.0 **!** | 11 |
| `js/prose_resolve_targets.js:3125` | `toKey` | moderate | 5 | 4 | 30.0 **!** | 7 |
| `js/prose_resolve_targets.js:3252` | `findIndex` | moderate | 5 | 4 | 30.0 **!** | 11 |
| `js/prose_resolve_targets.js:3263` | `findLastIndex2` | moderate | 5 | 5 | 30.0 **!** | 12 |
| `js/prose_resolve_targets.js:3302` | `indexOf` | moderate | 5 | 4 | 30.0 **!** | 11 |
| `js/prose_resolve_targets.js:3330` | `intersectionWith` | moderate | 5 | 4 | 30.0 **!** | 8 |
| `js/prose_resolve_targets.js:3361` | `pullAll` | moderate | 5 | 2 | 30.0 **!** | 3 |
| `js/prose_resolve_targets.js:3364` | `pullAllBy` | moderate | 5 | 2 | 30.0 **!** | 3 |
| `js/prose_resolve_targets.js:3367` | `pullAllWith` | moderate | 5 | 2 | 30.0 **!** | 3 |
| `js/prose_resolve_targets.js:3377` | `remove` | moderate | 5 | 5 | 30.0 **!** | 17 |
| `js/prose_resolve_targets.js:3417` | `sortedIndexOf` | moderate | 5 | 5 | 30.0 **!** | 10 |
| `js/prose_resolve_targets.js:3880` | `shouldInvoke` | moderate | 5 | 2 | 30.0 **!** | 4 |
| `js/prose_resolve_targets.js:3909` | `debounced` | moderate | 5 | 6 | 30.0 **!** | 20 |
| `js/prose_resolve_targets.js:3942` | `memoize` | moderate | 5 | 4 | 30.0 **!** | 16 |
| `js/prose_resolve_targets.js:3963` | `<anonymous>` | moderate | 5 | 1 | 30.0 **!** | 14 |
| `js/prose_resolve_targets.js:4023` | `throttle` | moderate | 5 | 6 | 30.0 **!** | 15 |
| `js/prose_resolve_targets.js:4135` | `isFunction` | moderate | 5 | 2 | 30.0 **!** | 7 |
| `js/prose_resolve_targets.js:4275` | `assign` | moderate | 5 | 5 | 30.0 **!** | 11 |
| `js/prose_resolve_targets.js:4624` | `parseInt2` | moderate | 5 | 4 | 30.0 **!** | 8 |
| `js/prose_resolve_targets.js:4687` | `<anonymous>` | moderate | 5 | 4 | 30.0 **!** | 17 |
| `js/prose_resolve_targets.js:4816` | `words` | moderate | 5 | 5 | 30.0 **!** | 8 |
| `js/prose_resolve_targets.js:5427` | `<anonymous>` | moderate | 5 | 5 | 30.0 **!** | 28 |
| `js/prose_resolve_targets.js:5692` | `<anonymous>` | moderate | 5 | 4 | 30.0 **!** | 12 |
| `js/prose_resolve_targets.js:5716` | `<anonymous>` | moderate | 5 | 4 | 30.0 **!** | 10 |
| `js/prose_resolve_targets.js:5892` | `<anonymous>` | moderate | 5 | 4 | 30.0 **!** | 10 |
| `js/prose_resolve_targets.js:6257` | `<anonymous>` | moderate | 5 | 4 | 30.0 **!** | 11 |
| `js/prose_resolve_targets.js:6655` | `resolveYamlBinary` | moderate | 5 | 6 | 30.0 **!** | 14 |
| `js/prose_resolve_targets.js:6769` | `resolveYamlPairs` | moderate | 5 | 6 | 30.0 **!** | 16 |
| `js/prose_resolve_targets.js:6803` | `resolveYamlSet` | moderate | 5 | 7 | 30.0 **!** | 12 |
| `js/prose_resolve_targets.js:6860` | `is_FLOW_INDICATOR` | moderate | 5 | 1 | 30.0 **!** | 3 |
| `js/prose_resolve_targets.js:6863` | `fromHexCode` | moderate | 5 | 4 | 30.0 **!** | 11 |
| `js/prose_resolve_targets.js:8119` | `indentString` | moderate | 5 | 7 | 30.0 **!** | 17 |
| `js/prose_resolve_targets.js:8612` | `dump$1` | moderate | 5 | 4 | 30.0 **!** | 13 |
| `js/prose_resolve_targets.js:8648` | `<anonymous>` | moderate | 5 | 2 | 30.0 **!** | 3 |
| `js/prose_resolve_targets.js:8902` | `<anonymous>` | moderate | 5 | 11 | 30.0 **!** | 16 |
| `js/prose_resolve_targets.js:9076` | `rgbToHex` | moderate | 5 | 2 | 30.0 **!** | 7 |
| `js/prose_resolve_targets.js:9231` | `<anonymous>` | moderate | 5 | 1 | 30.0 **!** | 19 |
| `js/prose_resolve_targets.js:12691` | `uniqWithHash` | moderate | 5 | 5 | 30.0 **!** | 44 |
| `js/prose_resolve_targets.js:12832` | `getEditNewActionType` | moderate | 5 | 2 | 30.0 **!** | 6 |
| `js/prose_resolve_targets.js:14638` | `segment` | moderate | 5 | 10 | 30.0 **!** | 16 |
| `js/prose_resolve_targets.js:15044` | `processTarget` | moderate | 5 | 1 | 30.0 **!** | 13 |
| `js/prose_resolve_targets.js:15061` | `<arrow>` | moderate | 5 | 3 | 30.0 **!** | 22 |
| `js/prose_resolve_targets.js:15198` | `targetsToContinuousTarget` | moderate | 5 | 4 | 30.0 **!** | 15 |
| `js/prose_resolve_targets.js:15355` | `constructScopeRangeTarget` | moderate | 5 | 4 | 30.0 **!** | 19 |
| `js/prose_resolve_targets.js:15721` | `<arrow>` | moderate | 5 | 6 | 30.0 **!** | 15 |
| `js/prose_resolve_targets.js:15870` | `<arrow>` | moderate | 5 | 6 | 30.0 **!** | 17 |
| `js/prose_resolve_targets.js:16137` | `<anonymous>` | moderate | 5 | 8 | 30.0 **!** | 31 |
| `js/prose_resolve_targets.js:16190` | `<anonymous>` | moderate | 5 | 8 | 30.0 **!** | 31 |
| `js/prose_resolve_targets.js:16434` | `<arrow>` | moderate | 5 | 4 | 30.0 **!** | 16 |
| `js/prose_resolve_targets.js:17628` | `<arrow>` | moderate | 5 | 4 | 30.0 **!** | 11 |
| `js/prose_resolve_targets.js:17853` | `<arrow>` | moderate | 5 | 4 | 30.0 **!** | 13 |
| `js/prose_resolve_targets.js:18050` | `getDirections` | moderate | 5 | 2 | 30.0 **!** | 13 |
| `js/prose_resolve_targets.js:18189` | `<arrow>` | moderate | 5 | 5 | 30.0 **!** | 11 |
| `js/prose_resolve_targets.js:18387` | `delimiterInfo` | moderate | 5 | 3 | 30.0 **!** | 17 |
| `js/prose_resolve_targets.js:18419` | `inferDelimiterSide2` | moderate | 5 | 4 | 30.0 **!** | 11 |
| `js/prose_resolve_targets.js:18519` | `nodeHasError` | moderate | 5 | 5 | 30.0 **!** | 14 |
| `js/prose_resolve_targets.js:18752` | `getSingleTarget` | moderate | 5 | 3 | 30.0 **!** | 20 |
| `js/prose_resolve_targets.js:18789` | `getInsertionDelimiter3` | moderate | 5 | 4 | 30.0 **!** | 3 |
| `js/prose_resolve_targets.js:18808` | `leadingDelimiterRange` | moderate | 5 | 2 | 30.0 **!** | 9 |
| `js/prose_resolve_targets.js:18817` | `trailingDelimiterRange` | moderate | 5 | 2 | 30.0 **!** | 9 |
| `js/prose_resolve_targets.js:19109` | `run` | moderate | 5 | 4 | 30.0 **!** | 24 |
| `js/prose_resolve_targets.js:19134` | `generateScopesInclusive` | moderate | 5 | 3 | 30.0 **!** | 24 |
| `js/prose_resolve_targets.js:19360` | `getLegacyScopeStage` | moderate | 5 | 1 | 30.0 **!** | 24 |

**6** files, **2849** functions analyzed (thresholds: cyclomatic > 20, cognitive > 15, CRAP >= 30.0)

### File Health Scores (6 files)

| File | Maintainability | Fan-in | Fan-out | Dead Code | Density | Risk |
|:-----|:---------------|:-------|:--------|:----------|:--------|:-----|
| `js/prose_allocate_hats.js` | 71.0 | 0 | 0 | 100% | 0.30 | 3782.0 |
| `js/prose_resolve_targets.js` | 71.9 | 0 | 0 | 100% | 0.27 | 3782.0 |
| `js/prose_actions.js` | 72.2 | 0 | 0 | 100% | 0.26 | 156.0 |
| `scripts/sync-to-talon.ts` | 72.8 | 0 | 0 | 100% | 0.24 | 90.0 |
| `scripts/build-js.ts` | 77.0 | 0 | 0 | 100% | 0.10 | 30.0 |
| `scripts/gen-command-table.ts` | 77.0 | 0 | 0 | 100% | 0.10 | 12.0 |

**Average maintainability index:** 73.7/100

### Hotspots (1 files, since 6 months)

| File | Score | Commits | Churn | Density | Fan-in | Trend |
|:-----|:------|:--------|:------|:--------|:-------|:------|
| `scripts/sync-to-talon.ts` | 100.0 | 3 | 112 | 0.24 | 0 | accelerating |

*5 files excluded (< 3 commits)*

### Refactoring Targets (2)

| Efficiency | Category | Effort / Confidence | File | Recommendation |
|:-----------|:---------|:--------------------|:-----|:---------------|
| 9.7 | complexity | high / high | `js/prose_allocate_hats.js` | Extract simpleEscapeSequence (cognitive: 171) and composeNode (cognitive: 109) in 12794-LOC file into smaller functions |
| 9.4 | dead code | high / high | `js/prose_resolve_targets.js` | Remove 16 unused exports to reduce surface area (100% dead) |

---

<details><summary>Metric definitions</summary>

- **MI**: Maintainability Index (0–100, higher is better)
- **Order**: risk-aware triage order using the larger of low-MI concern and CRAP risk
- **Fan-in**: files that import this file (blast radius)
- **Fan-out**: files this file imports (coupling)
- **Dead Code**: % of value exports with zero references
- **Density**: cyclomatic complexity / lines of code
- **Risk**: max CRAP score for the file; low <15, moderate 15-30, high >=30
- **Score**: churn × complexity (0–100, higher = riskier)
- **Commits**: commits in the analysis window
- **Churn**: total lines added + deleted
- **Trend**: accelerating / stable / cooling
- **Efficiency**: priority / effort (higher = better quick-win value, default sort)
- **Category**: recommendation type (churn+complexity, high impact, dead code, complexity, coupling, circular dep)
- **Effort**: estimated effort (low / medium / high) based on file size, function count, and fan-in
- **Confidence**: recommendation reliability (high = deterministic analysis, medium = heuristic, low = git-dependent)

[Full metric reference](https://docs.fallow.tools/explanations/metrics)

</details>


Failed: dead-code (6 issues), dupes (1 clone groups), health (510 above threshold): start with js/prose_allocate_hats.js
Setup: `fallow init --agents` writes an agent guide; `fallow hooks install --target agent` adds a commit gate (hide this hint: `fallow init --decline`).
