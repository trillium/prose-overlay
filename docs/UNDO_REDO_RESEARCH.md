# Undo / Redo Stack — Research

> **Provenance.** Synthesized 2026-06-29 from a background research-agent sweep of open-source undo / redo implementations, scoped to a voice-driven text editor with Cursorless + tree-sitter integration.
> **Companion doc:** [`VIEWPORT_RESEARCH.md`](./VIEWPORT_RESEARCH.md).

## Context — the constraints this research was scoped against

- **Editor:** voice-only, buffer-only (no file IO). Buffer is a rope or piece table in Python.
- **Two edit granularities:**
  1. **Character-level** (dictation inserting a word, a single delete).
  2. **Structural-level** (Cursorless "chuck funk" deletes a whole function node, "bring air after bat" moves an AST node). Structural edits may rewrite a contiguous range with totally different text.
- **Latency budget:** utterance → visible state change under ~100 ms. Undo bookkeeping must not add measurable lag per edit.
- **No multi-user / collaborative editing required** (OT/CRDT out of scope unless it gives a cheap undo abstraction worth borrowing).

---

## Executive framing

Three real candidates for v1:

1. **CodeMirror 6 `@codemirror/commands` history** — flat deque of HistEvents, time-based grouping with adjacency check, branch-cleared redo. Battle-tested, ~600 LOC of pure data-structure logic, ports trivially to Python.
2. **Helix `helix-core/src/history.rs`** — explicit revision tree with parent/last_child pointers, stores `(transaction, inversion)` pairs, supports `:earlier 30s` / `:later` time travel.
3. **VS Code `IUndoRedoElement`** — interface-per-element (callbacks for `undo()`/`redo()`), no canonical delta representation. Useful as a *protocol*, not a data structure.

The first two are real candidates. Skip Zed (CRDT-shaped, overkill, undo design only blog-level) and skip the Python "undo" PyPI packages (generic command-pattern, no editor-specific affordances).

---

## 1. CodeMirror 6 — `@codemirror/commands` history extension

**Source:** [`codemirror/commands` — `src/history.ts`](https://github.com/codemirror/commands/blob/main/src/history.ts) (TypeScript, MIT). [Reference](https://codemirror.net/docs/ref/).

### Data structure

```ts
class HistEvent {
  readonly changes: ChangeSet | undefined,
  readonly effects: readonly StateEffect<any>[],
  readonly mapped: ChangeDesc | undefined,
  readonly startSelection: EditorSelection | undefined,
  readonly selectionsAfter: readonly EditorSelection[]
}

class HistoryState {
  public readonly done: Branch,        // = HistEvent[]   (undo stack)
  public readonly undone: Branch,      // = HistEvent[]   (redo stack)
  private readonly prevTime: number,
  private readonly prevUserEvent: string | undefined
}
```

Two flat arrays — `done` and `undone`. Each `HistEvent` carries a `ChangeSet` (the change document, retain/insert/delete OT ops) plus the *previous* selection. The change set itself is invertible against the current document, so only one direction is stored.

### Entry points to imitate

- `historyField_: StateField` — central immutable state field holding `HistoryState`.
- `undo`, `redo`, `undoSelection`, `redoSelection` — public commands.
- `addChanges(event, time, userEvent, config, tr): HistoryState` — the core "should I append a new event or merge with the last one?" method.
- `isAdjacent(a: ChangeDesc, b: ChangeDesc): boolean` — adjacency predicate.
- `updateBranch(branch, to, maxLen, newEvent)` — stack capper.

### Grouping rule (the gold)

A new transaction merges into the prior event iff:

```ts
if (lastEvent && lastEvent.changes && !lastEvent.changes.empty && event.changes &&
    (!userEvent || joinableUserEvent.test(userEvent)) &&
    ((!lastEvent.selectionsAfter.length &&
      time - this.prevTime < config.newGroupDelay &&
      config.joinToEvent(tr, isAdjacent(lastEvent.changes, event.changes))) ||
     userEvent == "input.type.compose"))
```

Where:

```ts
const joinableUserEvent = /^(input\.type|delete)($|\.)/
// defaults:
minDepth: 100, newGroupDelay: 500, joinToEvent: (_t, isAdjacent) => isAdjacent
```

Translation: **merge if (same user-event family) AND (less than 500 ms since last) AND (the change ranges touch each other)**. Composition is literal:

```ts
new HistEvent(event.changes.compose(lastEvent.changes), ...)
```

When the predicate fails, a new HistEvent is pushed and the old one is sealed.

### Redo invalidation

Strictly linear. Any non-history transaction resets the redo stack:

```ts
return new HistoryState(done, none, time, userEvent)  // `none` = []
```

### Memory bounds

```ts
function updateBranch(branch, to, maxLen, newEvent) {
  let start = to + 1 > maxLen + 20 ? to - maxLen - 1 : 0
  let newBranch = branch.slice(start, to)
  newBranch.push(newEvent)
  return newBranch
}
```

`minDepth` defaults to 100 events; a 20-event hysteresis avoids reslicing on every push. Cap is by *count*, not bytes.

### Mapping onto structural edits

Excellent. A Cursorless "chuck funk" produces one transaction with one `ChangeSet` (a single replace of a wide range). The `joinableUserEvent` regex excludes it from the dictation-coalescing group (tag it `userEvent: "delete.structural"` or just leave `userEvent` undefined), so it lands as its own HistEvent. Exactly the intent: one structural utterance = one undo step.

---

## 2. Helix — `helix-core/src/history.rs`

**Source:** [`helix-editor/helix/helix-core/src/history.rs`](https://github.com/helix-editor/helix/blob/master/helix-core/src/history.rs); transactions in [`helix-core/src/transaction.rs`](https://github.com/helix-editor/helix/blob/master/helix-core/src/transaction.rs). Walkthrough: [DeepWiki — History and Undo System](https://deepwiki.com/helix-editor/helix/2.6-history-and-undo-system).

### Data structure (revision tree, not stacks)

```rust
pub struct History {
    revisions: Vec<Revision>,
    current: usize,
}

struct Revision {
    parent: usize,
    last_child: Option<NonZeroUsize>,
    transaction: Transaction,   // forward: parent -> this
    inversion: Transaction,     // reverse: this -> parent
    timestamp: Instant,
}
```

The root at index 0 is a sentinel. Edges form a tree; the `last_child` pointer turns the tree into a default "linear redo path" — most recent branch wins.

Why both `transaction` and `inversion`? `ChangeSet`'s `Delete(usize)` op stores no deleted text, so the inverse can't be reconstructed without snapshotting at commit time:

```rust
pub struct ChangeSet {
    pub(crate) changes: Vec<Operation>,   // Retain(n) | Delete(n) | Insert(Tendril)
    len: usize,
    len_after: usize,
}
```

### Entry points

- `commit_revision(&mut self, transaction: &Transaction, original: &State)` — append a child of `current`, compute inversion against `original`, set `current` to the new index, update parent's `last_child`.
- `undo() -> Option<&Transaction>` — returns `&current_revision.inversion` and moves `current` to parent.
- `redo() -> Option<&Transaction>` — follows `last_child`.
- `earlier(uk: UndoKind) -> Vec<Transaction>` / `later(uk: UndoKind) -> Vec<Transaction>` — time/step travel using LCA on the tree.
- `pub enum UndoKind { Steps(usize), TimePeriod(Duration) }`.

### Grouping

Helix does **not** auto-group inside `history.rs`. Grouping is decided by the command layer — each command commits one revision. If you call `commit_revision` once per dictated word, you get one revision per word. Grouping policy lives outside the data structure, which is liberating but means you bring your own debouncer.

### Redo invalidation

Non-destructive. A new edit after undo creates a *new branch*. Old branch survives in `revisions[]`, reachable only by `jump_to(target)` or `:earlier`. Vim's undo tree.

### Memory

Unbounded. DeepWiki: *"The revisions vector grows indefinitely. Long editing sessions can accumulate significant memory usage."* No GC, no cap. Tradeoff for the time-travel feature.

### Mapping onto structural edits

Native. Every `Transaction` is opaque to the history layer — a 4000-char Cursorless rewrite or a 1-char insert both fit. The `commit_revision` call site decides granularity. Pair with an "is this structural?" flag from the Cursorless adapter and you get the right behavior for free.

---

## 3. VS Code — `UndoRedoService`

**Source:** [`microsoft/vscode` — `src/vs/platform/undoRedo/common/undoRedo.ts`](https://github.com/microsoft/vscode/blob/main/src/vs/platform/undoRedo/common/undoRedo.ts) plus `src/vs/platform/undoRedo/common/undoRedoService.ts`.

### Data structure — interface, not delta

```ts
export const enum UndoRedoElementType { Resource, Workspace }

export interface IResourceUndoRedoElement {
  readonly type: UndoRedoElementType.Resource;
  readonly resource: URI;
  readonly label: string;
  readonly code: string;
  readonly confirmBeforeUndo?: boolean;
  undo(): Promise<void> | void;
  redo(): Promise<void> | void;
}

export interface IWorkspaceUndoRedoElement {
  readonly type: UndoRedoElementType.Workspace;
  readonly resources: readonly URI[];
  // ... split?(), prepareUndoRedo?()
  undo(): Promise<void> | void;
  redo(): Promise<void> | void;
}
```

Per resource, a `ResourceEditStack` holds elements (closures with `undo()`/`redo()` callbacks). The actual delta representation lives inside the text model (`editStack.ts` uses `SingleModelEditStackElement` with a snapshot of previous/next document state stored as `EditStackElement`).

### Entry points

- `pushElement(element: IUndoRedoElement)` — append.
- `undo(resource)`, `redo(resource)` — invoke the callbacks.
- `removeElements(resource)`, `setElementsValidFlag(...)` — manual GC.

### Grouping

Decided per-call by whoever pushes the element. The text model layer (TextModel + EditStack) implements its own time-based coalescing on top.

### Redo invalidation

Linear. A new push clears the redo half of the stack.

### Memory

Configurable — `editor.undoLimit` in some forks; the platform service itself does not cap by default but `ResourceEditStack` has a max size.

### Why it's interesting

The **interface-as-element** pattern is the right thing to copy if you have heterogeneous undo entries (text edits + selection changes + view-state changes). Cleaner than encoding all into one `ChangeSet` union. Borrow the *shape* (each entry implements `undo()`/`redo()` callable) without copying the rest.

---

## 4. Emacs — `buffer-undo-list`

**Source:** [GNU Emacs Lisp Reference Manual — Undo](https://www.gnu.org/software/emacs/manual/html_node/elisp/Undo.html).

### Data structure

One global per-buffer list: `buffer-undo-list`. Heterogeneous elements include:

- `(BEG . END)` — insertion at BEG to END.
- `(TEXT . POSITION)` — deletion (the deleted text *is stored*).
- `(t HIGH LOW MICRO PICO)` — modification time marker.
- `(nil PROPERTY VALUE BEG . END)` — property change.
- `nil` — **boundary marker** between change groups.

### Grouping

By explicit boundary insertion. `undo-boundary` is called by the command loop after every interactive command. `primitive-undo(count, list)` walks until it has popped `count` boundaries.

### Redo invalidation

There is no redo. "Redo" in Emacs is "undo the undo" — which itself becomes new entries on `buffer-undo-list`. Linear-only, but full history is preserved as long as the list isn't truncated.

### Memory

Truncated by `undo-limit` (160000 bytes default), `undo-strong-limit`, `undo-outer-limit`.

### Why it's interesting

The *boundary marker* idea is the cleanest separation of "change record" from "grouping policy" in any of these systems. **Steal this.** Storing boundaries as in-band sentinels lets you delay the "should this be a new group?" decision until commit time, and lets a voice command emit `begin_group` / `end_group` directly.

### Mapping onto structural edits

Fine. A Cursorless edit is a single insertion+deletion pair flanked by two `nil` boundaries. Done.

---

## 5. ProseMirror — `prosemirror-history`

**Source:** [`ProseMirror/prosemirror-history`](https://github.com/ProseMirror/prosemirror-history).

Branch-array of `Item`s (each a step + selection bookmark), grouped into "events" by `newGroupDelay` (default 500 ms) and a `depth` cap. `addToHistory: false` transaction metadata is the escape hatch for non-undoable changes.

Key trick: **selective undo via rebasing**. When a non-undoable transaction lands between undoable ones, undo rebases the inverse steps over the intervening change. More machinery than v1 needs, but if you ever want "undo only my dictation, not the LSP's autoformat", this is the model.

---

## 6. Slate.js — `slate-history`

**Source:** [`ianstormtaylor/slate/packages/slate-history/src/with-history.ts`](https://github.com/ianstormtaylor/slate/blob/main/packages/slate-history/src/with-history.ts).

Two stacks of `Batch` objects, each batch a list of `Operation`. Undo maps `Operation.inverse` over the batch and applies in reverse, wrapped in `Editor.withoutNormalizing` so the doc isn't half-fixed-up between steps. The `withoutNormalizing` pattern is worth borrowing as **"defer tree-sitter parse + side effects until the whole undo batch is applied."**

---

## 7. Quill — Delta history

**Source:** [Quill History Module](https://quilljs.com/docs/modules/history/).

Stack of `Delta` (OT) operations. Time-based grouping via `delay` option. Two bugs to flag if you copy: delta deletes don't carry the deleted text (same problem Helix solves by storing both `transaction` and `inversion`), and `diff()`-based undo computation can pick the wrong indices under concurrent edits. **Don't use diff-based reconstruction**; store the inverse at commit time.

---

## 8. GtkSourceView — `GtkSourceBuffer`

**Source:** [GtkSourceBuffer reference](https://developer-old.gnome.org/gtksourceview/stable/GtkSourceBuffer.html).

Two API affordances worth borrowing:

- `gtk_text_buffer_begin_user_action()` / `..._end_user_action()` — explicit group boundaries.
- `gtk_source_buffer_begin_not_undoable_action()` / `..._end_not_undoable_action()` — closes a "no undo" scope and clears the redo stack on close. Useful for initial buffer load.

---

## 9. Python options

| Package | Status |
|---|---|
| **rope `rope.base.history.History`** | Refactoring-library scope. Tracks `Change` objects with `do()` / `undo()` callbacks. Per-project, not per-buffer. [Source](https://github.com/python-rope/rope/blob/master/rope/base/history.py). Useful as a *callback-based* reference but not the right grain. |
| PyPI `undo` packages | Generic command-pattern toys. Skip. |

There is no "obvious" Python undo lib to pull in. You're writing this yourself. That's fine — the right model is ~200 LOC.

---

## Recommended stack for v1

**Clone CodeMirror 6's data-structure-and-grouping model. Borrow Emacs's explicit `undo-boundary` and Helix's `(transaction, inversion)` pair shape. Skip the tree.**

Concretely:

- **Two deques**, `done` and `undone`, of `UndoRecord` objects. Cap `done` at `min_depth = 200` (voice editing produces fewer events than typing, want headroom). Cap by *count* with a 20-event hysteresis like CM6's `updateBranch`.
- **Time + adjacency grouping** for dictation streams: `newGroupDelay = 400 ms`, merge if the new edit's range touches the previous edit's range AND the previous edit's `kind` is `dictation` (CM6's `joinableUserEvent` regex generalized). Compose deltas on merge.
- **Explicit boundary API** (`begin_group` / `end_group`) for Cursorless. Each structural command opens a group, applies one range-replace, closes the group. The grouping debouncer is bypassed entirely. This is the Emacs `undo-boundary` move.
- **Store both forward and inverse** explicitly. For dictation inserts, the inverse is "delete [start, start+len)" — trivial. For structural replacements, snapshot `old_text` at commit time. Same reason Helix carries `inversion`: piece-table deletes don't retain bytes.
- **Linear redo invalidation** (any new edit clears `undone`). The undo-tree is seductive but the voice UX for navigating branches is unsolved — no mouse, don't want to spend latency budget on "branch 3 of 5." Defer until v2 if ever. Keep the data structure compatible (parent pointer field reserved) so you can upgrade later without rewriting callers.
- **Latency.** Every operation is `O(1)` amortized — deque append + `time.monotonic()` compare + at most one composition. Well under 100 ms. Composition cost is the only real risk; cap by sealing groups after N composed deltas (CM6 doesn't, but you should — say 64).

### Proposed record shape

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class EditKind(Enum):
    DICTATION = "dictation"            # character/word-level voice input
    STRUCTURAL = "structural"          # Cursorless AST edit
    EXPLICIT = "explicit"              # explicit command (e.g. "undo that")
    PROGRAMMATIC = "programmatic"      # plugin/LSP/format-on-save

@dataclass
class Delta:
    """One contiguous range replacement on the buffer."""
    start: int                         # byte or codepoint offset, pick one
    old_len: int                       # length being replaced
    old_text: str                      # the displaced bytes (needed for inverse)
    new_text: str                      # the inserted bytes

    @property
    def new_len(self) -> int:
        return len(self.new_text)

@dataclass
class UndoRecord:
    deltas: list[Delta]                # composed deltas in apply order
    kind: EditKind
    label: str                         # for UI: "delete function 'foo'"
    timestamp: float                   # time.monotonic() at first delta
    selection_before: tuple[int, int]  # (anchor, head) before this group
    selection_after: tuple[int, int]   # (anchor, head) after this group
    sealed: bool = False               # True ⇒ never merge into this record
    # Reserved for future undo-tree upgrade:
    parent_index: Optional[int] = None
    children: list[int] = field(default_factory=list)
```

### Grouping rule (concrete)

```python
SHOULD_MERGE = (
    not last.sealed
    and last.kind == EditKind.DICTATION
    and new.kind == EditKind.DICTATION
    and (now - last.timestamp) < 0.400
    and ranges_touch(last.last_delta_range, new.delta_range)
    and len(last.deltas) < 64
)
```

Anything `STRUCTURAL` or `EXPLICIT` arrives pre-sealed. `PROGRAMMATIC` writes can either skip history (Slate's `addToHistory: false` / ProseMirror's metadata) or land as their own sealed record — your call, but skipping is what tree-sitter incremental re-parses should do.

### What I'd actively not do for v1

- Don't build the revision tree. Vim's undo tree is beloved but unusable without a UI, and your UI is voice. Pay the cost when there's a story for "show me my branches" by voice.
- Don't store text snapshots of the whole buffer per record. Deltas + `old_text` are sufficient and bounded.
- Don't roll your own OT/CRDT machinery. You don't need `compose`, you need `extend` (append a delta to the trailing record) and `invert` (per-delta, trivial).
- Don't use diff-based undo reconstruction (Quill's footgun). Capture `old_text` at edit time.

---

## Three things worth catching pre-implementation (synthesis)

1. **No diff-based reconstruction.** Snapshot `old_text` at commit time. Quill's known bug.
2. **`PROGRAMMATIC` skip-history flag from day one.** Incremental tree-sitter re-parses, future LSP formatters, etc. Easy now, expensive to retrofit.
3. **Cap composition at 64 deltas per record** even within the merge window. CodeMirror doesn't but should. Prevents one pathological dictation burst from creating a 50 KB unbreakable record.

---

## Sources

- [codemirror/commands — src/history.ts](https://github.com/codemirror/commands/blob/main/src/history.ts)
- [CodeMirror Reference Manual](https://codemirror.net/docs/ref/)
- [CodeMirror discuss — More conventional undo behaviour?](https://discuss.codemirror.net/t/more-conventional-undo-behaviour/5565)
- [helix-editor/helix — helix-core/src/history.rs](https://github.com/helix-editor/helix/blob/master/helix-core/src/history.rs)
- [helix-editor/helix — helix-core/src/transaction.rs](https://github.com/helix-editor/helix/blob/master/helix-core/src/transaction.rs)
- [DeepWiki — Helix History and Undo System](https://deepwiki.com/helix-editor/helix/2.6-history-and-undo-system)
- [Zed Blog — How CRDTs make multiplayer text editing part of Zed's DNA](https://zed.dev/blog/crdts)
- [microsoft/vscode — src/vs/platform/undoRedo/common/undoRedo.ts](https://github.com/microsoft/vscode/blob/main/src/vs/platform/undoRedo/common/undoRedo.ts)
- [GNU Emacs Lisp Reference Manual — Undo](https://www.gnu.org/software/emacs/manual/html_node/elisp/Undo.html)
- [Vim documentation — undo.txt](https://vimhelp.org/undo.txt.html)
- [ProseMirror/prosemirror-history](https://github.com/ProseMirror/prosemirror-history)
- [ianstormtaylor/slate — packages/slate-history/src/with-history.ts](https://github.com/ianstormtaylor/slate/blob/main/packages/slate-history/src/with-history.ts)
- [Quill History Module](https://quilljs.com/docs/modules/history/)
- [GtkSourceBuffer reference](https://developer-old.gnome.org/gtksourceview/stable/GtkSourceBuffer.html)
- [rope library — overview](https://rope.readthedocs.io/en/latest/overview.html)
- [Charles Crowley — Data Structures for Text Sequences](https://www.cs.unm.edu/~crowley/papers/sds/sds.html)
