"""Phase 0 turn-based system tests.

Covers:
  Unit tests (no WebSocket, no LLM):
    - Room.start_turns(): turn order initialised from player join order
    - Room.advance_turn(): index wraps correctly at end of order
    - Room.turn_elapsed(): returns time since turn_started_at
    - Room.current_turn_player_id(): returns None when turn_mode off
    - MAX_PLAYERS raised to 6
    - winner_player_id on GameSession

  _ts_tick() logic (monkeypatched asyncio tasks):
    - No timer action before TURN_HINT_SECS
    - turn_timeout_warning broadcast at >= TURN_HINT_SECS (once only)
    - turn_skipped broadcast at >= TURN_TIMEOUT_SECS; turn advances

  Integration tests (WebSocket via starlette.testclient):
    - turn_mode=True exposed in create-room response
    - start_room blocks if < 2 players
    - start_room broadcasts game_started with first_player info
    - Only the current player can chat (others get error)
    - After a DM response, turn_change is broadcast to all
    - Up to 6 players can join a room (cap raised from 4)
    - Winner attribution: winner_name in dm_response when game over
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-turn-mode")

from app.models import ChatResponse, GameSession  # noqa: E402
from app.puzzle_loader import load_puzzle  # noqa: E402
from app.room import Room, TURN_HINT_SECS, TURN_TIMEOUT_SECS, MAX_PLAYERS  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_puzzle():
    return load_puzzle("classic_turtle_soup", "zh")


def _make_room(turn_mode: bool = True) -> Room:
    puzzle = _make_puzzle()
    room = Room("TEST01", puzzle=puzzle, language="zh")
    room.turn_mode = turn_mode
    return room


def _add_player(room: Room, pid: str, name: str) -> None:
    ws = MagicMock()
    ws.send_json = AsyncMock()
    room.add_player(pid, name, ws)


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Unit: Room capacity
# ---------------------------------------------------------------------------


class TestMaxPlayers:
    def test_max_players_is_six(self):
        assert MAX_PLAYERS == 6

    def test_turtle_soup_room_defaults_to_six(self):
        room = _make_room()
        assert room.max_players == 6

    def test_six_players_fills_room(self):
        room = _make_room()
        for i in range(1, 6):
            _add_player(room, f"p{i}", f"Player{i}")
        assert not room.is_full()  # 5 players: not yet full
        _add_player(room, "p6", "Player6")
        assert room.is_full()  # 6th fills it


# ---------------------------------------------------------------------------
# Unit: turn order initialisation
# ---------------------------------------------------------------------------


class TestStartTurns:
    def test_turn_order_matches_join_order(self):
        room = _make_room()
        _add_player(room, "p1", "Alice")
        _add_player(room, "p2", "Bob")
        _add_player(room, "p3", "Carol")
        room.start_turns()
        assert room.turn_order == ["p1", "p2", "p3"]

    def test_current_turn_starts_at_first_player(self):
        room = _make_room()
        _add_player(room, "p1", "Alice")
        _add_player(room, "p2", "Bob")
        room.start_turns()
        assert room.current_turn_player_id() == "p1"
        assert room.current_turn_index == 0

    def test_turn_started_at_set_after_start(self):
        room = _make_room()
        _add_player(room, "p1", "Alice")
        before = time.time()
        room.start_turns()
        assert room.turn_started_at is not None
        assert room.turn_started_at >= before

    def test_hint_sent_flag_reset(self):
        room = _make_room()
        _add_player(room, "p1", "Alice")
        room._turn_hint_sent = True
        room.start_turns()
        assert not room._turn_hint_sent


# ---------------------------------------------------------------------------
# Unit: advance_turn
# ---------------------------------------------------------------------------


class TestAdvanceTurn:
    def test_advance_moves_to_next_player(self):
        room = _make_room()
        _add_player(room, "p1", "Alice")
        _add_player(room, "p2", "Bob")
        room.start_turns()
        nxt = room.advance_turn()
        assert nxt == "p2"
        assert room.current_turn_player_id() == "p2"

    def test_advance_wraps_around(self):
        room = _make_room()
        _add_player(room, "p1", "Alice")
        _add_player(room, "p2", "Bob")
        room.start_turns()
        room.advance_turn()  # → p2
        room.advance_turn()  # → p1 (wrap)
        assert room.current_turn_player_id() == "p1"

    def test_advance_resets_timer(self):
        room = _make_room()
        _add_player(room, "p1", "Alice")
        _add_player(room, "p2", "Bob")
        room.start_turns()
        before = time.time()
        room.advance_turn()
        assert room.turn_started_at is not None
        assert room.turn_started_at >= before

    def test_advance_clears_hint_sent(self):
        room = _make_room()
        _add_player(room, "p1", "Alice")
        _add_player(room, "p2", "Bob")
        room.start_turns()
        room._turn_hint_sent = True
        room.advance_turn()
        assert not room._turn_hint_sent

    def test_advance_three_players_full_cycle(self):
        room = _make_room()
        for i, name in enumerate(["Alice", "Bob", "Carol"], 1):
            _add_player(room, f"p{i}", name)
        room.start_turns()
        order = []
        for _ in range(6):
            order.append(room.current_turn_player_id())
            room.advance_turn()
        assert order == ["p1", "p2", "p3", "p1", "p2", "p3"]


# ---------------------------------------------------------------------------
# Unit: current_turn_player_id when turn_mode is off
# ---------------------------------------------------------------------------


class TestCurrentTurnOff:
    def test_returns_none_when_turn_mode_off(self):
        room = _make_room(turn_mode=False)
        _add_player(room, "p1", "Alice")
        room.start_turns()
        assert room.current_turn_player_id() is None

    def test_returns_none_before_start(self):
        room = _make_room()
        assert room.current_turn_player_id() is None


# ---------------------------------------------------------------------------
# Unit: turn_elapsed
# ---------------------------------------------------------------------------


class TestTurnElapsed:
    def test_elapsed_zero_when_not_started(self):
        room = _make_room()
        assert room.turn_elapsed() == 0.0

    def test_elapsed_increases_over_time(self):
        room = _make_room()
        _add_player(room, "p1", "Alice")
        room.start_turns()
        time.sleep(0.05)
        assert room.turn_elapsed() >= 0.04


# ---------------------------------------------------------------------------
# Unit: winner_player_id on GameSession
# ---------------------------------------------------------------------------


class TestWinnerPlayerIdModel:
    def test_winner_player_id_defaults_to_none(self):
        puzzle = _make_puzzle()
        session = GameSession(session_id="s1", puzzle=puzzle, history=[], language="zh")
        assert session.winner_player_id is None

    def test_winner_player_id_can_be_set(self):
        puzzle = _make_puzzle()
        session = GameSession(session_id="s1", puzzle=puzzle, history=[], language="zh")
        session.winner_player_id = "player_abc"
        assert session.winner_player_id == "player_abc"


# ---------------------------------------------------------------------------
# Unit: _ts_tick turn timer logic (async, monkeypatched)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTsTick:
    """Test the per-turn timer path inside _ts_tick without a live event loop."""

    def _make_room_with_players(self) -> Room:
        room = _make_room()
        _add_player(room, "p1", "Alice")
        _add_player(room, "p2", "Bob")
        room.start_turns()
        return room

    async def _collect_broadcasts(self, room: Room) -> list[dict]:
        """Run _ts_tick once and return all messages broadcast."""
        sent: list[dict] = []

        async def fake_broadcast(msg: dict):
            sent.append(msg)

        room.broadcast = fake_broadcast  # type: ignore[method-assign]
        # patch intervention so it never fires
        room.intervention.on_tick = MagicMock(return_value=None)  # type: ignore[method-assign]
        from app.ws import _ts_tick
        await _ts_tick(room)
        return sent

    async def test_no_message_before_hint_threshold(self):
        room = self._make_room_with_players()
        room.turn_started_at = time.time() - (TURN_HINT_SECS - 5)
        msgs = await self._collect_broadcasts(room)
        assert all(m["type"] != "turn_timeout_warning" for m in msgs)
        assert all(m["type"] != "turn_skipped" for m in msgs)

    async def test_hint_warning_at_hint_threshold(self):
        room = self._make_room_with_players()
        room.turn_started_at = time.time() - TURN_HINT_SECS
        msgs = await self._collect_broadcasts(room)
        warnings = [m for m in msgs if m["type"] == "turn_timeout_warning"]
        assert len(warnings) == 1
        assert warnings[0]["player_id"] == "p1"
        assert room._turn_hint_sent is True

    async def test_hint_warning_sent_only_once(self):
        room = self._make_room_with_players()
        room.turn_started_at = time.time() - TURN_HINT_SECS
        room._turn_hint_sent = True  # already sent
        msgs = await self._collect_broadcasts(room)
        assert all(m["type"] != "turn_timeout_warning" for m in msgs)

    async def test_turn_skipped_at_timeout_threshold(self):
        room = self._make_room_with_players()
        room.turn_started_at = time.time() - TURN_TIMEOUT_SECS
        msgs = await self._collect_broadcasts(room)
        skips = [m for m in msgs if m["type"] == "turn_skipped"]
        assert len(skips) == 1
        skip = skips[0]
        assert skip["skipped_player_id"] == "p1"
        assert skip["next_player_id"] == "p2"
        # Turn must have advanced
        assert room.current_turn_player_id() == "p2"

    async def test_skip_resets_hint_sent(self):
        room = self._make_room_with_players()
        room.turn_started_at = time.time() - TURN_TIMEOUT_SECS
        room._turn_hint_sent = True
        await self._collect_broadcasts(room)
        assert not room._turn_hint_sent

    async def test_no_tick_when_game_finished(self):
        room = self._make_room_with_players()
        room.turn_started_at = time.time() - TURN_TIMEOUT_SECS
        assert room.game_session is not None
        room.game_session.finished = True
        msgs = await self._collect_broadcasts(room)
        assert msgs == []

    async def test_hint_text_included_when_available(self):
        room = self._make_room_with_players()
        room.turn_started_at = time.time() - TURN_HINT_SECS
        assert room.game_session is not None
        # Ensure there's a hint in the puzzle
        assert len(room.game_session.puzzle.hints) > 0
        msgs = await self._collect_broadcasts(room)
        warnings = [m for m in msgs if m["type"] == "turn_timeout_warning"]
        assert warnings[0]["hint"] == room.game_session.puzzle.hints[0]


# ---------------------------------------------------------------------------
# Integration: WebSocket + REST flow
# ---------------------------------------------------------------------------

from starlette.testclient import TestClient  # noqa: E402
from app.main import app as _app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(_app) as c:
        yield c


def _ws_url(room_id: str, token: str) -> str:
    return f"/ws/{room_id}?token={token}"


def _drain_join(ws) -> dict:
    """Drain the first player's own join messages: system + room_snapshot.

    Returns the snapshot dict.
    """
    sys_msg = ws.receive_json()
    assert sys_msg["type"] == "system"
    snapshot = ws.receive_json()
    assert snapshot["type"] == "room_snapshot"
    return snapshot


def _drain_other_joins(ws, count: int = 1) -> None:
    """Drain messages that arrive on ws when `count` other players join.

    For each joining player, existing players receive:
      system + player_joined + players_update  (3 messages)
    """
    for _ in range(count):
        msg = ws.receive_json()
        assert msg["type"] == "system"
        next_msg = ws.receive_json()
        if next_msg["type"] == "player_joined":
            next_msg = ws.receive_json()
        assert next_msg["type"] == "players_update"


def _drain(ws, expected_types: list[str]) -> list[dict[str, Any]]:
    """Read exactly len(expected_types) messages from ws, verifying types in order."""
    msgs = []
    for expected in expected_types:
        msg = ws.receive_json()
        assert msg["type"] == expected, f"expected {expected!r}, got {msg['type']!r}: {msg}"
        msgs.append(msg)
    return msgs


class TestCreateRoomTurnMode:
    def test_turn_mode_in_response(self, client):
        resp = client.post("/api/rooms", json={"turn_mode": True, "lobby_mode": True})
        assert resp.status_code == 200
        body = resp.json()
        assert body["turn_mode"] is True
        assert body["game_type"] == "turtle_soup"

    def test_turn_mode_false_by_default(self, client):
        resp = client.post("/api/rooms", json={"lobby_mode": True})
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("turn_mode") is False


class TestStartRoomMinPlayers:
    def test_start_requires_two_players_in_turn_mode(self, client):
        resp = client.post("/api/rooms", json={"turn_mode": True, "lobby_mode": True})
        room_id = resp.json()["room_id"]
        tok1 = _make_token("Solo")

        with client.websocket_connect(_ws_url(room_id, tok1)) as ws:
            _drain_join(ws)
            start = client.post(f"/api/rooms/{room_id}/start")
            assert start.status_code == 422
            assert "2 players" in start.json()["detail"]

    def test_start_succeeds_with_two_players(self, client):
        resp = client.post("/api/rooms", json={"turn_mode": True, "lobby_mode": True})
        room_id = resp.json()["room_id"]
        tok1 = _make_token("Alice2")
        tok2 = _make_token("Bob2")

        with client.websocket_connect(_ws_url(room_id, tok1)) as ws1, \
             client.websocket_connect(_ws_url(room_id, tok2)) as ws2:

            _drain_join(ws1)         # Alice's own join
            _drain_other_joins(ws1)  # Bob joining → system + player_joined + players_update
            _drain_join(ws2)         # Bob's own join (system + snapshot)

            start = client.post(f"/api/rooms/{room_id}/start")
            assert start.status_code == 200


class TestStartRoomBroadcastsTurnInfo:
    def test_game_started_includes_first_player(self, client):
        resp = client.post("/api/rooms", json={"turn_mode": True, "lobby_mode": True})
        room_id = resp.json()["room_id"]
        tok1 = _make_token("FirstA")
        tok2 = _make_token("SecondA")

        with client.websocket_connect(_ws_url(room_id, tok1)) as ws1, \
             client.websocket_connect(_ws_url(room_id, tok2)) as ws2:

            _drain_join(ws1)
            _drain_other_joins(ws1)
            _drain_join(ws2)

            client.post(f"/api/rooms/{room_id}/start")

            start_msg = ws1.receive_json()
            assert start_msg["type"] == "game_started"
            assert start_msg["turn_mode"] is True
            assert start_msg["first_player_name"] == "FirstA"

    def test_non_turn_mode_game_started_no_turn_info(self, client):
        resp = client.post("/api/rooms", json={"turn_mode": False, "lobby_mode": True})
        room_id = resp.json()["room_id"]
        tok = _make_token("Solo2")

        with client.websocket_connect(_ws_url(room_id, tok)) as ws:
            _drain_join(ws)
            client.post(f"/api/rooms/{room_id}/start")
            msg = ws.receive_json()
            assert msg["type"] == "game_started"
            assert "turn_mode" not in msg or msg.get("turn_mode") is False


class TestTurnGating:
    """Only the current-turn player may submit a chat message."""

    def _setup_two_player_room(self, client, name1: str, name2: str):
        resp = client.post("/api/rooms", json={"turn_mode": True, "lobby_mode": True})
        room_id = resp.json()["room_id"]
        tok1 = _make_token(name1)
        tok2 = _make_token(name2)
        return room_id, tok1, tok2

    def test_off_turn_player_gets_error(self, client):
        room_id, tok1, tok2 = self._setup_two_player_room(client, "GateAlice", "GateBob")

        with client.websocket_connect(_ws_url(room_id, tok1)) as ws1, \
             client.websocket_connect(_ws_url(room_id, tok2)) as ws2:

            _drain_join(ws1)
            _drain_other_joins(ws1)
            _drain_join(ws2)

            client.post(f"/api/rooms/{room_id}/start")
            ws1.receive_json()  # game_started
            ws2.receive_json()  # game_started

            # Bob (player 2) tries to speak — it's Alice's turn
            ws2.send_json({"type": "chat", "text": "是不是发生了谋杀"})
            err = ws2.receive_json()
            assert err["type"] == "error"
            assert "GateAlice" in err["text"] or "turn" in err["text"].lower() or "回合" in err["text"]

    def test_current_player_can_chat(self, client):
        room_id, tok1, tok2 = self._setup_two_player_room(client, "ChatAlice", "ChatBob")

        with client.websocket_connect(_ws_url(room_id, tok1)) as ws1, \
             client.websocket_connect(_ws_url(room_id, tok2)) as ws2:

            _drain_join(ws1)
            _drain_other_joins(ws1)
            _drain_join(ws2)

            client.post(f"/api/rooms/{room_id}/start")
            ws1.receive_json()  # game_started
            ws2.receive_json()  # game_started

            fake_result = ChatResponse(
                judgment="不是",
                response="不对，请继续尝试。",
                truth_progress=0.1,
                should_hint=False,
            )
            with patch("app.ws.dm_turn", new=AsyncMock(return_value=fake_result)):
                ws1.send_json({"type": "chat", "text": "主人公是男性吗"})
                # Should receive player_message broadcast (not error)
                msg = ws1.receive_json()
                assert msg["type"] == "player_message"


def _drain_until(ws, target_type: str, max_msgs: int = 10) -> dict | None:
    """Read up to max_msgs messages, returning the first one with target_type."""
    for _ in range(max_msgs):
        msg = ws.receive_json()
        if msg["type"] == target_type:
            return msg
    return None


class TestTurnAdvanceAfterResponse:
    def test_turn_change_broadcast_after_dm_response(self, client):
        resp = client.post("/api/rooms", json={"turn_mode": True, "lobby_mode": True})
        room_id = resp.json()["room_id"]
        tok1 = _make_token("AdvAlice")
        tok2 = _make_token("AdvBob")

        with client.websocket_connect(_ws_url(room_id, tok1)) as ws1, \
             client.websocket_connect(_ws_url(room_id, tok2)) as ws2:

            _drain_join(ws1)
            _drain_other_joins(ws1)
            _drain_join(ws2)

            client.post(f"/api/rooms/{room_id}/start")
            ws1.receive_json()  # game_started (Alice)
            ws2.receive_json()  # game_started (Bob)

            fake_result = ChatResponse(
                judgment="不是",
                response="不对，继续。",
                truth_progress=0.1,
                should_hint=False,
            )
            with patch("app.ws.dm_turn", new=AsyncMock(return_value=fake_result)):
                ws1.send_json({"type": "chat", "text": "这是在室内发生的吗"})

                # Alice receives: player_message, dm_typing(True), dm_typing(False), dm_response, turn_change
                turn_msg = _drain_until(ws1, "turn_change", max_msgs=10)
                assert turn_msg is not None
                assert turn_msg["player_name"] == "AdvBob"

                # Bob also receives turn_change
                bob_turn = _drain_until(ws2, "turn_change", max_msgs=10)
                assert bob_turn is not None

    def test_winner_name_in_dm_response_on_win(self, client):
        resp = client.post("/api/rooms", json={"turn_mode": True, "lobby_mode": True})
        room_id = resp.json()["room_id"]
        tok1 = _make_token("WinnerAlice")
        tok2 = _make_token("WinnerBob")

        with client.websocket_connect(_ws_url(room_id, tok1)) as ws1, \
             client.websocket_connect(_ws_url(room_id, tok2)) as ws2:

            _drain_join(ws1)
            _drain_other_joins(ws1)
            _drain_join(ws2)

            client.post(f"/api/rooms/{room_id}/start")
            ws1.receive_json()  # game_started
            ws2.receive_json()  # game_started

            puzzle = _make_puzzle()
            winning_result = ChatResponse(
                judgment="是",
                response="完全正确！你解开了谜题！",
                truth_progress=1.0,
                should_hint=False,
                truth=puzzle.truth,
            )
            with patch("app.ws.dm_turn", new=AsyncMock(return_value=winning_result)):
                ws1.send_json({"type": "chat", "text": "他是故意跳楼的吗"})

                dm_resp = _drain_until(ws1, "dm_response", max_msgs=10)
                assert dm_resp is not None
                assert dm_resp["winner_name"] == "WinnerAlice"
                assert dm_resp["truth"] == puzzle.truth


class TestSixPlayerCapacity:
    def test_six_players_can_join_room(self, client):
        """Verify max_players=6 by using the REST API to check room state
        rather than opening 6 live WebSocket connections (which creates
        message-drain ordering issues in TestClient)."""
        from app.room import room_manager as _rm

        resp = client.post("/api/rooms", json={"lobby_mode": True})
        assert resp.status_code == 200
        room_id = resp.json()["room_id"]
        room = _rm.get_room(room_id)
        assert room is not None
        assert room.max_players == 6

        # Fill 5 players via add_player (unit level) — not full yet
        from unittest.mock import MagicMock, AsyncMock
        mock_ws = MagicMock()
        mock_ws.send_json = AsyncMock()
        for i in range(1, 6):
            room.add_player(f"p{i}", f"Cap{i}", mock_ws)
        assert not room.is_full()

        # Add the 6th — now full
        room.add_player("p6", "Cap6", mock_ws)
        assert room.is_full()

        # The 7th player is rejected via WebSocket
        tok7 = _make_token("Cap7")
        with client.websocket_connect(_ws_url(room_id, tok7)) as ws7:
            msg = ws7.receive_json()
            assert msg["type"] == "error"
            assert "6" in msg["text"] or "full" in msg["text"].lower() or "满" in msg["text"]


class TestNonTurnModeUnchanged:
    """Existing free-for-all mode should work the same as before."""

    def test_any_player_can_chat_without_turn_mode(self, client):
        resp = client.post("/api/rooms", json={"lobby_mode": True, "turn_mode": False})
        room_id = resp.json()["room_id"]
        tok1 = _make_token("FreeAlice")
        tok2 = _make_token("FreeBob")

        with client.websocket_connect(_ws_url(room_id, tok1)) as ws1, \
             client.websocket_connect(_ws_url(room_id, tok2)) as ws2:

            _drain_join(ws1)
            _drain_other_joins(ws1)
            _drain_join(ws2)

            client.post(f"/api/rooms/{room_id}/start")
            ws1.receive_json()  # game_started
            ws2.receive_json()  # game_started

            fake_result = ChatResponse(
                judgment="不是",
                response="不对。",
                truth_progress=0.1,
                should_hint=False,
            )
            with patch("app.ws.dm_turn", new=AsyncMock(return_value=fake_result)):
                # Bob goes first — no turn gating in free mode
                ws2.send_json({"type": "chat", "text": "是谋杀吗"})
                msg = ws2.receive_json()
                assert msg["type"] == "player_message"  # not error
