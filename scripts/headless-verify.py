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
STATE_PY = REPO / "prose_overlay_state.py"
HAT_JS = REPO / "js" / "prose_allocate_hats.js"
TEST_DRIVER_PY = REPO / "prose_overlay_test_driver.py"

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

def main() -> int:
    print("Headless verify — see docs/HEADLESS_VERIFY_PLAN.md\n")
    run_layer_1()
    run_layer_2()
    run_layer_3()

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
