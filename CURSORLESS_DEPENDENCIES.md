# Cursorless Dependencies

Active index of everything prose overlay relies on from real Cursorless —
grammar captures, spoken forms, JS algorithms, and structural conventions.
If Cursorless changes these, prose overlay breaks.

**Last audited:** 2026-05-23

---

## 1. Grammar Captures (Talon)

These captures are defined by Cursorless's `.talon-list` and `.py` files.
Prose overlay uses them directly in `prose_overlay_cursorless.talon`.

| Capture | Where defined | What it provides |
|---|---|---|
| `{user.cursorless_simple_action}` | Cursorless community files | Spoken action names: "chuck", "take", "change", "pre", "post", etc. |
| `{user.cursorless_target}` | Cursorless community files | Full target grammar: hat marks, scope modifiers, range syntax |
| `{user.cursorless_bring_move_action}` | Cursorless community files | "bring" and "move" spoken forms |
| `{user.cursorless_decorated_symbol}` | Cursorless community files | Single hat reference: color + letter |
| `{user.letter}` | knausj / community | Single letter capture |
| `tag: user.cursorless` | Cursorless | Tag set when Cursorless extension is active |

**Risk:** If Cursorless renames any of these captures, prose overlay's `.talon`
files silently stop matching — no error, commands just don't fire.

**Where to check:** `~/.talon/user/cursorless-talon/` for capture definitions.

---

## 2. Hat Allocation Algorithm (JS)

**Dependency:** `packages/cursorless-engine/src/util/allocateHats/proseStandalone.ts`
in the Cursorless source repo (`~/code/cursorless/`).

**How we use it:** Compiled to `js/prose_allocate_hats.js` via esbuild, loaded
into Talon's QuickJS engine by `prose_overlay_hats_js.py`.

**Build command:**
```bash
cd ~/code/prose-overlay
bun scripts/build-js.ts hats     # this bundle
bun scripts/build-js.ts targets  # the target/scope resolver (see §4)
bun scripts/build-js.ts all      # both, with size-ratio check
```
The script writes into `~/code/prose-overlay/js/`; `sync-to-talon.ts` then
propagates the bundle to the live Talon dir. Override the cursorless source
location with `CURSORLESS_DIR=…` if you're not using `~/code/cursorless`.

**Exported function:** `proseAllocateHats(tokensJson, oldAssignmentsJson, stability, cursorPosJson)`

**What we rely on:**
- Function name `proseAllocateHats` on the global scope (IIFE bundle)
- JSON input/output contract (all args and return value are JSON strings)
- Stability parameter: `"greedy"` | `"balanced"` | `"stable"`
- Output shape: `{"0": {"charIdx": N, "letter": "a", "color": "gray"}, ...}`

**Risk:** High — if Cursorless changes the `proseStandalone.ts` export name,
input/output contract, or removes the file, the bundle breaks. Must rebuild
bundle after any Cursorless update that touches `allocateHats/`.

**Fallback:** Python implementation in `prose_overlay_state.py:16–88` activates
automatically if JS load or call throws.

---

## 3. Target Object Shape (Python dict)

When Cursorless grammar fires and passes a `cursorless_target` to our action,
the Python dict we receive follows Cursorless's internal serialization format.

**Fields we parse in `prose_overlay_cursorless_resolve.py`:**

```python
# PrimitiveTarget
{
    "type": "primitive",
    "mark": {
        "type": "decoratedSymbol",
        "symbolColor": "default" | "blue" | "green" | ...,
        "character": "a"
    },
    "modifiers": [
        {"type": "containingScope", "scopeType": {"type": "word"}},
        {"type": "extendThroughStartOf"},
        {"type": "extendThroughEndOf"},
        # ... etc
    ]
}

# RangeTarget
{
    "type": "range",
    "anchor": <PrimitiveTarget>,
    "active": <PrimitiveTarget>,
    "excludeAnchor": bool,
    "excludeActive": bool
}

# ImplicitTarget
{"type": "implicit"}
```

**Risk:** High — if Cursorless changes its target serialization format (field
names, type strings, nesting), `prose_overlay_cursorless_resolve.py` breaks
silently. The parser uses direct dict key access with no schema validation.

**Where to check:** Cursorless's `packages/cursorless-engine/src/core/types/`
for target type definitions.

---

## 4. Action Name Strings

Cursorless action names are passed as strings via `{user.cursorless_simple_action}`
and `{user.cursorless_bring_move_action}`.

**Names we handle:**

| String | Source |
|---|---|
| `"remove"` | cursorless "chuck" |
| `"setSelection"` | cursorless "take" |
| `"clearAndSetSelection"` | cursorless "change" |
| `"setSelectionBefore"` | cursorless "pre" |
| `"setSelectionAfter"` | cursorless "post" |
| `"replaceWithTarget"` | cursorless "bring" |
| `"moveToTarget"` | cursorless "move" |

**Where used:** `_SUPPORTED_SIMPLE_ACTIONS` frozenset in
`prose_overlay_actions_cursorless.py:46–52`, `_action_color()` map in
`prose_overlay_actions_flash.py:53–62`.

**Risk:** Medium — if Cursorless renames an action string, it will fall through
to the "VS Code-only?" log and no-op. Not a crash, but commands silently stop
working.

**Where to check:** `packages/cursorless-engine/src/generateSpokenForm/defaultSpokenForms/actions.ts`
in the Cursorless source.

---

## 5. Color Names

Cursorless hat colors are passed as `symbolColor` strings in the target dict.

**Colors Cursorless uses:**
`"default"`, `"blue"`, `"green"`, `"red"`, `"pink"`, `"yellow"`,
`"purple"`, `"black"`, `"white"`

**Our mapping:** `"default"` → `"gray"` (see `CURSORLESS_REIMPLEMENTATIONS.md §5`).
All others pass through as-is.

**Risk:** Low — color names are stable; mapping is a single dict.

---

## 6. `tag: user.cursorless` Tag

Cursorless sets this tag when its VS Code extension is connected and the Talon
integration is active.

**How we use it:** `prose_overlay_cursorless.talon` requires this tag as a
context matcher. This means our Cursorless-routed commands only fire when
real Cursorless is loaded, which prevents false matches when Cursorless is
absent (e.g., in a non-VS Code context).

**Risk:** Low — if Cursorless ever renames this tag, our context stops matching.

---

## Update Checklist

Run this checklist after any Cursorless update (`git pull` in `~/code/cursorless/`):

- [ ] Did `proseStandalone.ts` change? → Rebuild `js/prose_allocate_hats.js`
- [ ] Did target type field names change? → Audit `prose_overlay_cursorless_resolve.py`
- [ ] Did action name strings change? → Update `_SUPPORTED_SIMPLE_ACTIONS` + `_action_color()`
- [ ] Did capture names change? → Update `prose_overlay_cursorless.talon`
- [ ] Did color name strings change? → Update `_CURSORLESS_TO_PROSE_COLOR`
- [ ] Did the `tag: user.cursorless` tag name change? → Update `.talon` context headers
