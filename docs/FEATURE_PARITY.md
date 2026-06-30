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
| `[x]` | History recall — last N confirmed prose entries | `overlay history` | `prose_overlay_actions_history.py` |
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
| `[ ]` | **word scope splits formatted tokens into sub-words** | inside "one_two_three", "take second word this" → selects "two" | **the user's stated requirement** — needs sub-word resolver |
| `[ ]` | sub-word identity preserves joiner under replace | "word changed" on selection {two} in "one_{two}_three" → "one_changed_three" | depends on sub-word selection |

### 3d. Surrounding pairs

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[x]` | round / box / curly / diamond / quad / twin / skis delimiters | "take quotes air" | ISC-5 |
| `[x]` | `any` / `pair` aggregation | "chuck pair" | ISC-5 |

### 3e. Bring / move / formatter

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[x]` | bring (copy src token → dst hat) | "bring air to drum" | ISC-6 |
| `[x]` | move (cut src → dst hat) | "move air to drum" | ISC-6 |
| `[x]` | applyFormatter on a hat target | "format snake at fox past bat" | ISC-7 |
| `[x]` | Prose formatters (say/sentence/title) routed to buffer | "sentence the quick brown fox" → "The quick brown fox" | `5652b0e` |
| `[x]` | Code formatters (snake/camel/dotted/...) routed to buffer | "snake the quick brown fox" → "the_quick_brown_fox" | `31df606` |

### 3f. JS resolver migration

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[~]` | JS resolver behind setting | `user.prose_overlay_use_js_resolver = True` | scaffolded; awaiting MANUAL_VERIFICATION.md walkthrough |
| `[ ]` | Python resolver removed once JS holds 3 sessions | grep for imports = 0 | ISC-9 |

## 4. Selection

| Status | Feature | Example | Notes |
|---|---|---|---|
| `[x]` | Token selection via cursorless `setSelection` | "take air" → selection on token | shipped |
| `[x]` | Range selection | "take air past drum" | shipped |
| `[x]` | Selection highlight render | blue 25% alpha | `prose_overlay_draw_tokens.py:158` |
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
| `[~]` | Shape hats on flagged tokens | Slice 1 of HOMOPHONE_SHAPES_PLAN | Forge bg agent in flight |
| `[ ]` | Shape panel with alternates | Slice 3 of HOMOPHONE_SHAPES_PLAN | future |
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
