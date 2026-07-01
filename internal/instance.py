"""Shared mutable state for the prose overlay plugin.

All module-level globals from prose_overlay.py are centralized here.
Action files import `instance` directly — never import prose_overlay.py.
prose_overlay.py owns initialization; action files own their read/write patterns.

Move 2 of the pure-function refactor plan splits the ~30 top-level fields
into two nested namespaces:

  - ``instance.state.*`` — pure data (dict-serializable). Includes
    ``buffer``: technically a live object but exposes a pure surface
    (tokens, cursor, selection, rev), so we treat it as opaque data.
  - ``instance.runtime.*`` — live Talon objects (canvas, contexts, cron
    handles, callbacks, viewport, draw_mod). Never JSON-serialized.

During the migration every legacy ``instance.<field>`` access is preserved
via ``@property`` forwarders that route to the sub-namespace. This lets
call sites migrate incrementally rather than in one atomic changeset.
The forwarders will be deleted once all call sites are moved.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class _State:
    """Pure-data half of ``ProseOverlayState``.

    Every field here must be dict-serializable (opaque ``buffer`` excepted
    — it exposes a pure surface via ``get_tokens`` / ``get_selection`` /
    ``get_rev`` and is treated as data even though it's technically a live
    object). Debug snapshots and future pure-function tests will consume
    this namespace directly.
    """

    buffer: Any = None  # ProseBuffer (opaque data surface)
    hat_assignments: dict = field(default_factory=dict)
    hat_to_token: dict = field(default_factory=dict)
    # Slice 2 of HOMOPHONE_SHAPES_PLAN.md §3 — token_idx -> shape_name
    # for currently flagged homophone tokens. Computed by
    # shim.shapes.compute_shape_assignments, called from
    # shim.actions_core._recompute_hats whenever shapes are enabled.
    # Parallel to (not co-mingled with) hat_assignments per §4.1.
    shape_assignments: dict = field(default_factory=dict)
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
    next_alt_assignments: dict = field(default_factory=dict)
    position_assignments: dict = field(default_factory=dict)
    # Slice C of docs/PHONES_SPEC.md — per-shape-hatted-token color
    # mapping for the expanded panel (Scenario 4). Computed by
    # shim.actions_core._recompute_hats via shim.shapes.compute_panel_alts.
    # Structure: token_idx -> {color_name -> alt_word}. The action
    # prose_overlay_phone_color_shape looks up by (shape, color);
    # the draw routine (ui.draw_panels) renders one chip per entry.
    # Color names match what prose_hat_color returns (normalised:
    # gold→yellow, plum→purple).
    homophone_panel_alts: dict = field(default_factory=dict)
    target_window_title: str = ""
    target_recall_name: Optional[str] = None
    help_visible: bool = False
    help_page: int = 0
    auto_dictation: bool = False
    cursor: Optional[int] = None
    change_mode: bool = False
    blink_on: bool = True
    flash_state: dict = field(default_factory=dict)
    history: list = field(default_factory=list)
    history_page: int = 0
    hat_js_fallback: bool = False  # True when JS allocator failed; triggers orange color scheme
    # Repr of the exception that forced the most recent fallback. Cleared
    # to "" on a clean JS call. Surfaced in the debug JSONL via the diff
    # stream so intermittent JS failures have root-cause data instead
    # of just a boolean flip — 2026-06-30 observed 52 fallbacks in one
    # session with no captured cause. See shim/hats_js.py:_last_err.
    hat_js_last_err: str = ""
    # Tracks the source of the most recent input. "letters" when a
    # <user.letters> NATO utterance landed; "text" for any other input
    # (dictation, formatter, symbol_key). Used by prose_overlay_add_letters
    # to decide whether to EXTEND the last token (consecutive letter
    # utterances) or APPEND a new one (letters after dictation).
    _last_input_source: str = "init"


@dataclass
class _Runtime:
    """Live-Talon half of ``ProseOverlayState``.

    Every field here is a live object with side-effecting methods
    (canvas draws, contexts install grammar, cron handles run callbacks,
    viewport queries live window geometry). Never JSON-serialized;
    never included in debug snapshots.

    Populated by ``prose_overlay.py`` at module init. Cleared references
    survive ``reset()``: the object references are preserved (a canvas
    hidden and re-showable, a Context still installed) — only the pure
    ``state`` half gets wiped.
    """

    canvas: Any = None                    # OverlayCanvas
    history_overlay: Any = None           # DismissibleOverlay
    ctx: Any = None                       # Context (overlay showing)
    ctx_auto: Any = None                  # Context (auto-dictation)
    ctx_history: Any = None               # Context (history showing)
    ctx_shim: Any = None                  # Context (dictation shim)
    flash_callback: Optional[Callable] = None
    blink_job: Any = None                 # talon.cron handle
    viewport: Any = None                  # prose_overlay_viewport.Viewport
    draw_mod: Any = None                  # prose_overlay_draw module


class ProseOverlayState:
    def __init__(self):
        self.state = _State()
        self.runtime = _Runtime()

    # ------------------------------------------------------------------
    # Transitional attribute aliases — Move 2 migration only.
    # These forward every legacy ``instance.<field>`` access to the new
    # sub-namespace so call sites can migrate incrementally without
    # forcing one atomic changeset. Removed in the final Move 2 commit
    # once every reader/writer is on ``instance.state.*`` /
    # ``instance.runtime.*``.
    # ------------------------------------------------------------------

    # ---- state aliases ----
    @property
    def buffer(self):
        return self.state.buffer

    @buffer.setter
    def buffer(self, v):
        self.state.buffer = v

    @property
    def hat_assignments(self):
        return self.state.hat_assignments

    @hat_assignments.setter
    def hat_assignments(self, v):
        self.state.hat_assignments = v

    @property
    def hat_to_token(self):
        return self.state.hat_to_token

    @hat_to_token.setter
    def hat_to_token(self, v):
        self.state.hat_to_token = v

    @property
    def shape_assignments(self):
        return self.state.shape_assignments

    @shape_assignments.setter
    def shape_assignments(self, v):
        self.state.shape_assignments = v

    @property
    def next_alt_assignments(self):
        return self.state.next_alt_assignments

    @next_alt_assignments.setter
    def next_alt_assignments(self, v):
        self.state.next_alt_assignments = v

    @property
    def position_assignments(self):
        return self.state.position_assignments

    @position_assignments.setter
    def position_assignments(self, v):
        self.state.position_assignments = v

    @property
    def homophone_panel_alts(self):
        return self.state.homophone_panel_alts

    @homophone_panel_alts.setter
    def homophone_panel_alts(self, v):
        self.state.homophone_panel_alts = v

    @property
    def target_window_title(self):
        return self.state.target_window_title

    @target_window_title.setter
    def target_window_title(self, v):
        self.state.target_window_title = v

    @property
    def target_recall_name(self):
        return self.state.target_recall_name

    @target_recall_name.setter
    def target_recall_name(self, v):
        self.state.target_recall_name = v

    @property
    def help_visible(self):
        return self.state.help_visible

    @help_visible.setter
    def help_visible(self, v):
        self.state.help_visible = v

    @property
    def help_page(self):
        return self.state.help_page

    @help_page.setter
    def help_page(self, v):
        self.state.help_page = v

    @property
    def auto_dictation(self):
        return self.state.auto_dictation

    @auto_dictation.setter
    def auto_dictation(self, v):
        self.state.auto_dictation = v

    @property
    def cursor(self):
        return self.state.cursor

    @cursor.setter
    def cursor(self, v):
        self.state.cursor = v

    @property
    def change_mode(self):
        return self.state.change_mode

    @change_mode.setter
    def change_mode(self, v):
        self.state.change_mode = v

    @property
    def blink_on(self):
        return self.state.blink_on

    @blink_on.setter
    def blink_on(self, v):
        self.state.blink_on = v

    @property
    def flash_state(self):
        return self.state.flash_state

    @flash_state.setter
    def flash_state(self, v):
        self.state.flash_state = v

    @property
    def history(self):
        return self.state.history

    @history.setter
    def history(self, v):
        self.state.history = v

    @property
    def history_page(self):
        return self.state.history_page

    @history_page.setter
    def history_page(self, v):
        self.state.history_page = v

    @property
    def hat_js_fallback(self):
        return self.state.hat_js_fallback

    @hat_js_fallback.setter
    def hat_js_fallback(self, v):
        self.state.hat_js_fallback = v

    @property
    def hat_js_last_err(self):
        return self.state.hat_js_last_err

    @hat_js_last_err.setter
    def hat_js_last_err(self, v):
        self.state.hat_js_last_err = v

    @property
    def _last_input_source(self):
        return self.state._last_input_source

    @_last_input_source.setter
    def _last_input_source(self, v):
        self.state._last_input_source = v

    # ---- runtime aliases ----
    @property
    def canvas(self):
        return self.runtime.canvas

    @canvas.setter
    def canvas(self, v):
        self.runtime.canvas = v

    @property
    def history_overlay(self):
        return self.runtime.history_overlay

    @history_overlay.setter
    def history_overlay(self, v):
        self.runtime.history_overlay = v

    @property
    def ctx(self):
        return self.runtime.ctx

    @ctx.setter
    def ctx(self, v):
        self.runtime.ctx = v

    @property
    def ctx_auto(self):
        return self.runtime.ctx_auto

    @ctx_auto.setter
    def ctx_auto(self, v):
        self.runtime.ctx_auto = v

    @property
    def ctx_history(self):
        return self.runtime.ctx_history

    @ctx_history.setter
    def ctx_history(self, v):
        self.runtime.ctx_history = v

    @property
    def ctx_shim(self):
        return self.runtime.ctx_shim

    @ctx_shim.setter
    def ctx_shim(self, v):
        self.runtime.ctx_shim = v

    @property
    def flash_callback(self):
        return self.runtime.flash_callback

    @flash_callback.setter
    def flash_callback(self, v):
        self.runtime.flash_callback = v

    @property
    def blink_job(self):
        return self.runtime.blink_job

    @blink_job.setter
    def blink_job(self, v):
        self.runtime.blink_job = v

    @property
    def viewport(self):
        return self.runtime.viewport

    @viewport.setter
    def viewport(self, v):
        self.runtime.viewport = v

    @property
    def draw_mod(self):
        return self.runtime.draw_mod

    @draw_mod.setter
    def draw_mod(self, v):
        self.runtime.draw_mod = v

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
        # Reset clears runtime history but IMMEDIATELY reloads the
        # persisted entries from disk. Semantics: 'overlay reset' is a
        # runtime-state escape hatch, not a data-loss command. If the user
        # wants to nuke on-disk history they delete the file explicitly
        # (~/.talon/prose_overlay_history.json). Without this reload,
        # reset would leave in-memory empty and the very next confirm
        # would write `[new_entry]` — silently truncating the on-disk
        # store to a single entry. Import is lazy so tests loading
        # instance.py stand-alone don't need the persist module on path.
        self.history = []
        try:
            from .history_persist import load_history
            self.history = load_history()
        except Exception:
            # A load failure inside reset() must not brick reset() —
            # history_persist.load_history is already defensive but
            # this belt+braces defends against import failures too.
            self.history = []
        self.history_page = 0
        self.hat_js_fallback = False
        self.hat_js_last_err = ""
        self._last_input_source = "init"
        if self.viewport is not None:
            self.viewport.set_scroll_offset(0)


instance = ProseOverlayState()
