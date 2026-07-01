"""Layer 4 — meta (codebase portability audit).

Thin wrapper — shells out to scripts/layer-audit.py which owns the
INTERNAL + CURSORLESS talon-free invariants (I1-I5). We don't
re-implement the audit here; running it captures the same contract
and gives us one canonical place to update layer assignments when
new files land.
"""

import subprocess
import sys

from .common import DIM, REPO, RESET, test


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

    with test("L4", "L4.2", "ruff finds no real bugs (F/E/W minus stylistic E501/E731)"):
        # Enforced code-quality gate. Rule selection:
        #   F* — pyflakes: unused imports, redefinitions, unused locals,
        #        f-strings without placeholders. All real bugs.
        #   E*/W* — pycodestyle: syntax + whitespace correctness. Real.
        #   E501 line-length + E731 lambda: ignored — stylistic only,
        #        long asserts + one-off lambdas in tests are fine.
        # Ruff is a soft dep — if it isn't installed the test skips with
        # a hint rather than failing, so contributors without their
        # env set up can still run the rest of the harness.
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m", "ruff", "check",
                    "internal/", "shim/", "ui/", "cursorless/", "scripts/",
                    "--select=F,E,W",
                    "--ignore=E501,E731",
                    "--output-format=concise",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=str(REPO),
            )
        except FileNotFoundError as e:
            # `python -m ruff` bubbles a FileNotFoundError only if python
            # itself is missing; ruff-missing shows as `No module named ruff`
            # in stderr with a non-zero exit code. Handle both.
            print(f"        {DIM}(ruff invocation failed: {e}; skipping){RESET}")
            return
        if result.returncode != 0 and "No module named ruff" in result.stderr:
            print(f"        {DIM}(ruff not installed — pip install ruff to enable; skipping){RESET}")
            return
        if result.stdout.strip():
            for line in result.stdout.splitlines():
                if line.strip():
                    print(f"        {line}")
        assert result.returncode == 0, (
            "ruff found real code-quality issues — see output above. "
            "Fix by hand OR autofix most of them with: "
            "python3 -m ruff check --select=F,E,W --ignore=E501,E731 --fix ."
        )
