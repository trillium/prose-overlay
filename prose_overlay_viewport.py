"""Prose Overlay Viewport -- scroll, anchor, and row-layout state.

Owns the mutable viewport state previously held as module-level globals in
prose_overlay_draw.py: scroll offset, anchor rect/position, the cached row
layout from the last draw, and the recenter cycle state.

Action modules access this via `instance.viewport.*`. The draw module reads
the same instance at draw time.
"""

from dataclasses import dataclass, field
from typing import Optional

from talon import ui
from talon.ui import Rect

from .prose_overlay_draw_constants import PANEL_H_FRACTION, PANEL_PAD, LINE_HEIGHT


@dataclass
class Viewport:
    _scroll_offset: int = 0
    _anchor_rect: Optional[Rect] = None
    _anchor_position: str = "top"
    _last_rows: list = field(default_factory=list)
    _recenter_state: int = 0

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_scroll_offset(self) -> int:
        return self._scroll_offset

    def set_scroll_offset(self, offset: int) -> None:
        self._scroll_offset = offset

    def set_anchor_rect(self, rect: Optional[Rect]) -> None:
        self._anchor_rect = rect

    def set_anchor_position(self, position: str) -> None:
        if position in ("top", "bottom"):
            self._anchor_position = position

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def get_max_visible_rows(self) -> int:
        """Return the maximum number of token rows that fit in the panel."""
        screen = ui.main_screen()
        panel_h = screen.rect.height * PANEL_H_FRACTION
        usable_h = panel_h - PANEL_PAD * 2
        return max(1, int(usable_h / LINE_HEIGHT))

    def _find_cursor_row(self, rows: list, cursor: "int | None") -> "int | None":
        if cursor is None:
            return None
        for row_idx, row in enumerate(rows):
            first_tok = row[0][0]
            last_tok = row[-1][0]
            if first_tok <= cursor <= last_tok + 1:
                return row_idx
        return None

    def compute_scroll_for_cursor(
        self,
        rows: list,
        cursor: "int | None",
        scroll_offset: int,
        max_visible_rows: int,
    ) -> int:
        """Return the scroll offset needed to keep the cursor row visible."""
        row_idx = self._find_cursor_row(rows, cursor)
        if row_idx is None:
            return scroll_offset
        if row_idx < scroll_offset:
            return row_idx
        if row_idx >= scroll_offset + max_visible_rows:
            return row_idx - max_visible_rows + 1
        return scroll_offset

    # ------------------------------------------------------------------
    # Alignment (Task 3 — Helix align + Emacs recenter cycling)
    # ------------------------------------------------------------------

    def align(self, cursor_row: int, where: str) -> None:
        """Where in {'top','center','bottom'}: hard-align cursor row at anchor."""
        max_vis = self.get_max_visible_rows()
        if where == "top":
            self._scroll_offset = max(0, cursor_row)
        elif where == "center":
            self._scroll_offset = max(0, cursor_row - max_vis // 2)
        elif where == "bottom":
            self._scroll_offset = max(0, cursor_row - max_vis + 1)
        self._recenter_state = 0

    def recenter(self, cursor_row: int) -> None:
        """Emacs recenter-top-bottom: center -> top -> bottom on repeats."""
        cycle = ("center", "top", "bottom")
        self.align(cursor_row, cycle[self._recenter_state])
        self._recenter_state = (self._recenter_state + 1) % 3
