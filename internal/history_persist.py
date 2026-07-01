"""Persistence for the prose overlay's confirmed-text history.

Written to disk on every successful ``prose_overlay_confirm`` so the
history survives Talon restarts. The store is a JSON file at
``~/.talon/prose_overlay_history.json`` — chosen to sit alongside the
existing debug JSONL (``~/.talon/prose_overlay_debug.jsonl``) rather
than the paper-trail dir (``~/Library/Logs/prose_overlay_trail/``) so
the whole overlay's user-visible state lives under one predictable
prefix.

Contract:
  - Pure Python. No talon imports. Callable from headless tests.
  - Never raises. Load returns ``[]`` on any error (missing file,
    corrupt JSON, wrong schema, permission denied); save eats
    exceptions after printing them. History is UX-critical but
    NOT correctness-critical — a persistence failure must never
    take down the overlay.
  - Atomic writes via tmp + ``os.replace``. Mid-write crash leaves
    the prior file intact (same pattern used by ``internal/trail.py``).
  - Bounded at ``HISTORY_MAX`` entries; save trims the tail so
    long-running sessions can't grow the file without bound.
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HISTORY_MAX = 100
HISTORY_PATH = pathlib.Path.home() / ".talon" / "prose_overlay_history.json"
# Bump this any time the on-disk schema shape changes so load_history can
# detect + drop stale versions instead of crashing on unexpected keys.
_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def load_history(path: pathlib.Path | None = None) -> list[str]:
    """Read the on-disk history file. Returns ``[]`` on any error.

    Errors that yield ``[]``: file missing, permission denied, invalid
    JSON, wrong schema shape, wrong schema version, list contains
    non-string entries. All of these are logged to stdout but never
    raised — the overlay must start cleanly even if the store is
    corrupt.
    """
    p = path if path is not None else HISTORY_PATH
    if not p.exists():
        return []
    try:
        with open(p, "r") as f:
            raw: Any = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"prose_overlay: history load failed ({e!r}), starting empty")
        return []
    if not isinstance(raw, dict):
        print(f"prose_overlay: history file is not a dict ({type(raw).__name__}), starting empty")
        return []
    if raw.get("version") != _SCHEMA_VERSION:
        print(
            f"prose_overlay: history file schema version "
            f"{raw.get('version')!r} != {_SCHEMA_VERSION}, starting empty"
        )
        return []
    entries = raw.get("entries")
    if not isinstance(entries, list):
        print("prose_overlay: history 'entries' is not a list, starting empty")
        return []
    # Drop any non-string entries defensively.
    clean = [e for e in entries if isinstance(e, str)]
    if len(clean) != len(entries):
        print(
            f"prose_overlay: history dropped "
            f"{len(entries) - len(clean)} non-string entries"
        )
    # Cap on load too — a hand-edited file with 10k entries shouldn't
    # bloat memory.
    return clean[:HISTORY_MAX]


def save_history(entries: list[str], path: pathlib.Path | None = None) -> None:
    """Persist ``entries`` to disk atomically. Silently no-ops on failure.

    Writes ``entries[:HISTORY_MAX]`` — the caller may pass a longer list
    and the on-disk copy is trimmed to the cap. The parent directory is
    created if it doesn't exist (``~/.talon`` should always exist under
    a working Talon install, but this makes the function usable from a
    scratch environment / headless test).
    """
    p = path if path is not None else HISTORY_PATH
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        payload = {
            "version": _SCHEMA_VERSION,
            "entries": [e for e in entries[:HISTORY_MAX] if isinstance(e, str)],
        }
        with open(tmp, "w") as f:
            json.dump(payload, f, separators=(",", ":"))
        os.replace(tmp, p)
    except OSError as e:
        # Disk full, permission denied, path invalid — history is UX,
        # not correctness. Log and swallow so the confirm action still
        # completes and pastes to the target window.
        print(f"prose_overlay: history save failed ({e!r}), on-disk store now stale")
