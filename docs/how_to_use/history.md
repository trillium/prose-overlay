# History

> *Pick a previously confirmed prose entry and bring it back to the overlay or paste it directly.*

## Voice commands

- `prose history` — open the history panel (works inside or outside the overlay)
- `history pick <N>` — load entry N into the overlay buffer for editing
- `history pick <N> bravely` — paste entry N directly to the target window, no overlay editing step (any [dictation ender](dictation.md) works, not just "bravely")
- `history next` / `history back` — paginate through history pages
- `overlay dismiss` — close the history panel without picking anything

## How it works

The overlay tracks the last 50 successfully `confirm`-ed buffers in a session-local history list. Each `confirm` pushes the text to slot 0 (most recent first); older entries shift down. The panel renders pages of entries; you pick by spoken number.

There are **two pick modes**:

1. **Pick to edit** (`history pick N`) — overlay opens with the entry pre-loaded; you can edit before confirming.
2. **Pick to paste** (`history pick N <ender>`) — entry pastes directly to the target window. Useful when you know the recovered text is correct as-is.

## Examples

### Example 1: Recover a buffer after a technical failure

You dictated some text, said `bravely` to confirm, but the paste went to the wrong window. Recover and re-paste:

```
You: prose history
       [history panel opens, listing recent entries with numbers]
You: history pick 1
       [overlay opens with the most recent entry pre-loaded]
       [you can edit, set cursor, change hats, etc.]
You: bravely
       [overlay confirms and pastes to the now-correct target window]
```

### Example 2: Quick re-paste with no editing

The recovered text is already correct — skip the editing step:

```
You: prose history
You: history pick 1 bravely
       [entry 1 pastes directly to the target window; no overlay editing]
```

### Example 3: Find an older entry

```
You: prose history
       [page 1: entries 1-10]
You: history next
       [page 2: entries 11-20]
You: history pick 14
       [entry 14 loads into the overlay]
```

## Caveats

- **History only captures on `confirm`** — text dictated but dismissed or lost to a mid-utterance crash isn't in history. For that case, see [`debug.md`](debug.md) — `~/.talon/prose_overlay_debug.jsonl` records every state diff and can be grepped for the lost buffer's tokens.
- **Session-local only** — history is cleared when Talon restarts.
- **50-entry cap** — older entries are evicted (oldest first).
- `history pick <N> bravely` accepts any [dictation ender](dictation.md) (`bravely`, `gravely`, `slap`, `lap`) — they all behave the same.

## Source

- Actions: `ui/actions_history.py:prose_overlay_history_pick`, `prose_overlay_history_paste`
- Grammar: `prose_overlay_history.talon` (panel-active context), `prose_overlay_start.talon` (`prose history` from outside the overlay)
- History list lives in `instance.history` on `ProseOverlayState`
