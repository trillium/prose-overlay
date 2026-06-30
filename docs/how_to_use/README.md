# How To Use — Prose Overlay

User-facing voice command reference. One file per feature; each
describes what the feature does, the voice commands that invoke it,
worked examples, and known caveats.

Distinct from:
- `docs/FEATURE_PARITY.md` — engineering checklist of what's shipped
- `docs/*_PLAN.md` — design docs for in-flight or proposed work
- `ISA.md` — project system-of-record

Read this if you're using the overlay and want to know what to say.

## Per-feature pages

### Lifecycle

- [`show_dismiss.md`](show_dismiss.md) — open, dismiss, reset, clear buffer

### Input

- [`dictation.md`](dictation.md) — speaking prose into the buffer
- [`characters.md`](characters.md) — NATO letters, symbols, digits (char-level input)
- [`formatters.md`](formatters.md) — `snake`, `camel`, `say`, `sentence`, `title`, etc.

### Editing (hat-targeted)

- [`hat_edits.md`](hat_edits.md) — `chuck`, `take`, `change`, `clear`, `replace`
- [`cursor.md`](cursor.md) — `pre`, `post`, cursor positioning
- [`scopes.md`](scopes.md) — `chuck sentence`, `take string`, `chuck file`, etc.
- [`surrounding_pairs.md`](surrounding_pairs.md) — `take round`, `chuck quad`, etc.
- [`bring_move.md`](bring_move.md) — `bring`, `move`, `swap`

### Undo / redo

- [`undo_redo.md`](undo_redo.md) — `overlay undo`, `overlay redo`, coalescing toggle

### Selection

- [`selection.md`](selection.md) — `take <hat>`, range/list selections

### Homophone surface

- [`homophone_underline.md`](homophone_underline.md) — amber dotted underline (always-on flag)
- [`homophone_shapes.md`](homophone_shapes.md) — shape hats (`bolt`, `wing`, `frame`, …); same group = same shape
- [`phones.md`](phones.md) — `phone <shape>` / `phones <word>` / `<color> <shape>` swap actions

### History

- [`history.md`](history.md) — `prose history`, `history pick N`, line-ender direct paste

### Window targeting

- [`window_anchor.md`](window_anchor.md) — `overlay anchor`, retarget, saved window names

### Help

- [`help_panel.md`](help_panel.md) — `overlay help`, `help bigger`/`smaller`, `help next`/`back`

### Debug / observability

- [`debug.md`](debug.md) — `overlay debug on/off`, `overlay dump`
- [`test_driver.md`](test_driver.md) — headless test queue (`scripts/test-overlay.sh`)

## Page template

When adding a new feature page, follow the shape established in `history.md`:

```markdown
# Feature Name

> One-line summary in italics.

## Voice commands

- `command 1` — what it does
- `command 2` — what it does

## How it works

(2-4 sentences on the mental model)

## Examples

### Example 1: <scenario name>

You say:
\`\`\`
Step 1
Step 2
\`\`\`
Result: ...

## Caveats

- known gap / surprise / edge case

## Source

- Action: `<dir>/<file>.py:<function_name>`
- Grammar: `<file>.talon`
- Plan: `docs/<PLAN>.md` (if applicable)
- ISC: ISC-N (if applicable)
```

Status legend at the top is OPTIONAL; only add if the feature is partial
or in-dev. Shipped features don't need a status line.
