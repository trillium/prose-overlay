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

| Genre     | Command                | Hint                                       |
| --------- | ---------------------- | ------------------------------------------ |
| Global    | `prose overlay`        | Open the overlay                           |
|           | `overlay auto`         | Toggle auto-dictation mode                 |
|           | `prose history`        | Toggle history panel                       |
|           | `overlay top`          | Attach panel to top of window              |
|           | `overlay bottom`       | Attach panel to bottom of window           |
| Confirm   | `bravely`              | Confirm and paste to target window         |
|           | `<prose> bravely`      | Append prose then confirm                  |
|           | `<window> bravely`     | Retarget window then confirm               |
|           | `overlay dismiss`      | Dismiss without pasting                    |
| Dictation | `<prose>`              | Append spoken text to buffer               |
|           | `<window> <prose>`     | Focus window then append prose             |
|           | `{symbol}`             | Route symbol key into buffer               |
| Delete    | `chuck <hat>`          | Delete word at hat                         |
|           | `chuck past <hat>`     | Delete hat through end of buffer           |
|           | `chuck head <hat>`     | Delete start of buffer through hat         |
|           | `chuck tail <hat>`     | Delete hat through end of buffer           |
| Cursor    | `pre <hat>`            | Move insertion cursor before hat           |
|           | `post <hat>`           | Move insertion cursor after hat            |
|           | `pre file`             | Move cursor to start of buffer             |
|           | `post file`            | Move cursor to end of buffer               |
| Edit      | `change <hat>`         | Delete word at hat, enter insert mode      |
|           | `change head <hat>`    | Delete start→hat, enter insert mode        |
|           | `change tail <hat>`    | Delete hat→end, enter insert mode          |
|           | `change <hat> <prose>` | Delete word, insert replacement prose      |
|           | `pre <hat> <prose>`    | Set cursor before hat, insert prose        |
|           | `post <hat> <prose>`   | Set cursor after hat, insert prose         |
|           | `overlay undo`         | Undo last buffer edit                      |
| Move      | `bring <hat> to <hat>` | Copy word at src to dst position           |
|           | `move <hat> to <hat>`  | Cut word at src, replace dst               |
| Colors    | `chuck <color> <hat>`  | Target a colored hat (collision avoidance) |
|           | `pre <color> <hat>`    | Cursor before colored hat                  |
|           | `change <color> <hat>` | Edit at colored hat                        |
| Controls  | `overlay speak`        | Read buffer aloud via TTS                  |
|           | `overlay help`         | Toggle paginated help panel                |
|           | `overlay anchor`       | Scope panel to current window width        |
|           | `overlay anchor clear` | Full-screen panel (no window scope)        |
| History   | `prose history`        | Show/hide history panel (last 50 phrases)  |
|           | `history next`         | Next history page                          |
|           | `history back`         | Previous history page                      |
|           | `history pick <N>`     | Load history entry N into buffer           |

> Regenerate this table: `bun scripts/gen-command-table.ts`

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

| Setting                            | Default | Description                              |
| ---------------------------------- | ------- | ---------------------------------------- |
| `user.prose_overlay_window_scoped` | `true`  | Scope panel width/position to target window |

Panel vertical position (`overlay top` / `overlay bottom`) is persisted across
restarts.

---

## License

MIT
