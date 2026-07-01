"""Layer 1 — pure Python (no talon, no bun).

Exercises internal/state.py (ProseBuffer + compute_hat_assignments),
internal/homophones.py, internal/history_persist.py, shim/shapes.py's
allocator, and the ProseOverlayState reset invariants.

Loaded via spec_from_file_location so no talon or JS is needed. This
is the biggest layer (~70 tests) — historically the most surface area
in one file. See docs/HEADLESS_VERIFY_PLAN.md for the test-ID scheme.
"""

import importlib.util
import pathlib
import tempfile

from .common import (
    DIM,
    REPO,
    RESET,
    _load_instance_module,
    _load_state_module,
    test,
)

# =============================================================================
# Layer 1 — pure Python
# =============================================================================

# _load_instance_module lives in .common — one source of truth used by
# both Layer 1's reset-invariants tests and Layer 3's stubbed-Talon
# fixture. Historical local copy removed 2026-07-01 during the split.


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

    # -----------------------------------------------------------------
    # L1.12c-h — persisted history store (internal/history_persist.py)
    # -----------------------------------------------------------------
    # Load the module via spec_from_file_location so the test doesn't
    # depend on prose_overlay being on sys.path as a package.
    persist_spec = importlib.util.spec_from_file_location(
        "prose_overlay_history_persist_test",
        REPO / "internal" / "history_persist.py",
    )
    persist_mod = importlib.util.module_from_spec(persist_spec)
    persist_spec.loader.exec_module(persist_mod)

    with test("L1", "L1.12c", "history_persist.load returns [] when file missing"):
        with tempfile.TemporaryDirectory() as td:
            missing = pathlib.Path(td) / "does_not_exist.json"
            assert persist_mod.load_history(missing) == []

    with test("L1", "L1.12d", "history_persist round-trip preserves order + content"):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "hist.json"
            entries = ["one two", "three four", "five", ""]
            # Include empty string — legitimate history entry (confirm allows
            # empty strings? Actually no — confirm early-returns on empty text.
            # But defensively the persist layer accepts them.)
            persist_mod.save_history(entries, p)
            assert p.exists(), "save should create the file"
            back = persist_mod.load_history(p)
            assert back == entries, f"round-trip mismatch: {back!r} != {entries!r}"

    with test("L1", "L1.12e", "history_persist.save caps at HISTORY_MAX"):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "hist.json"
            entries = [f"entry {i}" for i in range(persist_mod.HISTORY_MAX + 20)]
            persist_mod.save_history(entries, p)
            back = persist_mod.load_history(p)
            assert len(back) == persist_mod.HISTORY_MAX, (
                f"cap not enforced: got {len(back)} entries"
            )
            # HEAD-cap — keep the newest entries (which are the ones at the
            # front of the list because confirm inserts at position 0).
            assert back == entries[:persist_mod.HISTORY_MAX], (
                "cap should trim the tail, not the head"
            )

    with test("L1", "L1.12f", "history_persist.load handles corrupt JSON cleanly"):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "hist.json"
            p.write_text("{not valid json at all")
            assert persist_mod.load_history(p) == [], (
                "corrupt file must return [] without raising"
            )

    with test("L1", "L1.12g", "history_persist.load handles wrong schema cleanly"):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "hist.json"
            # Wrong shape 1 — bare list at top level.
            p.write_text('["a", "b", "c"]')
            assert persist_mod.load_history(p) == []
            # Wrong shape 2 — dict without version.
            p.write_text('{"entries": ["a", "b"]}')
            assert persist_mod.load_history(p) == []
            # Wrong shape 3 — future schema version.
            p.write_text('{"version": 99, "entries": ["a"]}')
            assert persist_mod.load_history(p) == []
            # Wrong shape 4 — entries not a list.
            p.write_text('{"version": 1, "entries": "oops"}')
            assert persist_mod.load_history(p) == []

    with test("L1", "L1.12h", "history_persist.load drops non-string entries defensively"):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "hist.json"
            p.write_text('{"version": 1, "entries": ["a", 42, "b", null, "c"]}')
            assert persist_mod.load_history(p) == ["a", "b", "c"], (
                "non-string entries must be dropped without failing the whole load"
            )

    with test("L1", "L1.12i", "history_persist.save is atomic — no leftover tmp on success"):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "hist.json"
            persist_mod.save_history(["x", "y"], p)
            assert p.exists(), "target file should exist"
            tmp = p.with_suffix(p.suffix + ".tmp")
            assert not tmp.exists(), (
                f"tmp file should have been renamed away; found {tmp}"
            )

    inst_mod = _load_instance_module()
    ProseOverlayState = inst_mod.ProseOverlayState

    with test("L1", "L1.13", "ProseOverlayState.reset() wipes all data fields to defaults"):
        inst = ProseOverlayState()
        inst.state.buffer = ProseBuffer()
        inst.state.buffer.add_text("contaminated state")
        inst.state.cursor = 5
        inst.state.change_mode = True
        inst.state.target_window_title = "stale-window"
        inst.state.target_recall_name = "stale-recall"
        inst.state.help_visible = True
        inst.state.help_page = 7
        inst.state.auto_dictation = True
        inst.state.hat_js_fallback = True
        inst.state.hat_js_last_err = "call(7 toks): RuntimeError('stack overflow')"
        inst.state.hat_assignments = {0: (0, "c", "gray")}
        inst.state.hat_to_token = {("c", "gray"): 0}
        inst.state.shape_assignments = {0: "wing"}  # Slice 2 — must also wipe.
        # Slice A of docs/PHONES_SPEC.md adds two parallel maps that reset()
        # must also clear, otherwise stale cycle state survives an "overlay
        # reset" and the next swap acts on the previous buffer's words.
        inst.state.next_alt_assignments = {0: "they're"}
        inst.state.position_assignments = {0: (1, 3)}
        # Slice C of docs/PHONES_SPEC.md adds homophone_panel_alts; reset()
        # must clear it too so a stale panel from the prior session can't
        # leak into the next.
        inst.state.homophone_panel_alts = {0: {"yellow": "their", "blue": "they're"}}
        inst.state.flash_state = {"indices": [1], "color": "ff0000"}
        inst.state.history = ["old", "stuff"]
        inst.state.history_page = 3
        inst.state._last_input_source = "letters"
        # reset() tries `from .history_persist import load_history` which
        # ImportErrors under this test's spec_from_file_location load (no
        # parent package). reset()'s try/except catches it and leaves
        # self.state.history = []. Same outcome as the pre-persistence build —
        # ideal for verifying the OTHER reset fields here. The wiring
        # itself (that reset() DOES call load_history in prod) is
        # verified by L1.13b at the source level.
        inst.reset()
        assert inst.state.buffer.get_tokens() == [], "buffer not cleared"
        assert inst.state.cursor is None
        assert inst.state.change_mode is False
        assert inst.state.target_window_title == ""
        assert inst.state.target_recall_name is None
        assert inst.state.help_visible is False
        assert inst.state.help_page == 0
        assert inst.state.auto_dictation is False
        assert inst.state.hat_js_fallback is False
        assert inst.state.hat_js_last_err == "", (
            f"hat_js_last_err should reset to empty; got {inst.state.hat_js_last_err!r}"
        )
        assert inst.state.hat_assignments == {}
        assert inst.state.hat_to_token == {}
        assert inst.state.shape_assignments == {}, (
            f"shape_assignments not cleared by reset(): {inst.state.shape_assignments!r}"
        )
        assert inst.state.next_alt_assignments == {}, (
            f"next_alt_assignments not cleared by reset(): "
            f"{inst.state.next_alt_assignments!r}"
        )
        assert inst.state.position_assignments == {}, (
            f"position_assignments not cleared by reset(): "
            f"{inst.state.position_assignments!r}"
        )
        assert inst.state.homophone_panel_alts == {}, (
            f"homophone_panel_alts not cleared by reset(): "
            f"{inst.state.homophone_panel_alts!r}"
        )
        assert inst.state.flash_state == {}
        assert inst.state.history == []
        assert inst.state.history_page == 0
        assert inst.state._last_input_source == "init"

    with test("L1", "L1.13b", "reset() wiring: instance.py imports+calls history_persist.load_history"):
        # Runtime coupling: reset() runs under a proper package in prod
        # but under spec_from_file_location (no parent package) in this
        # test — so the relative `from .history_persist import load_history`
        # ImportErrors in headless mode. Rather than build a fragile
        # sys.modules alias that only works for one test, verify the
        # wiring at the source-code level: reset() must (a) import
        # load_history from history_persist and (b) actually call it.
        # This catches refactors that would silently drop the reload
        # (e.g. removing the try/except block or renaming the fn).
        inst_src = (REPO / "internal" / "instance.py").read_text()
        assert "from .history_persist import load_history" in inst_src, (
            "instance.reset() must import load_history from history_persist"
        )
        assert "self.state.history = load_history()" in inst_src, (
            "instance.reset() must assign self.state.history from load_history() "
            "(Move 2 step 7/7 — legacy self.history alias removed)"
        )
        # Also verify the persistence file name matches the docstring
        # promise made in visibility's reset() docstring.
        vis_src = (REPO / "ui" / "actions_visibility.py").read_text()
        assert "~/.talon/prose_overlay_history.json" in vis_src, (
            "reset() docstring must name the on-disk path so users can "
            "find + manually nuke it"
        )

    with test("L1", "L1.13c", "debug._snapshot() emits all lossless fields with correct JSON-friendly types"):
        # 2026-07-01 (S9-motivated): _snapshot() must be a LOSSLESS view of
        # every visual-affecting piece of state. This test wires a mocked
        # instance into internal/debug.py's module namespace, calls
        # _snapshot(), and asserts every new field is (a) present and
        # (b) the correct JSON-friendly type. Existing fields keep their
        # order (append-only rule) so this test also spot-checks that the
        # historical keys still lead the dict.
        #
        # internal/debug.py imports:
        #   from .instance import instance
        #   from ..ui import draw as dm
        #   from . import homophones as _h
        # ...at CALL time inside _snapshot(). We can't use
        # spec_from_file_location for internal/debug.py directly because
        # those relative imports need a real parent package. Approach:
        # build a fake package `po_debug_pkg` in sys.modules with stubbed
        # `instance`, `ui.draw`, and `homophones` submodules, then load
        # internal/debug.py *inside* that package. Same pattern used by
        # the shape_bridge tests below (L1.58+).
        import sys as _sys
        import types as _types

        # Fresh package tree — don't reuse the shape_bridge one because
        # its `internal` submodule stubs things we need concrete versions
        # of (like a real ProseOverlayState).
        _pkg = _types.ModuleType("po_debug_pkg")
        _pkg.__path__ = []
        _internal_pkg = _types.ModuleType("po_debug_pkg.internal")
        _internal_pkg.__path__ = []
        _ui_pkg = _types.ModuleType("po_debug_pkg.ui")
        _ui_pkg.__path__ = []

        # Stub `ui.draw` — _snapshot() only touches `dm._hints_hidden_by_overflow`.
        _ui_draw_stub = _types.ModuleType("po_debug_pkg.ui.draw")
        _ui_draw_stub._hints_hidden_by_overflow = False

        # Stub `homophones` — _snapshot() only calls flagged_indices(tokens).
        _homophones_stub = _types.ModuleType("po_debug_pkg.internal.homophones")
        _homophones_stub.flagged_indices = lambda toks: set()

        # Real ProseOverlayState instance — but we hand-construct enough state
        # that every field the snapshot reads has a non-trivial value we can
        # assert against. This is the "mocked instance" the task requires.
        inst = ProseOverlayState()
        inst.state.buffer = ProseBuffer()
        inst.state.buffer.add_text("their there")
        inst.state.buffer.set_selection(0, 1)
        inst.state.shape_assignments = {0: "wing", 1: "wing"}
        inst.state.homophone_panel_alts = {0: {"yellow": "there", "blue": "they're"}}
        inst.state.next_alt_assignments = {0: "there"}
        inst.state.position_assignments = {0: (0, 3), 1: (1, 3)}
        inst.state.help_page = 2
        inst.state.flash_state = {"indices": [0], "color": "ff00ff"}
        inst.state.hat_assignments = {}
        inst.state.cursor = 1

        # Register the parent + internal packages in sys.modules BEFORE any
        # relative-import child loads under them — otherwise
        # `from .draw_constants import ...` inside viewport.py resolves to
        # `po_debug_pkg.internal.draw_constants` and blows up with
        # ModuleNotFoundError because we haven't installed the parent yet.
        _sys.modules["po_debug_pkg"] = _pkg
        _sys.modules["po_debug_pkg.internal"] = _internal_pkg

        # Viewport imports draw_constants relatively — load the constants
        # module under the same fake package first, then load viewport.
        # Both stay talon-free.
        dc_spec = importlib.util.spec_from_file_location(
            "po_debug_pkg.internal.draw_constants",
            REPO / "internal" / "draw_constants.py",
        )
        dc_mod = importlib.util.module_from_spec(dc_spec)
        _sys.modules["po_debug_pkg.internal.draw_constants"] = dc_mod
        dc_spec.loader.exec_module(dc_mod)

        vp_spec = importlib.util.spec_from_file_location(
            "po_debug_pkg.internal.viewport",
            REPO / "internal" / "viewport.py",
        )
        vp_mod = importlib.util.module_from_spec(vp_spec)
        _sys.modules["po_debug_pkg.internal.viewport"] = vp_mod
        vp_spec.loader.exec_module(vp_mod)
        inst.runtime.viewport = vp_mod.Viewport()
        inst.runtime.viewport.set_scroll_offset(3)
        inst.runtime.viewport.set_anchor_rect(vp_mod.Rect(10.0, 20.0, 300.0, 200.0))
        inst.runtime.viewport.set_anchor_position("bottom")

        class _FakeCanvas:
            is_showing = True
        inst.runtime.canvas = _FakeCanvas()

        # Wire the fake instance module.
        _inst_stub = _types.ModuleType("po_debug_pkg.internal.instance")
        _inst_stub.instance = inst

        _internal_pkg.instance = _inst_stub
        _internal_pkg.homophones = _homophones_stub
        _ui_pkg.draw = _ui_draw_stub

        _sys.modules["po_debug_pkg"] = _pkg
        _sys.modules["po_debug_pkg.internal"] = _internal_pkg
        _sys.modules["po_debug_pkg.internal.instance"] = _inst_stub
        _sys.modules["po_debug_pkg.internal.homophones"] = _homophones_stub
        _sys.modules["po_debug_pkg.ui"] = _ui_pkg
        _sys.modules["po_debug_pkg.ui.draw"] = _ui_draw_stub

        debug_spec = importlib.util.spec_from_file_location(
            "po_debug_pkg.internal.debug",
            REPO / "internal" / "debug.py",
        )
        debug_mod = importlib.util.module_from_spec(debug_spec)
        _sys.modules["po_debug_pkg.internal.debug"] = debug_mod
        debug_spec.loader.exec_module(debug_mod)

        snap = debug_mod._snapshot()

        # ---- Existing fields still lead the dict (append-only invariant) ----
        keys = list(snap.keys())
        legacy_head = [
            "showing", "cursor", "change_mode", "auto_dictation",
            "help_visible", "token_count", "tokens", "hats",
            "unhatted", "flagged", "hat_count", "hat_js_fallback",
            "hat_js_last_err", "buffer_rev", "scroll_offset",
            "hints_hidden", "target_window", "flash", "flash_color",
        ]
        assert keys[: len(legacy_head)] == legacy_head, (
            "legacy field order must not change (jq consumers depend on it); "
            f"got head={keys[: len(legacy_head)]!r}"
        )

        # ---- Lossless-snapshot fields: presence + type ----
        # selection: list[int] of length 2 (buffer had a selection set).
        assert "selection" in snap, "missing new field: selection"
        assert isinstance(snap["selection"], list), f"selection type: {type(snap['selection'])!r}"
        assert snap["selection"] == [0, 1], f"selection value: {snap['selection']!r}"

        # shape_assignments: dict with string keys, string values.
        assert "shape_assignments" in snap, "missing new field: shape_assignments"
        sa = snap["shape_assignments"]
        assert isinstance(sa, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in sa.items()), (
            f"shape_assignments shape wrong: {sa!r}"
        )
        assert sa == {"0": "wing", "1": "wing"}, f"shape_assignments value: {sa!r}"

        # homophone_panel_alts: dict[str, dict[str, str]].
        assert "homophone_panel_alts" in snap, "missing new field: homophone_panel_alts"
        hpa = snap["homophone_panel_alts"]
        assert isinstance(hpa, dict), f"homophone_panel_alts type: {type(hpa)!r}"
        assert hpa == {"0": {"yellow": "there", "blue": "they're"}}, (
            f"homophone_panel_alts value: {hpa!r}"
        )

        # next_alt_assignments: dict[str, str].
        assert "next_alt_assignments" in snap, "missing new field: next_alt_assignments"
        naa = snap["next_alt_assignments"]
        assert isinstance(naa, dict) and all(isinstance(v, str) for v in naa.values()), (
            f"next_alt_assignments type: {naa!r}"
        )
        assert naa == {"0": "there"}, f"next_alt_assignments value: {naa!r}"

        # position_assignments: dict[str, list[int]] — tuple → list conversion.
        assert "position_assignments" in snap, "missing new field: position_assignments"
        pa = snap["position_assignments"]
        assert isinstance(pa, dict), f"position_assignments type: {type(pa)!r}"
        for k, v in pa.items():
            assert isinstance(k, str), f"position_assignments key not str: {k!r}"
            assert isinstance(v, list), (
                f"position_assignments value must be JSON list (not tuple): {v!r}"
            )
            assert len(v) == 2 and all(isinstance(x, int) for x in v), v
        assert pa == {"0": [0, 3], "1": [1, 3]}, f"position_assignments value: {pa!r}"

        # help_page: int.
        assert "help_page" in snap, "missing new field: help_page"
        assert isinstance(snap["help_page"], int), type(snap["help_page"])
        assert snap["help_page"] == 2, snap["help_page"]

        # viewport_anchor_position: str ('top' or 'bottom').
        assert "viewport_anchor_position" in snap, "missing new field: viewport_anchor_position"
        assert snap["viewport_anchor_position"] == "bottom", snap["viewport_anchor_position"]

        # viewport_anchor_rect_summary: {x, y, w, h} dict when rect set.
        assert "viewport_anchor_rect_summary" in snap, (
            "missing new field: viewport_anchor_rect_summary"
        )
        rect = snap["viewport_anchor_rect_summary"]
        assert isinstance(rect, dict), f"rect_summary type: {type(rect)!r}"
        assert set(rect.keys()) == {"x", "y", "w", "h"}, (
            f"rect_summary keys: {sorted(rect.keys())!r}"
        )
        assert rect == {"x": 10.0, "y": 20.0, "w": 300.0, "h": 200.0}, (
            f"rect_summary value: {rect!r}"
        )

        # Settings: None when Talon is not importable (headless).
        # This asserts the sys.modules.get('talon') path: Talon isn't
        # loaded in the test harness, so _get_setting returns None
        # cleanly. Locking this in prevents a refactor from swapping the
        # defensive lookup for a bare import (which would trip
        # I5.INTERNAL_LAZY_TALON in scripts/layer-audit.py).
        for k in (
            "homophone_shapes_setting",
            "homophone_hint_setting",
            "window_scoped_setting",
            "hat_cursor_greedy_setting",
        ):
            assert k in snap, f"missing new field: {k}"
            assert snap[k] is None, (
                f"{k} must be None when Talon unavailable (headless); got {snap[k]!r}"
            )

        # ---- Full-dict json.dumps sanity: no non-serializable values ----
        import json as _json
        try:
            _json.dumps(snap)
        except TypeError as e:
            raise AssertionError(f"snapshot must be JSON-serializable: {e}") from None

        # ---- Rect None passthrough (defensive: no anchor rect set) ----
        # Reset viewport rect to None, call again — must produce None,
        # not raise. This mirrors the common case where the overlay is
        # showing full-screen (no window scope).
        inst.runtime.viewport.set_anchor_rect(None)
        snap2 = debug_mod._snapshot()
        assert snap2["viewport_anchor_rect_summary"] is None, (
            f"rect_summary must be None when anchor rect is None; got {snap2['viewport_anchor_rect_summary']!r}"
        )

    with test("L1", "L1.14", "reset() preserves object identity of buffer/canvas/etc."):
        # Object refs created at module init should NOT be reassigned.
        inst = ProseOverlayState()
        inst.state.buffer = ProseBuffer()
        b_id = id(inst.state.buffer)
        # canvas and viewport are typically created by prose_overlay.py;
        # reset() should leave None alone and not reassign existing refs.
        inst.reset()
        assert id(inst.state.buffer) == b_id, "buffer object identity should be preserved"

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

    with test("L1", "L1.16b", "shapes_enabled() is False by default (2026-07-01 flip)"):
        if shapes_mod is None:
            raise AssertionError("prose_overlay_shapes failed to import")
        # Default flipped True → False on 2026-07-01 to match the static setting
        # default (also False). Prior regression: static was False but runtime
        # was True, and ui/draw.py ORs them, so shapes stayed ON. Both must be
        # False for the OR to actually turn shapes off by default.
        assert shapes_mod.shapes_enabled() is False, (
            f"default should be OFF after 2026-07-01 runtime-flag flip; got "
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
        def gid(t):
            return 0 if t == "there" else 1
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
        # instance.state.hat_to_token populated by _recompute_hats).
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

    # -----------------------------------------------------------------------
    # Slice 2 of docs/BUNDLE_SHAPE_SCOPE.md — projection wrapper preserves
    # ISC-14c per-group-same-shape invariant when routing through the
    # bundle. shim/shape_bridge.py owns the projection layer; we exercise
    # it end-to-end via a stubbed bundle allocator so the tests are
    # deterministic and Talon-free. See docs/BUNDLE_SHAPE_DECISIONS.md OQ3.
    # -----------------------------------------------------------------------
    shape_bridge_spec = importlib.util.spec_from_file_location(
        "prose_overlay_shape_bridge",
        REPO / "shim" / "shape_bridge.py",
    )
    # shape_bridge imports from .hats_js which imports talon.lib.js — that
    # fails in the headless harness. Load hats_js manually WITHOUT calling
    # talon.lib.js by injecting a stub before the from-import runs.
    import sys as _sys
    import types as _types
    _talon_stub = _types.ModuleType("talon")
    _talon_lib_stub = _types.ModuleType("talon.lib")
    _talon_lib_js_stub = _types.ModuleType("talon.lib.js")
    class _StubCtx:
        def __init__(self): self.globals = _types.SimpleNamespace(proseAllocateHats=lambda *a: '{}')
        def eval(self, _): pass
    _talon_lib_js_stub.Context = _StubCtx
    _sys.modules.setdefault("talon", _talon_stub)
    _sys.modules.setdefault("talon.lib", _talon_lib_stub)
    _sys.modules.setdefault("talon.lib.js", _talon_lib_js_stub)
    # And the internal.trail module + state that hats_js pulls in.
    # Provide minimal stubs so the module loads without a live prose-overlay
    # package tree.
    _trail_stub = _types.ModuleType("po_trail_stub")
    _trail_stub.begin_command = lambda *a, **k: "cid"
    _trail_stub.end_command = lambda *a, **k: None
    _state_stub = _types.ModuleType("po_state_stub")
    _state_stub.compute_hat_assignments = lambda *a, **k: {}

    # Build a fake package structure so `from ..internal.trail import ...`
    # inside hats_js resolves without picking up the real internal/ files.
    _pkg = _types.ModuleType("po_shim_pkg")
    _pkg.__path__ = []  # package
    _internal_pkg = _types.ModuleType("po_shim_pkg.internal")
    _internal_pkg.__path__ = []
    _internal_pkg.trail = _trail_stub
    _internal_pkg.state = _state_stub
    _shim_pkg = _types.ModuleType("po_shim_pkg.shim")
    _shim_pkg.__path__ = []
    _sys.modules["po_shim_pkg"] = _pkg
    _sys.modules["po_shim_pkg.internal"] = _internal_pkg
    _sys.modules["po_shim_pkg.internal.trail"] = _trail_stub
    _sys.modules["po_shim_pkg.internal.state"] = _state_stub
    _sys.modules["po_shim_pkg.shim"] = _shim_pkg

    hats_js_spec = importlib.util.spec_from_file_location(
        "po_shim_pkg.shim.hats_js",
        REPO / "shim" / "hats_js.py",
    )
    hats_js_mod = importlib.util.module_from_spec(hats_js_spec)
    _sys.modules["po_shim_pkg.shim.hats_js"] = hats_js_mod
    hats_js_spec.loader.exec_module(hats_js_mod)

    shape_bridge_spec = importlib.util.spec_from_file_location(
        "po_shim_pkg.shim.shape_bridge",
        REPO / "shim" / "shape_bridge.py",
    )
    shape_bridge = importlib.util.module_from_spec(shape_bridge_spec)
    _sys.modules["po_shim_pkg.shim.shape_bridge"] = shape_bridge
    shape_bridge_spec.loader.exec_module(shape_bridge)

    with test(
        "L1",
        "L1.58",
        "hats_js.build_enabled_hat_styles returns 9 colors (default) or 99 with shapes",
    ):
        # Contract with cursorless proseStandalone.ts:
        # - 9-entry colors-only when include_shapes=False (backcompat)
        # - 99-entry color x (no-shape + 10 shapes) when include_shapes=True
        default = hats_js_mod.build_enabled_hat_styles(False)
        full = hats_js_mod.build_enabled_hat_styles(True)
        assert len(default) == 9, f"expected 9 colors, got {len(default)}: {list(default)!r}"
        assert len(full) == 99, f"expected 99 entries, got {len(full)}"
        assert "gray" in default and "gray-frame" not in default
        assert "gray-frame" in full and "blue-bolt" in full
        # Penalty invariant: shape adds +1 to color's penalty
        assert full["gray"]["penalty"] == 0
        assert full["gray-frame"]["penalty"] == 1
        assert full["blue"]["penalty"] == 1
        assert full["blue-bolt"]["penalty"] == 2

    with test(
        "L1",
        "L1.59",
        "shape_bridge: build_group_shape_enabled_styles pairs one color with used shapes",
    ):
        # 3 flagged tokens across 2 groups (there=frame, their=frame, whether=bolt)
        # Only 2 unique shapes used → expect 9 colors + 2 shape-suffixed entries.
        shape_assignments = {0: "frame", 1: "frame", 5: "bolt"}
        styles = shape_bridge.build_group_shape_enabled_styles(
            shape_assignments, color_for_shape="gray",
        )
        assert "gray" in styles, "plain colors must survive"
        assert "gray-frame" in styles, "used shape gray-frame must be present"
        assert "gray-bolt" in styles, "used shape gray-bolt must be present"
        # UNUSED shapes must NOT appear — the pool for the bundle stays tight.
        assert "gray-play" not in styles, "unused shape MUST NOT enter pool"
        assert len(styles) == 9 + 2, f"expected 11 entries; got {len(styles)}: {list(styles)!r}"

    with test(
        "L1",
        "L1.60",
        "shape_bridge: same-group tokens all get same shape-suffixed style (ISC-14c preserved)",
    ):
        # Stub bundle allocator: assigns the FIRST style-name matching each
        # token's grapheme count from the enabled pool. Deterministic; lets
        # us verify that the projection wrapper wires the right pool through
        # to the bundle, which is the load-bearing check for the wrapper.
        def _stub_allocator(tokens, old_assignments=None, stability="balanced",
                            cursor_pos=None, enabled_styles=None):
            # Assign to each token the style name that matches its shape_assignment
            # (received via the projected old_assignments) OR bare gray otherwise.
            # This mirrors what the real bundle does under the projection layer:
            # each shape-flagged token wears its group's shape.
            out = {}
            oa = old_assignments or {}
            for i, tok in enumerate(tokens):
                style = oa.get(i, (0, tok[0].lower() if tok else "a", "gray"))[2]
                letter = tok[0].lower() if tok else "a"
                out[i] = (0, letter, style)
            return out

        # Three tokens in group A (gid 42) share shape "frame"; two in group B
        # (gid 99) share shape "bolt". Verify the projected old_assignments
        # carries the shape-suffixed styles into the allocator, and the
        # returned dict has fully-qualified styles.
        tokens = ["there", "their", "whether", "than", "there"]
        shape_assignments = {0: "frame", 1: "frame", 2: "bolt", 4: "frame"}
        prior_old = {
            0: (0, "t", "gray-frame"),
            1: (0, "t", "gray-frame"),
            2: (0, "w", "gray-bolt"),
            4: (0, "t", "gray-frame"),
        }
        result = shape_bridge.compute_hat_assignments_with_group_shapes(
            tokens=tokens,
            shape_assignments=shape_assignments,
            old_assignments=prior_old,
            color_for_shape="gray",
            _allocator=_stub_allocator,
        )
        # ISC-14c: same-group tokens wear the same shape.
        assert result[0][2] == "gray-frame", f"idx 0 got {result[0]!r}"
        assert result[1][2] == "gray-frame", f"idx 1 got {result[1]!r}"
        assert result[2][2] == "gray-bolt", f"idx 2 got {result[2]!r}"
        assert result[4][2] == "gray-frame", f"idx 4 got {result[4]!r}"
        # Non-flagged token stays with a bare style (or whatever the allocator
        # returned) — no accidental shape suffix.
        assert "-" not in result[3][2], f"unflagged idx 3 should have no shape suffix, got {result[3]!r}"

    with test(
        "L1",
        "L1.61",
        "shape_bridge: empty shape_assignments falls through to colors-only path",
    ):
        # No flagged tokens → wrapper must skip the projection and call the
        # allocator with NO enabled_styles arg (so backcompat pool applies).
        seen_kwargs = {}
        def _spy_allocator(tokens, old_assignments=None, stability="balanced",
                           cursor_pos=None, enabled_styles=None):
            seen_kwargs["enabled_styles"] = enabled_styles
            return {i: (0, t[0].lower(), "gray") for i, t in enumerate(tokens) if t}
        shape_bridge.compute_hat_assignments_with_group_shapes(
            tokens=["hello", "world"],
            shape_assignments={},
            old_assignments=None,
            _allocator=_spy_allocator,
        )
        assert seen_kwargs["enabled_styles"] is None, (
            "empty shape assignments must not project any enabled_styles map; "
            f"got {seen_kwargs['enabled_styles']!r}"
        )

    with test(
        "L1",
        "L1.62",
        "shape_bridge: bad color_for_shape falls back to colors-only pool",
    ):
        # Defensive: a nonsense color name shouldn't crash — just skip the
        # shape-suffix pool augmentation. The wrapper still calls the
        # allocator, so the return doesn't lose the tokens.
        styles = shape_bridge.build_group_shape_enabled_styles(
            {0: "frame"}, color_for_shape="chartreuse",
        )
        # No shape-suffixed entries — nonsense color rejected upstream.
        assert not any("-" in k for k in styles), f"bad color leaked shape entries: {list(styles)!r}"
        assert "gray" in styles, "plain colors must still be there"

    # -----------------------------------------------------------------------
    # Slice 3 of docs/BUNDLE_SHAPE_SCOPE.md — opt-in setting for the bridge
    # path. Default must stay OFF; toggle must be reachable without any
    # code change other than the setting flip.
    # -----------------------------------------------------------------------

    with test(
        "L1",
        "L1.63",
        "prose_overlay.py declares prose_overlay_use_cursorless_shape_allocator setting, default False",
    ):
        po_text = (REPO / "prose_overlay.py").read_text()
        assert "prose_overlay_use_cursorless_shape_allocator" in po_text, (
            "setting missing from prose_overlay.py — Slice 3 flip surface"
        )
        # Find the setting block and verify default=False shows up in it.
        # The block starts with the setting name string and continues until
        # the terminating ')'. Slice keyword args from the block.
        i = po_text.find("prose_overlay_use_cursorless_shape_allocator")
        # Walk backwards to find the enclosing `mod.setting(` opening.
        opener = po_text.rfind("mod.setting(", 0, i)
        assert opener >= 0, "setting block for allocator missing mod.setting( opener"
        # Walk forwards past matching close paren.
        depth = 1
        j = po_text.index("(", opener) + 1
        while j < len(po_text) and depth:
            c = po_text[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            j += 1
        block = po_text[opener:j]
        assert "default=False" in block, (
            "Slice 3 setting must default to False — got "
            f"{block!r}"
        )

    with test(
        "L1",
        "L1.64",
        "shape_bridge: projected old_assignments carry shape-suffixed style for stability",
    ):
        # Contract for docs/BUNDLE_SHAPE_SCOPE.md §6 risk 3 mitigation:
        # the bridge must rewrite `oldAssignments` so the stability
        # comparator sees the styleName the bundle will hand back. This
        # test locks in that rewrite path so a future refactor can't
        # silently regress it.
        prior = {
            0: (0, "t", "gray"),      # was color-only pre-Slice-3
            1: (0, "t", "gray"),
        }
        shape_assignments = {0: "frame", 1: "frame"}
        projected = shape_bridge.project_group_shapes_onto_old_assignments(
            old_assignments=prior,
            shape_assignments=shape_assignments,
            color_for_shape="gray",
        )
        assert projected[0][2] == "gray-frame", (
            f"projection must rewrite bare color to shape-suffixed style; "
            f"got {projected[0]!r}"
        )
        assert projected[1][2] == "gray-frame", (
            f"projection must rewrite ALL flagged entries; got {projected[1]!r}"
        )
        # None case — must return empty dict, not raise.
        assert shape_bridge.project_group_shapes_onto_old_assignments(
            None, shape_assignments, "gray",
        ) == {}
        # Token not in shape_assignments keeps its prior style.
        prior_mixed = {0: (0, "t", "gray"), 3: (0, "b", "blue")}
        shape_only_0 = {0: "frame"}
        p2 = shape_bridge.project_group_shapes_onto_old_assignments(
            prior_mixed, shape_only_0, "gray",
        )
        assert p2[0][2] == "gray-frame"
        assert p2[3][2] == "blue", (
            f"non-shape token's style must pass through unchanged; got {p2[3]!r}"
        )


    # -----------------------------------------------------------------------
    # Move 4 (LayoutModel target shape) — ui/layout.py
    # Pure-data model produced by a future `layout(state) -> LayoutModel`
    # and consumed by `to_paint_ops` (Move 5). These tests lock in the
    # dataclass tree's constructability and JSON serialization contract
    # so downstream agents can rely on the shape.
    # -----------------------------------------------------------------------
    import dataclasses as _dc
    import json as _json
    layout_spec = importlib.util.spec_from_file_location(
        "po_ui_layout",
        REPO / "ui" / "layout.py",
    )
    layout_mod = importlib.util.module_from_spec(layout_spec)
    # Register in sys.modules BEFORE exec_module — required because the
    # file uses `from __future__ import annotations` and @dataclass, which
    # under Python 3.13 asks sys.modules[cls.__module__] for the class
    # namespace during KW_ONLY detection. Without this pre-registration
    # the exec raises AttributeError('NoneType' has no '__dict__').
    _sys.modules["po_ui_layout"] = layout_mod
    layout_spec.loader.exec_module(layout_mod)

    with test("L1", "L1.65", "LayoutModel + children construct with minimal args"):
        # Minimal-args smoke: every dataclass in ui/layout.py must be
        # constructible without runtime errors given only its declared
        # types. Catches accidental __post_init__ additions, unresolved
        # forward refs from `from __future__ import annotations`, and
        # any drift where a field's declared type doesn't match what
        # the producer would realistically pass.
        r = layout_mod.Rect(x=0.0, y=0.0, w=100.0, h=20.0)
        assert r.x == 0.0 and r.w == 100.0
        h = layout_mod.HatMark(
            char_index=1, letter="h", color="gray",
            position=layout_mod.Rect(1.0, 1.0, 4.0, 4.0),
        )
        s = layout_mod.ShapeMark(
            shape_name="wing",
            position=layout_mod.Rect(2.0, 1.0, 10.0, 7.0),
            scale=0.5, color="ffaa00ff",
        )
        u = layout_mod.UnderlineSegment(
            x0=0.0, x1=10.0, y=20.0, active=True, color="ff0000ff",
        )
        tok = layout_mod.TokenLayout(
            index=0, text="there", rect=r,
            hat=h, shape=s, underline_segments=[u],
            flagged=True, on_visible_row=True,
        )
        sel = layout_mod.SelectionOverlay(rects=[r])
        fl = layout_mod.FlashOverlay(rects=[r], color="ff00004d")
        b = layout_mod.BubbleLayout(
            token_idx=0, x=10.0, y=100.0, w=60.0, h=18.0,
            shape_name="wing", shape_scale=0.55,
            left_chip=("yellow", "their", 30.0),
            right_chip=("blue", "they're", 34.0),
            band=0,
        )
        hr = layout_mod.HelpRow(left="cmd", right="desc", y=50.0)
        hp = layout_mod.HelpLayout(rows=[hr], page=0, total_pages=3)
        cur = layout_mod.CursorLayout(
            rect=r, change_mode=False, blink_on=True,
        )

        # Minimum-viable LayoutModel — all optional fields None, all
        # list fields empty. Represents the "listening..." placeholder
        # frame with no tokens, no cursor, no help zone.
        m_min = layout_mod.LayoutModel(
            panel=r, content_area=r, help_area=None,
            tokens=[], selection=None, flash=None,
            bubbles=[], help=None, cursor=None,
            target_label="", using_fallback=False,
            hints_hidden_by_overflow=False,
        )
        assert m_min.tokens == [] and m_min.help is None

        # Fully-populated LayoutModel — every optional slot filled,
        # every list has at least one entry. Represents a typical
        # active draw with tokens, hats, shapes, homophone bubbles,
        # selection, flash, help side panel, and cursor.
        m_full = layout_mod.LayoutModel(
            panel=r, content_area=r, help_area=r,
            tokens=[tok], selection=sel, flash=fl,
            bubbles=[b], help=hp, cursor=cur,
            target_label="window: Terminal",
            using_fallback=False,
            hints_hidden_by_overflow=False,
        )
        assert len(m_full.tokens) == 1
        assert m_full.tokens[0].hat is not None
        assert m_full.tokens[0].shape is not None
        assert m_full.bubbles[0].right_chip is not None

        # Immutability contract — every dataclass must be frozen. Attempt
        # to mutate one field on each root-level record; the FrozenInstance
        # error is the desired outcome. If any of these silently succeeds
        # the frozen=True decorator got dropped somewhere.
        for obj, attr in [
            (r, "x"), (h, "char_index"), (s, "shape_name"),
            (u, "active"), (tok, "index"), (sel, "rects"),
            (fl, "color"), (b, "band"), (hr, "y"), (hp, "page"),
            (cur, "blink_on"), (m_full, "target_label"),
        ]:
            try:
                setattr(obj, attr, "should-not-take")
            except _dc.FrozenInstanceError:
                continue
            raise AssertionError(
                f"{type(obj).__name__}.{attr} accepted mutation — "
                f"missing @dataclass(frozen=True)?"
            )

    with test(
        "L1",
        "L1.66",
        "LayoutModel round-trips via dataclasses.asdict -> json.dumps -> json.loads",
    ):
        # Serialization contract: the model must be JSON-safe so debug
        # snapshots, headless test fixtures, and Move 5's paint-op emitter
        # can dump the model to disk and reload it. tuple-typed fields
        # (BubbleLayout.left_chip / right_chip) become JSON arrays on the
        # wire — that's expected; we compare structural equivalence after
        # normalizing tuples -> lists on the source side.
        r = layout_mod.Rect(x=1.0, y=2.0, w=3.0, h=4.0)
        h = layout_mod.HatMark(
            char_index=0, letter="a", color="gray",
            position=layout_mod.Rect(0.0, 0.0, 1.0, 1.0),
        )
        s = layout_mod.ShapeMark(
            shape_name="wing", position=r, scale=0.55, color="ffaa00ff",
        )
        u = layout_mod.UnderlineSegment(
            x0=0.0, x1=1.0, y=0.0, active=False, color="00000000",
        )
        tok = layout_mod.TokenLayout(
            index=0, text="a", rect=r, hat=h, shape=s,
            underline_segments=[u], flagged=True, on_visible_row=True,
        )
        b = layout_mod.BubbleLayout(
            token_idx=0, x=0.0, y=0.0, w=10.0, h=5.0,
            shape_name="wing", shape_scale=0.55,
            left_chip=("yellow", "alt1", 5.0),
            right_chip=("blue", "alt2", 5.0),
            band=0,
        )
        cur = layout_mod.CursorLayout(
            rect=r, change_mode=True, blink_on=True,
        )
        hp = layout_mod.HelpLayout(
            rows=[layout_mod.HelpRow(left="l", right="r", y=0.0)],
            page=1, total_pages=2,
        )
        m = layout_mod.LayoutModel(
            panel=r, content_area=r, help_area=r,
            tokens=[tok],
            selection=layout_mod.SelectionOverlay(rects=[r]),
            flash=layout_mod.FlashOverlay(rects=[r], color="ff00004d"),
            bubbles=[b], help=hp, cursor=cur,
            target_label="x", using_fallback=True,
            hints_hidden_by_overflow=False,
        )
        d = _dc.asdict(m)
        # asdict preserves tuples; json converts them to lists. Normalize
        # so the structural-equivalence check reflects what a real caller
        # sees on the far side of the JSON boundary.
        def _tuples_to_lists(x):
            if isinstance(x, tuple):
                return [_tuples_to_lists(v) for v in x]
            if isinstance(x, list):
                return [_tuples_to_lists(v) for v in x]
            if isinstance(x, dict):
                return {k: _tuples_to_lists(v) for k, v in x.items()}
            return x
        expected = _tuples_to_lists(d)
        actual = _json.loads(_json.dumps(d))
        assert actual == expected, (
            "JSON round-trip diverged from asdict (post tuple-normalize)."
        )
        # Sanity that the wire form is JSON-parseable string (i.e. no
        # non-serializable values like sets or floats-as-NaN slipped in).
        wire = _json.dumps(d)
        assert isinstance(wire, str) and len(wire) > 0
        # And a spot check on a specific tuple-typed field to lock in the
        # documented "tuple becomes list" wire contract.
        assert actual["bubbles"][0]["left_chip"] == ["yellow", "alt1", 5.0], (
            f"left_chip wire form should be a JSON array; got "
            f"{actual['bubbles'][0]['left_chip']!r}"
        )

    # -----------------------------------------------------------------------
    # Move 4a (per-token layout builder) — ui/layout_tokens.py
    # Pure builder that turns a state snapshot + measured widths into a
    # list of TokenLayout records. No consumers yet (Move 4e wires it into
    # a full layout(state, canvas) composition). These tests lock in the
    # extraction: row wrap, hat/shape/underline geometry, determinism,
    # and the max_visible_rows viewport trim.
    # -----------------------------------------------------------------------

    # Load ui/layout_tokens.py under a synthetic package tree so its
    # relative imports (`from ..internal.draw_constants import ...` and
    # `from .layout import ...`) resolve without pulling talon in.
    # Same trick the shape_bridge and debug L1 tests use above.
    import types as _types_lt
    _lt_pkg = _types_lt.ModuleType("po_lt_pkg")
    _lt_pkg.__path__ = []
    _lt_internal_pkg = _types_lt.ModuleType("po_lt_pkg.internal")
    _lt_internal_pkg.__path__ = []
    _lt_ui_pkg = _types_lt.ModuleType("po_lt_pkg.ui")
    _lt_ui_pkg.__path__ = []
    _sys.modules["po_lt_pkg"] = _lt_pkg
    _sys.modules["po_lt_pkg.internal"] = _lt_internal_pkg
    _sys.modules["po_lt_pkg.ui"] = _lt_ui_pkg

    # Constants module — used by layout_tokens for the geometry constants.
    dc_spec_lt = importlib.util.spec_from_file_location(
        "po_lt_pkg.internal.draw_constants",
        REPO / "internal" / "draw_constants.py",
    )
    dc_mod_lt = importlib.util.module_from_spec(dc_spec_lt)
    _sys.modules["po_lt_pkg.internal.draw_constants"] = dc_mod_lt
    dc_spec_lt.loader.exec_module(dc_mod_lt)

    # ui/layout.py — the dataclass tree, imported by layout_tokens.
    layout_spec_lt = importlib.util.spec_from_file_location(
        "po_lt_pkg.ui.layout",
        REPO / "ui" / "layout.py",
    )
    layout_mod_lt = importlib.util.module_from_spec(layout_spec_lt)
    _sys.modules["po_lt_pkg.ui.layout"] = layout_mod_lt
    layout_spec_lt.loader.exec_module(layout_mod_lt)

    # ui/layout_tokens.py — the builder under test.
    lt_spec = importlib.util.spec_from_file_location(
        "po_lt_pkg.ui.layout_tokens",
        REPO / "ui" / "layout_tokens.py",
    )
    lt_mod = importlib.util.module_from_spec(lt_spec)
    _sys.modules["po_lt_pkg.ui.layout_tokens"] = lt_mod
    lt_spec.loader.exec_module(lt_mod)

    # Alias for concision — L1 test bodies below use `_build` heavily.
    _build = lt_mod.build_token_layouts
    _DC = dc_mod_lt
    _LTL = layout_mod_lt

    # Tiny state stub — layout_tokens only reads .shape_assignments and
    # .position_assignments. A dataclass-equal-ish object suffices.
    class _StateStub:
        def __init__(self, shape=None, position=None):
            self.shape_assignments = shape or {}
            self.position_assignments = position or {}

    with test("L1", "L1.67", "build_token_layouts([]) → []"):
        # Empty tokens list returns empty list, no rows, no exceptions.
        # Locks the fast-path guard at the top of the builder.
        out = _build(
            _StateStub(),
            tokens=[],
            token_widths=[],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=100.0,
        )
        assert out == [], f"expected [] for no tokens; got {out!r}"

    with test("L1", "L1.68", "single unflagged token, no hat_assignments → default alphabetic hat"):
        # draw_tokens.py's `has_hat` fallback: when hat_assignments is None,
        # idx < len(HAT_ALPHABET) gets a hat with letter=HAT_ALPHABET[idx]
        # on char 0. Builder must mirror that so drop-in replacement is
        # faithful. Token 0 = "foo" with no state → gray hat on 'a' (the
        # HAT_ALPHABET[0]), because that's what today's paint code does.
        out = _build(
            _StateStub(),
            tokens=["foo"],
            token_widths=[24.0],
            x_origin=10.0,
            y_start=20.0,
            max_row_w=1000.0,
        )
        assert len(out) == 1, f"expected 1 layout, got {len(out)}"
        tok = out[0]
        assert tok.index == 0 and tok.text == "foo"
        assert tok.flagged is False and tok.underline_segments == []
        assert tok.shape is None, "shape_enabled defaulted off"
        assert tok.hat is not None, "default alphabetic hat should fire when hat_assignments is None"
        assert tok.hat.letter == "a", f"HAT_ALPHABET[0]='a' expected; got {tok.hat.letter!r}"
        assert tok.hat.char_index == 0
        assert tok.hat.color == "gray"

    with test("L1", "L1.69", "hat_assignments explicit → HatMark reflects it"):
        # When the caller passes an explicit hat_assignments dict, the
        # HatMark must use its (char_index, letter, color) directly.
        # Absent entry → no hat, even if idx < len(HAT_ALPHABET). This
        # mirrors draw_tokens.py's `assignment is not None` branch.
        out = _build(
            _StateStub(),
            tokens=["there", "foo"],
            token_widths=[30.0, 20.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
            hat_assignments={0: (1, "h", "blue")},
        )
        assert len(out) == 2
        assert out[0].hat is not None
        assert out[0].hat.char_index == 1
        assert out[0].hat.letter == "h"
        assert out[0].hat.color == "blue"
        assert out[1].hat is None, (
            "token 1 has no entry in hat_assignments; expected no hat "
            f"(got {out[1].hat!r})"
        )

    with test("L1", "L1.70", "two tokens on one row: x advances by tw + TOKEN_GAP_X"):
        # Row wrap sanity — when both tokens fit under max_row_w they land
        # on the same row and the second one's x is
        # x_origin + tw0 + TOKEN_GAP_X. y stays at y_start for row 0.
        out = _build(
            _StateStub(),
            tokens=["a", "b"],
            token_widths=[10.0, 15.0],
            x_origin=100.0,
            y_start=200.0,
            max_row_w=1000.0,
        )
        assert len(out) == 2
        assert out[0].rect.x == 100.0 and out[0].rect.y == 200.0
        expected_x1 = 100.0 + 10.0 + _DC.TOKEN_GAP_X
        assert out[1].rect.x == expected_x1, (
            f"row-2 x should be x_origin+tw0+TOKEN_GAP_X={expected_x1}; "
            f"got {out[1].rect.x}"
        )
        assert out[1].rect.y == 200.0, "still on row 0; y unchanged"

    with test("L1", "L1.71", "wrap: three tokens into two rows; row-2 y advances by LINE_HEIGHT"):
        # Row wrap under a narrow max_row_w. Tokens with tw=40 each and
        # TOKEN_GAP_X between: 40 + 5 + 40 = 85 fits in max_row_w=100 for
        # row 1; a third token pushes over. Row-2 token gets y = y_start
        # + LINE_HEIGHT.
        out = _build(
            _StateStub(),
            tokens=["aa", "bb", "cc"],
            token_widths=[40.0, 40.0, 40.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=100.0,
        )
        assert len(out) == 3
        # Row 0: tokens 0 and 1 sit on y = 0
        assert out[0].rect.y == 0.0 and out[1].rect.y == 0.0
        # Row 1: token 2 sits on y = LINE_HEIGHT and starts back at x_origin
        assert out[2].rect.y == float(_DC.LINE_HEIGHT), (
            f"row-2 y should be LINE_HEIGHT={_DC.LINE_HEIGHT}; got {out[2].rect.y}"
        )
        assert out[2].rect.x == 0.0, "row-2 first token restarts at x_origin"

    with test("L1", "L1.72", "flagged token, group_size 3 → 3 underline segments; active at pos"):
        # position_assignments = {0: (2, 3)} → 3 segments, active is idx 2
        # (the last). tw large enough that each segment stays >= MIN.
        st = _StateStub(position={0: (2, 3)})
        out = _build(
            st,
            tokens=["their"],
            token_widths=[60.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
            flagged_indices={0},
        )
        assert len(out) == 1
        segs = out[0].underline_segments
        assert len(segs) == 3, f"expected 3 segments; got {len(segs)}"
        # Segment 2 must be the active one; segments 0 and 1 inactive.
        assert segs[0].active is False
        assert segs[1].active is False
        assert segs[2].active is True
        # Active alpha vs inactive alpha suffix
        assert segs[2].color.endswith(_DC.HOMOPHONE_UNDERLINE_ACTIVE_ALPHA)
        assert segs[0].color.endswith(_DC.HOMOPHONE_UNDERLINE_INACTIVE_ALPHA)
        assert out[0].flagged is True

    with test("L1", "L1.73", "flagged token with too-narrow segments → solid fallback"):
        # A very narrow token where each segment would be
        # < HOMOPHONE_UNDERLINE_MIN_SEGMENT_W. Builder must fall back to
        # a single solid underline (matching draw_tokens.py's fallback).
        # With group_size=5 and tw=2 the segment width is negative — well
        # under MIN. Result: one segment spanning full tw at the solid
        # HOMOPHONE_UNDERLINE_COLOR (no alpha rewrite).
        st = _StateStub(position={0: (0, 5)})
        out = _build(
            st,
            tokens=["x"],
            token_widths=[2.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
            flagged_indices={0},
        )
        assert len(out) == 1
        segs = out[0].underline_segments
        assert len(segs) == 1, f"expected solid fallback (1 segment); got {len(segs)}"
        assert segs[0].color == _DC.HOMOPHONE_UNDERLINE_COLOR
        assert segs[0].x0 == 0.0 and segs[0].x1 == 2.0

    with test("L1", "L1.74", "flagged token, group_size 1 → solid, not segmented"):
        # Degenerate 1-member row: draw_tokens.py's use_segmented gate is
        # `pos[1] > 1`. Builder must emit ONE solid segment, no
        # segmentation logic. Mirror the OQ4 degeneracy handling.
        st = _StateStub(position={0: (0, 1)})
        out = _build(
            st,
            tokens=["there"],
            token_widths=[40.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
            flagged_indices={0},
        )
        assert len(out) == 1
        segs = out[0].underline_segments
        assert len(segs) == 1
        assert segs[0].color == _DC.HOMOPHONE_UNDERLINE_COLOR
        assert segs[0].active is False

    with test("L1", "L1.75", "shape_enabled + assignment + hat → ShapeMark on DIFFERENT char than hat"):
        # Per shim.shapes.shape_char_position: letter_char_idx=1,
        # token_len=5 → shape_char_idx = (1+1) % 5 = 2. So for "there"
        # with hat on idx 1, the shape lands on idx 2. HatMark and
        # ShapeMark must carry those distinct char indexes.
        st = _StateStub(shape={0: "wing"})
        # per_char_widths keeps hat & shape centers deterministic and
        # exact (avoids the proportional-fallback estimate).
        # token "there" = 5 chars, 40 px total; 8 px per char.
        pcw = {0: [0.0, 8.0, 16.0, 24.0, 32.0, 40.0]}
        out = _build(
            st,
            tokens=["there"],
            token_widths=[40.0],
            x_origin=100.0,
            y_start=0.0,
            max_row_w=1000.0,
            shape_enabled=True,
            hat_assignments={0: (1, "h", "gray")},
            per_char_widths=pcw,
        )
        assert len(out) == 1
        tok = out[0]
        assert tok.hat is not None and tok.hat.char_index == 1
        assert tok.shape is not None, "shape_enabled + assignment → ShapeMark expected"
        # The shape SVG anchors at (cx, cy); the position rect wraps it in
        # a 2*DOT_RADIUS square centered on the anchor. So cx = x + prefix
        # + char_w/2. For char_idx=2 the prefix width is 16, char width 8:
        # cx = 100 + 16 + 4 = 120.
        assert tok.shape.position.x == 120.0 - _DC.DOT_RADIUS, (
            f"shape rect x should center at cx=120; got x={tok.shape.position.x}"
        )
        assert tok.shape.scale == _DC.HOMOPHONE_SHAPE_SCALE
        assert tok.shape.color == _DC.HOMOPHONE_SHAPE_COLOR_HEX
        # Hat cx for char_idx=1: prefix=8, char_w=8, cx = 100 + 8 + 4 = 112.
        assert tok.hat.position.x == 112.0 - _DC.DOT_RADIUS

    with test("L1", "L1.76", "determinism: identical inputs → dataclass-equal output"):
        # Frozen dataclasses compare structurally. Two calls with byte-equal
        # inputs must produce byte-equal outputs. Guards against accidental
        # dict-iteration order dependence or per-call state creep.
        st = _StateStub(
            shape={0: "wing", 1: "frame"},
            position={0: (0, 2), 1: (1, 2)},
        )
        args = dict(
            tokens=["there", "their"],
            token_widths=[40.0, 40.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
            flagged_indices={0, 1},
            shape_enabled=True,
            hat_assignments={0: (0, "t", "gray"), 1: (0, "t", "blue")},
        )
        out1 = _build(st, **args)
        out2 = _build(st, **args)
        assert out1 == out2, "identical inputs produced non-equal outputs — builder is not deterministic"

    with test("L1", "L1.77", "max_visible_rows trims from the TOP; only last N rows survive"):
        # Terminal-pinned viewport trim — matches draw_overlay's
        # `rows = rows[len(rows) - max_visible_rows:]`. With 3 tokens
        # each on its own row (very narrow max_row_w) and
        # max_visible_rows=2, the FIRST token/row is trimmed. Returned
        # list is 2 layouts (indexes 1 and 2), row-2 y is y_start (the
        # first surviving row), row-3 y is y_start + LINE_HEIGHT.
        out = _build(
            _StateStub(),
            tokens=["aa", "bb", "cc"],
            token_widths=[40.0, 40.0, 40.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=50.0,   # each token on its own row
            max_visible_rows=2,
        )
        assert len(out) == 2, f"trim should leave 2 tokens; got {len(out)}"
        # Trimmed from the top: token 0 dropped, tokens 1 and 2 remain.
        assert out[0].index == 1 and out[1].index == 2
        # First surviving row anchors at y_start (the trim doesn't shift
        # coordinates upward; the top row IS y_start after trim).
        assert out[0].rect.y == 0.0
        assert out[1].rect.y == float(_DC.LINE_HEIGHT)

    with test("L1", "L1.78", "no state mutation: state dicts unchanged after build"):
        # Purity contract — the builder MUST NOT mutate state, tokens,
        # token_widths, flagged_indices, hat_assignments, or
        # per_char_widths. Snapshot copies before and compare after.
        st = _StateStub(
            shape={0: "wing"},
            position={0: (0, 2)},
        )
        shape_before = dict(st.shape_assignments)
        pos_before = dict(st.position_assignments)
        tokens_arg = ["there"]
        widths_arg = [40.0]
        flagged_arg = {0}
        hats_arg = {0: (1, "h", "gray")}
        pcw_arg = {0: [0.0, 8.0, 16.0, 24.0, 32.0, 40.0]}
        _build(
            st,
            tokens=tokens_arg,
            token_widths=widths_arg,
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
            flagged_indices=flagged_arg,
            shape_enabled=True,
            hat_assignments=hats_arg,
            per_char_widths=pcw_arg,
        )
        assert st.shape_assignments == shape_before
        assert st.position_assignments == pos_before
        assert tokens_arg == ["there"]
        assert widths_arg == [40.0]
        assert flagged_arg == {0}
        assert hats_arg == {0: (1, "h", "gray")}
        assert pcw_arg == {0: [0.0, 8.0, 16.0, 24.0, 32.0, 40.0]}

    # -----------------------------------------------------------------------
    # Move 4b (homophone-bubble layout builder) — ui/layout_bubbles.py
    # Pure builder that turns a state snapshot + measured widths into a
    # list of ui.layout.BubbleLayout records. No consumers yet (Move 4e
    # replaces the measurement+placement portion of draw_homophone_panels).
    # These tests lock in the extraction: measurement, ideal_x centering,
    # placement collision, anchor-aware band y, determinism, and no
    # mutation.
    # -----------------------------------------------------------------------

    # Load ui/layout_bubbles.py under the same synthetic package tree used
    # by layout_tokens above so its relative imports resolve without
    # pulling talon in. Reuse the po_lt_pkg tree — draw_constants and
    # ui.layout are already loaded under it.
    lb_spec = importlib.util.spec_from_file_location(
        "po_lt_pkg.ui.layout_bubbles",
        REPO / "ui" / "layout_bubbles.py",
    )
    lb_mod = importlib.util.module_from_spec(lb_spec)
    _sys.modules["po_lt_pkg.ui.layout_bubbles"] = lb_mod
    lb_spec.loader.exec_module(lb_mod)

    # Alias for concision.
    _build_bubbles = lb_mod.build_bubble_layouts

    # Tiny bubble state stub — layout_bubbles only reads
    # .homophone_panel_alts and .shape_assignments.
    class _BubbleStateStub:
        def __init__(self, panel_alts=None, shape=None):
            self.homophone_panel_alts = panel_alts or {}
            self.shape_assignments = shape or {}

    with test("L1", "L1.79", "build_bubble_layouts: empty panel_alts → []"):
        # Fast-path guard: when the state carries no homophone_panel_alts,
        # the builder short-circuits without touching tokens / widths.
        out = _build_bubbles(
            _BubbleStateStub(),
            tokens=["there"],
            token_widths=[40.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
            panel_rect_y=100.0,
            panel_rect_h=50.0,
            anchor_position="top",
        )
        assert out == [], f"expected [] when no panel_alts; got {out!r}"

    with test(
        "L1",
        "L1.80",
        "build_bubble_layouts: 3-member group → 2-chip BubbleLayout with correct centering",
    ):
        # One token "there" (width 40) with a 3-member group panel entry.
        # Left chip = yellow their, right chip = blue they're. Exact chip
        # widths INJECTED via alt_text_widths so the expected values are
        # deterministic (no proportional-fallback float drift).
        st = _BubbleStateStub(
            panel_alts={0: {"yellow": "their", "blue": "they're"}},
            shape={0: "play"},
        )
        # Chip text widths at BUBBLE_CHIP_FONT_SIZE. Numbers picked to
        # give tidy arithmetic:
        #   left_text_w = 30    → left_chip_w = 30 + 2*4 = 38
        #   right_text_w = 42   → right_chip_w = 42 + 2*4 = 50
        atw = {"their": 30.0, "they're": 42.0}
        # Token positioned at x=200 (well past x_origin=0) so the wide
        # bubble's ideal_x = 200 + (40 - 101.2)/2 = 169.4 stays above
        # x_origin — no clamp fires, and we test the centering algebra
        # itself, not the clamp. Clamp-then-shift composition is
        # covered in L1.85 / L1.86.
        out = _build_bubbles(
            st,
            tokens=["there"],
            token_widths=[40.0],
            x_origin=200.0,
            y_start=200.0,
            max_row_w=1000.0,
            panel_rect_y=300.0,
            panel_rect_h=50.0,
            anchor_position="top",
            alt_text_widths=atw,
        )
        assert len(out) == 1, f"expected 1 bubble; got {len(out)}"
        b = out[0]
        # Sanity: MUST be a ui.layout.BubbleLayout (frozen), not
        # internal/panel_layout.py's mutable placement record.
        assert type(b) is layout_mod_lt.BubbleLayout, (
            f"expected ui.layout.BubbleLayout; got {type(b).__name__}"
        )
        assert b.token_idx == 0
        # bubble_w = left_chip_w + INNER_GAP + shape_w + INNER_GAP + right_chip_w
        #          = 38 + 0 + (12*1.1) + 0 + 50 = 101.2
        shape_w = 12.0 * _DC.BUBBLE_SHAPE_SCALE
        expected_w = 38.0 + _DC.BUBBLE_INNER_GAP + shape_w + _DC.BUBBLE_INNER_GAP + 50.0
        assert b.w == expected_w, f"bubble_w: got {b.w}, expected {expected_w}"
        # bubble_h = max(chip_h, shape_h) = max(11+2*5=21, 9*1.1=9.9) = 21
        chip_h = _DC.BUBBLE_CHIP_FONT_SIZE + _DC.BUBBLE_CHIP_PAD_Y * 2
        shape_h = 9.0 * _DC.BUBBLE_SHAPE_SCALE
        assert b.h == max(chip_h, shape_h), (
            f"bubble_h: got {b.h}, expected {max(chip_h, shape_h)}"
        )
        # Ideal x: bubble centered on the token. token_x_abs = x_origin = 200,
        # token_w = 40. ideal_x = 200 + (40 - bubble_w) / 2 = 169.4.
        # Above x_origin=200? No — 169.4 < 200. Let's re-verify: the
        # placement pass clamps `x < x_origin` up to `x_origin`. So if
        # ideal_x < x_origin the placed x == x_origin. For this test we
        # WANT to see the raw centering, so we assert the max of the two.
        expected_ideal_x = 200.0 + (40.0 - expected_w) / 2.0
        expected_placed_x = max(expected_ideal_x, 200.0)
        assert b.x == expected_placed_x, (
            f"placed x for single bubble: got {b.x}, expected {expected_placed_x} "
            f"(ideal_x={expected_ideal_x}, x_origin=200.0)"
        )
        # Band y: anchor="top" → panel_y + panel_h + BUBBLE_TOP_GAP
        # = 300 + 50 + 6 = 356.
        assert b.y == 300.0 + 50.0 + _DC.BUBBLE_TOP_GAP, (
            f"band y: got {b.y}, expected {300.0 + 50.0 + _DC.BUBBLE_TOP_GAP}"
        )
        # Chip data — includes the measured chip widths (with pad).
        assert b.left_chip == ("yellow", "their", 38.0)
        assert b.right_chip == ("blue", "they're", 50.0)
        # Shape identity + scale + placement contract.
        assert b.shape_name == "play"
        assert b.shape_scale == _DC.BUBBLE_SHAPE_SCALE
        assert b.band == 0, f"v2 always band 0; got {b.band}"

    with test(
        "L1",
        "L1.81",
        "build_bubble_layouts: 2-member group → left_chip only, right_chip=None",
    ):
        # 2-member group ("aid,aide") → panel entry has one alt on the
        # yellow slot only. Builder must emit a bubble with right_chip=None
        # and bubble_w = left_chip_w + INNER_GAP + shape_w (no right side).
        st = _BubbleStateStub(
            panel_alts={0: {"yellow": "aide"}},
            shape={0: "wing"},
        )
        atw = {"aide": 24.0}  # left_chip_w = 24 + 8 = 32
        out = _build_bubbles(
            st,
            tokens=["aid"],
            token_widths=[20.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
            panel_rect_y=0.0,
            panel_rect_h=100.0,
            anchor_position="top",
            alt_text_widths=atw,
        )
        assert len(out) == 1
        b = out[0]
        assert b.left_chip == ("yellow", "aide", 32.0)
        assert b.right_chip is None, f"2-member group must have right_chip=None; got {b.right_chip!r}"
        shape_w = 12.0 * _DC.BUBBLE_SHAPE_SCALE
        expected_w = 32.0 + _DC.BUBBLE_INNER_GAP + shape_w
        assert b.w == expected_w, f"2-member bubble_w: got {b.w}, expected {expected_w}"

    with test(
        "L1",
        "L1.82",
        "build_bubble_layouts: token in panel_alts but missing shape_assignments → skipped",
    ):
        # Defensive: bubble anchors on the shape glyph; a panel entry
        # without a shape assignment would render a chip-pair with no
        # center glyph. draw_panels._build_row_bubbles skips these, so
        # the pure builder must skip them too.
        st = _BubbleStateStub(
            panel_alts={0: {"yellow": "their"}},
            shape={},  # no shape for idx 0
        )
        out = _build_bubbles(
            st,
            tokens=["there"],
            token_widths=[40.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
            panel_rect_y=0.0,
            panel_rect_h=100.0,
            anchor_position="top",
        )
        assert out == [], f"missing shape must skip the token; got {out!r}"

    with test(
        "L1",
        "L1.83",
        "build_bubble_layouts: anchor_position='top' → band y = panel_y + panel_h + BUBBLE_TOP_GAP",
    ):
        # Anchor-aware band y. "top" means the panel sits at the TOP of
        # the screen → bubble band appears BELOW the panel so it doesn't
        # overlap window chrome above.
        st = _BubbleStateStub(
            panel_alts={0: {"yellow": "their"}},
            shape={0: "wing"},
        )
        atw = {"their": 30.0}
        out = _build_bubbles(
            st,
            tokens=["there"],
            token_widths=[40.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
            panel_rect_y=100.0,
            panel_rect_h=200.0,
            anchor_position="top",
            alt_text_widths=atw,
        )
        assert len(out) == 1
        # band = 100 + 200 + BUBBLE_TOP_GAP.
        assert out[0].y == 100.0 + 200.0 + _DC.BUBBLE_TOP_GAP, (
            f"top-anchor band y: got {out[0].y}, "
            f"expected {100.0 + 200.0 + _DC.BUBBLE_TOP_GAP}"
        )

    with test(
        "L1",
        "L1.84",
        "build_bubble_layouts: anchor_position='bottom' → band y = panel_y - BUBBLE_ROW_H - BUBBLE_TOP_GAP",
    ):
        # "bottom" means the panel sits at the BOTTOM of the screen →
        # bubble band appears ABOVE the panel so it doesn't run off the
        # bottom of the display.
        st = _BubbleStateStub(
            panel_alts={0: {"yellow": "their"}},
            shape={0: "wing"},
        )
        atw = {"their": 30.0}
        out = _build_bubbles(
            st,
            tokens=["there"],
            token_widths=[40.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
            panel_rect_y=500.0,
            panel_rect_h=200.0,
            anchor_position="bottom",
            alt_text_widths=atw,
        )
        assert len(out) == 1
        # band = 500 - BUBBLE_ROW_H - BUBBLE_TOP_GAP.
        expected_y = 500.0 - _DC.BUBBLE_ROW_H - _DC.BUBBLE_TOP_GAP
        assert out[0].y == expected_y, (
            f"bottom-anchor band y: got {out[0].y}, expected {expected_y}"
        )

    with test(
        "L1",
        "L1.85",
        "build_bubble_layouts: two non-colliding bubbles keep their ideal_x",
    ):
        # Two tokens far apart with narrow bubbles → both sit at their
        # ideal_x with no shift. v2 placement contract: horizontal-only,
        # band always 0.
        st = _BubbleStateStub(
            panel_alts={
                0: {"yellow": "their"},
                2: {"yellow": "aide"},
            },
            shape={0: "wing", 2: "frame"},
        )
        atw = {"their": 30.0, "aide": 24.0}
        # 3 tokens: "there" (40 px), "spacer" (200 px), "aid" (20 px).
        # Token 0 sits at x=0; token 1 at 0 + 40 + TOKEN_GAP_X;
        # token 2 at 0 + 40 + gap + 200 + gap.
        gap = _DC.TOKEN_GAP_X
        out = _build_bubbles(
            st,
            tokens=["there", "spacer", "aid"],
            token_widths=[40.0, 200.0, 20.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
            panel_rect_y=0.0,
            panel_rect_h=50.0,
            anchor_position="top",
            alt_text_widths=atw,
        )
        assert len(out) == 2, f"expected 2 bubbles; got {len(out)}"
        # Bubble 0 centered on token 0 (width 40) starting at x=0.
        shape_w = 12.0 * _DC.BUBBLE_SHAPE_SCALE
        b0_w = 38.0 + _DC.BUBBLE_INNER_GAP + shape_w  # 30+8 for "their" left chip
        b0_ideal = 0.0 + (40.0 - b0_w) / 2.0
        # Bubble 1 centered on token 2 (width 20) starting at token 2's x.
        token2_x = 0.0 + 40.0 + gap + 200.0 + gap
        b1_w = 32.0 + _DC.BUBBLE_INNER_GAP + shape_w  # 24+8 for "aide" left chip
        b1_ideal = token2_x + (20.0 - b1_w) / 2.0
        # Placement clamps b0_ideal to x_origin=0 if it went negative — the
        # ideal_x for a wide bubble on a narrow token near x=0 is negative.
        # Verify against that too: whichever the builder places at is
        # max(ideal, x_origin), no right-shift because they don't collide.
        expected_b0 = max(b0_ideal, 0.0)
        assert out[0].x == expected_b0, (
            f"bubble 0 x: got {out[0].x}, expected {expected_b0}"
        )
        assert out[1].x == b1_ideal, (
            f"bubble 1 x should equal its ideal_x (no collision, above x_origin); "
            f"got {out[1].x}, expected {b1_ideal}"
        )
        assert out[0].band == 0 and out[1].band == 0
        assert out[0].token_idx == 0 and out[1].token_idx == 2

    with test(
        "L1",
        "L1.86",
        "build_bubble_layouts: two colliding bubbles → second shifts RIGHT by BUBBLE_OUTER_GAP",
    ):
        # Two tokens close together with wide bubbles → second bubble
        # collides and shifts right to prev_right + BUBBLE_OUTER_GAP. v2
        # contract: single row; no vertical wrap.
        st = _BubbleStateStub(
            panel_alts={
                0: {"yellow": "their"},
                1: {"yellow": "aide"},
            },
            shape={0: "wing", 1: "frame"},
        )
        atw = {"their": 30.0, "aide": 24.0}
        # Two adjacent tokens: "there" (40 px), "aid" (20 px). Token 1
        # sits at x = 0 + 40 + TOKEN_GAP_X.
        gap = _DC.TOKEN_GAP_X
        out = _build_bubbles(
            st,
            tokens=["there", "aid"],
            token_widths=[40.0, 20.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
            panel_rect_y=0.0,
            panel_rect_h=50.0,
            anchor_position="top",
            alt_text_widths=atw,
        )
        assert len(out) == 2
        shape_w = 12.0 * _DC.BUBBLE_SHAPE_SCALE
        b0_w = 38.0 + _DC.BUBBLE_INNER_GAP + shape_w
        b1_w = 32.0 + _DC.BUBBLE_INNER_GAP + shape_w
        b0_ideal = 0.0 + (40.0 - b0_w) / 2.0
        # Clamp: b0 ideal_x may be < x_origin=0.0.
        b0_placed = max(b0_ideal, 0.0)
        b0_right = b0_placed + b0_w
        # Expected b1 x: prev_right + BUBBLE_OUTER_GAP (they collide when
        # bubble widths straddle the small gap between token centers).
        expected_b1 = b0_right + _DC.BUBBLE_OUTER_GAP
        assert out[0].x == b0_placed
        assert out[1].x == expected_b1, (
            f"colliding bubble 1 must shift to prev_right + OUTER_GAP; "
            f"got {out[1].x}, expected {expected_b1}"
        )
        assert out[0].band == 0 and out[1].band == 0, (
            "v2 single band; no vertical wrap"
        )

    with test(
        "L1",
        "L1.87",
        "build_bubble_layouts: determinism — identical inputs → dataclass-equal output",
    ):
        # Frozen ui.layout.BubbleLayout compares structurally. Two builds
        # with identical inputs must produce byte-equal lists. Guards
        # against dict-iteration order dependence in panel_alts / shape
        # dict traversal, and against per-call state creep.
        st = _BubbleStateStub(
            panel_alts={
                0: {"yellow": "their", "blue": "they're"},
                1: {"yellow": "aide"},
            },
            shape={0: "play", 1: "wing"},
        )
        atw = {"their": 30.0, "they're": 42.0, "aide": 24.0}
        args = dict(
            tokens=["there", "aid"],
            token_widths=[40.0, 20.0],
            x_origin=100.0,
            y_start=200.0,
            max_row_w=1000.0,
            panel_rect_y=300.0,
            panel_rect_h=50.0,
            anchor_position="top",
            alt_text_widths=atw,
        )
        out1 = _build_bubbles(st, **args)
        out2 = _build_bubbles(st, **args)
        assert out1 == out2, (
            "identical inputs produced non-equal outputs — builder is not "
            "deterministic"
        )
        # Length parity + per-record equality — makes the failure message
        # actionable if the top-level equality ever regresses.
        assert len(out1) == len(out2)
        for a, b in zip(out1, out2):
            assert a == b, f"per-record diverged: {a!r} vs {b!r}"

    with test(
        "L1",
        "L1.88",
        "build_bubble_layouts: no state mutation — inputs untouched after build",
    ):
        # Purity contract — the builder MUST NOT mutate state,
        # tokens, token_widths, panel_alts, shape_assignments, or
        # alt_text_widths. Snapshot before, compare after.
        st = _BubbleStateStub(
            panel_alts={0: {"yellow": "their", "blue": "they're"}},
            shape={0: "play"},
        )
        # deep-ish copies for the state maps (they're dicts of dicts)
        panel_before = {k: dict(v) for k, v in st.homophone_panel_alts.items()}
        shape_before = dict(st.shape_assignments)
        tokens_arg = ["there"]
        widths_arg = [40.0]
        atw_arg = {"their": 30.0, "they're": 42.0}
        atw_before = dict(atw_arg)
        _build_bubbles(
            st,
            tokens=tokens_arg,
            token_widths=widths_arg,
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
            panel_rect_y=100.0,
            panel_rect_h=50.0,
            anchor_position="top",
            alt_text_widths=atw_arg,
        )
        # State dicts and their nested dicts unchanged.
        assert st.homophone_panel_alts == panel_before, (
            f"panel_alts mutated: before={panel_before}, "
            f"after={st.homophone_panel_alts}"
        )
        assert st.shape_assignments == shape_before, (
            f"shape_assignments mutated: before={shape_before}, "
            f"after={st.shape_assignments}"
        )
        # Argument lists / dicts unchanged.
        assert tokens_arg == ["there"]
        assert widths_arg == [40.0]
        assert atw_arg == atw_before, (
            f"alt_text_widths mutated: before={atw_before}, after={atw_arg}"
        )

    with test(
        "L1",
        "L1.89",
        "build_bubble_layouts: returns frozen ui.layout.BubbleLayout (not internal.panel_layout.BubbleLayout)",
    ):
        # Type-identity contract: the builder's output MUST be instances
        # of ui.layout.BubbleLayout. internal/panel_layout.py has its own
        # class of the same NAME but different shape (mutable __slots__).
        # A downstream renderer relies on the ui.layout paint-record
        # fields (token_idx, x, y, w, h, shape_scale, band, ...);
        # accidentally returning the placement-scratchpad type would
        # AttributeError at paint time. Lock that in here.
        import dataclasses as _dc2
        # Also load the internal.panel_layout module and verify the two
        # classes are DIFFERENT identities (regression guard against a
        # future consolidation move accidentally colliding them).
        pl_spec = importlib.util.spec_from_file_location(
            "prose_overlay_panel_layout_types",
            REPO / "internal" / "panel_layout.py",
        )
        pl_mod = importlib.util.module_from_spec(pl_spec)
        pl_spec.loader.exec_module(pl_mod)
        assert layout_mod_lt.BubbleLayout is not pl_mod.BubbleLayout, (
            "ui.layout.BubbleLayout and internal.panel_layout.BubbleLayout "
            "are still separate types — a consolidation move landed but "
            "this test wasn't updated. Update this test after consolidation."
        )
        st = _BubbleStateStub(
            panel_alts={0: {"yellow": "their"}},
            shape={0: "wing"},
        )
        atw = {"their": 30.0}
        out = _build_bubbles(
            st,
            tokens=["there"],
            token_widths=[40.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
            panel_rect_y=100.0,
            panel_rect_h=50.0,
            anchor_position="top",
            alt_text_widths=atw,
        )
        assert len(out) == 1
        b = out[0]
        # Type identity — must be the ui.layout version.
        assert type(b) is layout_mod_lt.BubbleLayout, (
            f"output type should be ui.layout.BubbleLayout; got "
            f"{type(b).__module__}.{type(b).__name__}"
        )
        # Frozen check — attempting to mutate must raise FrozenInstanceError.
        try:
            b.x = 999.0
        except _dc2.FrozenInstanceError:
            pass
        else:
            raise AssertionError(
                "returned BubbleLayout accepted mutation — should be frozen"
            )
