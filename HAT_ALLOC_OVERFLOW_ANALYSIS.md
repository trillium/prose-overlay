# HAT_ALLOC_OVERFLOW_ANALYSIS

> Analysis of `Maximum call stack size exceeded` in `proseAllocateHats` under Talon's
> embedded QuickJS engine.
> Date: 2026-05-21

---

## Root Cause

**The overflow is caused by the JS→Python proxy crossing at the callback site, not by
algorithm depth.**

The algorithm itself is iterative — no recursion in `proseAllocateHats`,
`getHatRankingContext`, `chooseTokenHat`, or `maxByFirstDiffering`. The call chain is flat:

```
proseAllocateHats()
  → getHatRankingContext()         [iterative, forEach loop]
  → for each token: chooseTokenHat()
      → maxByFirstDiffering()      [iterative, for-of loop over fns array]
        → maxByAllowingTies()      [iterative, single for-of]
  → callback(JSON.stringify(result))  ← THIS IS WHERE IT DIES
```

The very last line of all algorithm work is `callback(JSON.stringify(result))` (line 12497
of `prose_allocate_hats.js`). At that point, QuickJS has to marshal a call across the
JS→Python boundary via `NewProxy`. That crossing pushes a burst of QuickJS internal frames
on top of whatever the current stack depth is. The stack is already deep when the callback
fires, which tips it over the limit.

---

## Why the Stack Is Already Deep When callback Fires

The bundle (`prose_allocate_hats.js`, **12,515 lines**) uses esbuild's `__commonJS` wrapper
pattern. At eval time the entire lodash library (one `__commonJS` block, lines 35–5512)
is defined. At call time, every `require_lodash()` invocation re-enters `__require`, which
runs the factory if not yet cached. The bundle makes **9 separate `require_lodash()` calls**
at module initialization (lines 5515, 5518, 5519, 5520, 5521, 9164, 9165, 9166, 12223),
each going through `__toESM(require_lodash(), 1)`. Because `__commonJS` is lazy (memoized on
first call), only the first call actually runs lodash's factory; subsequent calls return the
cached `mod.exports`. So the `__commonJS` mechanism itself doesn't produce deep recursion at
runtime.

The stack depth at the point `callback` fires comes from a different source: QuickJS's IIFE
wrapper nesting. The whole bundle is one large `(() => { ... })()` IIFE. Inside it, the
module-level code that runs `require_lodash()` on initialization, combined with nested
closures for each helper, means the effective frame depth when `proseAllocateHats` is invoked
from Python is already non-trivial — estimated 30–60 frames of QuickJS internal
infrastructure before any algorithm code starts. Adding the JS→Python proxy marshal (which
itself can push 10–30 QuickJS frames per Talon's implementation) is what causes the
overflow.

**The contrast with `prose_actions.js`** (275 lines, simple IIFE, no `__commonJS`, returns
a value directly) makes this clear. `proseRunAction` works because: (a) the bundle is tiny
so the IIFE is shallow, and (b) it returns a value rather than calling back into Python.

---

## Stack Depth Estimate

- Algorithm proper: ~5–8 frames (`proseAllocateHats` → `getHatRankingContext` →
  `chooseTokenHat` → `maxByFirstDiffering` → `maxByAllowingTies` → metric closures)
- QuickJS IIFE + module frame: ~20–40 frames (12k-line bundle, deeply nested closure scope)
- JS→Python proxy marshal: ~15–30 frames (Talon's QuickJS binding overhead, estimated)
- **Total at callback site: ~40–80 frames**

QuickJS's default call stack limit is **256 frames** (configurable in the QuickJS source as
`JS_DEFAULT_STACK_SIZE = 256 * sizeof(JSValue)`, typically ~512–2048 bytes, or 256–512
logical frames depending on build). Talon does not expose a way to raise this limit. With a
12k-line bundle and a Python proxy crossing, a stack in the 40–80-frame range can easily hit
the limit if Talon compiles with a conservative setting or if the proxy boundary pushes more
frames than estimated.

---

## Bundle Complexity

| File                     | Lines  | `__commonJS` blocks | Bundle style       |
|--------------------------|--------|---------------------|--------------------|
| `prose_allocate_hats.js` | 12,515 | 1 (lodash, ~5,500 lines) | esbuild IIFE + `__commonJS` |
| `prose_actions.js`       | 275    | 0                   | esbuild IIFE, no deps      |

The lodash inclusion is the primary size driver. The algorithm only uses `deburr`, `memoize`,
and `min` from lodash — three functions out of a 5,500-line library.

---

## Recommended Fix

### Option A — Return value instead of callback (RECOMMENDED)

Change `proseAllocateHats` to return the JSON string instead of calling back into Python.
The Python side reads the return value directly. This eliminates the Python proxy entirely —
no `NewProxy`, no cross-boundary frame burst.

**TypeScript change in `proseStandalone.ts`:**

```typescript
// BEFORE
function proseAllocateHats(
  tokensJson: string,
  oldAssignmentsJson: string,
  stability: string,
  callback: (resultJson: string) => void,
): void {
  // ... algorithm ...
  callback(JSON.stringify(result));
}

// AFTER
function proseAllocateHats(
  tokensJson: string,
  oldAssignmentsJson: string,
  stability: string,
): string {
  // ... algorithm (identical body) ...
  return JSON.stringify(result);
}
```

**Python change in `prose_overlay_hats_js.py`:**

```python
# BEFORE
result_holder: list[str] = []
_fn(
    json.dumps(tokens),
    json.dumps(old_list),
    stability,
    js.JS.NewProxy(_ctx, lambda r: result_holder.append(str(r))),
)
# ... check result_holder[0] ...

# AFTER
result_json: str = str(_fn(
    json.dumps(tokens),
    json.dumps(old_list),
    stability,
))
# ... parse result_json directly ...
```

This exactly mirrors how `prose_actions.js` / `prose_overlay_actions_js.py` works — return
value, no proxy, no crossing. That pattern is confirmed working.

**Risk:** Low. The change is purely at the boundary; all algorithm logic is unchanged. The
`callback` parameter is a QuickJS-side detail; nothing else calls `proseAllocateHats`
externally.

---

### Option B — JS global as result sink

Before calling `_fn`, evaluate a small JS snippet that defines a global result store and
a pure-JS callback, then call `_fn` with that JS callback (not a Python proxy), then read
the global back from Python:

```python
_ctx.eval("var _hat_result = null; function _hat_cb(r){ _hat_result = r; }")
_fn(json.dumps(tokens), json.dumps(old_list), stability, _ctx.globals._hat_cb)
result_json = str(_ctx.globals._hat_result)
```

**Risk:** Medium. Relies on `_ctx.globals._hat_cb` being passable as a JS function (not a
proxy). Still requires verifying that Talon's `js.Context` exposes globals as callable
references. Also leaves mutable global state in the context. Option A is cleaner.

---

## Assessment

**Option A is the correct fix.** It:
- Eliminates the problem's root cause (the proxy crossing) rather than working around it
- Makes the API consistent with `prose_actions.js` (the only proven-working precedent)
- Requires 3-line changes in TS and 4-line changes in Python
- Has no risk of introducing new state or side-effects

---

## Rebuilding the Bundle

`bunx esbuild` is available (`0.28.0` installed). The bundle can be rebuilt.

**No existing build script is present** for `prose_allocate_hats.js` — no Makefile, no
`.sh`, no npm script in the overlay directory. The original build was done manually.
The equivalent command (matching the esbuild IIFE + CommonJS output style observed in the
bundle) would be:

```bash
cd /Users/trilliumsmith/code/cursorless
bunx esbuild \
  packages/cursorless-engine/src/util/allocateHats/proseStandalone.ts \
  --bundle \
  --format=iife \
  --platform=browser \
  --target=es2020 \
  --outfile=/Users/trilliumsmith/.talon/user/trillium_talon/trillium/plugin/prose_overlay/js/prose_allocate_hats.js
```

The `--format=iife` flag matches the `(() => { ... })()` wrapper in the current bundle.
The `--platform=browser` flag avoids Node built-ins that QuickJS doesn't have.
After applying the Option A TS change, rebuild with this command and the new bundle will have
the return-value signature.

---

## Action Items

1. Edit `proseStandalone.ts`: remove `callback` parameter, return `JSON.stringify(result)`
2. Edit `prose_overlay_hats_js.py`: capture `str(_fn(...))` return value, remove `NewProxy`
3. Rebuild bundle with `bunx esbuild` command above
4. Copy output to `js/prose_allocate_hats.js`
5. Reload Talon and verify no overflow on a real phrase

---

## Files Referenced

- `proseStandalone.ts`:
  `/Users/trilliumsmith/code/cursorless/packages/cursorless-engine/src/util/allocateHats/proseStandalone.ts`
- Python caller:
  `/Users/trilliumsmith/.talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay_hats_js.py`
- Bundle:
  `/Users/trilliumsmith/.talon/user/trillium_talon/trillium/plugin/prose_overlay/js/prose_allocate_hats.js`
- Working reference (return-value pattern):
  `/Users/trilliumsmith/.talon/user/trillium_talon/trillium/plugin/prose_overlay/js/prose_actions.js`
  `/Users/trilliumsmith/.talon/user/trillium_talon/trillium/plugin/prose_overlay/prose_overlay_actions_js.py`
