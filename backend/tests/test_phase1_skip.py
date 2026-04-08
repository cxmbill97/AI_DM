"""Phase 1 Feature 2: Skip system unit tests.

Tests cover:
- Single vote from 2 players does NOT pass
- Both players vote → majority passes (2/2 = 100%)
- 2 of 3 active players passes (>50%)
- 1 of 3 does not pass
- Non-player cannot cast a vote
- Votes clear after skip passes
- reset_to_puzzle swaps puzzle and resets game state
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.models import HINTS_PER_GAME, Puzzle
from app.room import Room


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_puzzle(puzzle_id: str = "p1", hints: list[str] | None = None) -> Puzzle:
    return Puzzle(
        id=puzzle_id,
        title="Test",
        surface="A man dies.",
        truth="He lived.",
        key_facts=["key fact"],
        hints=hints or ["H1", "H2", "H3"],
        difficulty="easy",
        tags=[],
    )


def _make_room_with_players(n: int, puzzle: Puzzle | None = None) -> tuple[Room, list[str]]:
    """Create a room with *n* connected players; return (room, player_ids)."""
    room = Room("SK0001", puzzle=puzzle or _make_puzzle())
    player_ids: list[str] = []
    for i in range(n):
        pid = f"p{i+1}"
        room.add_player(pid, f"Player{i+1}", MagicMock())
        player_ids.append(pid)
    return room, player_ids


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_single_vote_of_two_does_not_pass():
    room, pids = _make_room_with_players(2)
    passed = room.vote_skip_puzzle(pids[0])
    assert not passed
    assert room.skip_votes_count() == 1


def test_both_players_vote_passes():
    room, pids = _make_room_with_players(2)
    room.vote_skip_puzzle(pids[0])
    passed = room.vote_skip_puzzle(pids[1])
    assert passed


def test_majority_of_three_passes():
    room, pids = _make_room_with_players(3)
    room.vote_skip_puzzle(pids[0])
    passed = room.vote_skip_puzzle(pids[1])
    assert passed  # 2/3 > 50%


def test_minority_of_three_does_not_pass():
    room, pids = _make_room_with_players(3)
    passed = room.vote_skip_puzzle(pids[0])
    assert not passed
    assert room.skip_votes_count() == 1


def test_non_player_vote_ignored():
    room, _ = _make_room_with_players(2)
    passed = room.vote_skip_puzzle("outsider")
    assert not passed
    assert room.skip_votes_count() == 0


def test_votes_clear_after_skip_passes():
    room, pids = _make_room_with_players(2)
    room.vote_skip_puzzle(pids[0])
    room.vote_skip_puzzle(pids[1])
    # votes cleared on pass
    assert room.skip_votes_count() == 0


def test_reset_to_puzzle_replaces_puzzle_and_resets_state():
    old_puzzle = _make_puzzle("old")
    room, pids = _make_room_with_players(2, puzzle=old_puzzle)
    # Use a hint to dirty the state
    room.use_hint(pids[0])
    assert room.hints_remaining < HINTS_PER_GAME

    new_puzzle = _make_puzzle("new")
    room.reset_to_puzzle(new_puzzle)

    assert room.puzzle.id == "new"
    assert room.game_session is not None
    assert room.game_session.puzzle.id == "new"
    assert room.hints_remaining == HINTS_PER_GAME
    assert room.skip_votes_count() == 0
