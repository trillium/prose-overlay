"""Prose overlay paper trail — Slice A (faulthandler) + Slice B (last_command.json preamble).

Gated on the env var ``PROSE_OVERLAY_TRAIL``: set it to ``"1"`` before
launching Talon to enable. Anything else (including unset) leaves this
module near-inert — no fd is opened, no signal handler is registered,
``begin_command`` / ``end_command`` are no-op stubs.

To disable: ``unset PROSE_OVERLAY_TRAIL`` and restart Talon. The flag is
checked once at module import; there is no runtime toggle. See
``docs/STACK_OVERFLOW_PAPER_TRAIL_PLAN.md`` for the full slice tree.

Slice B: JS bridges call ``begin_command`` before the risky ``_fn(...)``
and ``end_command`` after. The preamble lands on disk via ``tmp +
os.replace`` (atomic per POSIX rename) BEFORE the JS call fires, so a
post-mortem can answer "what was the user trying to do when it died?"
Stubs are exported unconditionally so call-site code is the same shape
whether the trail is enabled or not — no ``if _TRAIL_ENABLED:`` branch
at every call site.
"""

import faulthandler
import json
import os
import pathlib
from datetime import datetime
from typing import Optional

_TRAIL_ENABLED = os.environ.get("PROSE_OVERLAY_TRAIL") == "1"
_LAST_COMMAND_FILE: Optional[pathlib.Path] = None
_corr_seq = 0

if _TRAIL_ENABLED:
    _TRAIL_DIR = pathlib.Path.home() / "Library" / "Logs" / "prose_overlay_trail"
    _TRAIL_DIR.mkdir(parents=True, exist_ok=True)
    # File handle MUST live for the process lifetime — see faulthandler docs.
    # Buffering=0 is implicit for the underlying fd; line buffering at the
    # Python wrapper is fine because the C-level handler bypasses the wrapper.
    _fault_fp = open(_TRAIL_DIR / "faulthandler.log", "a", buffering=1)
    # chain=True is the 3.10+ default — keep explicit so any Talon-installed
    # handler still runs after ours.
    faulthandler.enable(file=_fault_fp, all_threads=True, chain=True)
    _LAST_COMMAND_FILE = _TRAIL_DIR / "last_command.json"


def _next_corr_id() -> str:
    """Monotonic correlation id — process pid + sequence number."""
    global _corr_seq
    _corr_seq += 1
    return f"{os.getpid()}-{_corr_seq:06d}"


def _atomic_write_json(path: pathlib.Path, data: dict) -> None:
    """Write JSON via tmp + os.replace. Crash mid-write leaves prior file intact."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, path)


def begin_command(utterance: str, action: str, args: Optional[dict] = None) -> Optional[str]:
    """Write a preamble to last_command.json BEFORE the risky call fires.

    Returns the correlation id, or None when the trail is disabled.
    """
    if not _TRAIL_ENABLED or _LAST_COMMAND_FILE is None:
        return None
    corr_id = _next_corr_id()
    _atomic_write_json(_LAST_COMMAND_FILE, {
        "corr_id":    corr_id,
        "utterance":  utterance,
        "action":     action,
        "args":       args or {},
        "started_at": datetime.now().isoformat(timespec="milliseconds"),
        "ok":         None,
        "err":        None,
        "ended_at":   None,
    })
    return corr_id


def end_command(corr_id: Optional[str], ok: bool = True, err: Optional[str] = None) -> None:
    """Overwrite last_command.json with the end-of-call status. No-op when disabled."""
    if not _TRAIL_ENABLED or corr_id is None or _LAST_COMMAND_FILE is None:
        return
    try:
        with open(_LAST_COMMAND_FILE) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        data = {"corr_id": corr_id}
    data["ok"] = bool(ok)
    data["err"] = err
    data["ended_at"] = datetime.now().isoformat(timespec="milliseconds")
    _atomic_write_json(_LAST_COMMAND_FILE, data)
