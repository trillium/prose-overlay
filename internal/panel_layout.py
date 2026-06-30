"""Pure-python placement math for the homophone bubble panel.

Extracted from ui/draw_panels.py so the placement logic can be
exercised headlessly without importing Talon / Skia. The draw module
still owns measurement (chip-text widths require a live canvas) and
the actual paint pass — this file is only the math.

The placement contract (v2, 2026-06-30, PHONES_SPEC commit d535611):

  Given a list of bubbles ordered left-to-right with ideal x positions
  (centered on each token) and computed widths, assign each bubble a
  final `x` on a SINGLE horizontal row such that no two bubbles sit
  closer than `outer_gap` pixels horizontally.

  - Bubbles whose ideal_x underflows `x_origin` are soft-clamped to
    `x_origin` (preserves visibility — never start a bubble before the
    panel's left margin).
  - When a bubble's ideal_x would collide with the previously placed
    bubble's right edge + outer_gap, it shifts RIGHT to the minimum
    non-colliding position. There is no left shift, no vertical wrap,
    and no band assignment. The rightmost bubble may extend past the
    panel's right edge and clip at the screen boundary; the user's
    stated priority for v2 is horizontal clarity over off-screen
    alts.

  The `band` field on BubbleLayout is retained for API stability but
  is always 0 in the v2 contract.

v1.5 history (removed in this commit): the old contract assigned a
multi-row `band` index so colliding bubbles wrapped to a second row.
The user reported that vertical stacking was confusing — the bubble's
position no longer pointed at its token. v2 trades the wrap for a
right-shift that visibly preserves the horizontal order.

This module has zero Talon dependencies and is importable from the
headless test runner via the normal package-relative import or via
spec_from_file_location.
"""


class BubbleLayout:
    """Mutable placement record for one bubble.

    Inputs (set by caller):
      ideal_x        — absolute x (post-x_origin) where this bubble
                       WANTS to sit (centered on its token).
      bubble_w       — measured total bubble width in px.

    Outputs (set by `place_bubbles`):
      x              — final absolute x after clamp + right-shift.
      band           — always 0 in v2; field retained for API
                       stability with v1.5 callers.
    """

    __slots__ = ("ideal_x", "bubble_w", "x", "band")

    def __init__(self, ideal_x: float, bubble_w: float) -> None:
        self.ideal_x = float(ideal_x)
        self.bubble_w = float(bubble_w)
        # Defaults — `place_bubbles` overwrites `x`. `band` stays 0
        # in the v2 horizontal-only contract.
        self.x = float(ideal_x)
        self.band = 0


def place_bubbles(
    bubbles: list[BubbleLayout],
    x_origin: float,
    outer_gap: float,
) -> None:
    """Place bubbles on a single horizontal row, right-shifting on collision.

    Walks `bubbles` left-to-right (caller is responsible for ordering by
    `ideal_x`). For each bubble:

      1. Soft-clamp `x` to `>= x_origin`.
      2. If `x` is closer than `outer_gap` to the previous bubble's
         right edge, shift this bubble's `x` rightward to
         `prev_right + outer_gap`.
      3. Record this bubble's right edge as the new `prev_right` for
         the next iteration.

    Mutates the BubbleLayout objects in place — no return value.
    `band` is always left at 0; v1.5's vertical wrap was removed when
    the user verdict was "single horizontal row only".

    Parameters:
      bubbles    — list of BubbleLayout records, left-to-right.
      x_origin   — absolute x of the panel's left margin. Bubbles whose
                   ideal_x underflows this stick at x_origin.
      outer_gap  — minimum px gap between adjacent bubbles before the
                   right-hand one shifts further right.

    Side effect note: when many bubbles collide in sequence, each
    successive bubble's `x` ratchets further right, so the rightmost
    bubble may extend past the panel's right edge. The screen edge
    (Skia canvas extent) clips. This is the documented v2 trade-off —
    horizontal clarity beats off-screen alts.
    """
    prev_right: float | None = None
    for b in bubbles:
        abs_x = b.ideal_x
        if abs_x < x_origin:
            abs_x = x_origin
        if prev_right is not None and abs_x < prev_right + outer_gap:
            abs_x = prev_right + outer_gap
        b.x = abs_x
        b.band = 0
        prev_right = abs_x + b.bubble_w
