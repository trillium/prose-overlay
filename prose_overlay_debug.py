"""Prose Overlay Debug -- state-change observer with JSONL emission.

Continuous capture: every meaningful state change emits a JSONL line to
``~/.talon/prose_overlay_debug.jsonl`` with a diff against the previous
snapshot. Default ON — the cost of forgetting it's off is worse than the
cost of a rotating log file.

Coverage comes from a hook at the end of ``draw_overlay``: every render
triggers ``emit_if_changed("draw")``. Since every meaningful mutation in the
plugin ends with ``canvas.refresh()`` (which freezes the canvas → triggers
a draw), this single hook captures everything without scattering emit calls
across every action. The earlier-stage hooks (``set_cursor``, ``recompute_hats``,
``show``, ``hide``) still fire and give finer-grained trigger labels —
``emit_if_changed`` dedupes by snapshot equality so the later draw-time hook
is a no-op when the earlier one already emitted.

The log file rotates at ``LOG_ROTATE_BYTES``: when the file exceeds the cap,
it's renamed to ``…debug.jsonl.1`` (overwriting any previous rotation) and a
fresh file is started. Keeps disk usage bounded at ~2× the cap.

Usage:
  - Off-by-default toggle: voice ``overlay debug off`` / ``overlay debug on``
  - Tail the log: ``tail -f ~/.talon/prose_overlay_debug.jsonl | python3 -m json.tool``
"""

import json
import os
from datetime import datetime

# Default ON — observability beats forgetting to enable it. Override via
# voice command or set_debug_mode(False) at runtime.
_debug_enabled: bool = True
_last_snapshot: dict | None = None

DEBUG_LOG = os.path.expanduser("~/.talon/prose_overlay_debug.jsonl")
LOG_ROTATE_BYTES = 5 * 1024 * 1024  # 5 MB cap before rotating to .1


def set_debug_mode(enabled: bool) -> None:
    global _debug_enabled, _last_snapshot
    _debug_enabled = enabled
    _last_snapshot = None  # reset diff baseline on every toggle
    print(f"prose_overlay: debug mode {'ON' if enabled else 'OFF'} → {DEBUG_LOG}")


def _snapshot() -> dict:
    """Capture a point-in-time snapshot of all prose overlay state."""
    from .prose_overlay_instance import instance
    from . import prose_overlay_draw as dm
    from . import prose_overlay_homophones as _h

    tokens = instance.buffer.get_tokens()
    # Per-token hat mark: "color-letter" if hatted, "-" if not. Flat dict
    # keyed by str(idx) so JSON-friendly + greppable.
    hats = instance.hat_assignments or {}
    per_token_hat = {
        str(i): (f"{hats[i][2]}-{hats[i][1]}" if i in hats else "-")
        for i in range(len(tokens))
    }
    unhatted_indices = [i for i in range(len(tokens)) if i not in hats]
    flagged = sorted(_h.flagged_indices(tokens)) if tokens else []

    return {
        "showing":        instance.canvas.is_showing,
        "cursor":         instance.cursor,
        "change_mode":    getattr(instance, "change_mode", False),
        "auto_dictation": instance.auto_dictation,
        "help_visible":   instance.help_visible,
        "token_count":    len(tokens),
        "tokens":         tokens,
        "hats":           per_token_hat,
        "unhatted":       unhatted_indices,
        "flagged":        flagged,
        "hat_count":      len(hats),
        "hat_js_fallback": instance.hat_js_fallback,
        "buffer_rev":     instance.buffer.rev,
        "scroll_offset":  instance.viewport.get_scroll_offset(),
        "hints_hidden":   dm._hints_hidden_by_overflow,
        "target_window":  instance.target_window_title,
        "flash":          list(instance.flash_state.get("indices", [])),
        "flash_color":    instance.flash_state.get("color", ""),
    }


def _rotate_if_needed() -> None:
    try:
        if os.path.getsize(DEBUG_LOG) >= LOG_ROTATE_BYTES:
            os.replace(DEBUG_LOG, DEBUG_LOG + ".1")
    except FileNotFoundError:
        pass
    except OSError as e:
        print(f"prose_overlay: debug rotate failed: {e}")


def emit_if_changed(trigger: str) -> None:
    """Compare current state to last snapshot; emit a JSONL line if changed.

    No-ops when debug mode is off or nothing changed. Safe to call from any
    state-mutation site or from the draw path — duplicate calls in the same
    tick are deduped by snapshot equality.
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
    _rotate_if_needed()
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        print(f"prose_overlay: debug write failed: {e}")
