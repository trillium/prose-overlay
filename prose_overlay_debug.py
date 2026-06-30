"""Prose Overlay Debug -- state change observer with JSONL emission.

When debug mode is enabled, every meaningful state mutation emits a JSONL
line to ~/.talon/prose_overlay_debug.jsonl showing what changed and what
triggered the change.

Usage:
  - Toggle via voice: "overlay debug on" / "overlay debug off"
  - Or programmatically: set_debug_mode(True)
  - Tail the log: tail -f ~/.talon/prose_overlay_debug.jsonl | python3 -m json.tool
"""

import json
import os
from datetime import datetime

_debug_enabled: bool = False
_last_snapshot: dict | None = None

DEBUG_LOG = os.path.expanduser("~/.talon/prose_overlay_debug.jsonl")


def set_debug_mode(enabled: bool) -> None:
    global _debug_enabled, _last_snapshot
    _debug_enabled = enabled
    _last_snapshot = None  # reset diff baseline on every toggle
    print(f"prose_overlay: debug mode {'ON' if enabled else 'OFF'} → {DEBUG_LOG}")


def _snapshot() -> dict:
    """Capture a point-in-time snapshot of all prose overlay state."""
    from .prose_overlay_instance import instance
    from . import prose_overlay_draw as dm

    tokens = instance.buffer.get_tokens()
    return {
        "showing":        instance.canvas.is_showing,
        "cursor":         instance.cursor,
        "change_mode":    getattr(instance, "change_mode", False),
        "auto_dictation": instance.auto_dictation,
        "help_visible":   instance.help_visible,
        "token_count":    len(tokens),
        "tokens":         tokens,
        "hat_count":      len(instance.hat_assignments),
        "scroll_offset":  instance.viewport.get_scroll_offset(),
        "hints_hidden":   dm._hints_hidden_by_overflow,
        "target_window":  instance.target_window_title,
    }


def emit_if_changed(trigger: str) -> None:
    """Compare current state to last snapshot; emit a JSONL line if anything changed.

    Call this at every state mutation point, passing a short label for what
    caused the change (e.g. "add_text", "set_cursor", "recompute_hats").
    No-ops when debug mode is off or nothing changed.
    """
    global _last_snapshot
    if not _debug_enabled:
        return

    snap = _snapshot()

    if _last_snapshot is None:
        diff = {k: {"from": None, "to": v} for k, v in snap.items()}
    else:
        diff = {}
        for k, v in snap.items():
            prev = _last_snapshot.get(k)
            if v != prev:
                diff[k] = {"from": prev, "to": v}

    if not diff:
        return

    _last_snapshot = snap

    entry = {
        "ts":      datetime.now().isoformat(timespec="milliseconds"),
        "trigger": trigger,
        "diff":    diff,
    }
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        print(f"prose_overlay: debug write failed: {e}")
