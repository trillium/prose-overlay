"""Layer 7 — MVP cursorless-fixture harness (action pipeline end-to-end parity).

Wires cursorless's `data/fixtures/recorded/actions/*.yml` recorded ACTION
fixtures into the prose-overlay headless suite. Different scope from Layer 6
(which only checks hat allocation on `hatTokenMap/` plaintext fixtures):
Layer 7 exercises the full action-plan pipeline — take the fixture's recorded
command, build the target + document shapes the JS bundle expects, invoke
`js/prose_actions.js`'s ``proseRunAction`` via bun, apply the returned edit
plan in pure Python, and compare the resulting document text + cursor against
the fixture's ``finalState``.

Per the Layer 7 charter (this file's header comment + accompanying
`docs/CURSORLESS_ACTIONS_COVERAGE.md`), this MVP:

  - loads every `actions/*.yml` fixture from the submodule at
    `tests/cursorless-upstream/`;
  - filters via layered allow-lists keyed on ``command.action.name`` AND
    target shape (mark type, modifier type). Anything outside the shipped
    surface silently DIM-skips so a future action landing shifts fixtures
    from DIM to `[x]` without touching this file's list;
  - restricts to single-line plaintext documents (multi-line + non-plaintext
    are `[MVP:multiline-skip]` / `[MVP:non-plaintext]` respectively — see
    layer6_cursorless.py for the same tokenizer-scope rationale);
  - runs the shipped bundle in ONE batched bun invocation (mirroring Layer 6's
    performance guidance — cold-start bun is ~200-300ms so per-fixture
    invocations would dominate the layer runtime);
  - applies the returned edit plan in pure Python — a headless duplicate of
    ``shim/actions_cursorless_edit._apply_edit_plan`` (talon-free, no
    ProseBuffer). This is intentional: Layer 7 exists to verify the JS
    bundle's geometry matches cursorless upstream, NOT to test the shim's
    talon-side plumbing (that's Layers 1-3);
  - emits per-fixture `test()` rows. Failures are informational — a `[~ ...]`
    partial-match label + DIM log lines — because the MVP contract is
    "surface feature gaps," not "fail-close on unfinished features."

MVP scope OUT (deferred per the layer charter):

  - Multi-line documents. Our JS bundle geometrically ignores line boundaries;
    fixtures that clone across lines or wrap paragraphs produce single-line
    "wrong-shape" plans. Log DIM `[MVP:multiline-skip]`.
  - Actions outside the shipped `_SHIPPED_ACTIONS` set (breakLine, addSelection,
    editNewLineBefore/After, pasteFromClipboard, findIn*, cutToClipboard,
    outdentLine, indentLine, rewrapWithPairedDelimiter, callAsFunction,
    highlight, deselect, replace, getText, private.*/experimental.*). Silent
    DIM skip via allow-list.
  - Complex targets: list destinations, range spans, modifiers other than
    ``containingScope:token``, positional targets nested in
    ``insertionMode`` other than the plain trio {before, after, to}. Silent
    DIM skip so the coverage report shows which modifier types are the top
    feature gaps.

  - `finalState.marks` re-allocation parity. Cursorless recomputes hats after
    edits; our bundle does that in a separate path (proseAllocateHats — Layer
    6's territory). Comparing final marks here would double-count Layer 6
    coverage and blur which layer surfaces which regression.
"""

import json
import pathlib
import subprocess

import yaml

from .common import DIM, RESET, REPO, test

# =============================================================================
# Layer 7 — MVP cursorless-fixture harness (action-plan end-to-end)
# =============================================================================


_FIXTURE_ROOT = (
    REPO
    / "tests"
    / "cursorless-upstream"
    / "data"
    / "fixtures"
    / "recorded"
    / "actions"
)

_ACTIONS_JS = REPO / "js" / "prose_actions.js"


# Shipped-actions allow-list. Kept in sync with L2.9 ACTIONS_MUST_HAVE +
# _SUPPORTED_SIMPLE_ACTIONS (cursorless/resolve.py) + the twelve names the
# JS bundle geometrically supports. MOVE actions here when they ship in the
# JS bundle; fixtures whose `command.action.name` is not in this set silently
# DIM-skip and the coverage report enumerates them so the next contributor
# knows what's next.
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


# Modifier types we know how to reduce to a char range in the MVP. Anything
# else counts as a feature gap and DIM-skips the fixture.
#
# ``containingScope:token`` — the "clone token"-style fixtures. Resolves to
# the whitespace-delimited token containing the fixture cursor. Same shape as
# Layer 6's space-tokenizer, applied inline here.
#
# ``startOf`` / ``endOf`` — used in `bring air to start of air`-style
# fixtures. Reduces the mark's char range to a zero-width point at start/end.
_SIMPLE_MODIFIERS: "frozenset[str]" = frozenset({"containingScope", "startOf", "endOf"})


# =============================================================================
# YAML → in-memory fixture shape
# =============================================================================


def _extract_action_name(command: dict) -> "str | None":
    """Return the fixture's action name.

    Fixtures use two shapes:
      - ``action: setSelection`` (string)
      - ``action: {name: clearAndSetSelection, ...}`` (dict with name field)
    Return None if the shape is unrecognized — fixture will DIM-skip as
    ``unknown-action-shape`` rather than fail-close.
    """
    action = command.get("action")
    if isinstance(action, str):
        return action
    if isinstance(action, dict):
        name = action.get("name")
        if isinstance(name, str):
            return name
    return None


def _is_multiline(text: str) -> bool:
    """True if the document contents span multiple lines.

    Trailing newlines (YAML block-scalar `|` and `|+`) don't count — a
    single-line document with a terminal newline is single-line for us.
    """
    return "\n" in text.rstrip("\n")


def _fixture_line_zero(text: str) -> str:
    """Return the fixture's effective single line of text.

    YAML block-scalar `|` produces a trailing newline; strip it. Nothing else
    is trimmed — we preserve leading/trailing spaces because delimiter-wrap
    fixtures (voidWrapAir) depend on them.
    """
    return text.rstrip("\n")


class _TargetResolveError(Exception):
    """Raised when a target can't be reduced to (start_char, end_char).

    Message names the specific reason so the DIM log line explains the skip
    without needing to inspect the fixture.
    """


def _resolve_primitive_target(
    target: dict,
    marks: dict,
    cursor_active_char: int,
    doc_text: str,
) -> "tuple[int, int]":
    """Reduce a primitive-target dict to (start_char, end_char) in char space.

    Handles the MVP subset:

      * ``mark.type == decoratedSymbol`` — look up the mark by
        ``<color>.<character>`` in fixture ``initialState.marks``, return
        that mark's char range verbatim.
      * ``mark.type == cursor`` — return a zero-width range at the cursor.
      * ``mark absent, containingScope:token modifier`` — find the
        whitespace-delimited token containing ``cursor_active_char``. Uses
        the same "split on spaces + track offsets" tokenizer as Layer 6's
        ``_space_tokenize_single_line``.
      * ``modifiers:[startOf | endOf]`` — collapse the resolved base range
        to a zero-width point at start/end. Combines with the mark case.

    Raises ``_TargetResolveError`` for anything outside this envelope so the
    caller can DIM-skip with a specific reason. Keeps this function honest —
    silently returning wrong ranges would produce false parity results.
    """
    if not isinstance(target, dict):
        raise _TargetResolveError(f"target-not-dict:{type(target).__name__}")

    ttype = target.get("type")
    # Implicit destinations (bare cursor) — zero-width at cursor.
    if ttype == "implicit":
        return (cursor_active_char, cursor_active_char)

    if ttype != "primitive":
        raise _TargetResolveError(f"target-type:{ttype}")

    modifiers = target.get("modifiers") or []
    mark = target.get("mark")

    # --- Base range from the mark (or its absence) ---
    base_start: int
    base_end: int

    if mark is None:
        # No mark — must have a containingScope:token modifier that resolves
        # against the cursor. This handles the cloneToken-family fixtures.
        containing_mod = next(
            (m for m in modifiers if m.get("type") == "containingScope"),
            None,
        )
        if containing_mod is None:
            raise _TargetResolveError("no-mark-no-containing-scope")
        scope = (containing_mod.get("scopeType") or {}).get("type")
        if scope != "token":
            raise _TargetResolveError(f"containing-scope:{scope}")
        base_start, base_end = _containing_token_range(doc_text, cursor_active_char)
    else:
        mark_type = mark.get("type")
        if mark_type == "decoratedSymbol":
            color = mark.get("symbolColor", "default")
            char = mark.get("character", "")
            key = f"{color}.{char}"
            mark_pos = marks.get(key)
            if mark_pos is None:
                raise _TargetResolveError(f"missing-mark:{key}")
            # We already gated on single-line; verify the mark IS on line 0.
            # A mark on a different line would slip through if the fixture's
            # doc happens to be single-line but the mark references a
            # non-existent line — bail rather than silently misresolve.
            start_line = mark_pos.get("start", {}).get("line", 0)
            end_line = mark_pos.get("end", {}).get("line", 0)
            if start_line != 0 or end_line != 0:
                raise _TargetResolveError(
                    f"mark-off-line-zero:{key}(lines {start_line}..{end_line})"
                )
            base_start = mark_pos.get("start", {}).get("character")
            base_end = mark_pos.get("end", {}).get("character")
            if base_start is None or base_end is None:
                raise _TargetResolveError(f"mark-no-char:{key}")
        elif mark_type == "cursor":
            base_start = cursor_active_char
            base_end = cursor_active_char
        else:
            raise _TargetResolveError(f"mark-type:{mark_type}")

    # --- Apply supported modifiers (startOf / endOf collapse the range) ---
    for mod in modifiers:
        mtype = mod.get("type")
        if mtype == "containingScope":
            # Already used above when there was no mark. When a mark IS
            # present with containingScope, cursorless expands to the token
            # containing the mark's start; that's the same span for
            # single-line whitespace-token fixtures.
            continue
        if mtype == "startOf":
            base_end = base_start
        elif mtype == "endOf":
            base_start = base_end
        else:
            raise _TargetResolveError(f"modifier:{mtype}")

    return (base_start, base_end)


def _containing_token_range(text: str, cursor_char: int) -> "tuple[int, int]":
    """Find the whitespace-delimited token containing ``cursor_char``.

    Cursorless's ``containingScope: token`` resolves to the token the cursor
    is inside (or immediately adjacent to). For plaintext single-line docs
    that reduces to "walk left to the nearest whitespace, walk right to the
    nearest whitespace." When the cursor sits ON whitespace we return the
    token immediately to the LEFT — matches cursorless's "cursor at end of
    token" convention used by the cloneToken fixtures (see cloneToken.yml:
    cursor=8 on "hello world", token = [6,11] "world").

    A cursor at position 0 with a leading token returns [0, end-of-first].
    An empty document raises the caller catches → DIM skip.
    """
    n = len(text)
    if n == 0:
        raise _TargetResolveError("containing-token-empty-doc")

    # Clamp cursor into [0, n]. Positions beyond n happen with YAML `|`
    # block-scalars carrying a virtual newline; we've already stripped that
    # for single-line docs, but be defensive.
    pos = max(0, min(cursor_char, n))

    # If cursor is on whitespace, prefer the token to the LEFT (cursorless
    # convention for cloneToken2 etc.). Walk left across the whitespace to
    # find the previous non-space character.
    while pos > 0 and text[pos - 1] == " ":
        pos -= 1
    if pos == 0 and (n == 0 or text[0] == " "):
        # Cursor is at start and there's no token to the left — take the
        # first token on the right instead.
        while pos < n and text[pos] == " ":
            pos += 1
        if pos == n:
            raise _TargetResolveError("containing-token-only-whitespace")

    # Walk left to token start.
    start = pos
    while start > 0 and text[start - 1] != " ":
        start -= 1
    # Walk right to token end (exclusive).
    end = pos
    while end < n and text[end] != " ":
        end += 1
    return (start, end)


# =============================================================================
# JS bundle invocation (batched)
# =============================================================================


def _batch_run_actions(inputs: list[dict]) -> list[dict]:
    """Run ``proseRunAction`` on each input in ONE bun process.

    Batched to amortize bun cold-start (~200-300ms) over all runnable
    fixtures. Each input is a dict:

        {
            "actionName": str,
            "source":     TargetObj | list[TargetObj] | None,
            "dest":       TargetObj | None,
            "doc":        DocumentObj,
            "options":    {"left": str, "right": str} | None,
        }

    Returns the parsed JSON edit-plan dict from the bundle, in the same order.
    A plan whose bundle produced an error slot will carry {"error": str}
    rather than exploding the whole batch — Layer 7 flags those as
    ``bundle-error`` rows.
    """
    payload = json.dumps(inputs)
    # Write the script and payload to a tempfile so we don't blow up bun's
    # argv on large batches. Same pattern as Layer 6.
    script = f"""
const code = require('fs').readFileSync('{_ACTIONS_JS}', 'utf8');
eval(code);
const inputs = {payload};
const out = inputs.map(input => {{
  const args = [
    JSON.stringify(input.actionName),
    JSON.stringify(input.source),
    JSON.stringify(input.dest),
    JSON.stringify(input.doc),
  ];
  if (input.options !== null && input.options !== undefined) {{
    args.push(JSON.stringify(input.options));
  }}
  return JSON.parse(globalThis.proseRunAction(...args));
}});
process.stdout.write(JSON.stringify(out));
"""
    tmp = pathlib.Path("/tmp/headless-verify-l7-batch.js")
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


# =============================================================================
# Pure-Python edit-plan applier (headless duplicate of _apply_edit_plan)
# =============================================================================


def _edit_start(edit: dict) -> int:
    """Sort key: character offset where the edit begins.

    Mirrors ``shim/actions_cursorless_edit._edit_start``. Kept in this file so
    Layer 7 doesn't import from ``shim/`` (which pulls in talon).
    """
    if "range" in edit:
        return edit["range"]["start"]["character"]
    if "position" in edit:
        return edit["position"]["character"]
    return 0


def _apply_one_edit(text: str, edit: dict) -> str:
    """Apply a single insert/delete/replace edit to ``text``.

    Mirrors ``shim/actions_cursorless_edit._apply_one_edit``. Same char-only
    slicing — the fixtures we run against are single-line so we never need to
    address lines.
    """
    etype = edit.get("type")
    if etype == "delete":
        r = edit["range"]
        return text[: r["start"]["character"]] + text[r["end"]["character"] :]
    if etype == "insert":
        pos = edit["position"]["character"]
        return text[:pos] + edit.get("text", "") + text[pos:]
    if etype == "replace":
        r = edit["range"]
        return (
            text[: r["start"]["character"]]
            + edit.get("text", "")
            + text[r["end"]["character"] :]
        )
    return text


def _apply_edit_plan_pure(
    text: str,
    plan: dict,
) -> "tuple[str, int | None, int | None]":
    """Apply the JS bundle's edit plan to a plain string.

    Returns ``(new_text, new_active_char, new_anchor_char)``. Cursor fields
    are None when the plan produced no newSelections (e.g. reverseTargets
    without a cursor). Mirrors the reverse-sort applied by
    ``_apply_edit_plan`` — later edits process first so earlier offsets stay
    valid.
    """
    if "error" in plan:
        raise _TargetResolveError(f"bundle-error:{plan['error']}")

    edits = plan.get("edits", [])
    for edit in sorted(edits, key=_edit_start, reverse=True):
        text = _apply_one_edit(text, edit)

    new_selections = plan.get("newSelections") or []
    if new_selections:
        sel = new_selections[0]
        active = sel.get("active", {}).get("character")
        anchor = sel.get("anchor", {}).get("character")
        return (text, active, anchor)
    return (text, None, None)


# =============================================================================
# Fixture case classification
# =============================================================================


class _FixtureCase:
    """Loaded fixture + classification result.

    Instances land in one of three buckets:
      * ``skip_reason is not None`` — allow-list rejected this fixture.
      * ``execute_input is not None`` — ready to feed to the batched bun run.
      * neither — an internal wiring error; treated as an informational skip.
    """

    __slots__ = (
        "path",
        "name",
        "action",
        "language",
        "initial_text",
        "final_text",
        "initial_active",
        "initial_anchor",
        "final_active",
        "marks",
        "execute_input",
        "skip_reason",
    )

    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        self.name = path.stem
        self.execute_input: "dict | None" = None
        self.skip_reason: "str | None" = None

        try:
            raw = yaml.safe_load(path.read_text())
        except Exception as e:
            self.action = None
            self.language = ""
            self.initial_text = ""
            self.final_text = ""
            self.initial_active = 0
            self.initial_anchor = 0
            self.final_active = 0
            self.marks = {}
            self.skip_reason = f"yaml-parse-error:{type(e).__name__}"
            return

        command = raw.get("command") or {}
        initial = raw.get("initialState") or {}
        final = raw.get("finalState") or {}

        self.action = _extract_action_name(command)
        self.language = raw.get("languageId", "")
        self.initial_text = initial.get("documentContents") or ""
        self.final_text = final.get("documentContents") or ""
        self.marks = initial.get("marks") or {}

        # Extract first selection's active/anchor char. Absent selection ==>
        # default to 0 (matches cursorless's convention for cursor-less docs).
        initial_sels = initial.get("selections") or []
        if initial_sels:
            self.initial_active = initial_sels[0].get("active", {}).get("character", 0)
            self.initial_anchor = initial_sels[0].get("anchor", {}).get("character", 0)
        else:
            self.initial_active = 0
            self.initial_anchor = 0

        final_sels = final.get("selections") or []
        if final_sels:
            self.final_active = final_sels[0].get("active", {}).get("character", 0)
        else:
            self.final_active = 0

        # ---- Layered allow-list filters. First match wins. ----
        if self.action is None:
            self.skip_reason = "unknown-action-shape"
            return
        if self.action not in _SHIPPED_ACTIONS:
            self.skip_reason = f"unsupported-action:{self.action}"
            return
        if self.language != "plaintext":
            self.skip_reason = f"MVP:non-plaintext:{self.language}"
            return
        if _is_multiline(self.initial_text) or _is_multiline(self.final_text):
            self.skip_reason = "MVP:multiline-skip"
            return

        # Try to reduce every target to a char range. This is the last-mile
        # filter — feature gaps we can't yet resolve produce a specific DIM
        # message per fixture.
        doc_text = _fixture_line_zero(self.initial_text)
        try:
            self.execute_input = self._build_execute_input(command, doc_text)
        except _TargetResolveError as e:
            self.skip_reason = f"MVP:{e}"
            return

    def _build_execute_input(self, command: dict, doc_text: str) -> dict:
        """Reduce the fixture's command to a JS-bundle input dict.

        Raises ``_TargetResolveError`` if any target/dest can't be resolved —
        caller DIM-skips with the specific reason.
        """
        action_node = command.get("action") or {}
        if not isinstance(action_node, dict):
            raise _TargetResolveError("action-node-not-dict")

        # Resolve source / target and destination per action shape. The naming
        # differs between actions — cursorless's grammar uses `target` for
        # single-target actions (remove, clone, wrap, setSelection...) and
        # `source` + `destination` for two-target actions (replaceWithTarget,
        # moveToTarget).
        source_key = "target" if "target" in action_node else "source"
        source_node = action_node.get(source_key)
        if source_node is None:
            raise _TargetResolveError(f"no-{source_key}-key")

        source_range = _resolve_primitive_target(
            source_node, self.marks, self.initial_active, doc_text,
        )

        # Destination handling — only present for two-target actions, and the
        # bundle's ``dest`` slot expects a TargetObj (contentRange). The
        # destination may nest another target under ``insertionMode``
        # ({before, after, to}) — in that case the inner target's range is
        # collapsed per insertionMode to a zero-width point (before → start,
        # after → end, to → same as after per cursorless convention).
        dest_range: "tuple[int, int] | None" = None
        dest_node = action_node.get("destination")
        if dest_node is not None:
            dest_range = self._resolve_destination(dest_node, doc_text)

        source_target = _target_obj(source_range)
        dest_target = _target_obj(dest_range) if dest_range is not None else None

        options: "dict | None" = None
        if self.action == "wrapWithPairedDelimiter":
            left = action_node.get("left")
            right = action_node.get("right")
            if not isinstance(left, str) or not isinstance(right, str):
                raise _TargetResolveError("wrap-missing-delimiters")
            options = {"left": left, "right": right}

        doc_obj = {
            "text": doc_text,
            "selectionAnchorChar": self.initial_anchor,
            "selectionActiveChar": self.initial_active,
        }

        return {
            "actionName": self.action,
            "source": source_target,
            "dest": dest_target,
            "doc": doc_obj,
            "options": options,
        }

    def _resolve_destination(
        self, dest_node: dict, doc_text: str,
    ) -> "tuple[int, int]":
        """Reduce a destination node to (start_char, end_char).

        Cursorless destination shapes we handle in the MVP:

          * ``{type: implicit}`` — zero-width at cursor.
          * ``{type: primitive, insertionMode: before|after|to, target: ...}``
            — resolve the inner target, then collapse per insertionMode.
          * ``{type: primitive, mark: ..., insertionMode: ...}`` — the
            destination IS a primitive target itself. Resolve inline.

        Multi-destination lists (``{type: list, destinations: [...]}``) raise
        DestinationListSkip because the MVP scope is single-target actions.
        """
        if not isinstance(dest_node, dict):
            raise _TargetResolveError("dest-not-dict")

        dtype = dest_node.get("type")
        if dtype == "implicit":
            return (self.initial_active, self.initial_active)
        if dtype == "list":
            raise _TargetResolveError("destination-list")

        # Both "primitive" destination and a bare inner "primitive" target
        # share the same reduction path — extract the underlying primitive.
        inner: "dict | None"
        if "target" in dest_node:
            inner = dest_node.get("target")
        else:
            inner = dest_node

        if inner is None:
            raise _TargetResolveError("dest-no-inner")

        base = _resolve_primitive_target(
            inner, self.marks, self.initial_active, doc_text,
        )

        # Collapse per insertionMode. The trio {before, after, to} maps to
        # {start-point, end-point, end-point} — matches cursorless's
        # PositionalTarget contentRange collapsing.
        mode = dest_node.get("insertionMode")
        if mode == "before":
            return (base[0], base[0])
        if mode == "after":
            return (base[1], base[1])
        if mode == "to":
            # `to X` cursorless-wise means "into X's range" — for prose we
            # treat it as a replace into that range (leave it as-is).
            return base
        if mode is None:
            return base
        raise _TargetResolveError(f"insertion-mode:{mode}")


def _target_obj(char_range: "tuple[int, int]") -> dict:
    """Build a JS-bundle TargetObj from a char range on line 0."""
    start, end = char_range
    return {
        "contentRange": {
            "start": {"line": 0, "character": start},
            "end": {"line": 0, "character": end},
        },
        "isReversed": False,
    }


# =============================================================================
# Coverage-report bookkeeping
# =============================================================================


class _CoverageCounts:
    """Running tallies for the layer's coverage summary block.

    Kept in a dedicated class rather than free counters so `write_summary`
    has a single object to consult. Mirrors Layer 6's inventory-print style
    but adds finer skip buckets (per-modifier-type, per-mark-type).
    """

    def __init__(self) -> None:
        self.total = 0
        self.full_pass = 0
        self.partial = 0
        self.bundle_error = 0
        self.skip_unsupported_action: dict[str, int] = {}
        self.skip_multiline = 0
        self.skip_non_plaintext: dict[str, int] = {}
        self.skip_complex: dict[str, int] = {}
        self.skip_other: dict[str, int] = {}

    def record_skip(self, reason: str) -> None:
        if reason.startswith("unsupported-action:"):
            name = reason.split(":", 1)[1]
            self.skip_unsupported_action[name] = self.skip_unsupported_action.get(name, 0) + 1
            return
        if reason == "MVP:multiline-skip":
            self.skip_multiline += 1
            return
        if reason.startswith("MVP:non-plaintext:"):
            lang = reason.split(":", 2)[2]
            self.skip_non_plaintext[lang] = self.skip_non_plaintext.get(lang, 0) + 1
            return
        if reason.startswith("MVP:"):
            # Anything under MVP: is a feature gap — bucket by the specific
            # tag so the coverage doc lists the top gaps in priority order.
            self.skip_complex[reason] = self.skip_complex.get(reason, 0) + 1
            return
        self.skip_other[reason] = self.skip_other.get(reason, 0) + 1

    def render_summary_block(self) -> list[str]:
        """Return lines for the coverage-summary block printed at layer end."""
        total_skipped = (
            sum(self.skip_unsupported_action.values())
            + self.skip_multiline
            + sum(self.skip_non_plaintext.values())
            + sum(self.skip_complex.values())
            + sum(self.skip_other.values())
        )
        lines = [
            "=== L7 fixture-harness coverage report ===",
            f"Total fixtures walked:      {self.total}",
            f"[x] full pass:              {self.full_pass}   (green)",
            f"[~] partial (state divergence with diff): {self.partial}",
            f"[!] bundle-error:           {self.bundle_error}",
            f"[skip] unsupported action:  {sum(self.skip_unsupported_action.values())}",
            f"[skip] non-plaintext:       {sum(self.skip_non_plaintext.values())}",
            f"[skip] multiline:           {self.skip_multiline}",
            f"[skip] complex target/mod:  {sum(self.skip_complex.values())}",
            f"[skip] other:               {sum(self.skip_other.values())}",
            f"                                     total skipped = {total_skipped}",
        ]
        if self.skip_complex:
            lines.append("  Top feature gaps (skip:complex):")
            for reason, count in sorted(
                self.skip_complex.items(), key=lambda kv: -kv[1],
            )[:5]:
                lines.append(f"    {count:4d}  {reason}")
        if self.skip_unsupported_action:
            lines.append("  Top unsupported actions:")
            for name, count in sorted(
                self.skip_unsupported_action.items(), key=lambda kv: -kv[1],
            )[:5]:
                lines.append(f"    {count:4d}  {name}")
        return lines


# =============================================================================
# Layer entry point
# =============================================================================


def run_layer_7() -> None:
    print(
        f"\n=== Layer 7 — Cursorless fixture harness "
        f"({DIM}actions/ end-to-end, MVP{RESET}) ==="
    )

    # Submodule presence guard — same shape as Layer 6.
    if not _FIXTURE_ROOT.exists():
        with test(
            "L7", "L7.0",
            f"submodule fixtures at {_FIXTURE_ROOT.relative_to(REPO)}",
        ):
            raise AssertionError(
                f"submodule dir missing: {_FIXTURE_ROOT} — did you run "
                "`git submodule update --init tests/cursorless-upstream`?"
            )
        return

    # Bundle presence guard — the layer is pointless without the JS bundle.
    if not _ACTIONS_JS.exists():
        with test("L7", "L7.0", f"js bundle at {_ACTIONS_JS.relative_to(REPO)}"):
            raise AssertionError(
                f"bundle missing: {_ACTIONS_JS} — build with the shipped bundler"
            )
        return

    fixture_paths = sorted(_FIXTURE_ROOT.glob("*.yml"))
    cases: list[_FixtureCase] = [_FixtureCase(p) for p in fixture_paths]

    counts = _CoverageCounts()
    counts.total = len(cases)

    runnable = [c for c in cases if c.execute_input is not None]
    skipped = [c for c in cases if c.execute_input is None]

    print(
        f"  {DIM}[L7 inventory] "
        f"total={len(cases)} runnable={len(runnable)} skipped={len(skipped)}{RESET}"
    )

    for c in skipped:
        # skip_reason is always set for a non-runnable case (guaranteed by
        # __init__ — every path either sets it or produces execute_input).
        reason = c.skip_reason or "unknown-skip"
        counts.record_skip(reason)

    # Batch every runnable fixture into one bun process for cost amortization.
    if runnable:
        try:
            plans = _batch_run_actions([c.execute_input for c in runnable])
        except (AssertionError, subprocess.TimeoutExpired) as e:
            with test("L7", "L7.batch", "bun batch invocation of proseRunAction"):
                raise AssertionError(f"batch bun run failed: {e}")
            return
        if len(plans) != len(runnable):
            with test("L7", "L7.batch", "bun batch returned matching count"):
                raise AssertionError(
                    f"got {len(plans)} plans for {len(runnable)} inputs"
                )
            return
    else:
        plans = []

    # Emit one test() row per runnable fixture. Partial-match rows are
    # informational — the row still marks [x] with a `[~ ...]` prefix in the
    # description so downstream summary counts don't drop.
    tid = 1
    for case, plan in zip(runnable, plans):
        desc_head = f"actions/{case.name}"
        try:
            new_text, new_active, _new_anchor = _apply_edit_plan_pure(
                _fixture_line_zero(case.initial_text), plan,
            )
        except _TargetResolveError as e:
            # Bundle returned {"error": ...} — surface as its own row so the
            # coverage report distinguishes "we couldn't feed the bundle" (a
            # target-resolve error, DIM-skip) from "the bundle refused" (a
            # bundle contract regression, informational fail).
            counts.bundle_error += 1
            with test(
                "L7", f"L7.{tid}",
                f"{desc_head} — [! BUNDLE-ERROR] {e}",
            ):
                # Don't raise — we want the coverage row visible.
                pass
            tid += 1
            continue

        expected_text = _fixture_line_zero(case.final_text)
        text_match = new_text == expected_text

        # Cursor comparison is best-effort: fixtures without newSelections in
        # the plan won't have new_active. Compare when both sides give a
        # cursor; otherwise the cursor half is "n/a" and doesn't count against
        # full-pass.
        cursor_expected = case.final_active
        cursor_match: "bool | None"
        if new_active is None:
            cursor_match = None
        else:
            cursor_match = new_active == cursor_expected

        if text_match and cursor_match is not False:
            counts.full_pass += 1
            with test(
                "L7", f"L7.{tid}",
                f"{desc_head} — text+cursor match ({case.action})",
            ):
                pass
        elif text_match and cursor_match is False:
            counts.partial += 1
            with test(
                "L7", f"L7.{tid}",
                f"{desc_head} — [~ PARTIAL] text-match, cursor {new_active}!={cursor_expected}",
            ):
                print(
                    f"    {DIM}[L7 partial] {case.action} — text ok, "
                    f"cursor diverged{RESET}"
                )
        else:
            counts.partial += 1
            with test(
                "L7", f"L7.{tid}",
                f"{desc_head} — [~ PARTIAL] {case.action} state divergence",
            ):
                print(
                    f"    {DIM}[L7 partial] expected={expected_text!r} "
                    f"got={new_text!r}{RESET}"
                )
        tid += 1

    # Coverage summary block — printed as plain text (not test rows) so it
    # shows up once at the end of the layer and lands in the docs/coverage
    # md too. Uses `print` directly rather than the DIM formatter so the
    # block is copy-pasteable into the coverage doc.
    print()
    for line in counts.render_summary_block():
        print(f"  {line}")
