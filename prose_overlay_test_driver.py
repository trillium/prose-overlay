"""File-driven command queue for headless overlay testing.

Gated on env var ``PROSE_OVERLAY_TEST=1`` (default off — production users
don't need a polling cron). When enabled, a 200 ms cron tails
``~/.talon/prose_overlay_test_queue.jsonl`` and dispatches each new JSON line
as a Talon action call. Lets external processes (shells, scripts, agents)
drive the overlay as if dictating, without going through the voice loop or
the cursorless RPC.

The watcher tracks file position by byte offset; appending lines is
sufficient, no signal needed. Pairs with the always-on debug JSONL
(``prose_overlay_debug.py``) — pipe commands in, tail the debug log out.

Commands (one JSON object per line):

  {"cmd": "show"}
  {"cmd": "add", "text": "hello world there"}
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
  {"cmd": "clear_queue"}        # truncate the queue file, reset cursor

Shell shortcut: ``scripts/test-overlay.sh <verb> [args...]`` wraps the JSON.
"""

import json
import os

from talon import actions, cron


_QUEUE = os.path.expanduser("~/.talon/prose_overlay_test_queue.jsonl")
_pos = 0  # byte offset; advance as we consume lines
_job = None


def _dispatch(cmd: dict) -> None:
    name = cmd.get("cmd")
    print(f"prose_overlay test: dispatch {name!r} {cmd}")
    try:
        if name == "show":
            actions.user.prose_overlay_show()
        elif name == "add":
            actions.user.prose_overlay_add_text(cmd.get("text", ""))
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


if os.environ.get("PROSE_OVERLAY_TEST") == "1":
    # Start the cursor at end-of-file so we don't re-process queue contents
    # that were sitting around from a prior Talon session.
    try:
        _pos = os.path.getsize(_QUEUE)
    except FileNotFoundError:
        _pos = 0
    _job = cron.interval("200ms", _tick)
    print(f"prose_overlay test: driver active — append commands to {_QUEUE}")
