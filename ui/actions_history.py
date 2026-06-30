"""History panel actions for the prose overlay.

Owns: _on_draw_history, _on_history_overlay_hide, and all history/confirm/undo
      action methods.

Never imports prose_overlay.py.
"""

import subprocess

from talon import Module, actions

from ..internal.instance import instance
from ..shim.actions_core import _recompute_hats

mod = Module()

_HISTORY_MAX = 50


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _on_draw_history(c, overlay):
    draw_mod = instance.draw_mod
    rect = draw_mod.draw_history_panel(c, overlay, instance.history, instance.history_page)
    if rect:
        overlay.set_panel_rect(rect)


def _on_history_overlay_hide():
    """Called by DismissibleOverlay when dismissed via click-outside or escape."""
    actions.user.prose_overlay_hide_history()


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@mod.action_class
class Actions:
    def prose_overlay_add_text(text: str):
        """Add dictated text to the overlay buffer and refresh display.

        If the cursor is active, inserts at the cursor gap position and
        advances the cursor past the inserted tokens. Otherwise appends.
        """
        from .actions_cursor import _set_cursor, _auto_scroll_to_cursor
        instance._last_input_source = "text"
        if instance.cursor is not None:
            words = text.strip().split()
            instance.buffer.insert_at(instance.cursor, text)
            _set_cursor(instance.cursor + len(words), False)
            _recompute_hats()
            _auto_scroll_to_cursor()
            instance.canvas.refresh()
        else:
            instance.buffer.add_text(text)
            _recompute_hats()
            _auto_scroll_to_cursor()
            instance.canvas.refresh()

    def prose_overlay_insert_format_code(strings: list):
        """Route a community <user.format_code>+ result list into the overlay buffer.

        Mirrors insert_many's loop (formatters.py:493) but writes through
        prose_overlay_add_text instead of actions.insert. Each pre-formatted
        string ('the_quick_brown_fox', 'helloWorld', etc.) is added as a
        single add_text call — whitespace inside the string still splits to
        multiple tokens (e.g. title case 'The Quick Brown Fox' yields four
        tokens), but snake/camel/dotted output stays as one token per chunk.
        """
        for s in strings:
            actions.user.prose_overlay_add_text(s)

    def prose_overlay_add_chars(chars: str):
        """Add character-level input (letters, symbols, digits) to the buffer.

        Models a text editor: single-character inputs extend the token where
        the cursor is. With no active cursor, extends the LAST token. With
        an active cursor in a gap, currently appends as new token at that
        gap (cursor-targeted char insertion is a future slice).

        Drives the user-stated requirement:
          dictation "bubble" "downscore" "trap" "odd" "pit"
          → "bubble_top"  (one token, last token extended by each char)

        Used by both the <user.letters> rule (NATO letter forms) and the
        {user.symbol_key} rule (spoken symbol forms). Word-level inputs
        (raw_prose, dictation_insert, formatter outputs) still route through
        prose_overlay_add_text and produce new tokens on whitespace boundaries.
        """
        if not chars:
            return
        from .actions_cursor import _auto_scroll_to_cursor
        from ..internal.state import EditKind
        extending = (
            instance.cursor is None
            and bool(instance.buffer.get_tokens())
        )
        if extending:
            tokens = instance.buffer.get_tokens()
            new_tokens = tokens[:-1] + [tokens[-1] + chars]
            instance.buffer.commit_start("extend_chars", EditKind.STRUCTURAL)
            instance.buffer.set_tokens_raw(new_tokens)
            instance.buffer.commit_end()
            _recompute_hats()
            _auto_scroll_to_cursor()
            instance.canvas.refresh()
        else:
            # Empty buffer OR cursor active — fall back to add_text so the
            # input lands in the right place (start of buffer or at cursor).
            actions.user.prose_overlay_add_text(chars)
        instance._last_input_source = "chars"

    def prose_overlay_add_letters(letters: str):
        """Deprecated alias kept for the test driver's 'add_letters' cmd —
        routes through prose_overlay_add_chars."""
        actions.user.prose_overlay_add_chars(letters)

    def prose_overlay_speak():
        """Speak the current buffer contents via the speak TTS tool."""
        text = instance.buffer.get_text()
        if not text:
            return
        _speak_env = __import__("os").environ.copy()
        _speak_env["PATH"] = ":".join([
            "/opt/homebrew/bin",
            "/opt/homebrew/sbin",
            "/Users/trilliumsmith/.local/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
            _speak_env.get("PATH", ""),
        ])
        subprocess.Popen(
            ["/Users/trilliumsmith/code/speak/bin/speak", "--caller", "prose-overlay", text],
            start_new_session=True,
            env=_speak_env,
        )

    def prose_overlay_toggle_history():
        """Toggle the prose history panel."""
        if instance.history_overlay.is_showing:
            actions.user.prose_overlay_hide_history()
        else:
            instance.history_page = 0
            instance.history_overlay.show()
            instance.ctx_history.tags = ["user.prose_history_active"]

    def prose_overlay_hide_history():
        """Hide the prose history panel."""
        instance.history_overlay.hide()
        instance.ctx_history.tags = []

    def prose_overlay_history_next():
        """Advance to the next history page."""
        draw_mod = instance.draw_mod
        total_pages = max(1, (len(instance.history) + draw_mod.HISTORY_PAGE_SIZE - 1) // draw_mod.HISTORY_PAGE_SIZE)
        instance.history_page = min(instance.history_page + 1, total_pages - 1)
        instance.history_overlay.freeze()

    def prose_overlay_history_back():
        """Go to the previous history page."""
        instance.history_page = max(0, instance.history_page - 1)
        instance.history_overlay.freeze()

    def prose_overlay_history_pick(n: int):
        """Load the nth history entry (1-based) into the overlay buffer."""
        if 1 <= n <= len(instance.history):
            entry = instance.history[n - 1]
            actions.user.prose_overlay_hide_history()
            actions.user.prose_overlay_show()
            actions.user.prose_overlay_add_text(entry)

    def prose_overlay_confirm():
        """Insert buffer text into the target window (or active window), then hide."""
        from .actions_cursor import _prose_overlay_clear_cursor
        from .actions_flash import _clear_flash
        if not instance.canvas.is_showing:
            return  # overlay not open — ignore stale ender
        _prose_overlay_clear_cursor()
        _clear_flash()
        text = instance.buffer.get_text()
        if not text:
            actions.user.prose_overlay_hide()
            return

        # Push to history before hide clears the buffer
        instance.history.insert(0, text)
        if len(instance.history) > _HISTORY_MAX:
            instance.history.pop()

        if instance.target_recall_name:
            actions.user.recall_window(instance.target_recall_name)
            actions.sleep("80ms")

        actions.insert(text)
        actions.key("enter")
        actions.user.prose_overlay_hide()

    def prose_overlay_undo():
        """Undo the last prose overlay edit."""
        if instance.buffer.undo():
            instance.viewport.set_scroll_offset(0)
            _recompute_hats()
            instance.canvas.refresh()

    def prose_overlay_redo():
        """Redo the last undone prose overlay edit."""
        if instance.buffer.redo():
            instance.viewport.set_scroll_offset(0)
            _recompute_hats()
            instance.canvas.refresh()

    def prose_overlay_undo_group_set(enabled: int):
        """Toggle CM6-style dictation coalescing. 1 = group within 400ms, 0 = off."""
        from ..internal import state as _state
        _state._GROUP_DELAY_S = 0.400 if enabled else 0.0
        print(f"prose_overlay: undo grouping {'ON (400ms)' if enabled else 'OFF'}")
