---
task: Build MVP prose dictation overlay for Talon Voice
slug: prose-overlay-mvp
effort: E3
phase: observe
progress: 0/36
mode: build
started: 2026-05-21T00:00:00Z
updated: 2026-05-21T00:00:00Z
project: prose_overlay
---

## Problem

Voice dictation in Talon types directly into the focused application with no buffer, preview, or editing step. Misrecognitions get committed immediately. The user cannot review, correct, or restructure dictated text before it lands. There is no visual feedback showing individual word tokens or a way to target specific words for deletion by voice.

## Vision

A translucent overlay panel appears on screen showing each dictated word as a distinct token with a gray Cursorless-style hat letter above it. The user sees their dictation accumulate in real time, can say "chuck bat" to delete the word under hat "b", and when satisfied says "bravely" to paste the entire buffer into the previously focused window. The experience feels like a voice-first text editor floating above the desktop.

## Out of Scope

- Misrecognition store or correction history
- Homophone detection or suggestion
- Color-coded hats (gray only for MVP)
- Custom confirm grammar (reuse existing line-enders)
- Code/AST editing or syntax awareness
- Sentence/paragraph scope targeting
- Multi-line cursor or selection model
- Undo/redo within the overlay
- Browser panel rendering (canvas only)

## Principles

- Reuse existing Talon community infrastructure (user.letter list, line-ender commands) rather than reinventing
- Non-invasive: overlay must not steal focus from the previously active application
- Minimal grammar surface: only the commands needed for MVP, nothing speculative
- Single-file-per-concern: separate rendering, state, and grammar

## Constraints

- Python-only Talon scripting (no JS, no subprocess, no external servers)
- Talon canvas for rendering (Canvas.from_screen pattern from friction_overlay.py)
- Must live in /Users/trilliumsmith/.talon/user/trillium/plugin/prose_overlay/
- Must use the existing user.letter list (air=a, bat=b, cap=c, ..., zip=z) for hat identifiers
- Hat alphabet limited to 26 letters; if buffer exceeds 26 tokens, later tokens get no hat
- Must hook into existing dictation_ender mechanism for confirm (bravely/gravely/slap/lap)
- canvas.blocks_mouse = False (non-blocking overlay)

## Goal

Deliver a working Talon plugin with: (1) a canvas overlay that renders dictation buffer tokens with gray hat letters, (2) dictation capture that intercepts text and routes it to the buffer instead of the focused app, (3) hat-targeted delete commands, (4) confirm-and-paste via existing line-enders, and (5) a setting toggle.

## Criteria

- [x] ISC-1: Directory exists at /Users/trilliumsmith/.talon/user/trillium/plugin/prose_overlay/
- [x] ISC-2: prose_overlay_state.py exists and defines a ProseBuffer class with tokens list, add_text(), delete_token(index), delete_through(index), get_tokens(), clear(), and get_text() methods
- [x] ISC-3: ProseBuffer.add_text("hello world") results in tokens ["hello", "world"]
- [x] ISC-4: ProseBuffer.delete_token(1) on ["hello", "world"] results in ["hello"]
- [x] ISC-5: ProseBuffer.delete_through(1) on ["hello", "world", "foo"] results in ["hello"] (deletes from hat position through end)
- [x] ISC-6: ProseBuffer.get_text() returns tokens joined with spaces
- [x] ISC-7: prose_overlay_draw.py exists with a draw function that renders tokens as text with gray hat letters above each
- [x] ISC-8: Hat letters are assigned sequentially a-z from the user.letter list values
- [x] ISC-9: Hat rendering uses gray color (not colored) for the hat letter text
- [x] ISC-10: Tokens beyond index 25 render without hats (no crash, graceful degradation)
- [x] ISC-11: prose_overlay_canvas.py exists managing Canvas lifecycle (show/hide/freeze)
- [x] ISC-12: Canvas uses Canvas.from_screen pattern (consistent with friction_overlay.py)
- [x] ISC-13: Canvas sets blocks_mouse = False
- [x] ISC-14: prose_overlay.py exists as the main module with actions and settings
- [x] ISC-15: Setting user.prose_overlay_enabled exists (type bool, default true)
- [x] ISC-16: Action user.prose_overlay_show() creates and shows the canvas overlay
- [x] ISC-17: Action user.prose_overlay_hide() destroys the canvas overlay and clears buffer
- [x] ISC-18: Action user.prose_overlay_add_text(text) adds text to buffer and refreshes canvas
- [x] ISC-19: Action user.prose_overlay_delete_hat(letter) deletes the token at the hat letter's index
- [x] ISC-20: Action user.prose_overlay_delete_past_hat(letter) deletes from end back through the hat letter's token
- [x] ISC-21: Action user.prose_overlay_confirm() pastes buffer text to previously focused window and clears
- [x] ISC-22: prose_overlay.py captures the active window (ui.active_window()) before showing the overlay
- [x] ISC-23: On confirm, focus is restored to the captured window before pasting
- [x] ISC-24: prose_overlay.talon exists with tag-gated grammar for overlay commands
- [x] ISC-25: Tag user.prose_overlay_active is defined and set when overlay is visible
- [x] ISC-26: Command "chuck <user.letter>" calls user.prose_overlay_delete_hat with the letter value
- [x] ISC-27: Command "chuck past <user.letter>" calls user.prose_overlay_delete_past_hat
- [x] ISC-28: prose_overlay_dictation.talon exists to intercept dictation when overlay is active
- [x] ISC-29: When tag user.prose_overlay_active is set and mode is dictation, raw_prose routes to overlay buffer instead of direct insertion
- [x] ISC-30: prose_overlay_ender.talon hooks into dictation_ender pattern to trigger confirm on bravely/gravely/slap/lap
- [x] ISC-31: After confirm, the overlay hides and buffer clears
- [x] ISC-32: Anti: Overlay canvas must NOT steal focus from the previously active window
- [x] ISC-33: Anti: Plugin must NOT redefine the user.letter list or user.dictation_ender list
- [x] ISC-34: Anti: No files outside prose_overlay/ directory are modified
- [x] ISC-35: Antecedent: Canvas.from_screen and canvas.freeze pattern works (validated by friction_overlay.py existing precedent)
- [x] ISC-36: All .py files have no syntax errors (python3 -m py_compile succeeds)

## Test Strategy

| ISC | Type | Check | Threshold | Tool |
|-----|------|-------|-----------|------|
| ISC-1 | filesystem | directory exists | exists | Bash ls |
| ISC-2 | code | class and methods defined | all present | Grep |
| ISC-3..6 | logic | buffer operations correct | exact match | Read (code review) |
| ISC-7..10 | code | draw function with hat rendering | present | Read/Grep |
| ISC-11..13 | code | canvas lifecycle | pattern match | Read |
| ISC-14..23 | code | actions and settings | defined | Grep |
| ISC-24..30 | code | talon grammar files | correct syntax | Read |
| ISC-31 | code | confirm clears buffer | present | Read |
| ISC-32..34 | anti | no focus steal, no redefinition, no external mods | absence | Grep |
| ISC-35 | antecedent | canvas pattern precedent | exists | Read |
| ISC-36 | build | syntax check | exit 0 | Bash py_compile |

## Features

| Name | Description | Satisfies | Depends On | Parallelizable |
|------|-------------|-----------|------------|----------------|
| ProseBuffer | State management for word token buffer | ISC-2..6 | none | yes |
| OverlayDraw | Canvas draw callback rendering tokens with gray hats | ISC-7..10 | ProseBuffer | yes |
| CanvasLifecycle | Canvas creation, show, hide, freeze | ISC-11..13 | OverlayDraw | no |
| MainModule | Actions, settings, window capture, confirm flow | ISC-14..23 | ProseBuffer, CanvasLifecycle | no |
| EditGrammar | .talon file for chuck commands | ISC-24..27 | MainModule | yes |
| DictationIntercept | .talon file routing dictation to buffer | ISC-28..29 | MainModule | yes |
| EnderHook | .talon file for line-ender confirm | ISC-30..31 | MainModule | yes |
| AntiChecks | Verify no focus steal, no redefinitions | ISC-32..34 | all | no |

## Decisions

## Changelog

## Verification
