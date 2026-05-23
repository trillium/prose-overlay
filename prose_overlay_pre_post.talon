# Prose overlay — pre/post file cursor navigation.
# Moves the insertion cursor to the start or end of the buffer.
mode: dictation
mode: command
tag: user.prose_overlay_active
-
pre file: user.prose_overlay_cursor_start()
post file: user.prose_overlay_cursor_end()
