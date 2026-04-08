"""Tests for record_turn_score() and get_player_scores() in Room."""

import pytest

from app.room import Room
from app.models import Puzzle


def _make_room() -> Room:
    puzzle = Puzzle(
        id="p1", title="Test", surface="surface", truth="truth",
        key_facts=[], hints=[], difficulty="easy", tags=[],
    )
    return Room(room_id="r1", puzzle=puzzle)


def test_correct_scores_10():
    room = _make_room()
    pts = room.record_turn_score("p1", "correct")
    assert pts == 10
    assert room.get_player_scores()["p1"] == 10


def test_hint_penalty():
    room = _make_room()
    pts = room.record_turn_score("p1", "correct", hints_used=3)
    assert pts == 7  # 10 - 3


def test_speed_bonus():
    room = _make_room()
    pts = room.record_turn_score("p1", "relevant", elapsed_seconds=5)
    assert pts == 2  # 1 + 1 bonus


def test_cumulative_scores():
    room = _make_room()
    room.record_turn_score("p1", "relevant")   # 1
    room.record_turn_score("p1", "close")      # 3
    room.record_turn_score("p1", "correct")    # 10
    assert room.get_player_scores()["p1"] == 14


def test_zero_score_irrelevant():
    room = _make_room()
    pts = room.record_turn_score("p1", "irrelevant")
    assert pts == 0
    assert room.get_player_scores().get("p1", 0) == 0
