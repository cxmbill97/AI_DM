"""Utilities for safe puzzle serialization (Phase 1, Feature 4).

Strips metadata fields that could let experienced players identify a puzzle
from its source/pack/origin before the game is played.
"""

from __future__ import annotations

# Fields that identify puzzle provenance — strip before sending to clients
_SOURCE_FIELDS: frozenset[str] = frozenset({"source", "origin", "pack", "dataset"})


def safe_puzzle_dict(data: dict) -> dict:
    """Return *data* with provenance fields removed.

    Works on raw dicts (e.g. freshly-loaded JSON before Pydantic validation,
    or the output of puzzle.model_dump()).  Fields not present in *data* are
    silently ignored.
    """
    return {k: v for k, v in data.items() if k not in _SOURCE_FIELDS}
