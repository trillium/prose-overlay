# Prose overlay editing commands -- active when the overlay is showing.
# Uses the existing user.letter capture for hat-targeted word deletion.
#
# mode: dictation is included so these commands have equal context specificity
# to the dictation intercept (which has mode: dictation + tag). Without it,
# the intercept's higher specificity causes "overlay speak" etc. to be swallowed
# as raw_prose. Literal rules then beat <user.raw_prose> on rule specificity.
mode: dictation
mode: command
tag: user.prose_overlay_active
-
# Delete a single word by its hat (gray = no color prefix)
chuck <user.letter>: user.prose_overlay_delete_hat(letter)
chuck <user.prose_hat_color> <user.letter>: user.prose_overlay_delete_hat(letter, prose_hat_color)

# Delete from the beginning through a hat's word
chuck past <user.letter>: user.prose_overlay_delete_past_hat(letter)
chuck past <user.prose_hat_color> <user.letter>: user.prose_overlay_delete_past_hat(letter, prose_hat_color)

# Confirm and paste to previous window (alternative to line-enders)
confirm: user.prose_overlay_confirm()

# Speak the buffer contents via the speak TTS tool
# Prefixed "overlay" to avoid dictation ambiguity (matches help text)
overlay speak: user.prose_overlay_speak()

# Dismiss without pasting
# "overlay cancel" would be swallowed by the abort mechanism (last word = "cancel"
# triggers abort_update_phrase before the rule can fire). Use "overlay dismiss" instead.
overlay dismiss: user.prose_overlay_hide()

# Toggle auto-show on all dictation phrases
overlay auto: user.prose_overlay_toggle_auto_dictation()

# Retarget to a recall named window (say the window name while overlay is open)
<user.saved_window_names>: user.prose_overlay_retarget(saved_window_names)

# Undo the last prose overlay edit
overlay undo: user.prose_overlay_undo()

# Help text size
help bigger: user.prose_overlay_help_bigger()
help smaller: user.prose_overlay_help_smaller()

# Paginated help panel
overlay help: user.prose_overlay_help_toggle()
help next: user.prose_overlay_help_next()
help back: user.prose_overlay_help_back()

# Window anchor — scope overlay to a specific window's width/position
^overlay anchor$: user.prose_overlay_set_anchor()
^overlay anchor clear$: user.prose_overlay_clear_anchor()

# Cursor positioning: before a hat
pre <user.letter>: user.prose_overlay_set_cursor_before_hat(letter)
pre <user.prose_hat_color> <user.letter>: user.prose_overlay_set_cursor_before_hat(letter, prose_hat_color)

# Cursor positioning: after a hat
post <user.letter>: user.prose_overlay_set_cursor_after_hat(letter)
post <user.prose_hat_color> <user.letter>: user.prose_overlay_set_cursor_after_hat(letter, prose_hat_color)

# Change mode: delete token at hat and enter insertion mode at that position
change <user.letter>: user.prose_overlay_change_hat(letter)
change <user.prose_hat_color> <user.letter>: user.prose_overlay_change_hat(letter, prose_hat_color)

# Symbol keys: capture spoken-form symbols (dot → ".", slash → "/", etc.) into the buffer.
# Without this, command-mode-only forms like "dot", "point", "semi", "slash", "dash" etc.
# fire key() in the background window instead of routing to the overlay.
# {user.symbol_key} includes all spoken forms — both command-and-dictation and command-only.
{user.symbol_key}: user.prose_overlay_add_text(symbol_key)

# Manual show (for re-opening after dismiss) -- in prose_overlay_start.talon
# Cursorless-grammar actions live in prose_overlay_cursorless.talon (separate file,
# separate context header with higher specificity than cursorless.talon).
