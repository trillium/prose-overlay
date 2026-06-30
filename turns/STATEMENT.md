# ISA-loop kickoff statement

Paste this verbatim after `/loop 30m ` to start the autonomous push toward
`ISA.md` v2 ideal state (all 24 ISCs green). The same statement re-fires
every 30 min until the goal is reached or the user interrupts.

---

## Paste this:

```
Advance prose-overlay toward ISA.md v2 ideal state (24 ISCs across 4 phases — Cursorless verb parity, visual ambiguity feedback, observability+headless driving, modular substrate). Stop when every ISC checkbox is ticked.

Each turn, do exactly this:

1. Determine turn number N: `ls turns/[0-9]*.md 2>/dev/null | wc -l` plus 1.
2. Read ISA.md. Enumerate unchecked ISCs. Pick the highest-leverage next one based on: explicit dependencies named in the spec, slice plans in docs/*_PLAN.md (UNDO_REDO_PLAN, HOMOPHONE_UI_PLAN, STACK_OVERFLOW_PAPER_TRAIL_PLAN), and avoiding ISCs that need external repro (e.g. ISC-18's HAT_ALLOC crash reproduction, ISC-8's MANUAL_VERIFICATION pass) unless the user is present to drive that.
3. Execute one slice's worth of work — favor depth (one ISC fully done) over breadth (three half-built). For coding tasks at E3+, spawn Forge in worktree (`isolation: worktree`, `commit after each feature completes — do not batch into a single commit at the end`, `use relative paths or $WORKTREE_DIR — never write to ~/.claude/ or ~/.talon/`). For plan-doc work, spawn Architect. For locate, spawn Explore. Land worktree branches via rebase-onto-main + ff-merge before turn end.
4. Append a turn report to turns/{N}.md following the format in turns/README.md (targeted ISC, why, commits shipped, what's open, decisions, blockers, ISA delta). If turns/{N}.md already exists for any reason, increment N until you find a free slot.
5. If you flipped an ISC checkbox in ISA.md, also append a one-line entry to the ISA `## Changelog` section with the date and the shipped ISC numbers.
6. If blocked (waiting on user input, manual repro needed, external auth, etc.), write the turn report with the blocker section filled and stop. Do not loop on a blocked task — the next 30-min fire will re-evaluate.
7. End-of-turn: one sentence to the user naming the ISC turned green this turn (or the blocker if none). That's it.

Respect the modular-reversible-exploratory framing from the existing plan docs — don't ship past a slice's kill criterion just to mark an ISC green. If a slice's keep criterion needs user feedback (e.g. "does the homophone underline read as useful signal or noise?"), the right move is to ship slice A, write a turn report noting "blocked on user keep/kill verdict for slice A", and stop. Don't speculatively build slice B.

Use the headless test driver (scripts/test-overlay.sh) and always-on debug log (~/.talon/prose_overlay_debug.jsonl) to validate behavior end-to-end without the mic. If PROSE_OVERLAY_TEST=1 isn't set on the live Talon, your test-driver-based validation step will be a no-op — note that as a verification gap in the turn report rather than skipping the build.

If the worktree lock at .claude/state/active-dir-locked.json is set from a prior session's agent, release it (`rm -f .claude/state/active-dir-locked.json`) before doing main-tree edits.

Stop conditions:
- All 24 ISCs green → final turn report names "COMPLETE", no more loop fires needed (user manually stops the loop).
- Blocker that requires user input → turn report flags blocker, this fire returns; next fire re-evaluates.
- Unrecoverable error (git conflict you can't resolve, repeated test failures) → turn report flags it, this fire returns.

Do not ask the user for confirmation mid-turn. YOLO mode is implicit for this loop — make the call, ship, document.
```

---

## Notes

- **Interval choice:** 30 min is a guess. Tune up (1h+) if the loop is doing too much; tune down (10–15 min) if it's idling. Each fire consumes context for the ISA re-read and plan-doc scan even if no real work is done, so don't over-frequency.
- **Stopping the loop:** `/loop stop` or whatever the loop skill's stop verb is. The loop also self-stops when the final turn report names "COMPLETE".
- **Auditing progress:** `ls turns/` (locally — gitignored) shows the timeline; `git log --oneline ISA.md` shows the durable progress.
- **If a turn produces no real work** (everything's blocked or already green), the turn report still gets written with a one-line "no actionable ISC this fire" — useful signal that the loop is alive but waiting.
