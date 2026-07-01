"""Shared setup for the headless verify layers.

Every layer file (``layer1.py`` … ``layer5.py``) imports from here so the
paths, colors, results list, ``test()`` context, and module-loading
helpers have exactly one source of truth. Adding a new layer? Import
what you need from ``.common`` and register a ``run_layer_N`` function
that the top-level ``scripts/headless-verify.py`` orchestrator calls.
"""

import importlib.util
import pathlib
from contextlib import contextmanager

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# scripts/headless_verify/common.py → repo root is parent×3.
REPO = pathlib.Path(__file__).resolve().parent.parent.parent
STATE_PY = REPO / "internal" / "state.py"
HAT_JS = REPO / "js" / "prose_allocate_hats.js"
ACTIONS_JS = REPO / "js" / "prose_actions.js"
RESOLVE_JS = REPO / "js" / "prose_resolve_targets.js"
TEST_DRIVER_PY = REPO / "ui" / "test_driver.py"

# ---------------------------------------------------------------------------
# Terminal formatting
# ---------------------------------------------------------------------------

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"

# ---------------------------------------------------------------------------
# Test framework
# ---------------------------------------------------------------------------

# (layer, id, passed, detail). Mutated in place by test(); the runner
# reads it at the end to emit the summary + Failures block.
results: list[tuple[str, str, bool, str]] = []


@contextmanager
def test(layer: str, tid: str, desc: str):
    """Context manager wrapping each named test.

    Body raises AssertionError → row marked FAIL with the assert message.
    Body raises anything else → row marked FAIL as UNCAUGHT <Type>.
    Body completes cleanly → row marked [x].
    """
    try:
        yield
        results.append((layer, tid, True, desc))
        print(f"  {GREEN}[x]{RESET} {tid}: {desc}")
    except AssertionError as e:
        results.append((layer, tid, False, f"{desc} — {e}"))
        print(f"  {RED}[ ]{RESET} {tid}: FAIL — {desc} — {e}")
    except Exception as e:
        results.append((layer, tid, False, f"{desc} — UNCAUGHT {type(e).__name__}: {e}"))
        print(f"  {RED}[ ]{RESET} {tid}: FAIL — {desc} — UNCAUGHT {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Cross-layer module loaders
# ---------------------------------------------------------------------------

def _load_state_module():
    """Load internal/state.py as ``prose_overlay_state``.

    Used by Layer 1 (ProseBuffer + compute_hat_assignments) and (via
    Layer 5's synthetic package machinery) by the resolver-parity
    harness — both need to import the file without pulling talon in.
    """
    spec = importlib.util.spec_from_file_location("prose_overlay_state", STATE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_instance_module():
    """Load internal/instance.py — ProseOverlayState is dependency-free."""
    spec = importlib.util.spec_from_file_location(
        "prose_overlay_instance",
        REPO / "internal" / "instance.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
