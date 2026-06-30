# Prose overlay dictation intercept -- routes dictation to the overlay buffer
# instead of inserting directly when the overlay is active.
#
# This takes priority over the default dictation_mode.talon rule for raw_prose
# because the tag provides additional specificity.
mode: dictation
tag: user.prose_overlay_active
-

<user.raw_prose>: user.prose_overlay_add_text(raw_prose)

# Number words bypass raw_prose because raw_prose only includes number_prose_prefixed
# ("numeral five"), not number_prose_unprefixed ("five", "42", "three point one four").
# When the overlay is active, unprefixed numbers would otherwise fire via
# numbers_unprefixed.talon (tag: user.unprefixed_numbers, always set) and insert
# directly into the background window via key(). This rule has higher specificity
# (mode: dictation + tag: user.prose_overlay_active > tag: user.unprefixed_numbers alone)
# so it wins and routes all number speech into the overlay buffer instead.
<user.number_string>: user.prose_overlay_add_text(number_string)

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
