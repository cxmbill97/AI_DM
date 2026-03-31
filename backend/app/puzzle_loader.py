"""Load puzzle and murder mystery script JSON files — cached at first access."""

from __future__ import annotations

import json
import random
from pathlib import Path

from app.models import Puzzle, Script

PUZZLES_DIR = Path(__file__).parent.parent / "data" / "puzzles"
SCRIPTS_DIR = Path(__file__).parent.parent / "data" / "scripts"

# ---------------------------------------------------------------------------
# Turtle soup puzzles
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Murder mystery scripts (Phase 4)
# ---------------------------------------------------------------------------

# Module-level cache for scripts
_script_cache: list[Script] | None = None


def _get_scripts() -> list[Script]:
    """Return the script cache, loading from disk if needed."""
    global _script_cache
    if _script_cache is None:
        _script_cache = []
        if SCRIPTS_DIR.exists():
            for path in sorted(SCRIPTS_DIR.glob("*.json")):
                data = json.loads(path.read_text(encoding="utf-8"))
                script = Script.model_validate(data)
                _script_cache.append(script)
    return _script_cache


def load_scripts() -> list[Script]:
    """Return all murder mystery scripts as a list."""
    return _get_scripts()


def load_script(script_id: str) -> Script:
    """Return a script by id. Raises KeyError if not found."""
    for script in _get_scripts():
        if script.id == script_id:
            return script
    raise KeyError(f"Script not found: {script_id!r}")
