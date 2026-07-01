"""Layer 2 — JS bundle via bun.

Sanity-checks that the shipped js/prose_allocate_hats.js loads under
bun and produces expected hat assignments for a handful of fixtures.
Bun is a hard dep here; if the CI environment doesn't have it, this
layer will fail loudly rather than silently skipping.
"""

import json
import pathlib
import subprocess

from .common import test, REPO, GREEN, RED, DIM, RESET, HAT_JS


# =============================================================================
# Layer 2 — JS bundle via bun
# =============================================================================

def _run_bun_probe(tokens: list[str]) -> dict:
    """Eval prose_allocate_hats.js in bun, call proseAllocateHats, return parsed result."""
    script = f"""
const code = require('fs').readFileSync('{HAT_JS}', 'utf8');
eval(code);
const out = globalThis.proseAllocateHats(
  JSON.stringify({json.dumps(tokens)}),
  JSON.stringify([]),
  'balanced',
  '-1',
);
process.stdout.write(out);
"""
    tmp = pathlib.Path("/tmp/headless-verify-bun-probe.js")
    tmp.write_text(script)
    proc = subprocess.run(
        ["bun", str(tmp)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if proc.returncode != 0:
        raise AssertionError(f"bun exited {proc.returncode}: {proc.stderr.strip()[:200]}")
    return json.loads(proc.stdout)


def run_layer_2() -> None:
    print(f"\n=== Layer 2 — JS bundle ({DIM}js/prose_allocate_hats.js via bun{RESET}) ===")

    with test("L2", "L2.1", "bun loads bundle without exception"):
        # Trivial: load the bundle and ensure globalThis.proseAllocateHats is a function.
        tmp = pathlib.Path("/tmp/headless-verify-bun-loadcheck.js")
        tmp.write_text(
            f"const code = require('fs').readFileSync('{HAT_JS}', 'utf8'); "
            f"eval(code); "
            f"if (typeof globalThis.proseAllocateHats !== 'function') process.exit(2);"
        )
        proc = subprocess.run(["bun", str(tmp)], capture_output=True, text=True, timeout=15)
        assert proc.returncode == 0, f"bun exit {proc.returncode}: {proc.stderr[:200]}"

    with test("L2", "L2.2", "proseAllocateHats(['foo','bar']) returns hats for both"):
        r = _run_bun_probe(["foo", "bar"])
        assert "0" in r and "1" in r, f"missing keys: {sorted(r.keys())}"

    with test("L2", "L2.3", "proseAllocateHats(['123']) returns hat for digit (regression 39b4cb6)"):
        r = _run_bun_probe(["123"])
        assert "0" in r, f"no hat for digit token: {r}"
        assert r["0"]["letter"] == "1", f"expected letter '1', got {r['0']!r}"

    with test("L2", "L2.4", "proseAllocateHats(['!']) returns hat for punct"):
        r = _run_bun_probe(["!"])
        assert "0" in r, f"no hat for punct: {r}"
        assert r["0"]["letter"] == "!", f"expected letter '!', got {r['0']!r}"

    with test("L2", "L2.5", "end-to-end user repro: ['testing','testing','123'] all get hats"):
        r = _run_bun_probe(["testing", "testing", "123"])
        assert {"0", "1", "2"}.issubset(r.keys()), f"missing keys: {sorted(r.keys())}"
        assert r["2"]["letter"] == "1", f"123 should hat letter '1', got {r['2']!r}"

