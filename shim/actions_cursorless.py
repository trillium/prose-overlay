"""Cursorless dispatch actions for the prose overlay.

Migrated from prose_overlay.py in wave 4. Edit-plan execution and
matcher-misfire diagnostics live in prose_overlay_actions_cursorless_edit.

All state access uses instance.*. Never imports prose_overlay.py.
"""

from typing import Any

from talon import Module, actions

from ..internal.instance import instance
from ..internal.state import EditKind
from .actions_core import _recompute_hats
from ..ui.actions_flash import _flash_tokens, _action_color
from ..cursorless.resolve import (
    _resolve_target_to_token_range,
    _cursorless_symbol_to_token_index,
    _SUPPORTED_SIMPLE_ACTIONS,
)
from .actions_cursorless_edit import (
    _po_matcher_misfire,
    _token_char_range,
    _cursor_to_char,
    _apply_edit_plan,
)
from . import actions_js as _js

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

        if not instance.runtime.canvas.is_showing:
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

        # Wishlist #13 Reverse — multi-target action. All ranges are
        # extracted, texts reversed, then written back in ONE JS call so the
        # text-order swap happens atomically. Bailing to the per-range loop
        # would extract-and-replace each range in isolation and never swap
        # texts between them.
        if action_name == "reverseTargets":
            def _execute_reverse():
                tokens = instance.state.buffer.get_tokens()
                text = " ".join(tokens)
                char_ranges: list[tuple[int, int]] = []
                for first_idx, last_idx in token_ranges:
                    start, _ = _token_char_range(first_idx, tokens)
                    _, end = _token_char_range(last_idx, tokens)
                    char_ranges.append((start, end))
                cursor_char = _cursor_to_char(instance.state.cursor, tokens, text)
                plan = _js.run_action_multi(
                    action_name, char_ranges, text,
                    cursor_anchor_char=cursor_char,
                    cursor_active_char=cursor_char,
                )
                _apply_edit_plan(plan)
                _recompute_hats()
                instance.runtime.canvas.refresh()

            _flash_tokens(all_indices, _action_color(action_name), _execute_reverse)
            return

        def _execute():
            # Apply each range in reverse order so earlier indices stay valid.
            for first_idx, last_idx in sorted(token_ranges, reverse=True):
                tokens = instance.state.buffer.get_tokens()
                text = " ".join(tokens)
                src_start, _ = _token_char_range(first_idx, tokens)
                _, src_end = _token_char_range(last_idx, tokens)
                cursor_char = _cursor_to_char(instance.state.cursor, tokens, text)
                plan = _js.run_action(
                    action_name, src_start, src_end, text,
                    cursor_anchor_char=cursor_char,
                    cursor_active_char=cursor_char,
                )
                _apply_edit_plan(plan)
                if action_name in ("setSelection", "clearAndSetSelection"):
                    instance.state.buffer.set_selection(first_idx, last_idx)
            _recompute_hats()
            instance.runtime.canvas.refresh()

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

        tokens = instance.state.buffer.get_tokens()
        text = " ".join(tokens)
        first_idx = min(anchor_idx, active_idx)
        last_idx = max(anchor_idx, active_idx)
        src_start, _ = _token_char_range(first_idx, tokens)
        _, src_end = _token_char_range(last_idx, tokens)
        cursor_char = _cursor_to_char(instance.state.cursor, tokens, text)
        range_indices = list(range(first_idx, last_idx + 1))

        def _execute():
            plan = _js.run_action(
                action_name, src_start, src_end, text,
                cursor_anchor_char=cursor_char,
                cursor_active_char=cursor_char,
            )
            _apply_edit_plan(plan)
            if action_name in ("setSelection", "clearAndSetSelection"):
                instance.state.buffer.set_selection(first_idx, last_idx)
            _recompute_hats()
            instance.runtime.canvas.refresh()

        _flash_tokens(range_indices, _action_color(action_name), _execute)

    def prose_overlay_apply_formatter(cursorless_target: Any, formatters: str):
        """Apply community-formatter pipeline (user.reformat_text) to the target tokens.

        formatters is a comma-separated list of formatter IDs (e.g. 'SNAKE_CASE',
        'ALL_CAPS,SNAKE_CASE' for CONSTANT_CASE).
        """
        if not instance.runtime.canvas.is_showing:
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
            instance.state.buffer.commit_start("apply_formatter", EditKind.STRUCTURAL)
            try:
                for first_idx, last_idx in sorted(token_ranges, reverse=True):
                    tokens = instance.state.buffer.get_tokens()
                    source_text = " ".join(tokens[first_idx : last_idx + 1])
                    # reformat_text handles split (de-camel, de-snake) and rejoin.
                    formatted = actions.user.reformat_text(source_text, formatters)
                    # Formatted may be one joined token (snake/camel) or several
                    # space-separated words (title case).
                    new_tokens = formatted.split() if formatted else []
                    current_tokens = list(instance.state.buffer.get_tokens())
                    current_tokens[first_idx : last_idx + 1] = new_tokens
                    instance.state.buffer.set_tokens_raw(current_tokens)
            finally:
                instance.state.buffer.commit_end()
            _recompute_hats()
            instance.runtime.canvas.refresh()

        _flash_tokens(all_indices, _action_color("applyFormatter"), _execute)

    def prose_overlay_swap(cursorless_swap_targets: Any):
        """Exchange the texts of two resolved targets (wishlist #3 Swap).

        Bound to the dedicated rule in prose_overlay_cursorless.talon:
          {user.cursorless_swap_action} <user.cursorless_swap_targets>:
            user.prose_overlay_swap(cursorless_swap_targets)

        cursorless_swap_targets is a SwapTargets dataclass from
        cursorless-talon (src/actions/swap.py); it exposes .target1 and
        .target2 attributes, each a CursorlessTarget. If target1 is an
        ImplicitTarget (single-target spoken form `swap with drum`),
        we resolve it against the cursor via the standard
        _resolve_target_to_token_range path.

        Multi-range targets (each side is a RangeTarget or ListTarget)
        collapse into a single (first_idx, last_idx) span per side,
        matching how cursorless's Swap treats each target as one text
        blob. Multi-range on EACH side would need N-way swap semantics
        which cursorless itself does not ship; see docs/BUNDLE_REST_SCOPE.md
        §2 #3.
        """
        target1 = getattr(cursorless_swap_targets, "target1", None)
        target2 = getattr(cursorless_swap_targets, "target2", None)
        if target1 is None or target2 is None:
            print("prose_overlay: swap requires two targets — got malformed capture")
            return

        if not instance.runtime.canvas.is_showing:
            _po_matcher_misfire("swap", "swapTargets", cursorless_swap_targets)
            actions.user.cursorless_command("swapTargets", cursorless_swap_targets)
            return

        r1 = _resolve_target_to_token_range(target1)
        r2 = _resolve_target_to_token_range(target2)
        if r1 is None or r2 is None:
            print("prose_overlay: unresolvable target for swap")
            return

        # Collapse each side to one span — the leftmost start and the
        # rightmost end across whatever ranges the side resolves to.
        first1 = min(a for a, _ in r1)
        last1 = max(b for _, b in r1)
        first2 = min(a for a, _ in r2)
        last2 = max(b for _, b in r2)

        all_indices = list(range(first1, last1 + 1)) + list(range(first2, last2 + 1))

        def _execute():
            tokens = instance.state.buffer.get_tokens()
            text = " ".join(tokens)
            s1, _ = _token_char_range(first1, tokens)
            _, e1 = _token_char_range(last1, tokens)
            s2, _ = _token_char_range(first2, tokens)
            _, e2 = _token_char_range(last2, tokens)
            cursor_char = _cursor_to_char(instance.state.cursor, tokens, text)
            plan = _js.run_action(
                "swapTargets", s1, e1, text,
                dest_start_char=s2, dest_end_char=e2,
                cursor_anchor_char=cursor_char,
                cursor_active_char=cursor_char,
            )
            _apply_edit_plan(plan)
            _recompute_hats()
            instance.runtime.canvas.refresh()

        _flash_tokens(all_indices, _action_color("swapTargets"), _execute)

    def prose_overlay_wrap_with_paired_delimiter(
        cursorless_wrap_action: str,
        cursorless_target: Any,
        cursorless_wrapper_paired_delimiter: list,
    ):
        """Wrap the resolved target with a paired delimiter (wishlist #5).

        Bound to the C7 rule shape mirrored from cursorless.talon:
          <user.cursorless_wrapper_paired_delimiter>
          {user.cursorless_wrap_action}
          <user.cursorless_target>

        The three captures/list correspond to:
        - cursorless_wrap_action:               str from LIST — for prose overlay
                                                only `wrapWithPairedDelimiter`
                                                is supported (upstream also
                                                exposes `rewrap`, which is a
                                                Cursorless-VSCode-only edit
                                                that requires round-tripping
                                                the current surrounding pair
                                                — out of scope on the flat
                                                prose buffer).
        - cursorless_wrapper_paired_delimiter:  list[str] of [left, right] from
                                                cursorless-talon's
                                                paired_delimiter capture (see
                                                paired_delimiter.py:45-56).
        - cursorless_target:                    the target dict — resolved via
                                                the standard target-resolution
                                                path.

        Multi-range targets (list or range) wrap EACH resolved range with the
        same delimiter pair, one wrap per range — matches upstream's `Wrap.ts`
        behaviour where the action applies to every target the resolver
        returns. Applied in reverse document order so earlier offsets stay
        valid as later ones shift.
        """
        # Rewrap is a VSCode-specific edit path (round-trips the current
        # surrounding pair via the language service). Not supported on prose.
        # Same escape route as the other unsupported actions — dispatch back
        # to cursorless proper.
        if cursorless_wrap_action != "wrapWithPairedDelimiter":
            print(
                f"prose_overlay: unsupported wrap action "
                f"'{cursorless_wrap_action}' (VSCode-only?)"
            )
            return

        if not instance.runtime.canvas.is_showing:
            _po_matcher_misfire(
                "wrap_with_paired_delimiter",
                cursorless_wrap_action,
                cursorless_target,
            )
            actions.user.cursorless_command(
                cursorless_wrap_action,
                cursorless_target,
                cursorless_wrapper_paired_delimiter,
            )
            return

        # paired_delimiter capture returns list[str] of length 2 (see
        # ~/.talon/user/cursorless-talon/src/paired_delimiter.py:56). Anything
        # else means the capture got remapped — bail loudly rather than
        # silently truncating.
        if (
            not isinstance(cursorless_wrapper_paired_delimiter, (list, tuple))
            or len(cursorless_wrapper_paired_delimiter) != 2
        ):
            print(
                "prose_overlay: wrap expected [left, right] delimiter pair, "
                f"got {cursorless_wrapper_paired_delimiter!r}"
            )
            return
        left = str(cursorless_wrapper_paired_delimiter[0])
        right = str(cursorless_wrapper_paired_delimiter[1])

        token_ranges = _resolve_target_to_token_range(cursorless_target)
        if token_ranges is None:
            print(
                f"prose_overlay: unresolvable target for wrap "
                f"({cursorless_wrap_action})"
            )
            return

        all_indices: list[int] = []
        for first_idx, last_idx in token_ranges:
            all_indices.extend(range(first_idx, last_idx + 1))

        def _execute():
            # Bracket the multi-range wrap as one STRUCTURAL undo step. Pass
            # manage_undo_group=False to each _apply_edit_plan call so it
            # doesn't seal our outer bracket mid-loop (which would produce
            # one undo record per range instead of one atomic wrap).
            instance.state.buffer.commit_start("wrap", EditKind.STRUCTURAL)
            try:
                for first_idx, last_idx in sorted(token_ranges, reverse=True):
                    tokens = instance.state.buffer.get_tokens()
                    text = " ".join(tokens)
                    src_start, _ = _token_char_range(first_idx, tokens)
                    _, src_end = _token_char_range(last_idx, tokens)
                    cursor_char = _cursor_to_char(instance.state.cursor, tokens, text)
                    plan = _js.run_action_wrap(
                        src_start, src_end, text, left, right,
                        cursor_anchor_char=cursor_char,
                        cursor_active_char=cursor_char,
                    )
                    _apply_edit_plan(plan, manage_undo_group=False)
            finally:
                instance.state.buffer.commit_end()
            _recompute_hats()
            instance.runtime.canvas.refresh()

        _flash_tokens(all_indices, _action_color("wrapWithPairedDelimiter"), _execute)

    def prose_overlay_bring_move(action_name: str, cursorless_target: Any):
        """replaceWithTarget / moveToTarget — source is resolved from
        cursorless_target, destination is the current cursor gap (no-op if no
        active cursor). For 'move' the JS shim returns two edits (insert at
        dest, delete at source); _apply_edit_plan handles ordering.
        """
        if not instance.runtime.canvas.is_showing:
            _po_matcher_misfire("bring_move", action_name, cursorless_target)
            actions.user.cursorless_command(action_name, cursorless_target)
            return

        if instance.state.cursor is None:
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
                tokens = instance.state.buffer.get_tokens()
                text = " ".join(tokens)
                src_start, _ = _token_char_range(first_idx, tokens)
                _, src_end = _token_char_range(last_idx, tokens)
                cursor_char = _cursor_to_char(instance.state.cursor, tokens, text)
                plan = _js.run_action(
                    action_name, src_start, src_end, text,
                    dest_start_char=cursor_char,
                    dest_end_char=cursor_char,
                    cursor_anchor_char=cursor_char,
                    cursor_active_char=cursor_char,
                )
                _apply_edit_plan(plan)
            _recompute_hats()
            instance.runtime.canvas.refresh()

        _flash_tokens(all_indices, _action_color(action_name), _execute)
