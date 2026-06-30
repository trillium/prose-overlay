# Python Health Report — prose-overlay

> Generated 2026-06-29 via `uvx radon` + `uvx vulture`.
> Regenerate: `bash scripts/python-report.sh` (or re-run the commands at the
> bottom of this file).
>
> Replaces the earlier `FALLOW_REPORT.md` — fallow analyzes JS/TS only and
> 99% of its findings were in vendored cursorless bundles.

## TL;DR

- **3996 LOC** across 25 `prose_overlay_*.py` modules.
- **Avg cyclomatic complexity: 3.18 (A).** Codebase is generally simple.
- **Maintainability index avg: ~71 (A).** Lowest file at 43.48 — still A grade.
- **One dead variable.** `prose_overlay.py:158 'auto_cap'` (100% confidence).
- **Two files over the 250-line gate** (brain ISA `brain-n5uc` — applies to
  the massage repo, used here as a sensible internal guideline):
  - `prose_overlay_cursorless_resolve.py` — **484 LOC**
  - `prose_overlay_actions_cursorless.py` — **440 LOC**

## Refactor candidates (by complexity, ranked)

| File:Line | Function | CC | Grade | Why it's flagged |
|:----------|:---------|---:|:-----:|:-----------------|
| `prose_overlay_cursorless_resolve.py:256` | `_resolve_primitive_to_token_range` | **31** | **E** | Long if/elif chain across modifier kinds + scope types. Candidate: dispatch table keyed by `mod_type`. |
| `prose_overlay_draw_tokens.py:101` | `_draw_token_rows` | 23 | D | Token rendering with hat, highlight, cursor, flash all interleaved. Candidate: extract per-token render fn. |
| `prose_overlay_draw.py:130` | `draw_overlay` | 22 | D | Main draw routine — fallback colors, overflow handling, anchor mode, listening hint. Candidate: extract panel-frame and content-layout phases. |
| `prose_overlay_cursorless_resolve.py:399` | `_resolve_target_to_token_range` | 19 | C | Target-type dispatch (primitive / range / list / implicit). Tolerable, but if it grows further consider per-type fn. |
| `prose_overlay_cursorless_resolve.py:166` | `_resolve_surrounding_pair` | 17 | C | Symmetric + asymmetric pair handling + `any`/`pair` aggregation. Splittable into `_pair_asymmetric` / `_pair_symmetric`. |
| `prose_overlay_state.py:16` | `compute_hat_assignments` | 13 | C | Python fallback for the JS allocator. CC matches the algorithmic shape; refactor only if extending. |
| `prose_overlay_actions_cursorless.py:108` | `_apply_edit_plan` | 12 | C | Edit-plan execution with snapshot/undo + flash + cursor sync. |
| `prose_overlay_targets_js.py:175` | `resolve_target` | 12 | C | JS-bridge resolution path. New code; CC reflects target-shape variety. |

Anything not listed is **B or A** — no action needed.

## Lowest maintainability (still all A-grade)

| File | MI | LOC |
|:-----|---:|---:|
| `prose_overlay_cursorless_resolve.py` | 43.48 | 484 |
| `prose_overlay_actions_cursorless.py` | 52.83 | 440 |
| `prose_overlay_draw.py` | 53.46 | 279 |
| `prose_overlay_help.py` | 56.36 | 235 |
| `prose_overlay_draw_tokens.py` | 56.76 | 185 |
| `prose_overlay_state.py` | 56.82 | 244 |

MI accounts for cyclomatic complexity, halstead volume, and LOC — the bottom of
the list is consistent with the complexity hotspots above.

## Dead code

```
prose_overlay.py:158: unused variable 'auto_cap' (100% confidence)
```

Trivially deletable. Everything else either is used or vulture is
under-confident (≥70% threshold).

## Recommended next moves

1. **Delete `auto_cap`** at `prose_overlay.py:158` — one-liner.
2. **Split `_resolve_primitive_to_token_range`** — the E-grade hotspot.
   Suggested shape: top-level fn dispatches to `_resolve_extend`,
   `_resolve_every_scope`, `_resolve_containing_scope`, etc., keyed off
   `mod_type`. Each sub-fn ≤ B-grade.
3. **Split `prose_overlay_cursorless_resolve.py`** (484 LOC → ~250 + ~250).
   Natural seam: surrounding-pair helpers + DELIMITER_PAIRS into a
   `prose_overlay_surrounding_pair.py` module; main resolver keeps the
   primitive/range/list/implicit dispatch.
4. **Split `prose_overlay_actions_cursorless.py`** (440 LOC). Natural seam:
   the misfire diagnostic (`_po_matcher_misfire`) and edit-plan executor
   (`_apply_edit_plan`) could move to a `prose_overlay_actions_cursorless_edit.py`
   helper.

---

## radon — cyclomatic complexity (CC)

```
prose_overlay_actions_bring_move.py
    C 20:0 Actions - B (7)
    M 45:4 Actions.prose_overlay_move_hat_to_hat - B (6)
    M 21:4 Actions.prose_overlay_bring_hat_to_hat - A (5)
prose_overlay_actions_core.py
    F 20:0 _recompute_hats - A (3)
    F 46:0 _sync_tags - A (3)
    F 60:0 _hat_to_index - A (1)
prose_overlay_actions_cursor.py
    F 59:0 _auto_scroll_to_cursor - A (3)
    F 36:0 _prose_overlay_set_cursor - A (2)
    F 44:0 _prose_overlay_clear_cursor - A (2)
    C 87:0 Actions - A (2)
    M 88:4 Actions.prose_overlay_set_cursor_before_hat - A (2)
    M 97:4 Actions.prose_overlay_set_cursor_after_hat - A (2)
    M 106:4 Actions.prose_overlay_get_cursor - A (2)
    M 130:4 Actions.prose_overlay_change_hat - A (2)
    M 143:4 Actions.prose_overlay_change_head_hat - A (2)
    M 156:4 Actions.prose_overlay_change_tail_hat - A (2)
    F 23:0 _set_cursor - A (1)
    F 53:0 _blink_tick - A (1)
    M 110:4 Actions.prose_overlay_get_change_mode - A (1)
    M 114:4 Actions.prose_overlay_get_blink_on - A (1)
    M 118:4 Actions.prose_overlay_cursor_start - A (1)
    M 124:4 Actions.prose_overlay_cursor_end - A (1)
prose_overlay_actions_cursorless.py
    F 108:0 _apply_edit_plan - C (12)
    C 200:0 Actions - A (5)
    M 201:4 Actions.prose_overlay_run_action - A (5)
    M 384:4 Actions.prose_overlay_bring_move - A (5)
    F 79:0 _cursor_to_char - A (4)
    M 271:4 Actions.prose_overlay_run_action_range - A (4)
    M 323:4 Actions.prose_overlay_apply_formatter - A (4)
    F 45:0 _po_matcher_misfire - A (3)
    F 94:0 _token_char_range - A (3)
prose_overlay_actions_delete.py
    C 23:0 Actions - A (3)
    M 24:4 Actions.prose_overlay_delete_hat - A (2)
    M 34:4 Actions.prose_overlay_delete_past_hat - A (2)
    M 45:4 Actions.prose_overlay_delete_head_hat - A (2)
    M 56:4 Actions.prose_overlay_delete_tail_hat - A (1)
prose_overlay_actions_flash.py
    F 20:0 _clear_flash - A (2)
    F 28:0 _flash_tokens - A (2)
    C 72:0 Actions - A (2)
    F 52:0 _action_color - A (1)
    M 73:4 Actions.prose_overlay_get_flash_indices - A (1)
    M 77:4 Actions.prose_overlay_get_flash_color - A (1)
prose_overlay_actions_help.py
    C 18:0 Actions - A (2)
    M 19:4 Actions.prose_overlay_help_toggle - A (1)
    M 24:4 Actions.prose_overlay_help_visible - A (1)
    M 28:4 Actions.prose_overlay_help_page - A (1)
    M 32:4 Actions.prose_overlay_help_next - A (1)
    M 38:4 Actions.prose_overlay_help_back - A (1)
    M 44:4 Actions.prose_overlay_help_bigger - A (1)
    M 50:4 Actions.prose_overlay_help_smaller - A (1)
prose_overlay_actions_history.py
    M 118:4 Actions.prose_overlay_confirm - A (5)
    C 42:0 Actions - A (3)
    F 25:0 _on_draw_history - A (2)
    M 43:4 Actions.prose_overlay_add_text - A (2)
    M 63:4 Actions.prose_overlay_speak - A (2)
    M 84:4 Actions.prose_overlay_toggle_history - A (2)
    M 110:4 Actions.prose_overlay_history_pick - A (2)
    M 144:4 Actions.prose_overlay_undo - A (2)
    F 32:0 _on_history_overlay_hide - A (1)
    M 93:4 Actions.prose_overlay_hide_history - A (1)
    M 98:4 Actions.prose_overlay_history_next - A (1)
    M 105:4 Actions.prose_overlay_history_back - A (1)
prose_overlay_actions_js.py
    F 82:0 run_action - A (3)
    F 39:0 _ensure_loaded - A (2)
    F 53:0 _make_target - A (1)
    F 69:0 _make_document - A (1)
    F 144:0 action_remove - A (1)
    F 149:0 action_set_selection - A (1)
    F 158:0 action_clear_and_set_selection - A (1)
    F 163:0 action_replace_with_target - A (1)
    F 175:0 action_move_to_target - A (1)
    F 191:0 action_set_selection_before - A (1)
    F 196:0 action_set_selection_after - A (1)
prose_overlay_actions_layout.py
    F 24:0 _on_win_focus - A (5)
    F 39:0 _on_win_move - A (5)
    C 68:0 Actions - A (4)
    M 69:4 Actions.prose_overlay_set_anchor - A (3)
    M 94:4 Actions.prose_overlay_set_anchor_position - A (3)
    M 85:4 Actions.prose_overlay_clear_anchor - A (2)
    F 57:0 _save_prefs_from_layout - A (1)
prose_overlay_actions_target.py
    M 39:4 Actions.prose_overlay_get_target_label - A (4)
    C 20:0 Actions - A (3)
    M 21:4 Actions.prose_overlay_retarget - A (1)
    M 29:4 Actions.prose_overlay_retarget_focus - A (1)
prose_overlay_actions_visibility.py
    F 40:0 _load_prefs - A (4)
    M 64:4 Actions.prose_overlay_show - A (4)
    C 63:0 Actions - A (3)
    F 27:0 _save_prefs - A (2)
    M 94:4 Actions.prose_overlay_hide - A (2)
    M 120:4 Actions.prose_overlay_toggle_auto_dictation - A (2)
    M 131:4 Actions.prose_overlay_get_selection - A (2)
    M 127:4 Actions.prose_overlay_is_active - A (1)
    M 138:4 Actions.prose_overlay_debug - A (1)
prose_overlay_canvas.py
    M 75:4 OverlayCanvas._on_draw - B (8)
    C 21:0 OverlayCanvas - A (3)
    M 50:4 OverlayCanvas.show - A (2)
    M 69:4 OverlayCanvas._on_dismissed_externally - A (2)
    M 28:4 OverlayCanvas.__init__ - A (1)
    M 42:4 OverlayCanvas.set_hat_assignments - A (1)
    M 47:4 OverlayCanvas.is_showing - A (1)
    M 57:4 OverlayCanvas.refresh - A (1)
    M 61:4 OverlayCanvas.hide - A (1)
prose_overlay_cursorless_resolve.py
    F 256:0 _resolve_primitive_to_token_range - E (31)
    F 399:0 _resolve_target_to_token_range - C (19)
    F 166:0 _resolve_surrounding_pair - C (17)
    F 100:0 _char_range_to_token_range - B (7)
    F 143:0 _cursor_gap_to_char_offset - A (3)
    F 153:0 _token_idx_to_char_offset - A (2)
    C 21:0 _ResolveState - A (2)
    F 244:0 _cursorless_symbol_to_token_index - A (1)
    M 33:4 _ResolveState.__init__ - A (1)
prose_overlay_debug.py
    F 51:0 emit_if_changed - B (8)
    F 23:0 set_debug_mode - A (2)
    F 30:0 _snapshot - A (1)
prose_overlay_draw_tokens.py
    F 101:0 _draw_token_rows - D (23)
    F 44:0 _flow_layout - B (6)
    F 28:0 _fit_text - A (5)
    F 73:0 draw_cursor - A (3)
prose_overlay_draw.py
    F 130:0 draw_overlay - D (22)
    F 98:0 _find_cursor_row - A (4)
    F 109:0 compute_scroll_for_cursor - A (4)
    F 73:0 set_anchor_position - A (2)
    F 67:0 set_anchor_rect - A (1)
    F 80:0 set_scroll_offset - A (1)
    F 90:0 get_max_visible_rows - A (1)
prose_overlay_hats_js.py
    F 47:0 compute_hat_assignments - B (9)
    F 33:0 _ensure_loaded - A (2)
prose_overlay_help.py
    F 133:0 draw_help_panel - B (7)
    F 106:0 rotate_help_ring_buffer - B (6)
    F 93:0 _build_command_pool - A (4)
prose_overlay_history_panel.py
    F 37:0 draw_history_panel - B (7)
prose_overlay_instance.py
    C 10:0 ProseOverlayState - A (2)
    M 11:4 ProseOverlayState.__init__ - A (1)
prose_overlay_state.py
    F 16:0 compute_hat_assignments - C (13)
    M 95:4 ProseBuffer._split_trailing_punct - B (6)
    M 156:4 ProseBuffer.add_text - A (3)
    M 202:4 ProseBuffer.replace_token - A (3)
    C 89:0 ProseBuffer - A (2)
    M 122:4 ProseBuffer.snapshot - A (2)
    M 128:4 ProseBuffer.undo - A (2)
    M 171:4 ProseBuffer.delete_token - A (2)
    M 178:4 ProseBuffer.delete_through - A (2)
    M 190:4 ProseBuffer.delete_head - A (2)
    M 113:4 ProseBuffer.__init__ - A (1)
    M 140:4 ProseBuffer.set_selection - A (1)
    M 144:4 ProseBuffer.clear_selection - A (1)
    M 148:4 ProseBuffer.get_selection - A (1)
    M 211:4 ProseBuffer.insert_at - A (1)
    M 218:4 ProseBuffer.get_tokens - A (1)
    M 222:4 ProseBuffer.get_text - A (1)
    M 226:4 ProseBuffer.set_tokens_raw - A (1)
    M 234:4 ProseBuffer.clear - A (1)
    M 240:4 ProseBuffer.__len__ - A (1)
    M 243:4 ProseBuffer.__bool__ - A (1)
prose_overlay_targets_js.py
    F 175:0 resolve_target - C (12)
    F 87:0 _target_to_json - B (9)
    F 69:0 _normalize_mark - A (4)
    F 149:0 _build_hat_map_json - A (3)
    F 42:0 _ensure_loaded - A (2)
    F 131:0 _token_start_offset - A (2)
    F 139:0 _build_document_json - A (2)
    F 61:0 _to_cursorless_color - A (1)
prose_overlay.py
    C 157:0 _ShimActions - A (3)
    C 149:0 _OverlayActiveActions - A (2)
    M 158:4 _ShimActions.dictation_insert - A (2)
    M 171:4 _ShimActions.insert_formatted - A (2)
    F 71:0 prose_hat_color - A (1)
    M 150:4 _OverlayActiveActions.insert_formatted - A (1)

168 blocks (classes, functions, methods) analyzed.
Average complexity: A (3.1785714285714284)
```

## radon — maintainability index (MI)

```
prose_overlay_actions_bring_move.py - A (75.58)
prose_overlay_actions_core.py - A (87.99)
prose_overlay_actions_cursor.py - A (60.35)
prose_overlay_actions_cursorless.py - A (52.83)
prose_overlay_actions_delete.py - A (78.29)
prose_overlay_actions_flash.py - A (82.67)
prose_overlay_actions_help.py - A (75.52)
prose_overlay_actions_history.py - A (60.15)
prose_overlay_actions_js.py - A (77.53)
prose_overlay_actions_layout.py - A (71.90)
prose_overlay_actions_target.py - A (92.22)
prose_overlay_actions_visibility.py - A (68.94)
prose_overlay_canvas.py - A (74.42)
prose_overlay_cursorless_resolve.py - A (43.48)
prose_overlay_debug.py - A (75.69)
prose_overlay_draw_constants.py - A (81.00)
prose_overlay_draw_tokens.py - A (56.76)
prose_overlay_draw.py - A (53.46)
prose_overlay_hats_js.py - A (79.23)
prose_overlay_help.py - A (56.36)
prose_overlay_history_panel.py - A (60.11)
prose_overlay_instance.py - A (100.00)
prose_overlay_state.py - A (56.82)
prose_overlay_targets_js.py - A (61.99)
prose_overlay.py - A (100.00)
```

## radon — raw LOC stats

```
    - Comment Stats
        (C % L): 13%
        (C % S): 21%
        (C + M % L): 20%
prose_overlay_hats_js.py
    LOC: 105
    LLOC: 46
    SLOC: 56
    Comments: 14
    Single comments: 13
    Multi: 19
    Blank: 17
    - Comment Stats
        (C % L): 13%
        (C % S): 25%
        (C + M % L): 31%
prose_overlay_help.py
    LOC: 235
    LLOC: 130
    SLOC: 163
    Comments: 31
    Single comments: 26
    Multi: 13
    Blank: 33
    - Comment Stats
        (C % L): 13%
        (C % S): 19%
        (C + M % L): 19%
prose_overlay_history_panel.py
    LOC: 132
    LLOC: 73
    SLOC: 89
    Comments: 8
    Single comments: 8
    Multi: 9
    Blank: 26
    - Comment Stats
        (C % L): 6%
        (C % S): 9%
        (C + M % L): 13%
prose_overlay_instance.py
    LOC: 38
    LLOC: 43
    SLOC: 28
    Comments: 9
    Single comments: 0
    Multi: 5
    Blank: 5
    - Comment Stats
        (C % L): 24%
        (C % S): 32%
        (C + M % L): 37%
prose_overlay_state.py
    LOC: 244
    LLOC: 146
    SLOC: 124
    Comments: 20
    Single comments: 29
    Multi: 44
    Blank: 47
    - Comment Stats
        (C % L): 8%
        (C % S): 16%
        (C + M % L): 26%
prose_overlay_targets_js.py
    LOC: 244
    LLOC: 112
    SLOC: 139
    Comments: 26
    Single comments: 25
    Multi: 33
    Blank: 47
    - Comment Stats
        (C % L): 11%
        (C % S): 19%
        (C + M % L): 24%
prose_overlay.py
    LOC: 194
    LLOC: 75
    SLOC: 113
    Comments: 38
    Single comments: 29
    Multi: 17
    Blank: 35
    - Comment Stats
        (C % L): 20%
        (C % S): 34%
        (C + M % L): 28%
** Total **
    LOC: 3996
    LLOC: 2110
    SLOC: 2343
    Comments: 435
    Single comments: 435
    Multi: 518
    Blank: 700
    - Comment Stats
        (C % L): 11%
        (C % S): 19%
        (C + M % L): 24%
```

## vulture — dead code (confidence ≥ 70%)

```
prose_overlay.py:158: unused variable 'auto_cap' (100% confidence)
```
