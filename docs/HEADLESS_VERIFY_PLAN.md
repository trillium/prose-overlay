# Headless Verification Plan

> How to verify prose-overlay changes **without** driving the live Talon
> process. Companion runner: `scripts/headless-verify.py`. The runner walks
> each test below and emits a `[x]` / `[ ] FAIL: <reason>` checklist.
>
> Drafted 2026-06-30 after a session where I admitted I "couldn't drive
> Talon" and bailed on the autonomous loop. The truth was: I could always
> have run the relevant Python directly — I just never tried. This doc
> exists so future me starts here.

## 1. Why this exists

The live Talon process is one verification path. It is not the only one.
Three things matter:

1. **Most code that handles buffer state, undo, and hat allocation is pure
   Python** — `prose_overlay_state.py` imports nothing from `talon`. It can
   be imported and exercised in any Python REPL.
2. **The JS hat allocator is a self-contained bundle.** `js/prose_allocate_hats.js`
   runs in any JS runtime — `bun`, `node`, `deno`. No Talon-specific globals.
3. **Talon-importing modules can be exercised with stubs.** `prose_overlay_test_driver.py`
   imports `talon.Module`, `talon.actions`, `talon.cron` — stub them in
   `sys.modules` before import and the module loads + functions are callable.

What can NOT be verified headlessly:
- Voice grammar in `*.talon` files (needs Talon's grammar matcher)
- `talon.lib.js` (QuickJS embedded in Talon) — only reachable via live Talon
- Canvas rendering, focus restoration, OS-level key insertion
- `dictation_insert` / `insert_formatted` routing (community grammar lives in Talon)

For these, the live Talon is the only path. But everything else doesn't have
to be.

## 2. Test layers

### Layer 1 — Pure Python (no Talon, no JS)

`prose_overlay_state.py` is the substrate. Direct import works.

| ID | Test | Notes |
|---|---|---|
| L1.1 | `ProseBuffer()` constructs without exception | smoke |
| L1.2 | `add_text("testing testing one two three")` produces 5 tokens | basic mutation |
| L1.3 | `undo()` restores the prior token list | undo path |
| L1.4 | `redo()` reapplies | redo path (ISC-23 Phase 2) |
| L1.5 | `commit_start` + 2× `add_text` + `commit_end` = ONE undo step | bracket API (ISC-23 Phase 2) |
| L1.6 | `rev` advances monotonically across mutations | substrate for debug + cache |
| L1.7 | `compute_hat_assignments(["foo", "bar"])` returns hat for every letter token | baseline |
| L1.8 | `compute_hat_assignments(["123"])` returns a hat (regression: aa2909e) | digit-hat visibility |
| L1.9 | `compute_hat_assignments(["!"])` returns a hat | punct-hat visibility |
| L1.10 | `compute_hat_assignments(["testing", "testing", "123"])` returns hats for ALL three | end-to-end user repro |
| L1.11 | Letter-extend pattern: "air" then "bat cap" → one token `abc` (regression: 0ee89cd) | extends-last-token semantics |
| L1.12 | Letter-extend then undo restores prior single-letter token | undo round-trip |
| L1.13 | `ProseOverlayState.reset()` wipes every data field to defaults | debug reset |
| L1.14 | `reset()` preserves object identity (buffer/canvas refs not reassigned) | safe re-init |
| L1.15 | `hint_enabled()` returns True by default (keep-verdict regression) | slice A default-on |
| L1.16 | `is_flagged("their")` and `is_flagged("there")` return True | CSV load smoke |
| L1.17 | `add_text("the_quick_brown_fox")` → 1 token (snake formatter output) | buffer contract for formatters |
| L1.18 | `add_text("theQuickBrownFox")` → 1 token (camel formatter output) | buffer contract for formatters |
| L1.19 | `add_text("The Quick Brown Fox")` → 4 tokens (title-case has spaces) | documented split behavior |
| L1.20 | `HAT_SHAPES` is a 10-tuple of strs (excludes 'dot') | slice 1 vocabulary |
| L1.21 | `shape_pool() == HAT_SHAPES` | slice 1 round-robin contract |
| L1.22 | Every spoken shape in `HAT_SHAPES` has an SVG file in `svg/` (cross → crosshairs.svg) | vendored asset coverage |
| L1.23 | `_parse_svg_entries()` returns ≥10 entries (1 per shape, +1 default); all entries have non-empty `d` | parse smoke |

### Layer 2 — JS bundle via `bun` (no Talon)

`js/prose_allocate_hats.js` exposes `globalThis.proseAllocateHats(tokensJson, oldAssignmentsJson, stability, cursorGapJson)`.

| ID | Test | Notes |
|---|---|---|
| L2.1 | `bun` loads the bundle without exception | smoke |
| L2.2 | `proseAllocateHats(["foo", "bar"])` returns hats for both | baseline |
| L2.3 | `proseAllocateHats(["123"])` returns a hat (regression: 39b4cb6) | digit-hat — JS layer |
| L2.4 | `proseAllocateHats(["!"])` returns a hat | punct-hat — JS layer |
| L2.5 | `proseAllocateHats(["testing", "testing", "123"])` returns hats for ALL three | end-to-end user repro — JS layer |

### Layer 3 — Talon-stubbed (`prose_overlay_test_driver.py`)

Stub `talon.Module`, `talon.actions`, `talon.cron` before import. The module's
`@mod.action_class` decorator must not throw under stubs. Test the
queue-dispatch and runtime-toggle behavior.

| ID | Test | Notes |
|---|---|---|
| L3.1 | Module imports under stubbed `talon` | smoke |
| L3.2 | `_dispatch({"cmd": "add", "text": "x"})` invokes `actions.user.prose_overlay_add_text("x")` | command routing |
| L3.3 | `_dispatch({"cmd": "show"})` invokes `actions.user.prose_overlay_show()` | command routing |
| L3.4 | `_dispatch({"cmd": "dump"})` invokes `actions.user.prose_overlay_dump_state()` | command routing |
| L3.5 | `_dispatch({"cmd": "delete_hat", "letter": "a", "color": "blue"})` passes both args | nested kwargs |
| L3.5b | `_dispatch({"cmd": "add_letters", "letters": "abc"})` → `prose_overlay_add_letters` | letter-extend dispatch |
| L3.5c | `_dispatch({"cmd": "reset"})` → `prose_overlay_reset` | debug reset dispatch |
| L3.6 | `_dispatch({"cmd": "bogus"})` prints "unknown cmd" and does not raise | error path |
| L3.7 | `_dispatch({"cmd": "add"})` with malformed JSON entry is handled by `_tick` | parse-error path |
| L3.8 | Appending a JSON line to the queue + calling `_tick` advances `_pos` and dispatches | queue tail logic |
| L3.9 | `prose_overlay_test_set(1)` creates the flag file (runtime toggle, e979025) | enable path |
| L3.10 | `prose_overlay_test_set(0)` removes the flag file (runtime toggle, e979025) | disable path |

### Layer 4 — Out of scope for this plan

These require the live Talon process. Document the gap; do not run.

- `prose_overlay.talon` voice routing (`<user.letters>` for NATO letter input, `overlay test on/off` etc.)
- `prose_overlay_hats_js.py` end-to-end (needs `talon.lib.js`)
- `prose_overlay_targets_js.py` end-to-end (same)
- Canvas refresh + draw cycle
- `prose_overlay_trail.py` slice B against a real crash (HAT_ALLOC repro)
- `prose_overlay_shapes.draw_hat_shape()` actual Skia paint (Slice 1) — the
  module's vocabulary, parse, and asset-existence checks are L1.20-L1.23;
  the `Path.from_svg` + FILL+STROKE compositing path is verify-in-Talon only.
  Live check: `overlay shapes homo on` while a flagged word is in the
  buffer; expect a small hat shape (bolt / curve / fox / ...) above the
  letter-hat dot.

## 3. How the runner works

`scripts/headless-verify.py` is one Python file with three sections:
- **Layer 1**: imports `prose_overlay_state` via `importlib.util.spec_from_file_location` and exercises ProseBuffer + compute_hat_assignments.
- **Layer 2**: spawns `bun` with an inline JS that loads the bundle and calls `proseAllocateHats`. Compares JSON output to expected shape.
- **Layer 3**: installs stub modules into `sys.modules` for `talon`, `talon.lib.js`, then imports `prose_overlay_test_driver`. Captures stub `actions.user.*` calls to verify routing.

Each layer's tests are functions that raise `AssertionError` on failure. The
runner catches per-test, marks `[x]` on success and `[ ] FAIL: <reason>` on
failure, prints a summary, and exits non-zero if any fail.

Run:
```bash
python3 scripts/headless-verify.py
```

Expected output shape:
```
=== Layer 1 — Pure Python ===
  [x] L1.1: ProseBuffer instantiation
  [x] L1.2: add_text → 5 tokens
  ...

=== Layer 2 — JS bundle via bun ===
  [x] L2.1: bun loads bundle
  ...

=== Layer 3 — Stubbed Talon ===
  [x] L3.1: module imports under stubs
  ...

Summary: 25/25 passed
```

## 4. Maintenance rule

Every feature that lands in this repo SHOULD add at least one test to this
plan + runner if it's testable headlessly. The cost is small (one function
+ one row in the table); the payoff is durable regression coverage that
doesn't require firing up Talon.

If a feature is genuinely live-only (voice grammar, canvas paint), say so
explicitly in the commit message: `live-verify: <what to check in Talon>`.
