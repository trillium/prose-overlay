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
import sys
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


def _get_setting(name: str):
    """Read a Talon setting defensively — None when Talon isn't loaded.

    The internal layer stays Talon-free by contract (see scripts/layer-audit.py
    I5.INTERNAL_LAZY_TALON). Rather than issuing a lazy `from talon import
    settings`, we resolve `talon` through `sys.modules` — which is populated
    only when the module has been imported elsewhere (the live Talon runtime).
    In headless verify + unit tests there is no `talon` key in `sys.modules`,
    and we return None cleanly. Every exception is swallowed so a partial
    Talon environment (e.g. a stubbed `talon` module without `.settings`)
    still falls through to None instead of crashing the snapshot.
    """
    try:
        talon_mod = sys.modules.get("talon")
        if talon_mod is None:
            return None
        settings = getattr(talon_mod, "settings", None)
        if settings is None:
            return None
        return settings.get(name)
    except Exception:
        return None


def _rect_summary(rect) -> dict | None:
    """Convert a rect-like object to a JSON-friendly {x, y, w, h} dict.

    Duck-typed on `x/y/width/height` so both the internal Rect dataclass
    (from internal/viewport.py) and talon.ui.Rect pass through cleanly.
    Returns None when the input is None so the snapshot consumer sees a
    stable JSON `null` for the "no anchor rect" case.
    """
    if rect is None:
        return None
    try:
        return {
            "x": rect.x,
            "y": rect.y,
            "w": rect.width,
            "h": rect.height,
        }
    except AttributeError:
        return None


def _snapshot() -> dict:
    """Capture a point-in-time snapshot of all prose overlay state.

    Lossless view of every visual-affecting piece of state: buffer tokens +
    rev + selection, hat + shape + panel assignments, cycling group state,
    viewport (scroll + anchor), settings that gate rendering, and transient
    render flags (flash, overflow, help page). Field ORDER is stable — new
    fields APPEND at the end so jq consumers snapshotting older logs stay
    backwards-compatible with the leading keys.

    Rules:
      - JSON-friendly: tuples → lists, None stays None, keys stringify cleanly.
      - Settings live behind `_get_setting` (returns None when Talon absent).
      - Rects live behind `_rect_summary` (returns {x,y,w,h} dict or None).
    """
    from .instance import instance
    from ..ui import draw as dm
    from . import homophones as _h

    tokens = instance.state.buffer.get_tokens()
    # Per-token hat mark: "color-letter" if hatted, "-" if not. Flat dict
    # keyed by str(idx) so JSON-friendly + greppable.
    hats = instance.state.hat_assignments or {}
    per_token_hat = {
        str(i): (f"{hats[i][2]}-{hats[i][1]}" if i in hats else "-")
        for i in range(len(tokens))
    }
    unhatted_indices = [i for i in range(len(tokens)) if i not in hats]
    flagged = sorted(_h.flagged_indices(tokens)) if tokens else []

    # ------------------------------------------------------------------
    # JSON-friendly derivations for lossless-snapshot fields.
    # ------------------------------------------------------------------
    # Selection lives on the buffer as an internal tuple[int, int] or None;
    # accessed via get_selection() (the public accessor). Convert tuple → list
    # so json.dumps stays trivial and jq sees an array not a stringified tuple.
    sel = instance.state.buffer.get_selection()
    selection_field = list(sel) if sel is not None else None

    # position_assignments values are tuple[int, int] (active_idx, group_size).
    # json.dumps handles tuples but treats them as arrays — for consistency
    # with `selection_field` and to keep values greppable we materialize as
    # lists explicitly. Keys stringified because Python's json emits int keys
    # as numeric strings anyway; making that explicit prevents jq consumers
    # from having to guard for two shapes across versions.
    pos_assignments_raw = instance.state.position_assignments or {}
    position_assignments_field = {
        str(k): list(v) for k, v in pos_assignments_raw.items()
    }

    # shape / next_alt / panel dicts already carry JSON-friendly values
    # (str / dict[str,str]); stringify keys for the same jq-consistency reason.
    shape_assignments_field = {
        str(k): v for k, v in (instance.state.shape_assignments or {}).items()
    }
    next_alt_assignments_field = {
        str(k): v for k, v in (instance.state.next_alt_assignments or {}).items()
    }
    homophone_panel_alts_field = {
        str(k): dict(v) for k, v in (instance.state.homophone_panel_alts or {}).items()
    }

    # Viewport anchor state — captured alongside scroll_offset so a JSONL
    # line fully reproduces where the panel sits on screen without needing
    # to replay the window-scope handshake.
    viewport = instance.runtime.viewport
    anchor_position_field = getattr(viewport, "_anchor_position", None)
    anchor_rect_field = _rect_summary(getattr(viewport, "_anchor_rect", None))

    return {
        "showing":        instance.runtime.canvas.is_showing,
        "cursor":         instance.state.cursor,
        "change_mode":    getattr(instance.state, "change_mode", False),
        "auto_dictation": instance.state.auto_dictation,
        "help_visible":   instance.state.help_visible,
        "token_count":    len(tokens),
        "tokens":         tokens,
        "hats":           per_token_hat,
        "unhatted":       unhatted_indices,
        "flagged":        flagged,
        "hat_count":      len(hats),
        "hat_js_fallback": instance.state.hat_js_fallback,
        "hat_js_last_err": instance.state.hat_js_last_err,
        "buffer_rev":     instance.state.buffer.rev,
        "scroll_offset":  viewport.get_scroll_offset(),
        "hints_hidden":   dm._hints_hidden_by_overflow,
        "target_window":  instance.state.target_window_title,
        "flash":          list(instance.state.flash_state.get("indices", [])),
        "flash_color":    instance.state.flash_state.get("color", ""),
        # ------------------------------------------------------------------
        # Lossless-snapshot additions (2026-07-01, S9-motivated).
        # Field ORDER: strictly appended after the historical keys above so
        # any existing jq snapshots keyed on the legacy layout continue to
        # match. Do NOT reorder the block above.
        # ------------------------------------------------------------------
        "selection":                    selection_field,
        "shape_assignments":            shape_assignments_field,
        "homophone_panel_alts":         homophone_panel_alts_field,
        "next_alt_assignments":         next_alt_assignments_field,
        "position_assignments":         position_assignments_field,
        "help_page":                    instance.state.help_page,
        "viewport_anchor_position":     anchor_position_field,
        "viewport_anchor_rect_summary": anchor_rect_field,
        "homophone_shapes_setting":     _get_setting("user.prose_overlay_homophone_shapes"),
        "homophone_hint_setting":       _get_setting("user.prose_overlay_homophone_hint"),
        "window_scoped_setting":        _get_setting("user.prose_overlay_window_scoped"),
        "hat_cursor_greedy_setting":    _get_setting("user.prose_overlay_hat_cursor_greedy"),
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
