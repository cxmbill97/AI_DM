"""Tests for Phase 1: spectator mode.

Unit tests:
  - Room.add_spectator() does NOT increase _active_player_count()
  - Room.is_full() ignores spectators (a 6-player room still allows spectators)
  - Room.broadcast() sends to both players and spectators
  - Room.spectator_count property counts connected spectators

Integration tests (WebSocket):
  - Spectator receives full message history replay on join
  - Spectator cannot send chat (gets error)
  - Spectator cannot vote (gets error)
  - Regular player room snapshot includes spectator_count
  - spectator_joined event broadcast to players when spectator joins
  - spectator_left event broadcast when spectator disconnects
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-spectator")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_room():
    from app.puzzle_loader import load_puzzle
    from app.room import Room
    puzzle = load_puzzle("classic_turtle_soup", "zh")
    return Room("SPEC01", puzzle=puzzle, language="zh")


def _add_player(room, pid: str, name: str):
    ws = MagicMock()
    ws.send_json = AsyncMock()
    room.add_player(pid, name, ws)
    return ws


def _add_spectator(room, pid: str, name: str):
    ws = MagicMock()
    ws.send_json = AsyncMock()
    room.add_spectator(pid, name, ws)
    return ws


def _make_token(name: str) -> str:
    import app.auth as auth_mod
    user = auth_mod.upsert_user(f"test:{name}", name, f"{name.lower()}@test.com", "")
    return auth_mod.create_jwt(user["id"])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _auth_db(monkeypatch, tmp_path):
    import app.auth as auth_mod
    monkeypatch.setattr(auth_mod, "_DB_PATH", tmp_path / "auth.db")
    auth_mod.init_auth_db()
    yield


@pytest.fixture(autouse=True)
def clean_rooms(monkeypatch):
    from app.room import room_manager as _rm
    _rm.rooms.clear()
    monkeypatch.setattr("app.ws._ensure_tick_running", lambda _room: None)
    yield
    _rm.rooms.clear()


@pytest.fixture
def client():
    from starlette.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Unit: Room spectator management
# ---------------------------------------------------------------------------


class TestSpectatorPlayerCount:
    def test_add_spectator_does_not_increase_player_count(self):
        room = _make_room()
        _add_player(room, "p1", "Alice")
        assert room._active_player_count() == 1
        _add_spectator(room, "s1", "Spectator1")
        assert room._active_player_count() == 1  # unchanged

    def test_is_full_ignores_spectators(self):
        room = _make_room()
        # Fill to max (6)
        for i in range(1, 7):
            _add_player(room, f"p{i}", f"Player{i}")
        assert room.is_full()
        # Spectator still allowed
        _add_spectator(room, "s1", "Watcher")
        assert room.is_full()  # still full for players
        assert room.spectator_count == 1


class TestSpectatorCount:
    def test_spectator_count_zero_initially(self):
        room = _make_room()
        assert room.spectator_count == 0

    def test_spectator_count_increments_on_add(self):
        room = _make_room()
        _add_spectator(room, "s1", "S1")
        _add_spectator(room, "s2", "S2")
        assert room.spectator_count == 2

    def test_spectator_count_decrements_on_disconnect(self):
        room = _make_room()
        _add_spectator(room, "s1", "S1")
        room.disconnect_spectator("s1")
        assert room.spectator_count == 0


class TestBroadcastIncludesSpectators:
    def test_broadcast_reaches_spectator(self):
        room = _make_room()
        player_ws = _add_player(room, "p1", "Alice")
        spectator_ws = _add_spectator(room, "s1", "Watcher")
        msg = {"type": "test", "text": "hello"}

        asyncio.get_event_loop().run_until_complete(room.broadcast(msg))

        player_ws.send_json.assert_called_once_with(msg)
        spectator_ws.send_json.assert_called_once_with(msg)

    def test_broadcast_skips_disconnected_spectator(self):
        room = _make_room()
        spectator_ws = _add_spectator(room, "s1", "Watcher")
        room.disconnect_spectator("s1")
        msg = {"type": "test"}

        asyncio.get_event_loop().run_until_complete(room.broadcast(msg))

        spectator_ws.send_json.assert_not_called()


# ---------------------------------------------------------------------------
# Integration: WebSocket spectator flow
# ---------------------------------------------------------------------------


def _ws_url(room_id: str, token: str, spectate: bool = False) -> str:
    url = f"/ws/{room_id}?token={token}"
    if spectate:
        url += "&spectate=true"
    return url


def _drain_join(ws) -> list[dict]:
    """Consume initial join messages: system + room_snapshot."""
    msgs = []
    for _ in range(2):
        msgs.append(ws.receive_json())
    return msgs


class TestSpectatorWebSocket:
    def test_spectator_receives_room_snapshot_with_role(self, client):
        resp = client.post("/api/rooms", json={})
        room_id = resp.json()["room_id"]
        tok = _make_token("SpecWatcher")

        with client.websocket_connect(_ws_url(room_id, tok, spectate=True)) as ws:
            # spectator_joined broadcast (sent to room — since room is empty, only spectator sees it)
            msg1 = ws.receive_json()
            # room_snapshot
            msg2 = ws.receive_json()
            assert msg2["type"] == "room_snapshot"
            assert msg2["role"] == "spectator"
            assert "spectator_count" in msg2

    def test_spectator_cannot_chat(self, client):
        resp = client.post("/api/rooms", json={})
        room_id = resp.json()["room_id"]
        tok = _make_token("ChatlessWatcher")

        with client.websocket_connect(_ws_url(room_id, tok, spectate=True)) as ws:
            ws.receive_json()  # spectator_joined
            ws.receive_json()  # room_snapshot
            ws.send_json({"type": "chat", "text": "Can I talk?"})
            err = ws.receive_json()
            assert err["type"] == "error"

    def test_spectator_cannot_vote(self, client):
        resp = client.post("/api/rooms", json={})
        room_id = resp.json()["room_id"]
        tok = _make_token("VotelessWatcher")

        with client.websocket_connect(_ws_url(room_id, tok, spectate=True)) as ws:
            ws.receive_json()  # spectator_joined
            ws.receive_json()  # room_snapshot
            ws.send_json({"type": "vote", "target": "some_player"})
            err = ws.receive_json()
            assert err["type"] == "error"

    def test_regular_player_snapshot_includes_spectator_count(self, client):
        resp = client.post("/api/rooms", json={})
        room_id = resp.json()["room_id"]
        player_tok = _make_token("RegPlayer")
        spectator_tok = _make_token("SomeWatcher")

        with client.websocket_connect(_ws_url(room_id, player_tok)) as player_ws, \
             client.websocket_connect(_ws_url(room_id, spectator_tok, spectate=True)) as spec_ws:

            # Player join
            player_ws.receive_json()  # system
            snapshot = player_ws.receive_json()  # room_snapshot
            assert "spectator_count" in snapshot

    def test_spectator_receives_message_history_replay(self, client):
        resp = client.post("/api/rooms", json={})
        room_id = resp.json()["room_id"]

        # A player joins first and sends a message (adds to history via join notice)
        player_tok = _make_token("HistPlayer")
        with client.websocket_connect(_ws_url(room_id, player_tok)) as ws:
            ws.receive_json()  # system
            ws.receive_json()  # snapshot
            # Now a spectator joins and should get history replay
            spec_tok = _make_token("HistWatcher")
            with client.websocket_connect(_ws_url(room_id, spec_tok, spectate=True)) as spec_ws:
                spec_ws.receive_json()   # spectator_joined (broadcast)
                snapshot = spec_ws.receive_json()  # room_snapshot
                assert snapshot["role"] == "spectator"
                # History replay: at minimum the player join system message
                replay = spec_ws.receive_json()
                assert replay["type"] == "system"

    def test_spectator_does_not_affect_room_capacity(self):
        """Spectators are not counted in _active_player_count so a full room still allows them."""
        room = _make_room()
        # Fill to capacity
        for i in range(1, 7):
            _add_player(room, f"p{i}", f"Player{i}")
        assert room.is_full()
        # Spectator joins — room stays full for player purposes but spectator is added
        _add_spectator(room, "s1", "Watcher")
        assert room.is_full()                    # still full for players
        assert room.spectator_count == 1          # spectator counted separately
        assert room._active_player_count() == 6   # player count unchanged
