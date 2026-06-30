# Auto-dictation intercept -- when prose_overlay_auto is active, the first spoken
# phrase in dictation mode automatically opens the overlay and routes text into it.
# The tag is off while the overlay is already showing (prose_overlay_active), so
# this rule never conflicts with prose_overlay_dictation.talon.
mode: dictation
tag: user.prose_overlay_auto
-

<user.raw_prose>:
    user.prose_overlay_show()
    user.prose_overlay_add_text(raw_prose)

# Window-name prefix before prose: open overlay, focus window, buffer text.
<user.saved_window_names> <user.raw_prose>:
    user.prose_overlay_show()
    user.prose_overlay_retarget_focus(saved_window_names)
    user.prose_overlay_add_text(raw_prose)
