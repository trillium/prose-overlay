# Manual Verification — JS Resolver Migration (F9)

> Walks every grammar rule in `prose_overlay_cursorless.talon` against a live
> prose buffer, with the JS resolver flag flipped on, and logs observed
> behavior next to expected. One row per spoken-form / target-shape combo.
>
> **Status:** template populated 2026-06-06; awaiting Talon verification pass.
>
> ISA: brain-z6m4 (Feature F9, ISCs 58–66). The ISA Verification section
> mirrors the rows below once each is filled in.

## How to run

1. Set `user.prose_overlay_use_js_resolver = True` in
   `prose_overlay/settings.talon` (or a personal override file).
2. Open the prose overlay over any window — speak `prose start` (or whatever
   binding shows the canvas).
3. Dictate the buffer text shown in the **Buffer** column for each row.
4. Speak the **Spoken form**, observe the effect, take a screenshot
   (`⌘⇧4` → name as `f9-<row>.png` next to this file).
5. Record **Observed** and tick **PASS** or **FAIL**. If FAIL: append a
   one-line failure note. Do not delete failing rows — they become Decisions.

## Pre-flight

| Check | How |
|---|---|
| Bundle is fresh | `ls -la js/prose_resolve_targets.js` mtime ≥ today |
| Flag is on | `actions.user.print_settings()` (or read settings.talon) shows `prose_overlay.use_js_resolver: True` |
| JS errors surface, not silence | Speak `take zed` (a letter with no hat) — Talon log should show `prose_overlay: JS resolver failed (no fallback): …`, and the buffer must be unchanged. |

## Verification rows

Buffer used for all rows unless noted: dictate `the air ball drum echo` after
showing the overlay (5 tokens, hats t/a/b/d/e on each token respectively).

| # | ISC | Spoken form | Buffer | Expected | Observed | Screenshot | P/F |
|---|---|---|---|---|---|---|---|
| 1 | 59 | `take air` | std | "air" highlighted as selection | | f9-01.png | |
| 2 | 59 | `chuck ball` | std | "ball" deleted → `the air drum echo` | | f9-02.png | |
| 3 | 59 | `chuck blue air` | std + blue hats | "air" deleted only if blue 'a' matches | | f9-03.png | |
| 4 | 60 | `chuck head ball` | std | tokens 0..2 deleted → `drum echo` | | f9-04.png | |
| 5 | 60 | `chuck tail drum` | std | tokens 3..4 deleted → `the air ball` | | f9-05.png | |
| 6 | 61 | `change head ball` | std | tokens 0..2 deleted, cursor parked at start | | f9-06.png | |
| 7 | 61 | `change tail drum` | std | tokens 3..4 deleted, cursor parked at end of `ball` | | f9-07.png | |
| 8 | 62 | `bring air to drum` | std | drum replaced by air's value | | f9-08.png | |
| 9 | 62 | `move air to drum` | std | "air" removed, drum replaced with "air" | | f9-09.png | |
| 10 | 62 | `bring blue air to drum` | std + blue 'a' | blue-a sourced, drum overwritten | | f9-10.png | |
| 11 | 63 | `pre start` | std, cursor anywhere | cursor at gap 0 (before "the") | | f9-11.png | |
| 12 | 63 | `post end` | std, cursor anywhere | cursor at gap 5 (after "echo") | | f9-12.png | |
| 13 | 64 | `chuck file` | std | whole buffer cleared | | f9-13.png | |
| 14 | 64 | `chuck line` | std | whole buffer cleared (single-line ⇒ whole buffer) | | f9-14.png | |
| 15 | 64 | `take file` | std | whole buffer selected | | f9-15.png | |
| 16 | 65 | `take quotes air` | `" the air "` (dictate quotes as `quad`) | the parenthesized `the air` highlighted | | f9-16.png | |
| 17 | 65 | `chuck round air` | `( the air )` | round-paren contents removed | | f9-17.png | |
| 18 | 33 | range: `chuck air past drum` | std | tokens 1..3 deleted | | f9-18.png | |
| 19 | — | list: `take air and drum` | std | both "air" and "drum" selected | | f9-19.png | |
| 20 | — | format: `format snake air past drum` | std | tokens 1..3 → `air_ball_drum` | | f9-20.png | |

(Buffer key: `std` = `the air ball drum echo` with default-color hats.)

## Failure protocol

When a row fails:

1. Capture the Talon log lines around the command — filter for `prose_overlay:`
   and `JS resolver`.
2. Append a row to the **Failures** section below with: ISC #, spoken form,
   log excerpt, hypothesis (Python diverged from JS / bundle stale / mark
   shape wrong / etc.).
3. Reproduce on a clean buffer to confirm.
4. Append the result to ISA brain-z6m4 Verification + open a child task on #19.

## Failures

(none yet)

## Sign-off

| Field | Value |
|---|---|
| Date completed | _____ |
| Bundle SHA-256 | _____ |
| Cursorless source HEAD | _____ |
| Talon version | _____ |
| Prose overlay commit | _____ |
| Total rows passed | _____ / 20 |
