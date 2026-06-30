# Homophone Indication & Swap — Research

> **Provenance.** Synthesized 2026-06-29 from a background research-agent sweep of voice-editor / accessibility / dictation prior art for homophone UI indication, data-structure design, and selection / replacement mechanisms.
> **Companion docs:** [`VIEWPORT_RESEARCH.md`](./VIEWPORT_RESEARCH.md), [`UNDO_REDO_RESEARCH.md`](./UNDO_REDO_RESEARCH.md), [`STACK_OVERFLOW_PAPER_TRAIL.md`](./STACK_OVERFLOW_PAPER_TRAIL.md).

## Context

In a voice-driven text editor, dictation can't always disambiguate `their / there / they're`, `to / too / two`, `right / write / rite`, `principal / principle`, etc. The user often only catches the wrong choice on a visual scan. This doc captures research on **how to indicate flagged homophones**, **how to keep their state in memory**, and **how to let the user swap by voice** — composing with Cursorless's hat addressing system rather than fighting it.

---

## 1. TL;DR recommendation

For v1, ship a **two-layer indicator** on top of Cursorless hats: (a) a **1 px low-saturation dotted underline** under every flagged token (sub-syntax-color readability), with **opacity scaled to ambiguity** (50/50 → fully opaque, 95/5 → barely visible); and (b) when the user issues `phones show` (or moves the focus rect over a flagged token), a **right-anchored inline ghost chip** of the form `→their²·there³` rendered to the right of the token in the gutter or end-of-line, where the superscripts are speakable ordinals. This composes with hats — Cursorless owns the *prefix* of the token graphic (the hat), so the homophone signal owns the *suffix* (underline below + chip right of EOL). No color collisions, no shape collisions.

Data structure: a **two-tier homophone index** — (a) cold immutable `Map<phonetic_key, FrozenSet<surface>>` built once from `pimentel/homophones` (641 entries, the same CSV already in `trillium_talon/core/homophones/`) keyed by Double Metaphone, with CMUdict as a fallback for proper-noun coverage; and (b) hot mutable `IntervalMap<DocumentOffset, Flag>` keyed by buffer range, where each `Flag` carries `group_id`, `current_word`, `confidence`, `dismissed`, and a `revision` checkpoint so it can be invalidated on tree-sitter `changed_ranges`. Confidence comes from a **local trigram lookup** over the surrounding 2-token-left / 2-token-right window against a precomputed `(prev, candidate, next) → log_prob` map distilled from Google Books Ngrams — no neural model required for v1.

Swap mechanism: register **`phone` as a Cursorless action** (sibling to `chuck`, `take`, `phones`) and a **`homophone` scope** that matches only flagged tokens. The four commands that matter: `phone <hat>` cycles to the most-likely alternative on the hat'd token; `phone <hat> as <word>` direct-targets a specific homophone; `phones every <scope>` triages all flagged tokens in a line/paragraph; `phones ignore <hat>` dismisses session-scoped. The existing `phones <word>` modal HUD ([trillium_talon/core/homophones/homophones.py](file:///Users/trilliumsmith/.talon/user/trillium_talon/core/homophones/homophones.py)) stays as the explicit "I know what I want, list 'em" fallback. Pre-seal as one `STRUCTURAL` undo step per [`UNDO_REDO_RESEARCH.md`](./UNDO_REDO_RESEARCH.md).

---

## 2. UI indication catalog

Each entry: name · what it looks like · voice-addressability · screen cost · accessibility · prior art.

### A. Confidence-graded sub-syllabic underline
A 1-pixel dotted underline directly under the token, opacity = `1 - certainty_of_current_word`. So "their" in a context where the trigram model rates it 0.93 likely shows barely visible; "their" in a 0.51 context glows. Voice-addressable indirectly — Cursorless hat on top of the token is the address. Screen cost: minimal (same line height, no displacement). Accessibility: monochrome-friendly (opacity, not color), survives color-blind users. Prior art: LSP `DiagnosticSeverity.Hint` renders as a faded / no-squiggle in VS Code precisely because hints are below-threshold cosmetic ([LSP 3.18 spec](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.18/specification/), [VS Code diagnostic rendering](https://github.com/microsoft/vscode/issues/142810)). Grammarly's four-color underline ([Grammarly engineering blog](https://www.grammarly.com/blog/engineering/making-grammarly-feel-native-on-every-website/)) is the same primitive with type encoding instead of confidence.

### B. End-of-line "→alt¹·alt²·alt³" suffix chip
For each line containing flagged tokens, paint a faint chip past EOL: `their²·there³`. Superscripts are the speakable ordinals. Voice-addressability: native — `swap homophone two on this line` works without hats. Screen cost: lives in the empty trailing region of the line, zero text displacement. Accessibility: text-rendered (screen-reader compatible if the canvas exposes it). Prior art: Vim signs + VS Code `gutterIconPath` ([VS Code decoration API](https://code.visualstudio.com/api/references/vscode-api)) and `IModelDecorationMinimapOptions` — but moving them inline-right of EOL is the novelty, because in a canvas you control the line geometry; you don't have to fit into a gutter someone else owns.

### C. Cursorless "homophone hat" — distinct shape, no color collision
Cursorless ships 10 shapes (`bolt curve fox frame play wing hole ex cross eye`) plus default-dot, across 5 colors plus default-gray ([Cursorless hat assignment docs](https://www.cursorless.org/docs/user/hatassignment/)). The "hat space" is the cartesian product the allocator partitions per visible token. **Reserve one shape — `frame` is the obvious pick because it visually says "look at this"** — and one color slot (e.g., a desaturated amber not in the standard palette) **strictly for homophone-flagged tokens**, paid for by removing that shape/color combo from the general pool. Voice command becomes literally `phone frame` (= "swap the frame-hatted token, which is the homophone next to my cursor"). Screen cost: zero new pixels — re-uses the hat slot. Accessibility: the shape is the signal, color is reinforcement. Prior art: Cursorless's existing hat allocator ([HatAllocator.ts](file:///Users/trilliumsmith/code/cursorless/packages/cursorless-engine/src/core/HatAllocator.ts)) debounces over visible tokens — a homophone scope plugs into the same loop. **Composes** with Cursorless rather than fights it because you're trading a hat slot, not stacking glyphs.

### D. Peripheral homophone strip (right margin density indicator)
Sublime-style minimap, but only for homophones: a 4-pixel vertical strip on the right edge with a single tick per flagged token, vertically aligned to its line. Voice: `phones show all` jumps focus through them in order; `phone tick three` addresses the third strip mark from the top. Screen cost: 4 px of width. Accessibility: small motor-control gain — scannable at a glance across the whole document, not just visible viewport. Prior art: VS Code minimap markers via `IModelDecorationMinimapOptions` ([editor widget minimap](https://deepwiki.com/microsoft/vscode/2.2-editor-widget-configuration-and-minimap)). Trade-off vs. inline indication: better for whole-doc triage, worse for in-context disambiguation.

### E. Just-in-time reveal triggered by focus zone
The underline (A) is *always-on* but at 30% opacity floor; when the cursor / Cursorless "that" target lands within N tokens of a flagged token, the underline bumps to its actual confidence-driven opacity and the chip (B) appears. Voice: untouched — the canvas tracks focus, you don't say anything. Screen cost: dynamic; clutter floor is provably bounded. Accessibility: removes always-on visual noise for users with visual processing fatigue. Prior art: Apple's iOS-17 blue autocorrect underline only persists briefly post-correction ([Apple support](https://support.apple.com/en-lamr/104995)).

### F. Confidence as glyph density, not opacity
Instead of opacity, use number-of-dots in the underline as the confidence channel: 1 dot under "their" if model says 0.95-correct; 4 dots if 0.5. Reads as "how worried should I be." Voice: untouched, underline is informational. Accessibility: better than opacity for high-contrast or low-vision modes where translucency is hard to perceive. Prior art: not seen shipped — Grammarly does color-as-category, not density-as-confidence — so this is a real expansion of the design space.

### G. Audible confidence chirp
For genuine ambiguity (confidence < 0.6) at the cursor's current word, a brief sub-200 ms TTS chirp or pitched beep when the user issues `that` or `take` against the token, indicating "by the way, this is a homophone you might've missed." Voice-addressable: chirp is signal, not command. Accessibility: pairs with the underline rather than replacing it — gives blind / low-vision users an out-of-band cue. Prior art: Dragon NaturallySpeaking's correction tones; iOS VoiceOver's verbal hints.

*Beyond the prior baseline list* (wavy underline / tint / badge / tooltip / pulse): A, C, D, F, G are net-new. B and E are softened versions of "inline alternative display" and "just-in-time reveal" pinned to concrete canvas geometry the baseline didn't specify.

---

## 3. Data structures

Two layers: a cold static index (rarely changes) and a hot per-document state (mutates every edit).

```python
# ─────────── COLD: built once at startup, immutable ───────────

from typing import FrozenSet, NewType
from dataclasses import dataclass

PhoneticKey   = NewType("PhoneticKey", str)   # Double-Metaphone primary code
GroupId       = NewType("GroupId", int)       # row index in homophones.csv
SurfaceWord   = NewType("SurfaceWord", str)   # lowercase

@dataclass(frozen=True, slots=True)
class HomophoneGroup:
    id: GroupId
    words: FrozenSet[SurfaceWord]           # e.g. {"their", "there", "they're"}
    canonical: SurfaceWord                  # display anchor, first in CSV row
    phonetic: PhoneticKey                   # for confusion-set extension

@dataclass(frozen=True, slots=True)
class StaticIndex:
    by_word:     dict[SurfaceWord, GroupId]            # O(1) "is X a homophone?"
    by_phonetic: dict[PhoneticKey, FrozenSet[GroupId]] # for phonetic-fallback
    groups:      tuple[HomophoneGroup, ...]            # GroupId -> group

# ─────────── HOT: per-document, mutates on every edit ───────────

from typing import Optional
Offset    = NewType("Offset", int)
Revision  = NewType("Revision", int)

@dataclass(slots=True)
class FlagState:
    start:       Offset
    end:         Offset
    group_id:    GroupId
    current:     SurfaceWord
    confidence:  float          # P(current is correct | local context), 0..1
    scored_at:   Revision       # buffer rev when confidence last computed
    dismissed:   bool = False   # session-scoped; persisted at doc level if needed
    last_swap:   Optional[float] = None  # epoch sec, for animation/decay

@dataclass(slots=True)
class DocFlagSet:
    flags:    "IntervalTree[Offset, FlagState]"  # range-queryable
    by_line:  dict[int, list[FlagState]]          # for line-scoped commands
    rev:      Revision                            # current doc revision
    dirty:    set[tuple[Offset, Offset]]         # ranges needing re-scan
```

**Why this shape, justified by concrete operations:**

- **"Given the word I just typed, what are its homophones?"** — `static.by_word[word.lower()] → group_id → static.groups[gid].words`. Two dict lookups, both O(1).
- **"Given a buffer range that was edited, what flags need re-checking?"** — `doc.flags.overlap(start, end)` from the interval tree is O(log n + k). Augment by *expanding* the range by ±N tokens (default N=3) before querying so context shifts re-score neighbors.
- **"How do I render the indicator for visible tokens?"** — `doc.flags.overlap(viewport.start, viewport.end)` returns the FlagStates to paint, already carrying their `confidence` for opacity calc.
- **"Voice command 'phones every paragraph'"** — `doc.by_line[ln]` for ln in paragraph; bulk apply.

**Incremental maintenance** mirrors tree-sitter exactly ([tree-sitter incremental parsing](https://tomassetti.me/incremental-parsing-using-tree-sitter/)). On each edit, the edit handler emits a `(start_byte, old_end_byte, new_end_byte)` triple → shift every `FlagState.start/end` past `start_byte` by `(new_end_byte - old_end_byte)` (interval-tree bulk shift is O(n) worst case but cheap with implicit offset, see persistent-tree-of-intervals techniques) → mark `(start_byte - WORD_CONTEXT, new_end_byte + WORD_CONTEXT)` dirty → on idle (debounce 150 ms — same as Cursorless's HatAllocator pattern), re-tokenize dirty ranges, look up each token in `static.by_word`, replace/insert flags, recompute confidence over the new ±2-token window. Critically, the flag table is keyed off the **revision counter** so a swap action seals the previous rev and the next rescan can never operate on stale offsets.

**Confidence layer.** Don't ship a neural LM in v1. The `(prev, word, next)` trigram space for the ~1500 surface words that appear in pimentel's 641 groups is tiny — precompute log-prob from [Google Books Ngrams](https://storage.googleapis.com/books/ngrams/books/datasetsv3.html) trimmed to those words and ship a compressed lookup table. Score for a flagged token = `softmax_over_group_members(logP(prev, w, next))`. Confidence = `score[current_word]`. Fall back to BlueDrink9's [GloVe-50 cosine-similarity approach](https://github.com/BlueDrink9/homophoner-talon) for OOV context. A neural LM (a quantized distilled Gemma-2B or similar local model) is a v2 swap-in behind the same `confidence: float` interface.

**Why pimentel CSV over CMUdict for v1:** pimentel's 641 curated entries are pre-filtered for *actual user confusion* and are already loaded by `trillium_talon/core/homophones/homophones.py`. [CMUdict's 134k pronunciations](https://github.com/cmusphinx/cmudict) generates true homophone groups via phoneme equality but the false-positive rate is brutal for English's near-homophones (`merry / marry / Mary` only collide in some dialects). Use CMUdict-derived groups only as a fallback when pimentel misses (proper nouns, archaic words) — and gate phonetic-key fallback behind [Double Metaphone](https://en.wikipedia.org/wiki/Metaphone) on both candidate and surface so you're not flagging `which / witch` as same-group with `whip / wick`. Metaphone 3 claims 98% accuracy vs Double Metaphone's 89% but is licensed; Double Metaphone is the right v1 choice ([algorithm comparison](https://www.datablist.com/learn/data-cleaning/double-metaphone)).

---

## 4. Selection & replacement

### Voice command grammar (Cursorless-style)

Add `homophone` as a custom scope via the existing experimental hatch — it's a regex-driven scope per the documented mechanism ([Customization](https://www.cursorless.org/docs/user/customization/)), but here it's a **dynamic** scope backed by the `DocFlagSet`. Concretely:

```
# user/cursorless-settings/experimental/scope_types_custom.csv
# (registered programmatically via the talon-everywhere API)
homophone, phone | phones
```

Then register a custom action that consumes a target:

```python
# In a talon file, leveraging cursorless's public capture API
@mod.action_class
class Actions:
    def cursorless_swap_homophone(target: dict, choice: str = ""):
        """Replace target token with its next/named homophone."""
        text = actions.user.cursorless_get_text(target)
        flag = doc_flags.lookup_at_text(text)
        if not flag:
            app.notify(f"'{text}' not flagged as homophone")
            return
        new_word = _select_replacement(flag, choice)
        actions.user.cursorless_replace(target, new_word)
        doc_flags.swap(flag.id, new_word)  # seal as one undo step
```

```
# user.talon binding
phone <user.cursorless_target>:
    user.cursorless_swap_homophone(cursorless_target, "")

phone <user.cursorless_target> as <user.word>:
    user.cursorless_swap_homophone(cursorless_target, word)

phones every <user.cursorless_target>:
    user.cursorless_swap_all_homophones(cursorless_target)

phones ignore <user.cursorless_target>:
    user.cursorless_dismiss_homophone(cursorless_target)
```

That's the *one syntax to rule them all*: `phone bat` swaps the most-likely alternative on whichever token wears hat 'b'; `phone bat as write` is the explicit form when the user wants `right → write` specifically and doesn't trust the LM.

### Three swap mechanisms with trade-offs

**1. Direct-named addressing — `phone bat as write`**
Most precise, most verbose, never wrong. Best when the LM confidence at the flag is near 50/50 and you want to be unambiguous. Trade-off: requires user to know all members of the group; voice grammar must accept the literal alt-word as a `<user.word>` capture, which means homophones with spaces (`a lot` ↔ `allot`) need a multi-word capture or fall back to ordinal.

**2. Ordinal addressing — `swap homophone two`**
Reads the speakable ordinal from the indicator chip (Indicator B). Best when the chip is on-screen and the user can scan-then-speak. Trade-off: depends on the chip being visible; ordinals are unstable across edits (rank by likelihood, not insertion order, so the ordering can flip after re-scoring). Mitigation: pin ordinal order per-flag at first render and only re-order on explicit `phones rerank`.

**3. Implicit-context swap — `phone bat` (no `as`)**
The LM picks the highest-likelihood alternative *other than the current word*. Best when the model is confident and the user just wants the right word fast. Trade-off: when LM is wrong, user has to undo + re-do with `as`. Mitigation: if `confidence(current) > 0.7`, refuse the implicit swap and force `as` — i.e., the editor says "I think this is right, name your target if you disagree." Voice feedback: short TTS "are you sure?" with a one-shot listener for `yes` to bypass.

### Bulk operations
- `phones every line` / `phones every paragraph` / `phones every air` (Cursorless scope chain): iterate `DocFlagSet.flags` overlapping the resolved range, swap to highest-likelihood alternative *only if* `confidence(current) < 0.6`. Dump a summary "swapped 3, kept 7" via TTS.
- `phones accept all` / `phones dismiss all` for triage workflows: terminal state, no per-token decisions, sealed as one undo.

### Undo composition
Per [`UNDO_REDO_RESEARCH.md`](./UNDO_REDO_RESEARCH.md): each `phone` action emits a single `STRUCTURAL` undo entry that captures `(rev_before, [(offset, old_word, new_word), ...], rev_after)`. Bulk operations roll up all sub-swaps into one entry. Pre-seal at action entry, post-seal at action exit — never mid-swap.

### Dismissal scope
For v1, **session-scoped** is the right default. A dismissed flag stays in `DocFlagSet` with `dismissed=true` for the lifetime of the document open. Persistence (per-doc or per-user) is a v2 feature with a real cost: needs an on-disk store keyed by document path + word position + buffer hash, plus an invalidation story when the document changes around the dismissed flag. Don't pay that price until users ask.

### Voice rejection / TTS confirmation loop
For genuinely ambiguous flags (confidence in `[0.4, 0.6]`), when the user issues `phone bat` without `as`, the editor TTS-speaks "their, there, or they're?" and listens for a one-syllable answer (`one`, `two`, `three`, or the literal word). This is the **single most expensive UI choice** in the whole proposal — it adds an audio modality that didn't exist before and demands a listen window. **Recommendation: gate behind a user setting, off by default**, because Trillium's pattern is voice-in, screen-out; he scans the screen, not his ears. Patterned after Dragon NaturallySpeaking's correction dialog ([Dragon for Mac correction docs](https://www.nuance.com/products/help/dragon/dragon-for-mac/enx/content/Correction/CorrectionMenu.html)) but compressed to a half-second tone instead of a full menu read.

---

## 5. Prior art deep dives

### 5a. BlueDrink9 / homophoner-talon — closest neighbor, steal the resolver
[BlueDrink9/homophoner-talon](https://github.com/BlueDrink9/homophoner-talon) ships exactly the "voice-said-ambiguous-word, pick-with-context" half of this problem. Resolution function signature: `find_nearest_homophone(input_word: str, context: str) -> str`; scores candidates by cosine similarity of their GloVe vectors against the averaged context vector; overrides keyed by `(input_homophone, context_word) → replacement` for known model failures. **Worth stealing:** the override CSV pattern (perfect for the edge cases the LM gets wrong), the GloVe-50 fallback for OOV context. **Leave:** the modal command syntax (`phony right read`) is exactly the kind of explicit address you don't want when the editor is already painting indicators — invert the relationship: user spots flag visually, says `phone bat`, system uses the same resolver to pick.

### 5b. Ghotit Real Writer — the homophone UX standard for dyslexia
[Ghotit](https://www.ghotit.com/dyslexia-software-real-writer-for-windows) is the assistive-tech tool for dyslexia / dysgraphia and has the most refined homophone-flag UX in the wild: full-sentence context analysis to auto-fix `there / their`, plus an explicit "Homophone Alert" panel that shows each candidate with a usage example and click-to-replace. **Worth stealing:** the usage-example pattern (`there → "I left it there"` vs `their → "their car"`) shown on focus — for a voice user, TTS could speak the example on `phones explain bat`. **Leave:** the modal panel itself — costs too much screen real estate and breaks the canvas-buffer aesthetic.

### 5c. iOS-17 blue autocorrect underline — single-tap revert pattern
[Apple's iOS-17 autocorrect](https://support.apple.com/en-lamr/104995) underlines auto-corrected words in blue; tap reveals "original | alt1 | alt2" with one-tap choice. **Worth stealing:** the *temporal* underline — visible until next user action, then it fades. For a voice editor, the analog is: after a `phone` swap, the swapped token's underline goes from confidence-graded → bright "just changed" red-orange for 2 seconds, then fades back to confidence opacity. Cheap visual confirmation. **Leave:** the tap interaction, obviously.

### 5d. LSP `DiagnosticSeverity.Hint` — the right severity slot for homophones
[LSP 3.18](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.18/specification/) defines four severities: Error, Warning, Information, Hint. `Hint` is the "below threshold for the Problems panel; render as faded or no-squiggle" tier ([VS Code issue 142810](https://github.com/microsoft/vscode/issues/142810)). **Homophone flags are exactly Hint-tier** — they aren't errors (the doc still parses), they aren't even warnings (most homophones are correct). Treat them with Hint visuals: the faint dotted underline, no entry in any "problems list," noticeable only on scan. This gives the editor a principled visual hierarchy: if the editor ever grows real diagnostics (typos, true grammar errors), they cleanly out-rank homophone hints by squiggle weight.

### 5e. Grammarly's range-rect overlay rendering — the right canvas technique
Grammarly's [engineering blog post](https://www.grammarly.com/blog/engineering/making-grammarly-feel-native-on-every-website/) on browser-extension internals: they couldn't inject DOM nodes into hosts' text fields, so they paint underlines via `Range.getClientRects()` onto an absolutely-positioned overlay layer. **For a Skia-canvas buffer editor this is trivially native** — you already own the layout, you can ask the text layout system for the glyph bounding box of any offset range and draw the underline yourself, no DOM dance required. The takeaway is architectural: render homophone indicators on a **separate Skia layer above the text layer but below the cursor/selection layer**. That layer can re-paint independently of buffer text on confidence updates or focus moves, which is critical for the just-in-time reveal pattern (Indicator E).

### 5f. Hunspell PHONE / REP tables — the established phonetic-suggestion data model
[Hunspell's affix-file format](https://manpages.org/hunspell/5) defines `PHONE` (table-driven phonetic transcription, borrowed from aspell) and `REP` (replacement suggestions table). **Worth stealing:** the REP table as the model for an authoring-time override file. Ship a `homophones_overrides.csv` with rows like `there|context_pattern→their` where `context_pattern` is a simple glob over surrounding words. Mirrors Hunspell's REP-has-highest-suggestion-priority semantic — your overrides win over LM scoring. Same data shape as BlueDrink9's `(input, context_words) → replacement` mapping but standardized to the Hunspell idiom users already grok.

---

## 6. Open questions before implementing

1. **Reserve a Cursorless hat slot or paint a parallel decoration?** Indicator C trades one shape/color combo from Cursorless's allocator pool for a guaranteed-clean voice address (`phone frame`). Indicator A+B does not touch Cursorless. Both can ship, but the hat-reservation choice has a one-time visual-vocabulary cost across the whole editor. **Pick one before starting.**

2. **Is the canvas's text layout API capable of returning glyph bboxes for arbitrary offset ranges?** Indicator A (dotted underline at confidence opacity) and Indicator B (EOL chip) both require this. If the answer is no, the rendering layer needs to track per-token bboxes itself, which is a larger change.

3. **Trigram lookup table size budget.** A precomputed `(prev, candidate, next) → log_prob` table for the ~1500 surface words in pimentel's groups is ~50–200 MB raw, 5–20 MB after frequency pruning. Acceptable, or do we want a streamed/lazy lookup? Affects startup time vs. memory.

4. **Confidence threshold for "indicator visible at all."** Always-on at ≥30% opacity vs. only-visible-below-confidence-0.85 vs. just-in-time-on-focus (Indicator E). This is the single biggest readability dial; pick one and tune from there.

5. **Persistence of dismissals.** Session-scoped is the safe v1 default — but if you frequently re-open the same long docs (your own blog drafts on `trilliumsmith.com`, for instance), session-scoped means re-dismissing every reopen. Worth a v1.5 follow-up, not a v1 block.

6. **Audio confirmation gate (Section 4 final paragraph).** Confirm screen-out, voice-in is the right default — i.e., TTS confirmation loop is opt-in, not opt-out — so we don't ship an audible feedback channel you'll find annoying.

---

## Files referenced

- `/Users/trilliumsmith/.talon/user/trillium_talon/core/homophones/homophones.py` — existing modal homophone HUD (preserve as fallback)
- `/Users/trilliumsmith/.talon/user/trillium_talon/core/homophones/homophones.csv` — 680-row homophone list (Pimentel-derived)
- `/Users/trilliumsmith/.talon/user/cursorless-talon/src/actions/homophones.py` — existing Cursorless `phones <hat>` cycle-next action (extend, don't replace)
- `/Users/trilliumsmith/code/cursorless/packages/cursorless-engine/src/core/HatAllocator.ts` — debounced visible-token allocation lifecycle to mirror for the homophone scope
- `/Users/trilliumsmith/code/cursorless/packages/cursorless-engine/src/processTargets/modifiers/scopeHandlers/RegexScopeHandler.ts` — `NestedScopeHandler` shape a `HomophoneScopeHandler` should subclass

---

## Sources

- [pimentel/homophones GitHub](https://github.com/pimentel/homophones) — the 641-entry CSV already in use
- [CMU Pronouncing Dictionary (cmusphinx/cmudict)](https://github.com/cmusphinx/cmudict) — 134k pronunciations, CC-style license, phoneme-equality fallback source
- [Double Metaphone overview (Datablist)](https://www.datablist.com/learn/data-cleaning/double-metaphone)
- [Metaphone (Wikipedia)](https://en.wikipedia.org/wiki/Metaphone) — algorithm comparison table
- [BlueDrink9/homophoner-talon](https://github.com/BlueDrink9/homophoner-talon) — closest Talon prior art; GloVe + cosine-sim resolver
- [Cursorless customization](https://www.cursorless.org/docs/user/customization/) — custom regex scopes + custom actions CSV mechanism
- [Cursorless hat assignment](https://www.cursorless.org/docs/user/hatassignment/) — shape/color inventory
- [Ghotit Real Writer](https://www.ghotit.com/dyslexia-software-real-writer-for-windows) — homophone-alert UX in dyslexia tools
- [Grammarly engineering: native-feel rendering](https://www.grammarly.com/blog/engineering/making-grammarly-feel-native-on-every-website/) — `getClientRects()` overlay technique
- [LSP 3.18 spec](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.18/specification/) — `DiagnosticSeverity` semantics
- [VS Code diagnostic squiggle behavior change](https://github.com/microsoft/vscode/issues/142810) — Hint-tier rendering
- [Apple iOS-17 autocorrect underline](https://support.apple.com/en-lamr/104995)
- [Hunspell affix format (manpage)](https://manpages.org/hunspell/5) — PHONE / REP / MAP tables
- [Tree-sitter incremental parsing (Tomassetti)](https://tomassetti.me/incremental-parsing-using-tree-sitter/) — `changed_ranges` invalidation model
- [Dragon for Mac correction menu docs](https://www.nuance.com/products/help/dragon/dragon-for-mac/enx/content/Correction/CorrectionMenu.html) — voice-correction dialog prior art
- [VS Code minimap decoration internals (DeepWiki)](https://deepwiki.com/microsoft/vscode/2.2-editor-widget-configuration-and-minimap)
