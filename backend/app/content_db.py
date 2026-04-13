"""SQLite-backed storage for puzzle and script content.

Schema
------
puzzles  (id, lang, title, difficulty, tags_json, data_json)
scripts  (id, lang, title, player_count, difficulty, game_mode, data_json)

The `data_json` column holds the full Pydantic model serialised to JSON so that
adding fields to Puzzle/Script never requires a schema migration.  The other
columns exist solely for fast listing/filtering without deserialising the blob.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Generator

from app.models import Puzzle, Script

_DB_PATH = Path(__file__).parent.parent / "data" / "content.db"
_lock = Lock()
_conn: sqlite3.Connection | None = None


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                _conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
                _conn.row_factory = sqlite3.Row
                _conn.execute("PRAGMA journal_mode=WAL")
                _conn.execute("PRAGMA foreign_keys=ON")
                _init_schema(_conn)
    return _conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS puzzles (
            id         TEXT NOT NULL,
            lang       TEXT NOT NULL,
            title      TEXT NOT NULL,
            difficulty TEXT NOT NULL DEFAULT '',
            tags_json  TEXT NOT NULL DEFAULT '[]',
            data_json  TEXT NOT NULL,
            PRIMARY KEY (id, lang)
        );

        CREATE TABLE IF NOT EXISTS scripts (
            id           TEXT NOT NULL,
            lang         TEXT NOT NULL,
            title        TEXT NOT NULL,
            player_count INTEGER NOT NULL DEFAULT 0,
            difficulty   TEXT NOT NULL DEFAULT '',
            game_mode    TEXT NOT NULL DEFAULT 'whodunit',
            data_json    TEXT NOT NULL,
            PRIMARY KEY (id, lang)
        );
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Puzzle operations
# ---------------------------------------------------------------------------


def get_puzzle(puzzle_id: str, lang: str = "zh") -> Puzzle:
    """Return a Puzzle by id+lang. Raises KeyError if absent."""
    row = _get_conn().execute(
        "SELECT data_json FROM puzzles WHERE id=? AND lang=?", (puzzle_id, lang)
    ).fetchone()
    if row is None:
        raise KeyError(f"Puzzle not found: {puzzle_id!r} (lang={lang!r})")
    return Puzzle.model_validate_json(row["data_json"])


def list_puzzles(lang: str = "zh") -> list[Puzzle]:
    """Return all puzzles for *lang* ordered by title."""
    rows = _get_conn().execute(
        "SELECT data_json FROM puzzles WHERE lang=? ORDER BY title", (lang,)
    ).fetchall()
    return [Puzzle.model_validate_json(r["data_json"]) for r in rows]


def upsert_puzzle(puzzle: Puzzle, lang: str = "zh") -> None:
    """Insert or replace a puzzle (keyed on id+lang)."""
    _get_conn().execute(
        """
        INSERT INTO puzzles (id, lang, title, difficulty, tags_json, data_json)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id, lang) DO UPDATE SET
            title      = excluded.title,
            difficulty = excluded.difficulty,
            tags_json  = excluded.tags_json,
            data_json  = excluded.data_json
        """,
        (
            puzzle.id,
            lang,
            puzzle.title,
            puzzle.difficulty,
            json.dumps(puzzle.tags, ensure_ascii=False),
            puzzle.model_dump_json(),
        ),
    )
    _get_conn().commit()


def delete_puzzle(puzzle_id: str, lang: str = "zh") -> None:
    _get_conn().execute(
        "DELETE FROM puzzles WHERE id=? AND lang=?", (puzzle_id, lang)
    )
    _get_conn().commit()


# ---------------------------------------------------------------------------
# Script operations
# ---------------------------------------------------------------------------


def get_script(script_id: str, lang: str = "zh") -> Script:
    """Return a Script by id+lang. Raises KeyError if absent."""
    row = _get_conn().execute(
        "SELECT data_json FROM scripts WHERE id=? AND lang=?", (script_id, lang)
    ).fetchone()
    if row is None:
        raise KeyError(f"Script not found: {script_id!r} (lang={lang!r})")
    return Script.model_validate_json(row["data_json"])


def list_scripts(lang: str = "zh") -> list[Script]:
    """Return all scripts for *lang* ordered by title."""
    rows = _get_conn().execute(
        "SELECT data_json FROM scripts WHERE lang=? ORDER BY title", (lang,)
    ).fetchall()
    return [Script.model_validate_json(r["data_json"]) for r in rows]


def upsert_script(script: Script, lang: str = "zh") -> None:
    """Insert or replace a script (keyed on id+lang)."""
    _get_conn().execute(
        """
        INSERT INTO scripts (id, lang, title, player_count, difficulty, game_mode, data_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id, lang) DO UPDATE SET
            title        = excluded.title,
            player_count = excluded.player_count,
            difficulty   = excluded.difficulty,
            game_mode    = excluded.game_mode,
            data_json    = excluded.data_json
        """,
        (
            script.id,
            lang,
            script.title,
            script.metadata.player_count,
            script.metadata.difficulty,
            script.game_mode,
            script.model_dump_json(),
        ),
    )
    _get_conn().commit()


def delete_script(script_id: str, lang: str = "zh") -> None:
    _get_conn().execute(
        "DELETE FROM scripts WHERE id=? AND lang=?", (script_id, lang)
    )
    _get_conn().commit()
