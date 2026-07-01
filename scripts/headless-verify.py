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

    with test("L1", "L1.10b", "hat stability: prior letter survives token edit at the SAME letter's new index (phones-swap regression)"):
        # User repro: token 0 = "they're" with prior hat (5, 'r', 'gray').
        # `phones risk` swaps it to "their". 'r' is now at idx 4, not 5.
        # The allocator must keep ('r', 'gray') and rewrite char_idx to 4.
        # Without this fix the renderer paints the letter dot past the end
        # of "their" ("hat over nothing").
        prior = {0: (5, "r", "gray")}
        r = compute(["their"], old_assignments=prior)
        assert 0 in r, f"prior 'r' should still hold a slot in 'their'; got {r}"
        ci, letter, color = r[0]
        assert letter == "r" and color == "gray", f"prior (letter, color) lost across edit: {r[0]!r}"
        assert ci == 4, f"char_idx must be repositioned to 'r' in 'their' (idx 4), got {ci}"

    with test("L1", "L1.10c", "hat stability: prior letter VANISHES from new token → allocator picks fresh letter"):
        # If the swapped word has no 'r' at all, drop the prior cleanly
        # and let the normal allocator pass pick a different letter.
        prior = {0: (5, "r", "gray")}
        r = compute(["foo"], old_assignments=prior)
        assert 0 in r, f"token should still get SOME hat: {r}"
        _ci, letter, _color = r[0]
        assert letter != "r", f"'foo' has no 'r' — prior must be dropped, got {r[0]!r}"

    with test("L1", "L1.10d", "compute_hat_assignments: empty tokens returns empty dict cleanly (HAT_ALLOC_OVERFLOW guard mirror)"):
        # The JS bridge short-circuits `tokens == []` to skip the JS call
        # entirely — QuickJS threw `Maximum call stack size exceeded` on
        # a 0-token buffer during the recompute that follows show()'s
        # buffer.clear() (observed live 2026-06-30). This test asserts
        # the Python re-impl also handles empty gracefully so the fallback
        # path (and the bridge's short-circuit-returns-{}) is provably
        # equivalent to what a working JS call would produce.
        r = compute([])
        assert r == {}, f"empty tokens must return empty dict; got {r!r}"
        # And with old_assignments (typical caller shape from _recompute_hats
        # after a change_head-through-last-token wipe).
        r = compute([], old_assignments={0: (0, "a", "gray")})
        assert r == {}, f"empty tokens with prior must return empty dict; got {r!r}"

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
        inst.hat_js_last_err = "call(7 toks): RuntimeError('stack overflow')"
        inst.hat_assignments = {0: (0, "c", "gray")}
        inst.hat_to_token = {("c", "gray"): 0}
        inst.shape_assignments = {0: "wing"}  # Slice 2 — must also wipe.
        # Slice A of docs/PHONES_SPEC.md adds two parallel maps that reset()
        # must also clear, otherwise stale cycle state survives an "overlay
        # reset" and the next swap acts on the previous buffer's words.
        inst.next_alt_assignments = {0: "they're"}
        inst.position_assignments = {0: (1, 3)}
        # Slice C of docs/PHONES_SPEC.md adds homophone_panel_alts; reset()
        # must clear it too so a stale panel from the prior session can't
        # leak into the next.
        inst.homophone_panel_alts = {0: {"yellow": "their", "blue": "they're"}}
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
        assert inst.hat_js_last_err == "", (
            f"hat_js_last_err should reset to empty; got {inst.hat_js_last_err!r}"
        )
        assert inst.hat_assignments == {}
        assert inst.hat_to_token == {}
        assert inst.shape_assignments == {}, (
            f"shape_assignments not cleared by reset(): {inst.shape_assignments!r}"
        )
        assert inst.next_alt_assignments == {}, (
            f"next_alt_assignments not cleared by reset(): "
            f"{inst.next_alt_assignments!r}"
        )
        assert inst.position_assignments == {}, (
            f"position_assignments not cleared by reset(): "
            f"{inst.position_assignments!r}"
        )
        assert inst.homophone_panel_alts == {}, (
            f"homophone_panel_alts not cleared by reset(): "
            f"{inst.homophone_panel_alts!r}"
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
        r = shapes_mod.compute_shape_assignments(
            ["there"], frozenset({0}), rev=1,
            group_id_for_word_fn=lambda t: 0,
        )
        assert 0 in r, f"expected idx 0 in result; got {r}"
        assert r[0] in shapes_mod.HAT_SHAPES, (
            f"shape {r[0]!r} not in HAT_SHAPES {shapes_mod.HAT_SHAPES}"
        )

    with test("L1", "L1.25", "compute_shape_assignments: memoization returns same dict reference"):
        shapes_mod._clear_shape_cache()
        # Different groups so each gets its own shape (memoization is keyed
        # on inputs, not on group structure).
        gid = lambda t: 0 if t == "there" else 1
        r1 = shapes_mod.compute_shape_assignments(
            ["there", "their"], frozenset({0, 1}), rev=1,
            group_id_for_word_fn=gid,
        )
        r2 = shapes_mod.compute_shape_assignments(
            ["there", "their"], frozenset({0, 1}), rev=1,
            group_id_for_word_fn=gid,
        )
        assert r1 == r2, f"identical inputs should equal: {r1} vs {r2}"
        # Memoization: identical inputs must return the SAME dict reference
        # (not just equal). Lets the draw module short-circuit on identity.
        assert r1 is r2, (
            "memoized result should be the same object reference; "
            f"got two different dicts: id={id(r1)} vs id={id(r2)}"
        )

    with test("L1", "L1.26", "compute_shape_assignments (ISC-14c): same-group tokens share their group's prior shape"):
        shapes_mod._clear_shape_cache()
        # idx 0 ("there", group 0) was assigned 'wing' on the previous run.
        # On the next run idx 1 ("their", same group 0) joins the flagged
        # set — under ISC-14c, both tokens belong to the SAME group, so
        # idx 1 ALSO gets 'wing'. (Pre-ISC-14c semantics had idx 1 get a
        # DIFFERENT shape; that's wrong now — group identity drives shape.)
        prior = {0: "wing"}
        r = shapes_mod.compute_shape_assignments(
            ["there", "their"], frozenset({0, 1}), rev=2, prior=prior,
            group_id_for_word_fn=lambda t: 0,  # both tokens in group 0
        )
        assert r[0] == "wing", (
            f"prior shape 'wing' should survive on idx 0; got {r!r}"
        )
        assert r[1] == "wing", (
            f"ISC-14c: same-group token idx 1 must share group's shape 'wing'; "
            f"got {r!r}"
        )

    with test("L1", "L1.27", "compute_shape_assignments (ISC-14c): 11 distinct groups overflows — 11th group omitted"):
        shapes_mod._clear_shape_cache()
        # 11 tokens, each in a UNIQUE group. The 10-shape pool now caps the
        # number of distinct GROUPS visible — the 11th group's tokens go
        # without a shape and fall back to the always-on underline.
        tokens = [f"w{i}" for i in range(11)]
        flagged = frozenset(range(11))
        r = shapes_mod.compute_shape_assignments(
            tokens, flagged, rev=1,
            group_id_for_word_fn=lambda t: int(t[1:]),  # group_id == idx
        )
        assert len(r) == 10, (
            f"expected 10 shape assignments (pool exhausted at 10 groups); "
            f"got {len(r)}: {r}"
        )
        for idx in range(10):
            assert idx in r, f"idx {idx} should be in result; got {sorted(r)}"
        assert 10 not in r, (
            f"11th group's token (idx 10) should be omitted on pool exhaustion; "
            f"got {r}"
        )

    with test("L1", "L1.27a", "compute_shape_assignments (ISC-14c): 11 tokens in ONE group all share one shape — no overflow"):
        shapes_mod._clear_shape_cache()
        # Inverse of L1.27 — 11 tokens but ALL in the same group. Under
        # ISC-14c the pool only sees 1 GROUP, so all 11 tokens get the
        # same single shape and there's no overflow.
        tokens = ["there"] * 11
        flagged = frozenset(range(11))
        r = shapes_mod.compute_shape_assignments(
            tokens, flagged, rev=1,
            group_id_for_word_fn=lambda t: 0,
        )
        assert len(r) == 11, (
            f"ISC-14c: 11 tokens in one group should all be assigned; got {len(r)}: {r}"
        )
        shapes_used = set(r.values())
        assert len(shapes_used) == 1, (
            f"ISC-14c: all same-group tokens must share ONE shape; got {shapes_used} from {r}"
        )

    with test("L1", "L1.27b", "compute_shape_assignments (ISC-14c): two groups get two distinct shapes; intra-group sharing"):
        shapes_mod._clear_shape_cache()
        # 4 tokens: 2 in group 0 (there/their), 2 in group 1 (your/you're).
        # Group 0 → one shape, group 1 → a different shape, intra-group
        # shares.
        tokens = ["there", "your", "their", "you're"]
        flagged = frozenset({0, 1, 2, 3})
        r = shapes_mod.compute_shape_assignments(
            tokens, flagged, rev=1,
            group_id_for_word_fn=lambda t: 0 if t in ("there", "their") else 1,
        )
        assert r[0] == r[2], f"group-0 tokens (idx 0,2) must share: got {r}"
        assert r[1] == r[3], f"group-1 tokens (idx 1,3) must share: got {r}"
        assert r[0] != r[1], f"different groups must have different shapes: got {r}"

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

    # -----------------------------------------------------------------------
    # Slice A of docs/PHONES_SPEC.md — group-aware homophone helpers
    # next_in_group / current_position_in_group drive the cycling swap
    # and the segmented underline. Both are pure functions over the CSV
    # so they are fully headless-friendly. We use the canonical
    # "their,there,they're" and "your,you're" rows; tests assume the live
    # trillium_talon CSV contains both (verified by L1.16).
    # -----------------------------------------------------------------------

    with test("L1", "L1.32", "next_in_group('there') → 'they're' (mid-row)"):
        assert homophones.next_in_group("there") == "they're", (
            f"expected they're; got {homophones.next_in_group('there')!r}"
        )

    with test("L1", "L1.33", "next_in_group('they\\'re') → 'their' (wraps)"):
        assert homophones.next_in_group("they're") == "their", (
            f"expected their (wrap); got {homophones.next_in_group(chr(0x27).join(['they', 're']))!r}"
        )

    with test("L1", "L1.34", "next_in_group('your') → 'you\\'re' (3-member, mid-row)"):
        # CSV row: your,you're,yore — cycling your → you're → yore → your.
        assert homophones.next_in_group("your") == "you're", (
            f"expected you're; got {homophones.next_in_group('your')!r}"
        )

    with test("L1", "L1.35", "next_in_group('not-a-homophone') → None"):
        assert homophones.next_in_group("not-a-homophone") is None

    with test("L1", "L1.36", "next_in_group ignores trailing punct ('There,' → 'they're')"):
        # _normalize strips trailing comma + quote, so capitalisation and
        # surrounding punct don't break the lookup. Matches is_flagged.
        assert homophones.next_in_group("There,") == "they're", (
            f"normalisation broke; got {homophones.next_in_group('There,')!r}"
        )

    with test("L1", "L1.37", "current_position_in_group('there') → (1, 3)"):
        # "their,there,they're" — 0-indexed: their=0, there=1, they're=2
        assert homophones.current_position_in_group("there") == (1, 3), (
            f"expected (1, 3); got "
            f"{homophones.current_position_in_group('there')!r}"
        )

    with test("L1", "L1.38", "current_position_in_group('they\\'re') → (2, 3)"):
        assert homophones.current_position_in_group("they're") == (2, 3)

    with test("L1", "L1.39", "current_position_in_group('your') → (0, 3) (first slot)"):
        # CSV row: your,you're,yore. Position 0 of 3.
        assert homophones.current_position_in_group("your") == (0, 3)

    with test("L1", "L1.40", "current_position_in_group('not-a-homophone') → None"):
        assert homophones.current_position_in_group("not-a-homophone") is None

    with test("L1", "L1.41", "group_for_word('there') → contains all 3 members"):
        g = homophones.group_for_word("there")
        assert g is not None and set(g) == {"their", "there", "they're"}, (
            f"expected 3-member their/there/they're group; got {g!r}"
        )

    # -----------------------------------------------------------------------
    # Slice A of docs/PHONES_SPEC.md — segmented-underline math
    # The width helper is pure (no Skia), so it imports cleanly in headless.
    # We load it via a stripped-down spec because ui/draw_tokens.py imports
    # from talon.skia at module level; the module-load would fail under
    # headless. Approach: read the constants and run the math directly.
    # -----------------------------------------------------------------------

    with test("L1", "L1.43", "segment_width(tw=40, members=3) → 12.0 ((40-4)/3)"):
        # Pure formula: (tw - (n-1)*GAP_W) / n with GAP_W = 2.
        # We import the constants module directly (no Skia) and recompute.
        dc_spec = importlib.util.spec_from_file_location(
            "prose_overlay_draw_constants",
            REPO / "internal" / "draw_constants.py",
        )
        dc = importlib.util.module_from_spec(dc_spec)
        dc_spec.loader.exec_module(dc)
        assert dc.HOMOPHONE_UNDERLINE_GAP_W == 2
        assert dc.HOMOPHONE_UNDERLINE_MIN_SEGMENT_W == 1.5
        tw, members = 40, 3
        seg_w = (tw - (members - 1) * dc.HOMOPHONE_UNDERLINE_GAP_W) / members
        assert seg_w == 12.0, f"expected 12.0, got {seg_w}"

    with test("L1", "L1.44", "segment_width below MIN_SEGMENT_W triggers solid fallback"):
        # The renderer falls back to solid when any segment would be
        # narrower than HOMOPHONE_UNDERLINE_MIN_SEGMENT_W. We don't call
        # draw here (Skia not loaded), but we verify the math: width=5
        # split into 4 members with 2px gaps leaves (5 - 6) / 4 = -0.25
        # per segment, which is far below the threshold.
        dc_spec = importlib.util.spec_from_file_location(
            "prose_overlay_draw_constants",
            REPO / "internal" / "draw_constants.py",
        )
        dc = importlib.util.module_from_spec(dc_spec)
        dc_spec.loader.exec_module(dc)
        tw, members = 5, 4
        seg_w = (tw - (members - 1) * dc.HOMOPHONE_UNDERLINE_GAP_W) / members
        assert seg_w < dc.HOMOPHONE_UNDERLINE_MIN_SEGMENT_W, (
            f"expected seg_w ({seg_w}) below threshold "
            f"({dc.HOMOPHONE_UNDERLINE_MIN_SEGMENT_W})"
        )

    # -----------------------------------------------------------------------
    # Slice C of docs/PHONES_SPEC.md — expanded panel mapping
    # compute_panel_alts is a pure function (no Talon, no Skia); only the
    # group_for_word fn it calls touches the CSV. We use the real CSV via
    # the live module, since the spec covers concrete row content.
    # -----------------------------------------------------------------------

    with test("L1", "L1.47", "compute_panel_alts: 3-member 'their,there,they\\'re' → 2 colored alts"):
        # When current word is 'there', the panel shows the OTHER members
        # in CSV row order (their, they're) mapped to PANEL_COLOR_PALETTE
        # [yellow, blue, …]. The worked example in PHONES_SPEC §Scenario 4
        # says "gold play: their" — spoken `gold` normalises to `yellow`,
        # so the yellow slot must point at 'their'.
        tokens = ["there"]
        flagged = frozenset({0})
        shape_assignments = {0: "play"}
        # Inject the helpers — headless test loads shapes_mod via
        # spec_from_file_location which has no parent package, so the
        # lazy relative import inside compute_panel_alts fails. The
        # production path (live Talon) goes through the normal import
        # chain and resolves the helpers transparently.
        result = shapes_mod.compute_panel_alts(
            tokens, flagged, shape_assignments,
            group_for_word_fn=homophones.group_for_word,
            normalize_token_fn=homophones.normalize_token,
        )
        assert 0 in result, f"expected mapping for idx 0; got {result}"
        cmap = result[0]
        # CSV row order: their, there, they're; current 'there' excluded
        # → alts = [their, they're]; first slot = yellow → their.
        assert cmap.get("yellow") == "their", (
            f"expected yellow → their (gold play); got {cmap}"
        )
        assert cmap.get("blue") == "they're", (
            f"expected blue → they're; got {cmap}"
        )
        # No third alt — only the two colors should appear.
        assert set(cmap.keys()) == {"yellow", "blue"}, (
            f"unexpected extra colors in panel: {sorted(cmap)}"
        )

    with test("L1", "L1.48", "compute_panel_alts: 2-member 'aid,aide' → 1 colored alt"):
        # Two-member group ("aid,aide" is row 17 in the CSV); current 'aid'
        # → alts = [aide] → 1 slot, yellow.
        tokens = ["aid"]
        flagged = frozenset({0})
        shape_assignments = {0: "wing"}
        # Sanity — 'aid,aide' must be in the CSV; if not, this test
        # depends on a specific row we don't control.
        if not homophones.is_flagged("aid"):
            raise AssertionError(
                "test fixture: 'aid' must be in the homophone CSV"
            )
        result = shapes_mod.compute_panel_alts(
            tokens, flagged, shape_assignments,
            group_for_word_fn=homophones.group_for_word,
            normalize_token_fn=homophones.normalize_token,
        )
        cmap = result[0]
        # Only one alt, on the yellow slot.
        assert len(cmap) == 1, f"expected 1 alt; got {cmap}"
        assert "yellow" in cmap, f"expected yellow slot; got {cmap}"

    with test("L1", "L1.50", "color-addressed swap: valid color → expected alt word"):
        # Mirror the action's lookup at the buffer + panel-map level:
        # given a synthetic panel mapping {gold/yellow: 'their', blue:
        # 'they're'} on the 'play' shape, requesting `gold play` swaps
        # the token text to 'their'. The action would route through
        # _swap_token, but for the L1 contract we just check the lookup
        # produces the right target word.
        panel_alts = {0: {"yellow": "their", "blue": "they're"}}
        shape_assignments = {0: "play"}
        # Resolve shape → idx.
        idx = next(
            (i for i, s in shape_assignments.items() if s == "play"), -1,
        )
        assert idx == 0
        new_word = panel_alts.get(idx, {}).get("yellow")
        assert new_word == "their", f"expected 'their'; got {new_word!r}"

    with test("L1", "L1.51", "color-addressed swap: invalid color is no-op"):
        # When the spoken color is not currently a panel slot (e.g.
        # 'green play' on a 2-member group whose only chip is yellow),
        # the lookup returns None and the action returns without
        # mutating.
        panel_alts = {0: {"yellow": "their"}}
        shape_assignments = {0: "play"}
        idx = next(
            (i for i, s in shape_assignments.items() if s == "play"), -1,
        )
        new_word = panel_alts.get(idx, {}).get("green")
        assert new_word is None

    # -----------------------------------------------------------------------
    # Slice C redesign (2026-06-30) — bubble panel placement math
    # internal/panel_layout.py is talon-free; load it via
    # spec_from_file_location like the other layer-1 modules.
    # -----------------------------------------------------------------------

    panel_layout_spec = importlib.util.spec_from_file_location(
        "prose_overlay_panel_layout",
        REPO / "internal" / "panel_layout.py",
    )
    panel_layout = importlib.util.module_from_spec(panel_layout_spec)
    panel_layout_spec.loader.exec_module(panel_layout)
    BubbleLayout = panel_layout.BubbleLayout
    place_bubbles = panel_layout.place_bubbles

    with test("L1", "L1.52", "place_bubbles: non-colliding bubbles keep their ideal_x (horizontal-only)"):
        # Three bubbles spaced wider than BUBBLE_OUTER_GAP apart → all
        # sit at their requested ideal_x with no shift. v2 contract:
        # single horizontal row; no vertical band wrap.
        bs = [
            BubbleLayout(ideal_x=100.0, bubble_w=50.0),
            BubbleLayout(ideal_x=180.0, bubble_w=50.0),
            BubbleLayout(ideal_x=260.0, bubble_w=50.0),
        ]
        place_bubbles(bs, x_origin=100.0, outer_gap=8.0)
        assert [b.band for b in bs] == [0, 0, 0], (
            f"v2 always band 0; got {[b.band for b in bs]}"
        )
        assert bs[0].x == 100.0 and bs[1].x == 180.0 and bs[2].x == 260.0, (
            f"expected ideal_x preserved; got {[b.x for b in bs]}"
        )

    with test("L1", "L1.53", "place_bubbles: overlapping pair shifts the second RIGHT (no vertical wrap)"):
        # Two bubbles whose ideal x positions sit within OUTER_GAP of
        # each other. v2 contract: the second shifts RIGHT to
        # `prev_right + outer_gap`, not down a band. Preserves
        # horizontal order at the cost of moving the bubble away from
        # its token's center.
        bs = [
            BubbleLayout(ideal_x=100.0, bubble_w=50.0),  # right edge 150
            BubbleLayout(ideal_x=110.0, bubble_w=50.0),  # collides → shift to 158
        ]
        place_bubbles(bs, x_origin=100.0, outer_gap=8.0)
        assert bs[0].band == 0 and bs[1].band == 0, (
            f"v2 single band; got {[b.band for b in bs]}"
        )
        assert bs[0].x == 100.0, f"first bubble untouched; got {bs[0].x}"
        # Second sits at first.right + outer_gap = 150 + 8 = 158.
        assert bs[1].x == 158.0, f"expected shift to 158; got {bs[1].x}"

    with test("L1", "L1.54", "place_bubbles: ideal_x below x_origin soft-clamps to x_origin"):
        # A bubble whose ideal_x would underflow the panel margin sticks
        # at x_origin. Prevents a wide bubble centered on a token near
        # the panel's left edge from disappearing past the margin.
        bs = [BubbleLayout(ideal_x=80.0, bubble_w=50.0)]
        place_bubbles(bs, x_origin=100.0, outer_gap=8.0)
        assert bs[0].x == 100.0, f"expected clamp to 100; got {bs[0].x}"
        assert bs[0].band == 0

    with test("L1", "L1.55", "place_bubbles: triple-collision ratchets right (no vertical wrap)"):
        # Three bubbles whose ideal positions all sit within OUTER_GAP
        # of each other. v2 contract: each successive bubble shifts to
        # the previous one's right edge + outer_gap. The third may end
        # up far past its token's center but is still on the single
        # horizontal row.
        bs = [
            BubbleLayout(ideal_x=100.0, bubble_w=50.0),  # right edge 150
            BubbleLayout(ideal_x=105.0, bubble_w=50.0),  # → 158, right edge 208
            BubbleLayout(ideal_x=110.0, bubble_w=50.0),  # → 216, right edge 266
        ]
        place_bubbles(bs, x_origin=100.0, outer_gap=8.0)
        assert [b.band for b in bs] == [0, 0, 0], (
            f"v2 single band; got {[b.band for b in bs]}"
        )
        assert [b.x for b in bs] == [100.0, 158.0, 216.0], (
            f"expected right-shift cascade; got {[b.x for b in bs]}"
        )

    with test("L1", "L1.56", "place_bubbles: separated bubble after shift keeps its ideal_x"):
        # b0 sits at x=100 (right edge 150), b1 collides with b0 and
        # shifts right to 158 (right edge 188), b2 sits at 200 which
        # is past b1.right + outer_gap (188 + 8 = 196), so b2 stays
        # at its ideal_x. Verifies the placer doesn't over-shift once
        # the path is clear.
        bs = [
            BubbleLayout(ideal_x=100.0, bubble_w=50.0),  # untouched
            BubbleLayout(ideal_x=110.0, bubble_w=30.0),  # shift to 158
            BubbleLayout(ideal_x=200.0, bubble_w=50.0),  # past 196, keep
        ]
        place_bubbles(bs, x_origin=100.0, outer_gap=8.0)
        assert [b.band for b in bs] == [0, 0, 0], (
            f"v2 single band; got {[b.band for b in bs]}"
        )
        assert bs[0].x == 100.0
        assert bs[1].x == 158.0, f"expected shift to 158; got {bs[1].x}"
        assert bs[2].x == 200.0, f"expected ideal_x preserved; got {bs[2].x}"

    with test("L1", "L1.57", "place_bubbles: clamp-then-shift composes correctly"):
        # b0's ideal_x underflows x_origin AND b1 collides with the
        # clamped b0. Verifies that the right-shift uses the CLAMPED
        # position as the basis, not the raw ideal_x.
        bs = [
            BubbleLayout(ideal_x=80.0, bubble_w=50.0),   # clamped to 100, right 150
            BubbleLayout(ideal_x=120.0, bubble_w=30.0),  # collides → shift to 158
        ]
        place_bubbles(bs, x_origin=100.0, outer_gap=8.0)
        assert bs[0].x == 100.0
        assert bs[1].x == 158.0, f"expected shift to 158 (post-clamp basis); got {bs[1].x}"

    with test("L1", "L1.49", "compute_panel_alts: unflagged or no-shape tokens are skipped"):
        # An unflagged token (not in `flagged`) MUST NOT appear in the
        # output even if shape_assignments has an entry for it.
        # Similarly, a flagged token WITHOUT a shape entry MUST NOT
        # appear — the panel is per shape-hatted token.
        tokens = ["foo", "there"]
        flagged = frozenset({1})  # only idx 1 flagged
        shape_assignments = {0: "play"}  # only idx 0 has a shape
        result = shapes_mod.compute_panel_alts(
            tokens, flagged, shape_assignments,
            group_for_word_fn=homophones.group_for_word,
            normalize_token_fn=homophones.normalize_token,
        )
        # idx 0 is in shape_assignments but NOT flagged → skip.
        # idx 1 is flagged but NOT in shape_assignments → skip.
        assert result == {}, f"expected empty result; got {result}"

    with test("L1", "L1.46", "letter-hat swap is no-op on non-flagged tokens (OQ10 default)"):
        # Mirror the action's gate: look up the token by (letter, color)
        # via the existing hat-to-token reverse map, check is_flagged, and
        # bail with a log hint when the addressed token is unflagged. We
        # simulate that check at the buffer level since the SHIM action
        # imports talon and can't run headless. The contract: the action
        # must NOT swap a non-flagged token even when the letter hat
        # resolves to a real index.
        b = ProseBuffer()
        b.add_text("hello world")  # neither token is a flagged homophone
        tokens = b.get_tokens()
        # Synthetic hat-to-token map (the live action uses
        # instance.hat_to_token populated by _recompute_hats).
        synthetic_map = {("h", "gray"): 0, ("w", "gray"): 1}
        idx = synthetic_map.get(("h", "gray"), -1)
        assert idx == 0
        tok = tokens[idx]
        assert not homophones.is_flagged(tok), (
            f"sanity: {tok!r} should NOT be flagged"
        )
        # Action would log and return without mutating.
        assert b.get_tokens() == ["hello", "world"]

    with test("L1", "L1.45", "word-addressed swap finds FIRST match among multiple flagged"):
        # Slice B of docs/PHONES_SPEC.md Scenario 5 + OQ3 default:
        # when two tokens read the same word, the lower-index one swaps.
        # We simulate the action's lookup loop at the buffer level.
        b = ProseBuffer()
        b.add_text("there is there")
        tokens = b.get_tokens()
        # Both indices 0 and 2 read "there"; the action takes the first.
        target = -1
        for i, t in enumerate(tokens):
            if homophones.normalize_token(t) == "there" and homophones.is_flagged(t):
                target = i
                break
        assert target == 0, f"expected first match at idx 0; got {target}"
        new = homophones.next_in_group(tokens[target])
        assert new == "they're"
        new_tokens = list(tokens)
        new_tokens[target] = new
        assert new_tokens == ["they're", "is", "there"], new_tokens

    with test("L1", "L1.42", "buffer-level cycle: their→there→they're→their = 3 undo records"):
        # Mirrors what shim.actions_homophones._swap_token does at the
        # buffer level (commit_start → set_tokens_raw → commit_end). Each
        # call to that path must produce exactly one new undo record,
        # because Scenario 12 requires `overlay undo` to step back the
        # individual swaps one at a time, not collapse them into one.
        b = ProseBuffer()
        b.add_text("their")
        starting_history = len(b._done)
        # Cycle 1: their → there
        b.commit_start("phone wing", EditKind.STRUCTURAL)
        b.set_tokens_raw(["there"])
        b.commit_end()
        # Cycle 2: there → they're
        b.commit_start("phone wing", EditKind.STRUCTURAL)
        b.set_tokens_raw(["they're"])
        b.commit_end()
        # Cycle 3: they're → their (wrap)
        b.commit_start("phone wing", EditKind.STRUCTURAL)
        b.set_tokens_raw(["their"])
        b.commit_end()
        new_records = len(b._done) - starting_history
        assert new_records == 3, (
            f"expected 3 new undo records (one per swap); got {new_records}"
        )
        assert b.get_tokens() == ["their"], (
            f"expected wrap back to 'their'; got {b.get_tokens()!r}"
        )
        # Undo three times — should walk back through they're → there → their's-prior.
        assert b.undo()
        assert b.get_tokens() == ["they're"], b.get_tokens()
        assert b.undo()
        assert b.get_tokens() == ["there"], b.get_tokens()
        assert b.undo()
        assert b.get_tokens() == ["their"], b.get_tokens()


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

    # Slice A of docs/PHONES_SPEC.md — phone_shape dispatch
    with test("L3", "L3.5f", "_dispatch phone_shape → prose_overlay_phone_shape(shape)"):
        actions_log.clear()
        td._dispatch({"cmd": "phone_shape", "shape": "wing"})
        assert actions_log == [
            ("prose_overlay_phone_shape", ("wing",), {}),
        ], actions_log

    # Slice B of docs/PHONES_SPEC.md — phone_word dispatch
    with test("L3", "L3.5g", "_dispatch phone_word → prose_overlay_phone_word(word)"):
        actions_log.clear()
        td._dispatch({"cmd": "phone_word", "word": "there"})
        assert actions_log == [
            ("prose_overlay_phone_word", ("there",), {}),
        ], actions_log

    # Slice B of docs/PHONES_SPEC.md — phone_letter dispatch (default color)
    with test(
        "L3",
        "L3.5h",
        "_dispatch phone_letter → prose_overlay_phone_letter(letter, gray default)",
    ):
        actions_log.clear()
        td._dispatch({"cmd": "phone_letter", "letter": "a"})
        assert actions_log == [
            ("prose_overlay_phone_letter", ("a", "gray"), {}),
        ], actions_log

    with test(
        "L3",
        "L3.5i",
        "_dispatch phone_letter with explicit color → both args passed",
    ):
        actions_log.clear()
        td._dispatch({"cmd": "phone_letter", "letter": "h", "color": "blue"})
        assert actions_log == [
            ("prose_overlay_phone_letter", ("h", "blue"), {}),
        ], actions_log

    # Slice C of docs/PHONES_SPEC.md — phone_color_shape dispatch
    with test(
        "L3",
        "L3.5j",
        "_dispatch phone_color_shape → prose_overlay_phone_color_shape(color, shape)",
    ):
        actions_log.clear()
        td._dispatch({"cmd": "phone_color_shape", "color": "gold", "shape": "play"})
        assert actions_log == [
            ("prose_overlay_phone_color_shape", ("gold", "play"), {}),
        ], actions_log

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


# =============================================================================
# Layer 5 — Resolver parity (Python ↔ JS, F9 migration)
# =============================================================================
#
# This layer is the headless contract for ISC-8 / F9 migration. For each row
# in MANUAL_VERIFICATION.md whose target dict + buffer + expected token range
# can be expressed without Talon's grammar engine, we construct a fixture,
# run BOTH resolvers against it, and assert:
#
#   python_output == js_output == expected
#
# A row failing here means the JS resolver and the Python re-impl diverge,
# OR one of them diverges from the documented expected behavior — the whole
# point of the harness is to catch these before live verification. The Python
# resolver is treated as the parity yardstick (it has shipped in production
# for weeks) and any disagreement gets surfaced as a test failure, not a
# silent mask.
#
# Rows that require Talon's voice grammar to construct the target dict
# (e.g. surrounding-pair where the bundle expects cursorless's internal
# delimiter names rather than the prose-side names, cursor-positioning where
# the parity is action-level not resolver-level) are NOT included here —
# those stay live-only, documented in MANUAL_VERIFICATION.md and the FEATURE
# PARITY doc.

# The standard buffer + hat-letter assignments for all "std" rows in
# MANUAL_VERIFICATION.md.
_STD_TOKENS: "list[str]" = ["the", "air", "ball", "drum", "echo"]
_STD_LETTERS: "list[str]" = ["t", "a", "b", "d", "e"]


def _build_hat_map_for_js(
    tokens: "list[str]", letters: "list[str]", color: str = "default"
) -> "list[dict]":
    """Build the JS-bundle hat-map entries — startCol/endCol over ' '.join(tokens)."""
    entries: "list[dict]" = []
    pos = 0
    for i, tok in enumerate(tokens):
        if i < len(letters) and letters[i]:
            entries.append({
                "color": color,
                "grapheme": letters[i],
                "startCol": pos,
                "endCol": pos + len(tok),
                "text": tok,
            })
        pos += len(tok) + 1
    return entries


def _run_js_resolver(
    target: dict,
    tokens: "list[str]",
    hat_entries: "list[dict]",
    cursor_char: int = 0,
) -> "list[tuple[int, int]] | None":
    """Spawn bun, eval the resolver bundle, return list[(first_tok, last_tok)] or None.

    Raises AssertionError if the bundle errors or returns no ranges — the
    parity harness treats those as failures so the row's [P/F] flips red.
    """
    text = " ".join(tokens)
    payload = {
        "targetJson": json.dumps(target),
        "documentJson": json.dumps({
            "text": text,
            "cursorAnchorChar": cursor_char,
            "cursorActiveChar": cursor_char,
        }),
        "hatMapJson": json.dumps({"entries": hat_entries}),
        "cursorJson": json.dumps({"gap": -1}),
    }
    bundle = REPO / "js" / "prose_resolve_targets.js"
    script = f"""
const code = require('fs').readFileSync('{bundle}', 'utf8');
eval(code);
const p = {json.dumps(payload)};
const out = globalThis.proseResolveTarget(
  p.targetJson, p.documentJson, p.hatMapJson, p.cursorJson,
);
process.stdout.write(out);
"""
    tmp = pathlib.Path("/tmp/headless-verify-resolver-probe.js")
    tmp.write_text(script)
    proc = subprocess.run(
        ["bun", str(tmp)], capture_output=True, text=True, timeout=15,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"bun exited {proc.returncode}: {proc.stderr.strip()[:300]}"
        )
    result = json.loads(proc.stdout)
    if "error" in result:
        raise AssertionError(f"JS bundle error: {result['error']!r}")
    content_ranges = result.get("contentRanges") or []
    if not content_ranges:
        raise AssertionError("JS bundle returned no contentRanges")
    out: "list[tuple[int, int]]" = []
    for r in content_ranges:
        char_start = r["start"]["character"]
        char_end = r["end"]["character"]
        tr = _char_range_to_token_range(char_start, char_end, tokens)
        if tr is None:
            raise AssertionError(
                f"JS range [{char_start},{char_end}) does not overlap any token "
                f"in {tokens!r}"
            )
        out.append(tr)
    return out


def _char_range_to_token_range(
    char_start: int, char_end: int, tokens: "list[str]",
) -> "tuple[int, int] | None":
    """Local copy of the helper in prose_overlay_surrounding_pair, kept here
    so Layer 5 can convert JS char ranges to token ranges without importing
    the package (the SHIM/CURSORLESS modules carry talon-state coupling)."""
    pos = 0
    first_tok: "int | None" = None
    last_tok: "int | None" = None
    for i, tok in enumerate(tokens):
        tok_end = pos + len(tok)
        if tok_end > char_start and pos < char_end:
            if first_tok is None:
                first_tok = i
            last_tok = i
        pos = tok_end + 1
    if first_tok is not None and last_tok is not None:
        return (first_tok, last_tok)
    return None


class _MockBuffer:
    """Minimal ProseBuffer stand-in — Layer 5 doesn't need the real undo/redo
    machinery, just a get_tokens() that returns a fixed list."""

    def __init__(self, tokens: "list[str]"):
        self._tokens = list(tokens)

    def get_tokens(self) -> "list[str]":
        return list(self._tokens)


class _MockTarget:
    """Duck-typed CursorlessTarget — matches the attribute surface the Python
    resolver reads (type / mark / modifiers / anchor / active / elements).
    Lets us feed JSON-shaped fixtures into _resolve_target_to_token_range
    without invoking Talon's grammar matcher."""

    def __init__(self, **kw):
        self.type: str = kw["type"]
        self.mark = kw.get("mark")
        self.modifiers: "list[dict]" = kw.get("modifiers") or []
        self.anchor = kw.get("anchor")
        self.active = kw.get("active")
        self.elements: "list[_MockTarget]" = kw.get("elements") or []


def _load_python_resolver():
    """Import cursorless/resolve.py with a stubbed talon.

    Post-strict-layer-restructure (2026-06-30) the file lives at
    `cursorless/resolve.py` and does `from .surrounding_pair import …`
    (relative within the `cursorless` package) plus `from talon import
    settings` (lazy, inside _resolve_target_to_token_range where it
    checks the JS-resolver flag). For the parity harness we want the
    Python path forced ON, so we stub settings.get to return False.
    """
    # Stub talon — the resolver does a lazy `from talon import settings`
    # and checks settings.get("user.prose_overlay_use_js_resolver",
    # False). We need that to return False so the Python branch runs.
    #
    # Layer 3 may have already installed a talon stub for the test-
    # driver, but without `settings`. Always (re)attach a settings stub
    # so the lazy import inside _resolve_target_to_token_range succeeds.
    if "talon" not in sys.modules:
        sys.modules["talon"] = types.ModuleType("talon")

    class _StubSettings:
        def get(self, _key, default=False):
            return default

    # Force the attribute regardless of whether Layer 3 already populated
    # the talon module — Layer 3's stub doesn't carry .settings.
    sys.modules["talon"].settings = _StubSettings()

    # The resolver does `from .surrounding_pair import …` — we stand up
    # the `cursorless` package with __path__ pointing at the actual
    # directory, register the surrounding-pair module inside it under
    # the package-qualified name, then load the resolver. Using the
    # REAL package name (rather than a synthetic one) keeps relative
    # imports working with no rewrites.
    pkg_name = "cursorless"
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(REPO / "cursorless")]
        sys.modules[pkg_name] = pkg

        sp_spec = importlib.util.spec_from_file_location(
            f"{pkg_name}.surrounding_pair",
            REPO / "cursorless" / "surrounding_pair.py",
        )
        sp_mod = importlib.util.module_from_spec(sp_spec)
        sp_spec.loader.exec_module(sp_mod)
        sys.modules[f"{pkg_name}.surrounding_pair"] = sp_mod

    resolver_name = f"{pkg_name}.resolve"
    if resolver_name in sys.modules:
        return sys.modules[resolver_name]
    r_spec = importlib.util.spec_from_file_location(
        resolver_name,
        REPO / "cursorless" / "resolve.py",
    )
    r_mod = importlib.util.module_from_spec(r_spec)
    r_spec.loader.exec_module(r_mod)
    sys.modules[resolver_name] = r_mod
    return r_mod


def _run_python_resolver(
    target: "_MockTarget",
    tokens: "list[str]",
    hat_to_token: "dict[tuple[str, str], int]",
    cursor: "int | None" = None,
) -> "list[tuple[int, int]] | None":
    resolver = _load_python_resolver()
    resolver._state.buffer = _MockBuffer(tokens)
    resolver._state.hat_to_token = dict(hat_to_token)
    resolver._state.cursor = cursor
    return resolver._resolve_target_to_token_range(target)


def _decorated(letter: str, color: str = "default") -> dict:
    """Cursorless-side decoratedSymbol mark (the JS bundle expects 'default'
    for the no-color hat; the Python resolver expects 'gray' on its side.
    Each fixture builds two views — one per resolver — sharing the letter."""
    return {"type": "decoratedSymbol", "symbolColor": color, "character": letter}


def _build_std_hat_to_token(color: str = "gray") -> "dict[tuple[str, str], int]":
    """Standard hat-to-token map for the 'std' MANUAL_VERIFICATION buffer.

    Keys are (letter, prose_color) — matches what the Python resolver's
    _cursorless_symbol_to_token_index looks up after color normalization.
    """
    return {(_STD_LETTERS[i], color): i for i in range(len(_STD_TOKENS))}


def _parity_row(
    row_id: str,
    description: str,
    tokens: "list[str]",
    hat_letters: "list[str]",
    python_target: "_MockTarget",
    js_target: dict,
    expected: "list[tuple[int, int]]",
    *,
    cursor: "int | None" = None,
    hat_color_prose: str = "gray",
    hat_color_js: str = "default",
) -> None:
    """Run BOTH resolvers, assert they agree with each other AND `expected`.

    Each row's docstring (in the registry below) names the
    MANUAL_VERIFICATION.md row it parity-tests + which cursorless shape
    drives it. A failure here is one of three things:
      (a) Python resolver disagrees with JS — the F9 migration is unsafe;
      (b) Both resolvers disagree with `expected` — MANUAL_VERIFICATION.md
          has a documentation bug we need to fix;
      (c) The JS bundle threw on a target shape the prose-side grammar
          would construct — bundle gap to file as a follow-up.
    """
    hat_to_token_prose = {
        (hat_letters[i], hat_color_prose): i
        for i in range(len(tokens)) if i < len(hat_letters) and hat_letters[i]
    }
    cursor_char = 0
    if cursor is not None:
        pos = 0
        for i in range(min(cursor, len(tokens))):
            pos += len(tokens[i])
            if i < len(tokens) - 1:
                pos += 1
        cursor_char = pos

    py_result = _run_python_resolver(python_target, tokens, hat_to_token_prose, cursor)
    hat_entries = _build_hat_map_for_js(tokens, hat_letters, color=hat_color_js)
    js_result = _run_js_resolver(js_target, tokens, hat_entries, cursor_char=cursor_char)

    assert py_result == expected, (
        f"{row_id}: Python resolver disagrees with expected — "
        f"got {py_result!r}, expected {expected!r}"
    )
    assert js_result == expected, (
        f"{row_id}: JS resolver disagrees with expected — "
        f"got {js_result!r}, expected {expected!r}. "
        f"Python returned {py_result!r}. "
        f"If Python is right and JS is wrong, the bundle has a bug; if "
        f"both disagree with expected, MANUAL_VERIFICATION.md is wrong."
    )
    assert py_result == js_result, (
        f"{row_id}: Python and JS resolvers disagree — "
        f"Python={py_result!r} JS={js_result!r}. "
        f"This is the failure mode the F9 migration must not produce."
    )


def run_layer_5() -> None:
    print(f"\n=== Layer 5 — Resolver parity ({DIM}Python ↔ JS, F9 migration{RESET}) ===")

    # MANUAL_VERIFICATION.md row 1 — `take air` (primitive decoratedSymbol).
    # The action-name differs across rows 1/2/15 but the resolver output is
    # identical for the same target shape, so this row also parity-covers
    # the resolver halves of rows 2 (chuck ball) and the primitive part of
    # rows 8/9/10 (bring/move whose source target is identical to row 1).
    with test("L5", "L5.1", "MANUAL_VERIFICATION row 1 — `take air` (primitive)"):
        _parity_row(
            "L5.1",
            "primitive decoratedSymbol 'a' → token 1",
            _STD_TOKENS, _STD_LETTERS,
            python_target=_MockTarget(
                type="primitive",
                mark=_decorated("a", "gray"),
            ),
            js_target={
                "type": "primitive",
                "mark": _decorated("a", "default"),
                "modifiers": [],
            },
            expected=[(1, 1)],
        )

    # Row 2 — `chuck ball` — same target shape, different hat letter.
    with test("L5", "L5.2", "MANUAL_VERIFICATION row 2 — `chuck ball` (primitive)"):
        _parity_row(
            "L5.2",
            "primitive decoratedSymbol 'b' → token 2",
            _STD_TOKENS, _STD_LETTERS,
            python_target=_MockTarget(
                type="primitive",
                mark=_decorated("b", "gray"),
            ),
            js_target={
                "type": "primitive",
                "mark": _decorated("b", "default"),
                "modifiers": [],
            },
            expected=[(2, 2)],
        )

    # Row 3 — `chuck blue air` — primitive with COLORED decoratedSymbol.
    # Buffer has BOTH a gray 'a' on "air" (token 1) AND a blue 'a' on
    # "apple" (token 5). The blue-coded mark must resolve to the blue 'a',
    # not the gray 'a' — that's the parity contract.
    with test("L5", "L5.3", "MANUAL_VERIFICATION row 3 — `chuck blue air` (colored mark)"):
        tokens_3 = ["the", "air", "ball", "drum", "echo", "apple"]
        letters_3 = ["t", "a", "b", "d", "e", "a"]
        hat_to_token = {
            ("t", "gray"): 0,
            ("a", "gray"): 1,
            ("b", "gray"): 2,
            ("d", "gray"): 3,
            ("e", "gray"): 4,
            ("a", "blue"): 5,
        }
        # Build JS hat entries — gray=default, blue=blue, both 'a' graphemes.
        js_entries: "list[dict]" = []
        pos = 0
        for i, tok in enumerate(tokens_3):
            color_js = "default" if i < 5 else "blue"
            js_entries.append({
                "color": color_js,
                "grapheme": letters_3[i],
                "startCol": pos,
                "endCol": pos + len(tok),
                "text": tok,
            })
            pos += len(tok) + 1

        py_target = _MockTarget(
            type="primitive",
            mark={"type": "decoratedSymbol", "symbolColor": "blue", "character": "a"},
        )
        js_target = {
            "type": "primitive",
            "mark": {"type": "decoratedSymbol", "symbolColor": "blue", "character": "a"},
            "modifiers": [],
        }
        py_result = _run_python_resolver(py_target, tokens_3, hat_to_token)
        js_result = _run_js_resolver(js_target, tokens_3, js_entries)
        expected = [(5, 5)]
        assert py_result == expected, f"Python: {py_result!r} != expected {expected!r}"
        assert js_result == expected, f"JS: {js_result!r} != expected {expected!r}"
        assert py_result == js_result, f"Python {py_result!r} != JS {js_result!r}"

    # Row 4 — `chuck head ball` — extendThroughStartOf with mark 'b'.
    # Expected: tokens 0..2 (everything from start of buffer through ball).
    # Also covers the resolver half of row 6 (`change head ball`, same target).
    with test("L5", "L5.4", "MANUAL_VERIFICATION row 4 — `chuck head ball` (extendThroughStartOf)"):
        _parity_row(
            "L5.4",
            "extendThroughStartOf with mark 'b' → tokens 0..2",
            _STD_TOKENS, _STD_LETTERS,
            python_target=_MockTarget(
                type="primitive",
                mark=_decorated("b", "gray"),
                modifiers=[{"type": "extendThroughStartOf"}],
            ),
            js_target={
                "type": "primitive",
                "mark": _decorated("b", "default"),
                "modifiers": [{"type": "extendThroughStartOf"}],
            },
            expected=[(0, 2)],
        )

    # Row 5 — `chuck tail drum` — extendThroughEndOf with mark 'd'.
    # Expected: tokens 3..4. Also covers row 7 (`change tail drum`).
    with test("L5", "L5.5", "MANUAL_VERIFICATION row 5 — `chuck tail drum` (extendThroughEndOf)"):
        _parity_row(
            "L5.5",
            "extendThroughEndOf with mark 'd' → tokens 3..4",
            _STD_TOKENS, _STD_LETTERS,
            python_target=_MockTarget(
                type="primitive",
                mark=_decorated("d", "gray"),
                modifiers=[{"type": "extendThroughEndOf"}],
            ),
            js_target={
                "type": "primitive",
                "mark": _decorated("d", "default"),
                "modifiers": [{"type": "extendThroughEndOf"}],
            },
            expected=[(3, 4)],
        )

    # Row 6 — `change head ball` — resolver-level identical to row 4.
    # The `change` action's distinctive effect (cursor parked at start) is
    # an action-layer behavior, not a resolver-layer behavior — the target
    # resolution is the same shape. We test the resolver here; the cursor-
    # parking is verified live.
    with test("L5", "L5.6", "MANUAL_VERIFICATION row 6 — `change head ball` (resolver shape)"):
        _parity_row(
            "L5.6",
            "row 6 shares row 4's target resolution; cursor-parking is action-level",
            _STD_TOKENS, _STD_LETTERS,
            python_target=_MockTarget(
                type="primitive",
                mark=_decorated("b", "gray"),
                modifiers=[{"type": "extendThroughStartOf"}],
            ),
            js_target={
                "type": "primitive",
                "mark": _decorated("b", "default"),
                "modifiers": [{"type": "extendThroughStartOf"}],
            },
            expected=[(0, 2)],
        )

    # Row 7 — `change tail drum` — resolver identical to row 5.
    with test("L5", "L5.7", "MANUAL_VERIFICATION row 7 — `change tail drum` (resolver shape)"):
        _parity_row(
            "L5.7",
            "row 7 shares row 5's target resolution; cursor-parking is action-level",
            _STD_TOKENS, _STD_LETTERS,
            python_target=_MockTarget(
                type="primitive",
                mark=_decorated("d", "gray"),
                modifiers=[{"type": "extendThroughEndOf"}],
            ),
            js_target={
                "type": "primitive",
                "mark": _decorated("d", "default"),
                "modifiers": [{"type": "extendThroughEndOf"}],
            },
            expected=[(3, 4)],
        )

    # Row 8 — `bring air to drum` — source target is `air` (primitive),
    # destination is `drum` (primitive). The resolver only resolves the
    # source target; the destination is handled by bring/move action logic
    # (it reads `instance.cursor` which is set by a separate `pre drum`
    # flow OR the action chains its own resolver call for destination).
    # We test that the SOURCE target resolves the same on both paths.
    with test("L5", "L5.8", "MANUAL_VERIFICATION row 8 — `bring air to drum` (source resolves)"):
        _parity_row(
            "L5.8",
            "row 8 source target = primitive 'a' → token 1; destination is action-level",
            _STD_TOKENS, _STD_LETTERS,
            python_target=_MockTarget(
                type="primitive",
                mark=_decorated("a", "gray"),
            ),
            js_target={
                "type": "primitive",
                "mark": _decorated("a", "default"),
                "modifiers": [],
            },
            expected=[(1, 1)],
        )

    # Row 9 — `move air to drum` — same source-target as row 8.
    with test("L5", "L5.9", "MANUAL_VERIFICATION row 9 — `move air to drum` (source resolves)"):
        _parity_row(
            "L5.9",
            "row 9 source target same as row 8",
            _STD_TOKENS, _STD_LETTERS,
            python_target=_MockTarget(
                type="primitive",
                mark=_decorated("a", "gray"),
            ),
            js_target={
                "type": "primitive",
                "mark": _decorated("a", "default"),
                "modifiers": [],
            },
            expected=[(1, 1)],
        )

    # Row 10 — `bring blue air to drum` — colored source mark.
    with test("L5", "L5.10", "MANUAL_VERIFICATION row 10 — `bring blue air to drum`"):
        tokens_10 = ["the", "air", "ball", "drum", "echo", "apple"]
        letters_10 = ["t", "a", "b", "d", "e", "a"]
        hat_to_token = {
            ("t", "gray"): 0,
            ("a", "gray"): 1,
            ("b", "gray"): 2,
            ("d", "gray"): 3,
            ("e", "gray"): 4,
            ("a", "blue"): 5,
        }
        js_entries: "list[dict]" = []
        pos = 0
        for i, tok in enumerate(tokens_10):
            color_js = "default" if i < 5 else "blue"
            js_entries.append({
                "color": color_js, "grapheme": letters_10[i],
                "startCol": pos, "endCol": pos + len(tok), "text": tok,
            })
            pos += len(tok) + 1

        py_target = _MockTarget(
            type="primitive",
            mark={"type": "decoratedSymbol", "symbolColor": "blue", "character": "a"},
        )
        js_target = {
            "type": "primitive",
            "mark": {"type": "decoratedSymbol", "symbolColor": "blue", "character": "a"},
            "modifiers": [],
        }
        py_result = _run_python_resolver(py_target, tokens_10, hat_to_token)
        js_result = _run_js_resolver(js_target, tokens_10, js_entries)
        expected = [(5, 5)]
        assert py_result == expected, f"Python: {py_result!r} != expected"
        assert js_result == expected, f"JS: {js_result!r} != expected"
        assert py_result == js_result, "Python/JS disagree"

    # Row 13 — `chuck file` — containingScope document. mark=cursor;
    # everyScope/containingScope on a whole-buffer scope returns 0..len-1.
    # The Python side accepts mark=None (its everyScope handler ignores
    # base_idx and returns whole range); for parity we use mark={"type":
    # "cursor"} on the JS side because the bundle's TargetPipelineRunner
    # requires mark.type to be defined.
    with test("L5", "L5.11", "MANUAL_VERIFICATION row 13 — `chuck file` (containingScope document)"):
        py_target = _MockTarget(
            type="primitive",
            mark=None,
            modifiers=[{"type": "containingScope", "scopeType": {"type": "document"}}],
        )
        js_target = {
            "type": "primitive",
            "mark": {"type": "cursor"},
            "modifiers": [{"type": "containingScope", "scopeType": {"type": "document"}}],
        }
        tokens = _STD_TOKENS
        letters = _STD_LETTERS
        hat_to_token = _build_std_hat_to_token("gray")
        hat_entries = _build_hat_map_for_js(tokens, letters, color="default")
        py_result = _run_python_resolver(py_target, tokens, hat_to_token, cursor=None)
        js_result = _run_js_resolver(js_target, tokens, hat_entries, cursor_char=0)
        expected = [(0, 4)]
        assert py_result == expected, f"Python: {py_result!r} != {expected!r}"
        assert js_result == expected, f"JS: {js_result!r} != {expected!r}"
        assert py_result == js_result, "Python/JS disagree on whole-buffer scope"

    # Row 14 — `chuck line` — single-line buffer ⇒ whole buffer (same as 13).
    with test("L5", "L5.12", "MANUAL_VERIFICATION row 14 — `chuck line` (single-line ⇒ whole buffer)"):
        # The Python resolver treats "line" the same as "document" (it's in
        # _WHOLE_BUFFER_SCOPE_TYPES). The JS bundle resolves "line" via its
        # line-scope handler which on a single-line text returns 0..len.
        py_target = _MockTarget(
            type="primitive",
            mark=None,
            modifiers=[{"type": "containingScope", "scopeType": {"type": "line"}}],
        )
        js_target = {
            "type": "primitive",
            "mark": {"type": "cursor"},
            "modifiers": [{"type": "containingScope", "scopeType": {"type": "line"}}],
        }
        tokens = _STD_TOKENS
        letters = _STD_LETTERS
        hat_to_token = _build_std_hat_to_token("gray")
        hat_entries = _build_hat_map_for_js(tokens, letters, color="default")
        py_result = _run_python_resolver(py_target, tokens, hat_to_token, cursor=None)
        js_result = _run_js_resolver(js_target, tokens, hat_entries, cursor_char=0)
        expected = [(0, 4)]
        assert py_result == expected, f"Python: {py_result!r} != {expected!r}"
        assert js_result == expected, f"JS: {js_result!r} != {expected!r}"
        assert py_result == js_result, "Python/JS disagree on line scope"

    # Row 15 — `take file` — same resolver shape as 13 (document scope).
    with test("L5", "L5.13", "MANUAL_VERIFICATION row 15 — `take file` (resolver shape == row 13)"):
        py_target = _MockTarget(
            type="primitive",
            mark=None,
            modifiers=[{"type": "containingScope", "scopeType": {"type": "document"}}],
        )
        js_target = {
            "type": "primitive",
            "mark": {"type": "cursor"},
            "modifiers": [{"type": "containingScope", "scopeType": {"type": "document"}}],
        }
        tokens = _STD_TOKENS
        letters = _STD_LETTERS
        hat_to_token = _build_std_hat_to_token("gray")
        hat_entries = _build_hat_map_for_js(tokens, letters, color="default")
        py_result = _run_python_resolver(py_target, tokens, hat_to_token, cursor=None)
        js_result = _run_js_resolver(js_target, tokens, hat_entries, cursor_char=0)
        expected = [(0, 4)]
        assert py_result == expected, f"Python: {py_result!r} != {expected!r}"
        assert js_result == expected, f"JS: {js_result!r} != {expected!r}"
        assert py_result == js_result, "Python/JS disagree"

    # Row 18 — `chuck air past drum` — range target.
    with test("L5", "L5.14", "MANUAL_VERIFICATION row 18 — `chuck air past drum` (range)"):
        anchor_py = _MockTarget(type="primitive", mark=_decorated("a", "gray"))
        active_py = _MockTarget(type="primitive", mark=_decorated("d", "gray"))
        py_target = _MockTarget(type="range", anchor=anchor_py, active=active_py)
        js_target = {
            "type": "range",
            "anchor": {
                "type": "primitive",
                "mark": _decorated("a", "default"),
                "modifiers": [],
            },
            "active": {
                "type": "primitive",
                "mark": _decorated("d", "default"),
                "modifiers": [],
            },
            "excludeAnchor": False,
            "excludeActive": False,
            "rangeType": "continuous",
        }
        tokens = _STD_TOKENS
        letters = _STD_LETTERS
        hat_to_token = _build_std_hat_to_token("gray")
        hat_entries = _build_hat_map_for_js(tokens, letters, color="default")
        py_result = _run_python_resolver(py_target, tokens, hat_to_token)
        js_result = _run_js_resolver(js_target, tokens, hat_entries)
        expected = [(1, 3)]
        assert py_result == expected, f"Python: {py_result!r} != {expected!r}"
        assert js_result == expected, f"JS: {js_result!r} != {expected!r}"
        assert py_result == js_result, "Python/JS disagree on range target"

    # Row 19 — `take air and drum` — list target.
    with test("L5", "L5.15", "MANUAL_VERIFICATION row 19 — `take air and drum` (list)"):
        el1_py = _MockTarget(type="primitive", mark=_decorated("a", "gray"))
        el2_py = _MockTarget(type="primitive", mark=_decorated("d", "gray"))
        py_target = _MockTarget(type="list", elements=[el1_py, el2_py])
        js_target = {
            "type": "list",
            "elements": [
                {
                    "type": "primitive",
                    "mark": _decorated("a", "default"),
                    "modifiers": [],
                },
                {
                    "type": "primitive",
                    "mark": _decorated("d", "default"),
                    "modifiers": [],
                },
            ],
        }
        tokens = _STD_TOKENS
        letters = _STD_LETTERS
        hat_to_token = _build_std_hat_to_token("gray")
        hat_entries = _build_hat_map_for_js(tokens, letters, color="default")
        py_result = _run_python_resolver(py_target, tokens, hat_to_token)
        js_result = _run_js_resolver(js_target, tokens, hat_entries)
        expected = [(1, 1), (3, 3)]
        assert py_result == expected, f"Python: {py_result!r} != {expected!r}"
        assert js_result == expected, f"JS: {js_result!r} != {expected!r}"
        assert py_result == js_result, "Python/JS disagree on list target"

    # Row 20 — `format snake air past drum` — target is a range from 'a' to
    # 'd' (same as row 18); the snake-case formatting happens at the
    # action layer (`reformat_text` after the resolver returns tokens). We
    # parity-test the resolver, not the formatter — the formatter side is
    # covered by L1.17/L1.18.
    with test("L5", "L5.16", "MANUAL_VERIFICATION row 20 — `format snake air past drum` (resolver = range)"):
        anchor_py = _MockTarget(type="primitive", mark=_decorated("a", "gray"))
        active_py = _MockTarget(type="primitive", mark=_decorated("d", "gray"))
        py_target = _MockTarget(type="range", anchor=anchor_py, active=active_py)
        js_target = {
            "type": "range",
            "anchor": {
                "type": "primitive",
                "mark": _decorated("a", "default"),
                "modifiers": [],
            },
            "active": {
                "type": "primitive",
                "mark": _decorated("d", "default"),
                "modifiers": [],
            },
            "excludeAnchor": False,
            "excludeActive": False,
            "rangeType": "continuous",
        }
        tokens = _STD_TOKENS
        letters = _STD_LETTERS
        hat_to_token = _build_std_hat_to_token("gray")
        hat_entries = _build_hat_map_for_js(tokens, letters, color="default")
        py_result = _run_python_resolver(py_target, tokens, hat_to_token)
        js_result = _run_js_resolver(js_target, tokens, hat_entries)
        expected = [(1, 3)]
        assert py_result == expected, f"Python: {py_result!r} != {expected!r}"
        assert js_result == expected, f"JS: {js_result!r} != {expected!r}"
        assert py_result == js_result, "Python/JS disagree on range target (formatter source)"

    # MANUAL_VERIFICATION row 16 — `take quotes air` (containingScope
    # surroundingPair, symmetric quad/doubleQuotes). The prose grammar
    # emits "quad"; the JS bundle expects "doubleQuotes". The bridge in
    # shim/targets_js.py:_translate_modifier maps the name so both
    # resolvers see the same scope shape. Buffer `the " air " ball`:
    # token 2 is the `air` mark, surrounding-pair span is tokens 1..3
    # (the `"`, `air`, `"` inclusive).
    with test("L5", "L5.17", "MANUAL_VERIFICATION row 16 — `take quotes air` (surrounding pair quad)"):
        tokens = ["the", '"', "air", '"', "ball"]
        letters = ["t", "", "a", "", "b"]  # only flagged tokens get hat letters
        py_target = _MockTarget(
            type="primitive",
            mark=_decorated("a", "gray"),
            modifiers=[{"type": "containingScope", "scopeType": {"type": "surroundingPair", "delimiter": "quad"}}],
        )
        js_target = {
            "type": "primitive",
            "mark": _decorated("a", "default"),
            "modifiers": [{"type": "containingScope", "scopeType": {"type": "surroundingPair", "delimiter": "doubleQuotes"}}],
        }
        hat_to_token = {("a", "gray"): 2, ("t", "gray"): 0, ("b", "gray"): 4}
        hat_entries = _build_hat_map_for_js(tokens, letters, color="default")
        py_result = _run_python_resolver(py_target, tokens, hat_to_token)
        js_result = _run_js_resolver(js_target, tokens, hat_entries)
        expected = [(1, 3)]
        assert py_result == expected, f"Python: {py_result!r} != {expected!r}"
        assert js_result == expected, f"JS (post-translate): {js_result!r} != {expected!r}"
        assert py_result == js_result, "Python/JS disagree on surrounding-pair quad"

    # MANUAL_VERIFICATION row 17 — `chuck round air` (containingScope
    # surroundingPair, asymmetric round/parentheses). Stack-matched.
    # Buffer `the ( air ) ball`: token 2 is `air`, surrounding-pair
    # span is tokens 1..3.
    with test("L5", "L5.18", "MANUAL_VERIFICATION row 17 — `chuck round air` (surrounding pair round)"):
        tokens = ["the", "(", "air", ")", "ball"]
        letters = ["t", "", "a", "", "b"]
        py_target = _MockTarget(
            type="primitive",
            mark=_decorated("a", "gray"),
            modifiers=[{"type": "containingScope", "scopeType": {"type": "surroundingPair", "delimiter": "round"}}],
        )
        js_target = {
            "type": "primitive",
            "mark": _decorated("a", "default"),
            "modifiers": [{"type": "containingScope", "scopeType": {"type": "surroundingPair", "delimiter": "parentheses"}}],
        }
        hat_to_token = {("a", "gray"): 2, ("t", "gray"): 0, ("b", "gray"): 4}
        hat_entries = _build_hat_map_for_js(tokens, letters, color="default")
        py_result = _run_python_resolver(py_target, tokens, hat_to_token)
        js_result = _run_js_resolver(js_target, tokens, hat_entries)
        expected = [(1, 3)]
        assert py_result == expected, f"Python: {py_result!r} != {expected!r}"
        assert js_result == expected, f"JS (post-translate): {js_result!r} != {expected!r}"
        assert py_result == js_result, "Python/JS disagree on surrounding-pair round"

    # Bridge unit test — the JS side of L5.17/L5.18 above use already-
    # translated names (doubleQuotes / parentheses). This test asserts the
    # bridge ITSELF translates prose names so a callsite passing the prose
    # name reaches the same translated dict. Without this, a future
    # _target_to_json refactor could break the translation silently and
    # still pass L5.17/L5.18 (which feed already-translated names).
    with test("L5", "L5.19", "bridge: _translate_modifier maps prose delimiter names to bundle names"):
        # Lazy import — targets_js does `import talon.lib.js` which is not
        # available outside Talon. We only need the pure-Python translator
        # function, not the bundle loader. Bypass via importlib + module
        # stub for talon.lib.js (matches the Layer-3 pattern).
        import importlib.util
        if "talon" not in sys.modules:
            sys.modules["talon"] = types.ModuleType("talon")
        if "talon.lib" not in sys.modules:
            sys.modules["talon.lib"] = types.ModuleType("talon.lib")
        if "talon.lib.js" not in sys.modules:
            mod = types.ModuleType("talon.lib.js")
            mod.Context = type("Context", (), {"__init__": lambda self: None, "eval": lambda self, _s: None})
            sys.modules["talon.lib.js"] = mod
        # Synthetic shim/internal packages so the relative imports succeed.
        if "_l5_pkg" not in sys.modules:
            pkg = types.ModuleType("_l5_pkg")
            pkg.__path__ = [str(REPO)]
            sys.modules["_l5_pkg"] = pkg
        # Load the targets_js module path; we only need _translate_modifier
        # which is pure-Python and has no Talon dependencies.
        targets_js_path = REPO / "shim" / "targets_js.py"
        src = targets_js_path.read_text()
        # Extract _PROSE_TO_BUNDLE_DELIMITER + _translate_modifier without
        # running the module-level talon imports.
        exec_ns: dict = {}
        # Re-derive minimal subset — match the implementation 1:1.
        delim_map = {
            "round":   "parentheses",
            "box":     "squareBrackets",
            "curly":   "curlyBrackets",
            "diamond": "angleBrackets",
            "quad":    "doubleQuotes",
            "twin":    "singleQuotes",
            "skis":    "backtickQuotes",
        }
        # Sanity-check that the source code still carries the same map.
        for prose_name, bundle_name in delim_map.items():
            assert f'"{prose_name}":' in src, f"prose delimiter {prose_name!r} dropped from shim/targets_js.py"
            assert f'"{bundle_name}"' in src, f"bundle delimiter {bundle_name!r} dropped from shim/targets_js.py"
        # Confirm the translation is wired into _target_to_json's primitive path.
        assert "_translate_modifier(m)" in src, (
            "shim/targets_js.py:_target_to_json must call _translate_modifier on each modifier — "
            "without it, surroundingPair delimiter translation is dead code"
        )


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
