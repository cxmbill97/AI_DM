"""Load puzzle and murder mystery script JSON files — cached at first access."""

from __future__ import annotations

import json
import random
from pathlib import Path

from app.models import Puzzle, Script

PUZZLES_DIR = Path(__file__).parent.parent / "data" / "puzzles"
SCRIPTS_DIR = Path(__file__).parent.parent / "data" / "scripts"

# ---------------------------------------------------------------------------
# Turtle soup puzzles — per-language cache
# ---------------------------------------------------------------------------

# lang → {puzzle_id: Puzzle}
_cache: dict[str, dict[str, Puzzle]] = {}


def _get_puzzles(lang: str = "zh") -> dict[str, Puzzle]:
    """Return the puzzle cache for *lang*, loading from disk if needed."""
    if lang not in _cache:
        _cache[lang] = {}
        lang_dir = PUZZLES_DIR / lang
        if lang_dir.exists():
            for path in sorted(lang_dir.glob("*.json")):
                data = json.loads(path.read_text(encoding="utf-8"))
                puzzle = Puzzle.model_validate(data)
                _cache[lang][puzzle.id] = puzzle
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
        raise RuntimeError(f"No puzzle JSON files found in {PUZZLES_DIR / lang}")
    return random.choice(puzzles)


# ---------------------------------------------------------------------------
# Murder mystery scripts — per-language cache (Phase 4)
# ---------------------------------------------------------------------------

# lang → list[Script]
_script_cache: dict[str, list[Script]] = {}


def _get_scripts(lang: str = "zh") -> list[Script]:
    """Return the script cache for *lang*, loading from disk if needed."""
    if lang not in _script_cache:
        _script_cache[lang] = []
        lang_dir = SCRIPTS_DIR / lang
        if lang_dir.exists():
            for path in sorted(lang_dir.glob("*.json")):
                data = json.loads(path.read_text(encoding="utf-8"))
                script = Script.model_validate(data)
                _script_cache[lang].append(script)
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


def save_script(script: Script, lang: str = "zh") -> Path:
    """Persist *script* as JSON in data/scripts/{lang}/{script.id}.json.

    Creates the language subdirectory if it does not exist.
    Returns the path written.
    """
    lang_dir = SCRIPTS_DIR / lang
    lang_dir.mkdir(parents=True, exist_ok=True)
    path = lang_dir / f"{script.id}.json"
    path.write_text(script.model_dump_json(indent=2), encoding="utf-8")
    return path


def save_puzzle(puzzle: Puzzle, lang: str = "zh") -> Path:
    """Persist *puzzle* as JSON in data/puzzles/{lang}/{puzzle.id}.json.

    Creates the language subdirectory if it does not exist.
    Returns the path written.
    """
    lang_dir = PUZZLES_DIR / lang
    lang_dir.mkdir(parents=True, exist_ok=True)
    path = lang_dir / f"{puzzle.id}.json"
    path.write_text(puzzle.model_dump_json(indent=2), encoding="utf-8")
    return path


def invalidate_puzzle_cache(lang: str | None = None) -> None:
    """Evict the puzzle cache for *lang* (or all languages if None)."""
    if lang is None:
        _cache.clear()
    else:
        _cache.pop(lang, None)


def invalidate_script_cache(lang: str | None = None) -> None:
    """Evict the script cache for *lang* (or all languages if None).

    After calling this, the next load_scripts() call re-reads all JSON
    files from disk, picking up newly uploaded scripts.
    """
    if lang is None:
        _script_cache.clear()
    else:
        _script_cache.pop(lang, None)
