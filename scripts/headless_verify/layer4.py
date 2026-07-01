"""Layer 4 — meta (codebase portability audit).

Thin wrapper — shells out to scripts/layer-audit.py which owns the
INTERNAL + CURSORLESS talon-free invariants (I1-I5). We don't
re-implement the audit here; running it captures the same contract
and gives us one canonical place to update layer assignments when
new files land.
"""

import subprocess
import sys

from .common import test, REPO, GREEN, RED, DIM, RESET


def run_layer_4() -> None:
    """Meta — structural overfit test. Defers to scripts/layer-audit.py."""
    print(f"\n=== Layer 4 — Meta (codebase portability — {DIM}scripts/layer-audit.py{RESET}) ===")
    with test("L4", "L4.1", "INTERNAL + CURSORLESS layers are talon-free (portable substrate)"):
        # The layer-audit script returns 0 on pass, 1 on overfit. We don't
        # re-implement the invariants here — running it captures the same
        # contract and gives the user one canonical place to update layer
        # assignments when new files land.
        result = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "layer-audit.py")],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Print the audit output verbatim so the failing rows are visible
        # in this runner's transcript even when overfit is present.
        if result.stdout.strip():
            for line in result.stdout.splitlines():
                if line.strip():
                    print(f"        {line}")
        assert result.returncode == 0, (
            "layer-audit.py reported overfit findings — see output above. "
            "Refactor the FAIL items into the correct layer, OR update the "
            "layer assignment in scripts/layer-audit.py if the categorization "
            "is wrong."
        )
