"""Community script metadata — SQLite-backed store.

Tracks uploaded scripts with author name, like count, and creation timestamp.
Uses stdlib sqlite3 only (no extra deps).  All writes are synchronous and
expected to be called from FastAPI endpoints via asyncio.to_thread().
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent / "data" / "community.db"
_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist.  Call once at startup."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock, _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS script_meta (
                script_id   TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                author      TEXT NOT NULL DEFAULT '',
                difficulty  TEXT NOT NULL DEFAULT '',
                player_count INTEGER NOT NULL DEFAULT 0,
                game_mode   TEXT NOT NULL DEFAULT 'whodunit',
                lang        TEXT NOT NULL DEFAULT 'zh',
                likes       INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL,
                is_public   INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.commit()


def upsert_script(
    script_id: str,
    title: str,
    author: str,
    difficulty: str,
    player_count: int,
    game_mode: str,
    lang: str,
    is_public: bool = True,
) -> None:
    """Insert or update a script's community metadata."""
    now = datetime.now(UTC).isoformat()
    with _lock, _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO script_meta
                (script_id, title, author, difficulty, player_count, game_mode, lang, created_at, is_public)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(script_id) DO UPDATE SET
                title        = excluded.title,
                author       = excluded.author,
                difficulty   = excluded.difficulty,
                player_count = excluded.player_count,
                game_mode    = excluded.game_mode,
                is_public    = excluded.is_public
            """,
            (script_id, title, author, difficulty, player_count, game_mode, lang, now, int(is_public)),
        )
        conn.commit()


def like_script(script_id: str) -> int:
    """Increment likes for *script_id*.  Returns new like count."""
    with _lock, _get_conn() as conn:
        conn.execute(
            "UPDATE script_meta SET likes = likes + 1 WHERE script_id = ?",
            (script_id,),
        )
        conn.commit()
        row = conn.execute("SELECT likes FROM script_meta WHERE script_id = ?", (script_id,)).fetchone()
    return row["likes"] if row else 0


def list_community_scripts(
    lang: str | None = None,
    search: str | None = None,
    difficulty: str | None = None,
    game_mode: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Return community scripts matching the given filters."""
    clauses: list[str] = ["is_public = 1"]
    params: list[object] = []

    if lang:
        clauses.append("lang = ?")
        params.append(lang)
    if search:
        clauses.append("(title LIKE ? OR author LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if difficulty:
        clauses.append("difficulty = ?")
        params.append(difficulty)
    if game_mode:
        clauses.append("game_mode = ?")
        params.append(game_mode)

    where = " AND ".join(clauses)
    params.append(limit)

    with _get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM script_meta WHERE {where} ORDER BY likes DESC, created_at DESC LIMIT ?",
            params,
        ).fetchall()

    return [dict(r) for r in rows]
