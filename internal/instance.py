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
        # Slice 2 of HOMOPHONE_SHAPES_PLAN.md §3 — token_idx -> shape_name
        # for currently flagged homophone tokens. Computed by
        # shim.shapes.compute_shape_assignments, called from
        # shim.actions_core._recompute_hats whenever shapes are enabled.
        # Parallel to (not co-mingled with) hat_assignments per §4.1.
        self.shape_assignments: dict[int, str] = {}
        # Slice A of docs/PHONES_SPEC.md — per-flagged-token group state used
        # by the cycling swap (Scenarios 1+2) and the segmented underline
        # (Scenario 3). Computed by shim.actions_core._recompute_hats from
        # internal.homophones.next_in_group / current_position_in_group.
        # Both maps key on the same token_idx as shape_assignments and live
        # in parallel to it (not co-mingled) per the same layering rule used
        # for hat_assignments vs shape_assignments.
        #
        # next_alt_assignments[idx]    = next-cycle word for the token at idx
        # position_assignments[idx]    = (active_idx, group_size) in the
        #                                 token's homophone group
        # Tokens not flagged as homophones never appear in either dict.
        self.next_alt_assignments: dict[int, str] = {}
        self.position_assignments: dict[int, tuple[int, int]] = {}
        # Slice C of docs/PHONES_SPEC.md — per-shape-hatted-token color
        # mapping for the expanded panel (Scenario 4). Computed by
        # shim.actions_core._recompute_hats via shim.shapes.compute_panel_alts.
        # Structure: token_idx -> {color_name -> alt_word}. The action
        # prose_overlay_phone_color_shape looks up by (shape, color);
        # the draw routine (ui.draw_panels) renders one chip per entry.
        # Color names match what prose_hat_color returns (normalised:
        # gold→yellow, plum→purple).
        self.homophone_panel_alts: dict[int, dict[str, str]] = {}
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
        # Repr of the exception that forced the most recent fallback. Cleared
        # to "" on a clean JS call. Surfaced in the debug JSONL via the diff
        # stream so intermittent JS failures have root-cause data instead
        # of just a boolean flip — 2026-06-30 observed 52 fallbacks in one
        # session with no captured cause. See shim/hats_js.py:_last_err.
        self.hat_js_last_err: str = ""
        # Tracks the source of the most recent input. "letters" when a
        # <user.letters> NATO utterance landed; "text" for any other input
        # (dictation, formatter, symbol_key). Used by prose_overlay_add_letters
        # to decide whether to EXTEND the last token (consecutive letter
        # utterances) or APPEND a new one (letters after dictation).
        self._last_input_source: str = "init"

    def reset(self) -> None:
        """Wipe per-session mutable state back to ProseOverlayState() defaults.

        Used by the ``overlay reset`` debug command and by the test driver's
        ``reset`` cmd. Object references created at module init (``buffer``,
        ``canvas``, ``viewport``, the ``ctx_*`` Contexts, ``history_overlay``,
        ``draw_mod``) are PRESERVED — only their state is cleared. Pre-existing
        cron jobs (``blink_job``) are left alone; the caller is responsible for
        cancelling and clearing those before invoking reset.
        """
        if self.buffer is not None:
            self.buffer.clear()
        self.hat_assignments = {}
        self.hat_to_token = {}
        self.shape_assignments = {}
        self.next_alt_assignments = {}
        self.position_assignments = {}
        self.homophone_panel_alts = {}
        self.target_window_title = ""
        self.target_recall_name = None
        self.help_visible = False
        self.help_page = 0
        self.auto_dictation = False
        self.cursor = None
        self.change_mode = False
        self.blink_on = True
        self.flash_state = {}
        self.flash_callback = None
        self.history = []
        self.history_page = 0
        self.hat_js_fallback = False
        self.hat_js_last_err = ""
        self._last_input_source = "init"
        if self.viewport is not None:
            self.viewport.set_scroll_offset(0)


instance = ProseOverlayState()
