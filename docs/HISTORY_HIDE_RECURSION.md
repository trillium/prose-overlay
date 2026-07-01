# Recursion Cycle in prose_overlay_history_pick

## §1. Call Sites & Function Bodies

### Line 57: `_on_history_overlay_hide()`
```python
def _on_history_overlay_hide():
    """Called by DismissibleOverlay when dismissed via click-outside or escape."""
    actions.user.prose_overlay_hide_history()
```

### Line 177: `prose_overlay_hide_history()` action definition
```python
def prose_overlay_hide_history():
    """Hide the prose history panel."""
    instance.history_overlay.hide()
    instance.ctx_history.tags = []
```

### Line 223: `prose_overlay_history_pick()` call site (within the pick action)
```python
def prose_overlay_history_pick(n: int):
    """Load the nth history entry (1-based) into the overlay buffer. ..."""
    # ...
    if not instance.canvas.is_showing:
        actions.user.prose_overlay_show()
    actions.user.prose_overlay_hide_history()  # Line 223
    actions.user.prose_overlay_add_text(entry)
```

## §2. Overlay Initialization & on_hide Callback

At `/Users/trilliumsmith/code/prose-overlay/prose_overlay.py:207–214`:

```python
instance.history_overlay = DismissibleOverlay(
    on_draw=_on_draw_history,
    on_hide=_on_history_overlay_hide,  # Callback bound here
    close_hint_text='"overlay dismiss"',
    close_hint_size=12,
    close_hint_color="888899cc",
    blocks_mouse=False,
)
```

At `/Users/trilliumsmith/.talon/user/trillium_talon/trillium/utils/overlay_kit.py:224–225`:

When `.hide()` is called and the overlay was showing, it fires the callback:
```python
if was_showing and self._on_hide:
    self._on_hide()
```

## §3. Recursion Cycle Trace

1. **Voice input:** `history pick 1` → dispatches `prose_overlay_history_pick(1)`
2. **Line 223:** `history_pick` calls `actions.user.prose_overlay_hide_history()`
3. **Line 177:** `hide_history()` calls `instance.history_overlay.hide()`
4. **overlay_kit.py:224–225:** `.hide()` detects overlay was showing, invokes `self._on_hide()`
5. **Line 57:** `_on_history_overlay_hide()` executes, calls `actions.user.prose_overlay_hide_history()` AGAIN
6. **Recursion:** Talon's action layer rejects recursive re-entry → `RuntimeError: Cannot recursively call action: "user.prose_overlay_hide_history"`

## §4. Root Cause & Fix Options

**Root cause (one sentence):** The `_on_hide` callback (invoked by overlay teardown) re-enters the public action `prose_overlay_hide_history()` that triggered the teardown in the first place, causing a recursive action invocation that Talon forbids.

### Option A: Make `_on_hide` pure cleanup (recommended)
`_on_history_overlay_hide()` should NOT call the public action. It should only perform state cleanup (e.g., context tag management, bookkeeping) after the overlay is already torn down. The overlay is gone by the time this fires; calling `hide_history` is redundant.

### Option B: Idempotent hide action
Add an early exit guard to `prose_overlay_hide_history()`:
```python
if not instance.history_overlay.is_showing:
    return
instance.history_overlay.hide()
instance.ctx_history.tags = []
```
Makes the action safe to call multiple times.

### Option C: Split into public + private
- Public voice action: `prose_overlay_hide_history()` calls `.hide()` only
- Private callback: `_finalize_history_hide()` does state cleanup without re-entering the action layer

**Recommendation:** **Option A + light Option C** — `_on_hide` should be a pure cleanup handler. Also add a docstring comment in `_on_hide` to enforce "do not call public hide action from here" rule, and optionally move context tag clearing into a separate `_finalize_history_hide()` function that doesn't risk re-entry.

## §5. Test Coverage Gap

The headless test driver at `ui/test_driver.py` does **NOT** exercise `prose_overlay_history_pick` end-to-end. The `_dispatch()` function (lines 121–173) handles show/hide/add/confirm/undo/etc. but has no `history_pick` command implementation. This gap means the recursion bug was not caught at commit time and only surfaced during live voice use. **Follow-up:** Add headless coverage for `history_pick` + verify it with the history panel already showing.

## §6. Blast Radius

- **Triggered by:** `history pick <N>` when history panel is open
- **Impact:** Voice-driven history recovery is unusable while the panel is visible
- **Session startup:** Not blocked (overlay reload works cleanly per logs around 11:39:02.544)
- **Severity:** Medium — breaks a core workflow (history recovery) but only in active-panel scenario

