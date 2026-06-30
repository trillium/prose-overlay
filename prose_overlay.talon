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
chuck <user.prose_hat_color> <user.letter>:
    user.prose_overlay_delete_hat(letter, prose_hat_color)

# Delete from the beginning through a hat's word
chuck past <user.letter>: user.prose_overlay_delete_past_hat(letter)
chuck past <user.prose_hat_color> <user.letter>:
    user.prose_overlay_delete_past_hat(letter, prose_hat_color)

# Confirm and paste to previous window (alternative to line-enders)
confirm: user.prose_overlay_confirm()

# Speak the buffer contents via the speak TTS tool
# Prefixed "overlay" to avoid dictation ambiguity (matches help text)
overlay speak: user.prose_overlay_speak()

# Dismiss without pasting
# "overlay cancel" would be swallowed by the abort mechanism (last word = "cancel"
# triggers abort_update_phrase before the rule can fire). Use "overlay dismiss" instead.
overlay dismiss: user.prose_overlay_hide()

# Re-saying the launch phrase while the overlay is already active = fresh
# buffer (keeps canvas open). Without this rule it gets eaten by
# <user.raw_prose> in the dictation intercept and the words "prose overlay"
# enter the buffer instead. The start-rule version in prose_overlay_start.talon
# fires only when the overlay is INACTIVE (lower context specificity).
^prose overlay$: user.prose_overlay_clear_buffer()

# Debug: emit JSONL state diffs to ~/.talon/prose_overlay_debug.jsonl
overlay debug on: user.prose_overlay_debug(1)
overlay debug off: user.prose_overlay_debug(0)

# Dump current buffer + hat state to the Talon log (one-shot, no flag needed)
overlay dump: user.prose_overlay_dump_state()

# Hard reset — wipe all per-session state. Use when the overlay is stuck
# in a bad state. Doesn't restart Talon or reload modules; just zeros
# instance fields and hides the canvas. See prose_overlay_reset docstring.
overlay reset: user.prose_overlay_reset()

# Headless test driver — enables file-driven dispatch from scripts/test-overlay.sh
# without needing PROSE_OVERLAY_TEST=1 at Talon launch. Sticky across hot-reload
# via ~/.talon/prose_overlay_test_enabled.
overlay test on: user.prose_overlay_test_set(1)
overlay test off: user.prose_overlay_test_set(0)
overlay test status: user.prose_overlay_test_status()

# Homophone underline indicator (slice A — docs/HOMOPHONE_UI_PLAN.md)
overlay hints homo on: user.prose_overlay_set_homophone_hint(1)
overlay hints homo off: user.prose_overlay_set_homophone_hint(0)

# Homophone hat-shape overlay (slice 1 — docs/HOMOPHONE_SHAPES_PLAN.md)
overlay shapes homo on: user.prose_overlay_set_homophone_shapes(1)
overlay shapes homo off: user.prose_overlay_set_homophone_shapes(0)

# Slice A of docs/PHONES_SPEC.md — homophone cycle by shape hat.
# `phone <shape>` / `phones <shape>` both swap the token wearing <shape>
# to its next CSV-row member (wrapping). Cycle by repeating the verb.
# Singular and plural are aliased — same action, same one-undo-step swap.
(phone | phones) {user.prose_hat_shape}:
    user.prose_overlay_phone_shape(prose_hat_shape)

# Slice B of docs/PHONES_SPEC.md — addressing by current surface word.
# Scenario 5. Uses trillium_talon's existing user.homophones_canonical
# capture (in core/homophones/homophones.py:175); when the overlay is
# active, this rule wins context specificity over the modal HUD rule of
# the same shape in core/homophones/homophones.talon. The community
# modal HUD still works when the overlay is NOT active.
phones <user.homophones_canonical>:
    user.prose_overlay_phone_word(homophones_canonical)

# Slice B of docs/PHONES_SPEC.md — addressing by letter hat (Scenario 6).
# Two variants: gray-default and explicit color prefix. The action is a
# no-op when the addressed token is unflagged (OQ10 default). Caveat:
# the letter-hat allocator may reassign the slot after a swap (the new
# word may not have a `letter` char), so repeated `phones <letter>` may
# target different tokens. Use `phone <shape>` for muscle-memory cycling.
#
# OQ9 disambiguation: when the spoken word matches BOTH the homophones_canonical
# list AND the letter NATO form (rare — e.g. "air"), Talon's matcher
# picks by context specificity. Both rules sit in the overlay-active
# context with the same gate set. The homophones_canonical list is the
# narrower / more specific match by intent — but Talon resolves by
# rule order/length, not semantics, so document the resolution as
# "first match wins" and surface a TTS hint if surprise reports come in.
phones <user.letter>:
    user.prose_overlay_phone_letter(letter)
phones <user.prose_hat_color> <user.letter>:
    user.prose_overlay_phone_letter(letter, prose_hat_color)

# Toggle auto-show on all dictation phrases
overlay auto: user.prose_overlay_toggle_auto_dictation()

# Retarget to a recall named window (say the window name while overlay is open)
<user.saved_window_names>: user.prose_overlay_retarget(saved_window_names)

# Undo the last prose overlay edit
overlay undo: user.prose_overlay_undo()

# Slice A of docs/PHONES_SPEC.md Scenario 12 — accept `prose undo` as a
# second alias for the undo action, matching the launch-phrase prefix
# (`prose overlay`, `prose history`). Same action; both rules live in this
# file. `prose redo` is intentionally NOT bound for v1 — the existing
# `overlay redo` covers the redo path; we add the second alias only on
# the high-traffic undo verb per the spec.
prose undo: user.prose_overlay_undo()

# Redo the last undone prose overlay edit
overlay redo: user.prose_overlay_redo()

# Toggle CM6-style dictation coalescing (off by default)
overlay undo group on: user.prose_overlay_undo_group_set(1)
overlay undo group off: user.prose_overlay_undo_group_set(0)

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
pre <user.prose_hat_color> <user.letter>:
    user.prose_overlay_set_cursor_before_hat(letter, prose_hat_color)

# Cursor positioning: after a hat
post <user.letter>: user.prose_overlay_set_cursor_after_hat(letter)
post <user.prose_hat_color> <user.letter>:
    user.prose_overlay_set_cursor_after_hat(letter, prose_hat_color)

# Change mode: delete token at hat and enter insertion mode at that position
change <user.letter>: user.prose_overlay_change_hat(letter)
change <user.prose_hat_color> <user.letter>:
    user.prose_overlay_change_hat(letter, prose_hat_color)

# Symbol keys: capture spoken-form symbols (dot → ".", slash → "/", etc.) into the buffer.
# Without this, command-mode-only forms like "dot", "point", "semi", "slash", "dash" etc.
# fire key() in the background window instead of routing to the overlay.
# {user.symbol_key} includes all spoken forms — both command-and-dictation and command-only.
{user.symbol_key}: user.prose_overlay_add_chars(symbol_key)

# Prose formatters (say / sentence / title) — "say hello world" → "hello world".
# Mirrors text.talon:8 scoped to overlay-active so it fires in dictation mode
# too. insert_formatted is caught by the _ctx_overlay_active shim in
# prose_overlay.py and routed through formatted_text → add_text.
{user.prose_formatter} <user.prose>$: user.insert_formatted(prose, prose_formatter)
{user.prose_formatter} <user.prose> {user.phrase_ender}:
    user.insert_formatted(prose, prose_formatter)

# Code formatters (snake / camel / dotted / etc.) — "snake the quick brown
# fox" → one token "the_quick_brown_fox". <user.format_code>+ is the same
# capture community uses at text.talon:12; we route through the overlay
# variant of insert_many instead of actions.insert.
<user.format_code>+$: user.prose_overlay_insert_format_code(format_code_list)
<user.format_code>+ {user.phrase_ender}:
    user.prose_overlay_insert_format_code(format_code_list)

# NATO letter forms: "trap trap trap" → "ttt", "air bat cap" → "abc".
# Without this, single-letter NATO forms fire key(letter) in the background
# window (per core/keys/keys.talon:1) or get eaten as the literal word "trap"
# by community dictation. Routes through prose_overlay_add_letters so
# consecutive letter utterances ("air" then "bat cap") EXTEND the last
# token into one ("abc") rather than producing two tokens ("a","bc").
<user.letters>: user.prose_overlay_add_chars(letters)

# Viewport alignment — Helix/Emacs-style
overlay show top: user.prose_overlay_align_top()
overlay show bottom: user.prose_overlay_align_bottom()
overlay show center: user.prose_overlay_align_center()
overlay center: user.prose_overlay_recenter()

# Manual show (for re-opening after dismiss) -- in prose_overlay_start.talon
# Cursorless-grammar actions live in prose_overlay_cursorless.talon (separate file,
# separate context header with higher specificity than cursorless.talon).
