"""Auth layer — SQLite tables, JWT signing, user/favorites/history CRUD."""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import jwt as pyjwt

from app.config import settings

_DB_PATH = Path(__file__).parent.parent / "data" / "auth.db"
_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db() -> None:
    """Create auth tables. Call once at startup."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock, _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id           TEXT PRIMARY KEY,
                provider_sub TEXT UNIQUE NOT NULL,
                name         TEXT NOT NULL,
                email        TEXT NOT NULL,
                avatar_url   TEXT NOT NULL DEFAULT '',
                created_at   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS user_favorites (
                user_id   TEXT NOT NULL,
                item_id   TEXT NOT NULL,
                item_type TEXT NOT NULL,
                saved_at  TEXT NOT NULL,
                PRIMARY KEY (user_id, item_id, item_type)
            );
            CREATE TABLE IF NOT EXISTS room_history (
                id           TEXT PRIMARY KEY,
                user_id      TEXT NOT NULL,
                room_id      TEXT NOT NULL,
                game_type    TEXT NOT NULL,
                title        TEXT NOT NULL,
                player_count INTEGER NOT NULL DEFAULT 0,
                played_at    TEXT NOT NULL,
                outcome      TEXT
            );
        """)
        # Idempotent migration: rename google_sub → provider_sub on existing DBs
        cols = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "google_sub" in cols and "provider_sub" not in cols:
            conn.execute("ALTER TABLE users RENAME COLUMN google_sub TO provider_sub")
        # Idempotent migration: add outcome column if missing
        history_cols = {row[1] for row in conn.execute("PRAGMA table_info(room_history)").fetchall()}
        if "outcome" not in history_cols:
            conn.execute("ALTER TABLE room_history ADD COLUMN outcome TEXT")
        conn.commit()


def upsert_user(provider_sub: str, name: str, email: str, avatar_url: str) -> dict:
    """Insert or update a user. provider_sub format: 'google:<sub>' or 'apple:<sub>'"""
    now = datetime.now(UTC).isoformat()
    with _lock, _conn() as conn:
        conn.execute(
            """
            INSERT INTO users (id, provider_sub, name, email, avatar_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider_sub) DO UPDATE SET
                name       = excluded.name,
                email      = excluded.email,
                avatar_url = excluded.avatar_url
            """,
            (str(uuid.uuid4()), provider_sub, name, email, avatar_url, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE provider_sub = ?", (provider_sub,)).fetchone()
    return dict(row)


def create_jwt(user_id: str) -> str:
    """Return a signed HS256 JWT with 30-day expiry."""
    payload = {"sub": user_id, "exp": int(time.time()) + 60 * 60 * 24 * 30}
    return pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_jwt(token: str) -> dict:
    """Decode and verify a JWT. Raises ValueError on failure."""
    try:
        return pyjwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except pyjwt.PyJWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc


def get_user_by_id(user_id: str) -> dict | None:
    """Return user row or None."""
    with _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------

def add_favorite(user_id: str, item_id: str, item_type: str) -> None:
    now = datetime.now(UTC).isoformat()
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO user_favorites (user_id, item_id, item_type, saved_at) VALUES (?,?,?,?)",
            (user_id, item_id, item_type, now),
        )
        conn.commit()


def remove_favorite(user_id: str, item_id: str, item_type: str) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "DELETE FROM user_favorites WHERE user_id=? AND item_id=? AND item_type=?",
            (user_id, item_id, item_type),
        )
        conn.commit()


def list_favorites(user_id: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM user_favorites WHERE user_id=? ORDER BY saved_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def add_history(user_id: str, room_id: str, game_type: str, title: str, player_count: int) -> None:
    now = datetime.now(UTC).isoformat()
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO room_history (id, user_id, room_id, game_type, title, player_count, played_at) VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), user_id, room_id, game_type, title, player_count, now),
        )
        conn.commit()


def list_history(user_id: str, limit: int = 50) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM room_history WHERE user_id=? ORDER BY played_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def complete_history(user_id: str, room_id: str, outcome: str) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "UPDATE room_history SET outcome=? WHERE user_id=? AND room_id=?",
            (outcome, user_id, room_id),
        )
        conn.commit()
