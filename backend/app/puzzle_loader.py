"""Load puzzle JSON files from data/puzzles/ — cached at first access."""

from __future__ import annotations

import json
import random
from pathlib import Path

from app.models import Puzzle

PUZZLES_DIR = Path(__file__).parent.parent / "data" / "puzzles"

# Module-level cache populated on first call to _get_puzzles()
_cache: dict[str, Puzzle] | None = None


def _get_puzzles() -> dict[str, Puzzle]:
    """Return the puzzle cache, loading from disk if needed."""
    global _cache
    if _cache is None:
        _cache = {}
        for path in sorted(PUZZLES_DIR.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            puzzle = Puzzle.model_validate(data)
            _cache[puzzle.id] = puzzle
    return _cache


def load_puzzle(puzzle_id: str) -> Puzzle:
    """Return puzzle by id. Raises KeyError if not found."""
    puzzles = _get_puzzles()
    if puzzle_id not in puzzles:
        raise KeyError(f"Puzzle not found: {puzzle_id!r}")
    return puzzles[puzzle_id]


def load_all_puzzles() -> list[Puzzle]:
    """Return all puzzles as a list."""
    return list(_get_puzzles().values())


def load_puzzles() -> dict[str, Puzzle]:
    """Return the full puzzle dict (alias for _get_puzzles — public API)."""
    return _get_puzzles()


def random_puzzle() -> Puzzle:
    """Return a randomly selected puzzle."""
    puzzles = load_all_puzzles()
    if not puzzles:
        raise RuntimeError(f"No puzzle JSON files found in {PUZZLES_DIR}")
    return random.choice(puzzles)
