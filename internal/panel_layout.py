"""Pure-python placement math for the homophone bubble panel.

Extracted from ui/draw_panels.py so the band-assignment logic can be
exercised headlessly without importing Talon / Skia. The draw module
still owns measurement (chip-text widths require a live canvas) and
the actual paint pass — this file is only the math.

The placement contract:

  Given a list of bubbles ordered left-to-right with ideal x positions
  (centered on each token) and computed widths, assign each bubble a
  `band` index (0 = primary row directly below the underline, 1 = one
  row below, 2 = two rows below, …) such that no two bubbles on the
  same band sit closer than `outer_gap` pixels horizontally.

  Bubbles whose ideal_x underflows `x_origin` are soft-clamped to
  `x_origin` (preserves visibility — never start a bubble before the
  panel's left margin).

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
      x              — final absolute x after clamp + collision wrap.
      band           — 0 (primary row), 1+ when wrapped down.
    """

    __slots__ = ("ideal_x", "bubble_w", "x", "band")

    def __init__(self, ideal_x: float, bubble_w: float) -> None:
        self.ideal_x = float(ideal_x)
        self.bubble_w = float(bubble_w)
        # Defaults — `place_bubbles` overwrites these.
        self.x = float(ideal_x)
        self.band = 0


def place_bubbles(
    bubbles: list[BubbleLayout],
    x_origin: float,
    outer_gap: float,
) -> None:
    """Assign each bubble a band so adjacent bubbles don't collide.

    Walks `bubbles` left-to-right (caller is responsible for ordering by
    `ideal_x`). For each bubble:

      1. Soft-clamp `x` to `>= x_origin`.
      2. Find the lowest band where `x` is at least `outer_gap` past
         the rightmost edge of any previously placed bubble on that
         band. The first bubble on a band always fits.
      3. Update that band's rightmost-edge tracker to `x + bubble_w`.

    Mutates the BubbleLayout objects in place — no return value.

    Parameters:
      bubbles    — list of BubbleLayout records, left-to-right.
      x_origin   — absolute x of the panel's left margin. Bubbles whose
                   ideal_x underflows this stick at x_origin.
      outer_gap  — minimum px gap between adjacent bubbles on the same
                   band before the right-hand one wraps down.

    Termination guarantee: each iteration of the inner `while` loop
    either finds an empty band (`rightmost_on.get(band) is None`) and
    breaks, or increments `band`. Since `rightmost_on` only stores
    bands we've assigned, the loop always reaches an empty band in
    finite steps (bounded by the number of bubbles).
    """
    rightmost_on: dict[int, float] = {}
    for b in bubbles:
        abs_x = b.ideal_x
        if abs_x < x_origin:
            abs_x = x_origin
        band = 0
        while True:
            r = rightmost_on.get(band)
            if r is None or abs_x >= r + outer_gap:
                break
            band += 1
        b.band = band
        b.x = abs_x
        rightmost_on[band] = abs_x + b.bubble_w
