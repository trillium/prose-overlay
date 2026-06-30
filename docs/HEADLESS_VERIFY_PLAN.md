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
   Python** — `internal/state.py` imports nothing from `talon`. It can
   be imported and exercised in any Python REPL.
2. **The JS hat allocator is a self-contained bundle.** `js/prose_allocate_hats.js`
   runs in any JS runtime — `bun`, `node`, `deno`. No Talon-specific globals.
3. **Talon-importing modules can be exercised with stubs.** `ui/test_driver.py`
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

`internal/state.py` is the substrate. Direct import works.

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

### Layer 3 — Talon-stubbed (`ui/test_driver.py`)

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

### Layer 4 — Meta (codebase portability audit)

Defers to `scripts/layer-audit.py` — asserts INTERNAL + CURSORLESS Python
modules stay talon-free so the substrate ports to non-Talon environments
(VS Code, Vim, web, …) given a different SHIM + UI. See `docs/LAYER_AUDIT.md`.

| ID | Test | Notes |
|---|---|---|
| L4.1 | `layer-audit.py` returns 0 (no FAIL findings) | structural invariants hold |

### Layer 5 — Resolver parity (F9 migration: Python ↔ JS)

The ISC-8 contract: for each row in `MANUAL_VERIFICATION.md` whose target
dict + buffer + expected token range can be expressed without invoking
Talon's grammar engine, we construct a fixture, run BOTH resolvers, and
assert:

```
python_output == js_output == expected
```

A failure here means one of three things:

1. Python and JS resolvers diverge → the F9 migration is unsafe; stop.
2. Both resolvers disagree with `expected` → MANUAL_VERIFICATION.md is wrong.
3. JS bundle throws on a target shape the prose grammar would construct →
   bundle gap; file a follow-up.

| ID | Test | MANUAL_VERIFICATION row |
|---|---|---|
| L5.1 | `take air` — primitive decoratedSymbol → token 1 | 1 |
| L5.2 | `chuck ball` — primitive decoratedSymbol → token 2 | 2 |
| L5.3 | `chuck blue air` — colored mark, blue-a wins over gray-a | 3 |
| L5.4 | `chuck head ball` — extendThroughStartOf → tokens 0..2 | 4 |
| L5.5 | `chuck tail drum` — extendThroughEndOf → tokens 3..4 | 5 |
| L5.6 | `change head ball` — resolver shape (action-level cursor parking is live-only) | 6 |
| L5.7 | `change tail drum` — resolver shape (action-level cursor parking is live-only) | 7 |
| L5.8 | `bring air to drum` — source target = primitive 'a' | 8 |
| L5.9 | `move air to drum` — source target = primitive 'a' | 9 |
| L5.10 | `bring blue air to drum` — colored source mark | 10 |
| L5.11 | `chuck file` — containingScope document → whole buffer | 13 |
| L5.12 | `chuck line` — containingScope line (single-line ⇒ whole buffer) | 14 |
| L5.13 | `take file` — same resolver shape as row 13 | 15 |
| L5.14 | `chuck air past drum` — range target → tokens 1..3 | 18 |
| L5.15 | `take air and drum` — list target → two token ranges | 19 |
| L5.16 | `format snake air past drum` — range target (formatter is action-level) | 20 |

**Live-only rows (parity NOT machine-tested):**

| MANUAL_VERIFICATION row | Why live-only |
|---|---|
| 11 — `pre start` | Cursor-positioning is action-level; the resolver returns a token range and the action then places the cursor relative to it. Verify in Talon. |
| 12 — `post end` | Same — action-level cursor placement after resolver returns. |
| 16 — `take quotes air` | The cursorless JS bundle expects internal delimiter names (`quotationMark`, `parentheses`, …) where the prose grammar emits prose-side names (`quad`, `round`). Bundle errors on prose names today; bridging is a separate slice. The Python re-impl in `prose_overlay_surrounding_pair` handles these locally — when the JS default is on, this row is the live-evidence test for the bundle gap. |
| 17 — `chuck round air` | Same surrounding-pair gap as row 16. |

ISC-8 stays partial-green (`[~]`) on the back of Layer 5 — the 16 rows we
parity-test pass, but ISC-8's criterion text says "every row" so the
gap is documented in the ISA Decisions entry and gets retired once a
clean live walkthrough confirms rows 11, 12, 16, 17 behave.

### Out of scope for this plan

These require the live Talon process. Document the gap; do not run.

- `prose_overlay.talon` voice routing (`<user.letters>` for NATO letter input, `overlay test on/off` etc.)
- `prose_overlay_hats_js.py` end-to-end (needs `talon.lib.js`)
- `prose_overlay_targets_js.py` end-to-end (same)
- Canvas refresh + draw cycle
- `prose_overlay_trail.py` slice B against a real crash (HAT_ALLOC repro)
- `shim/shapes.py` `draw_hat_shape()` actual Skia paint (Slice 1) — the
  module's vocabulary, parse, and asset-existence checks are L1.20-L1.23;
  the `Path.from_svg` + FILL+STROKE compositing path is verify-in-Talon only.
  Live check: `overlay shapes homo on` while a flagged word is in the
  buffer; expect a small hat shape (bolt / curve / fox / ...) above the
  letter-hat dot.

## 3. How the runner works

`scripts/headless-verify.py` is one Python file with five sections:
- **Layer 1**: imports `internal/state.py` via `importlib.util.spec_from_file_location` and exercises ProseBuffer + compute_hat_assignments.
- **Layer 2**: spawns `bun` with an inline JS that loads the bundle and calls `proseAllocateHats`. Compares JSON output to expected shape.
- **Layer 3**: installs stub modules into `sys.modules` for `talon`, `talon.lib.js`, then imports `ui/test_driver.py`. Captures stub `actions.user.*` calls to verify routing.
- **Layer 4**: shells out to `scripts/layer-audit.py` which asserts INTERNAL + CURSORLESS layers have zero talon imports (top-level or lazy).
- **Layer 5**: parity harness. For each headless-testable row in MANUAL_VERIFICATION.md, builds a fixture, runs Python resolver (via the synthetic-package import trick — see the `_load_python_resolver` docstring) AND the JS bundle (via `bun`), asserts both equal each other AND the expected output.

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

=== Layer 4 — Meta (codebase portability) ===
  [x] L4.1: INTERNAL + CURSORLESS layers are talon-free

=== Layer 5 — Resolver parity (Python ↔ JS, F9 migration) ===
  [x] L5.1: MANUAL_VERIFICATION row 1 — `take air`
  ...

Summary: 62/62 passed
```

## 4. Maintenance rule

Every feature that lands in this repo SHOULD add at least one test to this
plan + runner if it's testable headlessly. The cost is small (one function
+ one row in the table); the payoff is durable regression coverage that
doesn't require firing up Talon.

If a feature is genuinely live-only (voice grammar, canvas paint), say so
explicitly in the commit message: `live-verify: <what to check in Talon>`.
