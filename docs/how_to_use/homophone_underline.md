# Homophone Underline

> *Amber solid underline painted under every flagged homophone token. The always-on signal that "this word has alternates you might have meant." For multi-member groups it segments into N parts with one part lit bright to show your current position in the group.*

## Voice commands

- `overlay hints homo on` — enable the underline at runtime (default ON)
- `overlay hints homo off` — disable; flagged tokens render without the underline

Underline is **on by default** — flagging signal is the primary UI cue, not a subtle hint. This matches spell-checker convention: loud, unmistakable, unavoidable. The setting `user.prose_overlay_homophone_hint` controls the launch default; the runtime toggles above override per-session.

## How it works

When the overlay is active and a token matches the homophone CSV (their/there/they're, your/you're, …), the renderer paints a 1.5-px amber bar directly under the token at `~93%` alpha. The color matches `HOMOPHONE_UNDERLINE_COLOR` (`ffb74dee`), which is the same amber the shape glyph uses — the underline and the shape read as a single visual signal.

### Segmented underline shows your group position

When a flagged token belongs to a multi-member group (e.g. `their/there/they're` has 3 members), the underline splits into **N segments** — one per CSV-row member, in order. The segment corresponding to the **current surface word** paints taller (2.5 px vs 1.5 px) and at full opacity (`ff`); the other segments stay at the base height with reduced opacity (`cc`).

You can read your current position in the cycle without saying anything: leftmost lit = you're on row member 0; middle lit = member 1; rightmost lit = member 2.

If the per-segment width drops below `HOMOPHONE_UNDERLINE_MIN_SEGMENT_W` (1.5 px), the segmented underline falls back to a solid bar — happens when the token text is too short to render N segments cleanly (e.g. a 1-char token in a 4-member group).

## Examples

### Example 1: Single-member group → solid bar

```
Buffer: too
       [under "too": solid amber bar; "too/to/two" is its group;
        no segmentation if all members render as a single tight bar]
```

### Example 2: Multi-member group → segmented bar with position lit

```
Buffer: their over there they're
       [under "their": 3 segments, LEFTMOST lit (position 0 of /their, there, they're/)]
       [under "there": 3 segments, MIDDLE lit (position 1)]
       [under "they're": 3 segments, RIGHTMOST lit (position 2)]
```

After `phones risk` (swap `their` → `they're`):

```
Buffer: they're over there they're
       [under "they're" (position 0): 3 segments, RIGHTMOST lit (position 2 now)]
```

### Example 3: Toggle off mid-session

```
You: overlay hints homo off
       [amber underlines disappear; flagging is now invisible until a phones command surfaces it]
You: overlay hints homo on
       [underlines return]
```

## Caveats

- **Underline is the load-bearing signal**. The shape hat ([`homophone_shapes.md`](homophone_shapes.md)) is opt-in; the underline is the one always-on cue that tells you the overlay caught a homophone. Turn it off only when you've memorized your patterns and find the visual noise distracting.
- **Spillover for non-shape tokens**: when shape painting is enabled and the 10-shape pool exhausts on >10 distinct groups, the overflow groups still get the underline — that's the entire fallback path per `HOMOPHONE_SHAPES_PLAN.md §4.8`.
- **Color matches the shape glyph by design** so the underline + shape read as one signal. If you change `HOMOPHONE_UNDERLINE_COLOR`, update `HOMOPHONE_SHAPE_COLOR_HEX` to match.
- **Min segment width fallback** can hide group position on very short tokens. If the underline goes solid for a flagged multi-member group, the token was too narrow for N segments — read position from the shape glyph or the bubble panel instead.

## Source

- Constants: `internal/draw_constants.py` — `HOMOPHONE_UNDERLINE_*`
- Render: `ui/draw_tokens.py` (underline paint block)
- Setting: `user.prose_overlay_homophone_hint` (default `True`); runtime flag in `prose_overlay.py`
- Position lookup: `internal/homophones.py:current_position_in_group`
- Plan: `docs/HOMOPHONE_UI_PLAN.md` (Slice A — kept after first-paint user verdict)
- ISCs: ISC-11 (underline shipped), ISC-12 (segmented variant — PHONES_SPEC Slice A / ISC-14d-A)
- Related: [`homophone_shapes.md`](homophone_shapes.md), [`phones.md`](phones.md)
