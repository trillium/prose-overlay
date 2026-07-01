# Feature Parity — Rebuttal: What `trillium_talon` and Talon Stdlib Already Cover

> Companion to `FEATURE_PARITY.md`. For each open row in that doc, tier how much of the work is already handled by **`trillium_talon`** (Trillium's own fork of community at `~/.talon/user/trillium_talon/`) and **Talon's stdlib** (`clip`, `actions.edit`, …) so prose-overlay's actual surface shrinks to "register a rule" rather than "build new substrate."
>
> Drafted 2026-06-30. **Revised 2026-06-30 after verification pass (see `REBUTTAL_ASSERTIONS.md`):** original draft misattributed every cited capture/verb to a "Talon community plugin." Community plugin is NOT installed in this setup (`find ~/.talon/user/ -maxdepth 2 -type d -name "*ommunity*"` returns only `__talon_community/trillium/`). The actual surface lives in `trillium_talon` + Talon stdlib. Re-attributed throughout. Costs estimates and the §4 `replace_selection` citation also corrected.

## Lens

`trillium_talon` (`~/.talon/user/trillium_talon/`) is Trillium's own fork of community-style code — captures, lists, actions, and grammar conventions for numbers, symbols, editing, formatters, etc. Talon's stdlib provides cross-cutting primitives like `clip` (system clipboard). Anything we can reach by registering a Talon rule that consumes a `trillium_talon` capture or calling a stdlib/`actions.edit` verb is **free leverage** — we don't own the parse, we don't own the conventions, we just route it into the prose-overlay buffer.

That `trillium_talon` is Trillium's own code makes the leverage *stronger* than a typical upstream lift: when the existing surface doesn't quite fit, he can extend `trillium_talon` rather than route around it.

The question is: for each open `[ ]` / `[~]` row, what fraction of the work is already done by `trillium_talon` or Talon stdlib?

## Tier 1 — `trillium_talon` / stdlib handle it almost entirely; prose-overlay just registers rules

These are near-free wins. Estimate: ~30-80 LOC per row, one bundled PR for all three.

| Row | Why it's already covered | Prose-overlay's residual work |
|---|---|---|
| **§2** Number hat namespace (`chuck num 1`) | `trillium_talon` ships `<user.number_small>` and number-string captures at `~/.talon/user/trillium_talon/core/numbers/numbers.py` — parse and spoken-form vocabulary already locked. | Register `chuck num <user.number_small>:` in `prose_overlay.talon`, resolve int → token index using existing `_hat_to_index`-style helper. |
| **§2** Letter hat addressability for digits/punct | `trillium_talon/core/keys/keys.py` + `keys.talon` + `symbols.py` define `<user.symbol_key>` and digit captures with full spoken-form vocab (verified in 5 files under trillium_talon). | Widen the hat-target capture via composition: `chuck (<user.letter> \| <user.digit> \| {user.symbol_key}):`. Or register a new `<user.prose_overlay_hat>` capture that unions them. |
| **§7** Cut/copy/paste through system clipboard | **Talon stdlib** provides `clip.set_text()` / `clip.text()` (built-in module, not community). **`trillium_talon`** provides `actions.edit.cut/copy/paste` verb routing — confirmed in `core/edit/edit_command.py:163,165` and `core/edit/edit_paragraph.py:49,54,59`. | Wire `take air` (or a new `copy <hat>`) to extract the token's text and call `clip.set_text(text)`; wire `paste` to `clip.text()` → `add_text`. |

**Already shipped — call out so it doesn't get rebuilt:** §1 trailing-punct split, phrase enders (`period`, `comma`, ...), `<user.number_string>` route, `<user.raw_prose>` capture. (`FEATURE_PARITY.md` notes "community grammar" — actual source is `trillium_talon`'s parse layer, not an upstream community plugin.) The parse runs there; the only prose-overlay code is routing the captured string into `buffer.add_text`.

## Tier 2 — `trillium_talon` / stdlib give you the pattern and verb conventions, but the implementation is custom because prose-overlay's buffer is its own thing

You get to mirror existing verb names, capture shapes, and arg conventions for voice-grammar consistency — but you implement against `ProseBuffer`, not a host editor.

| Row | What's already given | What you still own |
|---|---|---|
| **§1** `[~]` Insertion at cursor preserves split boundary | `actions.edit.insert(text)` is the verb-convention precedent (Talon stdlib + `trillium_talon` routing). | Buffer-level split-on-insert is overlay-specific; mid-token semantics need char-cursor first |
| **§4** Replace selection by dictation | **There is no `actions.user.replace_selection` API in this setup.** The shape to mirror is: compose `actions.edit.delete()` + `actions.edit.insert(text)`, OR (if going through Cursorless) call the `"replace"` action — see `FEATURE_PARITY_REBUTTAL_CURSORLESS.md` §Tier 2 for the Cursorless path. | Wire to `buffer.replace_range`, seal as STRUCTURAL via `commit_start/commit_end` |
| **§4** Selection extension (left/right by word) | `actions.edit.extend_word_left/right()` confirmed in `trillium_talon/core/edit/edit_command.py:71-73,127-131` and `edit_win.py:82,85`. | Custom impl against `buffer.get_tokens()` + selection state |
| **§9** Audit `^... overlay$` global commands | Mode/tag specificity patterns from `trillium_talon` and prose-overlay's own talon files are well-precedented. | Pure audit task, no code to lift |

These are "free design language." Copy the verb names for voice-grammar consistency with the rest of the user's Talon vocabulary, but implement against `ProseBuffer`.

## Tier 3 — `trillium_talon` / stdlib cannot help; the work IS the work

These rows depend on prose-overlay's custom buffer / canvas model. `trillium_talon` and Talon stdlib have no substrate to lift because their edit verbs assume a host editor with a keystroke surface.

| Row | Why it can't be lifted |
|---|---|
| **§2** Mid-token cursor positioning / char insertion / char delete | `trillium_talon`'s edit surface operates on host editors via keystrokes. Prose-overlay's buffer is a Python data structure with no keystroke surface. `CHAR_CURSOR_PLAN` territory. |
| **§3c** Sub-word scope splitting | Not a `trillium_talon` feature. (Cursorless engine handles this — see `FEATURE_PARITY_REBUTTAL_CURSORLESS.md`.) |
| **§3c** Sub-word identity preserves joiner on replace | Same as above. |
| **§3f** JS resolver migration / Python resolver removal | Internal to prose-overlay. |
| **§4** Sub-word selection | Depends on sub-word resolver. |
| **§5** Shape hats / panel / mid-token render / sub-word highlight | All custom Skia paint on prose-overlay's canvas. |
| **§7** N-step undo / redo, selection restore on undo/redo | Internal buffer concern; `actions.edit.undo()` chains keystrokes against a host. |
| **§8** Paper trail Slice B | Internal observability. |

## Shape of the answer

The parity doc has **24 open rows** (`[ ]` + `[~]`, verified row count). `trillium_talon` / stdlib coverage split (per-tier counts are estimates — explicit row-walk pending):

- **Tier 1 (~3 rows):** number-hat, digit/punct letter-hat, clipboard. Estimate: ~30-80 LOC each, one bundled PR.
- **Tier 2 (~4 rows):** insertion-at-cursor, replace-selection, selection-extension, arbitration audit. Verb conventions given; impl against `ProseBuffer`.
- **Tier 3 (~17 rows):** every mid-token, sub-word, shape, panel, internal-undo entry. The substantial roadmap — `CHAR_CURSOR_PLAN`, `SUBWORD_PLAN`, `HOMOPHONE_SHAPES_PLAN`, `UNDO_REDO_PLAN` Phase 3.

**Pragmatic order:** clear Tier 1 first (one bundled PR); then Tier 2 (consistent verb-surface ramp); then commit to the Tier 3 plan-doc-driven substrates. Several Tier 2/3 rows depend on completing the §3f JS-resolver migration — work that gate before treating Tier 2 as parallel to Tier 1.
