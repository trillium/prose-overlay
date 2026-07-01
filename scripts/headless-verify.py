#!/usr/bin/env python3
"""Headless verification runner — see docs/HEADLESS_VERIFY_PLAN.md.

Thin orchestrator. Each layer lives in its own file under
``scripts/headless_verify/``; this file just runs them in order and
emits the summary + failures block. Splitting the layers into their
own modules keeps any single file readable (the pre-split monolith
was ~2260 lines) and lets the runner pick up new layers by adding
one import + one call below.

Usage: python3 scripts/headless-verify.py
"""

# Make `scripts/headless_verify/` importable as a package regardless of
# the cwd this script is launched from. Repo root is the parent of the
# scripts dir; adding it to sys.path lets `headless_verify.*` resolve.
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from headless_verify.common import GREEN, RED, RESET, results
from headless_verify.layer1 import run_layer_1
from headless_verify.layer2 import run_layer_2
from headless_verify.layer3 import run_layer_3
from headless_verify.layer4 import run_layer_4
from headless_verify.layer5 import run_layer_5


def main() -> int:
    print("Headless verify — see docs/HEADLESS_VERIFY_PLAN.md\n")
    run_layer_1()
    run_layer_2()
    run_layer_3()
    run_layer_4()
    run_layer_5()

    passed = sum(1 for *_, ok, _ in results if ok)
    total = len(results)
    color = GREEN if passed == total else RED
    print(f"\n{color}Summary: {passed}/{total} passed{RESET}")
    if passed < total:
        print("\nFailures:")
        for layer, tid, ok, detail in results:
            if not ok:
                print(f"  {RED}{layer}/{tid}{RESET}: {detail}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
