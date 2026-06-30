# Prose history panel commands -- active while the history panel is showing.
mode: command
mode: dictation
tag: user.prose_history_active
-

^history next$: user.prose_overlay_history_next()
^history back$: user.prose_overlay_history_back()
^history pick <number_small>$: user.prose_overlay_history_pick(number_small)
^overlay dismiss$: user.prose_overlay_hide_history()
