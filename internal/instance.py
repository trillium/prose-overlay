"""Shared mutable state for the prose overlay plugin.

All module-level globals from prose_overlay.py are centralized here.
Action files import `instance` directly — never import prose_overlay.py.
prose_overlay.py owns initialization; action files own their read/write patterns.

Move 2 of the pure-function refactor plan split the ~30 top-level fields
into two nested namespaces:

  - ``instance.state.*`` — pure data (dict-serializable). Includes
    ``buffer``: technically a live object but exposes a pure surface
    (tokens, cursor, selection, rev), so we treat it as opaque data.
  - ``instance.runtime.*`` — live Talon objects (canvas, contexts, cron
    handles, callbacks, viewport, draw_mod). Never JSON-serialized.

The transitional ``@property`` forwarders that let callers migrate
incrementally are gone as of Move 2 step 7/7. Every reader/writer must
go through ``instance.state.<field>`` or ``instance.runtime.<field>``
directly. The debug snapshot (``internal/debug.py``) reads state.*;
pure-function tests (Move 4/5) will consume ``instance.state`` as an
opaque dict-like bundle.
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

    def reset(self) -> None:
        """Wipe per-session mutable state back to ProseOverlayState() defaults.

        Used by the ``overlay reset`` debug command and by the test driver's
        ``reset`` cmd. Object references created at module init (``buffer``,
        ``canvas``, ``viewport``, the ``ctx_*`` Contexts, ``history_overlay``,
        ``draw_mod``) are PRESERVED — only their state is cleared. Pre-existing
        cron jobs (``blink_job``) are left alone; the caller is responsible for
        cancelling and clearing those before invoking reset.
        """
        if self.state.buffer is not None:
            self.state.buffer.clear()
        self.state.hat_assignments = {}
        self.state.hat_to_token = {}
        self.state.shape_assignments = {}
        self.state.next_alt_assignments = {}
        self.state.position_assignments = {}
        self.state.homophone_panel_alts = {}
        self.state.target_window_title = ""
        self.state.target_recall_name = None
        self.state.help_visible = False
        self.state.help_page = 0
        self.state.auto_dictation = False
        self.state.cursor = None
        self.state.change_mode = False
        self.state.blink_on = True
        self.state.flash_state = {}
        self.runtime.flash_callback = None
        # Reset clears runtime history but IMMEDIATELY reloads the
        # persisted entries from disk. Semantics: 'overlay reset' is a
        # runtime-state escape hatch, not a data-loss command. If the user
        # wants to nuke on-disk history they delete the file explicitly
        # (~/.talon/prose_overlay_history.json). Without this reload,
        # reset would leave in-memory empty and the very next confirm
        # would write `[new_entry]` — silently truncating the on-disk
        # store to a single entry. Import is lazy so tests loading
        # instance.py stand-alone don't need the persist module on path.
        self.state.history = []
        try:
            from .history_persist import load_history
            self.state.history = load_history()
        except Exception:
            # A load failure inside reset() must not brick reset() —
            # history_persist.load_history is already defensive but
            # this belt+braces defends against import failures too.
            self.state.history = []
        self.state.history_page = 0
        self.state.hat_js_fallback = False
        self.state.hat_js_last_err = ""
        self.state._last_input_source = "init"
        if self.runtime.viewport is not None:
            self.runtime.viewport.set_scroll_offset(0)


instance = ProseOverlayState()
