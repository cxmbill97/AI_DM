"""Tests for Phase 2: per-turn scoring and MVP selection.

Unit tests:
  - _compute_turn_score() with all judgment types and clue bonus
  - Room.record_score() accumulates correctly
  - Room.get_leaderboard() returns correct sort order
  - Room.compute_mvp() handles ties and empty scores

Integration tests (WebSocket):
  - dm_response includes turn_score and leaderboard after a DM answer
  - game_over is broadcast when truth_progress >= 1.0 (game won)
  - game_over is NOT broadcast for non-winning turns
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-scoring")

from app.room import Room  # noqa: E402
from app.ws import _compute_turn_score  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_room() -> Room:
    from app.puzzle_loader import load_puzzle
    puzzle = load_puzzle("classic_turtle_soup", "zh")
    return Room("SCORE1", puzzle=puzzle, language="zh")


def _add_player(room: Room, pid: str, name: str) -> None:
    ws = MagicMock()
    ws.send_json = AsyncMock()
    room.add_player(pid, name, ws)


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
# Unit: _compute_turn_score
# ---------------------------------------------------------------------------


class TestComputeTurnScore:
    def test_yes_no_clue(self):
        assert _compute_turn_score("是", False) == 3

    def test_yes_with_clue_bonus(self):
        assert _compute_turn_score("是", True) == 4

    def test_partial_correct(self):
        assert _compute_turn_score("部分正确", False) == 2

    def test_partial_correct_with_clue(self):
        assert _compute_turn_score("部分正确", True) == 3

    def test_no(self):
        assert _compute_turn_score("不是", False) == 1

    def test_irrelevant(self):
        assert _compute_turn_score("无关", False) == 0

    def test_english_yes(self):
        assert _compute_turn_score("Yes", False) == 3

    def test_english_no(self):
        assert _compute_turn_score("No", False) == 1

    def test_english_partially_correct(self):
        assert _compute_turn_score("Partially correct", False) == 2

    def test_english_irrelevant(self):
        assert _compute_turn_score("Irrelevant", False) == 0

    def test_max_cap_at_four(self):
        # 是 (3) + clue (1) = 4 (cap)
        assert _compute_turn_score("是", True) == 4

    def test_unknown_judgment_gives_zero(self):
        assert _compute_turn_score("unknown", False) == 0


# ---------------------------------------------------------------------------
# Unit: Room.record_score
# ---------------------------------------------------------------------------


class TestRecordScore:
    def test_first_record_initialises(self):
        room = _make_room()
        room.record_score("p1", 3)
        assert room.player_scores["p1"] == 3
        assert room.player_turn_counts["p1"] == 1

    def test_accumulates_across_turns(self):
        room = _make_room()
        room.record_score("p1", 3)
        room.record_score("p1", 1)
        room.record_score("p1", 0)
        assert room.player_scores["p1"] == 4
        assert room.player_turn_counts["p1"] == 3

    def test_multiple_players(self):
        room = _make_room()
        room.record_score("p1", 3)
        room.record_score("p2", 2)
        room.record_score("p1", 1)
        assert room.player_scores["p1"] == 4
        assert room.player_scores["p2"] == 2


# ---------------------------------------------------------------------------
# Unit: Room.get_leaderboard
# ---------------------------------------------------------------------------


class TestGetLeaderboard:
    def test_sorted_by_score_desc(self):
        room = _make_room()
        _add_player(room, "p1", "Alice")
        _add_player(room, "p2", "Bob")
        room.record_score("p1", 1)
        room.record_score("p2", 3)
        lb = room.get_leaderboard()
        assert lb[0]["player_name"] == "Bob"
        assert lb[1]["player_name"] == "Alice"

    def test_tie_broken_by_fewer_turns(self):
        room = _make_room()
        _add_player(room, "p1", "Alice")
        _add_player(room, "p2", "Bob")
        # Both 3 points, but Alice took 2 turns, Bob took 1
        room.record_score("p1", 1)
        room.record_score("p1", 2)
        room.record_score("p2", 3)
        lb = room.get_leaderboard()
        assert lb[0]["player_name"] == "Bob"   # fewer turns

    def test_empty_leaderboard(self):
        room = _make_room()
        assert room.get_leaderboard() == []

    def test_avg_computed(self):
        room = _make_room()
        _add_player(room, "p1", "Alice")
        room.record_score("p1", 3)
        room.record_score("p1", 1)
        lb = room.get_leaderboard()
        assert lb[0]["avg"] == 2.0


# ---------------------------------------------------------------------------
# Unit: Room.compute_mvp
# ---------------------------------------------------------------------------


class TestComputeMvp:
    def test_single_player_is_mvp(self):
        room = _make_room()
        _add_player(room, "p1", "Alice")
        room.record_score("p1", 5)
        mvp = room.compute_mvp()
        assert mvp is not None
        assert mvp["player_name"] == "Alice"
        assert mvp["score"] == 5

    def test_higher_score_wins(self):
        room = _make_room()
        _add_player(room, "p1", "Alice")
        _add_player(room, "p2", "Bob")
        room.record_score("p1", 2)
        room.record_score("p2", 5)
        mvp = room.compute_mvp()
        assert mvp["player_name"] == "Bob"

    def test_tie_broken_by_fewer_turns(self):
        room = _make_room()
        _add_player(room, "p1", "Alice")
        _add_player(room, "p2", "Bob")
        room.record_score("p1", 3)
        room.record_score("p1", 0)  # 2 turns
        room.record_score("p2", 3)  # 1 turn
        mvp = room.compute_mvp()
        assert mvp["player_name"] == "Bob"

    def test_empty_scores_returns_none(self):
        room = _make_room()
        assert room.compute_mvp() is None


# ---------------------------------------------------------------------------
# Integration: dm_response includes turn_score and leaderboard
# ---------------------------------------------------------------------------


def _ws_url(room_id: str, token: str) -> str:
    return f"/ws/{room_id}?token={token}"


def _drain_join(ws) -> list[dict]:
    """Consume the initial join messages: system + room_snapshot."""
    msgs = []
    for _ in range(2):
        msgs.append(ws.receive_json())
    return msgs


def _drain_other_joins(ws) -> None:
    """Consume the 3 messages that arrive when a second player joins: system + player_joined + players_update."""
    for _ in range(3):
        ws.receive_json()


def _make_dm_result(judgment: str = "不是", truth_progress: float = 0.1):
    from app.models import ChatResponse
    return ChatResponse(
        judgment=judgment,
        response="测试回应",
        truth_progress=truth_progress,
        should_hint=False,
    )


class TestScoringIntegration:
    def test_dm_response_includes_turn_score(self, client):
        resp = client.post("/api/rooms", json={})  # lobby_mode=False → started=True
        room_id = resp.json()["room_id"]
        tok = _make_token("ScoreAlice")

        mock_result = _make_dm_result("不是", 0.1)
        with patch("app.ws.dm_turn", new=AsyncMock(return_value=mock_result)):
            with client.websocket_connect(_ws_url(room_id, tok)) as ws:
                _drain_join(ws)
                ws.send_json({"type": "chat", "text": "是不是死亡"})
                # Drain until we reach dm_response (may have 2x dm_typing)
                resp_msg = None
                for _ in range(5):
                    msg = ws.receive_json()
                    if msg["type"] == "dm_response":
                        resp_msg = msg
                        break
                assert resp_msg is not None, "Never received dm_response"
                assert "turn_score" in resp_msg
                assert resp_msg["turn_score"] == 1  # "不是" → 1 point
                assert "leaderboard" in resp_msg
                assert len(resp_msg["leaderboard"]) == 1

    def test_game_over_broadcast_on_win(self, client):
        resp = client.post("/api/rooms", json={})
        room_id = resp.json()["room_id"]
        tok = _make_token("WinAlice")

        from app.models import ChatResponse
        win_result = ChatResponse(
            judgment="是",
            response="正确！",
            truth_progress=1.0,
            truth="真相大白",
            should_hint=False,
        )
        with patch("app.ws.dm_turn", new=AsyncMock(return_value=win_result)):
            with client.websocket_connect(_ws_url(room_id, tok)) as ws:
                _drain_join(ws)
                ws.send_json({"type": "chat", "text": "谜底"})
                # Drain until dm_response
                dm_resp = None
                for _ in range(5):
                    msg = ws.receive_json()
                    if msg["type"] == "dm_response":
                        dm_resp = msg
                        break
                assert dm_resp is not None
                assert dm_resp["winner_name"] == "WinAlice"
                # game_over should follow immediately
                game_over = ws.receive_json()
                assert game_over["type"] == "game_over"
                assert game_over["winner_name"] == "WinAlice"
                assert "final_scores" in game_over
                assert "mvp" in game_over

    def test_game_over_not_sent_for_non_win(self, client):
        resp = client.post("/api/rooms", json={})
        room_id = resp.json()["room_id"]
        tok = _make_token("NoWinAlice")

        mock_result = _make_dm_result("无关", 0.0)
        with patch("app.ws.dm_turn", new=AsyncMock(return_value=mock_result)):
            with client.websocket_connect(_ws_url(room_id, tok)) as ws:
                _drain_join(ws)
                ws.send_json({"type": "chat", "text": "随便问问"})
                # Drain until dm_response
                dm_resp = None
                for _ in range(5):
                    msg = ws.receive_json()
                    if msg["type"] == "dm_response":
                        dm_resp = msg
                        break
                assert dm_resp is not None
                assert dm_resp.get("winner_name") is None
                assert dm_resp["turn_score"] == 0
