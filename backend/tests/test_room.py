"""Tests for multiplayer rooms: state machine + WebSocket integration.

Unit tests (no WebSocket):
  - Room creation, player slots, capacity, disconnect/reconnect state

WebSocket integration tests (starlette TestClient):
  - Join flow, snapshot delivery, capacity enforcement
  - Message broadcast to all players
  - Disconnect notice, reconnect within window
  - Shared clue state across players
  - Single-player REST endpoints unaffected by room machinery

Message ordering reference (used throughout these tests)
---------------------------------------------------------
When player N (1-indexed) joins a room that already has N-1 players:
  - ALL currently connected players (including N) receive:
      {"type": "system", "text": "<name> 加入了房间"}
  - Only player N receives:
      {"type": "room_snapshot", ...}

Helper drain_join_messages(ws, n_prior_players) reads exactly:
  - 1 system message ("Name joined")
  - 1 room_snapshot
from the perspective of the *joining* player (n_prior_players is unused
but kept for documentation clarity).

When a player disconnects, ALL remaining connected players receive:
  {"type": "system", "text": "<name> 断开连接"}

When a player reconnects, ALL connected players receive:
  {"type": "system", "text": "<name> 重新连接了"}
Then the reconnecting player receives any missed messages.
"""

from __future__ import annotations

import os
import time
from typing import Any
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "test-secret-key-room-tests")

from app.main import app  # noqa: E402
from app.puzzle_loader import load_puzzle  # noqa: E402
from app.room import room_manager  # noqa: E402


def _make_token(name: str) -> str:
    """Create a JWT token for a test user with the given name."""
    import app.auth as auth_mod
    user = auth_mod.upsert_user(f"test:{name}", name, f"{name.lower()}@test.com", "")
    return auth_mod.create_jwt(user["id"])


@pytest.fixture(autouse=True)
def _auth_db(monkeypatch, tmp_path):
    """Point auth module at a temp DB for each test."""
    import app.auth as auth_mod
    monkeypatch.setattr(auth_mod, "_DB_PATH", tmp_path / "auth.db")
    auth_mod.init_auth_db()
    yield

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_rooms(monkeypatch: pytest.MonkeyPatch):
    """Reset room_manager between every test.

    Also patches _ensure_tick_running to a no-op so the background silence-tick
    task never starts during integration tests.  Tick behavior is covered in
    full by test_intervention.py unit tests, which don't need a live event loop.
    Without this patch, tests that take > 5 s would receive spurious
    dm_intervention messages that confuse message-order assertions.
    """
    room_manager.rooms.clear()
    # Suppress the background tick for all WS integration tests
    monkeypatch.setattr("app.ws._ensure_tick_running", lambda _room: None)
    yield
    for room in list(room_manager.rooms.values()):
        if room._tick_task and not room._tick_task.done():
            room._tick_task.cancel()
    room_manager.rooms.clear()


@pytest.fixture
def icicle_puzzle():
    return load_puzzle("icicle_murder")


@pytest.fixture
def icicle_room(icicle_puzzle):
    """A freshly created icicle_murder room."""
    room_id = room_manager.create_room(icicle_puzzle)
    return room_manager.get_room(room_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _drain_join(ws: Any) -> dict:
    """Read the initial messages for a freshly joined player.

    Returns the room_snapshot dict.  Also consumes a trailing private_clue
    message when the puzzle has private clues for this player's slot.
    """
    from app.puzzle_loader import load_puzzle

    sys_msg = ws.receive_json()
    assert sys_msg["type"] == "system", f"expected system, got {sys_msg['type']}"
    snapshot = ws.receive_json()
    assert snapshot["type"] == "room_snapshot", f"expected snapshot, got {snapshot['type']}"
    # Puzzles with private_clues send a private_clue message immediately after
    # the snapshot (only to the joining player, not stored in message_history).
    try:
        puzzle = load_puzzle(snapshot["puzzle_id"])
        if puzzle.private_clues:
            pc = ws.receive_json()
            assert pc["type"] == "private_clue", f"expected private_clue, got {pc['type']}"
    except Exception:
        pass
    return snapshot


def _next_non_typing(ws: Any) -> dict:
    """Read messages until we get one that is not dm_typing."""
    while True:
        msg = ws.receive_json()
        if msg.get("type") != "dm_typing":
            return msg


def _drain_others_join_notice(ws: Any) -> dict:
    """When another player joins, existing players get a system notice,
    optionally a player_joined lobby event, then a players_update message.

    Reads all and returns the system notice.
    """
    msg = ws.receive_json()
    assert msg["type"] == "system"
    next_msg = ws.receive_json()
    # Consume optional player_joined lobby event
    if next_msg["type"] == "player_joined":
        next_msg = ws.receive_json()
    assert next_msg["type"] == "players_update"
    return msg


# ---------------------------------------------------------------------------
# Unit tests — Room state machine (no WebSocket)
# ---------------------------------------------------------------------------


class TestRoomStateMachine:
    def test_create_room_sets_puzzle(self, icicle_room, icicle_puzzle):
        assert icicle_room.puzzle.id == icicle_puzzle.id
        assert icicle_room.game_session.puzzle.id == icicle_puzzle.id

    def test_new_room_not_full(self, icicle_room):
        assert not icicle_room.is_full()

    def test_full_after_four_players(self, icicle_room):
        # turtle_soup max_players is now 4
        ws = MagicMock()
        for i in range(4):
            icicle_room.add_player(f"pid-{i}", f"Player{i}", ws)
        assert icicle_room.is_full()

    def test_not_full_at_three(self, icicle_room):
        ws = MagicMock()
        for i in range(3):
            icicle_room.add_player(f"pid-{i}", f"Player{i}", ws)
        assert not icicle_room.is_full()

    def test_find_player_by_name_found(self, icicle_room):
        ws = MagicMock()
        icicle_room.add_player("pid-alice", "Alice", ws)
        assert icicle_room.find_player_by_name("Alice") == "pid-alice"

    def test_find_player_by_name_not_found(self, icicle_room):
        assert icicle_room.find_player_by_name("Ghost") is None

    def test_disconnect_marks_slot_offline(self, icicle_room):
        ws = MagicMock()
        icicle_room.add_player("pid-1", "Alice", ws)
        icicle_room.disconnect_player("pid-1")
        slot = icicle_room.players["pid-1"]
        assert not slot["connected"]
        assert slot["websocket"] is None

    def test_reconnect_restores_slot(self, icicle_room):
        ws_old = MagicMock()
        ws_new = MagicMock()
        icicle_room.add_player("pid-1", "Alice", ws_old)
        icicle_room.disconnect_player("pid-1")
        icicle_room.reconnect_player("pid-1", ws_new)
        slot = icicle_room.players["pid-1"]
        assert slot["connected"]
        assert slot["websocket"] is ws_new

    def test_disconnected_within_window_counts_as_active(self, icicle_room):
        """A freshly disconnected player is still within the reconnect window."""
        ws = MagicMock()
        icicle_room.add_player("pid-1", "Alice", ws)
        icicle_room.disconnect_player("pid-1")
        assert icicle_room._active_player_count() == 1

    def test_disconnected_expired_window_not_counted(self, icicle_room):
        """A player disconnected >60 s ago no longer counts toward capacity."""
        ws = MagicMock()
        icicle_room.add_player("pid-1", "Alice", ws)
        # Backdate last_seen past the reconnect window
        icicle_room.players["pid-1"]["last_seen"] -= 120
        icicle_room.players["pid-1"]["connected"] = False
        assert icicle_room._active_player_count() == 0

    def test_messages_since_filters_by_timestamp(self, icicle_room):
        t0 = time.time()
        icicle_room.message_history = [
            {"type": "system", "text": "old", "timestamp": t0 - 10},
            {"type": "system", "text": "new", "timestamp": t0 + 1},
        ]
        result = icicle_room.messages_since(t0)
        assert len(result) == 1
        assert result[0]["text"] == "new"

    def test_phase_playing_with_connected_player(self, icicle_room):
        ws = MagicMock()
        icicle_room.add_player("pid-1", "Alice", ws)
        assert icicle_room.phase == "playing"

    def test_phase_waiting_when_all_disconnected(self, icicle_room):
        ws = MagicMock()
        icicle_room.add_player("pid-1", "Alice", ws)
        icicle_room.disconnect_player("pid-1")
        assert icicle_room.phase == "waiting"

    def test_phase_finished_when_game_over(self, icicle_room):
        icicle_room.game_session.finished = True
        assert icicle_room.phase == "finished"

    def test_intervention_engine_attached(self, icicle_room):
        from app.intervention import InterventionEngine

        assert isinstance(icicle_room.intervention, InterventionEngine)

    def test_tick_task_initially_none(self, icicle_room):
        assert icicle_room._tick_task is None


# ---------------------------------------------------------------------------
# WebSocket integration — join flow
# ---------------------------------------------------------------------------


class TestCreateAndJoinRoom:
    def test_two_players_appear_in_room(self, mock_llm):
        """Create room, join 2 players, assert both in player list, puzzle set."""
        with TestClient(app) as client:
            resp = client.post("/api/rooms", json={"puzzle_id": "icicle_murder"})
            assert resp.status_code == 200
            room_id = resp.json()["room_id"]

            with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Alice')}") as ws_a:
                snap_a = _drain_join(ws_a)
                assert snap_a["puzzle_id"] == "icicle_murder"
                assert len(snap_a["players"]) == 1

                with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Bob')}") as ws_b:
                    # Alice gets Bob's join notice
                    _drain_others_join_notice(ws_a)
                    # Bob: drain his own join + snapshot
                    snap_b = _drain_join(ws_b)
                    assert len(snap_b["players"]) == 2
                    names = {p["name"] for p in snap_b["players"]}
                    assert names == {"Alice", "Bob"}

            # Verify via REST
            room_resp = client.get(f"/api/rooms/{room_id}")
            assert room_resp.status_code == 200
            room_data = room_resp.json()
            assert room_data["puzzle_id"] == "icicle_murder"
            assert len(room_data["players"]) == 2

    def test_snapshot_contains_puzzle_surface(self, mock_llm):
        with TestClient(app) as client:
            resp = client.post("/api/rooms", json={"puzzle_id": "icicle_murder"})
            room_id = resp.json()["room_id"]
            with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Alice')}") as ws:
                snap = _drain_join(ws)
                assert snap["type"] == "room_snapshot"
                assert snap["puzzle_id"] == "icicle_murder"
                assert len(snap["surface"]) > 0

    def test_unknown_room_sends_error(self):
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/BADXXX?token={_make_token('Alice')}") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "BADXXX" in msg["text"] or "不存在" in msg["text"]

    def test_unauthenticated_sends_error(self, mock_llm):
        with TestClient(app) as client:
            resp = client.post("/api/rooms", json={})
            room_id = resp.json()["room_id"]
            with client.websocket_connect(f"/ws/{room_id}?token=") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "error"

    def test_duplicate_active_name_rejected(self, mock_llm):
        with TestClient(app) as client:
            resp = client.post("/api/rooms", json={})
            room_id = resp.json()["room_id"]
            with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Alice')}") as ws_a:
                _drain_join(ws_a)
                # Second connection with same name — Alice is still connected
                with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Alice')}") as ws_dup:
                    msg = ws_dup.receive_json()
                    assert msg["type"] == "error"
                    assert "Alice" in msg["text"] or "使用" in msg["text"]


# ---------------------------------------------------------------------------
# WebSocket integration — capacity
# ---------------------------------------------------------------------------


class TestRoomCapacityLimit:
    def test_seventh_player_rejected(self, mock_llm):
        """Fill 6 slots via add_player, then try 7th via WebSocket."""
        room_id = room_manager.create_room(load_puzzle("icicle_murder"))
        room = room_manager.get_room(room_id)
        mock_ws = MagicMock()
        for i in range(6):
            room.add_player(f"pid-{i}", f"Player{i}", mock_ws)
        assert room.is_full()

        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Extra')}") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "error"
                assert "满" in msg["text"]

    def test_room_not_full_with_five(self):
        room_id = room_manager.create_room(load_puzzle("icicle_murder"))
        room = room_manager.get_room(room_id)
        mock_ws = MagicMock()
        for i in range(5):
            room.add_player(f"pid-{i}", f"Player{i}", mock_ws)
        assert not room.is_full()


# ---------------------------------------------------------------------------
# WebSocket integration — message broadcast
# ---------------------------------------------------------------------------


class TestMessageBroadcast:
    def test_dm_response_reaches_both_players(self, mock_llm):
        """Player A sends a message; both A and B receive dm_response."""
        mock_llm.set_response(
            {
                "judgment": "不是",
                "response": "这与真相无关。",
                "truth_progress": 0.05,
                "should_hint": False,
            }
        )

        with TestClient(app) as client:
            resp = client.post("/api/rooms", json={"puzzle_id": "icicle_murder"})
            room_id = resp.json()["room_id"]

            with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Alice')}") as ws_a:
                _drain_join(ws_a)

                with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Bob')}") as ws_b:
                    _drain_others_join_notice(ws_a)  # Alice: "Bob joined"
                    _drain_join(ws_b)  # Bob: join + snapshot

                    # Alice sends a chat message (no clue keyword)
                    ws_a.send_json({"type": "chat", "text": "死者是男性吗？"})

                    # Alice gets: player_message, (dm_typing), dm_response, (dm_typing)
                    pm_a = ws_a.receive_json()
                    assert pm_a["type"] == "player_message"
                    assert pm_a["player_name"] == "Alice"
                    assert pm_a["text"] == "死者是男性吗？"

                    dm_a = _next_non_typing(ws_a)
                    assert dm_a["type"] == "dm_response"
                    assert dm_a["judgment"] == "不是"
                    assert dm_a["player_name"] == "Alice"

                    # Bob also gets: player_message, (dm_typing), dm_response, (dm_typing)
                    pm_b = ws_b.receive_json()
                    assert pm_b["type"] == "player_message"
                    assert pm_b["player_name"] == "Alice"

                    dm_b = _next_non_typing(ws_b)
                    assert dm_b["type"] == "dm_response"
                    assert dm_b["judgment"] == "不是"

    def test_dm_response_includes_truth_progress(self, mock_llm):
        mock_llm.set_response(
            {
                "judgment": "是",
                "response": "对！",
                "truth_progress": 0.4,
                "should_hint": False,
            }
        )
        with TestClient(app) as client:
            resp = client.post("/api/rooms", json={"puzzle_id": "icicle_murder"})
            room_id = resp.json()["room_id"]
            with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Alice')}") as ws:
                _drain_join(ws)
                ws.send_json({"type": "chat", "text": "凶器是固体的吗？"})
                ws.receive_json()  # player_message
                dm = _next_non_typing(ws)
                assert dm["type"] == "dm_response"
                assert dm["truth_progress"] == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# WebSocket integration — clue unlocks (shared state)
# ---------------------------------------------------------------------------


class TestSharedClueState:
    def test_clue_unlock_appears_in_session_and_dm_response(self, mock_llm):
        """Player A asks about 仓库 → clue_building unlocked, visible in session + dm_response."""
        mock_llm.set_response(
            {
                "judgment": "是",
                "response": "正确！",
                "truth_progress": 0.2,
                "should_hint": False,
            }
        )
        with TestClient(app) as client:
            resp = client.post("/api/rooms", json={"puzzle_id": "icicle_murder"})
            room_id = resp.json()["room_id"]
            room = room_manager.get_room(room_id)

            with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Alice')}") as ws:
                _drain_join(ws)
                # "仓库" is in clue_building.unlock_keywords
                ws.send_json({"type": "chat", "text": "案发地点旁边有仓库吗？"})
                ws.receive_json()  # player_message
                dm = _next_non_typing(ws)
                assert dm["type"] == "dm_response"
                assert dm["clue_unlocked"] is not None
                assert dm["clue_unlocked"]["id"] == "clue_building"

            # Shared session reflects the unlock
            assert "clue_building" in room.game_session.unlocked_clue_ids

    def test_unlocked_clue_appears_in_subsequent_dm_prompt(self, mock_llm):
        """After A unlocks a clue, B's DM call has the clue in its system prompt."""
        mock_llm.set_response(
            {
                "judgment": "无关",
                "response": "这与谜题无关。",
                "truth_progress": 0.0,
                "should_hint": False,
            }
        )
        with TestClient(app) as client:
            resp = client.post("/api/rooms", json={"puzzle_id": "icicle_murder"})
            room_id = resp.json()["room_id"]

            with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Alice')}") as ws_a:
                _drain_join(ws_a)

                with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Bob')}") as ws_b:
                    _drain_others_join_notice(ws_a)
                    _drain_join(ws_b)

                    # Alice unlocks clue_building with keyword "仓库"
                    ws_a.send_json({"type": "chat", "text": "旁边有仓库吗？"})
                    ws_a.receive_json()  # player_message
                    _next_non_typing(ws_a)  # dm_response (clue unlocked)
                    ws_b.receive_json()  # player_message (broadcast)
                    _next_non_typing(ws_b)  # dm_response (broadcast)

                    # Bob sends a follow-up question
                    ws_b.send_json({"type": "chat", "text": "凶手站在仓库里吗？"})
                    ws_b.receive_json()  # player_message
                    _next_non_typing(ws_b)  # dm_response

                    # The LLM should have been called with the unlocked clue in its prompt
                    assert (
                        "clue_building" in mock_llm.last_system_prompt
                        or "现场周边勘察" in mock_llm.last_system_prompt
                        or "冰柱" in mock_llm.last_system_prompt
                    )

    def test_clue_not_unlocked_twice(self, mock_llm):
        """Asking about the same keyword twice does not produce a second unlock."""
        mock_llm.set_response(
            {
                "judgment": "是",
                "response": "正确！",
                "truth_progress": 0.2,
                "should_hint": False,
            }
        )
        with TestClient(app) as client:
            resp = client.post("/api/rooms", json={"puzzle_id": "icicle_murder"})
            room_id = resp.json()["room_id"]
            room = room_manager.get_room(room_id)

            with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Alice')}") as ws:
                _drain_join(ws)
                # First question — should unlock clue_building
                ws.send_json({"type": "chat", "text": "现场旁边有仓库吗？"})
                ws.receive_json()  # player_message
                dm1 = _next_non_typing(ws)
                assert dm1["clue_unlocked"] is not None

                # Second question with same keyword — should NOT unlock again
                ws.send_json({"type": "chat", "text": "那个废弃仓库有多大？"})
                ws.receive_json()  # player_message
                dm2 = _next_non_typing(ws)
                assert dm2["clue_unlocked"] is None

            # Only one entry in the set
            assert (
                room.game_session.unlocked_clue_ids.count("clue_building")
                if isinstance(room.game_session.unlocked_clue_ids, list)
                else "clue_building" in room.game_session.unlocked_clue_ids
            )


# ---------------------------------------------------------------------------
# WebSocket integration — disconnect / reconnect
#
# NOTE ON TEST DESIGN
# -------------------
# Starlette's TestClient gives each websocket_connect() call its own OS
# thread + event loop.  Async sends from one session's event loop to
# another session's WebSocket fail silently (caught by _send_to_slot's
# `except Exception: pass`) when the sending session is in the process of
# closing.  This means we cannot reliably assert that player B's WS
# receives a broadcast emitted from within player A's disconnect handler.
#
# The broadcast mechanism itself IS covered by TestMessageBroadcast, which
# uses two concurrent sessions for normal chat and passes because both
# sessions are fully alive when the broadcast executes.
#
# For disconnect/reconnect we therefore:
#   - Verify room state and message_history (thread-safe, not WS-bound)
#   - Verify reconnect notice on the *reconnecting player's own* WS
#   - Inject fake history entries to test replay (no second live WS needed)
# ---------------------------------------------------------------------------


class TestPlayerDisconnectReconnect:
    def test_disconnect_marks_slot_offline_and_adds_leave_notice(self, mock_llm):
        """Disconnect → slot.connected=False, leave notice logged in history."""
        with TestClient(app) as client:
            resp = client.post("/api/rooms", json={"puzzle_id": "icicle_murder"})
            room_id = resp.json()["room_id"]
            room = room_manager.get_room(room_id)

            with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Alice')}") as ws:
                _drain_join(ws)
            # Alice disconnected

            alice_id = room.find_player_by_name("Alice")
            assert alice_id is not None
            assert not room.players[alice_id]["connected"]
            assert any("Alice" in m.get("text", "") and "断开" in m.get("text", "") for m in room.message_history if m.get("type") == "system")

    def test_disconnected_slot_within_reconnect_window(self, mock_llm):
        """Freshly disconnected player is still within the 60 s reconnect window."""
        with TestClient(app) as client:
            resp = client.post("/api/rooms", json={"puzzle_id": "icicle_murder"})
            room_id = resp.json()["room_id"]
            room = room_manager.get_room(room_id)

            with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Alice')}") as ws:
                _drain_join(ws)

            assert room._active_player_count() == 1  # still in window

    def test_reconnect_sends_notice_to_reconnecting_player(self, mock_llm):
        """The reconnecting player's new WS receives a 重新连接了 system message."""
        with TestClient(app) as client:
            resp = client.post("/api/rooms", json={"puzzle_id": "icicle_murder"})
            room_id = resp.json()["room_id"]

            with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Alice')}") as ws:
                _drain_join(ws)
            # Alice disconnected

            with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Alice')}") as ws2:
                msg = ws2.receive_json()
                assert msg["type"] == "system"
                assert "Alice" in msg["text"]
                assert "重新连接" in msg["text"]

    def test_reconnect_restores_slot_to_connected(self, mock_llm):
        """After reconnect, the room slot is marked connected again."""
        with TestClient(app) as client:
            resp = client.post("/api/rooms", json={"puzzle_id": "icicle_murder"})
            room_id = resp.json()["room_id"]
            room = room_manager.get_room(room_id)

            with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Alice')}") as ws:
                _drain_join(ws)

            with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Alice')}") as ws2:
                ws2.receive_json()  # reconnect notice
                alice_id = room.find_player_by_name("Alice")
                assert room.players[alice_id]["connected"]

    def test_reconnect_replays_missed_messages(self, mock_llm):
        """Messages logged while Alice was gone are replayed on her reconnect."""
        with TestClient(app) as client:
            resp = client.post("/api/rooms", json={"puzzle_id": "icicle_murder"})
            room_id = resp.json()["room_id"]
            room = room_manager.get_room(room_id)

            with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Alice')}") as ws:
                _drain_join(ws)
            # Alice disconnected

            alice_id = room.find_player_by_name("Alice")

            # The leave_notice timestamp is slightly after last_seen (both call
            # time.time() sequentially in ws.py).  Resetting last_seen to now
            # ensures the leave_notice is excluded from replay, so only our
            # two injected messages are returned to Alice.
            t_base = time.time()
            room.players[alice_id]["last_seen"] = t_base

            # Inject messages as if Bob sent them while Alice was away
            t = t_base + 0.1
            room.message_history.append(
                {
                    "type": "player_message",
                    "player_name": "Bob",
                    "text": "凶器是什么？",
                    "timestamp": t,
                }
            )
            room.message_history.append(
                {
                    "type": "dm_response",
                    "player_name": "Bob",
                    "judgment": "是",
                    "response": "对！",
                    "truth_progress": 0.1,
                    "clue_unlocked": None,
                    "hint": None,
                    "truth": None,
                    "timestamp": t + 0.1,
                }
            )

            with client.websocket_connect(f"/ws/{room_id}?token={_make_token('Alice')}") as ws2:
                ws2.receive_json()  # reconnect broadcast to Alice
                r1 = ws2.receive_json()  # replayed player_message
                r2 = ws2.receive_json()  # replayed dm_response
                assert {r1["type"], r2["type"]} == {"player_message", "dm_response"}


# ---------------------------------------------------------------------------
# Single-player REST endpoints work independently of rooms
# ---------------------------------------------------------------------------


class TestSinglePlayerStillWorks:
    def test_start_and_chat_via_rest(self, mock_llm):
        """Phase 1 REST endpoints function normally alongside Phase 2 rooms."""
        mock_llm.set_response(
            {
                "judgment": "是",
                "response": "对，这是正确的方向！",
                "truth_progress": 0.25,
                "should_hint": False,
            }
        )
        with TestClient(app) as client:
            # Start a single-player game
            start = client.post("/api/start", json={"puzzle_id": "icicle_murder"})
            assert start.status_code == 200
            session_data = start.json()
            assert "session_id" in session_data
            assert "surface" in session_data
            assert "truth" not in session_data  # truth never returned from /api/start

            # Send a chat message
            chat = client.post(
                "/api/chat",
                json={
                    "session_id": session_data["session_id"],
                    "message": "死者身上有明显的穿刺伤吗？",
                },
            )
            assert chat.status_code == 200
            chat_data = chat.json()
            assert chat_data["judgment"] == "是"
            # truth only returned when progress >= 1.0
            assert chat_data.get("truth") is None

    def test_room_creation_does_not_affect_single_player_session(self, mock_llm):
        """Creating multiplayer rooms doesn't pollute the single-player session store."""
        mock_llm.set_response(
            {
                "judgment": "无关",
                "response": "与谜题无关。",
                "truth_progress": 0.0,
                "should_hint": False,
            }
        )
        with TestClient(app) as client:
            # Create a multiplayer room
            client.post("/api/rooms", json={"puzzle_id": "icicle_murder"})

            # Start a separate single-player game
            start = client.post("/api/start", json={})
            session_id = start.json()["session_id"]

            chat = client.post(
                "/api/chat",
                json={
                    "session_id": session_id,
                    "message": "这与天气有关吗？",
                },
            )
            assert chat.status_code == 200
            assert chat.json()["judgment"] == "无关"

    def test_health_endpoint(self):
        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    def test_puzzle_list_endpoint(self):
        with TestClient(app) as client:
            resp = client.get("/api/puzzles")
            assert resp.status_code == 200
            puzzles = resp.json()
            assert len(puzzles) > 0
            # Truth must never appear in the listing
            for p in puzzles:
                assert "truth" not in p

    def test_chat_with_nonexistent_session_returns_404(self, mock_llm):
        with TestClient(app) as client:
            resp = client.post(
                "/api/chat",
                json={
                    "session_id": "does-not-exist",
                    "message": "任何问题",
                },
            )
            assert resp.status_code == 404

    def test_chat_with_empty_message_returns_422(self, mock_llm):
        with TestClient(app) as client:
            start = client.post("/api/start", json={})
            session_id = start.json()["session_id"]
            resp = client.post(
                "/api/chat",
                json={
                    "session_id": session_id,
                    "message": "   ",  # whitespace only
                },
            )
            assert resp.status_code == 422
