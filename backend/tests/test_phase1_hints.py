"""Phase 1 Feature 1: Hint system unit tests.

Tests cover:
- Hint budget starts at HINTS_PER_GAME (3)
- use_hint returns the next hint and decrements the counter
- Sequential calls return successive hints
- use_hint returns None when budget is exhausted
- use_hint returns None when puzzle has no hints
- use_hint is a no-op for murder_mystery rooms
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.models import HINTS_PER_GAME, GameSession, Puzzle
from app.room import Room


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_puzzle(hints: list[str] | None = None, key_facts: list[str] | None = None) -> Puzzle:
    return Puzzle(
        id="test_puzzle",
        title="Test",
        surface="A man is found dead.",
        truth="He was a liar.",
        key_facts=key_facts or ["他撒谎了"],
        hints=hints if hints is not None else ["Hint 1", "Hint 2", "Hint 3"],
        difficulty="easy",
        tags=[],
    )


def _make_room(puzzle: Puzzle | None = None) -> Room:
    p = puzzle or _make_puzzle()
    room = Room("TEST01", puzzle=p)
    # Stub out WebSocket for host player
    ws = MagicMock()
    room.add_player("p1", "Alice", ws)
    return room


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_hints_remaining_starts_at_default():
    room = _make_room()
    assert room.hints_remaining == HINTS_PER_GAME


def test_use_hint_returns_text_and_decrements():
    room = _make_room(_make_puzzle(hints=["Hint A", "Hint B", "Hint C"]))
    text = room.use_hint("p1")
    assert text == "Hint A"
    assert room.hints_remaining == HINTS_PER_GAME - 1


def test_use_hint_sequential_returns_successive_hints():
    hints = ["First", "Second", "Third"]
    room = _make_room(_make_puzzle(hints=hints))
    results = [room.use_hint("p1") for _ in range(3)]
    assert results == hints
    assert room.hints_remaining == 0


def test_use_hint_exhausted_returns_none():
    room = _make_room(_make_puzzle(hints=["Only one hint"]))
    room.hints_remaining = 0
    result = room.use_hint("p1")
    assert result is None


def test_use_hint_no_hints_in_puzzle_returns_none():
    room = _make_room(_make_puzzle(hints=[]))
    result = room.use_hint("p1")
    assert result is None


def test_use_hint_noop_for_murder_mystery_room():
    from app.models import (
        Character,
        NPC,
        Phase,
        Script,
        ScriptMetadata,
        ScriptTheme,
        ScriptTruth,
    )

    script = Script(
        id="s1",
        title="MM",
        metadata=ScriptMetadata(player_count=2, duration_minutes=60, difficulty="beginner"),
        characters=[
            Character(id="c1", name="A", public_bio="x", secret_bio="y", is_culprit=False),
            Character(id="c2", name="B", public_bio="x", secret_bio="y", is_culprit=True),
        ],
        phases=[Phase(id="ph1", type="narration", next=None, allowed_actions=set())],
        clues=[],
        npcs=[],
        truth=ScriptTruth(culprit="c2", motive="m", method="m2", timeline="t"),
        theme=ScriptTheme(),
    )
    room = Room("MM01", script=script)
    result = room.use_hint("p1")
    assert result is None
