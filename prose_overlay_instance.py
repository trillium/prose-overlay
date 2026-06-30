"""Shared mutable state for the prose overlay plugin.

All module-level globals from prose_overlay.py are centralized here.
Action files import `instance` directly — never import prose_overlay.py.
prose_overlay.py owns initialization; action files own their read/write patterns.
"""
from typing import Optional


class ProseOverlayState:
    def __init__(self):
        self.buffer = None                  # ProseBuffer
        self.hat_assignments: dict = {}
        self.hat_to_token: dict = {}
        self.canvas = None                  # OverlayCanvas
        self.ctx = None                     # Context (overlay showing)
        self.ctx_auto = None                # Context (auto-dictation)
        self.ctx_history = None             # Context (history showing)
        self.ctx_shim = None                # Context (dictation shim)
        self.target_window_title: str = ""
        self.target_recall_name: Optional[str] = None
        self.help_visible: bool = False
        self.help_page: int = 0
        self.auto_dictation: bool = False
        self.cursor: Optional[int] = None
        self.change_mode: bool = False
        self.blink_on: bool = True
        self.blink_job = None
        self.flash_state: dict = {}
        self.flash_callback = None
        self.history: list = []
        self.history_page: int = 0
        self.history_overlay = None         # DismissibleOverlay
        self.draw_mod = None                # prose_overlay_draw module
        self.viewport = None                # prose_overlay_viewport.Viewport
        self.hat_js_fallback: bool = False  # True when JS allocator failed; triggers orange color scheme


instance = ProseOverlayState()
