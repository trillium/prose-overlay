# Potentially Missed Features — Triage Doc

> Brainstormed 2026-06-30 against `docs/FEATURE_PARITY.md`. Each row is a
> candidate the parity doc doesn't currently list. For each: human marks
> `[+]` to add to FEATURE_PARITY.md (status [ ]), `[—]` to add to §10 Out
> of Scope with one-line reason, or `[?]` to think about. Pure triage —
> nothing implemented from this doc.
>
> When triaged, move accepted rows into the appropriate FEATURE_PARITY.md
> section and delete this doc (or archive to `docs/archive/`).

---

## A. Navigation — beyond hat-targeted

The parity doc covers `pre <hat>`, `post <hat>`, viewport scroll, cursor start/end. What's missing:

- [ ] **Cursor to nth token** — "cursor token 5" → cursor before token index 5. (Cursorless has ordinal targets.)
- [ ] **Cursor to start/end of token** — "cursor start `<hat>`" → cursor at char 0 of the hatted token. Depends on mid-token cursor.
- [ ] **Word/line/paragraph cursor stepping** — "cursor next word", "cursor previous line". Currently no stepping; only direct jumps.
- [ ] **Cursor to homophone** — "cursor next homophone" → jump to next flagged token. (Adjacent to slice B work.)
- [ ] **Bookmark + recall** — "mark this" → name a position; "go to mark X" → jump back. Voice-friendly version of vim marks.
- [ ] **`that` / `source` pronouns** — cursorless's "take this" / "chuck that" refer to the LAST target. We have implicit `cursor` mark; no explicit recent-target memory.
- [ ] **Numeric prefix navigation** — "cursor down 5 lines" or "back 3 tokens".

---

## B. Selection — beyond hat-targeted

The parity doc covers `take <hat>`, range, list. Adjacent gaps:

- [ ] **Clear selection** — voice `deselect` or `chuck selection` to deselect without mutation. Currently selection is cleared by most mutations; no explicit deselect verb.
- [ ] **Re-select last selection** — restore previous selection. Useful when undo cleared it.
- [ ] **Extend selection by scope** — "extend sentence" → grow current selection to include the next sentence.
- [ ] **Shrink selection** — inverse of extend.
- [ ] **Select all** — `take file` works at the cursorless level; does it actually fire for whole-buffer? Verify.
- [ ] **Select line / paragraph at cursor** — current scope verbs require a hat target. Implicit cursor target.
- [ ] **Inverse selection** — "take everything but `<hat>`" — niche, probably OOS.

---

## C. Editing — beyond what's there

- [ ] **Repeat last action** — voice `again` to re-execute the most recent destructive utterance. Common voice pattern.
- [ ] **Spoken correction** — "scratch that" / "fix that" → undo last dictation insert AND open a correction prompt. Talon community has these patterns.
- [ ] **Multi-step undo with confirmation** — undo continuously until "stop". 
- [ ] **Replace via voice prompt** — "replace `<hat>` with quick brown fox" → cursorless replace with inline new content.
- [ ] **Wrap selection with delimiter** — "wrap selection in quotes" / "wrap `<hat>` in round" → bracket the target with a delimiter pair.
- [ ] **Unwrap selection** — inverse: strip delimiters off a wrapped target.
- [ ] **Swap targets** — "swap `<hat1>` and `<hat2>`" → exchange two tokens. Cursorless has this.
- [ ] **Case operations** — "upper `<hat>`", "lower `<hat>`", "title `<hat>`" — single-target case change without going through full formatter.
- [ ] **Sort / dedupe selection** — niche; the buffer rarely holds list content but worth noting.
- [ ] **Insert newline / paragraph break** — voice "new line" → insert `\n` token. Current model treats whitespace as token boundary; explicit newlines as content might not survive confirm-to-host roundtrip.
- [ ] **Numeric prefix N for any verb** — "chuck 3 air" → delete 3 tokens starting at hat 'a'. Cursorless has count modifiers.

---

## D. Cursorless gaps (parity not covered or partial)

- [ ] **`with` modifier** — "take air with the next two words". Compound target.
- [ ] **`every` scope** — "chuck every line" / "take every word" — bulk operations.
- [ ] **`first` / `last` modifiers** — "take first word `<hat>`" → first sub-word.
- [ ] **`leading` / `trailing` whitespace modifier** — "chuck leading trailing of `<hat>`" — strip whitespace.
- [ ] **`inside` / `outside` for delimiters** — "take inside round `<hat>`" vs "take outside round". (Surrounding-pair has the outer; inside might not work.)
- [ ] **`copy` / `cut` / `paste`** — cursorless has these as named actions; we have `bring`/`move` which are close but not identical. Verify mapping.
- [ ] **`reverse`** — "reverse selection" — reverse order of tokens. Niche.
- [ ] **`clone`** — "clone `<hat>`" — duplicate the target adjacent. Cursorless has this.
- [ ] **`indent` / `outdent`** — code-mode, but might apply to nested prose. Probably OOS.
- [ ] **`comment` / `uncomment`** — OOS for prose, but cursorless has it.
- [ ] **Compound actions** — "swap `<hat1>` and bring `<hat2>` past `<hat3>`" — chaining. Cursorless's grammar supports this; ours may not.

---

## E. Voice / dictation niceties

- [ ] **Auto-capitalize at sentence start** — current `prose_formatter` includes `sentence: CAPITALIZE_FIRST_WORD` but it's an explicit prefix. Auto-capping after `.`/`!`/`?` is a community-formatter behavior; verify it works inside the overlay.
- [ ] **Smart quotes / typography** — "open quote", "close quote" → `“` / `”`. Currently just `"`. Maybe OOS.
- [ ] **Punctuation drag** — sticky punctuation that follows the cursor (vim-style). Probably OOS.
- [ ] **"continue" / "more"** — voice utterance to keep adding to the last edit instead of starting a new one. Adjacent to undo coalescing.
- [ ] **Confidence indicator** — visual cue when speech recognition was low-confidence. Could be a token color override.
- [ ] **Replay last utterance** — TTS-back what was just heard. Debugging affordance.
- [ ] **Voice command help inside overlay** — "what can I say" → render the help panel filtered to overlay-active commands. The help panel exists; verify it's voice-discoverable from inside the overlay.

---

## F. Visual feedback — beyond what's there

- [ ] **Selection extension by scope flash** — when you extend a selection, flash the newly-included tokens.
- [ ] **Cursor color change on mode** — currently amber for change mode; could differentiate selection / no-selection / range-mode visually.
- [ ] **Token grouping highlight** — visually group tokens that share a sub-word ancestry (e.g., snake_case parts).
- [ ] **Recently-edited highlight** — last N tokens that were inserted/changed get a brief tint, fading over time.
- [ ] **Token boundaries on hover / focus** — render thin separators between tokens for clarity (currently relies on space).
- [ ] **Page indicator** — when overflow truncates rows, show "scrolled X / Y rows" hint.
- [ ] **Empty buffer placeholder text customization** — currently "listening...". Per-context placeholder.

---

## G. History and recall

- [ ] **Pin a history entry** — keep specific entries from being evicted by the LRU. Useful for repeated templates.
- [ ] **Search history** — "find history with X" → narrow the panel to entries containing X.
- [ ] **Replay history into a different window** — load entry, retarget window, confirm.
- [ ] **History entry preview before recall** — currently you say `recall N` and it loads; could preview first.
- [ ] **Export history** — save to file. Probably OOS (buffer is ephemeral by design).

---

## H. Settings / preferences

- [ ] **Per-window preference overrides** — anchor mode, scope filter, default formatter — saved per target app.
- [ ] **Spoken preference toggle** — "overlay font bigger" / "overlay font smaller" already work; what about color theme? Visibility tweaks?
- [ ] **Preferences dump / inspect** — debug command to print current effective settings.
- [ ] **Reset preferences to default** — wipe `~/.talon/prose_overlay_prefs.json` from voice.

---

## I. Multi-cursor / multi-target adjacency

Likely OOS but worth flagging:

- [—] **Multi-cursor** — multiple insertion points simultaneously. The cursor model is single; multi-cursor would be a large architectural change.
- [—] **Find all matching tokens** — visual highlight every instance of a word. Common in code editors; awkward for prose.
- [—] **Linked editing** — change one occurrence updates all linked ones.

---

## J. Observability / debug surface

- [ ] **Buffer text TTS playback** — `overlay speak buffer` reads the current buffer aloud. (Exists as `overlay speak` — verify it reads the buffer specifically.)
- [ ] **Hat introspection** — voice "what is the hat for `<word>`" → TTS the hat letter+color.
- [ ] **History introspection** — "what's in history slot 3" → preview without recalling.
- [ ] **Selection introspection** — "what is selected" → TTS the selection text.
- [ ] **Cursor introspection** — "where is the cursor" → TTS the position (e.g., "before token 5: 'the'").
- [ ] **Command audit log** — JSONL of every voice command fired (not just state changes). Bigger than the current debug log; useful for voice-grammar diagnostics.
- [ ] **Visible debug overlay** — a debug panel rendered ON the canvas (not the JSONL file) for in-flight inspection.

---

## K. Quality-of-life / discoverability

- [ ] **Voice command help filtered by overlay state** — `help when overlay open` vs `help when overlay closed`.
- [ ] **First-run hints / onboarding** — when overlay opens for the first time, show a discoverability tour. Probably OOS.
- [ ] **Error toast / hint** — when a voice command fails (e.g., hat not found), surface a brief visual hint instead of just logging.
- [ ] **Successful-command audio chirp** — non-intrusive confirmation that the system heard you. Or visual flash.
- [ ] **Voice command timeout / pacing** — keep alive after long pause? Auto-confirm on N seconds idle?

---

## L. Text-editor primitives we might still want

- [ ] **Tab stops** — voice "tab" inserts a tab character. May conflict with confirmation patterns.
- [ ] **Whitespace visualization** — show invisible characters (spaces, newlines) on demand.
- [ ] **Hard / soft wrap toggle** — already handled by canvas overflow, but no toggle.
- [ ] **Line numbers** — never had them; might be useful for "chuck line 3".
- [ ] **Status bar** — token count / cursor position / buffer rev visible on the canvas.
- [ ] **Word count** — "overlay count" → TTS the word count.
- [ ] **Buffer search** — "find next 'the'" → cursor to next occurrence of literal text.
- [ ] **Buffer replace** — "replace all 'the' with 'a'" — niche but possible.
- [ ] **Macros** — record a sequence of voice commands and replay. Likely OOS.
- [ ] **Custom abbreviations** — "btw" → "by the way" inline. Community formatter handles `<user.abbreviation>`; verify routing.

---

## M. Integration with other tools

- [ ] **Cursorless's `make` action** — extracts a variable, creates a function, etc. Code-mode but might apply to prose templating.
- [ ] **Mouse-clock integration** — pointer-based hat selection (the shape vocabulary borrowed from there is already in slice 1).
- [ ] **TTS read-back from prose-overlay** — currently `overlay speak` works; what about per-paragraph or per-sentence?
- [ ] **Clipboard read** — "buffer paste" → insert system clipboard at cursor. Currently confirm-to-host writes; reverse direction missing.
- [ ] **System notification on confirm** — when buffer commits to target window, emit a Pulse / native notification.

---

## N. Edge cases we might want guards for

- [ ] **Extremely large buffer (>500 tokens)** — viewport handles overflow; does hat allocator gracefully degrade? Allocator skips at >234 (alphabet × colors).
- [ ] **Empty buffer + cursor active** — currently cursor sits at gap 0; verify drawing is correct.
- [ ] **Buffer-of-only-symbols** — "downscore comma slash" → ["_", ",", "/"]. Hats? Letter capture for selection?
- [ ] **Buffer-of-only-numbers** — "five six seven" → "567" (one token); "five comma six" → "5,6" (one token). Hats now exist; addressability via voice? (Already a known gap.)
- [ ] **Buffer entirely flagged as homophones** — every token gets a shape. Is the visual readable?
- [ ] **Cursorless target with no matching mark in buffer** — graceful failure already exists (`print` in resolve.py); verify.
- [ ] **Buffer survives target-window crashing** — overlay should stay open even if recall target dies.

---

## Triage workflow

1. Skim each section.
2. Mark each row `[+]` / `[—]` / `[?]`.
3. For `[+]` rows: copy into the appropriate FEATURE_PARITY.md section with status `[ ]`.
4. For `[—]` rows: copy into FEATURE_PARITY.md §10 Out of Scope with the one-line reason.
5. For `[?]` rows: leave here for the next pass.
6. When all rows are triaged: delete this doc or move to `docs/archive/POTENTIALLY_MISSED.<date>.md`.

## How this doc was built

Brainstormed by walking through:
- Common text-editor feature checklists (vim/emacs/vscode primitives)
- Cursorless's full action / modifier / scope surface
- Voice-first editor adjacencies (community formatters, talon-wiki patterns)
- Adjacent prose-overlay docs (HOMOPHONE_*, UNDO_REDO_PLAN, etc.) for "what comes next" implications
- Edge cases observed during development (empty buffer, overflow, homophone-heavy text)

Bias toward over-listing — better to mark `[—]` than miss a real feature.
