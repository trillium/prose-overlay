#!/usr/bin/env python3
"""Layer overfit audit — see docs/LAYER_AUDIT.md.

Asserts the structural invariants that keep prose-overlay portable. Each .py
module is assigned to one of four layers by the directory it lives in; the
auditor then checks that the layer's import rules hold. Failures are "overfit"
— code that has leaked across a boundary it shouldn't have.

Layers (top → bottom in dependency direction):

  4. UI         (ui/)         Talon canvas, voice grammar, action classes
                              The root prose_overlay.py also counts as UI —
                              it's the Talon entry point that wires settings,
                              tags, contexts, and imports every action module.
  3. SHIM       (shim/)       Talon ↔ {INTERNAL, CURSORLESS} bridges; the
                              only layer allowed to import from both above
                              and below.
  2. CURSORLESS (cursorless/) Python re-impl of cursorless logic; ports
                              anywhere with a token/text buffer.
  1. INTERNAL   (internal/)   Pure substrate — ProseBuffer, undo/redo,
                              homophone CSV, viewport math; ports anywhere
                              with no Talon.

The meta-test: this script asserts the layering is honest. If it passes, the
INTERNAL + CURSORLESS layers are viable primitives in another environment
(VS Code, Vim, web, …) — drop in a different SHIM and a different UI and
the buffer logic + cursorless resolution come for free.

Maintenance rule: a new .py file MUST live in one of the four layer
directories (or be `prose_overlay.py` at the root). New files inherit their
layer from the directory they sit in — no manual allowlist edit needed.

Exits 0 on pass, 1 on overfit findings.

Run standalone: `python3 scripts/layer-audit.py`
Or as part of the full suite: `python3 scripts/headless-verify.py`
"""

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent

# -----------------------------------------------------------------------------
# Directory → layer mapping. Files inherit their layer from their parent dir.
# The root prose_overlay.py is classified as UI (Talon entry point).
# -----------------------------------------------------------------------------

LAYER_DIRS: dict[str, str] = {
    "internal":   "INTERNAL",
    "cursorless": "CURSORLESS",
    "shim":       "SHIM",
    "ui":         "UI",
}

ROOT_UI_FILES: set[str] = {
    "prose_overlay.py",   # Talon entry point — settings/tags/contexts wiring
}


def layer_of(path: pathlib.Path) -> str | None:
    """Return the layer name for a given .py path, or None if uncategorized."""
    rel = path.relative_to(REPO)
    if rel.parent == pathlib.Path("."):
        if rel.name == "__init__.py":
            return None  # ignore package marker at root
        if rel.name in ROOT_UI_FILES:
            return "UI"
        return None
    layer = LAYER_DIRS.get(rel.parent.name)
    if layer is None:
        return None
    if rel.name == "__init__.py":
        return None  # ignore empty package markers inside layer dirs
    return layer


# -----------------------------------------------------------------------------
# Import detection
# -----------------------------------------------------------------------------

TALON_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+talon(?:\.[\w.]+)?\s+import|import\s+talon(?:\.[\w.]+)?)",
    re.MULTILINE,
)

# UI files should not reach into cursorless/ directly — that crosses the SHIM
# layer. We match any relative import that names `cursorless` as the first
# segment after the leading dots, e.g.
#   from .cursorless.resolve import ...       (root prose_overlay.py)
#   from ..cursorless.surrounding_pair ...    (a file inside ui/)
#   from ..cursorless import resolve          (rare, but caught)
UI_BYPASS_RE = re.compile(
    r"^\s*from\s+\.+cursorless(?:\.[\w_]+)*\s+import\b|"
    r"^\s*from\s+\.+\s+import\s+cursorless\b",
    re.MULTILINE,
)


def top_level_talon_imports(path: pathlib.Path) -> list[tuple[int, str]]:
    """Return (lineno, line) pairs for top-level talon imports."""
    out: list[tuple[int, str]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.startswith(("from talon", "import talon")):
            out.append((i, line.strip()))
    return out


def imports_cursorless_resolver(path: pathlib.Path) -> bool:
    return bool(UI_BYPASS_RE.search(path.read_text(encoding="utf-8")))


# -----------------------------------------------------------------------------
# Findings infrastructure
# -----------------------------------------------------------------------------

findings: list[tuple[str, str, str]] = []  # (severity, code, message)


def fail(code: str, message: str) -> None:
    findings.append(("FAIL", code, message))


def warn(code: str, message: str) -> None:
    findings.append(("WARN", code, message))


def _rel(path: pathlib.Path) -> str:
    """Path string relative to REPO for human-readable error messages."""
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


# -----------------------------------------------------------------------------
# Invariants
# -----------------------------------------------------------------------------

def check_invariant_1_internal_no_talon(py_files: list[pathlib.Path]) -> None:
    """INTERNAL layer files must not import from talon at top level."""
    for p in py_files:
        if layer_of(p) != "INTERNAL":
            continue
        leaks = top_level_talon_imports(p)
        for lineno, line in leaks:
            fail(
                "I1.INTERNAL_TALON_IMPORT",
                f"{_rel(p)}:{lineno} — INTERNAL layer file imports talon ({line!r}). "
                f"Refactor: move to SHIM, or replace talon.X with a pure-Python equivalent.",
            )


def check_invariant_2_cursorless_no_talon(py_files: list[pathlib.Path]) -> None:
    """CURSORLESS layer files (Python re-impl) must not import from talon."""
    for p in py_files:
        if layer_of(p) != "CURSORLESS":
            continue
        leaks = top_level_talon_imports(p)
        for lineno, line in leaks:
            fail(
                "I2.CURSORLESS_TALON_IMPORT",
                f"{_rel(p)}:{lineno} — CURSORLESS layer file imports talon ({line!r}). "
                f"Refactor: this layer must be portable across editor environments.",
            )


def check_invariant_3_ui_no_resolver(py_files: list[pathlib.Path]) -> None:
    """UI layer files should not import from the cursorless layer directly —
    that crosses through the SHIM layer."""
    for p in py_files:
        if layer_of(p) != "UI":
            continue
        if imports_cursorless_resolver(p):
            warn(
                "I3.UI_BYPASSES_SHIM",
                f"{_rel(p)} — UI layer file imports CURSORLESS layer directly. "
                f"Refactor: route through a SHIM module instead.",
            )


def check_invariant_4_all_files_categorized(py_files: list[pathlib.Path]) -> None:
    """Every .py file must live in a layer directory (or be the root entry
    point prose_overlay.py). Files in unknown locations are uncategorized."""
    for p in py_files:
        if layer_of(p) is None:
            fail(
                "I4.UNCATEGORIZED",
                f"{_rel(p)} — not assigned to any layer. "
                f"Move into internal/, cursorless/, shim/, or ui/, "
                f"or add to ROOT_UI_FILES in scripts/layer-audit.py "
                f"if it is another Talon entry point.",
            )


def check_invariant_5_internal_has_no_lazy_talon(py_files: list[pathlib.Path]) -> None:
    """INTERNAL layer files should not have lazy-imported talon either —
    even a function-local talon import means the function can't run in a
    non-Talon environment."""
    for p in py_files:
        if layer_of(p) != "INTERNAL":
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
            # Skip top-level matches (caught by I1)
            if line.startswith(("from talon", "import talon")):
                continue
            stripped = line.lstrip()
            if (stripped.startswith("from talon") or stripped.startswith("import talon")) and len(line) > len(stripped):
                fail(
                    "I5.INTERNAL_LAZY_TALON",
                    f"{_rel(p)}:{i} — INTERNAL layer has a lazy talon import ({line.strip()!r}). "
                    f"Pure layer must not depend on talon at any call site.",
                )


# -----------------------------------------------------------------------------
# Driver
# -----------------------------------------------------------------------------

def collect_py_files() -> list[pathlib.Path]:
    """Collect every .py file in the four layer directories and at the root.

    Skips:
      - __init__.py (empty package markers carry no logic to audit)
      - Anything outside the four layer dirs or root prose_overlay.py
        (those are flagged by I4 if they look like project files)
    """
    out: list[pathlib.Path] = []
    # Layer directories
    for layer_dir in LAYER_DIRS:
        d = REPO / layer_dir
        if not d.is_dir():
            continue
        out.extend(p for p in sorted(d.glob("*.py")) if p.name != "__init__.py")
    # Root entry point
    for name in sorted(ROOT_UI_FILES):
        p = REPO / name
        if p.is_file():
            out.append(p)
    return out


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
    check_invariant_4_all_files_categorized(py_files)
    check_invariant_1_internal_no_talon(py_files)
    check_invariant_2_cursorless_no_talon(py_files)
    check_invariant_3_ui_no_resolver(py_files)
    check_invariant_5_internal_has_no_lazy_talon(py_files)
    print_report(passed=not any(f[0] == "FAIL" for f in findings))
    return 0 if not any(f[0] == "FAIL" for f in findings) else 1


if __name__ == "__main__":
    sys.exit(main())
