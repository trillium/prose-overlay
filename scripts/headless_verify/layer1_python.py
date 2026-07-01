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

    # -----------------------------------------------------------------------
    # Move 4c (selection + flash overlay builders) — ui/layout_overlays.py
    # Two pure builders that turn a state snapshot + measured widths into
    # SelectionOverlay | None and FlashOverlay | None. No consumers yet
    # (Move 4e wires draw_overlay onto them). Tests lock in the extraction:
    # no-selection/no-flash short-circuits, per-token highlight geometry,
    # multi-row spans, viewport trim, alpha rewrite, determinism, no
    # mutation, and frozen type identity.
    # -----------------------------------------------------------------------

    # Load ui/layout_overlays.py under the same synthetic package tree used
    # by layout_tokens / layout_bubbles above. draw_constants and ui.layout
    # are already loaded under po_lt_pkg.
    lo_spec = importlib.util.spec_from_file_location(
        "po_lt_pkg.ui.layout_overlays",
        REPO / "ui" / "layout_overlays.py",
    )
    lo_mod = importlib.util.module_from_spec(lo_spec)
    _sys.modules["po_lt_pkg.ui.layout_overlays"] = lo_mod
    lo_spec.loader.exec_module(lo_mod)

    # Aliases for concision.
    _build_selection = lo_mod.build_selection_overlay
    _build_flash = lo_mod.build_flash_overlay

    # Tiny buffer stub — layout_overlays only calls buffer.get_selection().
    # State stub exposes .buffer (with get_selection) and .flash_state.
    class _BufferStub:
        def __init__(self, sel):
            self._sel = sel

        def get_selection(self):
            return self._sel

    class _OverlayStateStub:
        def __init__(self, selection=None, flash_state=None):
            self.buffer = _BufferStub(selection)
            self.flash_state = flash_state or {}

    # Shared highlight-rect geometry helper for the tests. Mirrors
    # ui/layout_overlays.py:_highlight_rect exactly so the test expectations
    # don't drift from the implementation constant.
    def _expected_hl_rect(x, y_base, tw):
        hl_pad_x = 2
        hl_y_top = y_base + (_DC.DOT_RADIUS * 2) + _DC.DOT_GAP_Y
        return (
            x - hl_pad_x,
            hl_y_top,
            tw + hl_pad_x * 2,
            _DC.TOKEN_FONT_SIZE + 2,
        )

    with test(
        "L1",
        "L1.90",
        "build_selection_overlay: no selection → None",
    ):
        # buffer.get_selection() returns None → builder short-circuits.
        out = _build_selection(
            _OverlayStateStub(selection=None),
            tokens=["there"],
            token_widths=[40.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        assert out is None, f"expected None when no selection; got {out!r}"

    with test(
        "L1",
        "L1.91",
        "build_selection_overlay: single-token span → one rect at exact geometry",
    ):
        # Selection = (0, 0) inclusive → one rect covering token 0.
        # Rect geometry mirrors ui/draw_tokens.py's highlight rect exactly:
        # (x - 2, y_base + (DOT_RADIUS*2) + DOT_GAP_Y, tw + 4, TOKEN_FONT_SIZE + 2)
        out = _build_selection(
            _OverlayStateStub(selection=(0, 0)),
            tokens=["there"],
            token_widths=[40.0],
            x_origin=100.0,
            y_start=200.0,
            max_row_w=1000.0,
        )
        assert out is not None, "expected SelectionOverlay; got None"
        assert type(out) is layout_mod_lt.SelectionOverlay
        assert len(out.rects) == 1
        r = out.rects[0]
        ex_x, ex_y, ex_w, ex_h = _expected_hl_rect(100.0, 200.0, 40.0)
        assert r.x == ex_x and r.y == ex_y, (
            f"rect origin: got ({r.x}, {r.y}), expected ({ex_x}, {ex_y})"
        )
        assert r.w == ex_w and r.h == ex_h, (
            f"rect size: got ({r.w}, {r.h}), expected ({ex_w}, {ex_h})"
        )

    with test(
        "L1",
        "L1.92",
        "build_selection_overlay: multi-token inclusive span → one rect per selected token",
    ):
        # Selection = (0, 2) inclusive covers tokens 0, 1, 2 on the same row.
        # Second rect x = 100 + tw0 + TOKEN_GAP_X = 100 + 10 + 5 = 115.
        # Third rect x = 115 + tw1 + TOKEN_GAP_X = 115 + 15 + 5 = 135.
        out = _build_selection(
            _OverlayStateStub(selection=(0, 2)),
            tokens=["a", "bb", "ccc"],
            token_widths=[10.0, 15.0, 20.0],
            x_origin=100.0,
            y_start=200.0,
            max_row_w=1000.0,
        )
        assert out is not None
        assert len(out.rects) == 3, f"expected 3 rects; got {len(out.rects)}"
        # Verify row order + rect x progression.
        expected_xs = [100.0, 115.0, 135.0]
        expected_tws = [10.0, 15.0, 20.0]
        for i, (want_x, want_tw) in enumerate(zip(expected_xs, expected_tws)):
            ex_x, ex_y, ex_w, ex_h = _expected_hl_rect(want_x, 200.0, want_tw)
            r = out.rects[i]
            assert r.x == ex_x, f"rect[{i}] x: got {r.x}, expected {ex_x}"
            assert r.w == ex_w, f"rect[{i}] w: got {r.w}, expected {ex_w}"
            assert r.y == ex_y, f"rect[{i}] y: got {r.y}, expected {ex_y}"

    with test(
        "L1",
        "L1.93",
        "build_selection_overlay: multi-row span → rects on both rows at correct y",
    ):
        # tw=40 each, TOKEN_GAP_X=5. Row width limit 100:
        #   row 0: 40 + 5 + 40 = 85 fits; 3rd token 40 more pushes over.
        # Row 0 has tokens 0, 1 at y=0. Row 1 has token 2 at y=LINE_HEIGHT.
        # Selection (0, 2) → one rect per token; token 2 lands on row 1.
        out = _build_selection(
            _OverlayStateStub(selection=(0, 2)),
            tokens=["aa", "bb", "cc"],
            token_widths=[40.0, 40.0, 40.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=100.0,
        )
        assert out is not None
        assert len(out.rects) == 3
        # Row 0 rects at y_base=0; row 1 rect at y_base=LINE_HEIGHT.
        hl_y_top_row0 = 0.0 + (_DC.DOT_RADIUS * 2) + _DC.DOT_GAP_Y
        hl_y_top_row1 = (
            float(_DC.LINE_HEIGHT) + (_DC.DOT_RADIUS * 2) + _DC.DOT_GAP_Y
        )
        assert out.rects[0].y == hl_y_top_row0
        assert out.rects[1].y == hl_y_top_row0
        assert out.rects[2].y == hl_y_top_row1, (
            f"row-1 rect y should be at LINE_HEIGHT band; "
            f"got {out.rects[2].y}, expected {hl_y_top_row1}"
        )
        # Row 1 token x restarts at x_origin.
        assert out.rects[2].x == 0.0 - 2, (
            "row-1 first-token x should restart at x_origin; "
            f"got {out.rects[2].x}"
        )

    with test(
        "L1",
        "L1.94",
        "build_selection_overlay: reversed range (5, 2) → None (paint would draw nothing)",
    ):
        # ui/draw_tokens.py uses `selection[0] <= idx <= selection[1]` which
        # paints NOTHING when start > end. Builder mirrors: returns None.
        out = _build_selection(
            _OverlayStateStub(selection=(5, 2)),
            tokens=["a", "b", "c"],
            token_widths=[10.0, 10.0, 10.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        assert out is None, f"expected None for reversed range; got {out!r}"

    with test(
        "L1",
        "L1.95",
        "build_selection_overlay: viewport trim omits selection rects on scrolled-off rows",
    ):
        # Three tokens, each on its own row (max_row_w=10 forces one-per-row).
        # max_visible_rows=1 drops rows 0 and 1; only row 2 (token 2) survives.
        # Selection (0, 2) covers all three; only the surviving token gets
        # a rect. Matches _draw_token_rows dropping trimmed rows entirely.
        out = _build_selection(
            _OverlayStateStub(selection=(0, 2)),
            tokens=["a", "b", "c"],
            token_widths=[100.0, 100.0, 100.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=10.0,
            max_visible_rows=1,
        )
        assert out is not None
        assert len(out.rects) == 1, (
            f"only surviving token should produce a rect; got {len(out.rects)}"
        )

    with test(
        "L1",
        "L1.96",
        "build_flash_overlay: no flash_state → None",
    ):
        out = _build_flash(
            _OverlayStateStub(flash_state={}),
            tokens=["there"],
            token_widths=[40.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        assert out is None, f"expected None when no flash_state; got {out!r}"

    with test(
        "L1",
        "L1.97",
        "build_flash_overlay: flash_state present → FlashOverlay with 30% alpha color",
    ):
        # Producer sets flash_state = {"indices": [...], "color": "aabbcc"}.
        # Builder emits FlashOverlay with color = "aabbcc" + "4d" per the
        # paint code's `flash_color[:6] + "4d"` rewrite.
        out = _build_flash(
            _OverlayStateStub(
                flash_state={"indices": [0, 2], "color": "aabbcc"},
            ),
            tokens=["a", "b", "c"],
            token_widths=[10.0, 15.0, 20.0],
            x_origin=100.0,
            y_start=200.0,
            max_row_w=1000.0,
        )
        assert out is not None
        assert type(out) is layout_mod_lt.FlashOverlay
        assert out.color == "aabbcc4d", (
            f"flash color should be [:6]+'4d'; got {out.color!r}"
        )
        # Two rects — token 0 at x=100, token 2 at x = 100 + 10 + 5 + 15 + 5 = 135.
        assert len(out.rects) == 2
        assert out.rects[0].x == 100.0 - 2, "token-0 rect x = x_origin - hl_pad"
        assert out.rects[1].x == 135.0 - 2, (
            f"token-2 rect x should skip token-1: got {out.rects[1].x}, "
            f"expected {135.0 - 2}"
        )

    with test(
        "L1",
        "L1.98",
        "build_flash_overlay: empty indices → None",
    ):
        # `indices` present but empty: nothing to paint.
        out = _build_flash(
            _OverlayStateStub(
                flash_state={"indices": [], "color": "ffaa00"},
            ),
            tokens=["a"],
            token_widths=[10.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        assert out is None, f"expected None for empty indices; got {out!r}"

    with test(
        "L1",
        "L1.99",
        "build_flash_overlay: color longer than 6 chars is truncated + alpha suffix",
    ):
        # Some callers may pass an 8-char color (with alpha). The paint code
        # slices [:6] before appending "4d"; builder mirrors that exactly.
        out = _build_flash(
            _OverlayStateStub(
                flash_state={"indices": [0], "color": "aabbccff"},
            ),
            tokens=["a"],
            token_widths=[10.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        assert out is not None
        assert out.color == "aabbcc4d", (
            f"color should be sliced to [:6] then get '4d' alpha; "
            f"got {out.color!r}"
        )

    with test(
        "L1",
        "L1.100",
        "layout_overlays builders: determinism — same inputs, byte-equal outputs",
    ):
        # Purity contract: identical inputs must produce dataclass-equal
        # outputs across calls. Applies to both builders.
        sel_state = _OverlayStateStub(selection=(0, 1))
        flash_state = _OverlayStateStub(
            flash_state={"indices": [0, 1], "color": "aabbcc"},
        )
        args = dict(
            tokens=["a", "b"],
            token_widths=[10.0, 15.0],
            x_origin=100.0,
            y_start=200.0,
            max_row_w=1000.0,
        )
        sel1 = _build_selection(sel_state, **args)
        sel2 = _build_selection(sel_state, **args)
        assert sel1 == sel2, "selection builder is non-deterministic"
        assert sel1 is not sel2, "must return a fresh instance, not a cached one"
        flash1 = _build_flash(flash_state, **args)
        flash2 = _build_flash(flash_state, **args)
        assert flash1 == flash2, "flash builder is non-deterministic"
        assert flash1 is not flash2, "must return a fresh instance"

    with test(
        "L1",
        "L1.101",
        "layout_overlays builders: no state mutation — inputs untouched",
    ):
        # Purity contract: builders MUST NOT mutate state, tokens,
        # token_widths, or the flash_state dict. Snapshot before / compare after.
        flash_dict = {"indices": [0, 1], "color": "aabbcc"}
        indices_ref = flash_dict["indices"]
        indices_before = list(indices_ref)
        state = _OverlayStateStub(selection=(0, 1), flash_state=flash_dict)
        tokens_arg = ["a", "b"]
        widths_arg = [10.0, 15.0]
        _build_selection(
            state,
            tokens=tokens_arg,
            token_widths=widths_arg,
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        _build_flash(
            state,
            tokens=tokens_arg,
            token_widths=widths_arg,
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        assert tokens_arg == ["a", "b"], f"tokens mutated: {tokens_arg}"
        assert widths_arg == [10.0, 15.0], f"widths mutated: {widths_arg}"
        assert flash_dict == {"indices": indices_ref, "color": "aabbcc"}, (
            f"flash_state top-level mutated: {flash_dict}"
        )
        assert indices_ref is flash_dict["indices"], (
            "flash_state.indices list identity replaced — builder must "
            "not swap the list reference"
        )
        assert list(indices_ref) == indices_before, (
            f"flash_state.indices mutated: before={indices_before}, "
            f"after={list(indices_ref)}"
        )

    with test(
        "L1",
        "L1.102",
        "SelectionOverlay + FlashOverlay outputs are frozen ui.layout dataclasses",
    ):
        # Type identity + frozen check — SelectionOverlay/FlashOverlay from
        # ui/layout.py are @dataclass(frozen=True). Locking the immutability
        # contract so downstream renderers can rely on it.
        import dataclasses as _dc3
        sel_out = _build_selection(
            _OverlayStateStub(selection=(0, 0)),
            tokens=["a"],
            token_widths=[10.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        flash_out = _build_flash(
            _OverlayStateStub(
                flash_state={"indices": [0], "color": "aabbcc"},
            ),
            tokens=["a"],
            token_widths=[10.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        assert type(sel_out) is layout_mod_lt.SelectionOverlay
        assert type(flash_out) is layout_mod_lt.FlashOverlay
        # Attempting to mutate must raise FrozenInstanceError.
        try:
            sel_out.rects = []
        except _dc3.FrozenInstanceError:
            pass
        else:
            raise AssertionError(
                "SelectionOverlay accepted mutation — should be frozen"
            )
        try:
            flash_out.color = "ffffffff"
        except _dc3.FrozenInstanceError:
            pass
        else:
            raise AssertionError(
                "FlashOverlay accepted mutation — should be frozen"
            )

    # -----------------------------------------------------------------------
    # Move 4d (help pager + cursor layout builders) — ui/layout_help_cursor.py
    # Two pure builders that turn a state snapshot + panel geometry into
    # HelpLayout | None and CursorLayout | None. No consumers yet — Move 4e
    # wires draw_overlay onto them. Tests lock in the extraction:
    #   - hidden/no-cursor short-circuits
    #   - HELP_PAGES rows produced with correct row-baseline y coordinates
    #   - section-header + title row shapes
    #   - out-of-range page → None
    #   - empty-tokens listening… cursor branch
    #   - cursor before token / cursor after last-token branches
    #   - viewport trim drops off-screen cursor
    #   - change_mode + blink phase propagated (not gated) in model
    #   - determinism, no mutation, frozen output
    # -----------------------------------------------------------------------

    lhc_spec = importlib.util.spec_from_file_location(
        "po_lt_pkg.ui.layout_help_cursor",
        REPO / "ui" / "layout_help_cursor.py",
    )
    lhc_mod = importlib.util.module_from_spec(lhc_spec)
    _sys.modules["po_lt_pkg.ui.layout_help_cursor"] = lhc_mod
    lhc_spec.loader.exec_module(lhc_mod)

    _build_help = lhc_mod.build_help_layout
    _build_cursor = lhc_mod.build_cursor_layout
    _HELP_PAGES = lhc_mod.HELP_PAGES

    # State stub — layout_help_cursor only reads .help_visible / .help_page
    # (help builder) and .cursor / .change_mode / .blink_on (cursor builder).
    class _HelpCursorStateStub:
        def __init__(
            self,
            *,
            help_visible=False,
            help_page=0,
            cursor=None,
            change_mode=False,
            blink_on=True,
        ):
            self.help_visible = help_visible
            self.help_page = help_page
            self.cursor = cursor
            self.change_mode = change_mode
            self.blink_on = blink_on

    # Convenience — the main-panel rect the help builder anchors from.
    _MAIN_PANEL = layout_mod_lt.Rect(x=100.0, y=200.0, w=800.0, h=400.0)

    with test(
        "L1",
        "L1.103",
        "build_help_layout: help_visible=False → None",
    ):
        # Fast-path: no draw when the pager is hidden.
        out = _build_help(
            _HelpCursorStateStub(help_visible=False, help_page=0),
            panel_rect=_MAIN_PANEL,
        )
        assert out is None, f"expected None when help_visible=False; got {out!r}"

    with test(
        "L1",
        "L1.104",
        "build_help_layout: help_page out of range → None",
    ):
        # Below zero.
        out_lo = _build_help(
            _HelpCursorStateStub(help_visible=True, help_page=-1),
            panel_rect=_MAIN_PANEL,
        )
        assert out_lo is None, f"expected None for page=-1; got {out_lo!r}"
        # At len(HELP_PAGES) — first invalid page.
        out_hi = _build_help(
            _HelpCursorStateStub(help_visible=True, help_page=len(_HELP_PAGES)),
            panel_rect=_MAIN_PANEL,
        )
        assert out_hi is None, (
            f"expected None for page={len(_HELP_PAGES)}; got {out_hi!r}"
        )

    with test(
        "L1",
        "L1.105",
        "build_help_layout: valid page → HelpLayout with title row + one row per entry",
    ):
        # Page 0 is "Basics" — 6 (cmd, desc) tuples, no section headers.
        # Rows list should be: 1 title + 6 entries = 7 rows.
        out = _build_help(
            _HelpCursorStateStub(help_visible=True, help_page=0),
            panel_rect=_MAIN_PANEL,
        )
        assert out is not None
        assert type(out) is layout_mod_lt.HelpLayout
        assert out.page == 0, f"page mismatch: {out.page}"
        assert out.total_pages == len(_HELP_PAGES), (
            f"total_pages mismatch: {out.total_pages} vs {len(_HELP_PAGES)}"
        )
        # Basics page: title + 6 entries.
        expected_rows = 1 + 6
        assert len(out.rows) == expected_rows, (
            f"expected {expected_rows} rows for page 0; got {len(out.rows)}"
        )
        # First row is the title: left="Basics", right="".
        assert out.rows[0].left == "Basics", (
            f"first row should be page title 'Basics'; got {out.rows[0].left!r}"
        )
        assert out.rows[0].right == "", (
            f"title row should have empty right column; got {out.rows[0].right!r}"
        )
        # Second row is the first entry: '"bravely"' -> "confirm + paste".
        assert out.rows[1].left == '"bravely"', (
            f"first entry should be '\"bravely\"'; got {out.rows[1].left!r}"
        )
        assert out.rows[1].right == "confirm + paste", (
            f"first entry desc should be 'confirm + paste'; got {out.rows[1].right!r}"
        )

    with test(
        "L1",
        "L1.106",
        "build_help_layout: section-header entries emit '── name ──' rows",
    ):
        # Page 1 is "Delete" — 4 tuple entries, 1 section header, 2 tuples = 7 entries.
        # Rows list: 1 title + 7 entries = 8 rows total; row index 5 (title + 4
        # entries before the section header) should be the section header.
        out = _build_help(
            _HelpCursorStateStub(help_visible=True, help_page=1),
            panel_rect=_MAIN_PANEL,
        )
        assert out is not None
        assert out.rows[0].left == "Delete"
        # Find the section-header row.
        header_rows = [r for r in out.rows if r.right == "" and r.left.startswith("──")]
        assert len(header_rows) == 1, (
            f"expected exactly one section header row on Delete page; "
            f"got {len(header_rows)}: {[r.left for r in header_rows]}"
        )
        assert header_rows[0].left == "── hat colors (on any command) ──", (
            f"header row shape wrong: got {header_rows[0].left!r}"
        )

    with test(
        "L1",
        "L1.107",
        "build_help_layout: row y coordinates are strictly monotonically increasing",
    ):
        # Rows are painted top-to-bottom; y baselines must advance monotonically.
        # Locks the paint-order invariant.
        for page_idx in range(len(_HELP_PAGES)):
            out = _build_help(
                _HelpCursorStateStub(help_visible=True, help_page=page_idx),
                panel_rect=_MAIN_PANEL,
            )
            assert out is not None
            ys = [r.y for r in out.rows]
            for a, b in zip(ys, ys[1:]):
                assert a < b, (
                    f"page {page_idx}: row y coordinates should strictly "
                    f"increase; got {ys}"
                )

    with test(
        "L1",
        "L1.108",
        "build_help_layout: rows anchor from panel_rect.y + panel_rect.h + gap + PANEL_PAD",
    ):
        # Title's baseline sits at:
        #   pager_y_top = panel_rect.y + panel_rect.h + HELP_PANEL_GAP
        #   cy = pager_y_top + PANEL_PAD
        #   title_baseline = cy + HINT_FONT_SIZE
        # With defaults hint_font_size=12, help_panel_gap=8.0 and PANEL_PAD=12:
        #   pager_y_top = 200 + 400 + 8 = 608
        #   cy = 608 + 12 = 620
        #   title_baseline = 620 + 12 = 632
        out = _build_help(
            _HelpCursorStateStub(help_visible=True, help_page=0),
            panel_rect=_MAIN_PANEL,
        )
        assert out is not None
        expected_title_y = 200.0 + 400.0 + 8.0 + _DC.PANEL_PAD + 12.0
        assert out.rows[0].y == expected_title_y, (
            f"title y mismatch: got {out.rows[0].y}, expected {expected_title_y}"
        )

    with test(
        "L1",
        "L1.109",
        "build_help_layout: custom hint_font_size flows into row heights",
    ):
        # help_bigger / help_smaller commands mutate the module-level
        # HINT_FONT_SIZE. Pure builder takes it as an arg — verify the
        # geometry scales. Title baseline moves by (new - default) px.
        default = _build_help(
            _HelpCursorStateStub(help_visible=True, help_page=0),
            panel_rect=_MAIN_PANEL,
        )
        bigger = _build_help(
            _HelpCursorStateStub(help_visible=True, help_page=0),
            panel_rect=_MAIN_PANEL,
            hint_font_size=20,
        )
        assert default is not None and bigger is not None
        # Title baseline: cy + HINT_FONT_SIZE, so bigger's title y is
        # exactly (20 - 12) = 8 px lower.
        assert bigger.rows[0].y - default.rows[0].y == 8.0, (
            "hint_font_size should shift title baseline by (new - default); "
            f"got shift {bigger.rows[0].y - default.rows[0].y}"
        )

    with test(
        "L1",
        "L1.110",
        "build_help_layout: HelpLayout output is frozen",
    ):
        import dataclasses as _dc4
        out = _build_help(
            _HelpCursorStateStub(help_visible=True, help_page=0),
            panel_rect=_MAIN_PANEL,
        )
        assert out is not None
        try:
            out.page = 999
        except _dc4.FrozenInstanceError:
            pass
        else:
            raise AssertionError("HelpLayout accepted mutation — should be frozen")

    with test(
        "L1",
        "L1.111",
        "build_help_layout: determinism — same inputs, dataclass-equal outputs",
    ):
        args = dict(
            state=_HelpCursorStateStub(help_visible=True, help_page=2),
            panel_rect=_MAIN_PANEL,
        )
        out1 = _build_help(**args)
        out2 = _build_help(**args)
        assert out1 == out2, "help builder is non-deterministic"
        assert out1 is not out2, "must return a fresh instance"

    with test(
        "L1",
        "L1.112",
        "build_help_layout: no state mutation — state and panel_rect untouched",
    ):
        state = _HelpCursorStateStub(help_visible=True, help_page=1)
        before = (state.help_visible, state.help_page)
        panel_before = (_MAIN_PANEL.x, _MAIN_PANEL.y, _MAIN_PANEL.w, _MAIN_PANEL.h)
        _build_help(state, panel_rect=_MAIN_PANEL)
        after = (state.help_visible, state.help_page)
        panel_after = (_MAIN_PANEL.x, _MAIN_PANEL.y, _MAIN_PANEL.w, _MAIN_PANEL.h)
        assert before == after, f"state mutated: before={before}, after={after}"
        assert panel_before == panel_after, (
            f"panel_rect mutated (Rect is frozen so this shouldn't be "
            f"possible): before={panel_before}, after={panel_after}"
        )

    # -------- build_cursor_layout tests --------

    with test(
        "L1",
        "L1.113",
        "build_cursor_layout: state.cursor is None → None",
    ):
        out = _build_cursor(
            _HelpCursorStateStub(cursor=None),
            tokens=["hello"],
            token_widths=[40.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        assert out is None, f"expected None when cursor is None; got {out!r}"

    with test(
        "L1",
        "L1.114",
        "build_cursor_layout: empty tokens + cursor=0 → rect at x_origin (listening…)",
    ):
        # ui/draw.py's empty-buffer branch draws the cursor at
        # (panel_x + PANEL_PAD, panel_y + PANEL_PAD + DOT_RADIUS*2 + DOT_GAP_Y).
        # Builder mirrors: with x_origin=X, y_start=Y, rect anchors at
        # (X - 1, Y + DOT_RADIUS*2 + DOT_GAP_Y).
        out = _build_cursor(
            _HelpCursorStateStub(cursor=0),
            tokens=[],
            token_widths=[],
            x_origin=100.0,
            y_start=200.0,
            max_row_w=1000.0,
        )
        assert out is not None
        assert type(out) is layout_mod_lt.CursorLayout
        expected_x = 100.0 - 1
        expected_y = 200.0 + _DC.DOT_RADIUS * 2 + _DC.DOT_GAP_Y
        assert out.rect.x == expected_x, (
            f"empty-buf cursor x should be x_origin - 1; got {out.rect.x}, "
            f"expected {expected_x}"
        )
        assert out.rect.y == expected_y, (
            f"empty-buf cursor y should be y_start + hat band; got "
            f"{out.rect.y}, expected {expected_y}"
        )
        assert out.rect.w == float(_DC.CURSOR_WIDTH), (
            f"cursor width should be CURSOR_WIDTH; got {out.rect.w}"
        )
        assert out.rect.h == float(_DC.TOKEN_FONT_SIZE), (
            f"cursor height should be TOKEN_FONT_SIZE; got {out.rect.h}"
        )

    with test(
        "L1",
        "L1.115",
        "build_cursor_layout: empty tokens + cursor != 0 → None",
    ):
        # ui/draw.py's empty-buf branch only draws for cursor == 0. Any
        # other value with empty tokens is silently skipped by paint.
        out = _build_cursor(
            _HelpCursorStateStub(cursor=1),
            tokens=[],
            token_widths=[],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        assert out is None, f"expected None for cursor=1 on empty tokens; got {out!r}"

    with test(
        "L1",
        "L1.116",
        "build_cursor_layout: cursor in gap before mid-row token → rect at token x",
    ):
        # Tokens on one row at x_origin=0, widths [10, 15, 20], gaps
        # TOKEN_GAP_X between. Cursor at idx 1 → gap BEFORE token 1.
        # Token 1's x = 0 + 10 + TOKEN_GAP_X.
        out = _build_cursor(
            _HelpCursorStateStub(cursor=1),
            tokens=["a", "b", "c"],
            token_widths=[10.0, 15.0, 20.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        assert out is not None
        expected_x = 0.0 + 10.0 + _DC.TOKEN_GAP_X - 1
        assert out.rect.x == expected_x, (
            f"cursor x at gap before token 1 should be its token x - 1; "
            f"got {out.rect.x}, expected {expected_x}"
        )
        expected_y = 0.0 + _DC.DOT_RADIUS * 2 + _DC.DOT_GAP_Y
        assert out.rect.y == expected_y, (
            f"cursor y should be y_base + hat band; got {out.rect.y}, "
            f"expected {expected_y}"
        )

    with test(
        "L1",
        "L1.117",
        "build_cursor_layout: cursor == len(tokens) → rect after last token",
    ):
        # Cursor after the final token in the buffer, on the final row.
        # Paint code: `x - TOKEN_GAP_X` where x has already advanced past
        # the last token's width + trailing gap. So the cursor sits at
        # (x_origin + sum_widths + (N-1)*TOKEN_GAP_X) - 1.
        tokens = ["a", "b", "c"]
        widths = [10.0, 15.0, 20.0]
        out = _build_cursor(
            _HelpCursorStateStub(cursor=3),
            tokens=tokens,
            token_widths=widths,
            x_origin=100.0,
            y_start=200.0,
            max_row_w=1000.0,
        )
        assert out is not None
        # Sum of widths + trailing-gap for each token, minus one trailing gap.
        # x after loop = 100 + 10 + gap + 15 + gap + 20 + gap; -gap = 100 + 45 + 2*gap
        expected_x = 100.0 + 10.0 + 15.0 + 20.0 + 2 * _DC.TOKEN_GAP_X - 1
        assert out.rect.x == expected_x, (
            f"cursor after last token x mismatch: got {out.rect.x}, "
            f"expected {expected_x}"
        )

    with test(
        "L1",
        "L1.118",
        "build_cursor_layout: change_mode + blink_on propagated verbatim",
    ):
        out_change = _build_cursor(
            _HelpCursorStateStub(cursor=0, change_mode=True, blink_on=True),
            tokens=["a"],
            token_widths=[10.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        assert out_change is not None
        assert out_change.change_mode is True
        assert out_change.blink_on is True

        out_blink_off = _build_cursor(
            _HelpCursorStateStub(cursor=0, change_mode=False, blink_on=False),
            tokens=["a"],
            token_widths=[10.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        # blink_on=False must NOT gate out — the layout is emitted so
        # debug snapshots can distinguish "cursor blinking off" from
        # "no cursor set."
        assert out_blink_off is not None, (
            "blink_on=False must NOT return None — paint layer keeps "
            "the gate; model carries the phase"
        )
        assert out_blink_off.blink_on is False
        assert out_blink_off.change_mode is False

    with test(
        "L1",
        "L1.119",
        "build_cursor_layout: cursor on trimmed row → None",
    ):
        # Three tokens, each on its own row (max_row_w=10 forces one-per-row).
        # max_visible_rows=1 drops rows 0 and 1; only row 2 (token 2) survives.
        # Cursor at token 0 targets a trimmed row → None.
        out = _build_cursor(
            _HelpCursorStateStub(cursor=0),
            tokens=["a", "b", "c"],
            token_widths=[100.0, 100.0, 100.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=10.0,
            max_visible_rows=1,
        )
        assert out is None, (
            f"cursor on trimmed row should return None; got {out!r}"
        )

    with test(
        "L1",
        "L1.120",
        "build_cursor_layout: cursor on surviving row after trim → rect at correct y",
    ):
        # Same setup — three rows, keep last. Cursor at token 2 lands on
        # the (only) surviving row at y_base = y_start (trim shifts the
        # row grid up so the last row is at y_start).
        out = _build_cursor(
            _HelpCursorStateStub(cursor=2),
            tokens=["a", "b", "c"],
            token_widths=[100.0, 100.0, 100.0],
            x_origin=0.0,
            y_start=200.0,
            max_row_w=10.0,
            max_visible_rows=1,
        )
        assert out is not None
        expected_y = 200.0 + _DC.DOT_RADIUS * 2 + _DC.DOT_GAP_Y
        assert out.rect.y == expected_y, (
            f"cursor y on surviving row should anchor at y_start; got "
            f"{out.rect.y}, expected {expected_y}"
        )

    with test(
        "L1",
        "L1.121",
        "build_cursor_layout: cursor out of range → None",
    ):
        # cursor = 5 but only 3 tokens; not equal to len(tokens)=3 either.
        out = _build_cursor(
            _HelpCursorStateStub(cursor=5),
            tokens=["a", "b", "c"],
            token_widths=[10.0, 10.0, 10.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        assert out is None, f"cursor > len(tokens)+1 should be None; got {out!r}"

    with test(
        "L1",
        "L1.122",
        "build_cursor_layout: multi-row wrap → cursor on row 1 lands at row 1's y_base",
    ):
        # Force a wrap: two tokens of width 100 with max_row_w=100 → each
        # token gets its own row. Cursor at token 1 → row 1 at
        # y_base = y_start + LINE_HEIGHT.
        out = _build_cursor(
            _HelpCursorStateStub(cursor=1),
            tokens=["a", "b"],
            token_widths=[100.0, 100.0],
            x_origin=0.0,
            y_start=50.0,
            max_row_w=100.0,
        )
        assert out is not None
        expected_y = 50.0 + _DC.LINE_HEIGHT + _DC.DOT_RADIUS * 2 + _DC.DOT_GAP_Y
        assert out.rect.y == expected_y, (
            f"cursor on row 1 y mismatch: got {out.rect.y}, "
            f"expected {expected_y}"
        )
        # x resets to x_origin at the start of each row.
        assert out.rect.x == 0.0 - 1, (
            f"cursor on row 1 x should restart at x_origin - 1; got {out.rect.x}"
        )

    with test(
        "L1",
        "L1.123",
        "build_cursor_layout: CursorLayout output is frozen",
    ):
        import dataclasses as _dc5
        out = _build_cursor(
            _HelpCursorStateStub(cursor=0),
            tokens=["a"],
            token_widths=[10.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        assert out is not None
        try:
            out.change_mode = True
        except _dc5.FrozenInstanceError:
            pass
        else:
            raise AssertionError(
                "CursorLayout accepted mutation — should be frozen"
            )

    with test(
        "L1",
        "L1.124",
        "build_cursor_layout: determinism — same inputs, dataclass-equal outputs",
    ):
        args = dict(
            state=_HelpCursorStateStub(cursor=1, change_mode=True, blink_on=False),
            tokens=["a", "b", "c"],
            token_widths=[10.0, 15.0, 20.0],
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        out1 = _build_cursor(**args)
        out2 = _build_cursor(**args)
        assert out1 == out2, "cursor builder is non-deterministic"
        assert out1 is not out2, "must return a fresh instance"

    with test(
        "L1",
        "L1.125",
        "build_cursor_layout: no state mutation — inputs untouched",
    ):
        state = _HelpCursorStateStub(cursor=1, change_mode=True, blink_on=True)
        tokens_arg = ["a", "b"]
        widths_arg = [10.0, 15.0]
        before = (state.cursor, state.change_mode, state.blink_on)
        _build_cursor(
            state,
            tokens=tokens_arg,
            token_widths=widths_arg,
            x_origin=0.0,
            y_start=0.0,
            max_row_w=1000.0,
        )
        after = (state.cursor, state.change_mode, state.blink_on)
        assert before == after, f"state mutated: before={before}, after={after}"
        assert tokens_arg == ["a", "b"], f"tokens mutated: {tokens_arg}"
        assert widths_arg == [10.0, 15.0], f"widths mutated: {widths_arg}"

    # -----------------------------------------------------------------------
    # Move 4e (top-level layout orchestrator) — ui/layout_root.py
    # Pure orchestrator that composes the four sub-builders into a full
    # LayoutModel. Uses a fake canvas for text measurement (the only impure
    # step). No live paint; wire-up into draw_overlay is env-gated (see
    # ui/draw.py:_layout_model_enabled and ui/draw_from_model.py). L1
    # tests here lock in the composition shape and the pure-function
    # contract at the orchestrator level.
    # -----------------------------------------------------------------------

    # Additional internal modules the orchestrator imports at composition
    # time — register them under po_lt_pkg so layout_root's relative
    # imports resolve without pulling talon in.

    # internal/instance.py — orchestrator does `from ..internal.instance
    # import instance as _live_instance` inside the function body. Load
    # it under po_lt_pkg.internal.instance so the guarded fallback finds
    # the shared instance without hitting the real filesystem tree.
    inst_spec_lr = importlib.util.spec_from_file_location(
        "po_lt_pkg.internal.instance",
        REPO / "internal" / "instance.py",
    )
    inst_mod_lr = importlib.util.module_from_spec(inst_spec_lr)
    _sys.modules["po_lt_pkg.internal.instance"] = inst_mod_lr
    inst_spec_lr.loader.exec_module(inst_mod_lr)

    # internal/homophones.py — pulls a CSV at import time. The read is
    # try/except-guarded so a missing file falls through cleanly. Load
    # under po_lt_pkg so `from ..internal import homophones as _homophones`
    # resolves. hint_enabled() defaults to True (see homophones module),
    # so the orchestrator's `flagged` set is computed even with an empty
    # CSV — the set is just empty.
    homo_spec_lr = importlib.util.spec_from_file_location(
        "po_lt_pkg.internal.homophones",
        REPO / "internal" / "homophones.py",
    )
    homo_mod_lr = importlib.util.module_from_spec(homo_spec_lr)
    _sys.modules["po_lt_pkg.internal.homophones"] = homo_mod_lr
    homo_spec_lr.loader.exec_module(homo_mod_lr)

    # shim/__init__.py so `from ..shim import shapes` resolves under
    # po_lt_pkg.
    _lt_shim_pkg = _types_lt.ModuleType("po_lt_pkg.shim")
    _lt_shim_pkg.__path__ = []
    _sys.modules["po_lt_pkg.shim"] = _lt_shim_pkg

    # shim/shapes.py — lazy Skia imports; safe to load headless. Load
    # under po_lt_pkg.shim.shapes so the orchestrator's
    # `from ..shim import shapes as _shapes_runtime` finds it.
    shapes_spec_lr = importlib.util.spec_from_file_location(
        "po_lt_pkg.shim.shapes",
        REPO / "shim" / "shapes.py",
    )
    shapes_mod_lr = importlib.util.module_from_spec(shapes_spec_lr)
    _sys.modules["po_lt_pkg.shim.shapes"] = shapes_mod_lr
    shapes_spec_lr.loader.exec_module(shapes_mod_lr)

    # Now load the orchestrator itself.
    lr_spec = importlib.util.spec_from_file_location(
        "po_lt_pkg.ui.layout_root",
        REPO / "ui" / "layout_root.py",
    )
    lr_mod = importlib.util.module_from_spec(lr_spec)
    _sys.modules["po_lt_pkg.ui.layout_root"] = lr_mod
    lr_spec.loader.exec_module(lr_mod)

    _compose_layout = lr_mod.layout
    _LayoutModel = lr_mod.LayoutModel

    # -----------------------------------------------------------------------
    # Fake canvas — the orchestrator only calls canvas.paint.typeface (write),
    # canvas.paint.textsize (read + write), and canvas.paint.measure_text
    # (read; returns a (metrics, rect_like) tuple with rect_like.width).
    # A width mapper drives determinism: every token width is 10 * len(tok).
    # -----------------------------------------------------------------------

    class _FakeMeasureRect:
        __slots__ = ("width",)
        def __init__(self, width):
            self.width = width

    class _FakePaint:
        def __init__(self):
            self.typeface = None
            self.textsize = 0

        def measure_text(self, text):
            # Return a (metrics-ish, rect-with-width) tuple matching Skia's
            # measure_text contract. The orchestrator only reads [1].width.
            return (None, _FakeMeasureRect(len(text) * 10.0))

    class _FakeCanvas:
        def __init__(self):
            self.paint = _FakePaint()

    # -----------------------------------------------------------------------
    # Fake screen rect + fake overlay — the orchestrator reads
    # state.screen_rect (width / height / left / top / x / y accessors) and
    # goes through instance.runtime.viewport for anchor state. For test we
    # replace the shared instance's viewport with a stub via monkey-patching.
    # -----------------------------------------------------------------------

    class _FakeScreenRect:
        def __init__(self, x=0.0, y=0.0, width=1000.0, height=800.0):
            self.x = x
            self.y = y
            self.width = width
            self.height = height
            # draw_overlay also reads .left / .top — mirror x / y.
            self.left = x
            self.top = y

    class _FakeViewport:
        def __init__(self, anchor_rect=None, anchor_position="top"):
            self._anchor_rect = anchor_rect
            self._anchor_position = anchor_position

    class _FakeOverlay:
        # The orchestrator accepts overlay but doesn't call any method on it
        # (viewport access goes through the instance). Kept as a marker
        # argument for API parity.
        pass

    # Point the shared instance's viewport at a fake for these tests.
    # Each test restores the original after — the instance object survives
    # across tests, so leaving a stub in place would leak into later tests.
    _live_instance = inst_mod_lr.instance
    _orig_viewport = _live_instance.runtime.viewport

    def _install_fake_viewport(anchor_rect=None, anchor_position="top"):
        _live_instance.runtime.viewport = _FakeViewport(
            anchor_rect=anchor_rect, anchor_position=anchor_position
        )

    def _restore_viewport():
        _live_instance.runtime.viewport = _orig_viewport

    # -----------------------------------------------------------------------
    # State stub — the orchestrator reads a lot of state fields.
    # Instead of building an ad-hoc stub, use the real _State from
    # internal/instance.py and populate the fields we care about; the
    # sub-builders read what they need via getattr fallbacks. buffer is
    # a lightweight get_tokens/get_selection surface.
    # -----------------------------------------------------------------------

    class _FakeBuffer:
        def __init__(self, tokens=None, selection=None):
            self._tokens = list(tokens or [])
            self._selection = selection

        def get_tokens(self):
            return list(self._tokens)

        def get_selection(self):
            return self._selection

    # Sentinel so callers can request "no screen_rect" (None) distinctly
    # from "use the default fake screen". A plain None default on the kw
    # arg would conflate the two.
    _SR_DEFAULT = object()

    def _mk_state(
        *,
        tokens=None,
        selection=None,
        screen_rect=_SR_DEFAULT,
        window_scoped=False,
        homophone_hint=False,
        homophone_shapes=False,
        shape_assignments=None,
        position_assignments=None,
        homophone_panel_alts=None,
        flash_state=None,
        help_visible=False,
        help_page=0,
        cursor=None,
        change_mode=False,
        blink_on=True,
    ):
        st = inst_mod_lr._State()
        st.buffer = _FakeBuffer(tokens=tokens, selection=selection)
        # sentinel → default fake; explicit None → propagate None; other
        # value → use it verbatim.
        if screen_rect is _SR_DEFAULT:
            st.screen_rect = _FakeScreenRect()
        else:
            st.screen_rect = screen_rect
        st.window_scoped = window_scoped
        st.homophone_hint = homophone_hint
        st.homophone_shapes = homophone_shapes
        st.shape_assignments = shape_assignments or {}
        st.position_assignments = position_assignments or {}
        st.homophone_panel_alts = homophone_panel_alts or {}
        st.flash_state = flash_state or {}
        st.help_visible = help_visible
        st.help_page = help_page
        st.cursor = cursor
        st.change_mode = change_mode
        st.blink_on = blink_on
        return st

    with test(
        "L1",
        "L1.126",
        "layout(): screen_rect=None → zero-panel LayoutModel with empty fields",
    ):
        _install_fake_viewport()
        try:
            st = _mk_state(tokens=["a"], screen_rect=None)
            canvas = _FakeCanvas()
            model = _compose_layout(st, canvas, _FakeOverlay())
            assert isinstance(model, _LayoutModel), (
                f"expected LayoutModel; got {type(model).__name__}"
            )
            assert model.panel.w == 0.0 and model.panel.h == 0.0, (
                f"panel should be zero when screen_rect is None; got "
                f"{model.panel!r}"
            )
            assert model.tokens == []
            assert model.selection is None
            assert model.flash is None
            assert model.bubbles == []
            assert model.help is None
            assert model.cursor is None
            assert model.hints_hidden_by_overflow is False
        finally:
            _restore_viewport()

    with test(
        "L1",
        "L1.127",
        "layout(): basic composition — panel + content_area + help_area + tokens",
    ):
        _install_fake_viewport()
        try:
            st = _mk_state(tokens=["hello", "world"])
            canvas = _FakeCanvas()
            model = _compose_layout(st, canvas, _FakeOverlay())

            # Panel geometry — 1000x800 screen, PANEL_H_FRACTION=0.10 so
            # panel_h is max(80, 3*LINE_HEIGHT + 2*PANEL_PAD).
            expected_panel_h = max(
                800.0 * dc_mod_lt.PANEL_H_FRACTION,
                3 * dc_mod_lt.LINE_HEIGHT + dc_mod_lt.PANEL_PAD * 2,
            )
            assert model.panel.w == 1000.0
            assert model.panel.h == expected_panel_h
            assert model.panel.x == 0.0
            assert model.panel.y == 0.0

            # Content area: content_w = 1000 * 0.80 = 800; usable
            # content-x width is 800 - 2*PANEL_PAD.
            assert model.content_area.w == 800.0 - dc_mod_lt.PANEL_PAD * 2
            assert model.content_area.x == 0.0 + dc_mod_lt.PANEL_PAD

            # Help area is present when hints aren't overflow-hidden.
            assert model.help_area is not None, (
                "help_area should be present under non-overflow layout"
            )
            # Help x anchor: panel_x + content_w
            assert model.help_area.x == 0.0 + 800.0

            # Two tokens survive.
            assert len(model.tokens) == 2
            assert model.tokens[0].text == "hello"
            assert model.tokens[1].text == "world"
            # Text alignment: token 0 at x_origin = 0 + PANEL_PAD.
            assert model.tokens[0].rect.x == float(dc_mod_lt.PANEL_PAD)
            # Widths from fake measurer: len(tok) * 10.
            assert model.tokens[0].rect.w == 50.0  # "hello"
            assert model.tokens[1].rect.w == 50.0  # "world"

            assert model.hints_hidden_by_overflow is False
            assert model.using_fallback is False
        finally:
            _restore_viewport()

    with test(
        "L1",
        "L1.128",
        "layout(): empty tokens → empty model.tokens, cursor at 0 lands at origin",
    ):
        _install_fake_viewport()
        try:
            st = _mk_state(tokens=[], cursor=0)
            canvas = _FakeCanvas()
            model = _compose_layout(st, canvas, _FakeOverlay(), cursor=0)

            assert model.tokens == []
            # Cursor should be present for cursor=0 on empty buffer.
            assert model.cursor is not None, (
                "cursor=0 with empty tokens should emit a cursor at origin"
            )
            # x_origin = 0 + PANEL_PAD; cursor rect x is that minus 1 per
            # the paint code contract (see layout_help_cursor's cursor
            # geometry).
            expected_x = float(dc_mod_lt.PANEL_PAD) - 1
            assert model.cursor.rect.x == expected_x, (
                f"cursor x should be x_origin - 1; got {model.cursor.rect.x}, "
                f"expected {expected_x}"
            )
        finally:
            _restore_viewport()

    with test(
        "L1",
        "L1.129",
        "layout(): using_fallback + target_label propagated to model",
    ):
        _install_fake_viewport()
        try:
            st = _mk_state(tokens=["one"])
            canvas = _FakeCanvas()
            model = _compose_layout(
                st,
                canvas,
                _FakeOverlay(),
                using_fallback=True,
                target_label="foo.txt",
            )
            assert model.using_fallback is True
            assert model.target_label == "foo.txt"
        finally:
            _restore_viewport()

    with test(
        "L1",
        "L1.130",
        "layout(): selection arg overrides state.buffer.get_selection() via shim",
    ):
        _install_fake_viewport()
        try:
            # State's buffer reports no selection. The caller's selection
            # arg should still produce a SelectionOverlay.
            st = _mk_state(tokens=["a", "b", "c"], selection=None)
            canvas = _FakeCanvas()
            model = _compose_layout(
                st,
                canvas,
                _FakeOverlay(),
                selection=(0, 1),
            )
            assert model.selection is not None, (
                "caller-supplied selection arg should synthesize a "
                "SelectionOverlay"
            )
            # Two tokens covered: idx 0 + idx 1.
            assert len(model.selection.rects) == 2
        finally:
            _restore_viewport()

    with test(
        "L1",
        "L1.131",
        "layout(): flash_indices + flash_color arg synthesizes flash overlay",
    ):
        _install_fake_viewport()
        try:
            # Empty state flash; caller's args should still produce a
            # FlashOverlay via the _FlashOverrideState shim.
            st = _mk_state(tokens=["a", "b", "c"])
            canvas = _FakeCanvas()
            model = _compose_layout(
                st,
                canvas,
                _FakeOverlay(),
                flash_indices=[2],
                flash_color="ff0000",
            )
            assert model.flash is not None, (
                "flash_indices+flash_color args should synthesize a FlashOverlay"
            )
            assert len(model.flash.rects) == 1
            # Color rewrite: 6 chars + "4d" alpha.
            assert model.flash.color == "ff00004d", (
                f"flash color should be flash_color[:6]+'4d'; got "
                f"{model.flash.color!r}"
            )
        finally:
            _restore_viewport()

    with test(
        "L1",
        "L1.132",
        "layout(): overflow detection — many tokens → hints_hidden_by_overflow",
    ):
        _install_fake_viewport()
        try:
            # Tiny screen so a handful of tokens can't fit in the content
            # zone height. PANEL_H_FRACTION=0.10 of screen height governs
            # panel_h; a tiny screen forces a tiny panel and overflow.
            tiny_screen = _FakeScreenRect(width=200.0, height=100.0)
            # Many single-char tokens → many rows on a narrow content zone.
            tokens_arg = [chr(ord("a") + i) for i in range(30)]
            st = _mk_state(tokens=tokens_arg, screen_rect=tiny_screen)
            canvas = _FakeCanvas()
            model = _compose_layout(st, canvas, _FakeOverlay())

            # Under overflow: hints_hidden_by_overflow=True; help_area=None.
            assert model.hints_hidden_by_overflow is True, (
                "many tokens on a tiny screen should trigger overflow"
            )
            assert model.help_area is None, (
                "help_area should be None when hints hidden by overflow"
            )
        finally:
            _restore_viewport()

    with test(
        "L1",
        "L1.133",
        "layout(): determinism — same inputs, structurally-equal outputs",
    ):
        _install_fake_viewport()
        try:
            st1 = _mk_state(tokens=["hello", "world"])
            st2 = _mk_state(tokens=["hello", "world"])
            canvas1 = _FakeCanvas()
            canvas2 = _FakeCanvas()
            m1 = _compose_layout(st1, canvas1, _FakeOverlay())
            m2 = _compose_layout(st2, canvas2, _FakeOverlay())
            # LayoutModel is frozen; equality is structural.
            assert m1 == m2, (
                "layout() should be deterministic — same inputs should "
                "produce dataclass-equal outputs"
            )
            assert m1 is not m2, "must return a fresh LayoutModel per call"
        finally:
            _restore_viewport()

    with test(
        "L1",
        "L1.134",
        "layout(): no state mutation — inputs untouched after composition",
    ):
        _install_fake_viewport()
        try:
            st = _mk_state(
                tokens=["a", "b", "c"],
                shape_assignments={0: "wing"},
                position_assignments={0: (0, 2)},
            )
            # Snapshot pre-call.
            shape_before = dict(st.shape_assignments)
            pos_before = dict(st.position_assignments)
            homo_alts_before = dict(st.homophone_panel_alts)
            flash_before = dict(st.flash_state)

            canvas = _FakeCanvas()
            _compose_layout(st, canvas, _FakeOverlay())

            assert st.shape_assignments == shape_before, "shape mutated"
            assert st.position_assignments == pos_before, "position mutated"
            assert st.homophone_panel_alts == homo_alts_before, "alts mutated"
            assert st.flash_state == flash_before, "flash mutated"
            # Buffer tokens should be unchanged.
            assert st.buffer.get_tokens() == ["a", "b", "c"], (
                "buffer tokens mutated"
            )
        finally:
            _restore_viewport()

    with test(
        "L1",
        "L1.135",
        "layout(): LayoutModel is frozen — mutation raises FrozenInstanceError",
    ):
        _install_fake_viewport()
        try:
            import dataclasses as _dc_lr
            st = _mk_state(tokens=["a"])
            canvas = _FakeCanvas()
            model = _compose_layout(st, canvas, _FakeOverlay())
            try:
                model.using_fallback = True
            except _dc_lr.FrozenInstanceError:
                pass
            else:
                raise AssertionError(
                    "LayoutModel accepted mutation — should be frozen"
                )
        finally:
            _restore_viewport()

    # -----------------------------------------------------------------------
    # Move 5 (PaintOp union + pure builder + Skia sink) — ui/paint_ops.py
    #
    # PaintOp is a flat, immutable description of one paint step. Sits
    # between LayoutModel (Move 4e) and the Skia sink (draw_from_model).
    #
    #     to_paint_ops(model) -> list[PaintOp]  # pure
    #     execute(ops, canvas)                  # side-effecting sink
    #
    # L1 scope covers:
    # * Frozen-dataclass contract on all four op types.
    # * to_paint_ops scope for what draw_from_model.py currently handles:
    #   listening placeholder, per-token text, cursor rect (with change
    #   mode). Bubbles / help / hats / underlines are OUT of scope for
    #   this move — those fields on LayoutModel are ignored by
    #   to_paint_ops.
    # * execute() dispatch via a fake canvas.
    # -----------------------------------------------------------------------

    # Load ui/paint_ops.py under po_lt_pkg.ui.paint_ops. The module has a
    # top-level `from .layout import LayoutModel` (already registered
    # earlier as po_lt_pkg.ui.layout) and lazy imports of
    # ..internal.draw_constants and talon.ui inside to_paint_ops /
    # execute respectively. draw_constants is already registered under
    # po_lt_pkg.internal.draw_constants; talon.ui needs a lightweight
    # stub before execute() is called (see below).
    po_spec = importlib.util.spec_from_file_location(
        "po_lt_pkg.ui.paint_ops",
        REPO / "ui" / "paint_ops.py",
    )
    po_mod = importlib.util.module_from_spec(po_spec)
    _sys.modules["po_lt_pkg.ui.paint_ops"] = po_mod
    po_spec.loader.exec_module(po_mod)

    _RectOp = po_mod.RectOp
    _TextOp = po_mod.TextOp
    _LineOp = po_mod.LineOp
    _EllipseOp = po_mod.EllipseOp
    _to_paint_ops = po_mod.to_paint_ops
    _execute = po_mod.execute

    # ui.layout dataclasses — reuse the already-loaded module.
    _po_layout = _sys.modules["po_lt_pkg.ui.layout"]
    _Rect_layout = _po_layout.Rect  # frozen geometry Rect (Move 4)
    _LayoutModelPO = _po_layout.LayoutModel
    _TokenLayout = _po_layout.TokenLayout
    _CursorLayout = _po_layout.CursorLayout

    # draw_constants — read the exact constants to_paint_ops uses so
    # each expected coordinate lines up numerically with the emitted op.
    _DC_PO = _sys.modules["po_lt_pkg.internal.draw_constants"]

    def _mk_empty_model_po(
        *,
        tokens=(),
        cursor=None,
        content_area=None,
    ):
        """Build a LayoutModel with the minimum fields to_paint_ops reads.

        Fields to_paint_ops actually consumes: tokens, content_area
        (only when tokens is empty), cursor. Everything else is passed
        as innocuous defaults so the model constructs.
        """
        panel = _Rect_layout(x=0.0, y=0.0, w=100.0, h=100.0)
        ca = content_area or _Rect_layout(x=10.0, y=20.0, w=80.0, h=80.0)
        return _LayoutModelPO(
            panel=panel,
            content_area=ca,
            help_area=None,
            tokens=list(tokens),
            selection=None,
            flash=None,
            bubbles=[],
            help=None,
            cursor=cursor,
            target_label="",
            using_fallback=False,
            hints_hidden_by_overflow=False,
        )

    def _mk_token_po(index, text, x, y, w=30.0, h=20.0):
        return _TokenLayout(
            index=index,
            text=text,
            rect=_Rect_layout(x=x, y=y, w=w, h=h),
            hat=None,
            shape=None,
            underline_segments=[],
            flagged=False,
            on_visible_row=True,
        )

    def _mk_cursor_po(x, y, h, *, change_mode=False, blink_on=True, w=1.0):
        return _CursorLayout(
            rect=_Rect_layout(x=x, y=y, w=w, h=h),
            change_mode=change_mode,
            blink_on=blink_on,
        )

    with test(
        "L1",
        "L1.136",
        "paint_ops: RectOp constructs with defaults and is frozen",
    ):
        import dataclasses as _dc_po
        op = _RectOp(x=1.0, y=2.0, w=3.0, h=4.0, color="ff0000ff")
        assert op.stroke is False, f"stroke should default False; got {op.stroke!r}"
        assert op.stroke_width == 1.0
        try:
            op.color = "00ff00ff"
        except _dc_po.FrozenInstanceError:
            pass
        else:
            raise AssertionError("RectOp accepted mutation — should be frozen")

    with test(
        "L1",
        "L1.137",
        "paint_ops: TextOp constructs and is frozen",
    ):
        import dataclasses as _dc_po
        op = _TextOp(x=1.0, y=2.0, text="hi", font_size=14.0, color="ffffffff")
        try:
            op.text = "bye"
        except _dc_po.FrozenInstanceError:
            pass
        else:
            raise AssertionError("TextOp accepted mutation — should be frozen")

    with test(
        "L1",
        "L1.138",
        "paint_ops: LineOp constructs with default width and is frozen",
    ):
        import dataclasses as _dc_po
        op = _LineOp(x0=0.0, y0=0.0, x1=10.0, y1=10.0, color="ffffffff")
        assert op.width == 1.0
        try:
            op.x1 = 99.0
        except _dc_po.FrozenInstanceError:
            pass
        else:
            raise AssertionError("LineOp accepted mutation — should be frozen")

    with test(
        "L1",
        "L1.139",
        "paint_ops: EllipseOp constructs with defaults and is frozen",
    ):
        import dataclasses as _dc_po
        op = _EllipseOp(cx=5.0, cy=5.0, rx=3.0, ry=3.0, color="ffffffff")
        assert op.stroke is False
        try:
            op.cx = 99.0
        except _dc_po.FrozenInstanceError:
            pass
        else:
            raise AssertionError("EllipseOp accepted mutation — should be frozen")

    with test(
        "L1",
        "L1.140",
        "to_paint_ops: empty tokens + no cursor → one listening TextOp",
    ):
        model = _mk_empty_model_po(tokens=(), cursor=None)
        ops = _to_paint_ops(model)
        assert isinstance(ops, list), f"expected list; got {type(ops).__name__}"
        assert len(ops) == 1, f"expected exactly 1 op (listening text); got {len(ops)}"
        assert isinstance(ops[0], _TextOp), (
            f"expected TextOp for listening placeholder; got {type(ops[0]).__name__}"
        )
        assert ops[0].text == "listening...", (
            f"expected 'listening...' text; got {ops[0].text!r}"
        )
        # Coord check against draw_constants: x = content_area.x,
        # y baseline = content_area.y + DOT_RADIUS*2 + DOT_GAP_Y + TOKEN_FONT_SIZE.
        assert ops[0].x == 10.0, f"listening x should be content_area.x; got {ops[0].x}"
        expected_y = (
            20.0
            + (_DC_PO.DOT_RADIUS * 2)
            + _DC_PO.DOT_GAP_Y
            + _DC_PO.TOKEN_FONT_SIZE
        )
        assert ops[0].y == expected_y, (
            f"listening baseline y mismatch: got {ops[0].y}, expected {expected_y}"
        )
        assert ops[0].color == _DC_PO.LISTENING_COLOR
        assert ops[0].font_size == _DC_PO.TOKEN_FONT_SIZE

    with test(
        "L1",
        "L1.141",
        "to_paint_ops: N tokens → N TextOps in token order, no cursor when cursor=None",
    ):
        toks = [
            _mk_token_po(0, "hello", x=10.0, y=30.0),
            _mk_token_po(1, "world", x=50.0, y=30.0),
            _mk_token_po(2, "again", x=90.0, y=30.0),
        ]
        model = _mk_empty_model_po(tokens=toks, cursor=None)
        ops = _to_paint_ops(model)
        assert len(ops) == 3, f"expected 3 TextOps; got {len(ops)}"
        for i, (op, tok) in enumerate(zip(ops, toks)):
            assert isinstance(op, _TextOp), (
                f"op[{i}] should be TextOp; got {type(op).__name__}"
            )
            assert op.text == tok.text, f"op[{i}].text mismatch"
            assert op.x == tok.rect.x, f"op[{i}].x mismatch"
            expected_y = (
                tok.rect.y
                + (_DC_PO.DOT_RADIUS * 2)
                + _DC_PO.DOT_GAP_Y
                + _DC_PO.TOKEN_FONT_SIZE
            )
            assert op.y == expected_y, (
                f"op[{i}].y baseline mismatch: got {op.y}, expected {expected_y}"
            )
            assert op.color == _DC_PO.TOKEN_COLOR
            assert op.font_size == _DC_PO.TOKEN_FONT_SIZE

    with test(
        "L1",
        "L1.142",
        "to_paint_ops: navigate-mode cursor (blink_on=True) → one cursor RectOp",
    ):
        cur = _mk_cursor_po(
            x=100.0, y=40.0, h=25.0, change_mode=False, blink_on=True
        )
        model = _mk_empty_model_po(
            tokens=[_mk_token_po(0, "a", x=10.0, y=30.0)], cursor=cur
        )
        ops = _to_paint_ops(model)
        # 1 token TextOp + 1 cursor RectOp = 2 ops.
        assert len(ops) == 2, f"expected 2 ops (1 text + 1 cursor); got {len(ops)}"
        assert isinstance(ops[0], _TextOp)
        cursor_op = ops[1]
        assert isinstance(cursor_op, _RectOp), (
            f"cursor should be RectOp; got {type(cursor_op).__name__}"
        )
        assert cursor_op.stroke is False, "cursor rect should be filled"
        assert cursor_op.color == _DC_PO.CURSOR_COLOR_NAVIGATE, (
            f"navigate cursor color mismatch: got {cursor_op.color!r}"
        )
        assert cursor_op.x == 100.0 and cursor_op.y == 40.0
        assert cursor_op.w == _DC_PO.CURSOR_WIDTH
        assert cursor_op.h == 25.0

    with test(
        "L1",
        "L1.143",
        "to_paint_ops: cursor blink_on=False → NO cursor op emitted (paint-side blink gate)",
    ):
        cur = _mk_cursor_po(
            x=100.0, y=40.0, h=25.0, change_mode=False, blink_on=False
        )
        model = _mk_empty_model_po(
            tokens=[_mk_token_po(0, "a", x=10.0, y=30.0)], cursor=cur
        )
        ops = _to_paint_ops(model)
        # Only the token TextOp — no cursor ops when blink_on=False.
        assert len(ops) == 1, (
            f"blink_off should suppress cursor; expected 1 op, got {len(ops)}"
        )
        assert isinstance(ops[0], _TextOp)

    with test(
        "L1",
        "L1.144",
        "to_paint_ops: change-mode cursor → change-zone RectOp + cursor RectOp",
    ):
        cur = _mk_cursor_po(
            x=100.0, y=40.0, h=25.0, change_mode=True, blink_on=True
        )
        model = _mk_empty_model_po(tokens=(), cursor=cur)
        # Empty tokens → 1 listening TextOp + 2 cursor ops = 3 ops total.
        ops = _to_paint_ops(model)
        assert len(ops) == 3, (
            f"expected 3 ops (listening + change-zone + cursor); got {len(ops)}"
        )
        assert isinstance(ops[0], _TextOp)
        zone_op = ops[1]
        cursor_op = ops[2]
        assert isinstance(zone_op, _RectOp), "change-zone should be RectOp"
        assert isinstance(cursor_op, _RectOp), "cursor should be RectOp"

        # Zone op: color = CURSOR_COLOR_CHANGE[:6] + CURSOR_CHANGE_ZONE_ALPHA
        expected_zone_color = (
            _DC_PO.CURSOR_COLOR_CHANGE[:6] + _DC_PO.CURSOR_CHANGE_ZONE_ALPHA
        )
        assert zone_op.color == expected_zone_color, (
            f"change-zone color mismatch: got {zone_op.color!r}, expected {expected_zone_color!r}"
        )
        # Zone geometry: x = cursor.rect.x + 1 - CURSOR_CHANGE_ZONE_WIDTH/2
        expected_zone_x = 100.0 + 1 - _DC_PO.CURSOR_CHANGE_ZONE_WIDTH / 2
        assert zone_op.x == expected_zone_x, (
            f"change-zone x mismatch: got {zone_op.x}, expected {expected_zone_x}"
        )
        assert zone_op.w == _DC_PO.CURSOR_CHANGE_ZONE_WIDTH
        assert zone_op.h == 25.0

        # Cursor op: color = CURSOR_COLOR_CHANGE, x = cursor.rect.x
        assert cursor_op.color == _DC_PO.CURSOR_COLOR_CHANGE
        assert cursor_op.x == 100.0
        assert cursor_op.w == _DC_PO.CURSOR_WIDTH

    with test(
        "L1",
        "L1.145",
        "to_paint_ops: determinism — same LayoutModel → structurally-equal ops",
    ):
        toks = [_mk_token_po(0, "hi", x=10.0, y=30.0)]
        cur = _mk_cursor_po(x=50.0, y=40.0, h=25.0)
        m1 = _mk_empty_model_po(tokens=toks, cursor=cur)
        m2 = _mk_empty_model_po(tokens=list(toks), cursor=cur)
        ops1 = _to_paint_ops(m1)
        ops2 = _to_paint_ops(m2)
        assert ops1 == ops2, (
            "to_paint_ops should be deterministic — same input should "
            f"produce equal ops. Got:\n  ops1={ops1}\n  ops2={ops2}"
        )
        assert ops1 is not ops2, "must return a fresh list per call"

    with test(
        "L1",
        "L1.146",
        "to_paint_ops: no mutation of LayoutModel or its token list",
    ):
        toks = [
            _mk_token_po(0, "a", x=10.0, y=30.0),
            _mk_token_po(1, "b", x=50.0, y=30.0),
        ]
        cur = _mk_cursor_po(x=90.0, y=40.0, h=25.0)
        model = _mk_empty_model_po(tokens=toks, cursor=cur)

        # Snapshot pre-call. The list identity + contents should be
        # unchanged after to_paint_ops.
        pre_len = len(model.tokens)
        pre_ids = [id(t) for t in model.tokens]

        _to_paint_ops(model)

        assert len(model.tokens) == pre_len, "token list length changed"
        assert [id(t) for t in model.tokens] == pre_ids, (
            "token list identity changed (list was mutated)"
        )
        # The caller-provided list should also be untouched (we passed
        # `toks` by reference through _mk_empty_model_po which called
        # `list(tokens)` — this asserts the copy path doesn't leak).
        assert toks == [
            _mk_token_po(0, "a", x=10.0, y=30.0),
            _mk_token_po(1, "b", x=50.0, y=30.0),
        ]

    # -----------------------------------------------------------------------
    # execute() sink — needs a fake canvas + a talon.ui.Rect stub because
    # execute() imports it lazily inside the function body.
    # -----------------------------------------------------------------------

    # talon.ui stub: execute() calls `from talon.ui import Rect`. Provide
    # a lightweight Rect record that matches (x, y, w, h). Register the
    # module before execute() is called.
    _talon_stub_po = _sys.modules.get("talon")
    if _talon_stub_po is None:
        _talon_stub_po = _types_lt.ModuleType("talon")
        _sys.modules["talon"] = _talon_stub_po
    _talon_ui_stub = _sys.modules.get("talon.ui")
    if _talon_ui_stub is None:
        _talon_ui_stub = _types_lt.ModuleType("talon.ui")
        _sys.modules["talon.ui"] = _talon_ui_stub

    class _StubTalonRect:
        __slots__ = ("x", "y", "w", "h", "width", "height")
        def __init__(self, x, y, w, h):
            self.x = x
            self.y = y
            self.w = w
            self.h = h
            self.width = w
            self.height = h
        def __eq__(self, other):
            return (
                isinstance(other, _StubTalonRect)
                and self.x == other.x
                and self.y == other.y
                and self.w == other.w
                and self.h == other.h
            )
        def __repr__(self):
            return f"_StubTalonRect({self.x},{self.y},{self.w},{self.h})"

    _talon_ui_stub.Rect = _StubTalonRect

    # Fake canvas that records every mutation and draw call in order.
    class _RecordingPaint:
        FILL = "FILL"
        STROKE = "STROKE"

        class Style:
            FILL = "FILL"
            STROKE = "STROKE"

        def __init__(self, log):
            self._log = log
            self._color = None
            self._style = None
            self._textsize = None
            self._stroke_width = None

        @property
        def color(self):
            return self._color

        @color.setter
        def color(self, v):
            self._color = v
            self._log.append(("set_color", v))

        @property
        def style(self):
            return self._style

        @style.setter
        def style(self, v):
            self._style = v
            self._log.append(("set_style", v))

        @property
        def textsize(self):
            return self._textsize

        @textsize.setter
        def textsize(self, v):
            self._textsize = v
            self._log.append(("set_textsize", v))

        @property
        def stroke_width(self):
            return self._stroke_width

        @stroke_width.setter
        def stroke_width(self, v):
            self._stroke_width = v
            self._log.append(("set_stroke_width", v))

    class _RecordingCanvas:
        def __init__(self):
            self.log = []
            self.paint = _RecordingPaint(self.log)

        def draw_rect(self, rect):
            self.log.append(("draw_rect", rect.x, rect.y, rect.w, rect.h))

        def draw_text(self, text, x, y):
            self.log.append(("draw_text", text, x, y))

        def draw_line(self, x0, y0, x1, y1):
            self.log.append(("draw_line", x0, y0, x1, y1))

        def draw_circle(self, cx, cy, r):
            self.log.append(("draw_circle", cx, cy, r))

    with test(
        "L1",
        "L1.147",
        "execute: RectOp(stroke=False) → FILL style + color set + draw_rect",
    ):
        canvas = _RecordingCanvas()
        _execute(
            [_RectOp(x=1.0, y=2.0, w=3.0, h=4.0, color="ff00ffaa")],
            canvas,
        )
        # Expected log: set style=FILL, set color, draw_rect
        assert ("set_style", "FILL") in canvas.log, (
            f"expected FILL style set; log={canvas.log}"
        )
        assert ("set_color", "ff00ffaa") in canvas.log, (
            f"expected color set; log={canvas.log}"
        )
        # draw_rect gets a Rect with the op's coords.
        assert ("draw_rect", 1.0, 2.0, 3.0, 4.0) in canvas.log, (
            f"expected draw_rect(1,2,3,4); log={canvas.log}"
        )

    with test(
        "L1",
        "L1.148",
        "execute: RectOp(stroke=True) → STROKE + stroke_width set, then FILL restored",
    ):
        canvas = _RecordingCanvas()
        _execute(
            [_RectOp(
                x=0.0, y=0.0, w=10.0, h=10.0, color="ffffffff",
                stroke=True, stroke_width=2.5,
            )],
            canvas,
        )
        log = canvas.log
        # Sequence check: STROKE set, stroke_width set, color set,
        # draw_rect, FILL restored.
        style_events = [e for e in log if e[0] == "set_style"]
        assert style_events[0] == ("set_style", "STROKE"), (
            f"first style set should be STROKE; got {style_events!r}"
        )
        assert ("set_stroke_width", 2.5) in log
        assert ("draw_rect", 0.0, 0.0, 10.0, 10.0) in log
        assert style_events[-1] == ("set_style", "FILL"), (
            f"last style set should restore FILL; got {style_events!r}"
        )

    with test(
        "L1",
        "L1.149",
        "execute: TextOp → color + textsize set + draw_text with coords",
    ):
        canvas = _RecordingCanvas()
        _execute(
            [_TextOp(x=5.0, y=15.0, text="hello", font_size=14.0, color="00ff00ff")],
            canvas,
        )
        assert ("set_color", "00ff00ff") in canvas.log
        assert ("set_textsize", 14.0) in canvas.log
        assert ("draw_text", "hello", 5.0, 15.0) in canvas.log, (
            f"expected draw_text('hello', 5.0, 15.0); log={canvas.log}"
        )

    with test(
        "L1",
        "L1.150",
        "execute: unknown op type raises TypeError",
    ):
        class _FakeOp:
            pass
        canvas = _RecordingCanvas()
        try:
            _execute([_FakeOp()], canvas)
        except TypeError as e:
            assert "unknown" in str(e).lower() or "PaintOp" in str(e), (
                f"TypeError message should mention unknown op or PaintOp; got {e!r}"
            )
        else:
            raise AssertionError(
                "execute() should raise TypeError on unknown op type"
            )

    # -----------------------------------------------------------------------
    # New PaintOp variants — RoundedRectOp + ShapeGlyphOp (retirement of the
    # env gate). Frozen-dataclass contract + execute() dispatch.
    #
    # RoundedRectOp routes to overlay_kit.draw_rounded_rect (Skia path
    # under the hood). ShapeGlyphOp routes to shim.shapes.draw_hat_shape
    # (SVG path cache). Both need lightweight module stubs so the L1
    # tests don't drag in Talon.
    # -----------------------------------------------------------------------

    _RoundedRectOp = po_mod.RoundedRectOp
    _ShapeGlyphOp = po_mod.ShapeGlyphOp

    with test(
        "L1",
        "L1.151",
        "paint_ops: RoundedRectOp constructs with defaults and is frozen",
    ):
        import dataclasses as _dc_po
        op = _RoundedRectOp(
            x=1.0, y=2.0, w=3.0, h=4.0, radius=2.0, color="ff0000ff"
        )
        assert op.stroke is False
        assert op.stroke_width == 1.0
        assert op.radius == 2.0
        try:
            op.color = "00ff00ff"
        except _dc_po.FrozenInstanceError:
            pass
        else:
            raise AssertionError(
                "RoundedRectOp accepted mutation — should be frozen"
            )

    with test(
        "L1",
        "L1.152",
        "paint_ops: ShapeGlyphOp constructs with defaults and is frozen",
    ):
        import dataclasses as _dc_po
        op = _ShapeGlyphOp(
            shape_name="bolt", cx=50.0, cy=60.0, scale=1.0, color="ffb74d"
        )
        assert op.alpha == 255
        assert op.outline is None
        try:
            op.shape_name = "frame"
        except _dc_po.FrozenInstanceError:
            pass
        else:
            raise AssertionError(
                "ShapeGlyphOp accepted mutation — should be frozen"
            )

    # RoundedRectOp / ShapeGlyphOp execute() dispatch — needs stubs for
    # overlay_kit.draw_rounded_rect and shim.shapes.draw_hat_shape. The
    # sink imports both lazily; we register lightweight fakes in
    # sys.modules that record their calls into the canvas log.

    # utils.overlay_kit stub — provides draw_rounded_rect. The sink
    # imports it via `from ....utils.overlay_kit import draw_rounded_rect`,
    # which resolves relative to the module's `po_lt_pkg.ui.paint_ops`
    # position (4-dots-up = the top-level root that hosts the fake
    # `trillium_talon` package tree). Under the L1 test harness the module
    # was loaded via spec_from_file_location so relative imports use
    # `__package__` = "po_lt_pkg.ui". Four dots up from `po_lt_pkg.ui.paint_ops`
    # is the ANCHOR — Python's importlib requires those parent packages to
    # exist as module objects to resolve the relative path. We supply them
    # as empty ModuleType shells + register a fake `utils.overlay_kit`
    # under the same anchor.

    # Build the parent package chain for `....utils.overlay_kit`:
    # relative import from po_lt_pkg.ui.paint_ops with 4 dots means:
    #   level 4 → strip 4 name components off po_lt_pkg.ui.paint_ops
    #   = ""  (empty; the anchor). Then append "utils.overlay_kit".
    # Under normal Talon load the module lives 4 packages deep; under the
    # L1 harness it lives in po_lt_pkg.ui.paint_ops (only 3 deep). To
    # avoid patching the source, we place `po_lt_pkg` as the anchor with
    # a stub `utils.overlay_kit` subtree AND add empty synthetic parents.
    # The importlib._bootstrap logic for "from A import B" with a level
    # N walks package.__name__ up N times then joins.
    #
    # Simpler path: monkey-patch a stub for the SPECIFIC relative import
    # by pre-registering `po_lt_pkg.utils.overlay_kit` — but that's still
    # 2 levels short. Cleanest: add empty parents (a two-level up from
    # `po_lt_pkg.ui.paint_ops` is `po_lt_pkg`; three-level is empty).
    #
    # For the test, we shortcut: patch the sink to import from a fixed
    # module name via sys.modules trickery. Register the stub under
    # every plausible parent path and let importlib find whichever
    # matches.

    _fake_okit = _types_lt.ModuleType("_fake_overlay_kit")

    _drr_log: list = []

    def _stub_draw_rounded_rect(canvas, rect, radius):
        _drr_log.append(("draw_rounded_rect", rect.x, rect.y, rect.w, rect.h, radius))
        # Match real behavior: it calls c.draw_path under the hood; the
        # recording canvas doesn't have a draw_path so we just log.

    _fake_okit.draw_rounded_rect = _stub_draw_rounded_rect

    # The relative import `from ....utils.overlay_kit import draw_rounded_rect`
    # inside execute() resolves against `po_mod.__package__`. Under the L1
    # harness po_mod was loaded as `po_lt_pkg.ui.paint_ops` so `__package__`
    # is "po_lt_pkg.ui" — level 4 attempts to climb 4 segments up from a
    # 2-segment package, which raises "attempted relative import beyond
    # top-level package". Under Talon the module lives at
    # `trillium_talon.trillium.plugin.prose_overlay.ui.paint_ops` so 4 dots
    # resolves to `trillium_talon.trillium.utils.overlay_kit`.
    #
    # Temporarily deepen po_mod's __package__ to match the Talon layout,
    # register the parent package chain, and register the fake overlay_kit
    # under the resolved path. We restore __package__ after these tests.
    _po_pkg_orig = po_mod.__package__
    _po_pkg_deep = "po_lt_deep_stub.plugin.prose_overlay.ui"
    po_mod.__package__ = _po_pkg_deep
    for _mp in (
        "po_lt_deep_stub",
        "po_lt_deep_stub.plugin",
        "po_lt_deep_stub.plugin.prose_overlay",
        "po_lt_deep_stub.plugin.prose_overlay.ui",
        "po_lt_deep_stub.utils",
    ):
        if _mp not in _sys.modules:
            _sys.modules[_mp] = _types_lt.ModuleType(_mp)
    _sys.modules["po_lt_deep_stub.utils.overlay_kit"] = _fake_okit
    # ..shim.shapes anchor for ShapeGlyphOp — level 2, so we need
    # po_lt_deep_stub.plugin.prose_overlay.shim.shapes
    for _mp in (
        "po_lt_deep_stub.plugin.prose_overlay.shim",
    ):
        if _mp not in _sys.modules:
            _sys.modules[_mp] = _types_lt.ModuleType(_mp)

    with test(
        "L1",
        "L1.153",
        "execute: RoundedRectOp(stroke=False) → FILL + color + draw_rounded_rect",
    ):
        _drr_log.clear()
        canvas = _RecordingCanvas()
        # Give the recording canvas a no-op draw_path so if the real helper
        # ever gets invoked instead of the stub, we don't crash.
        canvas.draw_path = lambda path: canvas.log.append(("draw_path",))
        _execute(
            [_RoundedRectOp(
                x=5.0, y=10.0, w=100.0, h=20.0,
                radius=3.0, color="089ad340",
            )],
            canvas,
        )
        assert ("set_style", "FILL") in canvas.log
        assert ("set_color", "089ad340") in canvas.log
        assert _drr_log, (
            f"expected stub draw_rounded_rect call; drr_log={_drr_log}, canvas.log={canvas.log}"
        )
        assert _drr_log[0][0] == "draw_rounded_rect"
        assert _drr_log[0][1:6] == (5.0, 10.0, 100.0, 20.0, 3.0), (
            f"rounded rect geometry mismatch; got {_drr_log[0]}"
        )

    with test(
        "L1",
        "L1.154",
        "execute: RoundedRectOp(stroke=True) → STROKE, stroke_width, then FILL restored",
    ):
        _drr_log.clear()
        canvas = _RecordingCanvas()
        canvas.draw_path = lambda path: canvas.log.append(("draw_path",))
        _execute(
            [_RoundedRectOp(
                x=0.0, y=0.0, w=10.0, h=10.0,
                radius=2.0, color="ffffffff",
                stroke=True, stroke_width=1.5,
            )],
            canvas,
        )
        style_events = [e for e in canvas.log if e[0] == "set_style"]
        assert style_events[0] == ("set_style", "STROKE"), (
            f"first style set should be STROKE; got {style_events!r}"
        )
        assert ("set_stroke_width", 1.5) in canvas.log
        assert style_events[-1] == ("set_style", "FILL"), (
            f"last style set should restore FILL; got {style_events!r}"
        )

    # shim.shapes stub. The sink imports it via
    # `from ..shim import shapes as _shapes_sink`. Package anchor is
    # `po_lt_pkg.ui.paint_ops` (relative level 2 → `po_lt_pkg`, then
    # `shim.shapes`). Register under po_lt_pkg.shim and po_lt_pkg.shim.shapes.

    _fake_shapes = _types_lt.ModuleType("_fake_shapes")
    _shape_glyph_log: list = []

    def _stub_draw_hat_shape(canvas, shape_name, color, cx, cy, scale=0.75, alpha=255, outline=None):
        _shape_glyph_log.append(
            ("draw_hat_shape", shape_name, color, cx, cy, scale, alpha, outline)
        )

    _fake_shapes.draw_hat_shape = _stub_draw_hat_shape

    # Register under the deepened package path so `from ..shim import shapes`
    # (level 2 from `po_lt_deep_stub.plugin.prose_overlay.ui`) resolves to
    # `po_lt_deep_stub.plugin.prose_overlay.shim.shapes`.
    _sys.modules["po_lt_deep_stub.plugin.prose_overlay.shim.shapes"] = _fake_shapes
    _fake_shim_pkg = _sys.modules["po_lt_deep_stub.plugin.prose_overlay.shim"]
    _fake_shim_pkg.shapes = _fake_shapes

    with test(
        "L1",
        "L1.155",
        "execute: ShapeGlyphOp → shim.shapes.draw_hat_shape called with fields",
    ):
        _shape_glyph_log.clear()
        canvas = _RecordingCanvas()
        _execute(
            [_ShapeGlyphOp(
                shape_name="bolt", cx=50.0, cy=60.0, scale=1.1,
                color="ffb74d", alpha=200, outline="000000",
            )],
            canvas,
        )
        assert _shape_glyph_log, (
            f"expected stub draw_hat_shape call; log={_shape_glyph_log}"
        )
        entry = _shape_glyph_log[0]
        assert entry == (
            "draw_hat_shape", "bolt", "ffb74d", 50.0, 60.0, 1.1, 200, "000000"
        ), f"draw_hat_shape args mismatch; got {entry!r}"

    # Restore po_mod.__package__ so subsequent test files that import
    # po_lt_pkg.ui.paint_ops (currently none, but future L1 tests may)
    # see the original stub-tree path.
    po_mod.__package__ = _po_pkg_orig

    # ----- L1.156-L1.157 — help-zone separator emission -----------------

    def _mk_model_with_help(help_area):
        panel = _Rect_layout(x=0.0, y=0.0, w=1000.0, h=200.0)
        ca = _Rect_layout(x=12.0, y=12.0, w=776.0, h=176.0)
        return _LayoutModelPO(
            panel=panel,
            content_area=ca,
            help_area=help_area,
            tokens=[],
            selection=None,
            flash=None,
            bubbles=[],
            help=None,
            cursor=None,
            target_label="",
            using_fallback=False,
            hints_hidden_by_overflow=False,
        )

    with test(
        "L1",
        "L1.156",
        "to_paint_ops: help_area=None → NO separator LineOp emitted",
    ):
        model = _mk_model_with_help(None)
        ops = _to_paint_ops(model)
        # Empty tokens + no cursor → just the listening TextOp.
        line_ops = [o for o in ops if isinstance(o, _LineOp)]
        assert not line_ops, (
            f"expected no LineOps when help_area is None; got {line_ops!r}"
        )

    _HatMark = _po_layout.HatMark
    _ShapeMark = _po_layout.ShapeMark
    _UnderlineSegment = _po_layout.UnderlineSegment

    def _mk_token_with_hat(index, text, x, y, hat, w=30.0, h=20.0):
        return _TokenLayout(
            index=index,
            text=text,
            rect=_Rect_layout(x=x, y=y, w=w, h=h),
            hat=hat,
            shape=None,
            underline_segments=[],
            flagged=False,
            on_visible_row=True,
        )

    with test(
        "L1",
        "L1.158",
        "to_paint_ops: gray letter hat → single EllipseOp before token TextOp",
    ):
        # Dot position: 2*DOT_RADIUS square. cx=x+DOT_RADIUS, cy=y+DOT_RADIUS.
        r = _DC_PO.DOT_RADIUS
        hat_pos = _Rect_layout(
            x=10.0, y=30.0, w=r * 2.0, h=r * 2.0
        )
        hat = _HatMark(char_index=0, letter="a", color="gray", position=hat_pos)
        tok = _mk_token_with_hat(0, "abc", x=10.0, y=30.0, hat=hat)
        model = _mk_empty_model_po(tokens=[tok])
        ops = _to_paint_ops(model)
        # Expect: [EllipseOp(gray dot), TextOp(token)]
        assert len(ops) == 2, f"expected 2 ops (hat + text); got {len(ops)}: {ops!r}"
        assert isinstance(ops[0], _EllipseOp), (
            f"first op should be hat EllipseOp; got {type(ops[0]).__name__}"
        )
        assert isinstance(ops[1], _TextOp)
        assert ops[0].color == _DC_PO.HAT_COLOR_HEX["gray"]
        assert ops[0].cx == 10.0 + r
        assert ops[0].cy == 30.0 + r
        assert ops[0].rx == r and ops[0].ry == r

    with test(
        "L1",
        "L1.159",
        "to_paint_ops: black letter hat → white outline EllipseOp BEFORE the colored dot",
    ):
        r = _DC_PO.DOT_RADIUS
        hat_pos = _Rect_layout(
            x=50.0, y=100.0, w=r * 2.0, h=r * 2.0
        )
        hat = _HatMark(char_index=0, letter="b", color="black", position=hat_pos)
        tok = _mk_token_with_hat(0, "z", x=50.0, y=100.0, hat=hat)
        model = _mk_empty_model_po(tokens=[tok])
        ops = _to_paint_ops(model)
        # Expect: [EllipseOp(white outer), EllipseOp(black dot), TextOp]
        assert len(ops) == 3, (
            f"expected 3 ops (white outline + black dot + text); got {len(ops)}: {ops!r}"
        )
        outer = ops[0]
        inner = ops[1]
        assert isinstance(outer, _EllipseOp) and isinstance(inner, _EllipseOp)
        assert outer.color == "ffffffff", (
            f"white outline should be ffffffff; got {outer.color!r}"
        )
        assert outer.rx == r + 1, f"outline radius should be DOT_RADIUS+1; got {outer.rx}"
        assert inner.color == _DC_PO.HAT_COLOR_HEX["black"]
        assert inner.rx == r
        assert isinstance(ops[2], _TextOp)

    with test(
        "L1",
        "L1.160",
        "to_paint_ops: no hat → only token TextOp",
    ):
        tok = _mk_token_with_hat(0, "abc", x=10.0, y=30.0, hat=None)
        model = _mk_empty_model_po(tokens=[tok])
        ops = _to_paint_ops(model)
        assert len(ops) == 1, f"expected 1 op (text only) when hat is None; got {len(ops)}: {ops!r}"
        assert isinstance(ops[0], _TextOp)

    def _mk_token_with_shape(index, text, x, y, shape_mark, w=30.0, h=20.0):
        return _TokenLayout(
            index=index,
            text=text,
            rect=_Rect_layout(x=x, y=y, w=w, h=h),
            hat=None,
            shape=shape_mark,
            underline_segments=[],
            flagged=False,
            on_visible_row=True,
        )

    with test(
        "L1",
        "L1.163",
        "to_paint_ops: shape mark → ShapeGlyphOp between hat and token text",
    ):
        r = _DC_PO.DOT_RADIUS
        shape_pos = _Rect_layout(x=20.0, y=30.0, w=r * 2.0, h=r * 2.0)
        shape_mark = _ShapeMark(
            shape_name="bolt",
            position=shape_pos,
            scale=_DC_PO.HOMOPHONE_SHAPE_SCALE,
            color=_DC_PO.HOMOPHONE_SHAPE_COLOR_HEX,
        )
        tok = _mk_token_with_shape(0, "there", 10.0, 30.0, shape_mark)
        model = _mk_empty_model_po(tokens=[tok])
        ops = _to_paint_ops(model)
        # Expect: [ShapeGlyphOp, TextOp] (no hat)
        assert len(ops) == 2, f"expected 2 ops (shape + text); got {len(ops)}: {ops!r}"
        assert isinstance(ops[0], _ShapeGlyphOp), (
            f"first op should be ShapeGlyphOp; got {type(ops[0]).__name__}"
        )
        s = ops[0]
        assert s.shape_name == "bolt"
        assert s.cx == 20.0 + r
        assert s.cy == 30.0 + r
        assert s.scale == _DC_PO.HOMOPHONE_SHAPE_SCALE
        assert s.color == _DC_PO.HOMOPHONE_SHAPE_COLOR_HEX
        assert s.alpha == 255
        assert s.outline is None
        assert isinstance(ops[1], _TextOp)

    def _mk_token_with_underline(index, text, x, y, segments, w=30.0, h=20.0):
        return _TokenLayout(
            index=index,
            text=text,
            rect=_Rect_layout(x=x, y=y, w=w, h=h),
            hat=None,
            shape=None,
            underline_segments=list(segments),
            flagged=True,
            on_visible_row=True,
        )

    with test(
        "L1",
        "L1.161",
        "to_paint_ops: single solid underline segment → one RectOp AFTER token text",
    ):
        seg = _UnderlineSegment(
            x0=10.0, x1=40.0, y=50.0, active=False,
            color=_DC_PO.HOMOPHONE_UNDERLINE_COLOR,
        )
        tok = _mk_token_with_underline(0, "here", 10.0, 30.0, [seg])
        model = _mk_empty_model_po(tokens=[tok])
        ops = _to_paint_ops(model)
        # Expect: [TextOp, RectOp]
        assert len(ops) == 2, f"expected 2 ops; got {len(ops)}: {ops!r}"
        assert isinstance(ops[0], _TextOp)
        r = ops[1]
        assert isinstance(r, _RectOp), (
            f"underline should be RectOp; got {type(r).__name__}"
        )
        assert r.x == 10.0 and r.y == 50.0
        assert r.w == 30.0
        assert r.h == _DC_PO.HOMOPHONE_UNDERLINE_HEIGHT
        assert r.color == _DC_PO.HOMOPHONE_UNDERLINE_COLOR

    with test(
        "L1",
        "L1.162",
        "to_paint_ops: 3-member segmented underline → 3 RectOps, middle one is ACTIVE_HEIGHT",
    ):
        base = _DC_PO.HOMOPHONE_UNDERLINE_COLOR[:6]
        active_color = base + _DC_PO.HOMOPHONE_UNDERLINE_ACTIVE_ALPHA
        inactive_color = base + _DC_PO.HOMOPHONE_UNDERLINE_INACTIVE_ALPHA
        segments = [
            _UnderlineSegment(x0=10.0, x1=18.0, y=50.0, active=False, color=inactive_color),
            _UnderlineSegment(x0=20.0, x1=28.0, y=50.0, active=True, color=active_color),
            _UnderlineSegment(x0=30.0, x1=38.0, y=50.0, active=False, color=inactive_color),
        ]
        tok = _mk_token_with_underline(0, "there", 10.0, 30.0, segments)
        model = _mk_empty_model_po(tokens=[tok])
        ops = _to_paint_ops(model)
        rects = [o for o in ops if isinstance(o, _RectOp)]
        assert len(rects) == 3, (
            f"expected 3 underline RectOps; got {len(rects)}"
        )
        assert rects[0].h == _DC_PO.HOMOPHONE_UNDERLINE_HEIGHT
        assert rects[1].h == _DC_PO.HOMOPHONE_UNDERLINE_ACTIVE_HEIGHT, (
            f"active segment height should be {_DC_PO.HOMOPHONE_UNDERLINE_ACTIVE_HEIGHT}; got {rects[1].h}"
        )
        assert rects[2].h == _DC_PO.HOMOPHONE_UNDERLINE_HEIGHT
        assert rects[1].color == active_color
        assert rects[0].color == inactive_color

    with test(
        "L1",
        "L1.157",
        "to_paint_ops: help_area set → one separator LineOp at help_area.x with SEP_COLOR",
    ):
        ha = _Rect_layout(x=800.0, y=12.0, w=176.0, h=176.0)
        model = _mk_model_with_help(ha)
        ops = _to_paint_ops(model)
        line_ops = [o for o in ops if isinstance(o, _LineOp)]
        assert len(line_ops) == 1, (
            f"expected exactly 1 separator LineOp; got {len(line_ops)}"
        )
        sep = line_ops[0]
        assert sep.x0 == sep.x1 == 800.0, (
            f"separator should be vertical at help_area.x=800; got x0={sep.x0}, x1={sep.x1}"
        )
        expected_y0 = 0.0 + _DC_PO.PANEL_PAD
        expected_y1 = 0.0 + 200.0 - _DC_PO.PANEL_PAD
        assert sep.y0 == expected_y0, (
            f"separator y0 should be panel.y+PANEL_PAD={expected_y0}; got {sep.y0}"
        )
        assert sep.y1 == expected_y1, (
            f"separator y1 should be panel.y+panel.h-PANEL_PAD={expected_y1}; got {sep.y1}"
        )
        assert sep.color == _DC_PO.SEP_COLOR, (
            f"separator color mismatch: expected SEP_COLOR={_DC_PO.SEP_COLOR}, got {sep.color!r}"
        )
        assert sep.width == 1.0

    # ----- L1.164-L1.165 — bubble emission (Step 6 of paint retirement) --

    _BubbleLayout = _po_layout.BubbleLayout

    def _mk_model_with_bubbles(bubbles):
        """Model carrying only bubbles (empty tokens, no cursor)."""
        panel = _Rect_layout(x=0.0, y=0.0, w=1000.0, h=200.0)
        ca = _Rect_layout(x=12.0, y=12.0, w=776.0, h=176.0)
        return _LayoutModelPO(
            panel=panel,
            content_area=ca,
            help_area=None,
            tokens=[],
            selection=None,
            flash=None,
            bubbles=list(bubbles),
            help=None,
            cursor=None,
            target_label="",
            using_fallback=False,
            hints_hidden_by_overflow=False,
        )

    with test(
        "L1",
        "L1.164",
        "to_paint_ops: bubble WITH right chip → 6 ops (2 chips × [rect+text] + backdrop + shape) in order",
    ):
        b = _BubbleLayout(
            token_idx=0,
            x=100.0, y=250.0, w=80.0, h=22.0,
            shape_name="bolt",
            shape_scale=_DC_PO.BUBBLE_SHAPE_SCALE,
            left_chip=("yellow", "their", 30.0),
            right_chip=("blue", "they're", 34.0),
            band=0,
        )
        model = _mk_model_with_bubbles([b])
        ops = _to_paint_ops(model)
        # Filter out listening TextOp (empty tokens branch): we assert on the
        # bubble ops after the placeholder.
        bubble_ops = [o for o in ops if not (isinstance(o, _TextOp) and o.text == "listening...")]
        assert len(bubble_ops) == 6, (
            f"expected 6 bubble ops (left rect+text, right rect+text, backdrop, shape); "
            f"got {len(bubble_ops)}: {[type(o).__name__ for o in bubble_ops]}"
        )
        # Order: left rounded rect → left text → right rounded rect → right text → backdrop ellipse → shape glyph
        assert isinstance(bubble_ops[0], _RoundedRectOp), f"op0 should be left chip RoundedRectOp; got {type(bubble_ops[0]).__name__}"
        assert isinstance(bubble_ops[1], _TextOp) and bubble_ops[1].text == "their"
        assert isinstance(bubble_ops[2], _RoundedRectOp), f"op2 should be right chip RoundedRectOp; got {type(bubble_ops[2]).__name__}"
        assert isinstance(bubble_ops[3], _TextOp) and bubble_ops[3].text == "they're"
        assert isinstance(bubble_ops[4], _EllipseOp), f"op4 should be backdrop EllipseOp; got {type(bubble_ops[4]).__name__}"
        assert bubble_ops[4].color == _DC_PO.BUBBLE_SHAPE_BACKDROP_COLOR
        assert isinstance(bubble_ops[5], _ShapeGlyphOp), f"op5 should be ShapeGlyphOp; got {type(bubble_ops[5]).__name__}"
        assert bubble_ops[5].shape_name == "bolt"
        assert bubble_ops[5].color == _DC_PO.HOMOPHONE_SHAPE_COLOR_HEX
        # Left chip fg: yellow is a LIGHT bg → black text ("000000ff").
        assert bubble_ops[1].color == "000000ff", (
            f"yellow chip fg should be black; got {bubble_ops[1].color!r}"
        )
        # Right chip fg: blue is a DARK bg → white text.
        assert bubble_ops[3].color == "ffffffff", (
            f"blue chip fg should be white; got {bubble_ops[3].color!r}"
        )
        # Left chip bg = HAT_COLOR_HEX["yellow"].
        assert bubble_ops[0].color == _DC_PO.HAT_COLOR_HEX["yellow"]
        # Right chip bg = HAT_COLOR_HEX["blue"].
        assert bubble_ops[2].color == _DC_PO.HAT_COLOR_HEX["blue"]
        # Left chip x/y match bubble.x, chip_y (centered vertically).
        chip_h = _DC_PO.BUBBLE_CHIP_FONT_SIZE + _DC_PO.BUBBLE_CHIP_PAD_Y * 2
        expected_chip_y = 250.0 + (22.0 - chip_h) / 2.0
        assert bubble_ops[0].x == 100.0
        assert bubble_ops[0].y == expected_chip_y
        assert bubble_ops[0].w == 30.0 and bubble_ops[0].h == chip_h

    with test(
        "L1",
        "L1.165",
        "to_paint_ops: bubble WITHOUT right chip (2-member group) → 4 ops (chip + backdrop + shape)",
    ):
        b = _BubbleLayout(
            token_idx=0,
            x=100.0, y=250.0, w=40.0, h=22.0,
            shape_name="frame",
            shape_scale=_DC_PO.BUBBLE_SHAPE_SCALE,
            left_chip=("green", "your", 28.0),
            right_chip=None,
            band=0,
        )
        model = _mk_model_with_bubbles([b])
        ops = _to_paint_ops(model)
        bubble_ops = [o for o in ops if not (isinstance(o, _TextOp) and o.text == "listening...")]
        assert len(bubble_ops) == 4, (
            f"expected 4 bubble ops (left rect+text, backdrop, shape); "
            f"got {len(bubble_ops)}: {[type(o).__name__ for o in bubble_ops]}"
        )
        assert isinstance(bubble_ops[0], _RoundedRectOp)
        assert isinstance(bubble_ops[1], _TextOp) and bubble_ops[1].text == "your"
        assert isinstance(bubble_ops[2], _EllipseOp)
        assert isinstance(bubble_ops[3], _ShapeGlyphOp)
        # Green is DARK → white fg.
        assert bubble_ops[1].color == "ffffffff"

    # ----- L1.166 — selection overlay emission (Step 7 of paint retirement) --

    _SelectionOverlay = _po_layout.SelectionOverlay

    with test(
        "L1",
        "L1.166",
        "to_paint_ops: selection overlay → one RoundedRectOp per rect at 25%% alpha blue, BEFORE token text",
    ):
        # Two selection rects — the model has already computed the
        # per-token rects in row-visible paint order.
        r1 = _Rect_layout(x=10.0, y=50.0, w=40.0, h=18.0)
        r2 = _Rect_layout(x=60.0, y=50.0, w=35.0, h=18.0)
        sel = _SelectionOverlay(rects=[r1, r2])
        # Give the model a single token so we can verify z-order.
        tok = _mk_token_with_hat(0, "abc", x=10.0, y=30.0, hat=None)
        panel = _Rect_layout(x=0.0, y=0.0, w=1000.0, h=200.0)
        ca = _Rect_layout(x=12.0, y=12.0, w=776.0, h=176.0)
        model = _LayoutModelPO(
            panel=panel,
            content_area=ca,
            help_area=None,
            tokens=[tok],
            selection=sel,
            flash=None,
            bubbles=[],
            help=None,
            cursor=None,
            target_label="",
            using_fallback=False,
            hints_hidden_by_overflow=False,
        )
        ops = _to_paint_ops(model)
        # First 2 ops should be the selection RoundedRectOps (25% alpha blue).
        sel_ops = [o for o in ops if isinstance(o, _RoundedRectOp) and o.color == "089ad340"]
        assert len(sel_ops) == 2, (
            f"expected exactly 2 selection RoundedRectOps at 089ad340; "
            f"got {len(sel_ops)}: {[type(o).__name__ for o in ops]}"
        )
        # Order: two selection ops must come BEFORE the token TextOp so
        # tokens paint on top of the highlight.
        first_text = next(
            (i for i, o in enumerate(ops) if isinstance(o, _TextOp) and o.text == "abc"),
            None,
        )
        assert first_text is not None, "token TextOp missing from ops"
        first_sel = next(
            (i for i, o in enumerate(ops) if isinstance(o, _RoundedRectOp) and o.color == "089ad340"),
            None,
        )
        assert first_sel is not None and first_sel < first_text, (
            f"selection ops must precede token text; "
            f"first_sel={first_sel}, first_text={first_text}"
        )
        # Geometry matches model rects exactly.
        assert (sel_ops[0].x, sel_ops[0].y, sel_ops[0].w, sel_ops[0].h) == (10.0, 50.0, 40.0, 18.0)
        assert (sel_ops[1].x, sel_ops[1].y, sel_ops[1].w, sel_ops[1].h) == (60.0, 50.0, 35.0, 18.0)
        # Corner radius 3 (mirrors draw_tokens.py's draw_rounded_rect(..., 3)).
        assert sel_ops[0].radius == 3.0
        assert sel_ops[1].radius == 3.0

    # ----- L1.167 — flash overlay emission (Step 8 of paint retirement) --

    _FlashOverlay = _po_layout.FlashOverlay

    with test(
        "L1",
        "L1.167",
        "to_paint_ops: flash overlay → RoundedRectOps with model-provided color, BEFORE token text",
    ):
        r1 = _Rect_layout(x=10.0, y=50.0, w=40.0, h=18.0)
        r2 = _Rect_layout(x=60.0, y=50.0, w=35.0, h=18.0)
        # Flash color already alpha-rewritten by the builder: "ff00004d".
        flash = _FlashOverlay(rects=[r1, r2], color="ff00004d")
        tok = _mk_token_with_hat(0, "abc", x=10.0, y=30.0, hat=None)
        panel = _Rect_layout(x=0.0, y=0.0, w=1000.0, h=200.0)
        ca = _Rect_layout(x=12.0, y=12.0, w=776.0, h=176.0)
        model = _LayoutModelPO(
            panel=panel,
            content_area=ca,
            help_area=None,
            tokens=[tok],
            selection=None,
            flash=flash,
            bubbles=[],
            help=None,
            cursor=None,
            target_label="",
            using_fallback=False,
            hints_hidden_by_overflow=False,
        )
        ops = _to_paint_ops(model)
        flash_ops = [o for o in ops if isinstance(o, _RoundedRectOp) and o.color == "ff00004d"]
        assert len(flash_ops) == 2, (
            f"expected 2 flash RoundedRectOps; got {len(flash_ops)}: "
            f"{[type(o).__name__ for o in ops]}"
        )
        # Flash must precede token text.
        first_text = next(
            (i for i, o in enumerate(ops) if isinstance(o, _TextOp) and o.text == "abc"),
            None,
        )
        assert first_text is not None
        first_flash = next(
            (i for i, o in enumerate(ops) if isinstance(o, _RoundedRectOp) and o.color == "ff00004d"),
            None,
        )
        assert first_flash is not None and first_flash < first_text, (
            f"flash ops must precede token text; "
            f"first_flash={first_flash}, first_text={first_text}"
        )
        assert flash_ops[0].radius == 3.0
        # Geometry mirrors model rects verbatim.
        assert (flash_ops[0].x, flash_ops[0].y, flash_ops[0].w, flash_ops[0].h) == (10.0, 50.0, 40.0, 18.0)
