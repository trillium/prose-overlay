"""Layer 3 — Talon-stubbed.

Loads ui/test_driver.py via spec_from_file_location AFTER installing
stubs for `talon` + `talon.lib.js` + friends in sys.modules. Verifies
the driver's dispatch routing (queue file → action calls) without
needing a live Talon process.
"""

import importlib.util
import os
import pathlib
import sys
import types

from .common import test, REPO, GREEN, RED, DIM, RESET, TEST_DRIVER_PY


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
