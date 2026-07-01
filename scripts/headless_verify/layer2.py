"""Layer 2 — JS bundle via bun.

Sanity-checks that the shipped js/prose_allocate_hats.js loads under
bun and produces expected hat assignments for a handful of fixtures.
Bun is a hard dep here; if the CI environment doesn't have it, this
layer will fail loudly rather than silently skipping.
"""

import json
import pathlib
import subprocess

from .common import ACTIONS_JS, DIM, HAT_JS, RESET, RESOLVE_JS, test

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

    # L2.8 — Resolver bundle canonical inventory. Item #14 done properly per
    # docs/BUNDLE_REST_SCOPE.md §3. Every stage class a shipped grammar rule
    # can reach — plus the sub-word substrate (WordScopeHandler, WordTokenizer,
    # CAMEL_REGEX) — is fail-closed must-have. Absent-planned handlers are
    # printed informationally, never fail (until the corresponding wishlist
    # item ships, at which point the row moves into TARGETS_MUST_HAVE).
    #
    # Rationale for grep-shape ('var NAME = class' or 'var NAME = '):
    # esbuild emits IIFE bundles as 'var Foo = class {...}' at module scope
    # (see js/prose_resolve_targets.js:15505 for the canonical form).
    # Substring-grep is robust to bundle formatter changes; sub-class chains
    # (HeadStage / TailStage extend HeadTailStage) match 'var HeadStage = class'.
    with test(
        "L2",
        "L2.8",
        "resolver bundle canonical inventory — every wishlist stage present",
    ):
        src = pathlib.Path(RESOLVE_JS).read_text()
        # Fail-closed must-haves — every identifier a shipped grammar rule
        # or JS-only resolver path today can reach. See scope doc §1 for
        # the class → wishlist-item map.
        TARGETS_MUST_HAVE = (
            # Stage classes already reachable via the JS resolver default
            # (F9 landed 2026-06-30). Present in bundle line refs from
            # docs/BUNDLE_REST_SCOPE.md §1.
            ("EveryScopeStage", "var EveryScopeStage = class"),
            ("HeadStage", "var HeadStage = class"),
            ("TailStage", "var TailStage = class"),
            ("InteriorOnlyStage", "var InteriorOnlyStage = class"),
            ("ExcludeInteriorStage", "var ExcludeInteriorStage = class"),
            ("LeadingStage", "var LeadingStage = class"),
            ("TrailingStage", "var TrailingStage = class"),
            ("OrdinalScopeStage", "var OrdinalScopeStage = class"),
            ("RelativeScopeStage", "var RelativeScopeStage = class"),
            ("BoundedNonWhitespaceSequenceStage", "var BoundedNonWhitespaceSequenceStage = class"),
            # Sub-word substrate — from docs/SUBWORD_INVESTIGATION.md §1.
            # L2.6 already asserts WordScopeHandler for backward compat;
            # covering here too keeps this test's inventory self-contained.
            ("WordScopeHandler", "var WordScopeHandler = class"),
            ("WordTokenizer", "var WordTokenizer = class"),
            ("CAMEL_REGEX", "var CAMEL_REGEX ="),
        )
        missing = [name for name, needle in TARGETS_MUST_HAVE if needle not in src]
        assert not missing, (
            f"resolver bundle missing must-have identifiers: {missing} — "
            "either the tree-shaker got aggressive or proseTargetsStandalone.ts "
            "no longer pulls the full ModifierStageFactoryImpl. See "
            "docs/BUNDLE_REST_SCOPE.md §1."
        )

    # L2.9 — Actions bundle canonical inventory. Fail-closed on the 7 shipped
    # actions from proseActionsStandalone.ts:200-207 (regression guard for a
    # bad rebuild dropping one). Fail-informational for planned action names
    # from wishlist items #3 (swap), #4 (paste), #5 (wrap), #12 (clone),
    # #13 (reverse) — prints ABSENT-planned lines so a future rebuild that
    # ships one flips the row of its own accord (add to _MUST_HAVE when
    # shipping the wishlist item). See docs/BUNDLE_REST_SCOPE.md §3.
    with test(
        "L2",
        "L2.9",
        "actions bundle canonical inventory — 7 shipped actions present, planned actions inventoried",
    ):
        src = pathlib.Path(ACTIONS_JS).read_text()
        # Fail-closed: the seven shipped action names from the dispatcher
        # (proseRunAction switch at prose_actions.js:239-266). Each is
        # both a function definition and a string-form case label; probe
        # the string form since it's what the Python dispatcher sends.
        ACTIONS_MUST_HAVE = (
            "\"remove\"",
            "\"setSelection\"",
            "\"clearAndSetSelection\"",
            "\"replaceWithTarget\"",
            "\"moveToTarget\"",
            "\"setSelectionBefore\"",
            "\"setSelectionAfter\"",
            # Wishlist #12 Clone shipped 2026-07-01 (see
            # docs/BUNDLE_REST_SCOPE.md §7). Both variants land together.
            "\"insertCopyBefore\"",
            "\"insertCopyAfter\"",
            # Wishlist #13 Reverse shipped 2026-07-01 (see
            # docs/BUNDLE_REST_SCOPE.md §7). Multi-target action.
            "\"reverseTargets\"",
        )
        missing = [name for name in ACTIONS_MUST_HAVE if name not in src]
        assert not missing, (
            f"actions bundle missing shipped action names: {missing} — "
            "proseActionsStandalone.ts dispatch switch regressed. See "
            "docs/BUNDLE_REST_SCOPE.md §1."
        )
        # Dispatcher itself — a bundle without proseRunAction is unusable
        # regardless of which action names survived.
        assert (
            "globalThis.proseRunAction" in src
        ), "actions bundle missing proseRunAction export — bundle unusable"

        # Fail-informational: wishlist actions not yet shipped. Present
        # here as documentation; when one ships, MOVE it up into
        # ACTIONS_MUST_HAVE in the same PR that lands the action.
        # Mapping: docs/BUNDLE_REST_SCOPE.md §7 recommended-order.
        ACTIONS_PLANNED = (
            ("swap", "#3 Swap action"),
            ("pasteAtDestination", "#4 Paste at destination"),
            ("wrap", "#5 Wrap paired delimiter"),
        )
        for name, label in ACTIONS_PLANNED:
            state = "PRESENT" if f'"{name}"' in src else "ABSENT — planned"
            # DIM-print so this stays visible in the L2 block without
            # cluttering fail summaries. Never asserts.
            print(f"    {DIM}[L2.9 inventory] {name:22s} {state:22s} ({label}){RESET}")

    # L2.10 — Wishlist #12 Clone (insertCopyBefore / insertCopyAfter).
    # Exercise the JS bundle directly with bun and assert the emitted
    # edit plan is a single insert op with the correct text + position.
    # Document: "the air ball drum echo" (std buffer, space-joined).
    # Target: token 1 "air" at chars [4, 7).
    with test(
        "L2",
        "L2.10",
        "wishlist #12 — insertCopyAfter emits one insert op with ' air' at end of range",
    ):
        script = f"""
const code = require('fs').readFileSync('{ACTIONS_JS}', 'utf8');
eval(code);
const out = globalThis.proseRunAction(
  JSON.stringify('insertCopyAfter'),
  JSON.stringify({{contentRange:{{start:{{line:0,character:4}},end:{{line:0,character:7}}}},isReversed:false}}),
  JSON.stringify(null),
  JSON.stringify({{text:'the air ball drum echo',selectionAnchorChar:0,selectionActiveChar:0}}),
);
process.stdout.write(out);
"""
        tmp = pathlib.Path("/tmp/headless-verify-clone-after.js")
        tmp.write_text(script)
        proc = subprocess.run(
            ["bun", str(tmp)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert proc.returncode == 0, f"bun exit {proc.returncode}: {proc.stderr[:200]}"
        plan = json.loads(proc.stdout)
        assert "error" not in plan, f"unexpected error: {plan!r}"
        edits = plan.get("edits", [])
        assert len(edits) == 1, f"expected 1 edit op, got {len(edits)}: {edits!r}"
        op = edits[0]
        assert op["type"] == "insert", f"expected insert op, got {op['type']!r}"
        assert op["text"] == " air", f"expected ' air' insert, got {op['text']!r}"
        assert op["position"]["character"] == 7, (
            f"expected insert at char 7 (end of 'air'), got {op['position']!r}"
        )

    with test(
        "L2",
        "L2.11",
        "wishlist #12 — insertCopyBefore emits one insert op with 'air ' at start of range",
    ):
        script = f"""
const code = require('fs').readFileSync('{ACTIONS_JS}', 'utf8');
eval(code);
const out = globalThis.proseRunAction(
  JSON.stringify('insertCopyBefore'),
  JSON.stringify({{contentRange:{{start:{{line:0,character:4}},end:{{line:0,character:7}}}},isReversed:false}}),
  JSON.stringify(null),
  JSON.stringify({{text:'the air ball drum echo',selectionAnchorChar:0,selectionActiveChar:0}}),
);
process.stdout.write(out);
"""
        tmp = pathlib.Path("/tmp/headless-verify-clone-before.js")
        tmp.write_text(script)
        proc = subprocess.run(
            ["bun", str(tmp)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert proc.returncode == 0, f"bun exit {proc.returncode}: {proc.stderr[:200]}"
        plan = json.loads(proc.stdout)
        assert "error" not in plan, f"unexpected error: {plan!r}"
        edits = plan.get("edits", [])
        assert len(edits) == 1, f"expected 1 edit op, got {len(edits)}: {edits!r}"
        op = edits[0]
        assert op["type"] == "insert", f"expected insert op, got {op['type']!r}"
        assert op["text"] == "air ", f"expected 'air ' insert, got {op['text']!r}"
        assert op["position"]["character"] == 4, (
            f"expected insert at char 4 (start of 'air'), got {op['position']!r}"
        )

    # L2.12 — Wishlist #13 Reverse (reverseTargets). Multi-target action.
    # The JS bundle accepts an ARRAY of TargetObj in the source slot when
    # the action is reverseTargets — see the ABI note in
    # cursorless/packages/cursorless-engine/src/actions/proseActionsStandalone.ts.
    # Std buffer: "the air ball drum echo". Three target ranges pointing
    # at air/ball/drum should come back as three replace ops with texts
    # reversed → drum/ball/air.
    with test(
        "L2",
        "L2.12",
        "wishlist #13 — reverseTargets emits N replace ops with texts reversed",
    ):
        script = f"""
const code = require('fs').readFileSync('{ACTIONS_JS}', 'utf8');
eval(code);
const targets = [
  {{contentRange:{{start:{{line:0,character:4}}, end:{{line:0,character:7}}}}, isReversed:false}},
  {{contentRange:{{start:{{line:0,character:8}}, end:{{line:0,character:12}}}}, isReversed:false}},
  {{contentRange:{{start:{{line:0,character:13}}, end:{{line:0,character:17}}}}, isReversed:false}},
];
const out = globalThis.proseRunAction(
  JSON.stringify('reverseTargets'),
  JSON.stringify(targets),
  JSON.stringify(null),
  JSON.stringify({{text:'the air ball drum echo',selectionAnchorChar:0,selectionActiveChar:0}}),
);
process.stdout.write(out);
"""
        tmp = pathlib.Path("/tmp/headless-verify-reverse.js")
        tmp.write_text(script)
        proc = subprocess.run(
            ["bun", str(tmp)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert proc.returncode == 0, f"bun exit {proc.returncode}: {proc.stderr[:200]}"
        plan = json.loads(proc.stdout)
        assert "error" not in plan, f"unexpected error: {plan!r}"
        edits = plan.get("edits", [])
        assert len(edits) == 3, f"expected 3 replace ops, got {len(edits)}: {edits!r}"
        # Bundle sorts targets by document position before extracting texts,
        # so edits[0] targets the leftmost range with the rightmost text.
        expected = [
            ("replace", 4, 7, "drum"),
            ("replace", 8, 12, "ball"),
            ("replace", 13, 17, "air"),
        ]
        for edit, (etype, start, end, text) in zip(edits, expected):
            assert edit["type"] == etype, (
                f"expected {etype} op, got {edit['type']!r}"
            )
            assert edit["range"]["start"]["character"] == start, (
                f"expected start {start}, got {edit['range']!r}"
            )
            assert edit["range"]["end"]["character"] == end, (
                f"expected end {end}, got {edit['range']!r}"
            )
            assert edit["text"] == text, (
                f"expected replace text {text!r}, got {edit['text']!r}"
            )

