"""Homophone flag set — Slice A of docs/HOMOPHONE_UI_PLAN.md.

Loads the pimentel homophones CSV from trillium_talon at import time and
exposes pure lookup functions over `str` / `list[str]`. No state, no class,
no buffer coupling — the draw module reads via parameter passing only.

Slice A of docs/PHONES_SPEC.md adds two row-structure helpers:
  - next_in_group(word)            — the next CSV-row member, wrapping
  - current_position_in_group(word) — (active_idx, group_size) in the row
Both read from the same CSV; the loader was extended to retain row
structure (a tuple of tuples) rather than only producing a flat
flagged set.
"""


_CSV_PATH = (
    "/Users/trilliumsmith/.talon/user/trillium_talon/core/homophones/homophones.csv"
)

# Trim characters used when normalising a buffer token before lookup. Mirrors
# ProseBuffer.TRAILING_PUNCT and adds leading-side quotes/brackets.
_STRIP = ".?!,;:)\"'`([{"


def normalize_token(token: str) -> str:
    """Lowercase + strip surrounding punct/quotes — the lookup key form.

    Public so SHIM callers (shim.actions_homophones) can match buffer
    tokens against group members without reaching into the private
    `_normalize` name. Mirrors what is_flagged does internally.
    """
    return token.strip(_STRIP).lower()


# Internal alias kept for backwards compatibility within this module —
# the public name is normalize_token.
_normalize = normalize_token


def _load() -> tuple[frozenset[str], tuple[tuple[str, ...], ...], dict[str, int]]:
    """Read the CSV once at import. Returns:
      flagged set      — every distinct member, lowercased, for is_flagged
      groups tuple     — one tuple-of-words per CSV row, lowercased, preserving
                         the row order so cycling is deterministic
      word -> group_idx — reverse map for O(1) lookup of which row a word lives in.
                          The first occurrence wins on the (rare) case a word
                          appears in multiple rows.
    """
    flagged: set[str] = set()
    groups: list[tuple[str, ...]] = []
    word_to_group: dict[str, int] = {}
    try:
        with open(_CSV_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                row = tuple(
                    cell.strip().lower() for cell in line.split(",") if cell.strip()
                )
                if not row:
                    continue
                gid = len(groups)
                groups.append(row)
                for w in row:
                    flagged.add(w)
                    word_to_group.setdefault(w, gid)
    except (OSError, UnicodeDecodeError) as e:
        print(f"prose_overlay: homophone CSV load failed ({e})")
        return frozenset(), tuple(), {}
    return frozenset(flagged), tuple(groups), word_to_group


_FLAGGED, _GROUPS, _WORD_TO_GROUP = _load()

# Live override toggleable by voice via prose_overlay_set_homophone_hint.
# Read by the draw module instead of (or in addition to) the static
# user.prose_overlay_homophone_hint setting. Talon DOES have a public
# live-setter (`ctx.settings["user.foo"] = value`), but it's context-scoped
# and the value reverts when the owning Context deactivates. This toggle
# wants process-global session semantics (persists across show/hide), so
# a module-level flag is the right tool for THIS toggle specifically.
# Default ON per user keep verdict 2026-06-30 (slice A KEEP). Toggle off
# at runtime via `overlay hints homo off`.
_hint_enabled: bool = True


def set_hint_enabled(v: bool) -> None:
    global _hint_enabled
    _hint_enabled = bool(v)


def hint_enabled() -> bool:
    return _hint_enabled


def is_flagged(token: str) -> bool:
    return _normalize(token) in _FLAGGED


def flagged_indices(tokens: list[str]) -> set[int]:
    return {i for i, t in enumerate(tokens) if is_flagged(t)}


# ---------------------------------------------------------------------------
# Slice A of docs/PHONES_SPEC.md — group-aware helpers
# ---------------------------------------------------------------------------
# next_in_group         — drives the cycling swap (Scenarios 1, 2)
# current_position_in_group — drives the segmented underline (Scenario 3)
# group_for_word        — convenience accessor; the spec lists it but the
#                         two helpers above cover the action surface.
# All three are case-insensitive and normalise surrounding punctuation via
# _normalize, mirroring is_flagged so a token like "There," still resolves.


def _group_index(token: str) -> int | None:
    """Return the CSV-row index that contains `token`, or None if unflagged."""
    return _WORD_TO_GROUP.get(_normalize(token))


def group_id_for_word(token: str) -> int | None:
    """Return a stable canonical group ID for `token`, or None if unflagged.

    The ID is the CSV-row index — stable across calls in a single process
    AND across processes for the same CSV (since the CSV is the source of
    truth). Used by the shape allocator to cluster tokens-in-the-same-group
    so they all wear the same glyph (HOMOPHONE_SHAPES_PLAN §3 Slice 3 /
    ISC-14c) — the user learns the group by its shape, not by per-token
    randomness.
    """
    return _group_index(token)


def group_for_word(token: str) -> tuple[str, ...] | None:
    """Return the tuple of group members for a flagged token (CSV row order)
    or None if the token is not a flagged homophone."""
    gid = _group_index(token)
    if gid is None:
        return None
    return _GROUPS[gid]


def next_in_group(current_word: str) -> str | None:
    """Return the next member of the homophone group after `current_word`,
    wrapping at the end of the row. None if the word is not flagged.

    The CSV-row order is the source of truth (OQ1 default — deterministic
    and matches how the CSV is read today). Two-member groups toggle;
    three-member groups rotate.
    """
    gid = _group_index(current_word)
    if gid is None:
        return None
    row = _GROUPS[gid]
    if len(row) == 1:
        # Degenerate 1-member row — there is no other alt. Per OQ4 the
        # caller treats this as a no-op; we surface the same word back so
        # callers can detect the degeneracy by equality (current == next).
        return row[0]
    key = _normalize(current_word)
    try:
        idx = row.index(key)
    except ValueError:
        # The word is in the flagged set but not in this row — shouldn't
        # happen because _WORD_TO_GROUP was built from this row. Defensive
        # fallback: return the first row member.
        return row[0]
    return row[(idx + 1) % len(row)]


def current_position_in_group(
    current_word: str,
) -> tuple[int, int] | None:
    """Return ``(active_idx, group_size)`` for a flagged word's position in
    its CSV row, or None if the word is not flagged.

    active_idx is 0-indexed; group_size is len(row). Used by the segmented
    underline renderer (docs/PHONES_SPEC.md Scenario 3) to know which
    segment to highlight and how many segments to draw.
    """
    gid = _group_index(current_word)
    if gid is None:
        return None
    row = _GROUPS[gid]
    key = _normalize(current_word)
    try:
        idx = row.index(key)
    except ValueError:
        # Defensive — same case as next_in_group above.
        return (0, len(row))
    return (idx, len(row))
