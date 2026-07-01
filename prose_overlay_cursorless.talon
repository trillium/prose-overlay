# Prose overlay cursorless-style editing commands.
#
# Separate file required -- a .talon file can only have one context header.
#
# Context activates anywhere the prose overlay canvas is showing — VSCode,
# Terminal, browser, anywhere. The cursorless-shape rules below are
# answered by our action bodies (which use a JS shim to resolve targets
# against the overlay buffer, not the host app).
#
# Mutual exclusion with cursorless.talon: cursorless.talon's matcher carries
# `not tag: user.prose_overlay_active`, so cursorless's context is INACTIVE
# whenever PO is showing. That means our rule bodies always win the grammar
# binding for the duplicate-shape rule
# `<user.cursorless_action_or_ide_command> <user.cursorless_target>` whenever
# PO is up — including outside VSCode where `user.cursorless` isn't set.
#
# Requiring `tag: user.cursorless` here would gate our context to VSCode
# only; in Terminal+PO the rule would route to cursorless.talon:10 and
# error out in the command server. So we deliberately do NOT require it.
#
# <user.cursorless_target> covers all target shapes:
#   - PrimitiveTarget with decoratedSymbol mark ("chuck air", "take blue bat")
#   - RangeTarget ("chuck air past bat")
#   - PrimitiveTarget with scope modifier ("chuck file", "chuck line")
#
# <user.cursorless_swap_targets> covers the two-target swap shape:
#   - `[<target>] with <target>` — implicit source at cursor if omitted.
mode: dictation
mode: command
tag: user.prose_overlay_active
and not tag: user.mouse_clock_showing
and not tag: user.clock_ring_showing
-

# ===========================================================================
# Cursorless-native dispatchers (full target resolution via JS shim)
# ===========================================================================

# LIST + CAPTURE shape — beats cursorless's CAPTURE + CAPTURE rule
# (`<user.cursorless_action_or_ide_command> <user.cursorless_target>`) on
# grammar-specificity tie-break. LIST `{...}` is more specific than
# CAPTURE `<...>`, so whenever our context is active this rule wins the
# binding for the same spoken-form surface, and the phrase routes to our
# JS shim instead of cursorless's command server.
#
# Mutual exclusion: cursorless.talon excludes `user.prose_overlay_active`,
# so cursorless's rule is only ever in the grammar when PO is off — meaning
# we don't shadow cursorless outside the overlay. Safe.
# This command is the issue
{user.cursorless_simple_action} <user.cursorless_target>:
    user.prose_overlay_run_action(cursorless_simple_action, cursorless_target)

# # # Bring / move to cursor position
{user.cursorless_bring_move_action} <user.cursorless_target>:
    user.prose_overlay_bring_move(cursorless_bring_move_action, cursorless_target)

# Swap two targets (wishlist #3). cursorless-talon's swap.py exposes
# cursorless_swap_targets as a two-target capture (`[<target>] with <target>`).
# Rule shape matches cursorless.talon C3 — LIST + CAPTURE so it outranks the
# generic action rule on grammar-specificity tie-break whenever our context
# is active.
{user.cursorless_swap_action} <user.cursorless_swap_targets>:
    user.prose_overlay_swap(cursorless_swap_targets)

# # # Reformat target with formatter(s) (e.g. "format snake air", "format camel air past bat")
{user.cursorless_reformat_action} <user.formatters> at <user.cursorless_target>:
    user.prose_overlay_apply_formatter(cursorless_target, formatters)

# Wrap target with a paired delimiter (wishlist #5). Matches cursorless.talon C7:
#   <wrapper_paired_delimiter> {wrap_action} <target>
# e.g. "round wrap air" surrounds hat 'a' with parens, "curly wrap fox past bat"
# surrounds the range with curly braces. Reuses cursorless-talon's existing
# `cursorless_wrapper_paired_delimiter` capture (paired_delimiter.py:45-56) so
# the 12-entry cursorless delimiter vocabulary flows through unchanged; the
# prose-side action rejects any wrap_action other than `wrapWithPairedDelimiter`
# (VSCode-only `rewrap` is not implementable on the flat prose buffer).
<user.cursorless_wrapper_paired_delimiter> {user.cursorless_wrap_action} <user.cursorless_target>:
    user.prose_overlay_wrap_with_paired_delimiter(cursorless_wrap_action, cursorless_target, cursorless_wrapper_paired_delimiter)

# ===========================================================================
# Range deletions -- head (start..hat) and tail (hat..end)
# ===========================================================================

chuck head <user.letter>: user.prose_overlay_delete_head_hat(letter)
chuck head <user.prose_hat_color> <user.letter>:
    user.prose_overlay_delete_head_hat(letter, prose_hat_color)

chuck tail <user.letter>: user.prose_overlay_delete_tail_hat(letter)
chuck tail <user.prose_hat_color> <user.letter>:
    user.prose_overlay_delete_tail_hat(letter, prose_hat_color)

# ===========================================================================
# Range changes -- delete range then enter insertion/change mode
# ===========================================================================

change head <user.letter>: user.prose_overlay_change_head_hat(letter)
change head <user.prose_hat_color> <user.letter>:
    user.prose_overlay_change_head_hat(letter, prose_hat_color)

change tail <user.letter>: user.prose_overlay_change_tail_hat(letter)
change tail <user.prose_hat_color> <user.letter>:
    user.prose_overlay_change_tail_hat(letter, prose_hat_color)


# ===========================================================================
# Cursor jumps -- beginning / end of buffer
# ===========================================================================

pre start: user.prose_overlay_cursor_start()
post end: user.prose_overlay_cursor_end()

# ===========================================================================
# History navigation
# ===========================================================================

overlay history: user.prose_overlay_toggle_history()
history back: user.prose_overlay_history_back()
history next: user.prose_overlay_history_next()
history pick <number_small>: user.prose_overlay_history_pick(number_small)
