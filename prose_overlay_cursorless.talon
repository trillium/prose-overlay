# Prose overlay cursorless-style editing commands.
#
# Separate file required -- a .talon file can only have one context header.
#
# Context specificity design:
# This context has MORE matchers than both cursorless.talon and the base
# prose_overlay.talon file. The combination of mode:dictation + mode:command +
# tag:prose_overlay_active + tag:cursorless gives this file the highest
# specificity, so our rules win over conflicting cursorless grammar for
# spoken forms like "bring", "move", "chuck head/tail", etc. Without this
# extra specificity, cursorless would capture these phrases and route them
# to the VS Code command server instead of the prose overlay buffer.
#
# <user.cursorless_target> covers all target shapes:
#   - PrimitiveTarget with decoratedSymbol mark ("chuck air", "take blue bat")
#   - RangeTarget ("chuck air past bat")
#   - PrimitiveTarget with scope modifier ("chuck file", "chuck line")
mode: dictation
mode: command
tag: user.prose_overlay_active
tag: user.cursorless
not tag: user.mouse_clock_showing
not tag: user.clock_ring_showing
-

# ===========================================================================
# Cursorless-native dispatchers (full target resolution via JS shim)
# ===========================================================================

# Any target shape: single hat, range, scope, etc.
{user.cursorless_simple_action} <user.cursorless_target>:
    user.prose_overlay_run_action(cursorless_simple_action, cursorless_target)

# Bring / move to cursor position
{user.cursorless_bring_move_action} <user.cursorless_target>:
    user.prose_overlay_bring_move(cursorless_bring_move_action, cursorless_target)

# ===========================================================================
# Range deletions -- head (start..hat) and tail (hat..end)
# ===========================================================================

chuck head <user.letter>:
    user.prose_overlay_delete_head_hat(letter)
chuck head <user.prose_hat_color> <user.letter>:
    user.prose_overlay_delete_head_hat(letter, prose_hat_color)

chuck tail <user.letter>:
    user.prose_overlay_delete_tail_hat(letter)
chuck tail <user.prose_hat_color> <user.letter>:
    user.prose_overlay_delete_tail_hat(letter, prose_hat_color)

# ===========================================================================
# Range changes -- delete range then enter insertion/change mode
# ===========================================================================

change head <user.letter>:
    user.prose_overlay_change_head_hat(letter)
change head <user.prose_hat_color> <user.letter>:
    user.prose_overlay_change_head_hat(letter, prose_hat_color)

change tail <user.letter>:
    user.prose_overlay_change_tail_hat(letter)
change tail <user.prose_hat_color> <user.letter>:
    user.prose_overlay_change_tail_hat(letter, prose_hat_color)

# ===========================================================================
# Bring -- copy src token to dst position (replace dst with src value)
# All four permutations of optional color prefix on src and dst.
# ===========================================================================

# Neither hat has a color prefix (both default to gray)
bring <user.letter> to <user.letter>:
    user.prose_overlay_bring_hat_to_hat(letter_1, "gray", letter_2, "gray")

# Only source has a color prefix
bring <user.prose_hat_color> <user.letter> to <user.letter>:
    user.prose_overlay_bring_hat_to_hat(letter_1, prose_hat_color, letter_2, "gray")

# Only destination has a color prefix
bring <user.letter> to <user.prose_hat_color> <user.letter>:
    user.prose_overlay_bring_hat_to_hat(letter_1, "gray", letter_2, prose_hat_color)

# Both hats have color prefixes
bring <user.prose_hat_color> <user.letter> to <user.prose_hat_color> <user.letter>:
    user.prose_overlay_bring_hat_to_hat(letter_1, prose_hat_color_1, letter_2, prose_hat_color_2)

# ===========================================================================
# Move -- cut src token and replace dst with it
# All four permutations of optional color prefix on src and dst.
# ===========================================================================

# Neither hat has a color prefix (both default to gray)
move <user.letter> to <user.letter>:
    user.prose_overlay_move_hat_to_hat(letter_1, "gray", letter_2, "gray")

# Only source has a color prefix
move <user.prose_hat_color> <user.letter> to <user.letter>:
    user.prose_overlay_move_hat_to_hat(letter_1, prose_hat_color, letter_2, "gray")

# Only destination has a color prefix
move <user.letter> to <user.prose_hat_color> <user.letter>:
    user.prose_overlay_move_hat_to_hat(letter_1, "gray", letter_2, prose_hat_color)

# Both hats have color prefixes
move <user.prose_hat_color> <user.letter> to <user.prose_hat_color> <user.letter>:
    user.prose_overlay_move_hat_to_hat(letter_1, prose_hat_color_1, letter_2, prose_hat_color_2)

# ===========================================================================
# Cursor jumps -- beginning / end of buffer
# ===========================================================================

pre start:
    user.prose_overlay_cursor_start()
post end:
    user.prose_overlay_cursor_end()

# ===========================================================================
# History navigation
# ===========================================================================

overlay history:
    user.prose_overlay_toggle_history()
history back:
    user.prose_overlay_history_back()
history next:
    user.prose_overlay_history_next()
history pick <number_small>:
    user.prose_overlay_history_pick(number_small)
