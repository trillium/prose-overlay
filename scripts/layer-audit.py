#!/usr/bin/env python3
"""Layer overfit audit — see docs/LAYER_AUDIT.md.

Asserts the structural invariants that keep prose-overlay portable. Each .py
module is explicitly assigned to one of four layers; the auditor then checks
that the layer's import rules hold. Failures are "overfit" — code that has
leaked across a boundary it shouldn't have.

Layers (top → bottom in dependency direction):

  4. UI       (Talon-canvas, voice grammar, action classes; freely Talon)
  3. SHIM     (Talon ↔ {INTERNAL, CURSORLESS} bridges; only allowed
               import-both layer)
  2. CURSORLESS (Python re-impl of cursorless logic; ports anywhere that has
               a token/text buffer)
  1. INTERNAL (Pure substrate — ProseBuffer, undo/redo, homophone CSV,
               viewport math; ports anywhere with no Talon)

The meta-test: this script asserts the layering is honest. If it passes, the
INTERNAL + CURSORLESS layers are viable primitives in another environment
(VS Code, Vim, web, …) — drop in a different SHIM and a different UI and
the buffer logic + cursorless resolution come for free.

Exits 0 on pass, 1 on overfit findings.

Run standalone: `python3 scripts/layer-audit.py`
Or as part of the full suite: `python3 scripts/headless-verify.py`
"""

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

# -----------------------------------------------------------------------------
# Layer assignment — explicit per-file. New files MUST be added here.
# -----------------------------------------------------------------------------

INTERNAL: set[str] = {
    "prose_overlay_state.py",          # ProseBuffer + undo/redo + hat allocator
    "prose_overlay_instance.py",       # shared state container
    "prose_overlay_homophones.py",     # CSV loader + flag lookup
    "prose_overlay_debug.py",          # JSONL snapshot writer
    "prose_overlay_draw_constants.py", # pure visual constants (no Skia types)
    "prose_overlay_trail.py",          # faulthandler + atomic JSON writer
    "prose_overlay_viewport.py",       # scroll/anchor math
}

CURSORLESS: set[str] = {
    "prose_overlay_cursorless_resolve.py",  # Python re-impl of processTargets
    "prose_overlay_surrounding_pair.py",    # cursorless delimiter pair handler
}

SHIM: set[str] = {
    # Talon → QuickJS (cursorless bundles)
    "prose_overlay_hats_js.py",
    "prose_overlay_targets_js.py",
    "prose_overlay_actions_js.py",
    # Talon action surface routing to cursorless
    "prose_overlay_actions_cursorless.py",
    "prose_overlay_actions_cursorless_edit.py",
    "prose_overlay_actions_target.py",
    # _recompute_hats / _hat_to_index — Talon-state mgmt that crosses layers
    "prose_overlay_actions_core.py",
    # SVG vocab (portable) + Skia paint (Talon, LAZY-imported)
    "prose_overlay_shapes.py",
}

UI: set[str] = {
    "prose_overlay.py",
    "prose_overlay_canvas.py",
    "prose_overlay_draw.py",
    "prose_overlay_draw_tokens.py",
    "prose_overlay_help.py",
    "prose_overlay_history_panel.py",
    # Talon action classes (voice + canvas interaction)
    "prose_overlay_actions_bring_move.py",
    "prose_overlay_actions_cursor.py",
    "prose_overlay_actions_delete.py",
    "prose_overlay_actions_flash.py",
    "prose_overlay_actions_help.py",
    "prose_overlay_actions_history.py",
    "prose_overlay_actions_layout.py",
    "prose_overlay_actions_visibility.py",
    # Talon cron-driven test queue
    "prose_overlay_test_driver.py",
}

LAYER_OF: dict[str, str] = (
    {f: "INTERNAL"  for f in INTERNAL}
    | {f: "CURSORLESS" for f in CURSORLESS}
    | {f: "SHIM"    for f in SHIM}
    | {f: "UI"      for f in UI}
)

# -----------------------------------------------------------------------------
# Import detection
# -----------------------------------------------------------------------------

TALON_IMPORT_RE = re.compile(r"^\s*(?:from\s+talon(?:\.[\w.]+)?\s+import|import\s+talon(?:\.[\w.]+)?)", re.MULTILINE)
LAZY_TALON_RE = re.compile(r"^\s+(?:from\s+talon(?:\.[\w.]+)?\s+import|import\s+talon(?:\.[\w.]+)?)", re.MULTILINE)
INTERNAL_IMPORT_RE = re.compile(r"^\s*from\s+\.prose_overlay_cursorless_resolve\b|^\s*from\s+\.prose_overlay_surrounding_pair\b", re.MULTILINE)


def top_level_talon_imports(path: pathlib.Path) -> list[tuple[int, str]]:
    """Return (lineno, line) pairs for top-level talon imports."""
    out: list[tuple[int, str]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.startswith(("from talon", "import talon")):
            out.append((i, line.strip()))
    return out


def imports_cursorless_resolver(path: pathlib.Path) -> bool:
    return bool(INTERNAL_IMPORT_RE.search(path.read_text(encoding="utf-8")))


# -----------------------------------------------------------------------------
# Findings infrastructure
# -----------------------------------------------------------------------------

findings: list[tuple[str, str, str]] = []  # (severity, code, message)


def fail(code: str, message: str) -> None:
    findings.append(("FAIL", code, message))


def warn(code: str, message: str) -> None:
    findings.append(("WARN", code, message))


# -----------------------------------------------------------------------------
# Invariants
# -----------------------------------------------------------------------------

def check_invariant_1_internal_no_talon(py_files: list[pathlib.Path]) -> None:
    """INTERNAL layer files must not import from talon at top level."""
    for p in py_files:
        if p.name not in INTERNAL:
            continue
        leaks = top_level_talon_imports(p)
        if leaks:
            for lineno, line in leaks:
                fail(
                    "I1.INTERNAL_TALON_IMPORT",
                    f"{p.name}:{lineno} — INTERNAL layer file imports talon ({line!r}). "
                    f"Refactor: move to SHIM, or replace talon.X with a pure-Python equivalent.",
                )


def check_invariant_2_cursorless_no_talon(py_files: list[pathlib.Path]) -> None:
    """CURSORLESS layer files (Python re-impl) must not import from talon."""
    for p in py_files:
        if p.name not in CURSORLESS:
            continue
        leaks = top_level_talon_imports(p)
        if leaks:
            for lineno, line in leaks:
                fail(
                    "I2.CURSORLESS_TALON_IMPORT",
                    f"{p.name}:{lineno} — CURSORLESS layer file imports talon ({line!r}). "
                    f"Refactor: this layer must be portable across editor environments.",
                )


def check_invariant_3_ui_no_resolver(py_files: list[pathlib.Path]) -> None:
    """UI layer files should not import from the Python cursorless resolver
    or surrounding_pair directly — that crosses through the SHIM layer."""
    for p in py_files:
        if p.name not in UI:
            continue
        if imports_cursorless_resolver(p):
            warn(
                "I3.UI_BYPASSES_SHIM",
                f"{p.name} — UI layer file imports CURSORLESS layer directly. "
                f"Refactor: route through a SHIM module instead.",
            )


def check_invariant_4_all_files_categorized(py_files: list[pathlib.Path]) -> None:
    """Every prose_overlay_*.py file must be assigned to exactly one layer."""
    seen = {p.name for p in py_files}
    all_categorized = INTERNAL | CURSORLESS | SHIM | UI
    uncategorized = seen - all_categorized
    for f in sorted(uncategorized):
        fail(
            "I4.UNCATEGORIZED",
            f"{f} — not assigned to any layer. "
            f"Add to INTERNAL / CURSORLESS / SHIM / UI in scripts/layer-audit.py.",
        )
    stale = all_categorized - seen
    for f in sorted(stale):
        warn(
            "I4.STALE_CATEGORIZATION",
            f"{f} — listed in a layer set but the file does not exist. Remove from layer-audit.",
        )


def check_invariant_5_internal_has_no_lazy_talon(py_files: list[pathlib.Path]) -> None:
    """INTERNAL layer files should not have lazy-imported talon either —
    even a function-local talon import means the function can't run in a
    non-Talon environment."""
    for p in py_files:
        if p.name not in INTERNAL:
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
            # Skip top-level matches (caught by I1)
            if line.startswith(("from talon", "import talon")):
                continue
            stripped = line.lstrip()
            if (stripped.startswith("from talon") or stripped.startswith("import talon")) and len(line) > len(stripped):
                fail(
                    "I5.INTERNAL_LAZY_TALON",
                    f"{p.name}:{i} — INTERNAL layer has a lazy talon import ({line.strip()!r}). "
                    f"Pure layer must not depend on talon at any call site.",
                )


# -----------------------------------------------------------------------------
# Driver
# -----------------------------------------------------------------------------

def collect_py_files() -> list[pathlib.Path]:
    return sorted(REPO.glob("prose_overlay*.py"))


def print_report(passed: bool) -> None:
    fails = [f for f in findings if f[0] == "FAIL"]
    warns = [f for f in findings if f[0] == "WARN"]
    print(f"\n=== Layer Audit — {len(fails)} fail, {len(warns)} warn ===\n")
    if fails:
        print("FAIL findings:")
        for sev, code, msg in fails:
            print(f"  [{code}] {msg}")
        print()
    if warns:
        print("WARN findings (advisory, not blocking):")
        for sev, code, msg in warns:
            print(f"  [{code}] {msg}")
        print()
    if not findings:
        print("All layer invariants hold. INTERNAL + CURSORLESS are portable.")


def main() -> int:
    py_files = collect_py_files()
    check_invariant_4_all_files_categorized(py_files)  # run first to flag stragglers
    check_invariant_1_internal_no_talon(py_files)
    check_invariant_2_cursorless_no_talon(py_files)
    check_invariant_3_ui_no_resolver(py_files)
    check_invariant_5_internal_has_no_lazy_talon(py_files)
    print_report(passed=not any(f[0] == "FAIL" for f in findings))
    return 0 if not any(f[0] == "FAIL" for f in findings) else 1


if __name__ == "__main__":
    sys.exit(main())
