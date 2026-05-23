# Prose overlay — bring/move between two hat targets.
# bring <src> to <dst>: copy src token text, replace dst token with it
# move <src> to <dst>: cut src token, replace dst token with it
mode: dictation
mode: command
tag: user.prose_overlay_active
-
bring <user.letter> to <user.letter>:
    user.prose_overlay_bring_hat_to_hat(letter_1, "gray", letter_2, "gray")
bring <user.prose_hat_color> <user.letter> to <user.letter>:
    user.prose_overlay_bring_hat_to_hat(letter, prose_hat_color, letter_1, "gray")
bring <user.letter> to <user.prose_hat_color> <user.letter>:
    user.prose_overlay_bring_hat_to_hat(letter_1, "gray", letter, prose_hat_color)
bring <user.prose_hat_color> <user.letter> to <user.prose_hat_color> <user.letter>:
    user.prose_overlay_bring_hat_to_hat(letter_1, prose_hat_color_1, letter_2, prose_hat_color_2)

move <user.letter> to <user.letter>:
    user.prose_overlay_move_hat_to_hat(letter_1, "gray", letter_2, "gray")
move <user.prose_hat_color> <user.letter> to <user.letter>:
    user.prose_overlay_move_hat_to_hat(letter, prose_hat_color, letter_1, "gray")
move <user.letter> to <user.prose_hat_color> <user.letter>:
    user.prose_overlay_move_hat_to_hat(letter_1, "gray", letter, prose_hat_color)
move <user.prose_hat_color> <user.letter> to <user.prose_hat_color> <user.letter>:
    user.prose_overlay_move_hat_to_hat(letter_1, prose_hat_color_1, letter_2, prose_hat_color_2)
