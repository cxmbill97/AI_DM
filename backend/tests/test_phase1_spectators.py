"""Phase 1 Feature 3: Spectator mode unit tests.

Tests cover:
- add_spectator registers in room.spectators (not room.players)
- Spectators do NOT count toward _active_player_count / is_full
- broadcast() reaches spectators
- disconnect_spectator marks spectator as disconnected
- Room state distinguishes players from spectators
- Player count enforced independently of spectators
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import Puzzle
from app.room import Room


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_puzzle() -> Puzzle:
    return Puzzle(
        id="p1", title="T", surface="S", truth="X",
        key_facts=[], hints=[], difficulty="easy", tags=[],
    )


def _make_ws() -> MagicMock:
    ws = MagicMock()
    ws.send_json = AsyncMock()
    return ws


def _make_room() -> Room:
    return Room("SP0001", puzzle=_make_puzzle())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_add_spectator_not_in_players():
    room = _make_room()
    room.add_spectator("s1", "Eve", _make_ws())
    assert "s1" in room.spectators
    assert "s1" not in room.players


def test_spectator_does_not_count_toward_active_players():
    room = _make_room()
    room.add_player("p1", "Alice", _make_ws())
    room.add_spectator("s1", "Eve", _make_ws())
    assert room._active_player_count() == 1


def test_spectators_do_not_trigger_is_full():
    room = _make_room()
    # Fill to max_players with spectators — room should remain joinable
    for i in range(room.max_players):
        room.add_spectator(f"s{i}", f"Spec{i}", _make_ws())
    assert not room.is_full()


def test_disconnect_spectator_marks_disconnected():
    room = _make_room()
    room.add_spectator("s1", "Eve", _make_ws())
    room.disconnect_spectator("s1")
    assert not room.spectators["s1"]["connected"]
    assert room.spectators["s1"]["websocket"] is None


@pytest.mark.asyncio
async def test_broadcast_reaches_spectator():
    room = _make_room()
    ws_player = _make_ws()
    ws_spec = _make_ws()
    room.add_player("p1", "Alice", ws_player)
    room.add_spectator("s1", "Eve", ws_spec)

    msg = {"type": "system", "text": "hello"}
    await room.broadcast(msg)

    ws_player.send_json.assert_awaited_once_with(msg)
    ws_spec.send_json.assert_awaited_once_with(msg)


def test_players_and_spectators_are_separate_dicts():
    room = _make_room()
    room.add_player("p1", "Alice", _make_ws())
    room.add_spectator("s1", "Eve", _make_ws())

    assert set(room.players.keys()) == {"p1"}
    assert set(room.spectators.keys()) == {"s1"}
