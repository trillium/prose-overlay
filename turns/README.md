# ISA-loop turn reports

This directory holds ephemeral per-iteration reports written by the
ISA-completion loop. Each turn = one fire of the recurring loop = one
`turns/{N}.md` file where `N` is the next integer (`ls turns/[0-9]*.md
| wc -l` + 1).

**Tracked in git:** `README.md` (this file), `STATEMENT.md` (the prompt
you paste to kick off the loop).
**Gitignored:** `turns/{N}.md` — the per-iteration reports. Durable
progress lives in commits + `ISA.md` checkbox updates; turn files are
the loop's own bookkeeping, not a permanent record.

## Per-turn report format

Each `turns/{N}.md` should capture (the loop prompt enforces this):

```markdown
# Turn {N} — {ISO timestamp}

## Targeted ISC
{e.g. ISC-13: Homophone slice B — `phone <hat>` cycles to next group member}

## Why this one
{one-line: dependency clear, plan exists, blocker absent, etc.}

## What shipped
{commit shas + subject lines, one per line}

## What's still open on this ISC
{nothing, OR specific follow-ups for a later turn}

## Decisions made (if any non-obvious)
{one-liners — these feed the ISA.md Decisions block on the next checkbox flip}

## Blockers (if loop should pause)
{empty if no blocker — loop continues. If non-empty, loop stops until user clears.}

## ISA delta
{which ISC checkboxes were flipped this turn, if any}
```

## Why gitignored

Turn reports are intermediate scratch — the same information lands in
the commit log + ISA.md by the end of each turn. Tracking them would
double-write durable history and add visual noise to `git log --stat`.
The `STATEMENT.md` is tracked because it's the *config* for the loop,
not its output.
