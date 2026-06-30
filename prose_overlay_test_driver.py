"""File-driven command queue for headless overlay testing.

Activation paths (any of):
  * env var ``PROSE_OVERLAY_TEST=1`` at Talon launch  (legacy / boot-on)
  * flag file ``~/.talon/prose_overlay_test_enabled`` exists at module import
  * voice command ``overlay test on`` mid-session (action
    ``prose_overlay_test_set(1)``), which creates the flag file as a sticky
    enable so hot-reload survives.

When active, a 200 ms cron tails ``~/.talon/prose_overlay_test_queue.jsonl``
and dispatches each new JSON line as a Talon action call. Lets external
processes (shells, scripts, agents) drive the overlay as if dictating,
without going through the voice loop or the cursorless RPC.

The watcher tracks file position by byte offset; appending lines is
sufficient, no signal needed. Pairs with the always-on debug JSONL
(``prose_overlay_debug.py``) — pipe commands in, tail the debug log out.

Commands (one JSON object per line):

  {"cmd": "show"}
  {"cmd": "add", "text": "hello world there"}
  {"cmd": "add_letters", "letters": "abc"}   # extends last token if prior was also letters
  {"cmd": "insert_format_code", "strings": ["the_quick_brown_fox"]}  # code-formatter route
  {"cmd": "hide"}
  {"cmd": "dump"}
  {"cmd": "delete_hat", "letter": "a"}
  {"cmd": "delete_hat", "letter": "a", "color": "blue"}
  {"cmd": "set_cursor_before_hat", "letter": "a"}
  {"cmd": "set_cursor_after_hat",  "letter": "a"}
  {"cmd": "change_hat", "letter": "a"}
  {"cmd": "confirm"}
  {"cmd": "undo"}
  {"cmd": "homophone_hint", "enabled": true}
  {"cmd": "reset"}              # hard reset all instance state
  {"cmd": "clear_queue"}        # truncate the queue file, reset cursor

Shell shortcut: ``scripts/test-overlay.sh <verb> [args...]`` wraps the JSON.
"""

import json
import os

from talon import Module, actions, cron


_QUEUE = os.path.expanduser("~/.talon/prose_overlay_test_queue.jsonl")
_FLAG_FILE = os.path.expanduser("~/.talon/prose_overlay_test_enabled")
_pos = 0  # byte offset; advance as we consume lines
_job = None
_enabled = False


def _start_cron() -> None:
    global _pos, _job, _enabled
    if _job is not None:
        return
    try:
        _pos = os.path.getsize(_QUEUE)
    except FileNotFoundError:
        _pos = 0
    _job = cron.interval("200ms", _tick)
    _enabled = True
    print(f"prose_overlay test: driver ACTIVE — append commands to {_QUEUE}")


def _stop_cron() -> None:
    global _job, _enabled
    if _job is None:
        return
    cron.cancel(_job)
    _job = None
    _enabled = False
    print("prose_overlay test: driver INACTIVE")


mod = Module()


@mod.action_class
class Actions:
    def prose_overlay_test_set(enabled: int):
        """Enable (1) or disable (0) the headless test driver at runtime.
        Enabling persists across hot-reload via ~/.talon/prose_overlay_test_enabled.
        """
        if enabled:
            try:
                open(_FLAG_FILE, "w").close()
            except OSError as e:
                print(f"prose_overlay test: flag-file create failed: {e}")
            _start_cron()
        else:
            try:
                if os.path.exists(_FLAG_FILE):
                    os.remove(_FLAG_FILE)
            except OSError as e:
                print(f"prose_overlay test: flag-file remove failed: {e}")
            _stop_cron()

    def prose_overlay_test_status():
        """Print whether the headless test driver is currently active."""
        flag = os.path.exists(_FLAG_FILE)
        env = os.environ.get("PROSE_OVERLAY_TEST") == "1"
        print(
            f"prose_overlay test: enabled={_enabled} "
            f"(flag_file={flag}, env={env}, queue={_QUEUE})"
        )


def _dispatch(cmd: dict) -> None:
    name = cmd.get("cmd")
    print(f"prose_overlay test: dispatch {name!r} {cmd}")
    try:
        if name == "show":
            actions.user.prose_overlay_show()
        elif name == "add":
            actions.user.prose_overlay_add_text(cmd.get("text", ""))
        elif name == "add_letters":
            actions.user.prose_overlay_add_letters(cmd.get("letters", ""))
        elif name == "insert_format_code":
            actions.user.prose_overlay_insert_format_code(cmd.get("strings", []))
        elif name == "hide":
            actions.user.prose_overlay_hide()
        elif name == "dump":
            actions.user.prose_overlay_dump_state()
        elif name == "delete_hat":
            actions.user.prose_overlay_delete_hat(cmd["letter"], cmd.get("color", "gray"))
        elif name == "set_cursor_before_hat":
            actions.user.prose_overlay_set_cursor_before_hat(cmd["letter"], cmd.get("color", "gray"))
        elif name == "set_cursor_after_hat":
            actions.user.prose_overlay_set_cursor_after_hat(cmd["letter"], cmd.get("color", "gray"))
        elif name == "change_hat":
            actions.user.prose_overlay_change_hat(cmd["letter"], cmd.get("color", "gray"))
        elif name == "confirm":
            actions.user.prose_overlay_confirm()
        elif name == "undo":
            actions.user.prose_overlay_undo()
        elif name == "homophone_hint":
            actions.user.prose_overlay_set_homophone_hint(1 if cmd.get("enabled") else 0)
        elif name == "reset":
            actions.user.prose_overlay_reset()
        elif name == "clear_queue":
            global _pos
            open(_QUEUE, "w").close()
            _pos = 0
        else:
            print(f"prose_overlay test: unknown cmd {name!r}")
    except Exception as e:
        print(f"prose_overlay test: {name!r} failed: {e}")


def _tick() -> None:
    global _pos
    try:
        size = os.path.getsize(_QUEUE)
    except FileNotFoundError:
        return
    if size <= _pos:
        return
    try:
        with open(_QUEUE, "r") as f:
            f.seek(_pos)
            chunk = f.read()
            _pos = f.tell()
    except OSError as e:
        print(f"prose_overlay test: queue read failed: {e}")
        return

    for raw in chunk.splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        try:
            cmd = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"prose_overlay test: bad JSON ({e}): {raw[:80]}")
            continue
        _dispatch(cmd)


if os.environ.get("PROSE_OVERLAY_TEST") == "1" or os.path.exists(_FLAG_FILE):
    _start_cron()
