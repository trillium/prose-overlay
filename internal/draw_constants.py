"""Shared visual constants for the prose overlay rendering system.

Imported by prose_overlay_draw.py, prose_overlay_draw_tokens.py, and
prose_overlay_history_panel.py. Keep this file free of Talon imports
and side effects — pure Python only.
"""

# ---------------------------------------------------------------------------
# Panel geometry
# ---------------------------------------------------------------------------
PANEL_RADIUS = 12
PANEL_PAD = 12
PANEL_H_FRACTION = 0.10  # total panel height: 10% of screen height

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
BG_COLOR = "1a1a2add"
BORDER_COLOR = "4488aacc"

# Fallback indicator colors — used when the JS hat allocator fails and the
# Python fallback is active. Orange scheme signals degraded mode to the user.
BG_COLOR_FALLBACK = "2a1500dd"      # dark amber background
BORDER_COLOR_FALLBACK = "ff8800cc"  # bright orange border
TOKEN_COLOR = "eeeeffee"
HINT_COLOR = "888899cc"
HINT_CMD_COLOR = "ccccddee"
LISTENING_COLOR = "666677cc"
SEP_COLOR = "44556688"
HELP_TITLE_COLOR = "66aaccee"

# Homophone-hint underline — Slice A. Was a sub-pixel (0.5px) dotted slate at
# 40% alpha (8899aa66) which most displays rasterized to nothing — user
# reported the homophones "look identical to any other token." Bumped to a
# spell-checker-style amber solid underline so it's unmistakable. Override at
# runtime if you want it subtler — keep contrast high enough to actually read.
HOMOPHONE_UNDERLINE_COLOR = "ffb74dee"      # amber, ~93% alpha
HOMOPHONE_UNDERLINE_HEIGHT = 1.5             # px — visible at standard DPI

# Homophone-shape paint — Slice 1+2 of docs/HOMOPHONE_SHAPES_PLAN.md. Hat-shape
# (Cursorless vocab: bolt/frame/eye/…) painted on flagged tokens, positioned
# on a DIFFERENT character than the letter-hat dot so both can coexist.
# 0.75 matches mouse-clock's default cursor-letter scale. Color matches the
# homophone underline exactly so the two indicators read as a single visual
# signal — same amber for both render layers.
HOMOPHONE_SHAPE_SCALE = 0.75
HOMOPHONE_SHAPE_COLOR_HEX = "ffb74d"        # amber base (no alpha) — matches HOMOPHONE_UNDERLINE_COLOR
HOMOPHONE_SHAPE_OUTLINE_HEX = "ffb74d"      # same amber for the stroke — no contrasting black outline

# Hat dot colors — matches Cursorless palette
HAT_COLOR_HEX: dict[str, str] = {
    "gray":   "999999ff",
    "blue":   "089ad3ff",
    "green":  "36b33fff",
    "red":    "e02d28ff",
    "pink":   "e06caaff",
    "yellow": "e5c02cff",
    "purple": "8e44adff",
    "black":  "000000ff",  # drawn with white border ring
    "white":  "ffffffff",
}
HAT_COLOR = HAT_COLOR_HEX["gray"]  # legacy fallback

# ---------------------------------------------------------------------------
# Font sizes
# ---------------------------------------------------------------------------
TOKEN_FONT_SIZE = 16
# NOTE: HINT_FONT_SIZE is intentionally absent — it is mutable state in
# prose_overlay_draw.py (written by help_bigger / help_smaller commands).

# ---------------------------------------------------------------------------
# Hat dot (Cursorless-style)
# ---------------------------------------------------------------------------
HAT_ALPHABET = "abcdefghijklmnopqrstuvwxyz"
DOT_RADIUS = 3       # small filled circle above first letter
DOT_GAP_Y = 2        # gap between dot bottom and token top

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
TOKEN_GAP_X = 5   # horizontal gap between tokens (~1 space-char width at 16pt)
TOKEN_GAP_Y = 6   # vertical gap between wrapped rows
LINE_HEIGHT = (DOT_RADIUS * 2) + DOT_GAP_Y + TOKEN_FONT_SIZE + TOKEN_GAP_Y

# ---------------------------------------------------------------------------
# Cursor
# ---------------------------------------------------------------------------
CURSOR_COLOR_NAVIGATE = "ffffffff"   # white, navigate mode
CURSOR_COLOR_CHANGE   = "e5a02cff"   # amber, change/replace mode
CURSOR_WIDTH = 2
CURSOR_CHANGE_ZONE_WIDTH = 24        # width of faint amber insertion-zone rect
CURSOR_CHANGE_ZONE_ALPHA = "4d"      # ~30% alpha
