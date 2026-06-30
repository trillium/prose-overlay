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

# Slice A of docs/PHONES_SPEC.md — segmented amber underline shows cycle
# position (Scenario 3). When the flagged token belongs to a multi-member
# CSV row, the underline splits into N segments (one per row member, in
# CSV row order). The segment whose position matches the current word's
# active_idx is rendered taller AND fully opaque; the others stay at the
# base height with a slightly dimmer alpha so the active position pops.
#
# Constants:
#   GAP_W                — px gap between segments (visual separator).
#   ACTIVE_HEIGHT        — px height of the highlighted (current) segment.
#   ACTIVE_ALPHA         — alpha hex for the highlighted segment (full).
#   INACTIVE_ALPHA       — alpha hex for non-active segments (dimmer).
#   MIN_SEGMENT_W        — px floor; below this, fall back to solid
#                          (OQ11 default — solid amber + log hint).
HOMOPHONE_UNDERLINE_GAP_W = 2
HOMOPHONE_UNDERLINE_ACTIVE_HEIGHT = 2.5
HOMOPHONE_UNDERLINE_MIN_SEGMENT_W = 1.5
# Per OQ12 default: active segment gets BOTH taller height AND full alpha,
# non-active segments stay at HOMOPHONE_UNDERLINE_HEIGHT with reduced alpha.
HOMOPHONE_UNDERLINE_ACTIVE_ALPHA = "ff"
HOMOPHONE_UNDERLINE_INACTIVE_ALPHA = "cc"

# Homophone-shape paint — Slice 1+2 of docs/HOMOPHONE_SHAPES_PLAN.md. Hat-shape
# (Cursorless vocab: bolt/frame/eye/…) painted on flagged tokens, positioned
# on a DIFFERENT character than the letter-hat dot so both can coexist.
# 0.75 matches mouse-clock's default cursor-letter scale. Color matches the
# homophone underline exactly so the two indicators read as a single visual
# signal — same amber for both render layers.
HOMOPHONE_SHAPE_SCALE = 0.75
HOMOPHONE_SHAPE_COLOR_HEX = "ffb74d"        # amber base (no alpha) — matches HOMOPHONE_UNDERLINE_COLOR
HOMOPHONE_SHAPE_OUTLINE_HEX = "ffb74d"      # same amber for the stroke — no contrasting black outline

# Slice C addendum (2026-06-30 redesign) — bubble panel layout.
# Replaces the original flat chip row that packed under each token. The
# bubble is `[chip][shape][chip]` (one or two chips around the homophone
# shape glyph) centered horizontally on its token, anchored below the
# segmented underline. The shape glyph re-renders INSIDE the bubble at a
# reduced scale (BUBBLE_SHAPE_SCALE) so the user can identify which
# token the bubble belongs to even when adjacent bubbles wrap.
#
# Chips size to their actual text content (no truncation). Bubble width =
# left_chip_w + INNER_GAP + SHAPE_W + INNER_GAP + right_chip_w (or just
# left_chip_w + INNER_GAP + SHAPE_W for 2-member groups). Adjacent
# bubbles separate by at least OUTER_GAP; if that's impossible on the
# same horizontal band the right-hand bubble wraps to a second row below.
BUBBLE_CHIP_FONT_SIZE = 11
BUBBLE_CHIP_PAD_X = 4
BUBBLE_CHIP_PAD_Y = 2
BUBBLE_CHIP_RADIUS = 3
# User verdict 2026-06-30: chip parts inside a bubble should touch (no inner
# gap) so the bubble reads as one contiguous unit; shape doubled (100%
# bigger) so it's identifiable inside the bubble at glance distance. Was
# BUBBLE_INNER_GAP=4, BUBBLE_SHAPE_SCALE=0.55. Bubble band height bumped
# proportionally so the larger shape glyph + its black backdrop don't clip.
BUBBLE_INNER_GAP = 0           # chip↔shape↔chip touch — bubble is one contiguous unit
BUBBLE_OUTER_GAP = 8           # gap BETWEEN adjacent tokens' bubbles (unchanged)
BUBBLE_TOP_GAP = 6             # gap between panel edge and bubble band
BUBBLE_SHAPE_SCALE = 1.1       # 2× prior (0.55 → 1.1); shape is now the visual anchor

# v2 redesign (2026-06-30, PHONES_SPEC commit d535611) — bubble band sits
# OUTSIDE the panel rect (above for bottom-anchor, below for top-anchor),
# stays on a SINGLE horizontal row (no vertical band-shift wrap), and the
# shape glyph paints over a black backdrop circle so it reads against the
# chip's saturated color.
#
# BUBBLE_ROW_H is the fixed vertical footprint reserved for the bubble
# band. Bumped 2026-06-30 with BUBBLE_SHAPE_SCALE = 1.1 — the shape's
# backdrop now spans ~16*1.1*1.15 ≈ 20 px, so 18 would clip. Chip
# height (FONT_SIZE + 2*PAD_Y = 11 + 4 = 15) still fits; the shape
# is the taller element now.
BUBBLE_ROW_H = 24

# Backdrop circle behind the homophone shape glyph inside the bubble. The
# chip backgrounds are bright Cursorless palette colors; the amber shape
# glyph between them was hard to spot. A near-black filled circle
# (slightly transparent so it doesn't punch a visual hole on every
# background) gives the glyph a consistent contrast surface.
#
# BACKDROP_FACTOR scales the circle radius relative to the shape's own
# native radius (_SVG_W * BUBBLE_SHAPE_SCALE / 2). 1.15 gives a thin halo
# without crowding the chips next to it. Tune by eye after first paint.
BUBBLE_SHAPE_BACKDROP_COLOR = "000000cc"
BUBBLE_SHAPE_BACKDROP_FACTOR = 1.15

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
