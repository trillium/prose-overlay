"""Layer 2 — JS bundle via bun.

Sanity-checks that the shipped js/prose_allocate_hats.js loads under
bun and produces expected hat assignments for a handful of fixtures.
Bun is a hard dep here; if the CI environment doesn't have it, this
layer will fail loudly rather than silently skipping.
"""

import json
import pathlib
import subprocess

from .common import DIM, HAT_JS, RESET, test

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

    # L2.6 — post-2026-07-01 un-strip: shape identifiers survive esbuild's
    # tree-shake into the shipped hat bundle, AND the targets bundle still
    # ships WordScopeHandler (piggyback probe from docs/SUBWORD_INVESTIGATION.md
    # §1 so a future rebuild that accidentally tree-shakes it out flags
    # here first). If either grep returns 0 the bundle was built from the
    # wrong source (or the tree-shaker aggressively dropped the vocabulary)
    # and the shim can't opt into shape-suffixed style names / sub-word
    # scope. See docs/BUNDLE_SHAPE_SCOPE.md §3 and docs/SUBWORD_INVESTIGATION.md §1.
    with test(
        "L2",
        "L2.6",
        "hats bundle: shape identifiers + styleName + proseBuildEnabledHatStyles; targets bundle: WordScopeHandler",
    ):
        hats_bundle = pathlib.Path(HAT_JS).read_text()
        # Shape suffix vocabulary — un-stripped 2026-07-01.
        assert "frame" in hats_bundle, "shape identifier 'frame' missing from hats bundle — un-strip regressed"
        assert "crosshairs" in hats_bundle, "shape identifier 'crosshairs' missing from hats bundle"
        # New helper name is a strong signal the hats bundle was rebuilt
        # from the post-un-strip source (globalThis attach, not tree-shakeable).
        assert (
            "proseBuildEnabledHatStyles" in hats_bundle
        ), "proseBuildEnabledHatStyles missing — hats bundle predates un-strip"
        # New styleName field on the return dict — Slice 1 contract.
        assert "styleName" in hats_bundle, "styleName field missing — hats bundle predates un-strip"
        # Targets bundle — verify sub-word scope substrate still present.
        # Independent of shape work but rebuilds could break it, so
        # keep the probe alongside the shape probes per parent instruction.
        targets_bundle = (pathlib.Path(HAT_JS).parent / "prose_resolve_targets.js").read_text()
        assert (
            "WordScopeHandler" in targets_bundle
        ), "WordScopeHandler missing from targets bundle — see docs/SUBWORD_INVESTIGATION.md §1"

    # L2.7 — 5th arg round-trip. Backward-compat and shape-enabled paths.
    with test(
        "L2",
        "L2.7",
        "proseAllocateHats accepts 5th enabledStylesJson arg + returns styleName",
    ):
        # Default (no 5th arg) — styleName present, no shape suffix.
        r_default = _run_bun_probe(["hello", "world"])
        assert (
            "styleName" in r_default["0"]
        ), f"styleName field missing on default: {r_default['0']!r}"
        assert (
            "-" not in r_default["0"]["styleName"]
        ), f"default should have no shape suffix, got {r_default['0']['styleName']!r}"

        # Shape-enabled (5th arg = full map from proseBuildEnabledHatStyles).
        script = f"""
const code = require('fs').readFileSync('{HAT_JS}', 'utf8');
eval(code);
const enabled = globalThis.proseBuildEnabledHatStyles(true);
const parsed = JSON.parse(enabled);
if (Object.keys(parsed).length !== 99) {{
  process.stderr.write('expected 99 entries, got ' + Object.keys(parsed).length);
  process.exit(2);
}}
if (!('blue-frame' in parsed)) {{
  process.stderr.write('blue-frame missing from full map');
  process.exit(2);
}}
const out = globalThis.proseAllocateHats(
  JSON.stringify(['hello']),
  JSON.stringify([]),
  'balanced',
  '-1',
  enabled
);
process.stdout.write(out);
"""
        tmp = pathlib.Path("/tmp/headless-verify-bun-shape.js")
        tmp.write_text(script)
        proc = subprocess.run(
            ["bun", str(tmp)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert proc.returncode == 0, f"bun exit {proc.returncode}: {proc.stderr[:200]}"
        r_shape = json.loads(proc.stdout)
        assert "0" in r_shape, f"missing hat: {r_shape}"
        assert "styleName" in r_shape["0"], f"styleName absent under shape-enabled: {r_shape}"

