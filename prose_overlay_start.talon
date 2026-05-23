# Prose overlay start + global controls -- available outside the overlay.
# prose_overlay_show() auto-enables dictation mode so speech routes to the buffer immediately.
# Both command and dictation mode so "overlay auto" is reachable regardless of current mode.
mode: command
mode: dictation
-
^prose overlay$: user.prose_overlay_show()
^overlay auto$: user.prose_overlay_toggle_auto_dictation()
^prose history$: user.prose_overlay_toggle_history()
^overlay top$: user.prose_overlay_set_anchor_position("top")
^overlay bottom$: user.prose_overlay_set_anchor_position("bottom")
