# Adaptive Help Zone — Scope

> Doc-only scope. No code touched. Retirement Forge on `ui/*` is running in parallel — do not race it.
>
> Related: `docs/SCENARIOS.md §S5`, `docs/POTENTIALLY_MISSED.md §F`, `docs/FEATURE_PARITY.md §0b`.

## §0. Executive summary

Today the overlay paints a `"listening..."` placeholder on empty and hides a rotating side-help column on overflow. We want a **tri-state help zone**: **State A** (buffer empty → full-panel help), **State B** (tokens present, no overflow → 20% side-panel help), **State C** (overflow → help hidden, tokens get full width). Transitions are automatic and reversible from buffer + overflow signals — no user commands. Effort: **S–M** end-to-end. State B/C is a rename of existing overflow logic; State A is genuinely new (reuse `build_help_layout` at a wider rect).

## §1. Current state — what the overlay does today

- **Empty buffer** paints `"listening..."` at `TOKEN_FONT_SIZE`, `LISTENING_COLOR`, anchored inside the content area. Cite `ui/draw.py:210-227` (old path) and `ui/layout_help_cursor.py:112-118` + `486-502` (empty-buffer cursor path, model side).
- **`overlay help` toggle** flips `state.help_visible` (`internal/instance.py:83`) and paints a paginated pager BELOW the main panel via `ui/help.py:draw_help_panel`. Content: `ui/help.py:50` (`HELP_PAGES`, five pages). Layout: `ui/layout_help_cursor.py:250-370` (`build_help_layout`) produces `HelpLayout(rows, page, total_pages)` (`ui/layout.py:444-467`).
- **Side hint column** ("rotating help ring") lives at `HELP_W_FRACTION = 0.20` of panel width when there's room. Auto-hides via the `_hints_hidden_by_overflow` module global (`ui/draw.py:64`, set at `ui/draw.py:189-193`; mirrored on the model at `ui/layout_root.py:456-460`). Rotating rows come from `help.rotate_help_ring_buffer` (`ui/draw.py:46`); paint code lives in `ui/draw.py` lines ~220-243 (old imperative path) — the pure model does NOT yet have a side-ring surface (`ui/layout_help_cursor.py:33-58` notes surface #1 vs #2 explicitly).
- **Overflow trim** — when rows overflow, `hints_hidden = True`, content reflows at `panel_w - PANEL_PAD*2`, help_area on the model becomes `None` (`ui/layout_root.py:479-488`).

## §2. Target — three states, precisely

- **State A — full-panel help.** `state.buffer.get_tokens() == []`. The whole content area IS help content. No `"listening..."` string. Buffer-empty + cursor 0 keeps the cursor drawn per today's contract (`ui/layout_help_cursor.py:486-502`).
- **State B — side-panel help.** Tokens present AND rows fit without overflow. Help lives in the right 20% (`help_area` rect on the model, already computed at `ui/layout_root.py:479-488`).
- **State C — help hidden.** Tokens present AND rows overflow content width. Same criterion the code already uses at `ui/layout_root.py:455-460`. Model's `help_area = None`, `help = None`.

State machine:

```
              tokens == []
             ┌──────────────┐
             ▼              │
        ┌────────┐  add tok │
        │   A    ├──────────┼──────►┌────────┐  overflow  ┌────────┐
        │ FULL   │          │       │   B    ├──────────► │   C    │
        │ HELP   │◄─────────┘       │ SIDE   │◄────────── │ HIDDEN │
        └────────┘  del all         │ HELP   │  fits again └────────┘
                                    └────────┘
```

Every transition is derived from `(len(tokens), overflow_bool)` on each draw. No latching, no timers.

## §3. Content — what fills the help zone in each state?

- **State A (full-panel).** Recommend: **the paginated `HELP_PAGES` pager, rendered inside `content_area`** — same `build_help_layout` output that `overlay help` shows today, just with a wider rect. Adds a hero row at the top: `("say prose overlay to dictate", "")` painted at larger font as a title. Rationale: reuse — one help data source, one row-emitter. If the pager pages beyond one screen, respect `state.help_page` for navigation (see §5).
- **State B (side-panel).** Recommend: same rows as State A, but the builder is called with the narrow `help_area` rect. Column-fit truncation via `_fit_text` (already in `ui/draw.py:40`). Font size is `HINT_FONT_SIZE` (the mutable side-hint font, already the pager's convention).
- **State C (hidden).** No rows. `LayoutModel.help = None`.

## §4. Implementation plan — where the pieces go

### `_State` field additions

Prefer **derived** over stored. `help_visible` and `help_page` already exist (`internal/instance.py:83-84`). Add a derived helper at model-composition time — no new state.

Optionally add ONE debug field: `help_zone_mode: Literal["full", "side", "hidden"]` on `LayoutModel` for debug snapshots. Not on `_State`.

### `build_help_layout` changes

Current signature (`ui/layout_help_cursor.py:250-256`):

```python
def build_help_layout(state, *, panel_rect, hint_font_size=12, help_panel_gap=8.0) -> HelpLayout | None
```

Extend to accept a `content_area_rect: Rect` and a `mode: Literal["full","side","below"]`. `"below"` preserves the current `overlay help` behavior (pager below main panel). `"full"` renders at content_area. `"side"` renders in help_area. Concrete new signature:

```python
def build_help_layout(
    state, *,
    panel_rect: Rect,
    target_rect: Rect,                        # where rows should paint
    mode: Literal["full", "side", "below"],
    hint_font_size: int = 12,
    help_panel_gap: float = 8.0,
) -> HelpLayout | None
```

`target_rect` is the authoritative geometry; `mode` only picks font/hero-row policy. The existing `panel_rect + help_panel_gap` math becomes a helper that computes `target_rect` for `"below"` at the call site — keeps back-compat for the current `overlay help` toggle.

### `layout_root.py` changes

Insert the tri-state decision in `layout()` after overflow detection (`ui/layout_root.py:462-488`). Pseudocode:

```python
tokens_empty = len(tokens) == 0
if tokens_empty:
    help_zone_mode = "full"
    help_target = content_area           # full width, minus padding
elif hints_hidden:                       # overflow
    help_zone_mode = "hidden"
    help_target = None
else:
    help_zone_mode = "side"
    help_target = help_area              # 20% right column

# When help_visible is user-toggled AND buffer non-empty, force "full"
# (respects §5's override recommendation)
if state.help_visible and not tokens_empty:
    help_zone_mode = "full"
    help_target = content_area

help_layout = (
    build_help_layout(state, panel_rect=panel_rect, target_rect=help_target,
                      mode=help_zone_mode, hint_font_size=hint_font_size)
    if help_target is not None else None
)
```

State A also needs the empty-buffer branch to NOT emit `"listening..."` — that's a paint-side change (`draw_from_model.py`), out of scope for the pure layout module; note it here for the paint-parity retirement Forge to pick up when it lands.

### `ui/draw.py` / paint pipeline changes

Do NOT touch `ui/draw.py` today. The retirement Forge is migrating paint through `to_paint_ops` (`ui/layout.py:35`). Land the layout-side change first; the paint side gets a follow-up commit once the Forge's paint parity is green. Concretely: `ui/draw_from_model.py` will need one branch — "if `model.tokens == []` and `model.help != None`, skip `listening...` and paint help rows at `content_area`". Note it in the phase-2 issue, don't ship it now.

## §5. Interaction with existing `overlay help` toggle

Today `overlay help` toggles a paginated help panel BELOW the main panel (obscures nothing; extends downward). In the new model that surface disappears — the pager content lives inside the main panel at either full width (A) or side width (B).

**Recommend: keep `overlay help` as an override for State A.** Semantics:

- `state.help_visible == True` **AND** `len(tokens) > 0` → force State A. The pager takes over the full content area even though tokens exist. Trillium's mental model: "show me the whole help sheet regardless of what I've typed." This matches the current `overlay help` intent.
- `state.help_visible == True` **AND** `len(tokens) == 0` → State A anyway (no-op override, buffer-driven state already there).
- `state.help_visible == False` → fall through to buffer-driven A/B/C.
- Retire `ui/help.py:draw_help_panel` (the below-main pager). All rows now paint inside `panel_rect`.

**OQ1 — pick: override (recommended) or retire.** Recommended answer: **override**. Retiring `overlay help` entirely is tempting but loses the "user wants help NOW without emptying the buffer" affordance. Override is cheap — one extra `if` in `layout_root.py`.

## §6. Reversibility + State C thresholds

- **State C engages** on the same criterion as today's `hints_hidden_by_overflow`: `len(rows) * LINE_HEIGHT > usable_h - label_reserve` at `content_w - PANEL_PAD*2` (`ui/layout_root.py:455-460`). No change.
- **State C → State B on delete.** Automatic — next draw's flow-fit check succeeds, `hints_hidden = False`, `help_area` is non-None, help re-emitted. This already works today at the model level for hints; extending to side-help is a rename, not new logic.
- **State B → State A on delete-all.** `tokens_empty` becomes True → decision block routes to "full". No latching, no debounce.

## §7. Risk register

- **R1 — Content flicker.** Rapid empty ↔ non-empty transitions (dictation stream that briefly clears the buffer) will pop between A and B, resizing the help zone every frame. Options: (a) 250ms debounce on the empty-buffer → State A transition, (b) accept the flicker as an informative signal, (c) snap-only-on-idle. Recommend accepting for v0; revisit if the transition is jarring in practice.
- **R2 — State A content overflow.** If `HELP_PAGES[current]` renders taller than `content_area.h`, State A cannot fit. Options: (a) auto-shrink `hint_font_size` until it fits, (b) truncate + show "help next" cue, (c) scroll — the terminal-pinned viewport logic (`ui/layout_root.py:462-465`) already exists, extend it to help rows. Recommend (b): honor pagination via `state.help_page` and always show the "page N of M" footer.
- **R3 — `hints_hidden_by_overflow` naming.** The bool now means "help is hidden due to content overflow" — but with the tri-state model, the paint code needs the fuller `help_zone_mode` distinction. Keep the bool for backward compat with `internal/debug.py:_snapshot()` readers, ADD `help_zone_mode` to `LayoutModel` for new consumers. Deprecate the bool in a follow-up commit once no readers depend on it.
- **R4 — Retirement Forge collision.** The Forge is refactoring `ui/*` paint. Landing `layout_root.py` and `layout_help_cursor.py` changes now WILL collide. Mitigation: land only after the Forge merges its paint-parity commit. Sequence explicit in §9.

## §8. Open questions

- **OQ1**: Retire `overlay help` toggle or keep it as an override? → **Recommended: override** (see §5).
- **OQ2**: State A content — page 1 verbatim, curated hero, or paginated? → Recommend paginated with a hero header row on page 1.
- **OQ3**: Font size in State A vs B — same or scaled? → Recommend scaled: `hint_font_size * 1.25` for State A hero, `hint_font_size` for body rows; State B uses `hint_font_size` throughout.
- **OQ4**: Transition animation or snap? → Snap for v0 (matches current overflow snap).
- **OQ5**: Does State A render bubbles/shape hats/etc.? → Moot; buffer is empty so `TokenLayout`, `BubbleLayout`, `SelectionOverlay`, `FlashOverlay` all empty by construction (`ui/layout_root.py:510-598`).
- **OQ6** (new): Should `state.help_page` be scoped per-mode (separate page counter for below-pager vs full-panel)? Recommend NO — one counter. `overlay help back/next` navigates whichever mode is active.
- **OQ7** (new): When `overlay help` overrides to State A while buffer non-empty, is the buffer content preserved and re-shown on toggle-off? YES — help zone is a paint decision, not a buffer mutation.

## §9. Effort + phasing

- **Phase 1 (S) — State B/C rename.** Extend `LayoutModel` with `help_zone_mode: Literal["full","side","hidden"]`. Keep `hints_hidden_by_overflow` bool. Populate `help_zone_mode = "side" | "hidden"` in `layout_root.py` at the existing overflow branch (`ui/layout_root.py:455-488`). No behavior change; just an added field. Debug snapshot picks it up. **Cannot land until retirement Forge merges** (R4).
- **Phase 2 (M) — State A.** Extend `build_help_layout` signature (§4). Wire the empty-buffer branch in `layout_root.py`. Update `draw_from_model.py` to paint help rows in State A instead of `"listening..."`. Add hero row policy per `mode="full"`. Add pagination footer inside `content_area`. **Blocks on Phase 1.**
- **Phase 3 (S, optional) — Retire below-panel pager.** Delete `ui/help.py:draw_help_panel` (paint side). Redirect `overlay help` toggle semantics per §5. `HELP_PAGES` data + `build_help_layout` builder stay. **Blocks on Phase 2 shipping cleanly for at least one release cycle.**

Total end-to-end: **S–M**. Phase 1 is a rename + field-add. Phase 2 is the one real chunk of new geometry (widened `target_rect`). Phase 3 is subtractive.
