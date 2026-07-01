# Grammar Structure Parity — how our `.talon` rules compare to `cursorless.talon`'s shape

> Companion to `FEATURE_PARITY.md`. `FEATURE_PARITY.md` tracks **which verbs are
> shipped**. This doc tracks **how our grammar rule bodies are shaped** relative
> to the aspirational reference at `~/.talon/user/cursorless-talon/src/cursorless.talon`.
>
> Aspiration: a small number of high-order rules, each `LIST + CAPTURE` (or
> `CAPTURE + CAPTURE`), each firing exactly one `user.private_cursorless_*`
> dispatcher. All the vocabulary lives in Python-defined captures/lists — the
> `.talon` file itself does not enumerate verb variants.
>
> Reality: nine `prose_overlay*.talon` files with ~90 rule bodies, many of which
> enumerate color/target permutations inline instead of composing them inside a
> capture.
>
> Drafted 2026-07-01.

## Status legend

- `✅` — same rule *shape* as cursorless.talon (LIST/CAPTURE composition, one dispatcher)
- `🟡` — same intent, handcrafted permutations (color-splayed, hand-enumerated)
- `🔁` — duplicated across two of our `.talon` files
- `➕` — prose-overlay-specific rule with no cursorless.talon counterpart (kept intentionally)
- `❌` — cursorless.talon rule not represented in prose-overlay

---

## 1. The aspiration — cursorless.talon (22 rule bodies)

`~/.talon/user/cursorless-talon/src/cursorless.talon`. Loaded when `tag: user.cursorless` is set, `not tag: user.mouse_clock_showing`, `not tag: user.clock_ring_showing`. **60 lines. No inline verb enumeration.**

| # | Name | Rule shape | Dispatcher |
|---|---|---|---|
| C1 | **simple-action** (`chuck air`, `take blue bat`) | `<user.cursorless_action_or_ide_command> <user.cursorless_target>` | `private_cursorless_action_or_ide_command` |
| C2 | **bring/move** (`bring air to bat`, `move air past drum`) | `{user.cursorless_bring_move_action} <user.cursorless_bring_move_targets>` | `private_cursorless_bring_move` |
| C3 | **swap** (`swap air with bat`) | `{user.cursorless_swap_action} <user.cursorless_swap_targets>` | `private_cursorless_swap` |
| C4 | **paste at destination** (`paste before air`) | `{user.cursorless_paste_action} <user.cursorless_destination>` | `private_cursorless_paste` |
| C5 | **reformat-at** (`format snake at fox past bat`) | `{user.cursorless_reformat_action} <user.formatters> at <user.cursorless_target>` | `cursorless_reformat` |
| C6 | **call-on** (`call air on bat` — wrap bat as a function call named air) | `{user.cursorless_call_action} <user.cursorless_target> on <user.cursorless_target>` | `private_cursorless_call` |
| C7 | **wrap with paired delimiter** (`round wrap air` — surround air with parens) | `<user.cursorless_wrapper_paired_delimiter> {user.cursorless_wrap_action} <user.cursorless_target>` | `private_cursorless_wrap_with_paired_delimiter` |
| C8 | **insert snippet at destination** (`snippet funk before air`) | `{user.cursorless_insert_snippet_action} {user.snippet} <user.cursorless_destination>` | `private_cursorless_insert_community_snippet` |
| C9 | **wrap with snippet** (`snippet ifElse wrap air`) | `{user.snippet_wrapper} {user.cursorless_wrap_action} <user.cursorless_target>` | `private_cursorless_wrap_with_community_snippet` |
| C10 | **show scope visualizer** | `{user.cursorless_show_scope_visualizer} <user.cursorless_scope_type> [{user.cursorless_visualization_type}]` | `private_cursorless_show_scope_visualizer` |
| C11 | **hide scope visualizer** | `{user.cursorless_hide_scope_visualizer}` | `private_cursorless_hide_scope_visualizer` |
| C12 | **open cursorless settings** | `{user.cursorless_homophone} settings` | `private_cursorless_show_settings_in_ide` |
| C13 | **open cursorless sidebar** | `bar {user.cursorless_homophone}` | `private_cursorless_show_sidebar` |
| C14 | **show command stats** | `{user.cursorless_homophone} stats` | `private_cursorless_show_command_statistics` |
| C15 | **start tutorial** | `{user.cursorless_homophone} tutorial` | `private_cursorless_start_tutorial` |
| C16 | **tutorial next page** | `tutorial next` | `private_cursorless_tutorial_next` |
| C17 | **tutorial previous page** | `tutorial (previous \| last)` | `private_cursorless_tutorial_previous` |
| C18 | **tutorial restart** | `tutorial restart` | `private_cursorless_tutorial_restart` |
| C19 | **tutorial resume** | `tutorial resume` | `private_cursorless_tutorial_resume` |
| C20 | **tutorial list/close** | `tutorial (list \| close)` | `private_cursorless_tutorial_list` |
| C21 | **jump to tutorial N** | `tutorial <number_small>` | `private_cursorless_tutorial_start_by_number` |
| C22 | **migrate snippets** | `{user.cursorless_homophone} migrate snippets` | `private_cursorless_migrate_snippets` |

**Core parity surface = simple-action, bring/move, swap, paste, reformat-at, call-on, wrap-paired, snippet-insert, snippet-wrap** (rows 1–9). Rows 10–22 are admin (scope visualizer + tutorial + settings) with no prose analogue. **Wherever this doc uses `C#` shorthand, this table is the key.**

---

## 2. Our rule inventory — per file

Count = number of rule *bodies*. Regenerate with:

```bash
cd ~/code/prose-overlay && for f in prose_overlay*.talon; do
  multi=$(grep -cE '^[^ \t#-].*:$' "$f")
  inline=$(grep -cE '^[^ \t#-][^:]*:[[:space:]]+user\.' "$f")
  echo "$((multi + inline))  $f"
done
```

Snapshot 2026-07-01:

| File | Rules | Context header |
|---|---:|---|
| `prose_overlay.talon` | 56 | `mode: dictation`, `mode: command`, `tag: user.prose_overlay_active` |
| `prose_overlay_cursorless.talon` | 28 | `mode: dictation`, `mode: command`, `tag: user.prose_overlay_active`, not `mouse_clock`, not `clock_ring` |
| `prose_overlay_dictation.talon` | 10 | `mode: dictation`, `tag: user.prose_overlay_active` |
| `prose_overlay_bring_move.talon` | 8 | `mode: dictation`, `mode: command`, `tag: user.prose_overlay_active` |
| `prose_overlay_start.talon` | 5 | `mode: command`, `mode: dictation` (global) |
| `prose_overlay_ender.talon` | 4 | `mode: dictation`, `tag: user.prose_overlay_active` |
| `prose_overlay_history.talon` | 6 | `mode: command`, `mode: dictation`, `tag: user.prose_history_active` |
| `prose_overlay_pre_post.talon` | 3 | same as cursorless.talon minus mouse-clock exclusions |
| `prose_overlay_auto.talon` | 3 | `mode: dictation`, `tag: user.prose_overlay_auto` |
| **Total** | **~123** | |

Reference: cursorless.talon = 22 rules / 60 lines / 1 file. We are **~5.6× the rule count** and **9× the file count** — much of which is inline permutation enumeration (§4d) and prose-overlay-specific surface (dictation intercept, homophone UI, viewport, history, auto-dictation) that cursorless has no counterpart for.

---

## 3. Rule-shape mapping — cursorless.talon → prose-overlay

For each cursorless.talon rule (C1..C22), how do we express it? Status per §Status legend above.

| C# | Cursorless shape | Our shape (file:line) | Status | Notes |
|---|---|---|---|---|
| C1 | `<action> <target>` | `prose_overlay_cursorless.talon:47` — `{user.cursorless_simple_action} <user.cursorless_target>` | ✅ | LIST+CAPTURE. Uses `simple_action` LIST instead of the `action_or_ide_command` capture, but structural intent matches: one rule covers all `verb <target>` shapes. Dispatcher = `prose_overlay_run_action`. |
| C2 | `{bring_move_action} <bring_move_targets>` | `prose_overlay_cursorless.talon:51` — `{user.cursorless_bring_move_action} <user.cursorless_target>` | ✅ | Present as a single composable rule at line 51. **Also duplicated as 8 hand-splayed permutations** at `prose_overlay_cursorless.talon:88-122` AND `prose_overlay_bring_move.talon:8-24`. See §4 for the cleanup path. |
| C3 | `{swap_action} <swap_targets>` | — | ❌ | Not shipped. `POTENTIALLY_MISSED.md §C` lists "Swap targets" as a planned row. Cursorless already exposes `cursorless_swap_action` + `cursorless_swap_targets` — same LIST+CAPTURE lift shape would work. |
| C4 | `{paste_action} <destination>` | — | ❌ | Not shipped. Adjacent to `FEATURE_PARITY.md §7` "Cut/copy/paste through system clipboard" (Tier 1 in the community rebuttal). |
| C5 | `{reformat_action} <formatters> at <target>` | `prose_overlay_cursorless.talon:55` — `{user.cursorless_reformat_action} <user.formatters> at <user.cursorless_target>` | ✅ | Structural match 1:1. Dispatcher = `prose_overlay_apply_formatter`. Ships as ISC-7. |
| C6 | `{call_action} <target> on <target>` | — | ❌ OOS | Decided OOS 2026-07-01. `call` wraps a target in a function-call at another target — a code-editor refactor primitive with no prose analogue. Logged as `[—]` in `FEATURE_PARITY.md §10`. |
| C7 | `<wrapper_paired_delimiter> {wrap_action} <target>` | — | ❌ | Not shipped. `POTENTIALLY_MISSED.md §C` lists "Wrap selection with delimiter" — cursorless-side already provides the LIST + wrapper capture; only the dispatcher needs to route to `buffer.wrap_range`. |
| C8 | `{snippet_action} {snippet} <destination>` | — | ❌ OOS | Decided OOS 2026-07-01. Cursorless snippets are language-scoped templates with variable interpolation (`ifElse`, `funk`, etc.) — no analogue for a prose buffer whose confirm-to-host lands raw text. Logged as `[—]` in `FEATURE_PARITY.md §10`. |
| C9 | `{snippet_wrapper} {wrap_action} <target>` | — | ❌ OOS | Decided OOS 2026-07-01 — same bucket as C8. If a prose-side wrap surface is later wanted (quotes/parens around a selection), it belongs under C7 (paired-delimiter wrap), not the snippet subsystem. |
| C10 | `{show_scope_visualizer} <scope_type> [...]` | — | ❌ | Scope visualizer is a VS Code extension surface; no PO equivalent. Cursorless owns this outside PO's active context so no conflict. |
| C11 | `{hide_scope_visualizer}` | — | ❌ | Same as C10. |
| C12 | `{homophone} settings` | — | ❌ | IDE settings — OOS for PO. |
| C13 | `bar {homophone}` | — | ❌ | Sidebar — OOS for PO. |
| C14 | `{homophone} stats` | — | ❌ | Command stats — OOS for PO. |
| C15..C21 | Tutorial admin (7 rules) | — | ❌ | Tutorial surface — OOS for PO. |
| C22 | `{homophone} migrate snippets` | — | ❌ | Snippet migration — OOS for PO. |

**Score: 3/9 core parity rules (C1, C2, C5) structurally match. 0/9 admin rules apply.**

---

## 4. Where we deviate from the aspiration — structural anti-patterns

### 4a. Duplicated bring/move blocks

- `prose_overlay_cursorless.talon:88-101` — 4 rules for `bring <letter> to <letter>` and the 3 color-prefix permutations.
- `prose_overlay_cursorless.talon:109-122` — 4 rules for `move <letter> to <letter>` and permutations.
- `prose_overlay_bring_move.talon:8-15` — **identical 4 bring rules**.
- `prose_overlay_bring_move.talon:17-24` — **identical 4 move rules**.

Two files, 16 rules total, but only 8 unique. `prose_overlay_bring_move.talon` predates the cursorless-native `{bring_move_action} <cursorless_target>` rule at `prose_overlay_cursorless.talon:51`. Kill candidates:

1. **Delete `prose_overlay_bring_move.talon` entirely** — the composable rule at `prose_overlay_cursorless.talon:51` already covers `bring <target>` and `move <target>` through the cursorless `<cursorless_target>` capture, which handles color-prefixed decorated marks natively.
2. **Also delete the hand-splayed 8-rule block at `prose_overlay_cursorless.talon:82-122`** for the same reason.
3. Verify with `MANUAL_VERIFICATION.md` that removing the hand-splayed rules doesn't regress a spoken form the composable rule can't reach. If a form regresses, the fix belongs in the capture, not another `.talon` rule.

### 4b. Handcrafted range verbs that could be `chuck <target>` where target is a range

- `chuck head <letter>` (2 rules), `chuck tail <letter>` (2 rules) — `prose_overlay_cursorless.talon:62-68`
- `change head <letter>` (2 rules), `change tail <letter>` (2 rules) — `prose_overlay_cursorless.talon:74-80`

These are `chuck` + `head/tail <letter>` where `head/tail` is a range shape (start→hat, hat→end). Cursorless expresses this through `<cursorless_target>` — e.g. `chuck past drum` is a RangeTarget with `end: {mark: "drum"}`. Our own `chuck past <letter>` in `prose_overlay.talon` uses a different action path (`prose_overlay_delete_past_hat`) rather than the composable dispatcher.

If we routed `chuck head/tail/past` through the composable `{simple_action} <cursorless_target>` rule with the correct target shape, all 8 rules disappear and the range-family surface unifies. This is a bigger refactor and depends on the JS resolver handling the range shape end-to-end (ISC-8 partial-green — see FEATURE_PARITY.md §3f).

### 4c. Deliberate structural mismatch — compound `<verb> <letter> <raw_prose>` rules

`prose_overlay_dictation.talon:30-47` — 6 rules for `change <letter> <raw_prose>`, `pre <letter> <raw_prose>`, `post <letter> <raw_prose>` and their color-prefix variants.

**These do NOT match cursorless.talon's shape, and the mismatch is load-bearing — do not refactor them.**

**The concrete failure mode they prevent.** If `change <letter>` were bound as a standalone rule (the cursorless-shape approach — one action verb, one target capture), Talon would commit to that match at the end of the letter capture, dispatch `prose_overlay_change_hat("t")` immediately, and then continue parsing the same utterance from where the rule ended. The remaining spoken words (`word force`, in the example utterance `change trap word force`) fall through to whatever context is active NEXT — in practice:
- `word` gets consumed by a cursorless scope-verb rule (from `cursorless.talon` or `prose_overlay_cursorless.talon`) and misfires against whichever buffer is focused,
- `force` misses every rule and gets typed literally into the host window via Talon's key-fallback path.

The user experience is: they say "change trap word force" intending to enter "change" mode on hat `t` and type the replacement text "word force" into the buffer, but the buffer gets an empty change-mode entry and the host window (VS Code, terminal, chat client, wherever the overlay is anchored) receives a stray `force` keypress plus a cursorless misfire on `word`.

**How the compound rule fixes it.** By binding the whole utterance under one rule that also captures `<user.raw_prose>` at the tail, Talon consumes `change trap word force` as a single dispatch, runs `change_hat("t")`, then `add_text("word force")` in the same action-body block. Nothing leaks past the rule boundary because there IS no rule boundary mid-utterance.

**Same rationale applies to the sibling rules.** `pre <letter> <raw_prose>` and `post <letter> <raw_prose>` (with and without color prefix) all bind cursor-placement + dictation as one utterance. Any hat verb that is naturally followed by dictation needs the compound shape, or the tail leaks.

**Refactor verdict: KEEP.** Restoring the cursorless shape here would regress the exact bug the compound rules were built to fix. The `.talon` file already carries a comment block above these rules explaining the reasoning (`prose_overlay_dictation.talon:27-29`) — that comment is load-bearing documentation, not commentary.

### 4d. Hand-splayed color-prefix permutations across the whole file set

Every hat verb ships as **two rule bodies** — one for gray (no color prefix), one for `<user.prose_hat_color> <letter>`. Counted across `prose_overlay.talon` + `prose_overlay_cursorless.talon` + `prose_overlay_bring_move.talon` + `prose_overlay_dictation.talon`, this pattern generates roughly 26 rules that would collapse to 13 if the color-optional composition lived inside a `<user.prose_overlay_hat>` capture.

**Refactor**: define one Python capture like

```python
@mod.capture(rule="[<user.prose_hat_color>] <user.letter>")
def prose_overlay_hat(m) -> tuple[str, str]:
    color = getattr(m, "prose_hat_color", "gray")
    return (m.letter, color)
```

then every hat rule collapses to a single body — e.g. `chuck <user.prose_overlay_hat>`, `pre <user.prose_overlay_hat>`, `change <user.prose_overlay_hat>`. This is the cursorless.talon idiom exactly: **push permutation into the capture, keep the `.talon` rule flat**.

### 4e. Non-cursorless surface (kept intentionally)

These are the rules with `➕` status — prose-overlay-specific verbs that have no cursorless counterpart and shouldn't be forced into the cursorless shape:

| Rule family | File | Why it's not in cursorless |
|---|---|---|
| Dictation intercept (`<user.raw_prose>`, `<user.number_string>`) | `prose_overlay_dictation.talon`, `prose_overlay_auto.talon` | Cursorless doesn't intercept dictation — it edits code, not free prose |
| Formatter passthroughs (`{prose_formatter} <prose>`, `<format_code>+`) | `prose_overlay.talon:179-189` | Prose-side formatters route to `add_text`; cursorless routes to VS Code insert |
| Homophone toggles + panel + shape/color swap | `prose_overlay.talon` | Prose-overlay-only visual system (`docs/PHONES_SPEC.md`) |
| Viewport align + recenter (`overlay show top/bottom/center`, `overlay center`) | `prose_overlay.talon:200-203` | Prose-overlay-only canvas |
| History panel (`overlay history`, `history back/next/pick`) | `prose_overlay.talon`, `prose_overlay_history.talon` | Prose-overlay-only |
| Anchor / auto / debug / dump / reset / test toggles | `prose_overlay.talon` | Observability + config for the overlay itself |
| Symbol / letters routing (`{user.symbol_key}`, `<user.letters>`) | `prose_overlay.talon:173, 197` | Character-level input that host apps get via key events; overlay must synthesize |
| Confirm / dismiss / paste-to-host (`bravely` via ender, `confirm`, `overlay dismiss`) | `prose_overlay.talon`, `prose_overlay_ender.talon` | Prose-overlay-only lifecycle |

These are **not** structural failures — they are the reason prose-overlay exists. Do not fold them into the cursorless surface.

---

## 5. Refactor priority order

Ordered by ratio of `.talon` line reduction to refactor risk. Each item is one landable slice.

| # | Refactor | Rules removed | Risk | Depends on |
|---|---|---|---|---|
| R1 | Delete `prose_overlay_bring_move.talon` (§4a — verified duplicate) | 8 | low | Regression walkthrough of bring/move in `MANUAL_VERIFICATION.md` |
| R2 | Delete the 16 hand-splayed bring/move rules in `prose_overlay_cursorless.talon:82-122` | 8 more | low | Same MANUAL_VERIFICATION rows as R1 |
| R3 | Introduce `<user.prose_overlay_hat>` capture that folds the color prefix (§4d) | ~13 | medium | New capture in `prose_overlay.py`; walkthrough of every chuck/pre/post/change/phones rule |
| R4 | Add **swap** verb (C3) — `swap air with bat` | −1 net (+1 rule, +1 shipped verb) | low | Add `prose_overlay_swap` dispatcher; cursorless swap captures already exist |
| R5 | Add **paste at destination** verb (C4) — `paste before air` | −1 net | low | Same as R4 + clipboard verbs (see COMMUNITY rebuttal §Tier 1) |
| R6 | Add **wrap with paired delimiter** verb (C7) — `round wrap air` surrounds air with parens | −1 net | medium | Buffer-level `wrap_range` primitive |
| R7 | Route `chuck head/tail/past` and `change head/tail` through composable `{simple_action} <cursorless_target>` (§4b) | ~8 | high | JS resolver holds ranges end-to-end (ISC-8 fully green) |

R1+R2 alone would drop rule count from ~105 → ~89 with zero behavior change. R3 pushes it toward ~76. R7 lands the biggest structural win but is gated on the JS resolver work already in flight.

---

## 6. Scoring — how close are we to cursorless.talon's shape?

- **Core parity structural match:** 3 of 9 — 33%. The three matching are **simple-action** (C1: `chuck air`, `take blue bat`), **bring/move** (C2: `bring air to bat`), and **reformat-at** (C5: `format snake at fox past bat`).
- **Core parity feature-shipped but not structurally matched:** 0. The six missing are **swap** (C3), **paste at destination** (C4), **call-on** (C6, OOS), **wrap with paired delimiter** (C7), **snippet insert** (C8, OOS), **snippet wrap** (C9, OOS).
- **Admin parity:** 0 of 13 (all admin rules OOS for prose-overlay).
- **Rule-count ratio:** ~123 rules vs 22 in cursorless.talon. Excluding prose-overlay-specific ➕ surface (~60 rules — dictation intercept, homophone UI, viewport, history, symbol/letter routing, auto/anchor/debug/dump/reset/test/help/undo/redo/formatter passthroughs), the cursorless-shaped surface is ~63 rules — still ~2.9× cursorless.talon because of hand-splayed permutations (§4d) and duplicated bring/move (§4a).
- **After R1+R2+R3:** projected ~86 rules total, ~26 cursorless-shaped — parity ratio approaches 1.2:1 on the shared surface.

---

## 7. Maintenance rule

When a `.talon` rule is added, moved, or deleted:

1. If it targets a cursorless-shaped verb (C1..C9), update the row in §3 above.
2. If it's a permutation of an existing rule, ask if it belongs inside a capture instead (§4d pattern).
3. Regenerate the counts in §2 with `grep -cE '^[^ #-].*:' *.talon` (rough — hand-counts are the source of truth).
4. Commit this doc in the same PR as the `.talon` change.

## 7a. Sub-word `word` scope — bundle finding (added 2026-07-01)

Investigation at `docs/SUBWORD_INVESTIGATION.md` verified that `js/prose_resolve_targets.js:14342-14380` ships `WordScopeHandler` + `WordTokenizer.splitIdentifier` + `CAMEL_REGEX`. Sub-word `word` scope on `snake_case` / `camelCase` / `kebab-case` identifiers is **not a bundle gap** — it's shipped on the JS resolver path, which has been the default since 2026-06-30.

The remaining blocker is asymmetric: the Python resolver fallback at `cursorless/resolve.py:108-115` returns `(base_idx, base_idx)` (token-level only) with no `splitIdentifier` call. ISC-9 (Python resolver retirement) makes this moot — until then, users on the JS path get sub-word for free; users forced to the Python path don't.

Impact on drift narrative: any earlier list here or in adjacent docs that lumped sub-word into "wantable but not shipped" needs to be reframed as "shipped via JS resolver; asymmetric on Python fallback; needs a headless row." `FEATURE_PARITY.md §3c` has been flipped from `[ ]` to `[~]` to reflect the corrected status.

## 8. How this doc was built

- Read `~/.talon/user/cursorless-talon/src/cursorless.talon` end-to-end (60 lines, 22 rule bodies).
- Read all 9 `prose_overlay*.talon` files at repo root, counted rule bodies, tagged each with structural-status.
- Cross-checked against existing docs (`FEATURE_PARITY.md`, `FEATURE_PARITY_REBUTTAL_CURSORLESS.md`, `POTENTIALLY_MISSED.md`, `REBUTTAL_ASSERTIONS.md`) — confirmed none of them tracks grammar-rule shape at this level.
- Refactor path in §5 is ordered by risk × reduction ratio, gated on the JS resolver work already in the ISA (ISC-8, ISC-9).
