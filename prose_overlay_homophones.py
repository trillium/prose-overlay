"""Homophone flag set — Slice A of docs/HOMOPHONE_UI_PLAN.md.

Loads the pimentel homophones CSV from trillium_talon at import time and
exposes pure lookup functions over `str` / `list[str]`. No state, no class,
no buffer coupling — the draw module reads via parameter passing only.
"""

import os

_CSV_PATH = (
    "/Users/trilliumsmith/.talon/user/trillium_talon/core/homophones/homophones.csv"
)

# Trim characters used when normalising a buffer token before lookup. Mirrors
# ProseBuffer.TRAILING_PUNCT and adds leading-side quotes/brackets.
_STRIP = ".?!,;:)\"'`([{"


def _load() -> frozenset[str]:
    try:
        with open(_CSV_PATH, encoding="utf-8") as f:
            words: set[str] = set()
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                for cell in line.split(","):
                    w = cell.strip().lower()
                    if w:
                        words.add(w)
            return frozenset(words)
    except (OSError, UnicodeDecodeError) as e:
        print(f"prose_overlay: homophone CSV load failed ({e})")
        return frozenset()


_FLAGGED: frozenset[str] = _load()


def is_flagged(token: str) -> bool:
    return token.strip(_STRIP).lower() in _FLAGGED


def flagged_indices(tokens: list[str]) -> set[int]:
    return {i for i, t in enumerate(tokens) if is_flagged(t)}
