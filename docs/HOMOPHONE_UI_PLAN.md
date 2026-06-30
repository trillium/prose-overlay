# Homophone UI — Exploration Plan

> Source research: [`HOMOPHONE_UI.md`](./HOMOPHONE_UI.md). Coordinates with [`UNDO_REDO_PLAN.md`](./UNDO_REDO_PLAN.md) and [`VIEWPORT_RESEARCH.md`](./VIEWPORT_RESEARCH.md).
> Drafted 2026-06-30.
>
> **This is an exploration plan, not a ship plan.** Each slice is a reversible experiment with an explicit kill criterion. We are looking for cheap evidence about *what the eye and the voice actually want* before paying for the data structure, the trigram model, or the Cursorless scope work the research doc proposes.

## 1. TL;DR

- We'd start with **Slice A: a static homophone underline** — read the pimentel CSV at startup, paint a 1 px dotted underline under any token whose lowercase appears in it. No confidence model, no chip, no swap action.
- The learning goal of Slice A is binary and cheap: **does the always-on indicator feel like signal or like noise?** That answer alone changes the entire downstream plan.
- Slice B adds `phone <hat>` as a swap action (cycle through the homophone group). No chip yet. Learns: is the swap discoverable without a visible alt list?
- Slice C adds the inline ghost chip (`→their²·there³`) once we know the swap is wanted. Learns: does seeing the alternates change which homophones the user notices?
- Slice D adds the trigram-confidence model — only if A/B/C established that the *indicator's precision* (not its presence) is the next bottleneck.
- Each slice is one commit, one feature flag, one `git revert` to undo. Nothing under Slice A locks the API for B/C/D.
- Foundational dodges in §4: keep the wordlist behind a loader function, the flag state off `ProseBuffer`, the underline on a separate decoration pass, and the voice grammar untyped until §B forces the choice.

## 2. Decision-tree shape

```
A — static-flag dotted underline only
    (no chip, no swap, no model, just "this token is in the CSV")
  └─ FEELS like signal              → B
  └─ FEELS like wallpaper / noise   → stop. We learned indicator placement isn't the problem;
                                       the problem is recall, not perception. Revisit with the
                                       modal HUD or audio cue instead.

B — `phone <hat>` cycle action (no chip)
    (reuses A's flag set; cycles to next group member; STRUCTURAL undo step)
  └─ Discoverable enough            → C optional
  └─ User can't remember alternates → ship A+B and stop; or jump to C

C — inline ghost chip (`→their²·there³`)
    (renders only when cursor is near a flagged token — Indicator E gate)
  └─ Improves swap accuracy / speed → consider D
  └─ Cluttered, distracting         → revert C; keep A+B

D — trigram confidence model
    (precomputed lookup; modulates underline opacity)
  └─ Improves precision (fewer false flags)  → keep
  └─ Adds perceived lag, no measurable gain  → fall back to "always-on at fixed opacity"

(E, F, G from research doc — peripheral strip, density-underline, audible chirp —
 are not in the tree. They unlock only if A-D produces an unambiguous "wrong primitive"
 verdict that would justify a different shape.)
```

Each slice lives behind its own setting (§3 per-slice spec). Reverting B does not touch A. Reverting D does not touch C. The flag *set* (the `set[str]` of CSV words) is the only shared substrate, and it ships with A — every later slice reads it, none mutates its shape.

## 3. Per-slice spec

### Slice A — static-flag dotted underline

**Goal.** Learn whether an always-on, sub-syntactic visual marker on homophone tokens reads as useful signal during normal dictation flow, or as ambient noise the eye filters out.

**Files touched** (rough LOC):
- **new** `prose_overlay_homophones.py` (~40 LOC) — module owns the flag set. Loads `homophones.csv` once at import (from the existing trillium_talon path, read-only, cite the path). Exposes `is_flagged(token: str) -> bool` and `flagged_indices(tokens: list[str]) -> set[int]`. **No state, no class, no buffer coupling.**
- `prose_overlay_draw_tokens.py` (~+15 LOC) — inside `_draw_token_rows`, after the token text is drawn, if `idx in flagged_indices` and the flag is enabled, paint a 1 px dotted underline at `y_base + DOT_RADIUS*2 + DOT_GAP_Y + TOKEN_FONT_SIZE + 1`. The flagged-index set is passed in as an argument — *not* read from a module global, *not* read from `ProseBuffer`.
- `prose_overlay_draw.py` (~+8 LOC) — compute `flagged = homophone_module.flagged_indices(tokens) if settings.get("user.prose_overlay_homophone_hint") else frozenset()` once, pass to `_draw_token_rows`.
- `prose_overlay.py` (~+6 LOC) — `mod.setting("prose_overlay_homophone_hint", type=bool, default=False, ...)`.
- `prose_overlay_draw_constants.py` (~+2 LOC) — `HOMOPHONE_UNDERLINE_COLOR = "8899aa66"` (low-sat, ~40% alpha).

Total: ~70 LOC across 5 files, one new module.

**Feature flag.** `user.prose_overlay_homophone_hint` (bool, default `False`). Off by default so the experiment is opt-in even after merge. Toggle live via Talon settings file or a v0 voice command (`overlay hints homo on` — see Voice surface).

**Voice surface (Slice A only).**
```talon
overlay hints homo on:  user.prose_overlay_set_homophone_hint(1)
overlay hints homo off: user.prose_overlay_set_homophone_hint(0)
```
Two literal toggles. No grammar for `phone` yet — that's Slice B.

**Keep criterion.** After ~3 sessions of normal dictation with the flag on, the user reports catching at least one wrong-homophone he'd otherwise have missed, *and* doesn't ask to turn it off mid-session because of distraction.

**Kill criterion.** User asks "can you make this stop" within the first session, or after 3 sessions reports neither catching extras nor noticing the underline at all (the latter means the visual is too weak to be useful and too weak to be irritating — i.e., dead pixels, the worst outcome because we still paid the render cost).

**Reversibility.** `git revert <slice-A-sha>` removes one new file, one setting, ~30 LOC of draw additions. Zero schema change to `ProseBuffer`. Zero new voice grammar in Cursorless space. Zero coupling to undo/redo, viewport, or hat allocator. The flag set is `frozenset[str]` built once, immutable, no migrations.

**Non-goals.**
- No confidence (every flagged token paints at the same opacity).
- No swap action.
- No chip.
- No interaction with Cursorless hats or scopes.
- No phonetic-fallback (Double Metaphone) — pimentel CSV literal-membership only.
- No focus-aware reveal (Indicator E) — always-on at fixed opacity. The "always vs. on-focus" tradeoff is itself something to learn, but A defers to the simpler always-on so the noise question is unambiguous.

---

### Slice B — `phone <hat>` cycle swap

**Goal.** Learn whether voice users can swap a flagged homophone without first being told what the alternates are. Tests the hypothesis that "user spots flag, asks editor to cycle, glances at result" is a viable loop without any HUD.

**Files touched** (rough LOC):
- **new** `prose_overlay_actions_homophones.py` (~50 LOC) — `prose_overlay_phone_hat(letter, color="gray")`. Resolves the hat to a token index (reuse `_hat_to_index` from `prose_overlay_actions_core`), looks up the group via the loader from Slice A, picks the next group member (`group_for_word(token)[(i+1) % len(group)]`), brackets in `commit_start("phone", STRUCTURAL)` / `commit_end()` (the bracket API from `UNDO_REDO_PLAN.md` Phase 2) and calls `buffer.replace_token(idx, new)`. If the undo Phase 2 bracket isn't landed yet, fall back to the existing `instance.buffer.snapshot()` + direct replace — identical sealing semantics.
- `prose_overlay_homophones.py` (~+15 LOC) — add `group_for_word(token: str) -> tuple[str, ...] | None`. Sibling to `is_flagged`, same load path.
- `prose_overlay_cursorless.talon` (~+6 LOC) — append the grammar:
  ```talon
  phone <user.letter>:                              user.prose_overlay_phone_hat(letter)
  phone <user.prose_hat_color> <user.letter>:       user.prose_overlay_phone_hat(letter, prose_hat_color)
  ```
  Mirrors the shape of `chuck <user.letter>` exactly (same letter + optional color prefix capture) — keeps the user's existing hat grammar intuition intact.

Total: ~70 LOC, one new module, no schema change.

**Feature flag.** `user.prose_overlay_homophone_swap` (bool, default `False`). Independent of `prose_overlay_homophone_hint` — you can have indicators without the swap, or the swap without indicators (useful for users who memorize their typical mistakes and want the action without the visual). The `phone` grammar is registered unconditionally, but the action body short-circuits with a `app.notify` if the flag is off, so the voice surface doesn't change with the flag.

**Voice surface (Slice B adds).**
```talon
phone <user.letter>
phone <user.prose_hat_color> <user.letter>
```

**Keep criterion.** User uses `phone <hat>` at least once per session unprompted after Slice A's underline tipped him off, and the cycle picks the right alternate ≥50% of the time on his real dictation (small groups: `their/there/they're` cycles right 1-in-2 by random; `to/too/two` 1-in-2; better-than-coinflip on his prose).

**Kill criterion.** Cycle picks wrong word >75% of the time *and* user reports the failed-cycle + undo + retry loop costs more friction than typing the fix. Indicates we need either Slice C (chip to pick a target by name) or Slice D (confidence model to pick smarter), so we'd stop here and re-decide which to try.

**Reversibility.** `git revert <slice-B-sha>` removes one new file, one setting, 6 talon lines, ~15 LOC in the homophone module. Slice A unaffected. **The grammar choice (`phone` not `phones` not `homo`) is load-bearing for revert cleanliness** — see §4 risk.

**Non-goals.**
- No "phone bat as <word>" form (that's the variant for Slice C).
- No bulk operation (`phones every line`).
- No dismissal / ignore.
- No TTS confirmation.
- No re-render of the swapped token in a different color to "confirm change" — undo gives that feedback if needed.

---

### Slice C — inline ghost chip

**Goal.** Learn whether seeing the alternate set in-context changes the *which* (which homophones the user fixes), not just the *whether*. The hypothesis worth testing: a chip on focus is the difference between "I see a flag, I don't know what's wrong" and "I see the choices, I know what I meant."

**Files touched** (rough LOC):
- **new** `prose_overlay_draw_homophones.py` (~80 LOC) — separate draw module so the chip lives in its own decoration pass. Exposes `draw_homophone_chips(c, rows, x_origin, y_base, flagged_indices, cursor, tokens)`. Renders to the right of EOL for any row containing a flagged token within N=3 tokens of the cursor. Layout: faint background, `→` arrow, group members joined with `·`, superscript ordinals.
- `prose_overlay_draw.py` (~+5 LOC) — call `draw_homophone_chips` after `_draw_token_rows` if `settings.get("user.prose_overlay_homophone_chip")`.
- `prose_overlay.py` (~+6 LOC) — `mod.setting("prose_overlay_homophone_chip", type=bool, default=False, ...)`.
- *Maybe* `prose_overlay_actions_homophones.py` (~+15 LOC) — add `prose_overlay_phone_hat_as(letter, word_capture, color="gray")` so the chip ordinals are addressable: `phone bat as write`. Or defer to Slice C.1 if the chip alone is enough.

Total: ~100 LOC plus optional ~15 LOC for `as`-form. One new draw module.

**Feature flag.** `user.prose_overlay_homophone_chip` (bool, default `False`). Independent of A and B.

**Voice surface (Slice C optionally adds).**
```talon
phone <user.letter> as <user.word>:                          user.prose_overlay_phone_hat_as(letter, word)
phone <user.prose_hat_color> <user.letter> as <user.word>:   user.prose_overlay_phone_hat_as(letter, word, prose_hat_color)
```

**Keep criterion.** Chip visible during ≥3 sessions, user reports it's read more than ignored, and the swap-accuracy from Slice B improves (because the user can pick from the chip via the `as` form rather than guessing what the cycle will land on).

**Kill criterion.** Chip judged "noisy" or "in the way" within first session of toggle-on, OR EOL chip layout collides with existing line-trailing content (the help-zone separator at 80% width, the target label) in a way that's not cheaply fixable.

**Reversibility.** `git revert <slice-C-sha>` removes one new draw module, one setting, ~5 LOC in `draw_overlay`, plus the optional grammar. Slices A and B untouched. The chip module is purely additive; nothing else reads from it.

**Non-goals.**
- No peripheral strip (Indicator D).
- No glyph-density encoding (Indicator F).
- No "speak the alternates" TTS variant.
- No persistence of "I dismissed this chip" — chip visibility is purely a function of `cursor proximity` and the flag.

---

### Slice D — trigram confidence model

**Goal.** Learn whether a local n-gram score over `(prev, candidate, next)` reduces the false-flag rate enough to be worth the lookup-table memory and the per-edit re-score cost. Tests the "always-on but graded by certainty" hypothesis from research §A and §E.

**Files touched** (rough LOC):
- **new** `prose_overlay_homophone_model.py` (~120 LOC) — module owns the precomputed lookup table (`dict[tuple[str, str, str], float]`) loaded lazily on first `score()` call. Exposes `confidence(prev: str, current: str, next: str, group: tuple[str, ...]) -> float`. Falls back to `1.0` for OOV context (treat as "we don't know, don't fade").
- **new** `data/homophone_trigrams.pkl.gz` (~5-20 MB after pruning, per research §6 OQ3) or `data/homophone_trigrams.bin` — checked into repo if under 10 MB, otherwise built on first run.
- `prose_overlay_homophones.py` (~+25 LOC) — add `flagged_indices_with_confidence(tokens) -> dict[int, float]`. Same data, plus per-flag confidence.
- `prose_overlay_draw_tokens.py` (~+10 LOC) — underline alpha scales with `1.0 - confidence` (capped at min 0x30 alpha so even high-confidence flags are still visible at all).

Total: ~155 LOC, one new module, one new data file (or build step), no API change to slices A/B/C.

**Feature flag.** `user.prose_overlay_homophone_confidence` (bool, default `False`). Off → underline alpha is fixed (Slice A behavior). On → alpha = `f(confidence)`. The model loads lazily on first scored flag so the cost is paid only by users who opt in.

**Voice surface.** None. This slice only changes how the indicator from Slice A is rendered.

**Keep criterion.** False-flag rate (homophones underlined when the user's choice was correct) measurably drops by 50%+, and lookup-table load doesn't push overlay startup past 100 ms.

**Kill criterion.** Model takes >50 ms per edit to re-score visible flags (blows the latency budget), OR table is too coarse to distinguish `their car` (0.95) from `their is a problem` (0.05), so confidence is uniformly ~0.5 and the indicator collapses to "always-on at half-alpha" — in which case fixed-alpha (Slice A) wins by being simpler.

**Reversibility.** `git revert <slice-D-sha>` removes one module, one (or two) data files, ~35 LOC across `homophones.py` and `draw_tokens.py`. Slices A/B/C unaffected because they pass `flagged_indices: set[int]` (set membership only) — Slice D adds a *new* call site for the confidence variant rather than changing the existing one.

**Non-goals.**
- No neural LM. Research §3 explicitly defers a quantized Gemma to v2; we agree.
- No GloVe cosine fallback (research §3 mentions it as v1.5; we'd add only if D's trigram approach proves the model layer is worth keeping but its specific algorithm is wrong).
- No per-doc training. The table is precomputed at build time from Google Books Ngrams, frozen, shipped.

## 4. Foundational risks to dodge

These are the choices that, if made wrong in Slice A, would make B/C/D expensive to undo. For each: name the risk + name the cheap dodge.

### 4.1 Flag-state location (schema lock-in) — HIGH RISK

**Risk.** Putting the homophone flag set on `ProseBuffer` (e.g., `self._homophone_flags: set[int]`) marries the experiment to the buffer's lifecycle, forces invalidation on every `rev` bump, and creates a coupling that's hard to undo. Worse: it sets precedent for "every decoration the editor invents lives on ProseBuffer", which is the wrong factoring.

**Dodge.** Flag state lives in a **separate module** (`prose_overlay_homophones.py`) as a pure function from the current `tokens: list[str]` to `frozenset[int]`. Computed once per draw, never stored. `ProseBuffer` stays homophone-unaware. Slice D's confidence variant follows the same shape (`flagged_indices_with_confidence(tokens, rev)` — `rev` only as a memoization key, not as state).

The `buffer.rev` counter from `prose_overlay_state.py:117` is the **right cache key** if memoization becomes necessary in Slice D — it already exists, it already bumps on every mutation, and no new state has to be invented.

### 4.2 Voice grammar choice (`phone` vs `phones` vs `homo`) — MEDIUM RISK

**Risk.** `phones <hat>` is already taken by the existing modal HUD at `trillium_talon/core/homophones/homophones.py`. `phones` (plural) is also the natural for bulk ("phones every line"). If Slice B uses `phones <hat>` for the singular swap, Slice C's bulk grammar has nowhere to land except a confusing reuse, and we may end up renaming Slice B's grammar mid-experiment — breaking user muscle memory.

**Dodge.** **Reserve the singular `phone` for per-hat swap (Slice B) and the plural `phones` for the future bulk surface (post-C).** Document this on Slice B's commit. Do NOT touch the existing `phones <word>` modal HUD grammar — it lives in another module entirely and is the user's known-good fallback. If `phone <hat>` collides with anything in the parent Talon config (audit before commit: `rg '^phone\s' ~/.talon`), pick `phony <hat>` as the backup (per BlueDrink9's homophoner-talon precedent cited in research §5a).

### 4.3 Render-layer coupling — MEDIUM RISK

**Risk.** Mixing the homophone underline into `_draw_token_rows` (the per-token rendering inner loop) creates an inner-loop dependency on `flagged_indices`. If Slice C adds a chip, or Slice D adds confidence, the inner loop grows additional parameters and the function becomes the kitchen sink.

**Dodge.** Slice A's underline lives in the inner loop **only** because it's per-token and trivial. Slice C's chip lives in a **separate draw pass** (`prose_overlay_draw_homophones.py` with its own `draw_homophone_chips` entry point — see Slice C spec) called from `draw_overlay` after `_draw_token_rows`. Slice D modulates an alpha; it does not add a new draw call. If Slice A's underline ever needs to also know confidence, it reads from a `dict[int, float]` passed in alongside `flagged_indices` — the function signature gets one optional argument, not a refactor.

This mirrors research §5e — Grammarly's separate-overlay-layer pattern, justified there for DOM constraints, justified here for revert cleanliness.

### 4.4 Wordlist storage — LOW RISK

**Risk.** Reading the CSV at every draw call is wasteful. Embedding it as a Python literal in the module makes the file 600+ lines of data. Building a precompiled `.pkl` adds a build step.

**Dodge.** Read the CSV **once at module import**, build the `frozenset[str]` and `dict[str, tuple[str, ...]]` in module globals. Total cost: ~10 ms at startup, ~50 KB resident. The CSV path is `~/.talon/user/trillium_talon/core/homophones/homophones.csv` — **read it, don't copy it.** Reading the external file means the user's own additions to that CSV automatically benefit the overlay; copying would silently diverge. Cite the path in the module docstring as the source of truth.

If the read fails (file missing on a machine without trillium_talon), the module exports an empty frozenset and `is_flagged` returns False for everything — the feature degrades to off, the overlay still draws normally.

### 4.5 Cursorless scope reservation (the research doc's Indicator C) — DON'T DO IT YET

**Risk.** Research §C proposes reserving a hat shape (`frame`) for homophone-flagged tokens. **This is the single most expensive lock-in in the whole proposal** — it changes the entire editor's visual vocabulary, repartitions the hat allocator's space, and is non-trivial to revert because users will have built muscle memory around `phone frame`.

**Dodge.** Defer indefinitely. The decision tree A → B → C → D **does not require** this. The underline (A) and chip (C) are decoration layers that don't touch the hat allocator. The swap action (B) uses the existing hat grammar (`phone <user.letter>`), not a reserved shape. Indicator C from the research doc enters the conversation only if A through D fail to deliver readable signal AND the user explicitly asks for "I want a dedicated hat for this." That's a separate slice with its own RFC, not a step on this plan.

## 5. Integration touchpoints with in-flight work

### Undo/redo (`docs/UNDO_REDO_PLAN.md`)

- Slice B's swap action is **exactly the STRUCTURAL boundary case** the undo plan calls out: one utterance → one undo step → exactly two tokens differ (`old_word` → `new_word`). Implement Slice B's body as:
  ```python
  instance.buffer.commit_start(label="phone", kind=EditKind.STRUCTURAL)
  instance.buffer.replace_token(idx, new_word)
  instance.buffer.commit_end()
  ```
  Phase 2 of the undo plan. If Phase 2 hasn't landed when Slice B is built, use the existing `snapshot()` + `replace_token()` shim — it pre-seals correctly today, just without the explicit `label`. The label becomes load-bearing only if `overlay undo what` ever ships (Phase 3 polish in the undo plan).
- Slice C's chip and Slice D's confidence don't touch undo at all — they're read-only over `buffer.get_tokens()`.

### Viewport (`prose_overlay_viewport.py`)

- Slice A's underline rides on top of the existing flow layout and is automatically clipped by whatever the viewport does — no change needed.
- Slice C's chip needs to know when the row it would attach to is scrolled out of view (`viewport._scroll_offset`). The chip module reads `instance.viewport.get_scroll_offset()` and the row layout in `viewport._last_rows`; if the flagged row isn't in the visible slice, the chip doesn't render. No new viewport API needed. (If the viewport plan introduces a public `visible_row_range() -> tuple[int, int]` helper, prefer that — but Slice C ships before that helper is required.)

### Buffer rev counter (`prose_overlay_state.py:117`)

- Use `buffer.rev` as the memoization key for Slice D's confidence cache: `if cached_rev == buffer.rev: return cached_scores`. This is exactly the use case `rev` was added for (commit `d9b6337`). Slices A/B/C don't need it because they recompute trivially.

### Existing `trillium_talon/core/homophones/`

- **Cite, do not modify.** The existing modal `phones <word>` HUD is the user's known-good fallback and lives outside this repo. The new code reads `homophones.csv` from that path (read-only) and registers `phone <hat>` in a different grammar slot. No edits to that directory, no PR there.
- Document the relationship in `prose_overlay_homophones.py`'s docstring: "this module is the *passive* homophone surface — flag and swap-by-hat. The active modal HUD at `trillium_talon/core/homophones/homophones.py` remains the explicit `phones <word>` fallback."

## 6. Open questions for Trillium

1. **Default-on or default-off for Slice A?** Plan says default-off so the experiment is opt-in. The opposite case: default-on so the always-on flag question is actually *tested* (a setting that nobody flips is a setting that doesn't ship). Lean toward default-off for the first commit, flip to default-on after one session of "yeah, leave it on" feedback. Worth a one-line confirm before merging Slice A.
2. **CSV path — read from `~/.talon/user/trillium_talon/.../homophones.csv`, or copy a snapshot into this repo?** Reading the external path keeps the wordlist single-sourced but ties the overlay to trillium_talon being installed. Copying makes the overlay self-contained but creates a drift point. Recommendation: read the external path with a try/except fallback to empty (the overlay degrades to no-flag), but call out the dependency in the README. Confirm before Slice A.

---

*Plan ends. The first commit should be invisible at the voice layer (Slice A is off by default), reversible in one revert, and decidable from one session of normal use.*
