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

## 5a. Refactor Status (audit 2026-07-01)

Executed the audit against actual git history + on-disk file state late 2026-07-01.
**TL;DR:** two of seven items shipped (R4 swap, R6 wrap). None of the four `.talon`
deletion / capture-folding items (R1, R2, R3, R7) has been executed — the plan
remains open. R5 (paste at destination) also not shipped. Rule count GREW from
123 → 126 because R4 and R6 added rules without any of the offsetting
deletions landing.

### Current rule counts (regenerated 2026-07-01 via §2 one-liner)

| File | Rules | Δ from baseline |
|---|---:|---:|
| `prose_overlay.talon` | 56 | 0 |
| `prose_overlay_cursorless.talon` | 30 | +2 (swap rule + wrap rule) |
| `prose_overlay_dictation.talon` | 10 | 0 |
| `prose_overlay_bring_move.talon` | 9 | +1 (still present; a rule was tweaked but the file was not deleted) |
| `prose_overlay_start.talon` | 5 | 0 |
| `prose_overlay_ender.talon` | 4 | 0 |
| `prose_overlay_history.talon` | 6 | 0 |
| `prose_overlay_pre_post.talon` | 3 | 0 |
| `prose_overlay_auto.talon` | 3 | 0 |
| **Total** | **126** | **+3** |

Delta from doc-drafting baseline (123): **+3 net**. Rules were added (R4, R6) but no rules were removed. All 9 `.talon` files still exist — file count unchanged from baseline.

### R-item status

| # | Item | Status | Evidence |
|---|------|--------|----------|
| R1 | Delete `prose_overlay_bring_move.talon` (§4a — verified duplicate) | ❌ NOT SHIPPED | File still on disk: `~/code/prose-overlay/prose_overlay_bring_move.talon` present, 9 rule bodies. Git log for the path shows only the initial commit `16aba79 feat: initial commit — prose overlay plugin` — no delete or refactor commit has ever touched it. Content unchanged: 8 bring/move rules identical to the duplicates in `prose_overlay_cursorless.talon:109-144`. |
| R2 | Delete 16 hand-splayed bring/move rules at `prose_overlay_cursorless.talon:82-122` | ❌ NOT SHIPPED | Hand-splayed block still present, actual lines shifted to `prose_overlay_cursorless.talon:109-144` (offset by the swap+wrap rules that landed between the composable bring/move rule at line 54 and the hand-splayed block). All 8 bring permutations at lines 110-123 and 8 move permutations at lines 131-144 are unchanged. |
| R3 | Introduce `<user.prose_overlay_hat>` capture that folds the color prefix (§4d) | ❌ NOT SHIPPED | No capture with that name exists. `grep -rn "prose_overlay_hat\b"` returns only doc mentions inside `docs/GRAMMAR_STRUCTURE_PARITY.md §4d, §5` and `docs/FEATURE_PARITY_REBUTTAL_COMMUNITY.md`. `prose_overlay.py:155` still only defines `prose_hat_color` (color-only capture). Every hat verb still ships as two rule bodies (with-color / without-color). |
| R4 | Add **swap** verb (C3) — `swap air with bat` | ✅ SHIPPED | Commit `dc3f985 feat(swap): wishlist #3 Swap action — swapTargets exchanges two target texts` (Wed Jul 1 10:57:12 2026). Grammar rule at `prose_overlay_cursorless.talon:62-63`: `{user.cursorless_swap_action} <user.cursorless_swap_targets>: user.prose_overlay_swap(cursorless_swap_targets)`. Matches cursorless.talon C3 shape exactly. Also logged as shipped in `FEATURE_PARITY.md §3e:223` and `BUNDLE_REST_SCOPE.md §Cluster A`. |
| R5 | Add **paste at destination** verb (C4) — `paste before air` | ❌ NOT SHIPPED | No paste rule in any `.talon` file — `grep -n "cursorless_paste_action" *.talon` returns empty. No `prose_overlay_paste` action defined in `.py` files. `FEATURE_PARITY.md §7:287` still marks "Cut/copy/paste through system clipboard" as `[ ]` (not started). Scoped in `BUNDLE_REST_SCOPE.md §#4:109` but never landed. |
| R6 | Add **wrap with paired delimiter** verb (C7) — `round wrap air` | ✅ SHIPPED | Commit `3a90365 feat(wrap): wishlist #5 wrap-with-paired-delimiter — bundle rebuild + shim + grammar + L2.14` (Wed Jul 1 11:24:50 2026). Grammar rule at `prose_overlay_cursorless.talon:77-78`: `<user.cursorless_wrapper_paired_delimiter> {user.cursorless_wrap_action} <user.cursorless_target>: user.prose_overlay_wrap_with_paired_delimiter(...)`. Matches cursorless.talon C7 shape exactly. Also logged as shipped in `FEATURE_PARITY.md §3e:227` and `BUNDLE_REST_SCOPE.md §Cluster B`. |
| R7 | Route `chuck head/tail/past` and `change head/tail` through composable `{simple_action} <cursorless_target>` (§4b) | ❌ NOT SHIPPED | Hand-splayed range verbs still present. `prose_overlay_cursorless.talon:84-102` still defines 8 rules (`chuck head`, `chuck tail`, `change head`, `change tail` × color-prefixed variants), each dispatching to bespoke action names (`prose_overlay_delete_head_hat`, `prose_overlay_change_tail_hat`, etc.) instead of routing through `{user.cursorless_simple_action} <user.cursorless_target>` with a RangeTarget shape. `prose_overlay.talon:19-20` also still hand-splays `chuck past`. ISC-8 (JS resolver holds ranges end-to-end) blocker referenced in the R7 row remains the gate; no evidence it fully closed. |

### Rule-count delta explanation

- R4 shipped: added 1 rule (swap) at `prose_overlay_cursorless.talon:62`.
- R6 shipped: added 1 rule (wrap paired delimiter) at `prose_overlay_cursorless.talon:77`.
- `prose_overlay_bring_move.talon` grew by 1 rule (8 → 9) via a minor edit — the delete-the-file decision (R1) was never made, so the file remains a live drift surface.
- Net: +3 rules, 0 deletions, so the shape moved *away* from cursorless.talon's tight 22-rule shape rather than toward it.

### Follow-up recommendation — highest-leverage next refactor

**Land R1 + R2 together in one commit.** This drops rule count from 126 → 110 (net -16) with zero behavior change, because:

- The composable `{user.cursorless_bring_move_action} <user.cursorless_target>` rule at `prose_overlay_cursorless.talon:54-55` already covers the entire bring/move surface via the cursorless target capture (which handles color-prefixed decorated marks natively).
- All 24 hand-splayed rules (8 in `prose_overlay_bring_move.talon` + 16 at `prose_overlay_cursorless.talon:109-144`) route to the same underlying `prose_overlay_bring_hat_to_hat` / `prose_overlay_move_hat_to_hat` actions the composable rule already dispatches through.
- Risk profile: `MANUAL_VERIFICATION.md` walkthrough of the bring/move rows would catch any missing spoken form; if a form regresses, the fix belongs inside the capture, not another `.talon` rule.

Concrete commit sequence to land it:

1. `git rm prose_overlay_bring_move.talon` (R1).
2. In the same commit, delete `prose_overlay_cursorless.talon:104-144` (the two `# ==== Bring ====` / `# ==== Move ====` blocks — 16 rule bodies plus the header comments) (R2).
3. Update this doc's §2 rule table and §5a Refactor Status row for R1/R2 to ✅ SHIPPED with the resulting commit SHA.
4. Run headless `MANUAL_VERIFICATION.md` bring/move rows in Talon and confirm all spoken forms still route correctly.

After R1+R2 land, R3 (`<user.prose_overlay_hat>` capture) becomes the next highest-leverage move: -~13 more rules for medium risk (needs a walkthrough of every chuck/pre/post/change/phones rule to confirm the capture reads letter+color correctly). R7 remains gated on the JS resolver work (ISC-8) and lands the biggest structural win once unblocked.

### Surprises

- **Rule count grew, not shrank.** The plan predicted R1+R2+R3 would land ~123 → ~86. Instead the file set grew to 126 because the "add a verb" R items (R4, R6) shipped before the "delete duplicates" R items (R1, R2, R3, R7). This is an inversion of the risk-vs-reduction ordering in §5, which suggested R1+R2 first because they're low-risk and reduce count with no behavior change.
- **`prose_overlay_bring_move.talon` is unchanged since initial commit** — the file has literally never been touched by a refactor. This confirms it was scoped but forgotten, not partially attempted.
- **R4 and R6 shipped within 30 minutes of each other on the same day** (2026-07-01 10:57 and 11:24 respectively), suggesting the "add cursorless verbs" work stream is active while the "delete duplicates" work stream has been dormant.

---

## 6. Scoring — how close are we to cursorless.talon's shape?

Refreshed 2026-07-01 after R4 (swap) and R6 (wrap) shipped — see §5a Refactor Status for the audit.

- **Core parity structural match:** 5 of 9 — 56%. Matching: **simple-action** (C1: `chuck air`, `take blue bat`), **bring/move** (C2: `bring air to bat`), **swap** (C3: `swap air with bat`, shipped 2026-07-01 via commit `dc3f985`), **reformat-at** (C5: `format snake at fox past bat`), and **wrap with paired delimiter** (C7: `round wrap air`, shipped 2026-07-01 via commit `3a90365`).
- **Core parity feature-shipped but not structurally matched:** 0. The four still-missing are **paste at destination** (C4), **call-on** (C6, OOS), **snippet insert** (C8, OOS), **snippet wrap** (C9, OOS). C4 (paste) is the only non-OOS gap left in the core parity table.
- **Admin parity:** 0 of 13 (all admin rules OOS for prose-overlay).
- **Rule-count ratio:** 126 rules vs 22 in cursorless.talon (baseline was 123 — the rules for R4 and R6 pushed the count up by 3 net; §5a). Excluding prose-overlay-specific ➕ surface (~60 rules — dictation intercept, homophone UI, viewport, history, symbol/letter routing, auto/anchor/debug/dump/reset/test/help/undo/redo/formatter passthroughs), the cursorless-shaped surface is ~66 rules — still ~3.0× cursorless.talon because R1/R2/R3/R7 have not shipped and hand-splayed permutations (§4d) + duplicated bring/move (§4a) remain live.
- **After R1+R2 (recommended next):** projected 110 rules total (-16), zero behavior change. §5a expands on the specific commit sequence.
- **After R1+R2+R3:** projected ~97 rules total, ~53 cursorless-shaped — parity ratio approaches 2.4:1 on the shared surface.

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

### 7a-note. Shape allocator via cursorless bundle — opt-in (added 2026-07-01)

Slice 3 of `docs/BUNDLE_SHAPE_SCOPE.md` landed a `mod.setting("prose_overlay_use_cursorless_shape_allocator", default=False)` that routes shape-flagged letter+color allocation through the cursorless bundle instead of the classic `compute_hat_assignments` path. The Python group-allocator in `shim/shapes.py` remains authoritative for the ISC-14c per-group-same-shape invariant (the option-b projection wrapper per `docs/BUNDLE_SHAPE_DECISIONS.md` OQ3). Default OFF while the projection layer bakes; grammar surface is unaffected — the `phone <shape>` and `<color> <shape>` rules resolve via `instance.shape_assignments` and `instance.hat_to_token` respectively, both of which keep their pre-Slice-3 semantics regardless of the setting. This section will be revisited if the setting flips default-on and the classic path is retired.

## 8. How this doc was built

- Read `~/.talon/user/cursorless-talon/src/cursorless.talon` end-to-end (60 lines, 22 rule bodies).
- Read all 9 `prose_overlay*.talon` files at repo root, counted rule bodies, tagged each with structural-status.
- Cross-checked against existing docs (`FEATURE_PARITY.md`, `FEATURE_PARITY_REBUTTAL_CURSORLESS.md`, `POTENTIALLY_MISSED.md`, `REBUTTAL_ASSERTIONS.md`) — confirmed none of them tracks grammar-rule shape at this level.
- Refactor path in §5 is ordered by risk × reduction ratio, gated on the JS resolver work already in the ISA (ISC-8, ISC-9).
