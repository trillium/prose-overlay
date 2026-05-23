# Cursorless Reimplementations

Active index of every Cursorless feature that prose overlay has custom-built
or approximated. Maintained here because drift from real Cursorless is the
most likely source of future breakage.

**Last audited:** 2026-05-23

---

## 1. Hat Allocation

**What Cursorless does:** Assigns unique (letter, color) pairs to editor tokens
using a penalty-based scoring algorithm with full grapheme normalization,
deburring, and unicode NFC.

**What we do:** Two implementations, JS-primary with Python fallback.

- **JS (primary):** `prose_overlay_hats_js.py` — loads the actual Cursorless
  `allocateHats` algorithm via Talon's QuickJS engine. Bundle built from
  `packages/cursorless-engine/src/util/allocateHats/proseStandalone.ts`.
  Passes all data as JSON strings (not native objects) to avoid a confirmed
  QuickJS call stack overflow when crossing JS→Python via `NewProxy`.
- **Python (fallback):** `prose_overlay_state.py:16–88` — proximity-sort,
  two-pass collision resolution, gray-first. ASCII only, no grapheme support.

**Gaps vs real Cursorless:**
- Python fallback: single character per token only; may misalign on accented
  characters or multi-codepoint graphemes
- No configurable stability parameter in the Python path

**Risk:** Medium — JS path is full Cursorless; Python path degrades gracefully
for ASCII. Non-ASCII is the edge case.

---

## 2. Target Resolution

**What Cursorless does:** Resolves spoken targets (PrimitiveTarget, RangeTarget,
ListTarget) to VS Code selections, with 50+ scope types and full modifier
stacking.

**What we do:** `prose_overlay_cursorless_resolve.py` — resolves targets to
`(first_token_idx, last_token_idx)` in the flat token array.

**Supported target types:**
- PrimitiveTarget with decorated symbol mark
- RangeTarget (anchor past active)
- ImplicitTarget (cursor position)

**NOT supported:**
- ListTarget (`and` expressions) — returns None, logs warning
- RangeTarget where anchor is ImplicitTarget

**Supported scope types (hardcoded at `prose_overlay_cursorless_resolve.py:58–73`):**

| Scope type | Spoken form | Resolves to |
|---|---|---|
| `document` | "file" | full buffer (0, last) |
| `line` | "line" | full buffer (single-line buffer) |
| `paragraph` | "block" | full buffer |
| `fullLine` | "full line" | full buffer |
| `token` | "token" | single token at cursor |
| `word` | "sub" | single token at cursor |
| `identifier` | "identifier" | single token at cursor |
| `character` | "char" | single token at cursor |

All other scope types → None + log. Real Cursorless has 50+.

**Risk:** High for scope type coverage — any unrecognized scope type fails
silently. Scope names are string-matched exactly; Cursorless renames would
break us without warning.

---

## 3. Actions

**What Cursorless does:** 60+ actions covering deletion, selection, code
transformation, navigation, snippets, formatting, etc.

**What we do:** 5 actions via `prose_overlay_actions_cursorless.py` and
`prose_overlay_actions_js.py`:

| Action name | Spoken via Cursorless | What we do |
|---|---|---|
| `remove` | "chuck \<target>" | delete token range from buffer |
| `setSelection` | "take \<target>" | set selection (highlight) |
| `clearAndSetSelection` | "change \<target>" | delete range + enter change mode |
| `setSelectionBefore` | "pre \<target>" | cursor before target |
| `setSelectionAfter` | "post \<target>" | cursor after target |

**Plus hat-to-hat operations (not from Cursorless grammar):**
- `bring <src> to <dst>` → `replaceWithTarget` (token granularity only)
- `move <src> to <dst>` → `moveToTarget` (token granularity only)

All other Cursorless actions log `"VS Code-only?"` and no-op.

**Risk:** Medium — users who know Cursorless will try unsupported actions; the
error message is visible only in Talon logs, not spoken or shown in overlay.

---

## 4. Edit Plan Execution (JS Shim)

**What Cursorless does:** Executes actions via VS Code extension API with full
AST awareness, multi-line support, language-specific formatting.

**What we do:** `js/prose_actions.js` — a minimal VS Code editor API simulation
that operates on a flat single-line string. Takes an action name + character
ranges and returns a declarative edit plan (list of {type, range, text} ops).
`_apply_edit_plan()` in `prose_overlay_actions_cursorless.py` applies the plan
to `instance.buffer` by rebuilding the token list from the modified flat string.

**Edit types:** delete, insert, replace

**Gaps:** No AST, no language awareness, no multi-line, no reversed selections.
All edits are single-line character-range geometry. This is intentional —
prose overlay is for single-sentence dictation, not code editing.

**Risk:** Low — fits the use case by design.

---

## 5. Color Mapping

**What Cursorless does:** Uses `"default"` as the name for the no-color hat.

**What we do:** Map `"default"` → `"gray"` at
`prose_overlay_cursorless_resolve.py:54–55`.

```python
_CURSORLESS_TO_PROSE_COLOR = {"default": "gray"}
```

All other color names pass through unchanged. Prose-specific colors:
gray, blue, green, red, pink, yellow, purple, black, white.

**Risk:** Low — single translation point, easy to extend.

---

## 6. Head / Tail Deletion Grammar

**What Cursorless does:** "chuck tail X" is not native Cursorless syntax;
head/tail modifiers come from Cursorless's `extendThroughStartOf` /
`extendThroughEndOf` modifier stacking.

**What we do:** Explicit grammar rules in `prose_overlay_cursorless.talon`
with direct Python dispatch:

- `chuck head <letter>` → `prose_overlay_delete_head_hat()` — delete 0..token
- `chuck tail <letter>` → `prose_overlay_delete_tail_hat()` → delegates to
  `prose_overlay_delete_past_hat()` — delete token..end
- `chuck past <letter>` → `prose_overlay_delete_past_hat()` — same as tail

**Risk:** Low — intentional simplification; works correctly.

---

## 7. Grammar Specificity Override

**What Cursorless does:** Its own `.talon` files capture "bring", "move",
"chuck", "take", etc. in command mode when Cursorless is active.

**What we do:** `prose_overlay_cursorless.talon` matches on BOTH
`tag: user.cursorless` AND `tag: user.prose_overlay_active` AND both modes.
This gives our rules higher specificity than Cursorless's rules, so our
handlers win when the overlay is open.

**Risk:** Medium — depends on Talon's specificity system behaving as expected.
If Cursorless adds further matchers to increase its own specificity, our rules
could lose. Must re-audit whenever Cursorless grammar files change.

---

## 8. Implicit Target (Cursor Position)

**What Cursorless does:** ImplicitTarget represents the current editor
selection, usable as an anchor or active in range targets.

**What we do:** ImplicitTarget resolves to the single token at
`_resolve_state.cursor` (the gap index). Supported as a standalone mark;
NOT supported as the anchor half of a RangeTarget
(`prose_overlay_cursorless_resolve.py:214–218`).

**Risk:** Medium — "chuck X past this" style commands fail silently.

---

## Known Gaps (not yet addressed)

- **ListTarget:** Multi-target `and` expressions not supported.
- **Range+Implicit anchor:** `chuck air past this` not supported.
- **Unsupported action feedback:** Failures are log-only, not visible to user.
- **Scope type extensibility:** List is hardcoded; no registration mechanism.
- **Non-ASCII hat allocation:** Python fallback may misalign on accented chars.
