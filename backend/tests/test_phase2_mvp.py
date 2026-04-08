"""Tests for compute_mvp() and mvp_player_id storage in Room."""

import pytest

from app.room import Room
from app.models import Puzzle


def _make_room() -> Room:
    puzzle = Puzzle(
        id="p1", title="Test", surface="surface", truth="truth",
        key_facts=[], hints=[], difficulty="easy", tags=[],
    )
    room = Room(room_id="r1", puzzle=puzzle)
    room.players = {
        "alice": {"name": "Alice", "connected": True},
        "bob": {"name": "Bob", "connected": True},
    }
    return room


def test_single_winner():
    room = _make_room()
    room.player_scores = {"alice": 10, "bob": 3}
    mvp = room.compute_mvp()
    assert mvp["player_id"] == "alice"


def test_tiebreak_by_verdict_scores():
    room = _make_room()
    room.player_scores = {"alice": 5, "bob": 5}
    room._scores = {"alice": 8, "bob": 3}  # alice wins tiebreak
    mvp = room.compute_mvp()
    assert mvp["player_id"] == "alice"


def test_tiebreak_by_fewest_turns():
    room = _make_room()
    room.player_scores = {"alice": 5, "bob": 5}
    room._scores = {"alice": 5, "bob": 5}  # same verdict scores
    room.player_turn_counts = {"alice": 2, "bob": 4}  # alice fewer turns
    mvp = room.compute_mvp()
    assert mvp["player_id"] == "alice"


def test_no_players_returns_none():
    room = _make_room()
    mvp = room.compute_mvp()
    assert mvp is None


def test_mvp_stored_in_state():
    room = _make_room()
    room.player_scores = {"alice": 10, "bob": 3}
    room.compute_mvp()
    assert room.mvp_player_id == "alice"
