# `format {formatter} at {target}` — Exploration Plan

> Source verbs: Cursorless `applyFormatter` (already shipped against PO buffer at ISC-7 via `prose_overlay_apply_formatter`). Coordinates with the already-bound `{user.cursorless_reformat_action} <user.formatters> at <user.cursorless_target>` rule at `prose_overlay_cursorless.talon:55-56`, the undo bracket API (ISC-23, shipped — `commit_start`/`commit_end` at `prose_overlay_state.py:303-338`), and the `change <user.letter>` precedent at `prose_overlay.talon:98-100` for "one utterance → one STRUCTURAL undo step against a hat-resolved token."
> Drafted 2026-06-30.
>
> **This is an exploration plan, not a ship plan.** Each slice is a reversible experiment behind its own setting with explicit kill criteria. We are layering **prose-overlay-native** target captures (current selection, hat-anchored token, count-of-tokens range) onto the formatter pipeline that already runs the community `user.reformat_text` machinery — so we get Cursorless's formatter inventory (snake, camel, kebab, dot, …) without going through `<user.cursorless_target>` for cases where the user's mental model is "the thing I just selected" or "two tokens starting at trap."

## 1. TL;DR

- ISC-7 already wires `format snake at <user.cursorless_target>` end-to-end (rule at `prose_overlay_cursorless.talon:55-56` → `prose_overlay_apply_formatter` at `prose_overlay_actions_cursorless.py:120-164`, undo-bracketed via `commit_start("apply_formatter", EditKind.STRUCTURAL)`). The substrate the new slices layer on **is already shipped**. We are not adding the formatter pipeline — we are adding **PO-native target captures** that bypass `<user.cursorless_target>` for two cases the Cursorless grammar handles awkwardly inside an overlay: (a) "the current selection" (the buffer's `_selection` field — `prose_overlay_state.py:167,344-354`) and (b) "{count} tokens starting at hat" (no Cursorless analogue in the PO grammar today).
- **Worked examples.**
  - Slice 1 (implicit selection): buffer has `[these tokens]` selected (selection set via Cursorless `setSelection`, which already calls `instance.buffer.set_selection` at `prose_overlay_actions_cursorless.py:80,114`) → user says `format snake` → buffer becomes `these_tokens`, selection retained on the rewritten span.
  - Slice 2 (single-hat target): buffer has `[t]hese tokens here` with hat `trap` on `these` → `format snake at trap` → buffer becomes `these tokens here` with `these` unchanged (single-token snake of `these` is a no-op). To see a real rewrite: `[t]heseTokens here` → `format snake at trap` → `these_tokens here`.
  - Slice 3 (count-token range): same buffer with hat `trap` on `these` → `format snake at two tokens trap` → buffer becomes `these_tokens here` (the two tokens starting at `trap` got snake-joined).
  - Slice 4 (optional, prose-scope): `format snake at sentence` → snake-cases every token in the cursor's sentence. Routes through the existing `_scope_regex` sentence regex from `prose_overlay_cursorless_resolve.py`.
  - Slice 5 (optional, JS-resolver passthrough): with `user.prose_overlay_use_js_resolver=True`, route through `processTargets` in the QuickJS bundle so PO-native targets become Cursorless `PrimitiveTarget` shapes — closes the divergence and makes ISC-9 (Python resolver retirement) cheaper.
- The `at` connector is **load-bearing in Slices 2-3** because the formatter list and the NATO letter list have overlapping spoken forms (`all cap` from `code_formatter.talon-list:3`; `air bat cap drum each fine gust harp sit jury crunch look made near odd pit quench risk sun trap urge vest whale plex yank zip` from `letter.talon-list`). The collision case is real but narrow — see §4.3, which decides **keep `at`** because dropping it makes `format all cap` ambiguous between "format-all-cap" (single formatter) and "format all (formatter), cap (letter)" (which currently parses but binds nothing). Slice 1 has no target capture so the `at` is absent there by definition — `format snake` is just `format snake`.
- Each slice ships behind its own setting, one commit, one `git revert` to undo. Slice 1 (selection target) lands first because its capture is trivial (no grammar arg) and because it directly exercises the selection retention story that Slices 2-3 depend on.
- Foundational dodges in §4: keep the formatter inventory imported from `code_formatter.talon-list` (not copied), keep the `{count} tokens {hat}` shape as a reusable `user.prose_overlay_token_range` capture (so future verbs can take the same range), keep the no-selection branch deterministic (no-op + `app.notify`, not "implicitly target the cursor token"), keep the undo bracket exactly as the existing `prose_overlay_apply_formatter` uses it (one `STRUCTURAL` step per utterance — already verified pattern at `prose_overlay_actions_cursorless.py:146-160`), keep the new grammar additive — never modify the existing ISC-7 rule.

## 2. Decision-tree shape

```
1 — `format {formatter}` (implicit current-selection target)
    (no `at`, no hat; requires non-None buffer.get_selection(); no-op otherwise)
  └─ Selection-target loop feels natural in real dictation → 2
  └─ Selection target ambiguous / no-selection no-op confusing → revert; ISC-7
                                                                  already covers
                                                                  the explicit
                                                                  `<user.cursorless_target>`
                                                                  case, so the
                                                                  user just keeps
                                                                  speaking `format
                                                                  snake at fox`.

2 — `format {formatter} at <user.letter>` (single-hat target)
    (rebuilds the `change <user.letter>` precedent for a different verb)
  └─ Single-hat reformat lands the right token ≥90% → 3
  └─ Hat resolution feels wrong (off-by-one, color collision) → revert;
                                                                 keep Slice 1
                                                                 alone, keep
                                                                 ISC-7.

3 — `format {formatter} at {count} tokens <user.letter>` (count-of-tokens range)
    (new `user.prose_overlay_token_range` capture, reusable for future verbs)
  └─ Range capture reads cleanly, no count/hat ambiguity → 4 optional
  └─ "two tokens trap" misparses, or off-by-one is confusing → revert the
                                                                range capture
                                                                but keep
                                                                Slices 1 & 2.

4 — `format {formatter} at <prose-scope>` (sentence / clause / line / paragraph)
    (routes through existing _REGEX_SCOPE_PATTERNS in cursorless_resolve.py)
  └─ Scope-anchored format is the missing tool → keep
  └─ Cursorless's existing `format snake at sentence trap` covers this case
                                                          already → revert.

5 (optional) — JS-resolver path
    (translate PO-native targets to PrimitiveTarget so processTargets does
     the resolution; only meaningful when user.prose_overlay_use_js_resolver=True)
  └─ Closes ISC-9 (Python resolver retirement) and removes a divergent code path → keep
  └─ Translation layer is more brittle than the dual-path duplication → defer
                                                                        until ISC-8
                                                                        clears.
```

Each slice lives behind its own setting (§3 per-slice spec). Reverting 4 does not touch 3. Reverting 3 does not touch 2. The shared substrate of 1-5 is **the already-shipped formatter pipeline** at `prose_overlay_apply_formatter` plus the undo bracket API. Nothing in the tree adds new mutation infrastructure; every slice is grammar + a thin dispatcher over `actions.user.reformat_text`.

## 3. Per-slice spec

### Slice 1 — `format {formatter}` (implicit current-selection target)

**Goal.** Learn whether `format snake` (no target, just the formatter) is the natural form when the user has already established a selection — i.e., does the loop "select tokens, then transform them" feel cleaner than "transform tokens identified by hat" for the cases where the selection already exists? The pattern matches how host-app editors work (`Cmd+L` then `Ctrl+K Ctrl+X` in VS Code) and matches the `setSelection` action that Cursorless's `take` already drives through `prose_overlay_actions_cursorless.py:80,114`.

**Files touched** (rough LOC):
- **new** `prose_overlay_actions_format_at.py` (~70 LOC) — single module owns the three actions (Slices 1, 2, 3 each add one). Slice 1 ships `prose_overlay_format_selection(formatters: str)`:
  ```python
  def prose_overlay_format_selection(formatters: str):
      """Apply community formatter pipeline to the current selection.

      No-op + notify if buffer.get_selection() is None. One STRUCTURAL undo
      step. Selection is retained on the rewritten span.
      """
      if not instance.canvas.is_showing:
          return
      sel = instance.buffer.get_selection()
      if sel is None:
          app.notify("prose overlay: no selection — try 'format snake at <hat>'")
          return
      first_idx, last_idx = sel
      _execute_format(first_idx, last_idx, formatters, label="format_selection")
  ```
  Plus a shared `_execute_format(first, last, formatters, label)` helper that mirrors `prose_overlay_apply_formatter`'s inner `_execute` (the `commit_start`/`replace span`/`commit_end` triad) — this becomes the substrate for Slices 2 & 3 too. Selection retention: after the rewrite, recompute the new last_idx (`first + len(new_tokens) - 1`) and call `instance.buffer.set_selection(first, new_last)`.
- `prose_overlay_cursorless.talon` (~+4 LOC) — append below the existing reformat rule at line 56:
  ```talon
  # Format current selection (no target). Requires non-None buffer selection.
  {user.cursorless_reformat_action} <user.formatters>:
      user.prose_overlay_format_selection(formatters)
  ```
  **Grammar specificity.** This rule is `LIST + CAPTURE` (two captures, no literal trailing). The existing ISC-7 rule is `LIST + CAPTURE + LITERAL("at") + CAPTURE` — more specific (more literals + captures). The new rule fires **only when** the utterance has no `at <target>` tail, so there's no shadowing. Verified by inspection: Talon's grammar-specificity rule prefers longer-literal rules first, and the LIST → `format` token is shared, so the partition is purely on whether `at <target>` follows.
- `prose_overlay.py` (~+8 LOC) — `mod.setting("prose_overlay_format_at_selection", type=bool, default=False, desc="...")`. The action body short-circuits with `app.notify` if the setting is off, so the voice surface doesn't change on toggle (mirrors the `prose_overlay_homophone_swap` pattern proposed in `HOMOPHONE_SHAPES_PLAN.md` Slice 4).

Total: ~80 LOC, one new module, four talon lines, one setting.

**Feature flag.** `user.prose_overlay_format_at_selection` (bool, default `False`). Off by default so the experiment is opt-in even after merge. Toggle live via `overlay format selection on/off` (added to `prose_overlay.talon` near the `overlay hints homo on/off` block at lines 54-56).

**Voice surface (Slice 1 only).**
```talon
{user.cursorless_reformat_action} <user.formatters>:
    user.prose_overlay_format_selection(formatters)
overlay format selection on:  user.prose_overlay_format_set(1)
overlay format selection off: user.prose_overlay_format_set(0)
```

`{user.cursorless_reformat_action}` is the existing Talon list from `~/.talon/user/cursorless-talon/src/actions/reformat.py:12` containing just `"format"`. `<user.formatters>` is the community-defined capture that resolves to a comma-separated formatter-ID string (e.g. `"SNAKE_CASE"`, `"ALL_CAPS,SNAKE_CASE"` for `constant`), already used by the shipped ISC-7 rule.

**Keep criterion.** After ~3 sessions, user reaches for `format snake` (no target) at least once per session unprompted after selecting tokens via `take` / Cursorless `setSelection`, and the rewrite lands the right transform ≥90% of the time. Selection retention behaves correctly — the cursor or selection sits on the rewritten span after commit, not on a stale pre-rewrite index.

**Kill criterion.** User reports the no-target form feels ambiguous ("did I forget the hat?"), OR the no-selection no-op is consistently confusing (the `app.notify` doesn't surface enough), OR the selection-retention logic breaks on multi-token → single-token transforms (snake of `the quick fox` → `the_quick_fox` is one token; what's the selection now?). Revert: ISC-7 already covers the explicit hat-target case, so the user falls back to `format snake at trap` and nothing is lost.

**Reversibility.** `git revert <slice-1-sha>` removes one new module, one setting, four talon lines. Zero schema change. Zero coupling to undo (the bracket API call is one line and identical to the existing `prose_overlay_apply_formatter`). The existing ISC-7 rule is untouched.

**Non-goals.**
- No new target capture (Slices 2 & 3's job).
- No no-selection-implicit-cursor-token behavior. If the buffer has no selection, the action is a no-op. The implicit-cursor-token alternative is a Slice 1.5 if no-op turns out to be too strict.
- No multi-formatter chaining beyond what `<user.formatters>` already supplies (the capture handles `constant` = `ALL_CAPS,SNAKE_CASE` natively).
- No deprecation of ISC-7. Both rules coexist; the user picks the form that fits the utterance.

---

### Slice 2 — `format {formatter} at <user.letter>` (single-hat target)

**Goal.** Learn whether the explicit single-hat form (`format snake at trap`) is preferred over the Cursorless-native `format snake at <user.cursorless_target>` already shipped at ISC-7 for the simple case "one token". The Cursorless target grammar handles this via `decoratedSymbol` mark resolution, which works but routes through `_resolve_target_to_token_range` (`prose_overlay_cursorless_resolve.py`) and the JS shim in some configurations. The direct-letter shortcut bypasses that pipeline for the simplest case — same pattern as `change <user.letter>` at `prose_overlay.talon:98-100` (no Cursorless target, direct letter capture, one-token mutation).

**Files touched** (rough LOC):
- `prose_overlay_actions_format_at.py` (~+40 LOC) — add `prose_overlay_format_hat(formatters: str, letter: str, color: str = "gray")`:
  ```python
  def prose_overlay_format_hat(formatters: str, letter: str, color: str = "gray"):
      """Apply formatter to the single token addressed by (letter, color)."""
      if not instance.canvas.is_showing:
          return
      idx = _hat_to_index(letter, color)
      if idx < 0:
          app.notify(f"prose overlay: no token for hat '{color} {letter}'")
          return
      _execute_format(idx, idx, formatters, label=f"format_hat:{color}_{letter}")
  ```
  Reuses `_hat_to_index` from `prose_overlay_actions_core.py:60-67` (already imported by Slice 1's module). Reuses `_execute_format` from Slice 1.
- `prose_overlay_cursorless.talon` (~+4 LOC) — append:
  ```talon
  {user.cursorless_reformat_action} <user.formatters> at <user.letter>:
      user.prose_overlay_format_hat(formatters, letter)
  {user.cursorless_reformat_action} <user.formatters> at <user.prose_hat_color> <user.letter>:
      user.prose_overlay_format_hat(formatters, letter, prose_hat_color)
  ```
- `prose_overlay.py` (~+0 LOC) — reuses Slice 1's `prose_overlay_format_at_selection` setting renamed in implementation to `prose_overlay_format_at_target` (covers Slices 1-3). Both rules read the same flag.

Total: ~45 LOC, no new module, four talon lines.

**Feature flag.** Reuses Slice 1's flag (`prose_overlay_format_at_target`). The Slice 2 grammar registers unconditionally; the dispatch shorts when the flag is off. Rationale: a user who turned on Slice 1 wants the whole `format … at … hat` family at once; gating each slice independently is friction without payoff. Slice 4 (scope target) gets a separate flag because scope vs hat is a different mental model.

**Voice surface (Slice 2 adds).**
```talon
{user.cursorless_reformat_action} <user.formatters> at <user.letter>:
    user.prose_overlay_format_hat(formatters, letter)
{user.cursorless_reformat_action} <user.formatters> at <user.prose_hat_color> <user.letter>:
    user.prose_overlay_format_hat(formatters, letter, prose_hat_color)
```

**Grammar specificity vs ISC-7.** ISC-7's rule uses `<user.cursorless_target>` which is a recursive capture covering many shapes including `<user.letter>` decorated-symbol marks. Slice 2's rule uses the bare `<user.letter>` capture. Both rules match `format snake at trap` in principle. Talon's grammar-specificity tie-break prefers the rule with the more-specific capture — `<user.letter>` resolves to a single regex over the NATO list and is **more specific than** `<user.cursorless_target>` (which is a top-level cursorless capture). Verified pattern: the same shape is what wins in ISC-23's `change <user.letter>` vs Cursorless's `change <user.cursorless_target>` — `change <user.letter>` consistently routes through `prose_overlay_change_hat`, not through Cursorless's pipeline, when PO is active.

If the rules genuinely tie in the live grammar (Talon's specificity rule changes between versions), the user-visible symptom is "format snake at trap" routing through ISC-7's slower path. The fix is to make the Slice 2 rule even more specific (e.g. `format <user.formatters> at <user.letter>` with `format` as a literal not via the `{user.cursorless_reformat_action}` LIST). Reserved as an OQ but not blocking — verified by inspection of the existing `change <user.letter>` precedent that has held across Talon updates.

**Keep criterion.** Across ~3 sessions, user prefers `format snake at trap` over `format snake at trap there` (the Cursorless decorated-symbol form has `air` as the implicit color; mark resolution goes through Cursorless's pipeline). Single-hat reformat lands the right token ≥90% (matches ISC-7's accuracy on the same utterance) and feels faster — observable as latency in the debug stream because the direct path skips JS resolution when the JS resolver setting is off.

**Kill criterion.** Hat resolution misfires (off-by-one due to color collision, e.g. `trap` resolves to gray-t when the user expected blue-t), OR the grammar specificity rule loses to ISC-7 and the user can't tell which dispatcher fired. Debug-log signal: every dispatcher emits a `recompute_hats` snapshot with the action label; if `format_hat` doesn't appear when expected, Slice 2's rule lost the binding. Revert and keep ISC-7 only.

**Reversibility.** `git revert <slice-2-sha>` removes ~40 LOC in the action module, four talon lines. Slice 1 unaffected. ISC-7 unaffected (the talon rule is purely additive; the grammar table loses two rules but the prior ones still bind).

**Non-goals.**
- No multi-hat target (`format snake at trap urge` to format two tokens). Slice 3's job via `{count} tokens <hat>`.
- No range form (`format snake at trap past sit`). The Cursorless `<user.cursorless_target>` already covers this via RangeTarget; users who want range get ISC-7.
- No color-defaulted variant beyond the two rules above. The two-rule pattern matches `change <user.letter>` exactly.

---

### Slice 3 — `format {formatter} at {count} tokens <user.letter>` (count-of-tokens range)

**Goal.** Learn whether the count-of-tokens form (`format snake at two tokens trap` = "two tokens starting at the hat-marked token") is intuitive enough to replace the Cursorless `<user.cursorless_target>` RangeTarget form (`format snake at trap past urge`) for the common case "I want N tokens, starting here." The Cursorless range form requires the user to know the **end** hat; the count form only requires the **start** hat plus a number — strictly less to remember, and the count-2 case ("two tokens trap") is the dominant verb in mouth-of-the-user testimony.

**Files touched** (rough LOC):
- **new capture** in `prose_overlay.py` (~+15 LOC):
  ```python
  @mod.capture(rule="<number_small> tokens <user.letter>")
  def prose_overlay_token_range(m) -> tuple[int, int]:
      """Resolve a count-of-tokens range starting at a hat-marked token.

      Returns (first_idx, last_idx) inclusive, or (-1, -1) if the hat is
      unbound or the count overshoots the buffer.
      """
      count = int(m.number_small)
      letter = str(m.letter)
      from .prose_overlay_actions_core import _hat_to_index
      from .prose_overlay_instance import instance
      first = _hat_to_index(letter)
      if first < 0:
          return (-1, -1)
      total = len(instance.buffer.get_tokens())
      last = min(first + count - 1, total - 1)
      return (first, last)
  ```
  **Reusable.** The capture is named `user.prose_overlay_token_range` — future verbs (e.g. `take {count} tokens trap`, `chuck {count} tokens trap`) can reuse it as a single capture without re-deriving the count+hat parse. Open question §6.5 covers whether to ship Slice 3 with the capture-only reuse or also pre-extend `take` / `chuck` to consume it in the same commit.
- `prose_overlay_actions_format_at.py` (~+25 LOC) — add `prose_overlay_format_range(formatters: str, token_range: tuple[int, int])`:
  ```python
  def prose_overlay_format_range(formatters: str, token_range):
      if not instance.canvas.is_showing:
          return
      first, last = token_range
      if first < 0:
          app.notify("prose overlay: hat unbound or range overshoots buffer")
          return
      _execute_format(first, last, formatters, label=f"format_range:{first}-{last}")
  ```
  Reuses `_execute_format` from Slice 1. The capture does the parsing; the action just dispatches.
- `prose_overlay_cursorless.talon` (~+2 LOC):
  ```talon
  {user.cursorless_reformat_action} <user.formatters> at <user.prose_overlay_token_range>:
      user.prose_overlay_format_range(formatters, prose_overlay_token_range)
  ```
- `prose_overlay.py` (~+0 LOC) — reuses Slice 1's flag.

Total: ~40 LOC + new capture, two talon lines.

**Feature flag.** Reuses `prose_overlay_format_at_target`.

**Voice surface (Slice 3 adds).**
```talon
{user.cursorless_reformat_action} <user.formatters> at <user.prose_overlay_token_range>:
    user.prose_overlay_format_range(formatters, prose_overlay_token_range)
```

The capture expands to `<number_small> tokens <user.letter>` so the spoken form is `format snake at two tokens trap`. Worked example: buffer `[t]hese tokens here` (hat `trap` on token 0) → `format snake at two tokens trap` → range resolves to `(0, 1)` → `_execute_format(0, 1, "SNAKE_CASE", ...)` → buffer `these_tokens here`. The `prose_overlay_apply_formatter` execute already joins the range with `" ".join(tokens[first:last+1])` then re-splits the result via `formatted.split()` (`prose_overlay_actions_cursorless.py:150-157`) — same pipeline.

**Grammar specificity vs ISC-7 and Slice 2.** The new rule's `<user.prose_overlay_token_range>` capture has the literal `tokens` baked in via the `<number_small> tokens <user.letter>` rule. ISC-7's `<user.cursorless_target>` could theoretically match `two tokens trap` if Cursorless has a `two tokens` ordinal scope (it does — `cursorless_ordinal_scope` in the modifiers/ordinal_scope.py) but the spoken form differs: Cursorless's is `two tokens` as a SCOPE plus hat as a SEPARATE target — not the same parse tree. Verified by inspection: `~/.talon/user/cursorless-talon/src/cursorless.talon` line 8 binds `<user.cursorless_action_or_ide_command> <user.cursorless_target>` where the target capture eats the whole `two tokens trap` blob through cursorless_target's recursive rules. Our LIST + CAPTURE pattern at `prose_overlay_cursorless.talon` (the same trick used to beat cursorless at ISC-7) wins the same way here because the literal `tokens` inside our capture is more specific than any sub-rule inside `<user.cursorless_target>` that produces the same surface form.

**Keep criterion.** Across ~3 sessions, user reaches for the count-of-tokens form at least twice per session (it's a workhorse, not a corner case) and reports the start-only addressing ("I only had to remember `trap`, not `trap past sit`") as concretely easier. Range resolution is correct on all `count` values 1-9 (`number_small` covers 1-99; we expect dominant use 1-3).

**Kill criterion.** "Two tokens trap" misparses (e.g. recognized as "to tokens trap" and the `number_small` capture rejects `to`) often enough to be unreliable, OR off-by-one is confusing (`two tokens trap` lands tokens 0 and 1 but the user expected 0, 1, 2 from "starting at trap, then two more"), OR the range capture leaks into other rules and breaks them. Debug-log signal: failed dispatch logs `prose overlay: hat unbound or range overshoots buffer`; spike in that line is the kill marker. Revert the capture and the range action; Slices 1 + 2 unaffected; users wanting ranges fall back to ISC-7's `<user.cursorless_target>`.

**Reversibility.** `git revert <slice-3-sha>` removes one capture, one action, two talon lines. The reusable `user.prose_overlay_token_range` capture goes with it — if any future verb has already started consuming it, those rules break. Mitigation: Slice 3 ships **without** preemptively wiring the capture into `take` / `chuck` (open question §6.5); the capture is single-consumer at revert time.

**Non-goals.**
- No `last {count} tokens <hat>` ("starting at hat, going BACKWARD count tokens"). Defer to a v2 if the forward-only form turns out to be insufficient.
- No `tokens` (plural without count) as a shortcut for "1 token starting here" — the count is mandatory in v1 because the singular form is exactly what Slice 2 already covers (`format snake at trap`).
- No range-end specification (`format snake at two tokens trap urge` = "two tokens between trap and urge"). The Cursorless RangeTarget form already does this; we don't duplicate.
- No multi-range form (`format snake at two tokens trap and three tokens urge`). v1 is single range.

---

### Slice 4 — `format {formatter} at <prose-scope>` (sentence / clause / line / paragraph)

**Goal.** Learn whether scope-anchored format (`format snake at sentence`) is the missing tool for "transform every token in the current sentence" — a case Cursorless handles via `format snake at sentence` (its scope grammar), but which inside the PO buffer routes through the existing `_REGEX_SCOPE_PATTERNS` table at `prose_overlay_cursorless_resolve.py:_REGEX_SCOPE_PATTERNS` (ISC-4 shipped). The slice tests whether wiring a PO-native scope shortcut buys any ergonomics over going through ISC-7's `<user.cursorless_target>` pipeline.

**Files touched** (rough LOC):
- `prose_overlay_actions_format_at.py` (~+45 LOC) — add `prose_overlay_format_scope(formatters: str, scope_name: str)`:
  ```python
  def prose_overlay_format_scope(formatters: str, scope_name: str):
      """Apply formatter to the cursor's current scope (sentence/clause/line/paragraph)."""
      if not instance.canvas.is_showing:
          return
      if instance.cursor is None:
          app.notify("prose overlay: no cursor for scope target")
          return
      # Resolve via existing scope regex pipeline.
      from .prose_overlay_cursorless_resolve import _scope_regex
      span = _scope_regex(scope_name, instance.cursor)
      if span is None:
          app.notify(f"prose overlay: cursor not in any {scope_name}")
          return
      first, last = span
      _execute_format(first, last, formatters, label=f"format_scope:{scope_name}")
  ```
- **new capture** in `prose_overlay.py` (~+8 LOC):
  ```python
  @mod.capture(rule="sentence | clause | line | paragraph")
  def prose_overlay_format_scope(m) -> str:
      return str(m)
  ```
- `prose_overlay_cursorless.talon` (~+2 LOC):
  ```talon
  {user.cursorless_reformat_action} <user.formatters> at <user.prose_overlay_format_scope>:
      user.prose_overlay_format_scope(formatters, prose_overlay_format_scope)
  ```
- `prose_overlay.py` (~+6 LOC) — separate flag `prose_overlay_format_at_scope` (bool, default `False`); scope form is mentally distinct from hat/range form, so a separate flag lets the user opt into scopes alone if hats already feel sufficient.

Total: ~60 LOC + one new capture, two talon lines, one new setting.

**Feature flag.** `user.prose_overlay_format_at_scope` (bool, default `False`). Independent of Slices 1-3.

**Voice surface (Slice 4 adds).**
```talon
{user.cursorless_reformat_action} <user.formatters> at <user.prose_overlay_format_scope>:
    user.prose_overlay_format_scope(formatters, prose_overlay_format_scope)
```

Spoken: `format snake at sentence` / `format snake at line` / `format camel at paragraph`. The `<user.prose_overlay_format_scope>` capture is named distinctly from `<user.prose_overlay_token_range>` so the rules don't tie.

**Grammar specificity vs ISC-7.** Cursorless's scope grammar covers `sentence | clause | line | paragraph` natively, so `format snake at sentence` is already a valid utterance against ISC-7's rule (routing through `<user.cursorless_target>`'s scope sub-rules). The PO-native rule competes; our literal-bearing capture wins specificity, as in Slices 2 and 3. **Decision in this plan: ship Slice 4 only if Slices 1-3 prove that bypassing the `<user.cursorless_target>` pipeline is reliably faster — otherwise the scope case stays on ISC-7 and Slice 4 adds nothing.**

**Keep criterion.** Across ~3 sessions, scope-anchored format is used at least once per session for sentence/paragraph (the most common scopes for prose) and feels distinctly faster than ISC-7's scope path (measurable via debug-stream timestamps).

**Kill criterion.** Scope name list (`sentence | clause | line | paragraph`) doesn't cover the cases the user actually wants — i.e., the user reaches for "string" or "email" (covered by ISC-4 but not in our shortlist), and the partial coverage is more confusing than helpful. Revert; ISC-7 still covers all scopes uniformly.

**Reversibility.** `git revert <slice-4-sha>` removes one action, one capture, two talon lines, one setting. Slices 1-3 untouched.

**Non-goals.**
- No `string | number | email | nonWhitespaceSequence` in the capture (ISC-4 covers them through Cursorless; we keep Slice 4 to the dominant prose scopes).
- No `every sentence` / `all paragraphs` bulk form. The `<user.cursorless_target>` already covers `every sentence` via Cursorless's scope grammar; v2 if needed.
- No "scope at cursor + n" relative ("format snake at next sentence") — Cursorless's relative-scope grammar covers this; we don't duplicate.

---

### Slice 5 — JS-resolver passthrough (optional, gated by `user.prose_overlay_use_js_resolver=True`)

**Goal.** Once `user.prose_overlay_use_js_resolver=True` (ISC-8 in progress per `ISA.md:68`), translate PO-native targets (selection, single-hat, count-range, scope) into Cursorless `PrimitiveTarget` shapes and route through `processTargets` in `js/prose_resolve_targets.js`. This closes ISC-9 (Python resolver retirement) by removing one of the dual code paths: the PO-native captures stay as the **voice ergonomics layer**, but the resolution-to-token-range work happens in cursorless's actual `processTargets` pipeline.

**Files touched** (rough LOC):
- `prose_overlay_actions_format_at.py` (~+35 LOC) — `_execute_format` becomes a thin shim that either (a) calls the existing local path when `prose_overlay_use_js_resolver=False` (default) or (b) constructs a `PrimitiveTarget` dict and routes through `prose_overlay_actions_cursorless.prose_overlay_apply_formatter(target, formatters)` when the setting is on. The PO-native captures (Slices 1-3) get a translation layer:
  - Slice 1 selection → `PrimitiveTarget` with `mark.type="explicit"`, `range.start.index=first_idx`, `range.end.index=last_idx` (the cursorless mark format already in use at `prose_overlay_actions_cursorless_edit.py`).
  - Slice 2 single-hat → `PrimitiveTarget` with `mark.type="decoratedSymbol"`, `mark.symbol=letter`, `mark.color=color`.
  - Slice 3 count-range → `PrimitiveTarget` with `modifiers=[{"type":"relativeScope","scopeType":{"type":"token"},"length":count,"offset":1,"direction":"forward"}]` plus the hat mark.
  - Slice 4 scope → `PrimitiveTarget` with `modifiers=[{"type":"containingScope","scopeType":{"type":scope_name}}]`.
- `prose_overlay.py` (~+0 LOC) — reuses existing `prose_overlay_use_js_resolver` setting; Slice 5 adds **no new flag**.

Total: ~35 LOC, no new module, no new setting, no new grammar.

**Feature flag.** Reuses `user.prose_overlay_use_js_resolver` (default `False`). When `False`, Slice 5 is dormant; the local path from Slices 1-4 runs. When `True`, the dispatch routes through `processTargets`.

**Voice surface.** None. Slice 5 only changes the resolution path beneath an already-shipped voice surface.

**Keep criterion.** With `user.prose_overlay_use_js_resolver=True`, the four target shapes (selection, single-hat, count-range, scope) all round-trip through `processTargets` and produce the same token-range as the local path for every row in `MANUAL_VERIFICATION.md` (the ISC-8 verification harness). Removes one of the two divergent code paths — Slice 5 keep implies ISC-9 is one step closer.

**Kill criterion.** Translation layer is brittle (PO's token-index space vs Cursorless's char-offset space drifts on edge cases like trailing-punctuation tokens — `prose_overlay_state.py:142,144-160` splits `"hello."` into `["hello", "."]`, which Cursorless's tokenizer may or may not mirror). If parity fails on >2 rows of `MANUAL_VERIFICATION.md`, Slice 5 is wrong and we keep the dual-path duplication until ISC-8 itself stabilizes.

**Reversibility.** `git revert <slice-5-sha>` removes ~35 LOC in the action module. Slices 1-4 unaffected because they don't depend on the JS-resolver path being on.

**Non-goals.**
- No new voice grammar.
- No Python-resolver retirement (that's ISC-9, a separate cleanup after Slice 5 keeps).
- No change to ISC-7's existing `<user.cursorless_target>` rule (which already routes through the JS resolver when the setting is on; no work needed).

## 4. Foundational risks to dodge

These are the choices that, if made wrong in Slice 1, would make 2-5 expensive to undo.

### 4.1 Formatter source — copy vs import — HIGH RISK

**Risk.** Slice 1's `<user.formatters>` capture is already supplied by the trillium_talon community formatter machinery at `~/.talon/user/trillium_talon/core/formatters/formatters.py:446` (`reformat_text`) and `~/.talon/user/cursorless-talon/src/actions/reformat.py:12` (`mod.list("cursorless_reformat_action")`). The shipped `prose_overlay_apply_formatter` at `prose_overlay_actions_cursorless.py:152` already calls `actions.user.reformat_text(source_text, formatters)`. If we *copy* the formatter inventory into prose-overlay, we get a drift point — community adds a new formatter, prose-overlay doesn't see it until manually synced.

**Dodge.** **Import, don't copy.** Every slice in this plan routes through `actions.user.reformat_text(source_text, formatters)` exactly as the shipped `prose_overlay_apply_formatter` does. The formatter inventory is owned by trillium_talon's `formatter_list` (lines 224-256 of `formatters.py`) and surfaced via `formatters_dict` (line 257); we never duplicate that list in prose-overlay. The `<user.formatters>` capture is community-owned, and the `{user.cursorless_reformat_action}` list is cursorless-talon-owned. Slice 1's voice surface adds rules consuming these captures — it does NOT redeclare or shadow them.

This means a user who adds a new entry to `code_formatter.talon-list` (the curated 22-formatter shortlist at `~/.talon/user/trillium_talon/core/formatters/code_formatter.talon-list`) gets it automatically in prose-overlay. Same for community-side adds to `formatter_list`.

If `<user.formatters>` capture or `actions.user.reformat_text` aren't installed (e.g. minimal Talon setup without trillium_talon), Slice 1's rule fails to bind at parse time — the user sees no `format ...` grammar registered. This is the same failure mode as the shipped ISC-7 rule (which also requires both `<user.formatters>` and the `reformat_action` LIST); Slice 1 inherits the same dependency surface and doesn't add a new one.

### 4.2 Grammar collision — `format` is heavily-bound — MEDIUM RISK

**Risk.** The voice token `format` is bound by:
- Cursorless itself (`~/.talon/user/cursorless-talon/src/cursorless.talon:20`) as `{user.cursorless_reformat_action} <user.formatters> at <user.cursorless_target>` — the canonical applyFormatter rule.
- Prose-overlay's own ISC-7 mirror (`prose_overlay_cursorless.talon:55-56`) — same rule shape, different action body, shadows Cursorless when PO is active.
- App-specific bindings: `format that` / `format selection` in `~/.talon/user/trillium_talon/apps/vscode/vscode.talon:116-117` and `apps/visualstudio/visual_studio.talon:42-43` — gated to those apps only.
- Trillium's Go language pack: `format print: fmt.Printf` at `~/.talon/user/trillium_talon/lang/go/code_common_function.talon-list:14` and similar — gated to Go context only.
- The dictation-mode `formatted <user.format_text>` rule at `~/.talon/user/trillium_talon/core/modes/dictation_mode.talon:63` — different prefix (`formatted`, not `format`), no collision.

**Dodge.** **Audit (done above) confirms `format` followed by `<user.formatters>` is a unique surface in PO-active contexts.** All conflicts are gated by app context (vscode, visualstudio) or language context (Go), and the PO matcher (`tag: user.prose_overlay_active`) is strictly more specific than the app-context matchers — when PO is showing, app-tag contexts are still active but the PO grammar rules outrank theirs on specificity because they carry both the PO tag and the LIST/CAPTURE pattern that beats `<user.cursorless_target>`.

The hardest case is `format that` inside VS Code with PO showing: VS Code's `format that` (formats document) competes with… nothing PO-side, because PO doesn't bind `format that`. So `format that` continues to fire VS Code's binding. **Decision: leave `format that` alone**; it's a host-app verb, and PO has no analogue (the "format the whole buffer" case is `format snake at line` × N or `format snake` after `take everything`, neither of which collides).

### 4.3 The `at` connector — keep it or drop it — DECIDED IN §1, RESTATED FOR THE RECORD

**Risk.** Cursorless's canonical `format <formatter> <target>` form has **no `at`** (`format snake fox` is valid Cursorless; the `at` is added in cursorless.talon:20's rule for clarity but is grammatical filler — the action call doesn't depend on it). Mirroring that exactly would yield `format snake fox` in PO. The risk in **keeping** `at`: utterance length grows by one word. The risk in **dropping** it: `format {formatter_list} <user.letter>` can collide when a formatter's spoken form contains a NATO letter form.

**Audit of overlapping spoken forms.** The user's curated formatter list at `~/.talon/user/trillium_talon/core/formatters/code_formatter.talon-list`:
- `all cap: ALL_CAPS` — `cap` is the NATO letter for C (`letter.talon-list:5`).
- `all down: ALL_LOWERCASE` — no NATO collision.
- `camel: PRIVATE_CAMEL_CASE` — no collision (camel is one word).
- `dotted | list | dub string | dunder | hammer | kebab | packed | padded | slasher | conga | smash | snake | string | constant | round | box | diamond | curly | skis | percentages` — none collide with single NATO letters.

The collision case is **exactly one formatter** (`all cap`). Drop-the-`at` parse: `format all cap` could parse as `format <formatter:ALL_CAPS>` (one rule, two-word formatter) OR `format <formatter:?> <letter:c>` (formatter is unfilled, hat is c). Talon's grammar engine fills the longer match first, so `all cap` consumes both tokens as the formatter. **No actual ambiguity.** But the precedent of "formatters can grow multi-word spoken forms" (anyone adds a formatter named `all bat` and the trap fires) makes drop-the-`at` a long-tail correctness risk for trivial utterance savings.

**Decision: keep `at`.** Three reasons: (1) matches the already-shipped ISC-7 rule that the user already has muscle memory for, so the new slices feel like a natural extension; (2) protects against the long-tail multi-word formatter collision; (3) matches Cursorless's `format snake at fox` published spoken form (the `at` is the user-facing canonical even though the action arg-list doesn't require it). Slice 1 is the only no-`at` rule, and that's because Slice 1 has no target at all — `format snake` is unambiguous because there's no second capture to fail against.

### 4.4 Range capture reusability — `user.prose_overlay_token_range` belongs in PO core — MEDIUM RISK

**Risk.** Slice 3's `<number_small> tokens <user.letter>` capture is useful well beyond `format`: every verb that takes a target could grow a range variant (`take two tokens trap`, `chuck two tokens trap`, `change two tokens trap`). If Slice 3 declares the capture in `prose_overlay_actions_format_at.py`, the namespace is wrong — the capture is **not format-specific**. Moving it later is a non-breaking change but creates a transient state where the capture is owned by the wrong module.

**Dodge.** **Declare `user.prose_overlay_token_range` in `prose_overlay.py`** (the central module owning settings and shared captures), not in the format-at action module. Slice 3's action module *consumes* the capture but doesn't own it. Future verbs (Slice 6+) consume the same capture without depending on the format-at module. Open question §6.5 covers whether Slice 3 should preemptively wire the capture into `take` / `chuck` in the same commit — recommended NO (one capability per slice, revert clean).

### 4.5 Selection semantics — no-selection branch decision — DECIDED IN SLICE 1

**Risk.** Slice 1's `format snake` requires a non-None `buffer.get_selection()`. What should happen when there's no selection? Three options:
- **No-op + notify** (chosen): `app.notify("prose overlay: no selection — try 'format snake at <hat>'")`. Strictly correct, never destructive, surfaces the right next-step.
- **Implicit cursor-token target**: format the token at `instance.cursor`. Convenient but silently does the wrong thing if the user expected the previous selection to still apply.
- **Implicit whole-buffer**: format every token. Catastrophically wrong on a 50-token buffer; never doing this.

**Dodge.** **No-op + notify.** Cheap, reversible, learnable — the notify points at the next form to try. The implicit-cursor-token alternative is reserved as a Slice 1.5 if no-op turns out to be too strict in real usage, but it has higher latent danger (silent wrong-target rewrites) and Slice 1 should ship with the safe variant first.

### 4.6 Multi-token formatter join semantics — owned by community, not PO — LOW RISK

**Risk.** When `_execute_format` runs with `first=0, last=2` on a buffer `[these, ., tokens]` (with `.` as a punctuation token from `_split_trailing_punct`), it joins `" ".join(["these", ".", "tokens"])` → `"these . tokens"`, then `reformat_text` snake-cases that to `"these_._tokens"` and splits to `["these_._tokens"]`. Is that right? Probably not what the user wanted ("these_tokens" with the punct dropped or preserved positionally). But that's a **community-pipeline question**, not a PO-design question.

**Dodge.** **Inherit the shipped behavior of `prose_overlay_apply_formatter`** — Slice 1-3's `_execute_format` is structurally identical to ISC-7's execute body at `prose_overlay_actions_cursorless.py:144-160`. Whatever community's `reformat_text` produces for the joined span is what we emit. Punctuation-aware joining is a future cross-cutting fix for the formatter pipeline at large (would also affect ISC-7). Out of scope for this plan; not a blocker.

If the punctuation-in-range case turns out to be common enough to need a special-case (skip leading/trailing punct tokens before joining), it lives in a Slice 1.5 dedicated to "format pipeline punctuation handling" — independent of which target capture is in use.

### 4.7 Undo sealing — one utterance = one STRUCTURAL record — VERIFIED FROM SHIPPED CODE

**Risk.** Each Slice 1-3 invocation must bracket as exactly one undo step. Multiple `_record` calls inside one `_execute_format` would create multiple undo records, breaking the "one utterance, one undo" contract that ISC-23 established.

**Dodge.** **Use the exact bracket the shipped `prose_overlay_apply_formatter` uses** at `prose_overlay_actions_cursorless.py:146-160`:
```python
instance.buffer.commit_start(label="format_selection", kind=EditKind.STRUCTURAL)
try:
    # ... mutate via set_tokens_raw / replace_token / etc
    pass
finally:
    instance.buffer.commit_end()
```
The bracket API at `prose_overlay_state.py:303-338` is verified — `commit_start` is nested-safe (no-op if already open), `commit_end` is no-op if no group is open, and the bracket-cap of `_MAX_COMPOSED_DELTAS=64` splits multi-edit brackets into multiple records (irrelevant for our case; we do 1 delta per format invocation when using `set_tokens_raw` inside the bracket, or per-token deltas when using `replace_token`, all under the same kind/label).

The `STRUCTURAL` kind is the right kind. ISC-23 verified that `STRUCTURAL` records never coalesce (per the `kind == EditKind.DICTATION` guard at `prose_overlay_state.py:396-401` in `_record`'s coalescing block), so the `overlay undo group on/off` toggle has no effect on our records — they always seal as discrete undo steps.

**Label format.** Slice 1: `"format_selection"`. Slice 2: `f"format_hat:{color}_{letter}"`. Slice 3: `f"format_range:{first}-{last}"`. Slice 4: `f"format_scope:{scope_name}"`. The label is human-readable per `prose_overlay_state.py:131,310` and surfaces as the undo description if `overlay undo what` ever ships (UNDO_REDO_PLAN Phase 3).

### 4.8 Selection retention — Slice 1 must keep selection on the rewritten span — LOAD-BEARING

**Risk.** Slice 1's selection-target loop only works if the post-rewrite selection sits on the **new** token span. If selection clears (which is the default behavior of every mutation in `prose_overlay_state.py` — `add_text`, `delete_token`, `replace_token`, `insert_at`, `set_tokens_raw` all `self._selection = None`), the user's "select-format-format-format" iterative loop is broken: they'd have to re-select between every format. That's friction-heavy enough to kill Slice 1's keep verdict.

**Dodge.** **`_execute_format` explicitly re-sets the selection after `commit_end`**. The pattern:
```python
new_last = first + len(new_tokens) - 1  # new_tokens = formatted span after split
instance.buffer.set_selection(first, new_last)
```
Call after `commit_end()` so the selection is registered against the post-mutation buffer state. The set is independent of the bracket (selection isn't part of the undo record's mutation list; it's recorded as `selection_after` at `prose_overlay_state.py:332,404` for the next undo to restore on revert). This means undo restores the pre-format selection too — round-trip correct.

Edge case: snake-formatting a 3-token span `["the", "quick", "fox"]` produces one token `["the_quick_fox"]`. The new selection is `(first, first)` — a one-token selection. The visual semantics: the box that was around 3 tokens is now around 1 token. Acceptable; mirrors how host editors handle the same case.

Edge case: title-formatting `["hello", "world"]` produces `["Hello", "World"]`. New selection is `(first, first + 1)` — span unchanged. Trivially correct.

## 5. Integration touchpoints with in-flight work

### Existing ISC-7 `apply_formatter` — `prose_overlay_cursorless.talon:55-56`, `prose_overlay_actions_cursorless.py:120-164`

- **Cite and inherit, do not modify.** Every slice's `_execute_format` is a copy of ISC-7's execute body. The shipped rule and action body stay byte-identical; the new slices are purely additive (new captures, new actions, new talon rules in the same file at the bottom).
- The label space is shared: ISC-7 uses `"apply_formatter"`, Slices 1-4 use `"format_selection"` / `"format_hat:..."` / `"format_range:..."` / `"format_scope:..."`. Distinct labels so the debug stream + future `overlay undo what` can distinguish dispatchers.
- ISC update: ISC-7 stays green (it covers the explicit Cursorless target case). The new ISCs are listed in §5 ISA updates below.

### Undo/redo (`docs/UNDO_REDO_PLAN.md`, ISC-23 shipped)

- Phase 2 of the undo plan has landed (commits `ec52d32`, `7eb3e56`, `1a618a3` per `ISA.md:91-92`). The bracket API is live:
  ```python
  # From prose_overlay_state.py:303-338 (verified read).
  instance.buffer.commit_start(label="format_selection", kind=EditKind.STRUCTURAL)
  # ... mutations ...
  instance.buffer.commit_end()
  ```
- All four slices use this bracket exactly. One utterance → one undo step. The `STRUCTURAL` kind is invariant across all four. Coalescing (the `overlay undo group on/off` toggle) is irrelevant because it only affects `DICTATION` records (`prose_overlay_state.py:396-401`).
- Slice 1's selection retention rides on the same record — `set_selection` after `commit_end` updates the post-state; undo restores the pre-format selection via `selection_before` on the undo record. Round-trip verified by the same logic that ISC-23 already verified for `prose_overlay_apply_formatter`.

### Buffer rev counter (`prose_overlay_state.py:117,168`, ISC-21 shipped)

- `buffer.rev` bumps once per delta inside the open bracket (per `_record` at line 388). Slice 1's selection format will produce 1 delta (`set_tokens_raw` inside bracket → 1 delta at line 542) → 1 rev bump per utterance. Identical to ISC-7.
- No new rev-keyed cache is introduced by this plan. The captures don't memoize (they're cheap to recompute on every utterance).

### Existing selection API — `prose_overlay_state.py:344-354`

- `set_selection(start, end)` / `clear_selection()` / `get_selection()` are the substrate. Slice 1 reads `get_selection()` to find the target; Slices 1-3 call `set_selection` to retain on the rewritten span.
- The selection is already wired to `Cursorless setSelection` / `clearAndSetSelection` actions via `prose_overlay_actions_cursorless.py:80,114`. So the loop `take fox past urge` (Cursorless setSelection) → `format snake` (Slice 1) works end-to-end on day one.

### Hat resolution — `_hat_to_index` at `prose_overlay_actions_core.py:60-67`

- Slice 2 reuses `_hat_to_index(letter, color)` exactly as `change <user.letter>` does at `prose_overlay.talon:98-100`. The function returns `-1` when the hat is unbound; Slice 2's action checks this and notifies.
- The `(letter, color)` → token index map is rebuilt on every `_recompute_hats` invocation (`prose_overlay_actions_core.py:31-43`); since `_execute_format` calls `_recompute_hats()` after `commit_end()` (matching ISC-7's pattern at `prose_overlay_actions_cursorless.py:161`), the next utterance's `_hat_to_index` sees the new buffer's hats. No stale-hat risk.

### Scope regex pipeline — `_scope_regex` in `prose_overlay_cursorless_resolve.py` (ISC-4 shipped)

- Slice 4 reuses the existing `_REGEX_SCOPE_PATTERNS` table from `prose_overlay_cursorless_resolve.py`. No new scope-resolution code is written; we route through the same function ISC-7 already routes through for the scope cases.
- If `_scope_regex` returns `None` (cursor not in any scope of the named type), Slice 4 notifies and returns. Same failure mode as ISC-7's scope path.

### JS resolver path — `user.prose_overlay_use_js_resolver` setting (`prose_overlay.py:60-70`)

- Slice 5 routes through the same setting. When `False` (default), Slices 1-4 use the local path. When `True`, Slice 5's translation layer constructs `PrimitiveTarget` shapes and dispatches through `prose_overlay_apply_formatter` (which already routes through the JS resolver when the setting is on, per `_resolve_target_to_token_range` in `prose_overlay_cursorless_resolve.py`).
- No new setting added by Slice 5.
- Slice 5 ships **after** ISC-8 passes parity (per the ISA's `MANUAL_VERIFICATION.md` row check). Until then, Slice 5 is dormant code behind the existing flag.

### Existing `change <user.letter>` precedent — `prose_overlay.talon:98-100`

- The change-hat rule mirrors the shape of Slice 2 exactly: bare `<user.letter>` capture (with optional `<user.prose_hat_color>` prefix), routes through `_hat_to_index`, one STRUCTURAL undo step. The grammar specificity vs Cursorless's `change <user.cursorless_target>` is the verified precedent that Slice 2 inherits.
- Cite the precedent in Slice 2's commit message and in `prose_overlay_actions_format_at.py` module docstring.

### Cursorless's native `format <formatter> <target>` rule — `~/.talon/user/cursorless-talon/src/cursorless.talon:20`

- Cite, do not modify. The native rule is gated by `tag: user.cursorless and not tag: user.prose_overlay_active` (`cursorless.talon:3-4`), so when PO is up, the native rule is dormant. The new PO-native rules carry `tag: user.prose_overlay_active` and bind in PO's place.
- The shared `<user.formatters>` and `{user.cursorless_reformat_action}` captures are owned by cursorless-talon and community; this plan consumes them without redeclaring. If the user updates cursorless-talon, both ISC-7's rule and the new Slice 1-4 rules automatically pick up the new formatter inventory.

### ISA updates (`/Users/trilliumsmith/code/prose-overlay/ISA.md`)

Propose these ISC edits when the plan is approved:
- **New ISC-25**: Slice 1 — `format <user.formatters>` (no target) operates on the current selection behind `prose_overlay_format_at_target` setting; selection retained on rewritten span; one STRUCTURAL undo step.
- **New ISC-26**: Slice 2 — `format <user.formatters> at [<color>] <user.letter>` operates on the single hat-resolved token; reuses `_hat_to_index`; one STRUCTURAL undo step.
- **New ISC-27**: Slice 3 — `format <user.formatters> at <number_small> tokens <user.letter>` operates on the count-of-tokens range starting at the hat; introduces reusable `user.prose_overlay_token_range` capture; one STRUCTURAL undo step.
- **New ISC-28** (optional): Slice 4 — `format <user.formatters> at (sentence | clause | line | paragraph)` operates on the cursor's containing scope via existing `_scope_regex`; behind `prose_overlay_format_at_scope` setting.
- **New ISC-29** (optional, gated on ISC-8): Slice 5 — PO-native format targets route through `processTargets` when `prose_overlay_use_js_resolver=True`; closes one divergent code path and contributes to ISC-9.

Update the Features table:
- Add `FormatAtSelection` (ISC-25) — shipped.
- Add `FormatAtHat` (ISC-26) — shipped.
- Add `FormatAtTokenRange` (ISC-27) — shipped + reusable capture.
- Add `FormatAtScope` (ISC-28) — optional.
- Add `FormatAtJSResolverPath` (ISC-29) — optional, blocked on ISC-8.

Update the Test Strategy table: ISC-25–29 entries point at this plan (`docs/FORMAT_AT_PLAN.md`) the same way ISC-13 points at `docs/HOMOPHONE_UI_PLAN.md`.

## 6. Open questions for Trillium

1. **Default-on or default-off for Slice 1?** Plan defaults `prose_overlay_format_at_target` to `False` so the experiment is opt-in. Counter-case: default-on so the no-target form is actually tested in normal flow (a setting that nobody flips is a setting that doesn't ship). Lean toward default-off for the first commit, flip to default-on after one session of "yeah leave it on" feedback. Same posture as `HOMOPHONE_UI_PLAN.md` §6 Q1.

2. **Formatter inventory — full community list, curated subset, or extensible?** The capture `<user.formatters>` already resolves through `code_formatter.talon-list` (curated 22-entry shortlist). The full inventory at `formatter_list` in `formatters.py:224-256` has ~29 entries including `NOOP`, `TRAILING_SPACE`, `REMOVE_FORMATTING`, `PARENTHESIZED`, etc. that aren't in the shortlist. The shipped ISC-7 rule consumes whatever `<user.formatters>` resolves to. **Decision: stay on the curated shortlist (whatever `<user.formatters>` already produces).** Confirm before Slice 1 ships. If Trillium wants the full list, he can extend `code_formatter.talon-list` and both ISC-7 and new slices pick it up automatically.

3. **No-selection branch — no-op + notify, or implicit cursor-token target?** Plan picks **no-op + notify** (§4.5). Counter-argument: the implicit-cursor-token form (format the token at `instance.cursor`) matches the host-editor convention "format current word." Pre-decided no-op for safety (silent wrong-target is worse than vocal no-op); confirm before Slice 1 ships, and reserve the implicit-cursor-token variant for a Slice 1.5 if no-op turns out to feel too strict in usage.

4. **Ship reverse `unformat <hat>` in this plan or defer?** The community has `remove_code_formatting` and `unformat_upper` at `formatters.py:163-176` plus a `REMOVE_FORMATTING` formatter in the inventory. A `unformat at <hat>` verb would route through `format remove_formatting at <hat>` already (the `REMOVE_FORMATTING` formatter does the de-snake / de-camel work). **Defer.** The verb is achievable via Slice 2's existing grammar — `format remove at trap` if `code_formatter.talon-list` has a `remove: REMOVE_FORMATTING` entry (it doesn't currently; would need a one-line addition). Adding the entry is a separate trivial change; building a separate `unformat` verb is over-engineering. Confirm.

5. **Pre-wire `user.prose_overlay_token_range` into `take` / `chuck` in the same commit as Slice 3, or land it format-only first?** The capture is reusable by definition (§4.4), but Slice 3 only consumes it from `format`. Pre-wiring `take {count} tokens trap` and `chuck {count} tokens trap` in the same commit gives the user three new useful verbs at once and amortizes the capture-design work. Counter: violates the "one capability per slice, revert clean" rule — if Slice 3's capture turns out to be wrong, reverting it pulls four verbs at once and breaks user muscle memory. **Recommendation: land Slice 3 format-only first, ship `take` / `chuck` extensions as a follow-up commit one session later after Slice 3's keep verdict is in.** Confirm.

---

*Plan ends. First commit (Slice 1) should be invisible at the voice layer (off by default), reversible in one revert, decidable from one session of normal use with the setting flipped on. Slice 2 follows immediately because it has zero new substrate (just a new dispatcher over the same `_execute_format` helper). Slice 3 ships after the reusable capture is reviewed (§4.4 + §6.5). Slices 4 and 5 are optional and gated on Slice 1-3 keep verdicts.*
