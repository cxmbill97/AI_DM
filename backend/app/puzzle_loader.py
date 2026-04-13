"""Load puzzle and murder mystery script content from the SQLite content database.

The in-memory cache on top of the DB means repeated calls within a server
process cost only a dict lookup.  Call invalidate_*_cache() after any write
so the next read reloads from the DB.
"""

from __future__ import annotations

import random
from pathlib import Path

from app.models import Puzzle, Script
import app.content_db as _db

# ---------------------------------------------------------------------------
# Turtle soup puzzles — per-language cache
# ---------------------------------------------------------------------------

# lang → {puzzle_id: Puzzle}
_cache: dict[str, dict[str, Puzzle]] = {}


def _get_puzzles(lang: str = "zh") -> dict[str, Puzzle]:
    """Return the puzzle cache for *lang*, loading from the DB if needed."""
    if lang not in _cache:
        _cache[lang] = {p.id: p for p in _db.list_puzzles(lang)}
    return _cache[lang]


def load_puzzle(puzzle_id: str, lang: str = "zh") -> Puzzle:
    """Return puzzle by id. Raises KeyError if not found."""
    puzzles = _get_puzzles(lang)
    if puzzle_id not in puzzles:
        raise KeyError(f"Puzzle not found: {puzzle_id!r}")
    return puzzles[puzzle_id]


def load_all_puzzles(lang: str = "zh") -> list[Puzzle]:
    """Return all puzzles for *lang* as a list."""
    return list(_get_puzzles(lang).values())


def load_puzzles(lang: str = "zh") -> dict[str, Puzzle]:
    """Return the full puzzle dict for *lang* (public API)."""
    return _get_puzzles(lang)


def random_puzzle(lang: str = "zh") -> Puzzle:
    """Return a randomly selected puzzle for *lang*."""
    puzzles = load_all_puzzles(lang)
    if not puzzles:
        raise RuntimeError(f"No puzzles found in content.db for lang={lang!r}")
    return random.choice(puzzles)


def save_puzzle(puzzle: Puzzle, lang: str = "zh") -> None:
    """Persist *puzzle* to the DB and invalidate the in-memory cache."""
    _db.upsert_puzzle(puzzle, lang)
    invalidate_puzzle_cache(lang)


# ---------------------------------------------------------------------------
# Murder mystery scripts — per-language cache
# ---------------------------------------------------------------------------

# lang → list[Script]
_script_cache: dict[str, list[Script]] = {}


def _get_scripts(lang: str = "zh") -> list[Script]:
    """Return the script cache for *lang*, loading from the DB if needed."""
    if lang not in _script_cache:
        _script_cache[lang] = _db.list_scripts(lang)
    return _script_cache[lang]


def load_scripts(lang: str = "zh") -> list[Script]:
    """Return all murder mystery scripts for *lang* as a list."""
    return _get_scripts(lang)


def load_script(script_id: str, lang: str = "zh") -> Script:
    """Return a script by id. Raises KeyError if not found."""
    for script in _get_scripts(lang):
        if script.id == script_id:
            return script
    raise KeyError(f"Script not found: {script_id!r}")


def save_script(script: Script, lang: str = "zh") -> None:
    """Persist *script* to the DB and invalidate the in-memory cache."""
    _db.upsert_script(script, lang)
    invalidate_script_cache(lang)


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------


def invalidate_puzzle_cache(lang: str | None = None) -> None:
    """Evict the puzzle cache for *lang* (or all languages if None)."""
    if lang is None:
        _cache.clear()
    else:
        _cache.pop(lang, None)


def invalidate_script_cache(lang: str | None = None) -> None:
    """Evict the script cache for *lang* (or all languages if None).

    After calling this, the next load_scripts() call reloads from the DB,
    picking up any scripts just written by save_script().
    """
    if lang is None:
        _script_cache.clear()
    else:
        _script_cache.pop(lang, None)
