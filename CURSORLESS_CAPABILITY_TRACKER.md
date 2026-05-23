# Cursorless Capability Tracker — Prose Overlay

**Last verified:** 2026-05-23  
**Status:** Code-verified (not live-tested)  
**Format:** Test matrix showing what can be spoken and whether it works correctly based on implementation analysis.

---

## 1. Target Grammar

Can the overlay resolve different target shapes?

### Single Hat
- **"chuck air"** — ✅ Works
  - Resolves via `_cursorless_symbol_to_token_index()` → `_resolve_primitive_to_token_range()` returns `(idx, idx)`
  - Deletes one token, flashes red, redraws

- **"take air"** — ✅ Works
  - Same resolution, sets selection via `instance.buffer.set_selection()`, visual feedback is blue highlight
  - Selection persists in `instance.buffer._selection` tuple

### Colored Hat
- **"chuck blue air"** — ✅ Works
  - Color passed through `_cursorless_symbol_to_token_index()` (blue, green, red, etc. all handled)
  - Hat lookup: `(character.lower(), prose_color)` in `_state.hat_to_token` dict
  - Returns -1 if not found (no-op with log)

- **"take green bat"** — ✅ Works
  - Same mechanism, different color in tuple key

### Range Target (Two hats)
- **"chuck air past bat"** — ✅ Works
  - Resolves as RangeTarget: anchor=air, active=bat
  - `_resolve_target_to_token_range()` handles type=="range"
  - Computes `first = min(anchor[0], active[0])`, `last = max(anchor[1], active[1])`
  - Returns spanning range even if hats are unordered

- **"take green air past blue bat"** — ✅ Works
  - Both hats with colors resolved separately, then range computed
  - Each hat looked up by `(letter, color)` pair

### Scope Target (Token-level scope)
- **"chuck word"** — ✅ Works
  - PrimitiveTarget with mark=None, modifiers=[{type: "containingScope", scopeType: {type: "word"}}]
  - scope_type "word" is in `_WORD_SCOPE_TYPES`, resolves to token at cursor
  - Returns `(cursor_idx, cursor_idx)` if cursor is set; None if not

- **"chuck line"** — ✅ Works
  - scope_type "line" is in `_WHOLE_BUFFER_SCOPE_TYPES`
  - Always returns full buffer `(0, len(tokens)-1)` (single-line prose)

- **"chuck file"** — ✅ Works
  - scope_type "document" is in `_WHOLE_BUFFER_SCOPE_TYPES`
  - Returns full buffer range

- **"chuck identifier"** — ✅ Works
  - scope_type "identifier" in `_WORD_SCOPE_TYPES` → token at cursor

- **"chuck token"** — ✅ Works
  - scope_type "token" in `_WORD_SCOPE_TYPES` → token at cursor

- **"chuck char"** — ⚠️ Partial
  - scope_type "character" in `_WORD_SCOPE_TYPES` → resolves to single token at cursor
  - **Gap:** "char" scope on a token-level buffer is lossy; can't target individual characters within a word
  - Entire token gets deleted, not just one character

### Implicit Target (Cursor position)
- **"chuck this"** — ✅ Works
  - Resolves ImplicitTarget via `_resolve_target_to_token_range(target.type == "implicit")`
  - Maps to `_state.cursor` (gap index converted to token index)
  - Deletes one token at cursor position

- **"change this"** — ✅ Works
  - Same, but action is "clearAndSetSelection", enters change mode

### List Target (Multi-target `and` expressions)
- **"chuck air and bat"** — ❌ Not implemented
  - `_resolve_target_to_token_range()` detects type=="list" and logs:
    > "prose_overlay: ListTarget (multi-target 'and' expressions) are not supported — operate on targets individually"
  - Returns None, action is a no-op

---

## 2. Actions

For each action, does it work and does it have visual feedback?

### remove / chuck
- **"chuck air"** — ✅ Works, has visual feedback
  - Action: `remove`
  - Flash: red (color code "e02d28")
  - Execution: `instance.buffer.delete_token(idx)`, flashes 150ms then deletes
  - Can be undone (calls `snapshot()` before mutation)
  - Recomputes hats post-deletion

### setSelection / take
- **"take air"** — ✅ Works, has visual feedback
  - Action: `setSelection`
  - Flash: blue (color code "089ad3")
  - Execution: `instance.buffer.set_selection(first_idx, last_idx)` (stored in `._selection` tuple)
  - Selection highlighting: rendered in `draw_overlay()` with 25% alpha blue (hex "089ad340")
  - Persists until cleared or another action executes

### clearAndSetSelection / change
- **"change air"** — ✅ Works, has visual feedback
  - Action: `clearAndSetSelection`
  - Flash: amber (color code "e5a02c")
  - Execution: deletes range, sets selection, enters change mode
  - Change mode visual: cursor renders in amber (CURSOR_COLOR_CHANGE = "e5a02cff") with faint amber insertion zone behind it

### setSelectionBefore / pre
- **"pre air"** — ✅ Works, has visual feedback
  - Action: `setSelectionBefore`
  - Flash: white (color code "ffffff")
  - Execution: `_prose_overlay_set_cursor(idx, change_mode=False)` — cursor positioned before token
  - Cursor rendered as white line in navigate mode

- **"pre air past bat"** (range) — ✅ Works
  - Cursor positioned at `first_idx` (start of range)

### setSelectionAfter / post
- **"post air"** — ✅ Works, has visual feedback
  - Action: `setSelectionAfter`
  - Flash: white (color code "ffffff")
  - Execution: `_prose_overlay_set_cursor(idx+1, change_mode=False)` — cursor positioned after token
  - Cursor visible, white line in navigate mode

- **"post air past bat"** (range) — ✅ Works
  - Cursor positioned at `last_idx+1` (after range)

### bring (hat-to-hat)
- **"bring air to bat"** — ✅ Works
  - Grammar: `bring <user.letter> to <user.letter>` (and color variants)
  - Execution: `prose_overlay_bring_hat_to_hat(src_letter, src_color, dst_letter, dst_color)`
  - Copies token at src, replaces token at dst with src value
  - No flash (not routed through `_flash_tokens()`)
  - Recomputes hats, refreshes canvas

- **"bring blue air to green bat"** — ✅ Works
  - Both hats resolved by color, copied and replaced

### move (hat-to-hat)
- **"move air to bat"** — ✅ Works
  - Grammar: `move <user.letter> to <user.letter>` (and color variants)
  - Execution: `prose_overlay_move_hat_to_hat(src_letter, src_color, dst_letter, dst_color)`
  - Copies src, replaces dst, deletes src
  - Order: replace first (index stable), then delete
  - No flash
  - Recomputes hats, refreshes canvas

### bring <cursorless_target> to cursor position
- **"bring air"** (to cursor) — ✅ Works
  - Grammar: `{user.cursorless_bring_move_action} <user.cursorless_target>`
  - Maps to `prose_overlay_bring_move(action_name="replaceWithTarget", target=...)`
  - Source resolved to token range, destination is cursor position
  - Flash: green (color code "36b33f") before executing
  - Execution: JS shim returns edit plan, `_apply_edit_plan()` inserts at cursor, deletes source if move
  - If no cursor is active, logs error and no-ops

### move <cursorless_target> to cursor position
- **"move air"** (to cursor) — ✅ Works
  - Grammar: `{user.cursorless_bring_move_action} <user.cursorless_target>`
  - Maps to `prose_overlay_bring_move(action_name="moveToTarget", target=...)`
  - Inserts at cursor AND deletes source (two edits in reverse char order)
  - Flash: green before executing
  - If no cursor active, no-ops with error log

---

## 3. Visual Feedback

What does the user see when commands execute?

### Flash Highlight (Before Action)
- **Timing:** 150ms flash duration set in `_flash_tokens(duration_ms=150)`
- **Rendering:** `draw_overlay()` checks `flash_indices` and `flash_color`, draws 30% alpha highlight rect behind tokens
- **Colors by action:**
  - remove: red (e02d28)
  - setSelection: blue (089ad3)
  - clearAndSetSelection: amber (e5a02c)
  - setSelectionBefore/After: white (ffffff)
  - replaceWithTarget/moveToTarget: green (36b33f)
- **Implementation:** Flash state stored in `instance.flash_state` dict, callback scheduled via `cron.after(f"{duration_ms}ms", _after_flash)`

### Selection Highlight (Persistent)
- **Status:** ✅ Implemented
- **Rendering:** When `instance.buffer._selection` is not None, all tokens in range `[start, end]` get blue highlight (25% alpha, hex "089ad340")
- **Persistence:** Remains visible until selection is cleared (happens on most mutations, or explicit clear)
- **Used by:** "take" action, but also set by hat-to-hat bring/move (no visual feedback there, but selection tracks it)

### Cursor Position Indicator
- **Status:** ✅ Implemented
- **Rendering:** `draw_cursor()` draws a 2-pixel white or amber line at the cursor gap position
- **Positioning:** Cursor can sit before any token (idx), after the last token (idx == len(tokens)), or be None (no cursor)
- **Change mode:** Cursor renders in amber (CURSOR_COLOR_CHANGE) with faint amber insertion-zone rectangle behind it

### Cursor Blink
- **Status:** ✅ Implemented
- **Mechanism:** `_blink_tick()` cron job toggles `instance.blink_on` every 500ms
- **Rendering:** `draw_cursor()` only renders if `blink_on == True`, so cursor disappears on off-phase
- **Canvas refresh:** triggered by cron callback, no manual refresh needed

### Hat Display
- **Status:** ✅ Implemented
- **Rendering:** For each token with index < 26, a small colored dot appears above the assigned character
  - Dot radius: 3 pixels
  - Color: matches hat color (gray, blue, green, red, pink, yellow, purple, black, white)
  - Black hat: drawn with white border so it's visible on dark background
- **Assignment:** From `hat_assignments` dict, populated by `_recompute_hats()` which calls `compute_hat_assignments()` in `prose_overlay_state.py`
- **Collision resolution:** Two tokens with same letter get different colors (gray first, then blue, green, etc.)
- **Beyond 26 tokens:** No hat drawn (only 26 letters)

---

## 4. Scope Types

For each scope modifier, does it resolve correctly?

| Scope Type (Code) | Spoken Form | Resolves to | Status |
|---|---|---|---|
| `document` | "file" | Full buffer (0, last_idx) | ✅ |
| `line` | "line" | Full buffer (single-line buffer always) | ✅ |
| `paragraph` | "block" | Full buffer | ✅ |
| `fullLine` | "full line" | Full buffer | ✅ |
| `token` | "token" | Single token at cursor | ✅ |
| `word` | "sub" | Single token at cursor | ✅ |
| `identifier` | "identifier" | Single token at cursor | ✅ |
| `character` | "char" | Single token at cursor (lossy) | ⚠️ |
| *(all others)* | *(not in Cursorless prose scope list)* | Logs error, returns None | ❌ |

**Scope type gaps:**
- Only 8 scope types recognized (hardcoded in `_WHOLE_BUFFER_SCOPE_TYPES` and `_WORD_SCOPE_TYPES`)
- Real Cursorless has 50+ scope types (statement, comment, class, function, regex, etc.)
- Any scope type not in the hardcoded sets → logs "unrecognized scope type" and returns None
- **Example fails:**
  - "chuck statement" → ❌ (scopeType.type == "statement" not recognized)
  - "chuck comment" → ❌
  - "chuck regex" → ❌

---

## 5. Range Modifiers

### head (from start to hat)
- **"chuck head air"** — ✅ Works
  - Modifier: `extendThroughStartOf`
  - Resolves to `(0, base_idx)` where base_idx is the hat's token index
  - Deletes tokens from start through and including air
  - Flash: red

- **"change head air"** — ✅ Works
  - Same range, but action is clearAndSetSelection (delete + enter change mode at position 0)
  - Cursor positioned at start of buffer

### tail (from hat to end)
- **"chuck tail air"** — ✅ Works
  - Modifier: `extendThroughEndOf`
  - Resolves to `(base_idx, len(tokens)-1)`
  - Deletes tokens from air through end
  - Flash: red

- **"change tail air"** — ✅ Works
  - Same range, action is clearAndSetSelection
  - Cursor positioned at hat's original index (after deletion)

### past (same as tail)
- **"chuck past air"** — ✅ Works
  - Alias for tail modifier
  - Grammar dispatch: `chuck past <user.letter>` → `prose_overlay_delete_past_hat()`

### Range with scope
- **"chuck head word"** (scope + head modifier) — ✅ Works
  - Modifier stacking: `containingScope` + `extendThroughStartOf`
  - First applies scope (token at cursor), then head modifier
  - Resolves to `(0, cursor_idx)`

- **"chuck tail line"** (scope + tail modifier) — ✅ Works
  - Scope resolves to full buffer `(0, last)`, then tail modifier applied
  - Result: same as full buffer (tail of full buffer == full buffer)

---

## 6. Multi-Token Operations

### Selection spanning multiple tokens
- **"take air past bat"** — ✅ Works visually
  - Selection set on range `(air_idx, bat_idx)` inclusive
  - All tokens in range highlighted with blue 25% alpha rectangles
  - Selection persists in `instance.buffer._selection`

- **"change air past bat"** — ✅ Works
  - Deletes entire range
  - Cursor positioned at start of deleted range (original air position)
  - Enters change mode (amber cursor + insertion zone)

### Copy (bring) multi-token to single-token position
- **"bring air past bat to cap"** — ✅ Works (token granularity)
  - Source is range (air to bat = multiple tokens, but copied as single range)
  - JS shim returns insert plan at cap position
  - Inserts the multi-token text at cap, replacing cap's token
  - Visual: green flash on source tokens before executing

- **Gap:** "bring" copies the entire text range as a unit. If source is "hello world" (tokens: hello, world), destination (cap) becomes "hello world" (or just "hello" if cap only takes first token — check `replace_token()` which uses `words[0]`)
  - **Actually:** `replace_token()` only takes the first word: `self._tokens[index] = words[0]`
  - So "bring air past bat to cap" where air=hello, bat=world results in cap=hello (world is lost)

### Move multi-token to single-token position
- **"move air past bat to cap"** — ✅ Works (token granularity with caveat)
  - Source range copied, source deleted
  - Same caveat as bring: only first token of source survives the move

---

## 7. Known Gaps and Failure Modes

### Multi-token copy/move limitation
- **Command:** "bring air past bat to cap" where air="hello", bat="world"
- **Expected (real Cursorless):** cap becomes "hello world" (two-token replacement)
- **Actual:** cap becomes "hello" (only first token copied)
- **Reason:** `replace_token()` uses `words[0]` after splitting on whitespace
- **Impact:** Multi-word phrases can't be fully copied via bring/move; lose everything after first word
- **Fix available:** Switch from word-split to character-range replace. Cursorless's
  `ProseTextEditorEdit.replace(range, text)` in `proseShim.ts` handles multi-word correctly
  by treating the source as a character range, not individual tokens. Small adaptation.

### ListTarget multi-target AND expressions
- **Command:** "chuck air and bat"
- **Expected:** Deletes both air and bat
- **Actual:** Logs error "multi-target 'and' expressions are not supported", no-ops
- **Workaround:** Execute as two separate commands: "chuck air" then "chuck bat"
- **Fix available:** Cursorless's `TargetPipelineRunner.ts:90–95` handles ListTarget with a
  simple `target.elements.flatMap(...)`. Drop-in: iterate elements, resolve each to a token
  range, apply action to each independently.

### RangeTarget with implicit anchor
- **Command:** "chuck past this" (no explicit anchor, implicit range from current to target)
- **Expected (real Cursorless):** Range from cursor to target
- **Actual:** Logs error "RangeTarget with implicit anchor is not supported", returns None
- **Reason:** Code explicitly rejects `anchor.type == "implicit"` in range resolution
- **Fix available:** Cursorless's `ImplicitStage.ts` resolves implicit anchor by reading
  current selection from `ide()`. For prose overlay, replace that with `_resolve_state.cursor`.
  Small adaptation — one guard removal + cursor lookup.

### Unrecognized scope types (silent fail)
- **Command:** "chuck statement"
- **Expected:** Deletes statement-level scope
- **Actual:** Logs "unrecognized scope type 'statement'", returns None, command is no-op
- **Reason:** Only 8 scope types hardcoded; Cursorless has 50+
- **User experience:** No error feedback visible in overlay; only in Talon logs
- **Partial fix available (text-only scopes):** Several Cursorless scope types are pure regex
  with no language server dependency — extractable from `RegexScopeHandler.ts`:
  - `nonWhitespaceSequence` — regex `/\S+/g`
  - `url` — full URL regex
  - `character` — Unicode-aware `/\p{L}\p{M}*|.../gu`
  - `glyph` — arbitrary char match
  - `customRegex` — user-provided regex
  These are drop-in bundles. Parse-tree scopes (statement, function, class) can never be
  supported without a language server — those stay ❌.

### Non-ASCII hat allocation (Python fallback)
- **Command:** Using cursor position to trigger hat allocation for accented text (café, Zürich, etc.)
- **Expected (JS path):** Cursorless grapheme-aware allocation
- **Actual (JS path):** ✅ Works perfectly (using real Cursorless algorithm)
- **Actual (Python fallback if JS fails):** ⚠️ May misalign on multi-codepoint graphemes
  - Python fallback uses simple `ch.lower()` iteration, no NFC normalization
  - Example: if a token is "café" and the é is stored as e+combining-accent, Python might assign the hat wrong
- **Frequency:** JS path is primary (tries first), so Python fallback rarely hit

### No visual error feedback for unsupported actions
- **Command:** "scroll air" (VS Code-specific action)
- **Expected:** Error message shown to user
- **Actual:** Logs "unsupported action 'scroll' (VS Code-only?)", no-ops silently
- **User impact:** Command doesn't work, but no overlay-visible feedback; must check logs to debug

### Cursor-dependent actions without cursor
- **Command:** "chuck word" when no cursor is active
- **Expected:** Resolves to word at cursor position
- **Actual:** Logs "scope 'word' requires an active cursor", returns None, command is no-op
- **Workaround:** Set cursor first via "pre air" or "post air"

### Change mode semantics
- **"change air"** enters change mode; cursor is positioned at deleted token's index
- **"change head air"** enters change mode; cursor is positioned at start (0)
- **"change tail air"** enters change mode; cursor is positioned at tail's original index
- **Behavior:** All three enter change mode visually (amber cursor + insertion zone), but cursor positions differ
- **Note:** This is implementation-specific, not documented in Cursorless spec (prose overlay custom)

### Cursor blink off-phase renders no cursor
- **Behavior:** Cursor line disappears for 250ms, reappears for 250ms
- **Visual:** May appear to flicker
- **Expected (some editors):** Cursor always visible but dims or changes shape on off-phase
- **Impact:** Minor; standard blinking cursor behavior

### Hat dots beyond 26 tokens
- **Behavior:** Token indices 26+ have no hats rendered
- **User impact:** Can't target tokens beyond the first 26 via hat names
- **Workaround:** Use scope modifiers ("chuck file", "chuck line") or selection-based ranges ("take air past bat")

### Selection doesn't clear on all mutations
- **"take air"** sets selection `(air, air)` (one token)
- **"take air past bat"** sets selection `(air, bat)` (multiple tokens)
- **Then "add text"** (dictate new words) does NOT clear selection
- **Bug or feature?** Unclear from code; `add_text()` doesn't check `_selection`
- **Result:** Selection remains visually highlighted on old tokens while new tokens appear below
- **Suggested fix:** Clear selection in `add_text()` before appending

---

## Summary: What Works, What Doesn't

### Fully Working (✅)
- Single hat targets with or without color
- Range targets (anchor past active)
- Scope targets (8 types: file, line, block, token, word, identifier, char)
- Actions: remove, setSelection, clearAndSetSelection, setSelectionBefore/After
- Bring and move (hat-to-hat copy/cut)
- Bring/move to cursor position
- Visual feedback: flash highlight (all colors), selection highlight (blue), cursor (white/amber), hat dots (colors), cursor blink
- Head and tail range modifiers
- Undo stack (20 entries)
- Hat collision resolution (same letter, different colors)
- Implicit target (this / cursor position)

### Partially Working (⚠️)
- Multi-token copy/move (limited to first token)
- Char scope (resolves to entire token, not individual chars)
- Non-ASCII hats (JS path perfect, Python fallback lossy)
- Selection persistence (doesn't always clear; may highlight stale tokens)

### Not Implemented (❌)
- ListTarget (and expressions)
- RangeTarget with implicit anchor (past this)
- 40+ scope types (only 8 supported)
- VS Code-only actions (scroll, fold, wrap, etc.)
- Multi-codepoint grapheme support in Python fallback
- User-visible error messages (logs only)

---

## Testing Checklist

For someone doing live testing, here's what to verify:

- [ ] Single hat deletion: "chuck air"
- [ ] Colored hat: "chuck blue bat"
- [ ] Range: "chuck air past bat"
- [ ] Range with colors: "take blue air past green bat"
- [ ] Head modifier: "chuck head air"
- [ ] Tail modifier: "chuck tail air"
- [ ] Scope: "chuck word", "chuck line", "chuck file"
- [ ] Hat-to-hat copy: "bring air to bat"
- [ ] Hat-to-hat cut: "move air to bat"
- [ ] Copy to cursor: "bring air" (with cursor active)
- [ ] Selection visual: "take air past bat" (blue highlight visible?)
- [ ] Change mode: "change air" (cursor amber + insertion zone?)
- [ ] Cursor position: "pre air" (white cursor before token?)
- [ ] Cursor blink: Does cursor blink at 500ms interval?
- [ ] Hat display: Do colored dots appear above first letter?
- [ ] Multi-token source: "bring air past bat to cap" (does cap get both words or just first?)
- [ ] Undo: "undo" after "chuck air" (token restored?)
- [ ] Non-ASCII: Test with accented characters (é, ñ, ü, etc.) — do hats allocate correctly?
- [ ] Unsupported action: Try "scroll air" (does it fail gracefully with log?)
- [ ] No cursor error: Try "chuck word" without setting cursor first (does it fail with log?)
- [ ] Hat collision: Say two words start with 'a' — do they get gray-a and blue-a?

---

## Build Artifacts

For the JS hat allocation algorithm:

**File:** `/Users/trilliumsmith/.talon/user/trillium_talon/trillium/plugin/prose_overlay/js/prose_allocate_hats.js`

**Build command (if needed):**
```bash
cd ~/code/cursorless
bunx esbuild \
  packages/cursorless-engine/src/util/allocateHats/proseStandalone.ts \
  --bundle --format=iife --platform=browser --target=es2020 \
  "--alias:lodash-es=lodash" \
  --outfile=/Users/trilliumsmith/.talon/user/trillium_talon/trillium/plugin/prose_overlay/js/prose_allocate_hats.js
```

**Exported function:** `proseAllocateHats(tokensJson, oldAssignmentsJson, stability, cursorPosJson)`

**Risk:** If `proseStandalone.ts` changes in Cursorless upstream, bundle must be rebuilt.

