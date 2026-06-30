# Character Input — NATO letters, symbols, digits

> *Character-at-a-time inputs (single letter, single symbol, single digit) extend the token at the cursor instead of producing new tokens. Text-editor mental model — like typing one key at a time.*

## Voice commands

### Letters (NATO alphabet)

- `<letter-name>` — single letter input. Talon's standard NATO alphabet: `air bat cap drum each fine gust harp sit jury crunch look made near odd pit quench red sun trap urge vest whale plex yank zip` → `a b c d e f g h i j k l m n o p q r s t u v w x y z`
- Multiple in a row: `air bat cap` → `abc` extends as one token

### Symbols

- `<symbol-name>` — single symbol input. Common ones: `dot` → `.`, `downscore` → `_`, `dash` → `-`, `slash` → `/`, `quote` → `"`, `bang` → `!`, `at sign` → `@`, etc. (Full list: trillium_talon `symbol_key` list.)

### Digits

- Spoken digit names extend the token too: `one two three` → `123` (community grammar; routed through the prose overlay's char-extension path when relevant)

## How it works

Single-character voice inputs route through `prose_overlay_add_chars` (not `add_text`). The behavior:

- **No cursor active + buffer is non-empty** → extends the **last token** with the new chars. So `bubble` (word) followed by `downscore trap odd pit` (4 chars) yields one token `bubble_top`.
- **Empty buffer or cursor positioned** → falls through to `add_text`, which creates a new token (or inserts at cursor).

This is the "text editor" model — you can build identifiers, snake_case names, or any compound token by speaking one char at a time. The buffer doesn't fragment into 5 separate tokens just because you spoke 5 short voice commands.

## Examples

### Example 1: Build a snake_case identifier

```
You: bubble
       [buffer: ["bubble"]]
You: downscore
       [buffer: ["bubble_"]] — symbol extended the last token
You: trap
       [buffer: ["bubble_t"]]
You: odd
       [buffer: ["bubble_to"]]
You: pit
       [buffer: ["bubble_top"]]
```

Result: **one** token, `bubble_top`. Not five tokens.

### Example 2: NATO letters at the end

```
You: hello world
       [buffer: ["hello", "world"]]
You: bat air dee
       [buffer: ["hello", "world_bad"]] — wait that's 3 chars; actually:
       [buffer: ["hello", "worldbad"]] — three chars extending "world"
```

### Example 3: Symbol mid-sentence

```
You: file
       [buffer: ["file"]]
You: dot
       [buffer: ["file."]]
You: trap shocks tear
       [buffer: ["file.txt"]] — 3 letter chars extending "file."
```

You just built `file.txt` as a single token through voice.

## Caveats

- **Cursor-targeted character insertion** (mid-token, char-level) is NOT yet shipped. With the cursor inside a token, character input still falls back to `add_text` (creating a new gap-token). The text-editor mid-token-typing model is a planned future slice (see `docs/FEATURE_PARITY.md §2`).
- The boundary "what counts as a single char" is set by Talon's `<user.letter>` and `<user.symbol_key>` captures — those decide which spoken phrases route to char-extension. Multi-word voice phrases (`hello world`) always create new tokens.
- **Digit voice grammar** (`one two three` → `123`) routes through `<user.number_string>` which currently uses `add_text`, not `add_chars`. So `one two three` becomes one token `123` (the string is joined first); separate utterances of single digit names don't currently chain via char-extension. Will revisit if it matters.

## Source

- Actions: `ui/actions_history.py:prose_overlay_add_chars` (extension logic), `prose_overlay_add_letters` (alias for back-compat)
- Grammar: `prose_overlay.talon` (the `<user.letters>` and `{user.symbol_key}` rules in the overlay-active context)
- Buffer side: `internal/state.py:ProseBuffer.set_tokens_raw` inside a `commit_start`/`commit_end` bracket → single undo step per char extension
- Related: [`dictation.md`](dictation.md) for word-level input, [`undo_redo.md`](undo_redo.md) for the bracket model
