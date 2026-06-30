#!/usr/bin/env python3
"""Headless verification runner — see docs/HEADLESS_VERIFY_PLAN.md.

Walks every test in the plan, prints a [x] / [ ] FAIL checklist per layer,
exits 0 if all pass, non-zero if any fail.

Usage: python3 scripts/headless-verify.py
"""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import types
from contextlib import contextmanager

REPO = pathlib.Path(__file__).resolve().parent.parent
STATE_PY = REPO / "internal" / "state.py"
HAT_JS = REPO / "js" / "prose_allocate_hats.js"
TEST_DRIVER_PY = REPO / "ui" / "test_driver.py"

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"

results: list[tuple[str, str, bool, str]] = []  # (layer, id, passed, detail)


@contextmanager
def test(layer: str, tid: str, desc: str):
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


def _load_state_module():
    spec = importlib.util.spec_from_file_location("prose_overlay_state", STATE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# =============================================================================
# Layer 1 — pure Python
# =============================================================================

def _load_instance_module():
    """Load prose_overlay_instance.py — ProseOverlayState is dependency-free."""
    spec = importlib.util.spec_from_file_location(
        "prose_overlay_instance",
        REPO / "internal" / "instance.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_layer_1() -> None:
    print(f"\n=== Layer 1 — Pure Python ({DIM}prose_overlay_state.py{RESET}) ===")
    state = _load_state_module()
    ProseBuffer = state.ProseBuffer
    EditKind = state.EditKind
    compute = state.compute_hat_assignments

    with test("L1", "L1.1", "ProseBuffer instantiation"):
        b = ProseBuffer()
        assert b.get_tokens() == []
        assert b.rev == 0

    with test("L1", "L1.2", "add_text('testing testing one two three') → 5 tokens"):
        b = ProseBuffer()
        b.add_text("testing testing one two three")
        assert b.get_tokens() == ["testing", "testing", "one", "two", "three"], b.get_tokens()

    with test("L1", "L1.3", "undo restores prior state"):
        b = ProseBuffer()
        b.add_text("a b")
        b.add_text("c d")
        assert b.get_text() == "a b c d"
        assert b.undo() is True
        assert b.get_text() == "a b", b.get_text()

    with test("L1", "L1.4", "redo replays the undone step"):
        b = ProseBuffer()
        b.add_text("a b")
        b.add_text("c d")
        b.undo()
        assert b.redo() is True
        assert b.get_text() == "a b c d", b.get_text()

    with test("L1", "L1.5", "commit_start + 2× add_text + commit_end = ONE undo step"):
        b = ProseBuffer()
        b.add_text("a b")
        b.commit_start("test", EditKind.STRUCTURAL)
        b.add_text("c")
        b.add_text("d")
        b.commit_end()
        assert b.get_text() == "a b c d"
        assert b.undo() is True
        assert b.get_text() == "a b", f"bracket did not collapse to one step; got {b.get_text()!r}"

    with test("L1", "L1.6", "rev advances monotonically across mutations"):
        b = ProseBuffer()
        r0 = b.rev
        b.add_text("x")
        r1 = b.rev
        b.add_text("y")
        r2 = b.rev
        assert r0 < r1 < r2, f"rev sequence not strictly increasing: {r0}, {r1}, {r2}"

    with test("L1", "L1.7", "compute_hat_assignments produces hats for letter tokens"):
        r = compute(["foo", "bar"])
        assert 0 in r and 1 in r, f"missing hat assignments: {r}"
        # Each entry is (char_idx, letter, color)
        assert r[0][1].isalpha() and r[1][1].isalpha()

    with test("L1", "L1.8", "compute_hat_assignments produces hat for digit token (regression aa2909e)"):
        r = compute(["123"])
        assert 0 in r, f"no hat for digit token: {r}"
        assert r[0][1] == "1", f"expected hat letter '1' for '123', got {r[0]!r}"

    with test("L1", "L1.9", "compute_hat_assignments produces hat for pure-punct token"):
        r = compute(["!"])
        assert 0 in r, f"no hat for punct token: {r}"
        assert r[0][1] == "!", f"expected hat letter '!' for '!', got {r[0]!r}"

    with test("L1", "L1.10", "end-to-end user repro: ['testing','testing','123']"):
        r = compute(["testing", "testing", "123"])
        assert {0, 1, 2}.issubset(r.keys()), f"missing hats; got keys {sorted(r.keys())}"
        # User's reported state had: testing→gray-e, testing→gray-t, 123→NO HAT
        # After fix: 123 should have a hat.
        assert r[2][1] in {"1"}, f"expected '1' hat letter for '123', got {r[2]!r}"

    with test("L1", "L1.11", "letter-extend pattern: 'air' then 'bat cap' → one token 'abc'"):
        # Mirrors what prose_overlay_add_letters does at the buffer level:
        # first utterance appends "a"; second utterance (with prior also
        # letters + no cursor + non-empty buffer) extends last token via
        # commit_start/set_tokens_raw/commit_end.
        b = ProseBuffer()
        b.add_text("a")                                # first letter utterance
        # Simulate the extend path
        tokens = b.get_tokens()
        new_tokens = tokens[:-1] + [tokens[-1] + "bc"]
        b.commit_start("extend_letters", EditKind.STRUCTURAL)
        b.set_tokens_raw(new_tokens)
        b.commit_end()
        assert b.get_tokens() == ["abc"], f"expected ['abc'], got {b.get_tokens()!r}"

    with test("L1", "L1.12", "letter-extend then undo restores prior single-letter token"):
        b = ProseBuffer()
        b.add_text("a")
        b.commit_start("extend_letters", EditKind.STRUCTURAL)
        b.set_tokens_raw(["abc"])
        b.commit_end()
        assert b.get_tokens() == ["abc"]
        assert b.undo() is True
        assert b.get_tokens() == ["a"], f"undo should restore single-letter token; got {b.get_tokens()!r}"

    with test("L1", "L1.12b", "char-extend full repro: 'bubble','_','t','o','p' → 'bubble_top'"):
        # Mirrors what prose_overlay_add_chars does at the buffer level for
        # the user's exact example. Word 'bubble' arrives via add_text;
        # subsequent chars ('_', 't', 'o', 'p') each extend the last token.
        b = ProseBuffer()
        b.add_text("bubble")
        for ch in ["_", "t", "o", "p"]:
            tokens = b.get_tokens()
            new_tokens = tokens[:-1] + [tokens[-1] + ch]
            b.commit_start("extend_chars", EditKind.STRUCTURAL)
            b.set_tokens_raw(new_tokens)
            b.commit_end()
        assert b.get_tokens() == ["bubble_top"], (
            f"expected one token 'bubble_top'; got {b.get_tokens()!r}"
        )

    inst_mod = _load_instance_module()
    ProseOverlayState = inst_mod.ProseOverlayState

    with test("L1", "L1.13", "ProseOverlayState.reset() wipes all data fields to defaults"):
        inst = ProseOverlayState()
        inst.buffer = ProseBuffer()
        inst.buffer.add_text("contaminated state")
        inst.cursor = 5
        inst.change_mode = True
        inst.target_window_title = "stale-window"
        inst.target_recall_name = "stale-recall"
        inst.help_visible = True
        inst.help_page = 7
        inst.auto_dictation = True
        inst.hat_js_fallback = True
        inst.hat_assignments = {0: (0, "c", "gray")}
        inst.hat_to_token = {("c", "gray"): 0}
        inst.shape_assignments = {0: "wing"}  # Slice 2 — must also wipe.
        inst.flash_state = {"indices": [1], "color": "ff0000"}
        inst.history = ["old", "stuff"]
        inst.history_page = 3
        inst._last_input_source = "letters"
        inst.reset()
        assert inst.buffer.get_tokens() == [], "buffer not cleared"
        assert inst.cursor is None
        assert inst.change_mode is False
        assert inst.target_window_title == ""
        assert inst.target_recall_name is None
        assert inst.help_visible is False
        assert inst.help_page == 0
        assert inst.auto_dictation is False
        assert inst.hat_js_fallback is False
        assert inst.hat_assignments == {}
        assert inst.hat_to_token == {}
        assert inst.shape_assignments == {}, (
            f"shape_assignments not cleared by reset(): {inst.shape_assignments!r}"
        )
        assert inst.flash_state == {}
        assert inst.history == []
        assert inst.history_page == 0
        assert inst._last_input_source == "init"

    with test("L1", "L1.14", "reset() preserves object identity of buffer/canvas/etc."):
        # Object refs created at module init should NOT be reassigned.
        inst = ProseOverlayState()
        inst.buffer = ProseBuffer()
        b_id = id(inst.buffer)
        # canvas and viewport are typically created by prose_overlay.py;
        # reset() should leave None alone and not reassign existing refs.
        inst.reset()
        assert id(inst.buffer) == b_id, "buffer object identity should be preserved"

    homophones_spec = importlib.util.spec_from_file_location(
        "prose_overlay_homophones",
        REPO / "internal" / "homophones.py",
    )
    homophones = importlib.util.module_from_spec(homophones_spec)
    homophones_spec.loader.exec_module(homophones)

    with test("L1", "L1.15", "homophone hint is ON by default (slice A KEEP verdict)"):
        assert homophones.hint_enabled() is True, (
            "default should be ON after 2026-06-30 keep verdict; got "
            f"{homophones.hint_enabled()!r}"
        )

    shapes_spec = importlib.util.spec_from_file_location(
        "prose_overlay_shapes",
        REPO / "shim" / "shapes.py",
    )
    try:
        shapes_mod = importlib.util.module_from_spec(shapes_spec)
        shapes_spec.loader.exec_module(shapes_mod)
    except Exception:
        shapes_mod = None

    with test("L1", "L1.16b", "shapes_enabled() is True by default (keep verdict)"):
        if shapes_mod is None:
            raise AssertionError("prose_overlay_shapes failed to import")
        assert shapes_mod.shapes_enabled() is True, (
            f"default should be ON after 2026-06-30 keep verdict; got "
            f"{shapes_mod.shapes_enabled()!r}"
        )

    with test("L1", "L1.16", "homophone flag set is populated from CSV (non-empty)"):
        # The CSV path is hardcoded to trillium_talon's homophones.csv; if the
        # path doesn't exist on this machine the load function returns an empty
        # set with a printed warning. On Trillium's machine the file exists.
        assert isinstance(homophones._FLAGGED, frozenset)
        # Spot-check a canonical homophone pair: "their"/"there"/"they're"
        # should all flag (case-insensitive, after _STRIP).
        assert homophones.is_flagged("their"), "'their' should be flagged"
        assert homophones.is_flagged("there"), "'there' should be flagged"

    with test("L1", "L1.17", "snake_case formatter output lands as ONE buffer token"):
        # Mirrors the shim chain: insert_formatted ("the quick brown fox",
        # "SNAKE_CASE") -> formatted_text -> "the_quick_brown_fox" ->
        # add_text("the_quick_brown_fox") -> buffer splits on whitespace -> 1 token.
        # We don't need the community formatter here — just verify the BUFFER
        # contract: a snake_case string (no whitespace) becomes one token.
        b = ProseBuffer()
        b.add_text("the_quick_brown_fox")
        assert b.get_tokens() == ["the_quick_brown_fox"], (
            f"snake_case output should be ONE token; got {b.get_tokens()!r}"
        )

    with test("L1", "L1.18", "camelCase formatter output lands as ONE buffer token"):
        b = ProseBuffer()
        b.add_text("theQuickBrownFox")
        assert b.get_tokens() == ["theQuickBrownFox"], b.get_tokens()

    with test("L1", "L1.19", "title-case formatter output stays multi-token (has spaces)"):
        # TITLE_CASE preserves spaces ("The Quick Brown Fox"), so add_text
        # naturally splits — 4 tokens, each capitalized. Documenting the
        # expected split behavior so future regressions are caught.
        b = ProseBuffer()
        b.add_text("The Quick Brown Fox")
        assert b.get_tokens() == ["The", "Quick", "Brown", "Fox"], b.get_tokens()

    # -----------------------------------------------------------------------
    # Homophone shapes (Slice 1 — docs/HOMOPHONE_SHAPES_PLAN.md)
    # The module imports cleanly without Talon (Skia is lazy-loaded inside
    # _get_shape_path_cache), so the static vocabulary + asset existence
    # checks are headless-friendly. The actual paint (draw_hat_shape) is
    # verify-in-Talon only because Skia rendering needs the live process.
    # -----------------------------------------------------------------------
    shapes_spec = importlib.util.spec_from_file_location(
        "prose_overlay_shapes",
        REPO / "shim" / "shapes.py",
    )
    shapes_mod = importlib.util.module_from_spec(shapes_spec)
    shapes_spec.loader.exec_module(shapes_mod)

    with test("L1", "L1.20", "HAT_SHAPES is a tuple of exactly 10 strings"):
        assert isinstance(shapes_mod.HAT_SHAPES, tuple), type(shapes_mod.HAT_SHAPES)
        assert len(shapes_mod.HAT_SHAPES) == 10, len(shapes_mod.HAT_SHAPES)
        assert all(isinstance(s, str) for s in shapes_mod.HAT_SHAPES), shapes_mod.HAT_SHAPES
        # 'dot' must NOT be in the pool — the existing letter-hat dot owns
        # that slot, per plan §3 ("dot is excluded — that's the default
        # letter-hat shape, not a homophone shape").
        assert "dot" not in shapes_mod.HAT_SHAPES, "'dot' should NOT be in HAT_SHAPES"

    with test("L1", "L1.21", "shape_pool() returns the same tuple as HAT_SHAPES"):
        assert shapes_mod.shape_pool() == shapes_mod.HAT_SHAPES, (
            f"shape_pool diverged from HAT_SHAPES: {shapes_mod.shape_pool()!r} vs "
            f"{shapes_mod.HAT_SHAPES!r}"
        )

    with test("L1", "L1.22", "All 10 SVG files for HAT_SHAPES exist in svg/"):
        # The 'cross' spoken form maps to filename 'crosshairs.svg' per upstream
        # HAT_NAMES; the loader's _HAT_NAMES dict carries that mapping. We check
        # by inverting _HAT_NAMES (spoken → stem) and confirming each stem has
        # a corresponding .svg file on disk.
        spoken_to_stem = {v: k for k, v in shapes_mod._HAT_NAMES.items()}
        svg_dir = REPO / "svg"
        assert svg_dir.is_dir(), f"svg/ dir missing at {svg_dir}"
        for spoken in shapes_mod.HAT_SHAPES:
            stem = spoken_to_stem.get(spoken, spoken)
            f = svg_dir / f"{stem}.svg"
            assert f.is_file(), f"missing SVG for shape {spoken!r}: expected {f}"

    with test("L1", "L1.23", "_parse_svg_entries returns 10 homophone-shape entries (+ 1 default)"):
        # Each entry is (stem, spoken_name, d, fill_rule). The parse picks up
        # all 11 SVGs including 'default'; the homophone subset is the 10
        # spoken names in HAT_SHAPES.
        entries = shapes_mod._svg_entries  # populated at import
        assert len(entries) >= 10, f"expected ≥10 SVG entries, got {len(entries)}"
        spokens = {e[1] for e in entries}
        for spoken in shapes_mod.HAT_SHAPES:
            assert spoken in spokens, f"shape {spoken!r} not in parsed entries {sorted(spokens)}"
        # And every entry must have non-empty path data — bad SVG would be
        # an import-time silent skip (logged) but still pass length check.
        for stem, spoken, d, fill_rule in entries:
            assert d, f"empty path data for {spoken} ({stem}.svg)"

    # -----------------------------------------------------------------------
    # Homophone shape allocator (Slice 2 — docs/HOMOPHONE_SHAPES_PLAN.md §3)
    # The allocator is a pure function with no Talon imports — fully
    # headless-friendly. These tests cover the four contractual behaviors:
    # basic assignment, memoization stability, prior-assignment carryover,
    # and pool-overflow omission.
    # -----------------------------------------------------------------------

    with test("L1", "L1.24", "compute_shape_assignments: single flagged token gets one shape from HAT_SHAPES"):
        shapes_mod._clear_shape_cache()
        r = shapes_mod.compute_shape_assignments(["there"], frozenset({0}), rev=1)
        assert 0 in r, f"expected idx 0 in result; got {r}"
        assert r[0] in shapes_mod.HAT_SHAPES, (
            f"shape {r[0]!r} not in HAT_SHAPES {shapes_mod.HAT_SHAPES}"
        )

    with test("L1", "L1.25", "compute_shape_assignments: memoization returns same dict reference"):
        shapes_mod._clear_shape_cache()
        r1 = shapes_mod.compute_shape_assignments(
            ["there", "their"], frozenset({0, 1}), rev=1,
        )
        r2 = shapes_mod.compute_shape_assignments(
            ["there", "their"], frozenset({0, 1}), rev=1,
        )
        assert r1 == r2, f"identical inputs should equal: {r1} vs {r2}"
        # Memoization: identical inputs must return the SAME dict reference
        # (not just equal). Lets the draw module short-circuit on identity.
        assert r1 is r2, (
            "memoized result should be the same object reference; "
            f"got two different dicts: id={id(r1)} vs id={id(r2)}"
        )

    with test("L1", "L1.26", "compute_shape_assignments: prior assignment survives a new flag"):
        shapes_mod._clear_shape_cache()
        # idx 0 was assigned 'wing' on the previous allocator run. When idx
        # 1 joins the flagged set, idx 0 should KEEP 'wing' and idx 1 should
        # be allocated from the pool of unused shapes (i.e. not 'wing').
        prior = {0: "wing"}
        r = shapes_mod.compute_shape_assignments(
            ["there", "their"], frozenset({0, 1}), rev=2, prior=prior,
        )
        assert r[0] == "wing", (
            f"prior shape 'wing' should survive on idx 0; got {r!r}"
        )
        assert r[1] != "wing", (
            f"new flagged idx should not duplicate a used shape; got {r!r}"
        )
        assert r[1] in shapes_mod.HAT_SHAPES, (
            f"new shape {r[1]!r} not in HAT_SHAPES"
        )

    with test("L1", "L1.27", "compute_shape_assignments: 11 flagged tokens overflows — 11th omitted"):
        shapes_mod._clear_shape_cache()
        tokens = ["there"] * 11
        flagged = frozenset(range(11))
        r = shapes_mod.compute_shape_assignments(tokens, flagged, rev=1)
        # Pool has exactly 10 shapes; 11 flagged tokens → exactly 10 entries.
        assert len(r) == 10, (
            f"expected 10 shape assignments (pool exhausted at 10); got "
            f"{len(r)}: {r}"
        )
        # The first 10 sorted indices get the shapes; idx 10 (the 11th)
        # falls into the overflow tail and is omitted per §4.8.
        for idx in range(10):
            assert idx in r, f"idx {idx} should be in result; got {sorted(r)}"
        assert 10 not in r, (
            f"11th idx (10) should be omitted on pool exhaustion; got {r}"
        )

    with test("L1", "L1.28", "shape_char_position: 'there' letter on idx 1 → shape on idx 2"):
        # Per user requirement: t[h]{e}re — letter-hat on 'h' (idx 1),
        # shape on 'e' (idx 2). Same token, both hats, no overlap.
        assert shapes_mod.shape_char_position(letter_char_idx=1, token_len=5) == 2

    with test("L1", "L1.29", "shape_char_position: letter on last char wraps to 0"):
        assert shapes_mod.shape_char_position(letter_char_idx=4, token_len=5) == 0

    with test("L1", "L1.30", "shape_char_position: single-char token → 0 (collision unavoidable)"):
        assert shapes_mod.shape_char_position(letter_char_idx=0, token_len=1) == 0

    with test("L1", "L1.31", "shape_char_position: no letter hat (-1) → 0"):
        assert shapes_mod.shape_char_position(letter_char_idx=-1, token_len=5) == 0


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


# =============================================================================
# Layer 3 — Talon-stubbed (prose_overlay_test_driver.py)
# =============================================================================

class _StubAction:
    """Records (name, args, kwargs) for every call. user.* attr access lazily creates these."""
    def __init__(self, log: list, name: str):
        self._log = log
        self._name = name
    def __call__(self, *args, **kwargs):
        self._log.append((self._name, args, kwargs))


class _StubActionsUser:
    def __init__(self, log: list):
        self._log = log
    def __getattr__(self, name: str):
        return _StubAction(self._log, name)


class _StubActions:
    def __init__(self, log: list):
        self.user = _StubActionsUser(log)


class _StubModule:
    def action_class(self, cls):
        return cls
    def setting(self, *a, **k): pass
    def tag(self, *a, **k): pass
    def capture(self, *a, **k):
        def deco(fn): return fn
        return deco
    def list(self, *a, **k): pass


def _install_talon_stubs(actions_log: list, cron_log: list):
    """Install minimal talon stubs in sys.modules for test-driver import."""
    talon = types.ModuleType("talon")
    talon.Module = lambda: _StubModule()
    talon.actions = _StubActions(actions_log)
    cron_mod = types.SimpleNamespace(
        interval=lambda when, fn: cron_log.append(("interval", when, fn)) or "JOB-ID",
        after=lambda when, fn: cron_log.append(("after", when, fn)) or "JOB-ID",
        cancel=lambda jid: cron_log.append(("cancel", jid)),
    )
    talon.cron = cron_mod
    sys.modules["talon"] = talon
    sys.modules["talon.cron"] = cron_mod


def _import_test_driver_fresh() -> types.ModuleType:
    """Re-import with a fresh stub registry."""
    sys.modules.pop("prose_overlay_test_driver", None)
    spec = importlib.util.spec_from_file_location("prose_overlay_test_driver", TEST_DRIVER_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_layer_3() -> None:
    print(f"\n=== Layer 3 — Stubbed Talon ({DIM}prose_overlay_test_driver.py{RESET}) ===")

    flag_path = pathlib.Path.home() / ".talon" / "prose_overlay_test_enabled"
    if flag_path.exists():
        flag_path.unlink()

    # Ensure env var is OFF so import doesn't auto-activate
    os.environ.pop("PROSE_OVERLAY_TEST", None)

    actions_log: list = []
    cron_log: list = []
    _install_talon_stubs(actions_log, cron_log)

    with test("L3", "L3.1", "module imports under stubs"):
        td = _import_test_driver_fresh()
        assert hasattr(td, "_dispatch"), "module missing _dispatch"

    td = _import_test_driver_fresh()

    with test("L3", "L3.2", "_dispatch add → prose_overlay_add_text"):
        actions_log.clear()
        td._dispatch({"cmd": "add", "text": "hello world"})
        assert actions_log == [("prose_overlay_add_text", ("hello world",), {})], actions_log

    with test("L3", "L3.3", "_dispatch show → prose_overlay_show"):
        actions_log.clear()
        td._dispatch({"cmd": "show"})
        assert actions_log == [("prose_overlay_show", (), {})], actions_log

    with test("L3", "L3.4", "_dispatch dump → prose_overlay_dump_state"):
        actions_log.clear()
        td._dispatch({"cmd": "dump"})
        assert actions_log == [("prose_overlay_dump_state", (), {})], actions_log

    with test("L3", "L3.5", "_dispatch delete_hat with letter+color passes both"):
        actions_log.clear()
        td._dispatch({"cmd": "delete_hat", "letter": "a", "color": "blue"})
        assert actions_log == [("prose_overlay_delete_hat", ("a", "blue"), {})], actions_log

    with test("L3", "L3.5b", "_dispatch add_letters → prose_overlay_add_letters"):
        actions_log.clear()
        td._dispatch({"cmd": "add_letters", "letters": "abc"})
        assert actions_log == [("prose_overlay_add_letters", ("abc",), {})], actions_log

    with test("L3", "L3.5b2", "_dispatch add_chars → prose_overlay_add_chars"):
        actions_log.clear()
        td._dispatch({"cmd": "add_chars", "chars": "_"})
        assert actions_log == [("prose_overlay_add_chars", ("_",), {})], actions_log

    with test("L3", "L3.5c", "_dispatch reset → prose_overlay_reset"):
        actions_log.clear()
        td._dispatch({"cmd": "reset"})
        assert actions_log == [("prose_overlay_reset", (), {})], actions_log

    with test("L3", "L3.5d", "_dispatch insert_format_code → prose_overlay_insert_format_code"):
        actions_log.clear()
        td._dispatch({"cmd": "insert_format_code", "strings": ["the_quick_brown_fox"]})
        assert actions_log == [
            ("prose_overlay_insert_format_code", (["the_quick_brown_fox"],), {}),
        ], actions_log

    with test("L3", "L3.5e", "_dispatch clear_buffer → prose_overlay_clear_buffer"):
        actions_log.clear()
        td._dispatch({"cmd": "clear_buffer"})
        assert actions_log == [("prose_overlay_clear_buffer", (), {})], actions_log

    with test("L3", "L3.6", "_dispatch bogus cmd does not raise"):
        actions_log.clear()
        td._dispatch({"cmd": "definitely-not-a-real-cmd"})
        assert actions_log == [], f"bogus cmd should not call any action: {actions_log}"

    with test("L3", "L3.7", "_tick handles malformed JSON line without crashing"):
        # Write a malformed line + a valid line to the queue
        queue = pathlib.Path.home() / ".talon" / "prose_overlay_test_queue.jsonl"
        queue.parent.mkdir(parents=True, exist_ok=True)
        queue.write_text('not-json\n{"cmd":"show"}\n')
        td._pos = 0
        actions_log.clear()
        td._tick()
        assert actions_log == [("prose_overlay_show", (), {})], \
            f"malformed line should be skipped, valid line dispatched: {actions_log}"

    with test("L3", "L3.8", "_tick advances _pos so re-call dispatches nothing new"):
        queue = pathlib.Path.home() / ".talon" / "prose_overlay_test_queue.jsonl"
        queue.write_text('{"cmd":"show"}\n')
        td._pos = 0
        actions_log.clear()
        td._tick()
        assert len(actions_log) == 1
        actions_log.clear()
        td._tick()
        assert actions_log == [], f"second _tick should be no-op; got {actions_log}"

    with test("L3", "L3.9", "prose_overlay_test_set(1) creates flag file + starts cron"):
        if flag_path.exists():
            flag_path.unlink()
        # Find the action class on the module's mod.action_class — the decorator
        # under stubs just returns the class, so we can call its method directly.
        Actions = next(
            obj for name, obj in vars(td).items()
            if isinstance(obj, type) and "prose_overlay_test_set" in vars(obj)
        )
        cron_log.clear()
        Actions.prose_overlay_test_set(1)
        assert flag_path.exists(), "flag file should be created"
        assert any(c[0] == "interval" for c in cron_log), f"cron.interval should be called: {cron_log}"

    with test("L3", "L3.10", "prose_overlay_test_set(0) removes flag file + cancels cron"):
        # State carries over from L3.9 — flag exists, cron is registered
        Actions = next(
            obj for name, obj in vars(td).items()
            if isinstance(obj, type) and "prose_overlay_test_set" in vars(obj)
        )
        cron_log.clear()
        Actions.prose_overlay_test_set(0)
        assert not flag_path.exists(), "flag file should be removed"
        assert any(c[0] == "cancel" for c in cron_log), f"cron.cancel should be called: {cron_log}"


# =============================================================================
# Main
# =============================================================================

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


def main() -> int:
    print("Headless verify — see docs/HEADLESS_VERIFY_PLAN.md\n")
    run_layer_1()
    run_layer_2()
    run_layer_3()
    run_layer_4()

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
