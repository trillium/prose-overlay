# Prose overlay dictation intercept -- routes dictation to the overlay buffer
# instead of inserting directly when the overlay is active.
#
# This takes priority over the default dictation_mode.talon rule for raw_prose
# because the tag provides additional specificity.
mode: dictation
tag: user.prose_overlay_active
-
<user.raw_prose>: user.prose_overlay_add_text(raw_prose)

# Window-name prefix: focus the window immediately, then buffer the prose.
# "edgar hello world" → switches to edgar, adds "hello world" to buffer.
<user.saved_window_names> <user.raw_prose>:
    user.prose_overlay_retarget_focus(saved_window_names)
    user.prose_overlay_add_text(raw_prose)

# Compound editing + prose: consume the whole phrase as one rule.
# Without these, Talon chains "change trap" + "word force" as separate commands —
# "word" gets caught by a Cursorless scope rule and "force" leaks to the window.
change <user.letter> <user.raw_prose>:
    user.prose_overlay_change_hat(letter)
    user.prose_overlay_add_text(raw_prose)
change <user.prose_hat_color> <user.letter> <user.raw_prose>:
    user.prose_overlay_change_hat(letter, prose_hat_color)
    user.prose_overlay_add_text(raw_prose)
pre <user.letter> <user.raw_prose>:
    user.prose_overlay_set_cursor_before_hat(letter)
    user.prose_overlay_add_text(raw_prose)
pre <user.prose_hat_color> <user.letter> <user.raw_prose>:
    user.prose_overlay_set_cursor_before_hat(letter, prose_hat_color)
    user.prose_overlay_add_text(raw_prose)
post <user.letter> <user.raw_prose>:
    user.prose_overlay_set_cursor_after_hat(letter)
    user.prose_overlay_add_text(raw_prose)
post <user.prose_hat_color> <user.letter> <user.raw_prose>:
    user.prose_overlay_set_cursor_after_hat(letter, prose_hat_color)
    user.prose_overlay_add_text(raw_prose)
