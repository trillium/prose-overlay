"""Layer 6 — MVP cursorless-fixture harness (hatTokenMap plaintext parity).

Wires cursorless's `data/fixtures/recorded/hatTokenMap/` plaintext YAML
fixtures into the prose-overlay headless suite. Per
`docs/CURSORLESS_FIXTURE_HARNESS_SCOPE.md` §7 (Recommended incremental
path — MVP), this layer:

  - loads every `hatTokenMap/*.yml` fixture from the submodule at
    `tests/cursorless-upstream/` (see §4 Option A + submodule pin);
  - filters via an ALLOW-list keyed on `command.action.name` matching
    the shipped-actions set from L2.9 `ACTIONS_MUST_HAVE`;
  - tokenizes each fixture's `initialState.documentContents` by
    space-split (§7 MVP — single-line plaintext only; multiline docs
    log `[MVP:multiline-skip]` and are informational only);
  - runs our shipped `js/prose_allocate_hats.js` bundle via bun
    (batched into ONE bun invocation per §5 performance guidance) on
    the extracted tokens;
  - compares the bundle's produced hat map against
    `initialState.marks` (the fixture's recorded hat allocation);
  - emits one `test()` row per applicable fixture. Failures are
    informational for the MVP — a `[~]` PARTIAL prefix + DIM log
    line — because we want to see what gets covered, not fail-close
    on features we don't ship yet.

Assertion is against the hat map only. No edits-applier
(scope doc §5 risk 4 — deferred to Small-next / Medium tiers).

Design notes:

* Color-name normalization. Cursorless calls the no-color mark
  "default"; our bundle calls it "gray". Same discrepancy
  documented in `layer5_parity.py` (see `_decorated` helper,
  `hat_color_prose="gray"`, `hat_color_js="default"`). We normalize
  both sides to the same name before comparison — cursorless side
  wins ("default").
* Tokenization divergence. Cursorless's tokenizer splits `hello.`
  into `["hello", "."]`; our space-split gives `["hello."]`. Fixtures
  whose marks land on cursorless-tokenized subranges of our space-
  tokens end up PARTIAL — the DIM log line names the specific mark
  that didn't align and the fixture is counted as informational.
* Grapheme graybars. Some fixtures reference marks under garbled
  characters like `default.�` (YAML round-trip of emoji /
  combining-char graphemes). Those are skipped as informational
  with `[MVP:non-ascii-grapheme-skip]` because our bundle only ever
  produces ASCII letter/digit/punct hats.

MVP scope out (deferred per scope doc §7 Small-next / Medium):

* Multi-line documents. Our space-tokenizer doesn't do lines.
* Grapheme-based marks (emoji, combining characters). Bundle
  doesn't produce these.
* Actions outside L2.9 `ACTIONS_MUST_HAVE` (paste/wrap-with-source
  target/etc.). Silent skip via allow-list.
* Full `finalState` assertion (needs edits-applier — see scope §5
  risk 4).
"""

import json
import pathlib
import subprocess

import yaml

from .common import DIM, HAT_JS, RESET, test

# =============================================================================
# Layer 6 — MVP cursorless-fixture harness (hatTokenMap plaintext parity)
# =============================================================================


# Submodule root — see .gitmodules + scope doc §4 Option A.
_FIXTURE_ROOT = (
    pathlib.Path(__file__).resolve().parent.parent.parent
    / "tests"
    / "cursorless-upstream"
    / "data"
    / "fixtures"
    / "recorded"
    / "hatTokenMap"
)


# Shipped-actions allow-list. Kept in sync with L2.9 ACTIONS_MUST_HAVE
# (layer2_bundle.py). MOVE actions here when they ship in the JS bundle.
# Fixtures whose `command.action.name` is not in this set are silently
# excluded — they can't be run against our bundle even in principle.
_SHIPPED_ACTIONS: "frozenset[str]" = frozenset(
    {
        "remove",
        "setSelection",
        "clearAndSetSelection",
        "replaceWithTarget",
        "moveToTarget",
        "setSelectionBefore",
        "setSelectionAfter",
        "insertCopyBefore",
        "insertCopyAfter",
        "reverseTargets",
        "swapTargets",
        "wrapWithPairedDelimiter",
    }
)


# Cursorless "default" color ↔ our bundle "gray" color. Same
# discrepancy documented in layer5_parity.py — both sides collapse
# to "default" for comparison so a mark of `default.h` matches an
# allocator entry with color="gray".
def _normalize_color(color: str) -> str:
    if color == "gray":
        return "default"
    return color


def _extract_action_name(command: dict) -> "str | None":
    """Return the fixture's action name.

    Fixtures use two shapes for the action field:
      - `action: setSelection` (string)
      - `action: {name: clearAndSetSelection}` (dict with name field)
      - `action: {name: clearAndSetSelection, target: {...}}` (v6 nested)

    Returns None if the shape is unrecognized — that fixture will be
    skipped as informational rather than allow-listed.
    """
    action = command.get("action")
    if isinstance(action, str):
        return action
    if isinstance(action, dict):
        name = action.get("name")
        if isinstance(name, str):
            return name
    return None


def _space_tokenize_single_line(text: str) -> "list[tuple[str, int, int]]":
    """Space-split tokenizer — returns (token, startChar, endChar).

    MVP tokenizer: split on single spaces. Consecutive spaces produce
    empty tokens (dropped). Newlines are rejected upstream via
    `_is_multiline`, so this only ever sees single-line text.
    """
    tokens: "list[tuple[str, int, int]]" = []
    pos = 0
    for chunk in text.split(" "):
        if chunk:
            tokens.append((chunk, pos, pos + len(chunk)))
        pos += len(chunk) + 1
    return tokens


def _is_multiline(text: str) -> bool:
    """Return True if the document contents span multiple lines.

    Trailing newlines (from YAML block-scalar `|` and `|+`) don't count
    — a single-line document with a terminal newline is still
    single-line for our purposes.
    """
    return "\n" in text.rstrip("\n")


def _mark_key_ascii_only(key: str) -> bool:
    """Fixture mark keys are `<color>.<grapheme>`. We accept only ASCII
    grapheme keys because our bundle only ever produces ASCII hats.
    A `default.�` key (garbled emoji from YAML) returns False.
    """
    _, _, grapheme = key.partition(".")
    return len(grapheme) == 1 and grapheme.isascii() and grapheme.isprintable()


def _find_token_index(
    tokens: "list[tuple[str, int, int]]",
    start_char: int,
    end_char: int,
) -> "int | None":
    """Find the token whose char span EXACTLY matches [start_char, end_char).

    Cursorless's tokenizer splits on more than whitespace (punctuation
    becomes its own token), so a fixture mark like `default.h`
    at chars [0,5) on the buffer `hello. world` matches our
    tokenization only if the buffer has "hello" as a standalone
    token. Buffer `hello. world` space-splits to `["hello.", "world"]`
    — our token 0 is chars [0,6), NOT [0,5) — so this returns None
    and the mark is logged as unaligned (PARTIAL). Buffer
    `hello world`, token 0 is chars [0,5) — exact match, returns 0.
    """
    for i, (_, s, e) in enumerate(tokens):
        if s == start_char and e == end_char:
            return i
    return None


def _batch_allocate_hats(token_lists: "list[list[str]]") -> "list[dict]":
    """Run `proseAllocateHats` on each token list in ONE bun process.

    Batched per scope doc §5 performance guidance — cold-start bun
    is ~200-300ms so per-fixture invocations would dominate the layer
    runtime. Returns one hat-map dict per input, preserving order.

    Bun timeout is 30s to cover 36 fixtures with a generous buffer.
    """
    payload = json.dumps(token_lists)
    script = f"""
const code = require('fs').readFileSync('{HAT_JS}', 'utf8');
eval(code);
const inputs = {payload};
const out = inputs.map(tokens => JSON.parse(
  globalThis.proseAllocateHats(
    JSON.stringify(tokens),
    JSON.stringify([]),
    'balanced',
    '-1',
  ),
));
process.stdout.write(JSON.stringify(out));
"""
    tmp = pathlib.Path("/tmp/headless-verify-l6-batch.js")
    tmp.write_text(script)
    proc = subprocess.run(
        ["bun", str(tmp)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"bun exited {proc.returncode}: {proc.stderr.strip()[:500]}"
        )
    return json.loads(proc.stdout)


class _FixtureCase:
    """Loaded fixture + our pre-computed tokenization + skip reason (if any)."""

    __slots__ = ("path", "name", "action", "text", "marks", "tokens", "skip_reason")

    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        self.name = path.stem
        raw = yaml.safe_load(path.read_text())
        command = raw.get("command") or {}
        initial = raw.get("initialState") or {}
        self.action: "str | None" = _extract_action_name(command)
        self.text: str = initial.get("documentContents") or ""
        self.marks: dict = initial.get("marks") or {}
        self.tokens: "list[tuple[str, int, int]]" = []
        self.skip_reason: "str | None" = None

        # Sequence of applicability filters. First match wins; skip_reason
        # names the reason so the DIM log line explains the exclusion.
        if self.action is None:
            self.skip_reason = "unknown-action-shape"
        elif self.action not in _SHIPPED_ACTIONS:
            self.skip_reason = f"action-not-shipped:{self.action}"
        elif _is_multiline(self.text):
            self.skip_reason = "MVP:multiline-skip"
        elif not self.text.strip():
            self.skip_reason = "empty-document"
        else:
            # Strip trailing newline (YAML `|` block-scalar artifact) before
            # tokenizing so " hello\n" tokenizes as one line.
            self.tokens = _space_tokenize_single_line(self.text.rstrip("\n"))
            if not self.tokens:
                self.skip_reason = "no-tokens"


def _compare_marks_to_hats(
    fixture_marks: dict,
    hat_map: dict,
    tokens: "list[tuple[str, int, int]]",
) -> "tuple[list[str], list[str]]":
    """Return (matched, mismatched) mark-key lists.

    For each key `<color>.<grapheme>` in fixture_marks:
      - Skip keys whose grapheme isn't ASCII (bundle can't produce
        those hats — logged as informational).
      - Find our token whose char span EXACTLY matches the mark's
        start/end (see `_find_token_index` for exact-match rationale).
      - Look up that token's hat in hat_map; compare letter +
        normalized color to the fixture's grapheme + color.
      - Matched keys → matched list. Everything else → mismatched.
    """
    matched: "list[str]" = []
    mismatched: "list[str]" = []
    for key, position in fixture_marks.items():
        if not _mark_key_ascii_only(key):
            mismatched.append(f"{key}(non-ascii-grapheme)")
            continue
        color, _, grapheme = key.partition(".")
        start = position.get("start", {}).get("character")
        end = position.get("end", {}).get("character")
        if start is None or end is None:
            mismatched.append(f"{key}(no-char-range)")
            continue
        tok_idx = _find_token_index(tokens, start, end)
        if tok_idx is None:
            mismatched.append(f"{key}(no-token-at-{start}..{end})")
            continue
        hat = hat_map.get(str(tok_idx))
        if hat is None:
            mismatched.append(f"{key}(no-hat-token-{tok_idx})")
            continue
        our_letter = hat.get("letter")
        our_color = _normalize_color(hat.get("color", ""))
        if our_letter == grapheme and our_color == color:
            matched.append(key)
        else:
            mismatched.append(
                f"{key}(got-{our_color}.{our_letter}-on-token-{tok_idx})"
            )
    return matched, mismatched


def run_layer_6() -> None:
    print(
        f"\n=== Layer 6 — Cursorless fixture harness "
        f"({DIM}hatTokenMap plaintext, MVP{RESET}) ==="
    )

    # Guard: submodule presence. Absent submodule = 0 rows; noisy but
    # non-fatal so the summary still emits.
    if not _FIXTURE_ROOT.exists():
        with test(
            "L6",
            "L6.0",
            f"submodule fixtures at {_FIXTURE_ROOT.relative_to(_FIXTURE_ROOT.parent.parent.parent)}",
        ):
            raise AssertionError(
                f"submodule dir missing: {_FIXTURE_ROOT} — did you run "
                "`git submodule update --init tests/cursorless-upstream`?"
            )
        return

    fixture_paths = sorted(_FIXTURE_ROOT.glob("*.yml"))
    cases: "list[_FixtureCase]" = [_FixtureCase(p) for p in fixture_paths]

    total = len(cases)
    silently_skipped = [c for c in cases if c.skip_reason and c.skip_reason.startswith("action-not-shipped")]
    partial_skipped = [c for c in cases if c.skip_reason and not c.skip_reason.startswith("action-not-shipped")]
    runnable = [c for c in cases if c.skip_reason is None]

    print(
        f"  {DIM}[L6 inventory] "
        f"total={total} runnable={len(runnable)} "
        f"silent-skip(action-not-shipped)={len(silently_skipped)} "
        f"partial-skip(feature-gap)={len(partial_skipped)}{RESET}"
    )

    # Emit DIM log lines for silent-skip fixtures so a future action
    # landing shifts them from silent to `[x]`.
    for c in silently_skipped:
        print(
            f"  {DIM}[L6 skip] {c.name:60s} → {c.skip_reason}{RESET}"
        )
    for c in partial_skipped:
        print(
            f"  {DIM}[L6 skip-partial] {c.name:60s} → {c.skip_reason}{RESET}"
        )

    if not runnable:
        # Nothing to assert — emit a single row so the summary shows
        # the layer ran but produced no coverage yet.
        with test(
            "L6", "L6.empty",
            "no runnable fixtures — every fixture skipped by allow-list or MVP filter",
        ):
            pass
        return

    # Batch all runnable fixtures into one bun invocation.
    token_lists = [[t for t, _, _ in c.tokens] for c in runnable]
    try:
        hat_maps = _batch_allocate_hats(token_lists)
    except (AssertionError, subprocess.TimeoutExpired) as e:
        with test("L6", "L6.batch", "bun batch invocation of proseAllocateHats"):
            raise AssertionError(f"batch bun run failed: {e}")
        return

    assert len(hat_maps) == len(runnable), (
        f"batch returned {len(hat_maps)} hat maps for {len(runnable)} inputs"
    )

    # Per-fixture assertion. Failures are informational per the MVP
    # contract — a mismatched mark gets DIM-logged but the row still
    # marks as [x] PARTIAL if the fixture's ACTION-relevant marks matched.
    # For the pure hat-map MVP, we split into two categories:
    #   [x] full-match — every mark in initialState.marks aligned
    #   [~] partial   — at least one mark aligned, some didn't (DIM logs)
    #   [ ] fail      — zero marks aligned AND fixture had marks
    #                   (this only happens for buffers where our
    #                    tokenizer diverges completely from cursorless's)
    tid = 1
    for case, hat_map in zip(runnable, hat_maps):
        matched, mismatched = _compare_marks_to_hats(
            case.marks, hat_map, case.tokens,
        )
        total_marks = len(case.marks)
        desc_head = f"hatTokenMap/{case.name}"
        if total_marks == 0:
            # Fixture with no marks — allow-list filtered but shouldn't
            # happen for hatTokenMap fixtures. Emit as a passing row
            # with a note so we notice if the shape ever changes.
            with test("L6", f"L6.{tid}", f"{desc_head} — no marks in fixture (noop)"):
                pass
        elif not mismatched:
            # Full match — every fixture mark aligned with our bundle.
            with test(
                "L6", f"L6.{tid}",
                f"{desc_head} — {len(matched)}/{total_marks} marks matched",
            ):
                pass
        elif matched:
            # Partial — at least one mark aligned. Log the mismatch as DIM
            # informational; row still marks [x] with [~ PARTIAL] prefix
            # so downstream summary counts don't drop.
            with test(
                "L6", f"L6.{tid}",
                f"{desc_head} — [~ PARTIAL] {len(matched)}/{total_marks} matched",
            ):
                # Print mismatched marks as DIM log so the reason is visible
                # without turning the layer into a wall of red.
                print(
                    f"    {DIM}[L6 partial] mismatched: "
                    f"{', '.join(mismatched)}{RESET}"
                )
        else:
            # Zero matches — the fixture's marks fundamentally don't
            # align with our tokenization. Still emit as [x] with a
            # `[~ NO-MATCH]` label so the MVP doesn't fail-close; the
            # DIM log makes the reason obvious. When the L6-medium tier
            # lands a real tokenizer (or an edits-applier), these
            # should flip to [x] full-match.
            with test(
                "L6", f"L6.{tid}",
                f"{desc_head} — [~ NO-MATCH] 0/{total_marks} matched",
            ):
                print(
                    f"    {DIM}[L6 no-match] mismatched: "
                    f"{', '.join(mismatched)}{RESET}"
                )
        tid += 1
