# Prose overlay line-ender intercept -- triggers confirm when the user says
# a line-ender word (bravely, gravely, slap, lap) while the overlay is active.
#
# This overrides the default dictation_bravely.talon behavior by matching
# with the prose_overlay_active tag for higher specificity.
mode: dictation
tag: user.prose_overlay_active
-
# Line-ender with preceding text: add text then confirm
<user.raw_prose> {user.dictation_ender}$:
    user.prose_overlay_add_text(raw_prose)
    user.prose_overlay_confirm()

# Line-ender alone: just confirm what's in the buffer
{user.dictation_ender}$: user.prose_overlay_confirm()

# Retarget to a recall window and confirm in one phrase: "edgar bravely"
<user.saved_window_names> {user.dictation_ender}$:
    user.prose_overlay_retarget(saved_window_names)
    user.prose_overlay_confirm()
