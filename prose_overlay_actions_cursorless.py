"""Cursorless dispatch actions for the prose overlay.

Migrated from prose_overlay.py in wave 4. Edit-plan execution and
matcher-misfire diagnostics live in prose_overlay_actions_cursorless_edit.

All state access uses instance.*. Never imports prose_overlay.py.
"""

from typing import Any

from talon import Module, actions

from .internal.instance import instance
from .internal.state import EditKind
from .prose_overlay_actions_core import _recompute_hats
from .prose_overlay_actions_flash import _flash_tokens, _action_color
from .cursorless.resolve import (
    _resolve_target_to_token_range,
    _cursorless_symbol_to_token_index,
    _SUPPORTED_SIMPLE_ACTIONS,
)
from .prose_overlay_actions_cursorless_edit import (
    _po_matcher_misfire,
    _token_char_range,
    _cursor_to_char,
    _apply_edit_plan,
)
from . import prose_overlay_actions_js as _js

mod = Module()


@mod.action_class
class Actions:
    def prose_overlay_run_action(
        cursorless_simple_action: str, cursorless_target: Any
    ):
        """Dispatch a cursorless simple action via the JS shim.

        Bound to `{user.cursorless_simple_action} <user.cursorless_target>` —
        the LIST+CAPTURE shape outranks cursorless's CAPTURE+CAPTURE rule, so
        this fires whenever `user.prose_overlay_active` is set (mutual
        exclusion is enforced upstream).
        """
        action_name = cursorless_simple_action

        if not instance.canvas.is_showing:
            _po_matcher_misfire("run_action", action_name, cursorless_target)
            actions.user.cursorless_command(action_name, cursorless_target)
            return

        if action_name not in _SUPPORTED_SIMPLE_ACTIONS:
            print(f"prose_overlay: unsupported action '{action_name}' (VS Code-only?)")
            return

        token_ranges = _resolve_target_to_token_range(cursorless_target)
        if token_ranges is None:
            print(f"prose_overlay: unresolvable target for action '{action_name}'")
            return

        all_indices: list[int] = []
        for first_idx, last_idx in token_ranges:
            all_indices.extend(range(first_idx, last_idx + 1))

        def _execute():
            # Apply each range in reverse order so earlier indices stay valid.
            for first_idx, last_idx in sorted(token_ranges, reverse=True):
                tokens = instance.buffer.get_tokens()
                text = " ".join(tokens)
                src_start, _ = _token_char_range(first_idx, tokens)
                _, src_end = _token_char_range(last_idx, tokens)
                cursor_char = _cursor_to_char(instance.cursor, tokens, text)
                plan = _js.run_action(
                    action_name, src_start, src_end, text,
                    cursor_anchor_char=cursor_char,
                    cursor_active_char=cursor_char,
                )
                _apply_edit_plan(plan)
                if action_name in ("setSelection", "clearAndSetSelection"):
                    instance.buffer.set_selection(first_idx, last_idx)
            _recompute_hats()
            instance.canvas.refresh()

        _flash_tokens(all_indices, _action_color(action_name), _execute)

    def prose_overlay_run_action_range(action_name: str, anchor: dict, active: dict):
        """Run a range-target action: spans from earlier to later token (anchor past active)."""
        if action_name not in _SUPPORTED_SIMPLE_ACTIONS:
            print(f"prose_overlay: unsupported action '{action_name}' (VS Code-only?)")
            return

        anchor_idx = _cursorless_symbol_to_token_index(anchor)
        active_idx = _cursorless_symbol_to_token_index(active)
        if anchor_idx < 0 or active_idx < 0:
            return

        tokens = instance.buffer.get_tokens()
        text = " ".join(tokens)
        first_idx = min(anchor_idx, active_idx)
        last_idx = max(anchor_idx, active_idx)
        src_start, _ = _token_char_range(first_idx, tokens)
        _, src_end = _token_char_range(last_idx, tokens)
        cursor_char = _cursor_to_char(instance.cursor, tokens, text)
        range_indices = list(range(first_idx, last_idx + 1))

        def _execute():
            plan = _js.run_action(
                action_name, src_start, src_end, text,
                cursor_anchor_char=cursor_char,
                cursor_active_char=cursor_char,
            )
            _apply_edit_plan(plan)
            if action_name in ("setSelection", "clearAndSetSelection"):
                instance.buffer.set_selection(first_idx, last_idx)
            _recompute_hats()
            instance.canvas.refresh()

        _flash_tokens(range_indices, _action_color(action_name), _execute)

    def prose_overlay_apply_formatter(cursorless_target: Any, formatters: str):
        """Apply community-formatter pipeline (user.reformat_text) to the target tokens.

        formatters is a comma-separated list of formatter IDs (e.g. 'SNAKE_CASE',
        'ALL_CAPS,SNAKE_CASE' for CONSTANT_CASE).
        """
        if not instance.canvas.is_showing:
            # Reformat re-dispatch: cursorless's IDE-side reformat entry point
            # lives behind a different rule shape. The matcher misfire signal
            # is the priority here; the no-op is acceptable until #28 lands.
            _po_matcher_misfire(
                "apply_formatter", f"reformat:{formatters}", cursorless_target
            )
            return

        token_ranges = _resolve_target_to_token_range(cursorless_target)
        if token_ranges is None:
            print("prose_overlay: unresolvable target for applyFormatter")
            return

        all_indices: list[int] = []
        for first_idx, last_idx in token_ranges:
            all_indices.extend(range(first_idx, last_idx + 1))

        def _execute():
            # Bracket the multi-range formatter run as one undo step.
            instance.buffer.commit_start("apply_formatter", EditKind.STRUCTURAL)
            try:
                for first_idx, last_idx in sorted(token_ranges, reverse=True):
                    tokens = instance.buffer.get_tokens()
                    source_text = " ".join(tokens[first_idx : last_idx + 1])
                    # reformat_text handles split (de-camel, de-snake) and rejoin.
                    formatted = actions.user.reformat_text(source_text, formatters)
                    # Formatted may be one joined token (snake/camel) or several
                    # space-separated words (title case).
                    new_tokens = formatted.split() if formatted else []
                    current_tokens = list(instance.buffer.get_tokens())
                    current_tokens[first_idx : last_idx + 1] = new_tokens
                    instance.buffer.set_tokens_raw(current_tokens)
            finally:
                instance.buffer.commit_end()
            _recompute_hats()
            instance.canvas.refresh()

        _flash_tokens(all_indices, _action_color("applyFormatter"), _execute)

    def prose_overlay_bring_move(action_name: str, cursorless_target: Any):
        """replaceWithTarget / moveToTarget — source is resolved from
        cursorless_target, destination is the current cursor gap (no-op if no
        active cursor). For 'move' the JS shim returns two edits (insert at
        dest, delete at source); _apply_edit_plan handles ordering.
        """
        if not instance.canvas.is_showing:
            _po_matcher_misfire("bring_move", action_name, cursorless_target)
            actions.user.cursorless_command(action_name, cursorless_target)
            return

        if instance.cursor is None:
            print("prose_overlay: bring/move requires an active cursor position")
            return

        token_ranges = _resolve_target_to_token_range(cursorless_target)
        if token_ranges is None:
            print(f"prose_overlay: unresolvable target for action '{action_name}'")
            return

        all_indices: list[int] = []
        for first_idx, last_idx in token_ranges:
            all_indices.extend(range(first_idx, last_idx + 1))

        def _execute():
            for first_idx, last_idx in sorted(token_ranges, reverse=True):
                tokens = instance.buffer.get_tokens()
                text = " ".join(tokens)
                src_start, _ = _token_char_range(first_idx, tokens)
                _, src_end = _token_char_range(last_idx, tokens)
                cursor_char = _cursor_to_char(instance.cursor, tokens, text)
                plan = _js.run_action(
                    action_name, src_start, src_end, text,
                    dest_start_char=cursor_char,
                    dest_end_char=cursor_char,
                    cursor_anchor_char=cursor_char,
                    cursor_active_char=cursor_char,
                )
                _apply_edit_plan(plan)
            _recompute_hats()
            instance.canvas.refresh()

        _flash_tokens(all_indices, _action_color(action_name), _execute)
