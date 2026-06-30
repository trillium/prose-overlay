# Viewport, Clipping, and Scrolling — Research

> **Provenance.** Synthesized 2026-06-29 from a background research-agent sweep of open-source viewport / clipping / scrolling implementations, scoped to a voice-driven text editor built on Talon's Skia canvas.
> **Companion doc:** [`UNDO_REDO_RESEARCH.md`](./UNDO_REDO_RESEARCH.md).

## Context — the constraints this research was scoped against

- **Rendering layer:** Talon's canvas, a thin Python binding over Skia. Immediate-mode `SkCanvas`, `SkPaint`, `drawText`/`drawParagraph`, manual clip + transform stacks. Metal backend on macOS. No built-in scroll containers, no retained-mode scene graph.
- **Interaction model:** voice-only. Inputs are discrete commands ("scroll down a page", "show line 42", "scroll to the cursor"). No smooth wheel scrolling, but command-driven pans should still feel animated.
- **Latency budget:** utterance-to-pixel under ~100 ms perceived. Viewport math has to be cheap enough that full-canvas redraws stay there.
- **Buffer model:** in-memory rope / piece-table. No file IO. Cursorless + tree-sitter available for token-level structure.
- **Required:** single- AND multi-axis scrolling. Horizontal matters because of one edge case — **a single token can be wider than the viewport** (long identifier or URL).
- **Keep-cursor-in-view:** after any edit or command, the cursor's visual rect must be made visible. Canonical "scrollIntoView" / "ensureVisible" semantics.

---

## 1. Skia + custom-canvas viewport patterns

### `SkCanvas::clipRect` + `SkMatrix::translate` (the canonical pair)
- **Links:** [Skia SkCanvas Reference](https://api.skia.org/classSkCanvas.html), [Flutter dart:ui Canvas.clipRect](https://api.flutter.dev/flutter/dart-ui/Canvas/clipRect.html)
- **What it does.** The immediate-mode pattern that backs every Skia-based viewport. Push a clip rect for the viewport, translate by `-scrollX, -scrollY`, draw content in world coordinates, then `restore()`. Flutter's entire scrolling stack reduces to this in `RenderViewport`.
- **APIs to imitate.** `SkCanvas::save()`, `SkCanvas::clipRect(viewportRect)`, `SkCanvas::translate(-scrollX, -scrollY)`, `SkCanvas::restore()`. In Talon-Python: `canvas.save()`, `canvas.clip_rect(...)`, `canvas.translate(...)`, `canvas.restore()` (Talon binding follows skia-python naming).
- **Mapping to Talon.** `talon.skia.Canvas` is `SkCanvas`. Build a `Viewport` class holding `(scroll_x, scroll_y, w, h)` exposing `with_clip_and_translate(canvas, draw_fn)` as a context manager.
- **Wide-token case.** Doesn't solve it directly, but a wide token painted past `scroll_x + w` is simply clipped — no extra work for offscreen pixels.
- **Latency.** Trivially under budget — nanoseconds for the calls; full text redraw on Metal Skia is well under 16 ms.

### `SkCanvas::quickReject` + `cullRect` for cheap culling
- **Links:** [SkCanvas::quickReject](https://api.skia.org/classSkCanvas.html), [SkiaSharp QuickReject](https://learn.microsoft.com/en-us/dotnet/api/skiasharp.skcanvas.quickreject?view=skiasharp-2.88)
- **What it does.** `quickReject(rect)` returns true if a world-space rect, after the current matrix, lies entirely outside the current clip — "should I bother building the draw call?". `drawTextBlob` also takes an optional `cullRect` that skips the draw when the blob's bounds are outside the clip.
- **APIs to imitate.** `bool SkCanvas::quickReject(const SkRect&) const;` plus the `cullRect` arg on text draws.
- **Mapping to Talon.** Per line (after binary-search culling locates the visible range), call `canvas.quick_reject(line_rect)` before building the text blob. Skips layout cost for partially-offscreen lines in the "fringe" range.
- **Wide-token case.** A wide token's bounding rect intersects the viewport and is *not* rejected; only the offscreen halves of the glyphs are culled at rasterization.
- **Latency.** Sub-µs per call. Net win past ~50 lines.

### `SkParagraph::getRectsForRange` for caret + selection + token rects
- **Links:** [SkParagraph Paragraph.h](https://github.com/google/skia/blob/main/modules/skparagraph/include/Paragraph.h), [Skia Text API Overview](https://skia.org/docs/dev/design/text_overview/)
- **What it does.** Returns `std::vector<TextBox>` enclosing all glyphs between two character indexes, with `RectHeightStyle` (tight / max / strut) and `RectWidthStyle` (tight / max). Layout is cached; subsequent calls are O(visible glyphs).
- **APIs to imitate.** `Paragraph::getRectsForRange(start, end, RectHeightStyle, RectWidthStyle)`; also `Paragraph::getGlyphPositionAtCoordinate(dx, dy)` for hit-testing.
- **Mapping to Talon.** Talon ships `SkParagraph` via `talon.skia`. Build paragraphs per line (or per viewport-page of lines), cache keyed by buffer-revision, query `getRectsForRange(cursorIdx, cursorIdx+1, kTight, kTight)` for the cursor rect, intersect with the viewport rect for the "cursor visible?" check.
- **Wide-token case.** **Perfectly.** `getRectsForRange` over a full token returns a `TextBox` whose `rect.right - rect.left` is the true world-space width. Compare against viewport width to detect "token wider than viewport" before choosing scroll strategy.
- **Latency.** ~µs per call after layout. Layout itself is the expensive bit — cache paragraphs.

---

## 2. Game-engine viewport math

### Godot `Camera2D` — drag margins + smoothing
- **Links:** [godot/scene/2d/camera_2d.cpp](https://github.com/godotengine/godot/blob/master/scene/2d/camera_2d.cpp), [Camera2D 4.4 docs](https://docs.godotengine.org/en/4.4/classes/class_camera2d.html)
- **What it does.** Holds a "target position" the camera keeps centered. Four `drag_margin_{left,right,top,bottom}` rectangles act as a dead-zone: the camera doesn't move while the followed point stays in the box. When the point exits, the camera moves just enough to put it back on the dead-zone edge. With `position_smoothing_enabled`, the actual position lerps toward target at `position_smoothing_speed` pixels/sec.
- **APIs to imitate.** `Camera2D::_update_scroll()`, `Camera2D::align()` ("forces the camera to update scroll immediately"), `Camera2D::reset_smoothing()`, `position_smoothing_speed`, the four `drag_margin_*` fields.
- **Mapping to Talon.** **The single best fit for the voice-loop UX.** The drag-margin / dead-zone model is Vim's `scrolloff` / `sidescrolloff` re-phrased in game terms. Smoothing animates "scroll to line 42" over ~150 ms without teleporting; `align()` is the hard "show line 42" instant jump. Dead-zone makes "cursor's already onscreen, don't move" feel correct.
- **Wide-token case.** Camera2D itself doesn't address it, but its target-pos + margins math extends naturally: when the cursor token is wider than viewport, set horizontal target so the *cursor's caret* (not the token's left edge) lands at viewport_width × 0.3 — the wide-token-centering rule plugs in here.
- **Latency.** A lerp tick is a few ALU ops. Voice command → set target → next-frame lerp = sub-ms.

### Pygame `Surface.set_clip` / `subsurface` + `Rect.clip`
- **Links:** [pygame.Surface](https://www.pygame.org/docs/ref/surface.html), [pygame.Rect](https://www.pygame.org/docs/ref/rect.html)
- **What it does.** Almost the exact analog to Skia's `clipRect`. Community pattern for a 2D camera: blit world surface onto screen with a source `Rect` offset by `-camera.x, -camera.y`. `Rect.clip(other)` returns the intersection — perfect "is this token visible?" test.
- **APIs to imitate.** `Rect.clip(other)`, `Rect.colliderect(other)` (boolean cull test), `Rect.contains(other)` ("fully inside?").
- **Mapping to Talon.** Re-implement `Rect` as a tiny dataclass with `intersect()`, `contains()`, `intersects()`. This is the AABB primitive everywhere downstream — cursor ∩ viewport, token ∩ viewport, etc.
- **Wide-token case.** `Rect.clip` returns the visible sub-rect when a wide token is partially onscreen; usable to position truncation indicators.
- **Latency.** Pure arithmetic. Free.

---

## 3. TUI / text-editor viewport logic

### Vim/Neovim `scroll_cursor_{top,bot,halfway}` + `scrolloff` / `sidescrolloff`
- **Links:** [src/nvim/move.c overview](https://deepwiki.com/neovim/neovim/3.3-cursor-movement-and-scrolling), [Vim sidescrolloff docs](https://vimdoc.sourceforge.net/htmldoc/scroll.html), [Sensible sidescroll](https://ddrscott.github.io/blog/2016/sidescroll/)
- **What it does.** Vim recomputes `topline` (the buffer line drawn at viewport row 0) after every cursor movement. If the cursor is within `scrolloff` lines of the edge, `scroll_cursor_top()` / `scroll_cursor_bot()` adjusts `topline` to keep the margin. `scroll_cursor_halfway()` centers (powers `zz`). Horizontal works the same: `leftcol` is the column drawn at viewport col 0, adjusted via `sidescrolloff`; `sidescroll` controls jump size.
- **APIs to imitate.** Names verbatim: `scroll_cursor_top`, `scroll_cursor_bot`, `scroll_cursor_halfway`, plus `update_topline` (the dispatch function called every redraw). The `scrolloff` (vertical margin in lines) + `sidescrolloff` (horizontal margin in cols) pair is the right parameter shape.
- **Mapping to Talon.** Literal Python methods on `Viewport`. Voice commands map cleanly: "show top" → `scroll_cursor_top()`, "center cursor" → `scroll_cursor_halfway()`, "show bottom" → `scroll_cursor_bot()`. Run `update_topline()` after every edit or cursor jump.
- **Wide-token case.** Vim's horizontal model assumes fixed character cells; `sidescroll` pages right by a fixed col count. Doesn't gracefully handle "token wider than viewport." Borrow the *control structure*, not this failure mode.
- **Latency.** Constant-time arithmetic; gold standard for "algorithm is free, layout dominates."

### Helix `View::ensure_cursor_in_view` / `offset_coords_to_in_view_center`
- **Link:** [helix-view/src/view.rs](https://github.com/helix-editor/helix/blob/master/helix-view/src/view.rs)
- **What it does.** Cleaner rewrite of Vim's logic. A single generic function `offset_coords_to_in_view_center<const CENTERING: bool>()` either applies scrolloff margins (`false` → "minimal scroll") or ignores them (`true` → "force to center"). Returns `Option<(anchor, horizontal_offset)>` — `None` means "can't satisfy the constraint, fall back to `align_view`."
- **APIs to imitate.** `ensure_cursor_in_view(doc, scrolloff)`, `ensure_cursor_in_view_center()`, `align_view(doc, Align::{Top,Center,Bottom})`. The `CENTERING` generic toggles whether margins are honored — port as a Python bool.
- **Mapping to Talon.** Almost a direct port. Replace Rust's `visual_offset_from_anchor` with a call into the line-rect cache. Use `scrolloff.min(viewport_h / 2)` to clamp margins on tiny viewports — Helix gets this right; historical Vim doesn't.
- **Wide-token case.** Helix sets `horizontal_offset = visual_col.saturating_sub(scrolloff_left)` and scrolls right when cursor exceeds `last_col - scrolloff_right`. For a single token > viewport, this scrolls in fixed steps — same Vim shortcoming. Use the structure; layer the Flutter "center the visible part of the rect" rule on top.
- **Latency.** Constant time. Helix is famously snappy.

### Textual `Widget.scroll_to_region` / `scroll_visible`
- **Links:** [textual/src/textual/widget.py](https://github.com/Textualize/textual/blob/main/src/textual/widget.py), [textual.scroll_view API](https://textual.textualize.io/api/scroll_view/)
- **What it does.** `scroll_to_region(region, *, animate, top=False, origin_visible=True, ...)` computes the minimal scroll delta to fit a given `Region` inside the widget's `scrollable_content_region`. `scroll_to(x, y, *, animate=True, duration=None, easing=...)` is the lerp-based animated target setter, with optional `level: AnimationLevel = "basic"` so users can downgrade smoothness.
- **APIs to imitate.** Signatures: `scroll_to(x, y, animate, duration, easing, on_complete, level, immediate)`; `scroll_to_region(region, ...)`; `scroll_visible(animate, top, ...)`. The split between **what region** and **how to animate** is the cleanest separation of concerns found.
- **Mapping to Talon.** Mirror directly. `scroll_to_region(cursor_rect, animate=True, duration=0.12)` becomes the one-stop "keep cursor visible." Animation can drive a 60 Hz redraw via Talon's `cron.interval`. `immediate=True` is the voice "show now" path.
- **Wide-token case.** When `region.width > scrollable_content_region.width`, Textual scrolls the region's *left* edge into view by default. Acceptable but not great. Override: when region wider than viewport, target = cursor caret − viewport_w × 0.3, not region.left.
- **Latency.** Animation runs on a frame timer; one-shot computation is sub-ms.

### Emacs `recenter` + `scroll-margin` (concept, not code)
- **Links:** [Recentering — Emacs manual](https://www.gnu.org/software/emacs/manual/html_node/emacs/Recentering.html), [Textual Scrolling — Elisp manual](https://www.gnu.org/software/emacs/manual/html_node/elisp/Textual-Scrolling.html)
- **What it does.** `recenter-top-bottom` cycles cursor position center → top → bottom on repeated invocations. `scroll-margin` is Emacs's `scrolloff` equivalent. Worth pulling for the **cycling-anchor UX**: "center cursor" → first invocation centers; second moves to top; third moves to bottom.
- **APIs to imitate.** `recenter-top-bottom` (the cycling state machine), `scroll-margin` semantics.
- **Mapping to Talon.** Excellent voice-UX win. "center" → cycles. Persist last-anchor in viewport state.
- **Wide-token case.** Not addressed.
- **Latency.** State var + Helix-style centering. Free.

### CodeMirror 6 `EditorView.scrollIntoView` / `ScrollTarget`
- **Links:** [codemirror/view editorview.ts](https://github.com/codemirror/view/blob/main/src/editorview.ts), [CodeMirror Reference Manual](https://codemirror.net/docs/ref/)
- **What it does.** `scrollIntoView(pos, {y, x, yMargin, xMargin})` with `y`/`x` each `"nearest" | "start" | "end" | "center"`. Default `"nearest"` is canonical "scroll the minimum required to make pos visible." Defaults to 5px margin. Implemented as a `StateEffect` carrying a `ScrollTarget` — atomic with the edit that caused it.
- **APIs to imitate.** Four-strategy enum is the right surface: `Y_STRATEGY = Literal["nearest", "start", "end", "center"]`. Same for X.
- **Mapping to Talon.** Single `ensure_visible(rect, *, y="nearest", x="nearest", y_margin=8, x_margin=24)` entry point on `Viewport`. Voice commands map: "scroll to cursor" → `y="nearest", x="nearest"`; "center on cursor" → `y="center", x="center"`; "show line 42 at top" → `y="start"`.
- **Wide-token case.** CM6 falls back to "show as much as fits, anchored to start" — same gap as Textual.
- **Latency.** Voice-grade fine.

### Flutter `RenderViewportBase.getOffsetToReveal` / `bringIntoView` — **the wide-token-centering pattern, the most important borrow**
- **Links:** [getOffsetToReveal](https://api.flutter.dev/flutter/rendering/RenderViewportBase/getOffsetToReveal.html), [EditableTextState.bringIntoView](https://api.flutter.dev/flutter/widgets/EditableTextState/bringIntoView.html), [PR 93248 — fix caret > viewport](https://github.com/flutter/flutter/pull/93248)
- **What it does.** `getOffsetToReveal(target, alignment)` returns the scroll offset that places `target` at fractional alignment 0.0 (leading) through 1.0 (trailing) — 0.5 means centered. `showInViewport` calls it twice (alignment 0.0 and 1.0), then uses `RevealedOffset.clampOffset` to choose minimal motion if already visible. **When the target rect is larger than the viewport,** PR 93248 fixes the algorithm to "center the viewport on the visible part of the rect" — i.e. you don't try to fit the unfittable; you center *on the caret-within-the-token*, not on the token rect.
- **APIs to imitate.** `getOffsetToReveal(target, alignment) -> RevealedOffset`, `RevealedOffset.clampOffset(min, max)`, `showInViewport(descendant, viewport, offset)`.
- **Mapping to Talon.** Direct port. For each axis: compute two candidate offsets (leading-aligned, trailing-aligned); if the current offset is between them the target is already visible and you return early. If the target is wider than viewport, center on the caret (not the token).
- **Wide-token case.** **This is the canonical solution.** Quote from the PR rationale: "center the viewport on the visible part of the rect" when rect > viewport.
- **Latency.** A handful of arithmetic ops. Voice-grade.

---

## 4. Text layout — wide-token detection

### Skia `SkParagraph` (covered in §1) — primary
The same `getRectsForRange` call that gives you cursor rect gives you token rect. One API does both.

### HarfBuzz / Pango / CoreText — skip
They give finer-grained glyph extents (`hb_buffer_get_glyph_positions`, Pango `pango_layout_get_extents`, CoreText `CTRunGetTypographicBounds`), but you'd be reimplementing 80% of `SkParagraph` to use them. Talon already ships Skia. Don't fight it.

---

## 5. Visible-range culling

### Binary search by cumulative line-top (Monaco / virtual-scroll standard)
- **Links:** [Monaco perf discussion](https://news.ycombinator.com/item?id=11940043), [Build your own virtual scroll part II](https://dev.to/adamklein/build-your-own-virtual-scroll-part-ii-3j86)
- **What it does.** Maintain a sorted array of `cumulative_top[i]` (sum of line heights through line `i`). To find the line at viewport-top, `bisect_right(cumulative_top, scroll_y) - 1`. To find the line at viewport-bottom, `bisect_left(cumulative_top, scroll_y + viewport_h)`. Loop draws only those lines. Monaco quote: *"if 20 lines visible, typing/colorizing/painting should be computed with loops covering those 20 lines, not the buffer size."*
- **APIs to imitate.** Python `bisect.bisect_right` / `bisect_left` on `list[float]`.
- **Mapping to Talon.** With fixed line height (v1), this collapses to integer division — even faster. With variable line height (post-v1), `bisect` over the cumulative array. Invalidate the array suffix on edits past line N.
- **Wide-token case.** Vertical culling only; horizontal culling within a line is by token-rect AABB test (`token.right > scroll_x and token.left < scroll_x + viewport_w`).
- **Latency.** O(log n) for the bisect; O(visible) for the draw. Trivially under budget on million-line buffers.

### Interval tree (overkill for v1)
Useful only with variable-height collapsible regions (folds, virtual lines, code-folding) where insertions/deletions are mid-buffer. Skip until folds exist.

---

## 6. Scroll indicators (canvas-style, no OS scrollbar)

### Edge-gradient / fade-out (Sublime Text, VS Code minimap)
- **Link:** [Sublime Settings — fade_fold_buttons, draw_minimap_border](https://docs.sublimetext.io/reference/settings.html)
- **What it does.** A small linear-gradient overlay on each viewport edge where content extends past. Cheapest implementation: `canvas.drawRect(edgeStrip, SkPaint(shader=LinearGradient(...)))`. Communicates "there's more in this direction" without any DOM scrollbar.
- **Mapping to Talon.** Four `drawRect`s with `SkGradientShader::MakeLinear`. Show only when `scroll_x > 0` / `scroll_x + viewport_w < world_w` / same for y.
- **Wide-token case.** Right-edge fade is exactly the truncation indicator. Pair with a single triangle/arrow glyph on the offscreen side of any token that exceeds the viewport.
- **Latency.** ~µs.

### Mini scrollbar (drawn in canvas)
- **What it does.** A 4-px-wide strip on the right edge showing `viewport_h / world_h` proportional thumb at `scroll_y / (world_h - viewport_h)`. Two rects.
- **Mapping to Talon.** Two `drawRect` calls. Fade in on scroll, fade out after 1.5 s of stillness.
- **Latency.** Free.

### Gutter arrow for offscreen cursor
- **What it does.** When a voice command moves cursor to a position outside the viewport but the user said "don't move the view" (rare but possible), draw a small arrow in the gutter pointing toward the offscreen cursor. Borrowed from Vim's `virtualedit` indicators and most IDEs' "find next" arrow.
- **Latency.** Free.

---

## Recommended stack (priority order)

1. **Helix's `ensure_cursor_in_view` + `align_view` control structure** — the algorithmic spine. Port `offset_coords_to_in_view_center<const CENTERING>` as a Python function with `centering: bool` arg. Use Vim-style `scrolloff` / `sidescrolloff` parameter naming because it's what voice users will say. *([source](https://github.com/helix-editor/helix/blob/master/helix-view/src/view.rs))*

2. **Flutter's `getOffsetToReveal` + the PR-93248 wide-target rule** — the wide-token solution. Wrap Helix's per-axis logic with: "if target rect > viewport, center the *caret-within-the-token*, not the token rect." Non-negotiable for the long-identifier UX. *([source](https://github.com/flutter/flutter/pull/93248))*

3. **Skia `SkParagraph::getRectsForRange` + `SkCanvas::clipRect`/`translate`/`quickReject`** — the rendering substrate. Cache one `SkParagraph` per visible line keyed by `(buffer_revision, line_number)`. Use `getRectsForRange` for cursor + token bounds. Use `quickReject` per line. Use `bisect_right` over cumulative line-tops for visible-range. *([SkParagraph](https://github.com/google/skia/blob/main/modules/skparagraph/include/Paragraph.h), [SkCanvas](https://api.skia.org/classSkCanvas.html))*

4. **Godot `Camera2D` smoothing model (lerp-to-target) + Textual `scroll_to(animate, duration, easing, level, immediate)` API shape** — the animation layer. `viewport.scroll_to(x, y, animate=True, duration=0.12, immediate=False)` schedules a frame timer that lerps current → target over ~7 frames at 60 Hz (under perception threshold). Voice command sets `target`; `immediate=True` skips the lerp for hard "show now." *([Camera2D](https://github.com/godotengine/godot/blob/master/scene/2d/camera_2d.cpp), [Textual widget.py](https://github.com/Textualize/textual/blob/main/src/textual/widget.py))*

**Skip for v1:** HarfBuzz/Pango/CoreText, interval trees, Emacs recenter-cycling (do v1.1 as pure UX sugar), CodeMirror transaction-scoped effect plumbing (overkill without a transaction system).

---

## Things to act on immediately (synthesis pass)

- **Cache one `SkParagraph` per visible line** keyed by `(buffer_revision, line_number)`. Layout is the only expensive thing on the redraw path; everything else (clip, translate, quickReject) is sub-µs. Invalidate on edit by line range.
- **Use `getRectsForRange(token_start, token_end)` as the wide-token detector.** Same call that gives the cursor rect tells you `(rect.right - rect.left) > viewport_width`. Branch from there.
- **Steal Emacs `recenter-top-bottom` cycling for v1.1** — "center cursor" said twice goes top, said thrice goes bottom. One state variable, big voice-UX payoff.
- **Buffer revision counter** is load-bearing — paragraphs cache by it. Add a monotonic u64 `rev` field to the buffer from day one.

---

## Sources

- [Helix view.rs](https://github.com/helix-editor/helix/blob/master/helix-view/src/view.rs)
- [Flutter PR 93248 — caret-larger-than-viewport fix](https://github.com/flutter/flutter/pull/93248)
- [Flutter getOffsetToReveal](https://api.flutter.dev/flutter/rendering/RenderViewportBase/getOffsetToReveal.html)
- [Flutter bringIntoView](https://api.flutter.dev/flutter/widgets/EditableTextState/bringIntoView.html)
- [Flutter editable.dart](https://github.com/flutter/flutter/blob/master/packages/flutter/lib/src/rendering/editable.dart)
- [Flutter ViewportOffset](https://api.flutter.dev/flutter/rendering/ViewportOffset-class.html)
- [Flutter dart:ui Canvas.clipRect](https://api.flutter.dev/flutter/dart-ui/Canvas/clipRect.html)
- [Skia SkCanvas reference](https://api.skia.org/classSkCanvas.html)
- [SkParagraph Paragraph.h](https://github.com/google/skia/blob/main/modules/skparagraph/include/Paragraph.h)
- [Skia Text API Overview](https://skia.org/docs/dev/design/text_overview/)
- [SkTextBlob reference](https://api.skia.org/classSkTextBlob.html)
- [skia-python Canvas](https://kyamagu.github.io/skia-python/reference/skia.Canvas.html)
- [SkiaSharp QuickReject](https://learn.microsoft.com/en-us/dotnet/api/skiasharp.skcanvas.quickreject?view=skiasharp-2.88)
- [Godot camera_2d.cpp](https://github.com/godotengine/godot/blob/master/scene/2d/camera_2d.cpp)
- [Godot Camera2D 4.4 docs](https://docs.godotengine.org/en/4.4/classes/class_camera2d.html)
- [Neovim cursor movement & scrolling](https://deepwiki.com/neovim/neovim/3.3-cursor-movement-and-scrolling)
- [Vim scroll docs](https://vimdoc.sourceforge.net/htmldoc/scroll.html)
- [Sensible sidescroll (Scott Dietrich)](https://ddrscott.github.io/blog/2016/sidescroll/)
- [Pygame Surface](https://www.pygame.org/docs/ref/surface.html)
- [Pygame Rect](https://www.pygame.org/docs/ref/rect.html)
- [Textual widget.py](https://github.com/Textualize/textual/blob/main/src/textual/widget.py)
- [Textual scroll_view API](https://textual.textualize.io/api/scroll_view/)
- [CodeMirror editorview.ts](https://github.com/codemirror/view/blob/main/src/editorview.ts)
- [CodeMirror smooth-scroll-line-into-view discussion](https://discuss.codemirror.net/t/smooth-scroll-line-into-view/3051)
- [Emacs Recentering manual](https://www.gnu.org/software/emacs/manual/html_node/emacs/Recentering.html)
- [Emacs Textual Scrolling (Elisp)](https://www.gnu.org/software/emacs/manual/html_node/elisp/Textual-Scrolling.html)
- [Sublime Text settings reference](https://docs.sublimetext.io/reference/settings.html)
- [Talon Voice docs](https://talonvoice.com/docs/)
- [Build your own virtual scroll part II](https://dev.to/adamklein/build-your-own-virtual-scroll-part-ii-3j86)
- [Monaco perf HN thread](https://news.ycombinator.com/item?id=11940043)
