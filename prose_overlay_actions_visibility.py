"""Visibility actions and preferences persistence for the prose overlay.

Owns: _save_prefs, _load_prefs, prose_overlay_show, prose_overlay_hide,
      prose_overlay_toggle_auto_dictation, prose_overlay_is_active,
      prose_overlay_get_selection.

Never imports prose_overlay.py.
"""

import json
import os

from talon import Module, actions, settings

from .internal.instance import instance
from .shim.actions_core import _recompute_hats, _sync_tags

mod = Module()

_PREFS_PATH = os.path.join(os.path.dirname(__file__), "prose_overlay_prefs.json")


# ---------------------------------------------------------------------------
# Preferences persistence
# ---------------------------------------------------------------------------

def _save_prefs() -> None:
    """Write current preferences to disk."""
    viewport = instance.viewport
    try:
        with open(_PREFS_PATH, "w") as f:
            json.dump({
                "auto_dictation": instance.auto_dictation,
                "anchor_position": viewport._anchor_position,
            }, f)
    except Exception as e:
        print(f"prose_overlay: could not save prefs: {e}")


def _load_prefs() -> None:
    """Load persisted preferences and apply them (called once at module init)."""
    viewport = instance.viewport
    try:
        with open(_PREFS_PATH) as f:
            prefs = json.load(f)
        instance.auto_dictation = bool(prefs.get("auto_dictation", False))
        _sync_tags()  # canvas is not showing at init, so tags derive cleanly
        print(f"prose_overlay: auto-dictation restored to {'ON' if instance.auto_dictation else 'OFF'}")
        pos = prefs.get("anchor_position", "top")
        viewport.set_anchor_position(pos)
        print(f"prose_overlay: anchor position restored to '{pos}'")
    except FileNotFoundError:
        pass  # first run — no prefs file yet
    except Exception as e:
        print(f"prose_overlay: could not load prefs: {e}")


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@mod.action_class
class Actions:
    def prose_overlay_show():
        """Show the prose dictation overlay. Inserts into whatever window is active at confirm time."""
        from talon import ui
        if not settings.get("user.prose_overlay_enabled"):
            return

        viewport = instance.viewport
        # Record window title and capture anchor rect for window-scoped layout.
        try:
            win = ui.active_window()
            instance.target_window_title = win.title or ""
            viewport.set_anchor_rect(win.rect)
        except Exception:
            instance.target_window_title = ""
            viewport.set_anchor_rect(None)

        instance.buffer.clear()
        instance.target_recall_name = None
        viewport.set_scroll_offset(0)
        from .prose_overlay_actions_cursor import _prose_overlay_clear_cursor
        _prose_overlay_clear_cursor()
        _recompute_hats()
        instance.canvas.show()
        _sync_tags()  # canvas.is_showing is now True
        from .internal.debug import emit_if_changed
        emit_if_changed("show")
        # Auto-enable dictation so <user.raw_prose> routes to the buffer.
        # prose_overlay_dictation.talon requires mode: dictation to fire.
        actions.mode.enable("dictation")

    def prose_overlay_hide():
        """Hide the prose overlay and clear the buffer."""
        from .prose_overlay_actions_cursor import _prose_overlay_clear_cursor
        from .prose_overlay_actions_flash import _clear_flash
        _prose_overlay_clear_cursor()
        _clear_flash()
        instance.viewport.set_scroll_offset(0)
        instance.canvas.hide()
        instance.buffer.clear()
        _sync_tags()  # canvas.is_showing is now False
        from .internal.debug import emit_if_changed
        emit_if_changed("hide")
        instance.target_window_title = ""
        instance.target_recall_name = None
        instance.help_visible = False
        instance.help_page = 0
        # Return to command mode — paired with the enable in prose_overlay_show.
        actions.mode.enable("command")
        # In auto mode, keep dictation active so the next phrase routes through
        # the dictation_insert shim and re-opens the overlay automatically.
        # Without this, the hide would drop dictation and the next phrase would
        # land in command mode where the shim never fires.
        if not instance.auto_dictation:
            actions.mode.disable("dictation")

    def prose_overlay_toggle_auto_dictation():
        """Toggle auto-show prose overlay on any dictation phrase."""
        instance.auto_dictation = not instance.auto_dictation
        _sync_tags()  # derives correct tag state from canvas + instance.auto_dictation
        _save_prefs()
        print(f"prose_overlay: auto-dictation {'ON' if instance.auto_dictation else 'OFF'}")

    def prose_overlay_is_active() -> bool:
        """Check if the prose overlay is currently showing."""
        return instance.canvas.is_showing

    def prose_overlay_get_selection() -> list:
        """Return [start, end] selection indices, or [] if no selection."""
        sel = instance.buffer.get_selection()
        if sel is None:
            return []
        return list(sel)

    def prose_overlay_debug(enabled: int):
        """Enable (1) or disable (0) JSONL state-change debug logging."""
        from .internal.debug import set_debug_mode
        set_debug_mode(bool(enabled))

    def prose_overlay_dump_state():
        """Print a snapshot of buffer + hat state to the Talon log.

        Use when you need to know what's in the buffer right now without
        wiring up the full debug-mode JSONL stream. Output: tokens, hats,
        cursor, change mode, canvas-showing, JS-fallback flag.
        """
        tokens = instance.buffer.get_tokens()
        hats = dict(instance.hat_assignments) if instance.hat_assignments else {}
        unhatted = [i for i in range(len(tokens)) if i not in hats]
        print(f"prose_overlay: dump — {len(tokens)} tokens")
        for i, t in enumerate(tokens):
            h = hats.get(i)
            mark = f"{h[2]}-{h[1]}" if h else "NO HAT"
            print(f"  [{i}] {t!r:30} → {mark}")
        print(f"  showing={instance.canvas.is_showing} cursor={instance.cursor} "
              f"change_mode={getattr(instance, 'change_mode', False)} "
              f"hat_js_fallback={instance.hat_js_fallback} unhatted={unhatted}")

    def prose_overlay_set_homophone_hint(enabled: int):
        """Enable (1) or disable (0) the homophone-underline indicator (slice A)."""
        from .internal import homophones as _h
        _h.set_hint_enabled(bool(enabled))
        if instance.canvas.is_showing:
            instance.canvas.refresh()
        print(f"prose_overlay: homophone hint {'ON' if enabled else 'OFF'}")

    def prose_overlay_set_homophone_shapes(enabled: int):
        """Enable (1) or disable (0) the homophone hat-shape overlay (slice 1).

        Slice 1 of docs/HOMOPHONE_SHAPES_PLAN.md. Mutates the module-level
        flag in prose_overlay_shapes (parallel to prose_overlay_homophones._
        hint_enabled). The draw module ORs this against the static
        user.prose_overlay_homophone_shapes setting so either path turns
        shapes on.
        """
        from .shim import shapes as _s
        _s.set_shapes_enabled(bool(enabled))
        if instance.canvas.is_showing:
            instance.canvas.refresh()
        print(f"prose_overlay: homophone shapes {'ON' if enabled else 'OFF'}")

    def prose_overlay_clear_buffer():
        """Clear the buffer + cursor + flash but KEEP the canvas showing.

        Bound to "prose overlay" while the overlay is already active — without
        this rule, the utterance falls through to <user.raw_prose> in the
        dictation intercept and the words "prose overlay" enter the buffer.
        Semantic: re-saying the launch phrase = fresh start, not dismiss.

        Distinct from prose_overlay_reset (which hides the canvas + wipes
        global state) and from prose_overlay_hide (which dismisses and
        clears the buffer). This keeps the panel visible and returns the
        buffer to its post-show empty state.
        """
        from .prose_overlay_actions_cursor import _prose_overlay_clear_cursor
        from .prose_overlay_actions_flash import _clear_flash
        _prose_overlay_clear_cursor()
        _clear_flash()
        instance.buffer.clear()
        instance.viewport.set_scroll_offset(0)
        instance.change_mode = False
        instance._last_input_source = "init"
        from .shim.actions_core import _recompute_hats
        _recompute_hats()
        if instance.canvas is not None:
            instance.canvas.refresh()
        from .internal.debug import emit_if_changed
        emit_if_changed("clear_buffer")
        print("prose_overlay: buffer cleared (canvas still showing)")

    def prose_overlay_reset():
        """Wipe ALL per-session prose-overlay state back to defaults.

        Debug / recovery escape hatch — use when the overlay state is in an
        unknown bad state (e.g. mid-flash leftover after a crash, stuck
        cursor, history full of garbage). Equivalent to a plugin re-init
        without restarting Talon.

        What this DOES:
          - Hide canvas + history overlay; cancel any pending flash callback.
          - Clear buffer tokens + undo/redo history.
          - Clear hat_assignments + hat_to_token + flash_state.
          - Reset cursor, change_mode, help_visible, help_page, auto_dictation,
            hat_js_fallback, _last_input_source.
          - Reset viewport scroll to 0.
          - Reset target_window_title + target_recall_name.
          - Return to command mode.

        What this does NOT do:
          - Doesn't re-instantiate canvas / viewport / contexts (those are
            module-init objects; rebuilding them mid-session would orphan
            the Talon-side handles).
          - Doesn't clear saved preferences (~/.talon/prose_overlay_prefs.json).
          - Doesn't re-load any imported modules.
        """
        from .prose_overlay_actions_cursor import _prose_overlay_clear_cursor
        from .prose_overlay_actions_flash import _clear_flash
        _prose_overlay_clear_cursor()
        _clear_flash()
        if instance.canvas is not None and instance.canvas.is_showing:
            instance.canvas.hide()
        if instance.history_overlay is not None and instance.history_overlay.is_showing:
            instance.history_overlay.hide()
        instance.reset()
        _sync_tags()
        from .internal.debug import emit_if_changed
        emit_if_changed("reset")
        actions.mode.enable("command")
        actions.mode.disable("dictation")
        print("prose_overlay: RESET — all per-session state wiped")
