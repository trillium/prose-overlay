"""Prose Overlay -- main module with actions, settings, and orchestration.

Coordinates the buffer, canvas, and window focus tracking to provide
a voice-first dictation buffer with hat-targeted editing.
"""

import os
from typing import Optional

from talon import Context, Module, actions, settings, ui

from .prose_overlay_canvas import OverlayCanvas
from . import prose_overlay_draw as _draw_mod_ref
from .prose_overlay_state import ProseBuffer
from .prose_overlay_viewport import Viewport
from ...utils.overlay_kit import DismissibleOverlay
from .prose_overlay_cursorless_resolve import (
    _state as _resolve_state,
)
from .prose_overlay_instance import instance
from .prose_overlay_actions_core import _recompute_hats, _sync_tags, _hat_to_index
from . import prose_overlay_trail  # noqa: F401
from . import prose_overlay_test_driver  # noqa: F401

mod = Module()

mod.setting(
    "prose_overlay_enabled",
    type=bool,
    default=True,
    desc="Enable the prose dictation overlay for buffered dictation with hat editing",
)

mod.setting(
    "prose_overlay_help_font_size",
    type=int,
    default=12,
    desc="Font size for the help footer in the prose overlay",
)

mod.tag("prose_overlay_active", desc="Prose dictation overlay is currently visible")
mod.tag("prose_overlay_auto", desc="Auto-show prose overlay on any dictation (toggled by user)")
mod.tag("prose_history_active", desc="Prose history panel is currently visible")

mod.setting(
    "prose_overlay_auto_dictation",
    type=bool,
    default=False,
    desc="When true, any phrase in dictation mode automatically opens the prose overlay",
)

mod.setting(
    "prose_overlay_window_scoped",
    type=bool,
    default=True,
    desc="When true, the overlay panel is sized and positioned to match the target window",
)

mod.setting(
    "prose_overlay_use_js_resolver",
    type=bool,
    default=False,
    desc=(
        "When true, target/scope resolution flows through cursorless's "
        "processTargets pipeline bundled at js/prose_resolve_targets.js. "
        "When false (default), the legacy Python resolver in "
        "prose_overlay_cursorless_resolve.py is used. Toggle for the F5 "
        "JS-resolver migration; remove the Python path once parity verified."
    ),
)

mod.setting(
    "prose_overlay_homophone_hint",
    type=bool,
    default=True,
    desc=(
        "When true, paint a dotted underline under every token whose "
        "lowercase appears in the trillium_talon homophone CSV. Slice A "
        "of the homophone-UI exploration (docs/HOMOPHONE_UI_PLAN.md) — "
        "user keep verdict received 2026-06-30, so default is ON. "
        "Toggle at runtime via 'overlay hints homo off'."
    ),
)

mod.setting(
    "prose_overlay_homophone_shapes",
    type=bool,
    default=True,
    desc=(
        "When true, paint a Cursorless-style hat shape (bolt, frame, eye, "
        "…) above every flagged token, on top of the existing letter-hat "
        "dot. Slice 1 of the homophone-shapes exploration "
        "(docs/HOMOPHONE_SHAPES_PLAN.md). Default ON since 2026-06-30 "
        "(user keep verdict — mirrors the slice-A homophone-hint default "
        "flip; rationale per memory feedback_overlay_subtle_hints_wrong: "
        "must-perceive signals should default loud, not subtle). Toggle "
        "off via 'overlay shapes homo off'."
    ),
)


@mod.capture(rule="red | blue | green | pink | yellow | purple | plum | gold | black | white")
def prose_hat_color(m) -> str:
    """Spoken color prefix for a hat, e.g. 'blue air', 'red bat'.
    Normalizes aliases: plum -> purple, gold -> yellow.
    """
    spoken = str(m).strip()
    return {"plum": "purple", "gold": "yellow"}.get(spoken, spoken)

# ---------------------------------------------------------------------------
# Initialize instance state
# ---------------------------------------------------------------------------
instance.buffer = ProseBuffer()
_resolve_state.buffer = instance.buffer  # share the ProseBuffer instance with the resolve module
instance.hat_assignments = {}
instance.hat_to_token = {}
instance.draw_mod = _draw_mod_ref
instance.viewport = Viewport()

_ctx = Context()
_ctx_auto = Context()  # owns the prose_overlay_auto tag

# Expose contexts on instance so actions_core._sync_tags can access them.
instance.ctx = _ctx
instance.ctx_auto = _ctx_auto

# Action-level shim: active when prose_overlay_auto tag is set.
# Overrides user.dictation_insert so every dictation path (community enders,
# punctuation enders, window-switch rules, etc.) routes to the overlay
# instead of inserting directly into the focused window.
_ctx_shim = Context()
_ctx_shim.matches = r"""
tag: user.prose_overlay_auto
"""

_ctx_history = Context()
instance.ctx_history = _ctx_history

# ---------------------------------------------------------------------------
# Canvas setup
# ---------------------------------------------------------------------------

instance.canvas = OverlayCanvas(instance.buffer)

# Wire canvas into flash module — flash needs canvas ref for refresh calls.
# (flash module reads from instance.canvas directly)

# ---------------------------------------------------------------------------
# History overlay setup
# ---------------------------------------------------------------------------
# Import helpers from history module now that instance.canvas and
# instance.draw_mod are set.
from .prose_overlay_actions_history import _on_draw_history, _on_history_overlay_hide  # noqa: E402

instance.history_overlay = DismissibleOverlay(
    on_draw=_on_draw_history,
    on_hide=_on_history_overlay_hide,
    close_hint_text='"overlay dismiss"',
    close_hint_size=12,
    close_hint_color="888899cc",
    blocks_mouse=False,
)

# ---------------------------------------------------------------------------
# Load persisted preferences
# ---------------------------------------------------------------------------
from .prose_overlay_actions_visibility import _load_prefs  # noqa: E402
_load_prefs()


# ---------------------------------------------------------------------------
# Shim: route all dictation_insert / insert_formatted calls to the overlay
# ---------------------------------------------------------------------------

# Active when overlay is showing — intercepts insert_formatted while overlay is open.
_ctx_overlay_active = Context()
_ctx_overlay_active.matches = r"""
tag: user.prose_overlay_active
"""

@_ctx_overlay_active.action_class("user")
class _OverlayActiveActions:
    def insert_formatted(phrase, formatters: str):
        """Route formatter output (e.g. 'say <prose>') to the overlay buffer."""
        text = actions.user.formatted_text(phrase, formatters)
        actions.user.prose_overlay_add_text(text)


@_ctx_shim.action_class("user")
class _ShimActions:
    def dictation_insert(text: str):
        """Shim: route dictated text to the prose overlay instead of inserting directly.

        Intercepts every path that ends in dictation_insert — community enders,
        punctuation enders, window-switch rules, etc. — so the overlay is the
        single destination for all spoken prose when auto mode is active.
        """
        if instance.canvas.is_showing:
            actions.user.prose_overlay_add_text(text)
        else:
            actions.user.prose_overlay_show()
            actions.user.prose_overlay_add_text(text)

    def insert_formatted(phrase, formatters: str):
        """Route formatter output (e.g. 'say <prose>') to the overlay buffer.

        insert_formatted calls actions.insert() directly, bypassing dictation_insert,
        so it needs its own shim. Uses user.formatted_text to get the formatted string
        without re-importing format_phrase.
        """
        text = actions.user.formatted_text(phrase, formatters)
        if instance.canvas.is_showing:
            actions.user.prose_overlay_add_text(text)
        else:
            actions.user.prose_overlay_show()
            actions.user.prose_overlay_add_text(text)


# ---------------------------------------------------------------------------
# Import action sub-modules so Talon registers their action classes
# ---------------------------------------------------------------------------
from . import prose_overlay_actions_cursor      # noqa: F401, E402
from . import prose_overlay_actions_layout      # noqa: F401, E402
from . import prose_overlay_actions_history     # noqa: F401, E402
from . import prose_overlay_actions_help        # noqa: F401, E402
from . import prose_overlay_actions_visibility  # noqa: F401, E402
from . import prose_overlay_actions_cursorless  # noqa: F401, E402
