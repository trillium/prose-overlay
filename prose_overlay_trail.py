"""Prose overlay paper trail — Slice A: faulthandler to a fixed file.

Gated on the env var ``PROSE_OVERLAY_TRAIL``: set it to ``"1"`` before
launching Talon to enable. Anything else (including unset) leaves this
module a no-op — no fd is opened, no signal handler is registered.

To disable: ``unset PROSE_OVERLAY_TRAIL`` and restart Talon. The flag is
checked once at module import; there is no runtime toggle. See
``docs/STACK_OVERFLOW_PAPER_TRAIL_PLAN.md`` for the full slice spec.
"""

import faulthandler
import os
import pathlib

_TRAIL_ENABLED = os.environ.get("PROSE_OVERLAY_TRAIL") == "1"

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
