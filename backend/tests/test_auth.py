"""Tests for auth.py — JWT, user CRUD, favorites, history."""

from __future__ import annotations

import os
import sqlite3

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-key-for-tests-only")


@pytest.fixture(autouse=True)
def _tmp_db(monkeypatch, tmp_path):
    db = str(tmp_path / "test.db")
    import app.auth as auth_mod
    monkeypatch.setattr(auth_mod, "_DB_PATH", __import__("pathlib").Path(db))
    auth_mod.init_auth_db()
    yield


def test_init_auth_db_creates_tables(tmp_path):
    import app.auth as auth_mod
    conn = sqlite3.connect(str(auth_mod._DB_PATH))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"users", "user_favorites", "room_history"} <= tables


def test_upsert_user_creates_and_returns():
    from app.auth import upsert_user
    user = upsert_user("google:sub_1", "Alice", "alice@example.com", "https://avatar.url/a")
    assert user["name"] == "Alice"
    assert user["email"] == "alice@example.com"
    assert "id" in user
    assert user["provider_sub"] == "google:sub_1"


def test_upsert_user_updates_on_conflict():
    from app.auth import upsert_user
    upsert_user("google:sub2", "Bob", "bob@example.com", "")
    user2 = upsert_user("google:sub2", "Bobby", "bob@example.com", "https://new.avatar")
    assert user2["name"] == "Bobby"


def test_create_and_decode_jwt():
    from app.auth import create_jwt, decode_jwt, upsert_user
    user = upsert_user("google:sub3", "Carol", "carol@example.com", "")
    token = create_jwt(user["id"])
    assert isinstance(token, str)
    payload = decode_jwt(token)
    assert payload["sub"] == user["id"]


def test_decode_jwt_invalid_raises():
    from app.auth import decode_jwt
    with pytest.raises(ValueError):
        decode_jwt("not.a.valid.token")


def test_favorites_add_list_remove():
    from app.auth import add_favorite, list_favorites, remove_favorite, upsert_user
    user = upsert_user("google:sub4", "Dave", "dave@example.com", "")
    uid = user["id"]
    add_favorite(uid, "puzzle_001", "puzzle")
    add_favorite(uid, "script_abc", "script")
    favs = list_favorites(uid)
    assert len(favs) == 2
    remove_favorite(uid, "puzzle_001", "puzzle")
    assert len(list_favorites(uid)) == 1


def test_add_favorite_idempotent():
    from app.auth import add_favorite, list_favorites, upsert_user
    user = upsert_user("google:sub5", "Eve", "eve@example.com", "")
    uid = user["id"]
    add_favorite(uid, "puzzle_x", "puzzle")
    add_favorite(uid, "puzzle_x", "puzzle")  # duplicate — should not raise
    assert len(list_favorites(uid)) == 1


def test_history_add_and_list():
    from app.auth import add_history, list_history, upsert_user
    user = upsert_user("google:sub6", "Frank", "frank@example.com", "")
    uid = user["id"]
    add_history(uid, "room_abc", "turtle_soup", "相册里的秘密", 3)
    add_history(uid, "room_def", "murder_mystery", "书房密室", 4)
    hist = list_history(uid)
    assert len(hist) == 2
    assert hist[0]["title"] in {"相册里的秘密", "书房密室"}


def test_apple_upsert_creates_user():
    from app.auth import upsert_user
    user = upsert_user("apple:001.abc123", "Tim", "tim@privaterelay.appleid.com", "")
    assert user["provider_sub"] == "apple:001.abc123"
    assert user["name"] == "Tim"


def test_google_and_apple_same_email_different_accounts():
    from app.auth import upsert_user
    g = upsert_user("google:gid1", "Alice", "alice@gmail.com", "")
    a = upsert_user("apple:aid1", "Alice", "alice@gmail.com", "")
    assert g["id"] != a["id"]
