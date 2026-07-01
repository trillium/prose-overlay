# prose-overlay

A [Talon Voice](https://talonvoice.com) plugin that holds dictated text in a
floating buffer before sending it to a target window. Words appear with
[Cursorless](https://cursorless.org)-style hat markers — you can delete,
change, reorder, and reposition by hat before confirming.

Designed for hands-free prose editing: say a sentence, fix it by voice, send
it when it's right.

---

## What it looks like

The overlay is a narrow panel that attaches to the top or bottom of your target
window. Each word gets a hat (a small colored marker above one letter). You
address words by their hat — same muscle memory as Cursorless, same hat
allocation algorithm.

---

## Requirements

- [Talon Voice](https://talonvoice.com)
- [knausj_talon](https://github.com/talonhub/community) or compatible community scripts (for `raw_prose`, `letter`, `dictation_ender`, `saved_window_names`)
- [Cursorless](https://cursorless.org) _(optional — enables hat-targeted actions via `cursorless_target`)_

---

## Installation

Clone into your Talon `user/` directory:

```sh
cd ~/.talon/user
git clone https://github.com/trillium/prose-overlay
```

Or symlink from elsewhere:

```sh
ln -s ~/code/prose-overlay ~/.talon/user/prose-overlay
```

The plugin also depends on `overlay_kit` — a shared canvas utility from the
same author. _(Link TBD once published.)_

---

## Usage

Say **`prose overlay`** to open the buffer and start dictating. Words appear
with hats as you speak. Edit by hat, then say **`bravely`** to confirm and
paste to whatever window you were in.

**Auto mode** (`overlay auto`) intercepts all dictation automatically — every
phrase opens the overlay instead of going directly to the focused window.

---

## Commands

| Genre     | Command                    | Hint                                                    |
| --------- | -------------------------- | ------------------------------------------------------- |
| Global    | `prose overlay`            | Open the overlay                                        |
|           | `overlay auto`             | Toggle auto-dictation mode                              |
|           | `prose history`            | Toggle history panel                                    |
|           | `overlay top`              | Attach panel to top of window                           |
|           | `overlay bottom`           | Attach panel to bottom of window                        |
| Confirm   | `bravely`                  | Confirm and paste to target window                      |
|           | `<prose> bravely`          | Append prose then confirm                               |
|           | `<window> bravely`         | Retarget window then confirm                            |
|           | `overlay dismiss`          | Dismiss without pasting                                 |
| Dictation | `<prose>`                  | Append spoken text to buffer                            |
|           | `<window> <prose>`         | Focus window then append prose                          |
|           | `{symbol}`                 | Route symbol key into buffer                            |
| Delete    | `chuck <hat>`              | Delete word at hat                                      |
|           | `chuck past <hat>`         | Delete hat through end of buffer                        |
|           | `chuck head <hat>`         | Delete start of buffer through hat                      |
|           | `chuck tail <hat>`         | Delete hat through end of buffer                        |
| Cursor    | `pre <hat>`                | Move insertion cursor before hat                        |
|           | `post <hat>`               | Move insertion cursor after hat                         |
|           | `pre file`                 | Move cursor to start of buffer                          |
|           | `post file`                | Move cursor to end of buffer                            |
| Edit      | `change <hat>`             | Delete word at hat, enter insert mode                   |
|           | `change head <hat>`        | Delete start→hat, enter insert mode                     |
|           | `change tail <hat>`        | Delete hat→end, enter insert mode                       |
|           | `change <hat> <prose>`     | Delete word, insert replacement prose                   |
|           | `pre <hat> <prose>`        | Set cursor before hat, insert prose                     |
|           | `post <hat> <prose>`       | Set cursor after hat, insert prose                      |
|           | `overlay undo`             | Undo last buffer edit                                   |
| Move      | `bring <hat> to <hat>`     | Copy word at src to dst position                        |
|           | `move <hat> to <hat>`      | Cut word at src, replace dst                            |
| Rearrange | `swap <hat> with <hat>`    | Swap two target texts (wishlist #3)                     |
|           | `clone <hat>`              | Duplicate target after itself (wishlist #12)            |
|           | `clone up <hat>`           | Duplicate target before itself                          |
|           | `reverse <hat> past <hat>` | Reverse token order in range (wishlist #13)             |
|           | `reverse <hat> and <hat>`  | Reverse two targets (list form)                         |
| Wrap      | `round wrap <hat>`         | Wrap target in ( ) — wishlist #5                        |
|           | `curly wrap <hat>`         | Wrap target in { }                                      |
|           | `box wrap <hat>`           | Wrap target in [ ]                                      |
|           | `quad wrap <hat>`          | Wrap target in double quotes                            |
|           | `twin wrap <hat>`          | Wrap target in single quotes                            |
|           | `diamond wrap <hat>`       | Wrap target in < >                                      |
|           | `skis wrap <hat>`          | Wrap target in backticks                                |
|           | `void wrap <hat>`          | Wrap target in spaces (whitespace)                      |
|           | `escaped round wrap <hat>` | Wrap target in \\( \\)                                  |
|           | `escaped curly wrap <hat>` | (reserved — escaped variant families)                   |
|           | `escaped quad wrap <hat>`  | Wrap target in \\" \\"                                  |
|           | `escaped twin wrap <hat>`  | Wrap target in \\' \\'                                  |
|           | `escaped box wrap <hat>`   | Wrap target in \\[ \\]                                  |
| Modifier  | `take first word`          | OrdinalScope — first word in buffer (wishlist #7)       |
|           | `take last word`           | OrdinalScope — last word                                |
|           | `take next word <hat>`     | RelativeScope — word after hat (wishlist #6)            |
|           | `take every word in file`  | EveryScope — all words in buffer (wishlist #9, partial) |
|           | `chuck leading <hat>`      | Leading modifier — degenerate on prose (wishlist #11)   |
|           | `chuck trailing <hat>`     | Trailing modifier — degenerate on prose                 |
| Pair      | `take inside round <hat>`  | Interior of paired delimiter (wishlist #8)              |
|           | `take bounds round <hat>`  | The two delimiter tokens as bounds                      |
| Colors    | `chuck <color> <hat>`      | Target a colored hat (collision avoidance)              |
|           | `pre <color> <hat>`        | Cursor before colored hat                               |
|           | `change <color> <hat>`     | Edit at colored hat                                     |
| Controls  | `overlay speak`            | Read buffer aloud via TTS                               |
|           | `overlay help`             | Toggle paginated help panel                             |
|           | `overlay anchor`           | Scope panel to current window width                     |
|           | `overlay anchor clear`     | Full-screen panel (no window scope)                     |
| History   | `prose history`            | Show/hide history panel (last 50 phrases)               |
|           | `history next`             | Next history page                                       |
|           | `history back`             | Previous history page                                   |
|           | `history pick <N>`         | Load history entry N into buffer                        |

> Regenerate this table: `bun scripts/gen-command-table.ts`
>
> **Cluster C modifiers (`take first`, `take next`, `every`, `leading`, `trailing`)** ride
> the composable `<user.cursorless_target>` capture through the JS resolver — no dedicated
> prose_overlay grammar rule. Python-fallback (`user.prose_overlay_use_js_resolver = false`)
> does NOT cover them; JS-only. Leading/trailing are degenerate on flat prose per
> `docs/BUNDLE_REST_SCOPE.md §7` (OQ3 resolution).
>
> **Cluster B wrap** exposes all 12 delimiters via cursorless-talon's
> `cursorless_wrapper_paired_delimiter` capture (see `~/.talon/user/cursorless-talon/src/paired_delimiter.py:28-42`).

---

## Hat colors

When two words would get the same hat letter, Cursorless-style color promotion
kicks in. Prefix any hat command with a color to target the right one:

```
chuck blue air
pre red bat
change green cap
```

Available colors: `blue`, `green`, `red`, `pink`, `yellow`, `gray` (default, no prefix needed).

---

## History panel

Every confirmed phrase is saved (up to 50). Say `prose history` to open the
panel, `history pick 3` to reload entry 3 into the buffer for re-editing.

---

## Settings

| Setting                                              | Default | Description                                                                         |
| ---------------------------------------------------- | ------- | ----------------------------------------------------------------------------------- |
| `user.prose_overlay_window_scoped`                   | `true`  | Scope panel width/position to target window                                         |
| `user.prose_overlay_use_cursorless_shape_allocator`  | `false` | Opt-in: use cursorless's native shape-aware hat allocator instead of the Python one |

Panel vertical position (`overlay top` / `overlay bottom`) is persisted across
restarts.

---

## License

MIT
