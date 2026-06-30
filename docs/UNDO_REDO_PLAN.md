# Undo / Redo — Implementation Plan

> Source research: [`UNDO_REDO_RESEARCH.md`](./UNDO_REDO_RESEARCH.md). Companion viewport plan shape: [`VIEWPORT_RESEARCH.md`](./VIEWPORT_RESEARCH.md).
> Drafted 2026-06-29.

## 1. TL;DR

- Keep one history object on `ProseBuffer`. Replace `_history: list[list[str]]` with two deques of `UndoRecord` (`done`, `undone`) — the CM6 shape from research §1.
- Each record stores a **forward delta** and its **inverse**, both expressed as token-range replacements: `replace tokens[start:end] with new_tokens`. Helix's `(transaction, inversion)` pair (research §2) generalized to this buffer's grain.
- Adopt CM6 time+adjacency coalescing for dictation streams. `newGroupDelay = 400 ms`, merge when previous record is `DICTATION` and the new edit's token range touches the last delta's range.
- Cursorless / structural edits arrive **sealed** (Emacs boundary, research §4). One utterance = one undo step.
- Add a monotonic `rev: int` counter, bumped on every applied record (forward, undo, or redo). The viewport's `SkParagraph` cache will key on it; same field used by `prose_overlay_debug.py` diff emission. Sibling viewport agent has the same recommendation — coordinate on the field name.
- Redo invalidation is linear (CM6 rule). Any new forward edit clears `undone`. Defer the undo tree (Helix) until there is a voice UX for branches.
- Cap `done` at 200 records (CM6 default `minDepth=100`, doubled for voice headroom). Cap composed deltas per record at 64 (research §Three things worth catching).
- Two-phase migration: Phase 1 swaps the internal representation behind the existing `snapshot()` / `undo()` API (no caller changes), Phase 2 adds redo + grouping policy + the `commit()` boundary API used by Cursorless. Phase 3 is voice-UX polish (`overlay redo five`).

## 2. Current-state assessment

What this codebase has today (`prose_overlay_state.py:113-238`):

- `_history: list[list[str]]` — a stack of full token-list snapshots.
- `_HISTORY_MAX = 20` — count-bounded with `pop(0)` on overflow.
- Every mutation method (`add_text`, `delete_token`, `delete_through`, `delete_head`, `replace_token`, `insert_at`) calls `self.snapshot()` first.
- `set_tokens_raw()` is the explicit escape hatch that does **not** snapshot — used by `prose_overlay_actions_cursorless.py:108 _apply_edit_plan`, which takes one manual `snapshot()` before applying a JS edit plan that internally may produce N edits.
- `undo()` pops and restores; clears selection; returns `bool`.
- No redo. No grouping (every mutation is its own snapshot). No revision counter. No labels. No selection-before / selection-after restore.

What's "good enough today": the snapshot-everything strategy is correct for v0. Token lists are short (< 200 tokens typical), so 20 full copies is ~bytes, not a memory problem. The `bool` return lets the action layer notify the canvas cleanly.

Gaps vs. research:

1. **No redo.** Research §1, §3, §4: every editor surveyed has redo. Cheap to add once the representation is delta-shaped.
2. **No coalescing.** Dictation that streams 8 words in 800 ms produces 8 undo steps; user has to say "overlay undo" 8 times to get back. CM6's `newGroupDelay` (research §1 "Grouping rule") solves this.
3. **No structural boundary.** `_apply_edit_plan` is the one site that handles a multi-edit transaction (a Cursorless `bring`/`move` produces 2 edits — destination insert + source delete). Today it takes one snapshot manually. The Emacs boundary pattern (research §4) makes this the rule rather than the exception.
4. **No revision counter.** Future SkParagraph cache (viewport plan §"Things to act on") needs one. Cheap and load-bearing.
5. **Snapshot cost is O(n) in token count.** Trivial today (< 200 tokens). Becomes real if the buffer ever holds long-form prose. Delta storage is O(edit-size) instead.

What's **not** broken and shouldn't be over-engineered:

- The voice command `overlay undo` works.
- The action layer (`prose_overlay_actions_history.py:144`) is one line: `if instance.buffer.undo(): … refresh`. Don't break it.
- `set_tokens_raw` is doing real work as the "I already snapshotted, don't touch history" escape hatch. The new API keeps an equivalent.

## 3. Recommended approach

**Clone CodeMirror 6's data-structure-and-grouping model. Borrow Emacs's explicit boundary for Cursorless. Store both forward and inverse per Helix. Skip the revision tree.**

This is the exact recommendation from research §"Recommended stack for v1," adapted for a token-list buffer instead of a character rope. The reasons it wins for *this* codebase:

1. **CM6's two-deque shape ports trivially to Python `collections.deque`.** `appendleft` / `pop` are O(1). The grouping predicate is a 6-line `if`. No tree machinery.
2. **The Emacs boundary pattern matches `_apply_edit_plan` exactly.** Cursorless edit plans are already "atomic transactions" in spirit — the JS shim returns a list of edits that should undo as one step. A boundary API (`commit(label, kind=STRUCTURAL)`) formalizes what the manual `snapshot()` call there is already doing.
3. **Helix's `(transaction, inversion)` pair is necessary, not optional.** A token-replace delta of the form `replace tokens[5:8] with ["foo", "bar"]` cannot be inverted without snapshotting the displaced `["old1", "old2", "old3"]` at commit time. Same reason Helix carries `inversion`. (Research §2.)

Alternatives considered and rejected:

- **Helix's revision tree** (§2). Beautiful for keyboard editors with `:earlier 30s`. No voice UX story for "branch 3 of 5." Defer.
- **VS Code's `IUndoRedoElement` callback interface** (§3). Right shape if entries are heterogeneous (text + selection + view-state). This buffer has one entry type (token-range replacement), so the callback indirection is overhead without payoff. Borrow only the `label: str` field for future UI affordances.
- **Keep snapshotting full token lists.** Simplest. Loses redo, grouping, and the revision-counter affordance the viewport plan needs. Worth keeping if Phase 1 alone is what ships and Phase 2 never does — but the data-structure change in Phase 1 already pays for itself.

## 4. File-by-file change inventory

| File | Status | LOC delta | What changes |
|---|---|---|---|
| `prose_overlay_state.py` | modified | `+120 / -25` | Add `EditKind`, `TokenDelta`, `UndoRecord` dataclasses. Replace `_history: list[list[str]]` with `_done: deque[UndoRecord]` + `_undone: deque[UndoRecord]`. Add `rev: int` field, bumped on every applied record. Rewrite `snapshot()` to be a legacy shim (Phase 1 only — see Migration). Add `commit(label, kind)`, `redo()`, `can_undo()`, `can_redo()`. Each mutation method computes a delta before mutating, calls `_record(delta, kind, label)`. |
| `prose_overlay_actions_history.py` | modified | `+12 / -1` | Add `prose_overlay_redo()` action mirroring `prose_overlay_undo()`. Both call `_recompute_hats` + `canvas.refresh()` on success. |
| `prose_overlay_actions_cursorless.py` | modified | `+5 / -2` | Replace the manual `instance.buffer.snapshot()` at line 131 with `instance.buffer.commit_start(label=action_name, kind=STRUCTURAL)` / `commit_end()` bracketing the edit-plan application. Same for the snapshot at line 369 in `prose_overlay_apply_formatter`. **Coordinate with sibling Forge** — this file is being refactored. The change is mechanical: wherever a `snapshot()` is called before `set_tokens_raw()`, replace with the bracket. If the refactor moves `_apply_edit_plan` to a new module, the bracket moves with it. |
| `prose_overlay.talon` | modified | `+3 / -0` | Add `overlay redo` and `overlay redo <number_small>` bindings. |
| `prose_overlay_state.py` legacy `snapshot()` | (same file, called out separately) | n/a | Phase 1 keeps `snapshot()` as a thin wrapper that opens an implicit single-step group, since `_apply_edit_plan` and `prose_overlay_apply_formatter` are the only external callers and may not have been refactored yet. Phase 2 deprecates with a `print()` warning. Phase 3 removes. |
| **(new)** `prose_overlay_history_core.py` | new file (optional) | `+150` | Only created if Phase 2's `UndoRecord` machinery pushes `prose_overlay_state.py` over 350 LOC (currently 244). If so, move `EditKind`, `TokenDelta`, `UndoRecord`, and the grouping predicate here; `ProseBuffer` imports them. **Default: don't create; keep it all in `prose_overlay_state.py`** until the LOC gate forces the split. The Python report calls out a 250-line gate (`brain-n5uc`); `+120` puts the file at 364, which is over. Plan to split as part of Phase 2 if it ships. |

Net Phase 1 + 2: roughly **+140 / -28**, one new file likely needed in Phase 2 to keep `prose_overlay_state.py` under the 250-LOC guideline. Sibling agent's refactor of `prose_overlay_actions_cursorless.py` is independent of this change set as long as the `commit_start` / `commit_end` bracket lands wherever `_apply_edit_plan` ends up.

## 5. API surface — exact signatures

Going into `prose_overlay_state.py` (or `prose_overlay_history_core.py` if split). Names match research §"Proposed record shape" with adjustments for token-list grain:

```python
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time


class EditKind(Enum):
    DICTATION = "dictation"        # add_text / insert_at from voice dictation
    STRUCTURAL = "structural"      # Cursorless edit-plan, formatter, bring/move
    EXPLICIT = "explicit"          # named voice command (delete_hat, change_hat, etc.)
    PROGRAMMATIC = "programmatic"  # internal — skipped from history (reserved)


@dataclass
class TokenDelta:
    """One contiguous token-range replacement. Token-grained, not character."""
    start: int                     # token index where replacement begins
    old_tokens: list[str]          # displaced tokens (needed for inverse)
    new_tokens: list[str]          # tokens inserted in place


@dataclass
class UndoRecord:
    """One undoable group. Holds deltas in apply order plus selection."""
    deltas: list[TokenDelta]                       # composed deltas, apply order
    kind: EditKind
    label: str                                     # for future UI ("delete tail bat")
    timestamp: float                               # time.monotonic() at first delta
    selection_before: Optional[tuple[int, int]]    # buffer._selection at start
    selection_after: Optional[tuple[int, int]]     # buffer._selection at end
    sealed: bool = False                           # True => never merge into this


# --- ProseBuffer additions / replacements --- #

class ProseBuffer:
    _HISTORY_MAX = 200                # was 20; voice-scale headroom (CM6 minDepth=100 doubled)
    _GROUP_DELAY_S = 0.400            # CM6 newGroupDelay generalized
    _MAX_COMPOSED_DELTAS = 64         # cap per-record composition (research §3 of "things to catch")

    def __init__(self) -> None:
        self._tokens: list[str] = []
        self._selection: Optional[tuple[int, int]] = None
        self._done: deque[UndoRecord] = deque(maxlen=self._HISTORY_MAX)
        self._undone: deque[UndoRecord] = deque(maxlen=self._HISTORY_MAX)
        self._open_group: Optional[UndoRecord] = None   # set between commit_start / commit_end
        self.rev: int = 0                                # monotonic; bumped on every applied record

    # ---- public undo / redo --------------------------------------------------

    def undo(self) -> bool:
        """Pop the top of done, apply inverse, push onto undone. Return True if popped."""

    def redo(self) -> bool:
        """Pop the top of undone, re-apply forward, push onto done. Return True if popped."""

    def can_undo(self) -> bool: ...
    def can_redo(self) -> bool: ...

    # ---- explicit boundary API (for Cursorless / formatter) ------------------

    def commit_start(self, label: str, kind: EditKind = EditKind.STRUCTURAL) -> None:
        """Open a multi-delta group. Mutations between start/end land in one record."""

    def commit_end(self) -> None:
        """Seal the open group, push to done, clear undone, bump rev."""

    # ---- legacy shim (Phase 1 only; deprecated in Phase 2) --------------------

    def snapshot(self) -> None:
        """DEPRECATED. Opens a single-step implicit group. Use commit_start/end."""

    # ---- internal ------------------------------------------------------------

    def _record(self, delta: TokenDelta, kind: EditKind, label: str) -> None:
        """Append delta to open group, or open + close a new group, with CM6 coalescing."""
```

Behavioral contracts (one-liners, the load-bearing ones):

- `undo()` and `redo()` set `_selection` to the record's `selection_before` / `selection_after`.
- `commit_start` while a group is already open is a no-op (nested-safe — for the case where `_apply_edit_plan` calls into another mutation method that would otherwise self-commit).
- Mutations called *outside* any `commit_start` / `commit_end` bracket auto-commit one delta as their own record, applying the CM6 merge rule against the top of `_done`.
- `_record` clears `_undone` on every non-history mutation (CM6 linear-redo rule).
- The composition cap: if `len(_open_group.deltas) >= _MAX_COMPOSED_DELTAS`, close the group, open a new one with the same `kind` and `label`. Prevents pathological dictation bursts from one unbreakable 50 KB record.

## 6. Voice commands

Append to `prose_overlay.talon`. Match the existing style (verb-first, lowercase, `overlay` prefix for top-level edits):

```talon
# Redo the last undone edit
overlay redo: user.prose_overlay_redo()

# Redo N steps at once (mirror of existing "overlay undo" which is single-step today)
overlay redo <number_small>: user.prose_overlay_redo_n(number_small)

# Multi-step undo (Phase 3 polish — symmetric with redo)
overlay undo <number_small>: user.prose_overlay_undo_n(number_small)
```

The existing single-step `overlay undo: user.prose_overlay_undo()` line stays. The new `<number_small>` variants are additive.

## 7. Migration path

### Phase 1 — internal swap, zero caller change

Rewrite `ProseBuffer._history` as the deque-of-records shape. Keep `snapshot()` and `undo()` signatures identical to today; they just internally route through `_record` + `commit_start` / `commit_end`. Every mutation method becomes "compute delta, call `_record`". The manual snapshot in `_apply_edit_plan` still works because `snapshot()` is preserved as a shim. Add `rev: int` and bump it from `_record`. No new voice commands. No redo yet — `_undone` exists but stays empty.

Smoke test: existing `overlay undo` works identically. Hat re-allocations behave the same. Debug JSONL diff includes the new `rev` field if `prose_overlay_debug.py` is wired to it (separate change — out of scope).

**Commit:** `feat(state): swap history to delta+inverse records (no behavior change)`

### Phase 2 — real shape

Add `redo()`, `commit_start()`, `commit_end()`. Add `overlay redo` voice binding. Switch the two manual-snapshot sites in `prose_overlay_actions_cursorless.py` from `snapshot()` to `commit_start` / `commit_end` brackets. Implement CM6 coalescing — dictated streams within 400 ms merge into one record. Cursorless edits arrive sealed. Print a `# DEPRECATION` warning the first time `snapshot()` is called from outside `prose_overlay_state.py` per session.

Smoke test: dictate 5 words in 2 seconds, say `overlay undo` once → all 5 words disappear. Run a Cursorless `chuck funk` → one undo step. `overlay redo` brings either back. New forward edit after undo clears redo stack.

**Commit:** `feat(state): redo + boundary API + dictation coalescing`

### Phase 3 — polish (optional)

Remove the deprecated `snapshot()` shim entirely. Add `overlay undo <number_small>` and `overlay redo <number_small>` voice commands. Wire `UndoRecord.label` to a future `overlay undo what` HUD line. Consider Emacs-style `recenter-top-bottom` cycling for the history HUD if one is ever built. Defer indefinitely if Phase 2 covers the lived UX.

**Commit:** `feat(state): drop snapshot() shim, add N-step undo/redo`

## 8. Risk / non-goals

**What could break:**

- **Selection restore.** Today `undo()` sets `_selection = None`. Phase 2 restores `selection_before`. If any caller depended on the old "undo clears selection" behavior, it will see selection reappear after undo. Grep showed no such dependency (`set_selection` is only called from `prose_overlay_actions_cursorless.py` for `setSelection`/`clearAndSetSelection` actions, and those are themselves undoable). Low risk; flag for verify.
- **`set_tokens_raw` callers.** `_apply_edit_plan` and `prose_overlay_apply_formatter` both call `snapshot()` then `set_tokens_raw()`. In Phase 1 this still works (the shim opens a one-step group around the next `set_tokens_raw` mutation). In Phase 2 they switch to brackets explicitly. If the sibling Cursorless refactor moves these calls to a new module, the bracket pattern moves with them — no semantic change.
- **History depth jump (20 → 200).** Memory is a non-issue (tokens are short, records are deltas). The user-visible change: `overlay undo` can now reach further back. No reported case where the 20-cap was load-bearing.
- **Dictation coalescing changes the feel.** Today, each `add_text` is a separate undo step. After Phase 2, a fast dictated phrase is one step. This is the *desired* behavior per research §1, but it's a behavioral change worth one verification session. If undesirable, set `_GROUP_DELAY_S = 0.0` and coalescing is off without removing the machinery.

**Explicit non-goals:**

- **No per-character undo.** This buffer is token-grained; characters within a token are atomic.
- **No undo tree / time travel / branches.** Field reserved (`parent_index` is not added until there's a voice UX for it). If added later, the existing linear API still works.
- **No `PROGRAMMATIC` skip-history flag in v1.** No current caller needs it — `set_tokens_raw` is the only "skip history" path and it's used inside an explicit commit bracket. Reserved for future LSP / formatter integrations (research §1, "PROGRAMMATIC skip-history flag from day one" — disagreed: there's no caller yet, so add it when the first one appears).
- **No diff-based undo reconstruction.** Quill's known footgun (research §7). We snapshot `old_tokens` at commit time, like Helix.
- **No multi-buffer history.** One `ProseBuffer`, one history.

## 9. Open questions for Trillium

1. **Coalescing on by default or behind a setting?** Phase 2 defaults to `_GROUP_DELAY_S = 0.400`. If you'd rather start with it off (each `add_text` = its own undo step, today's behavior) and toggle on later via `overlay undo group on`, that's a 5-minute change. Recommendation: ship it on; it's the whole point. Toggle is the fallback.
2. **`overlay redo` or `overlay forward`?** "Redo" is the term every editor uses but it's a homophone with "redo" the dictation word and may collide with raw_prose capture. "Overlay forward" / "overlay restore" is unambiguous. Lean toward `overlay redo` for muscle memory; switch if the dictation intercept eats it.

---

*Plan ends. Implementation lives behind a clean Phase 1 commit that should be invisible at the voice layer.*
