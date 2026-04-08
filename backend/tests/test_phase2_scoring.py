import pytest
from unittest.mock import MagicMock


def make_room():
    from app.room import Room
    r = Room.__new__(Room)
    r.player_scores = {}
    r.player_turn_counts = {}
    r.players = {}
    return r


def test_record_and_leaderboard():
    r = make_room()
    r.record_score("alice", 10)
    r.record_score("bob", 5)
    lb = r.get_leaderboard()
    assert lb[0]["player_id"] == "alice"
    assert lb[1]["player_id"] == "bob"

def test_cumulative():
    r = make_room()
    r.record_score("alice", 3)
    r.record_score("alice", 7)
    assert r.get_leaderboard()[0]["score"] == 10

def test_tiebreak_by_fewest_turns():
    r = make_room()
    r.record_score("alice", 10)
    r.record_score("alice", 0)
    r.record_score("bob", 10)
    lb = r.get_leaderboard()
    # alice has 2 turns, bob has 1 — bob should rank higher on tiebreak
    assert lb[0]["player_id"] == "bob"

def test_zero_score():
    r = make_room()
    r.record_score("alice", 0)
    assert r.get_leaderboard()[0]["score"] == 0

def test_mvp():
    r = make_room()
    r.record_score("alice", 10)
    r.record_score("bob", 5)
    mvp = r.compute_mvp()
    assert mvp["player_id"] == "alice"
