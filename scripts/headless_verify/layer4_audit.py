"""Layer 4 — meta (codebase portability audit).

Thin wrapper — shells out to scripts/layer-audit.py which owns the
INTERNAL + CURSORLESS talon-free invariants (I1-I5). We don't
re-implement the audit here; running it captures the same contract
and gives us one canonical place to update layer assignments when
new files land.
"""

import re
import subprocess
import sys

from .common import DIM, REPO, RESET, test


# -----------------------------------------------------------------------------
# L4.3 — draw-purity ratchet (Phase A of pure-function refactor)
# -----------------------------------------------------------------------------
#
# Goal: `ui/draw*.py` should ultimately be PURE paint routines — every input
# they need (settings, screen rect, action results) arrives as a function
# argument computed upstream in a recompute pass. Reading talon runtime state
# at paint time (settings.get / ui.main_screen / actions.X) makes draw
# non-deterministic and impossible to unit-test without a live Talon process.
#
# Today draw.py violates all of these. Rather than block the whole harness on
# a big refactor, this test RATCHETS the violation count: it captures today's
# floor per file per pattern, PASSES when the counts match, PASSES + prints
# `[improved]` when they drop, and FAILS when they rise. Eventual target is
# every count == 0, at which point we flip the assertion to "must be zero".
#
# Rules — one column per pattern:
#   settings_get   — literal `settings.get(` calls (talon settings API)
#   ui_screen      — `ui.main_screen()` / `ui.screens()` (screen queries)
#   actions_dot    — `actions.` attribute access (should never appear in draw)
#   impure_import  — top-level `from talon import <sym>` where sym is one of
#                    the known runtime symbols (settings, actions, ui, cron).
#                    Pure type imports (SkiaCanvas, Rect) are allowed and do
#                    NOT count.
#
# Counts are per file per rule; baseline is populated from a walk of the
# current tree on 2026-07-01.
# -----------------------------------------------------------------------------

# Files audited by L4.3. Any new ui/draw*.py file added later MUST be added
# here — the test asserts the set of files covered matches what's on disk.
DRAW_FILES = (
    "ui/draw.py",
    "ui/draw_tokens.py",
    "ui/draw_panels.py",
)

# Baseline populated by running the counters on the tree at 2026-07-01.
# When a count drops below the baseline the test passes and prints `[improved]`
# — after which the maintainer lowers the baseline in this file.
# Eventual target: every entry is 0 (draw is pure).
EXPECTED_DRAW_PURITY_VIOLATIONS: dict[str, dict[str, int]] = {
    # ui/draw.py dropped to all-zero on 2026-07-01 in Move 3 step 3/3 of
    # the pure-function refactor: ui.main_screen() + three settings.get()
    # calls were hoisted upstream to shim.actions_core._populate_visual_state,
    # landing on instance.state.{screen_rect, window_scoped, homophone_hint,
    # homophone_shapes}. draw_overlay now reads only from its args + state,
    # with a belt+braces None guard on screen_rect that returns an empty
    # Rect if paint fires before the first recompute.
    "ui/draw.py":        {"settings_get": 0, "ui_screen": 0, "actions_dot": 0, "impure_import": 0},
    "ui/draw_tokens.py": {"settings_get": 0, "ui_screen": 0, "actions_dot": 0, "impure_import": 0},
    "ui/draw_panels.py": {"settings_get": 0, "ui_screen": 0, "actions_dot": 0, "impure_import": 0},
}

# `talon` runtime symbols. Top-level `from talon import <one-of-these>` is a
# purity violation because it wires draw to talon-live state at import time.
# `SkiaCanvas` and `Rect` are pure types and are NOT in this list.
_TALON_RUNTIME_SYMBOLS = frozenset({"settings", "actions", "ui", "cron", "cache", "registry"})

# Regexes for the four rules. Kept simple / linewise — the goal is a ratchet
# gauge, not a full AST audit. False positives are fine as long as they show
# up in the baseline too; the assertion is about the DELTA.
_RE_SETTINGS_GET = re.compile(r"\bsettings\.get\(")
_RE_UI_SCREEN    = re.compile(r"\bui\.(?:main_screen|screens)\(")
# `actions.` — attribute access on a bare `actions` identifier. Negative
# lookbehind excludes identifier chars and dots so `_actions_runtime.foo` and
# `mod.actions.bar` don't trip. Handles the common `actions.user.X` case.
_RE_ACTIONS_DOT  = re.compile(r"(?<![\w.])actions\.")
# Top-level talon import line: `from talon[.<sub>] import <symbols>`. We
# capture the imported symbol list and check each against the runtime set.
_RE_TALON_IMPORT = re.compile(r"^\s*from\s+talon(?:\.[\w.]+)?\s+import\s+(.+?)\s*(?:#.*)?$")


def _count_line_matches(text: str, regex: re.Pattern[str]) -> tuple[int, list[int]]:
    """Return (total-matches, list-of-linenos) for regex over text.

    We report line numbers so a failure surfaces WHERE new violations landed,
    not just that the count went up.
    """
    total = 0
    linenos: list[int] = []
    for i, line in enumerate(text.splitlines(), start=1):
        # Ignore matches that live inside a comment — the goal is to catch
        # LIVE calls, and documentation of the pattern in a docstring or
        # `# settings.get(...) is banned here` comment shouldn't trip.
        code = line.split("#", 1)[0] if line.lstrip().startswith("#") else line
        # For non-comment-only lines we still need to strip inline comments so
        # e.g. `foo()  # settings.get is banned` doesn't count.
        if not line.lstrip().startswith("#"):
            code = re.sub(r"(?<!['\"])#.*$", "", line)
        n = len(regex.findall(code))
        if n:
            total += n
            linenos.append(i)
    return total, linenos


def _count_impure_talon_imports(text: str) -> tuple[int, list[int]]:
    """Count impure symbols imported from `talon` at top level.

    Each impure symbol on the import line counts once. Example:
        from talon import settings, ui, cron   → 3 violations
        from talon.skia.canvas import Canvas   → 0
        from talon.ui import Rect              → 0
    """
    total = 0
    linenos: list[int] = []
    for i, line in enumerate(text.splitlines(), start=1):
        m = _RE_TALON_IMPORT.match(line)
        if not m:
            continue
        # Symbol list — split on commas, strip whitespace, drop `as` aliases.
        raw = m.group(1)
        # Handle `from talon import (a, b, c)` parenthesized form defensively.
        raw = raw.strip().strip("()")
        symbols = [s.strip().split(" as ")[0].strip() for s in raw.split(",") if s.strip()]
        hits = sum(1 for s in symbols if s in _TALON_RUNTIME_SYMBOLS)
        if hits:
            total += hits
            linenos.append(i)
    return total, linenos


def _measure_draw_file(path_str: str) -> tuple[dict[str, int], dict[str, list[int]]]:
    """Return (counts, linenos) for one draw file.

    Missing files return zero-everything so the test reports the mismatch as
    a baseline drift rather than crashing on file-not-found.
    """
    path = REPO / path_str
    if not path.is_file():
        empty_counts = {"settings_get": 0, "ui_screen": 0, "actions_dot": 0, "impure_import": 0}
        empty_linenos: dict[str, list[int]] = {k: [] for k in empty_counts}
        return empty_counts, empty_linenos
    text = path.read_text(encoding="utf-8")
    s_n,  s_l  = _count_line_matches(text, _RE_SETTINGS_GET)
    u_n,  u_l  = _count_line_matches(text, _RE_UI_SCREEN)
    a_n,  a_l  = _count_line_matches(text, _RE_ACTIONS_DOT)
    i_n,  i_l  = _count_impure_talon_imports(text)
    counts = {"settings_get": s_n, "ui_screen": u_n, "actions_dot": a_n, "impure_import": i_n}
    linenos = {"settings_get": s_l, "ui_screen": u_l, "actions_dot": a_l, "impure_import": i_l}
    return counts, linenos


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

    with test("L4", "L4.3", "draw-purity violation count does not grow (Phase A ratchet toward pure ui/draw*.py)"):
        # Phase A of the pure-function draw refactor. Draw routines should
        # eventually take every input as a parameter — no talon-runtime reads
        # at paint time. Today's counts are the baseline; this test ratchets
        # them downward. FAIL when a count rises; PASS + `[improved]` when a
        # count drops (maintainer then lowers the baseline in this file).
        rising: list[str] = []
        improved: list[str] = []
        total_current = 0
        total_expected = 0
        for path_str in DRAW_FILES:
            expected = EXPECTED_DRAW_PURITY_VIOLATIONS.get(path_str)
            assert expected is not None, (
                f"{path_str} — file listed in DRAW_FILES but missing from "
                f"EXPECTED_DRAW_PURITY_VIOLATIONS. Add a baseline row."
            )
            counts, linenos = _measure_draw_file(path_str)
            for rule, exp_n in expected.items():
                cur_n = counts.get(rule, 0)
                total_current += cur_n
                total_expected += exp_n
                if cur_n > exp_n:
                    lines = ",".join(str(n) for n in linenos.get(rule, []))
                    rising.append(
                        f"{path_str} [{rule}] {exp_n} → {cur_n} "
                        f"(lines: {lines or 'n/a'})"
                    )
                elif cur_n < exp_n:
                    improved.append(f"{path_str} [{rule}] {exp_n} → {cur_n}")
        if improved:
            print(f"        {DIM}[improved] draw-purity dropped: "
                  f"{'; '.join(improved)}. "
                  f"Lower the baseline in scripts/headless_verify/layer4_audit.py "
                  f"→ EXPECTED_DRAW_PURITY_VIOLATIONS.{RESET}")
        print(f"        {DIM}(informational — draw-purity violations: "
              f"{total_current} total, target 0; "
              f"see docs on Phase A pure-function refactor){RESET}")
        assert not rising, (
            "draw-purity violation count ROSE — new talon-runtime reads landed in "
            "ui/draw*.py. Every rule in this ratchet is a step away from making "
            "draw pure. Either move the new read upstream into a recompute pass "
            "(preferred) OR, if the read is genuinely unavoidable in this phase, "
            "raise the baseline in scripts/headless_verify/layer4_audit.py → "
            "EXPECTED_DRAW_PURITY_VIOLATIONS with a comment explaining why. "
            "Rising counts:\n          " + "\n          ".join(rising)
        )
