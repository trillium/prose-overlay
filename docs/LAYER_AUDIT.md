# Layer Audit — Portability Substrate

> Companion runner: `scripts/layer-audit.py`. Integrated as Layer 4 of
> `scripts/headless-verify.py`. Status: **RED** (3 known overfits; see §3).
>
> The audit is the meta-test that proves prose-overlay's substrate is
> portable. If it goes green, the INTERNAL + CURSORLESS layers can be
> dropped into VS Code / Vim / web / any other environment by writing a
> different SHIM and UI. If it goes red, that claim is currently false —
> the failures name exactly where talon/canvas code has leaked into what
> should be environment-agnostic.

## 1. Layers

Top → bottom in dependency direction (UI calls SHIM calls {CURSORLESS, INTERNAL}; nothing calls UI).

### 4. UI — Talon-specific render + voice surface

Freely Talon-bound. Owns the Skia canvas, the action classes, the voice grammar (`.talon` files), and the orchestration in `prose_overlay.py`.

Files (16):
- `prose_overlay.py` — Module/Context/tag wiring, settings, top-level imports
- `prose_overlay_canvas.py` — Skia canvas wrapper
- `prose_overlay_draw.py`, `prose_overlay_draw_tokens.py` — Skia paint
- `prose_overlay_help.py`, `prose_overlay_history_panel.py` — panel render
- `prose_overlay_actions_*.py` — Talon `@mod.action_class` classes (bring_move, cursor, delete, flash, help, history, layout, visibility)
- `prose_overlay_test_driver.py` — Talon `cron.interval` polling

### 3. SHIM — Talon ↔ {CURSORLESS, INTERNAL} bridges

The ONLY layer allowed to import both Talon AND internal-logic primitives. Replace this layer to port to another environment.

Files (8):
- `prose_overlay_hats_js.py` — Talon → QuickJS bridge for cursorless hat allocator (talon.lib.js)
- `prose_overlay_targets_js.py` — Talon → QuickJS bridge for cursorless target resolver
- `prose_overlay_actions_js.py` — Talon action methods invoking the JS bridges
- `prose_overlay_actions_cursorless.py` — Talon action surface routing to cursorless verbs
- `prose_overlay_actions_cursorless_edit.py` — applies edit plans from the resolver
- `prose_overlay_actions_target.py` — target dispatch shim
- `prose_overlay_actions_core.py` — `_recompute_hats`, `_hat_to_index` (Talon-state mgmt across layers)
- `prose_overlay_shapes.py` — SVG vocab (portable) + Skia paint (Talon, LAZY-imported at call site)

### 2. CURSORLESS — Python re-impl of cursorless processing

Pure logic. Portable to any environment with a token/text buffer. The JS bundles in `js/` are also cursorless layer but live as build artifacts.

Files (2):
- `prose_overlay_cursorless_resolve.py` — Python re-impl of processTargets
- `prose_overlay_surrounding_pair.py` — delimiter pair resolver

### 1. INTERNAL — Pure substrate

Environment-agnostic. ProseBuffer + undo/redo + hat allocation Python fallback + homophone CSV + viewport math + JSONL debug. Should import nothing from talon at any level.

Files (7):
- `prose_overlay_state.py` (561 LOC — the substrate)
- `prose_overlay_instance.py` — shared state container
- `prose_overlay_homophones.py` — CSV loader + flag lookup
- `prose_overlay_debug.py` — JSONL snapshot writer
- `prose_overlay_draw_constants.py` — pure visual constants
- `prose_overlay_trail.py` — faulthandler + atomic JSON
- `prose_overlay_viewport.py` — scroll/anchor math

**Total:** 33 files. Every prose_overlay_*.py is categorized.

## 2. Invariants

| ID | Severity | Rule |
|---|---|---|
| I1 | FAIL | INTERNAL files must not import from talon at top level |
| I2 | FAIL | CURSORLESS files (Python re-impl) must not import from talon |
| I3 | WARN | UI files should not import from CURSORLESS directly — route through SHIM |
| I4 | FAIL | Every prose_overlay_*.py must be assigned to exactly one layer |
| I5 | FAIL | INTERNAL files must not have lazy (function-local) talon imports either |

## 3. Current findings (as of 2026-06-30 — RED)

### FAIL — INTERNAL/CURSORLESS leaking talon

| File:Line | Violation | Refactor plan (NOT executed yet) |
|---|---|---|
| `prose_overlay_viewport.py:14` | `from talon import ui` | Drop — `ui` is not actually used at runtime (the `Rect` is). |
| `prose_overlay_viewport.py:15` | `from talon.ui import Rect` | Replace with a pure-Python `Rect` dataclass (4-field: `x`, `y`, `width`, `height`). The Talon `Rect` is the only talon thing this module uses; the math is otherwise pure. Estimated ~10 LOC change in viewport.py + matching dataclass def. |
| `prose_overlay_cursorless_resolve.py:7` | `from talon import actions, settings  # noqa: F401` | Delete the line. The `noqa: F401` proves it's unused. ~1 LOC change. |

These three fails are the meta-test's value: they're the ONLY places blocking the portability claim. Two real refactor moments + one stale line.

### WARN — UI bypasses SHIM (advisory)

| File | Concern | Notes |
|---|---|---|
| `prose_overlay.py` | imports from CURSORLESS layer directly | The main orchestrator wires `_state.buffer` from `prose_overlay_cursorless_resolve`. This crossing is structural (wiring at module-init time) — could either accept it OR re-categorize `prose_overlay.py` as SHIM (it's the top-level orchestrator and arguably bridges everything). |
| `prose_overlay_actions_cursor.py` | imports from CURSORLESS layer directly | Cursor positioning reads `_state` for hat-to-token lookup. Could be re-categorized SHIM since it bridges Talon (action class) and cursorless state. |

The WARNs are categorization questions, not real overfit. Two possible resolutions:
- **Accept** — re-categorize these two as SHIM (they bridge talon and cursorless state, which IS the shim's job).
- **Refactor** — move the cross-layer imports into a smaller shim module so the action class can stay UI-clean.

Current call: re-categorize. Cleaner with the existing module shape.

## 4. Refactor plan (deferred — user has explicitly said NOT to implement yet)

Three FAIL items, ordered by effort:

### Step 1 — `cursorless_resolve.py:7` stale import (1 LOC, 30 seconds)

```diff
-from talon import actions, settings  # noqa: F401
```

Single line deletion. The `noqa: F401` already documents it's unused. Pure refactor; zero behavior change.

### Step 2 — `viewport.py` Rect dataclass (~15 LOC)

Add a pure-Python Rect:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float
    @property
    def left(self) -> float: return self.x
    @property
    def right(self) -> float: return self.x + self.width
    @property
    def top(self) -> float: return self.y
    @property
    def bottom(self) -> float: return self.y + self.height
```

Replace `from talon.ui import Rect` with import of this new class. Adapt any callers (most likely just `set_anchor_rect`). Talon's `Rect` and this dataclass have the same field names — the swap is mechanical.

Optionally, the SHIM layer can keep a `talon_rect_adapter()` that converts to/from Talon's Rect when handing off to Skia paint.

### Step 3 — `viewport.py:14` `from talon import ui` (1 LOC)

`ui` is imported but used only at line 25 (`ui.main_screen()`) in current code. Move that one call site into a SHIM module, or accept that viewport's "what's the screen size" needs a port adapter. Pure-Python fallback: pass screen dims in from the caller (which IS the SHIM/UI).

Estimated total: ~20 LOC across two files, no behavior change. Could land in a single commit titled `refactor(internal): viewport and cursorless_resolve are now talon-free`.

After landing, Layer 4 goes green. The portability claim becomes honest.

## 5. The portability claim — what going green proves

When Layer 4 passes:

1. **Drop INTERNAL + CURSORLESS Python files** into any project (VS Code extension host, browser bundle, Vim plugin via remote process, Emacs RPC server, headless test rig).
2. **Write a new SHIM** that adapts the host environment's APIs to the INTERNAL primitives — e.g. for VS Code: a webview that calls `ProseBuffer.add_text()` on every input event, calls `compute_hat_assignments()` for the dot overlay, queries the resolver for cursorless verbs.
3. **Write a new UI** for the target environment — VS Code's render layer, Vim's buffer paint hooks, whatever.

The voice grammar is necessarily Talon-bound (Talon is the speech recognizer). But the prose-buffer-with-cursorless model — undo, hats, scopes, formatters, homophones — becomes a drop-in module.

Voice grammar can also be ported (Vosk/Whisper + a different command surface) but that's a separate question — the BUFFER LOGIC portability is what this audit proves.

## 6. Maintenance rule

When adding a new `prose_overlay_*.py`:
1. Update `scripts/layer-audit.py` — add the filename to one of `INTERNAL` / `CURSORLESS` / `SHIM` / `UI`.
2. Run `python3 scripts/layer-audit.py`. Confirm green (or document the new overfit if it's intentional and add a TODO row to this file).
3. The headless suite's L4 will catch uncategorized new files automatically (invariant I4).

When refactoring:
- Moving a file across layers is allowed — update both the layer set in the audit script AND the corresponding section in this doc.
- Adding a talon import to an INTERNAL file IS an overfit. The audit will catch it; resolution is either to refactor or to re-categorize the file as SHIM.

When the audit goes green:
- Update this doc's status from RED to GREEN.
- Add a Changelog entry noting which file became portable.
- The portability claim in §5 is now true.
