"""Tests for GameStateMachine — Phase 4 deterministic phase transitions.

Covers:
- Initial state
- can_act() action guards per phase
- advance() transitions and terminal phase behaviour
- time_remaining() and is_timed_out() timer helpers
- is_terminal() convenience accessor
- Edge cases: missing next phase, empty phase list
"""

from __future__ import annotations

import time

import pytest

from app.models import Phase
from app.state_machine import GameStateMachine

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def make_phases(specs: list[dict]) -> list[Phase]:
    """Build a Phase list from minimal dicts."""
    return [Phase(**s) for s in specs]


FULL_PHASES = make_phases([
    {
        "id": "opening",
        "type": "narration",
        "next": "reading",
        "duration_seconds": 120,
        "allowed_actions": {"listen"},
    },
    {
        "id": "reading",
        "type": "reading",
        "next": "investigation_1",
        "duration_seconds": 300,
        "allowed_actions": {"read_script"},
    },
    {
        "id": "investigation_1",
        "type": "investigation",
        "next": "discussion",
        "duration_seconds": 600,
        "allowed_actions": {"ask_dm", "search", "private_chat"},
    },
    {
        "id": "discussion",
        "type": "discussion",
        "next": "voting",
        "duration_seconds": 600,
        "allowed_actions": {"public_chat", "private_chat"},
    },
    {
        "id": "voting",
        "type": "voting",
        "next": "reveal",
        "duration_seconds": 120,
        "allowed_actions": {"cast_vote"},
    },
    {
        "id": "reveal",
        "type": "reveal",
        "next": None,
        "duration_seconds": None,
        "allowed_actions": {"listen"},
    },
])


@pytest.fixture
def sm() -> GameStateMachine:
    return GameStateMachine(FULL_PHASES)


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_starts_at_first_phase(self, sm: GameStateMachine) -> None:
        assert sm.current_phase == "opening"

    def test_all_phases_indexed(self, sm: GameStateMachine) -> None:
        assert set(sm.phases.keys()) == {
            "opening", "reading", "investigation_1", "discussion", "voting", "reveal"
        }

    def test_started_at_is_recent(self, sm: GameStateMachine) -> None:
        assert abs(sm.started_at - time.time()) < 2.0

    def test_empty_phases_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one phase"):
            GameStateMachine([])


# ---------------------------------------------------------------------------
# Action guards
# ---------------------------------------------------------------------------


class TestCanAct:
    def test_opening_allows_listen(self, sm: GameStateMachine) -> None:
        assert sm.can_act("listen") is True

    def test_opening_forbids_ask_dm(self, sm: GameStateMachine) -> None:
        assert sm.can_act("ask_dm") is False

    def test_opening_forbids_search(self, sm: GameStateMachine) -> None:
        assert sm.can_act("search") is False

    def test_investigation_allows_ask_dm(self, sm: GameStateMachine) -> None:
        sm.current_phase = "investigation_1"
        assert sm.can_act("ask_dm") is True

    def test_investigation_allows_search(self, sm: GameStateMachine) -> None:
        sm.current_phase = "investigation_1"
        assert sm.can_act("search") is True

    def test_investigation_allows_private_chat(self, sm: GameStateMachine) -> None:
        sm.current_phase = "investigation_1"
        assert sm.can_act("private_chat") is True

    def test_investigation_forbids_cast_vote(self, sm: GameStateMachine) -> None:
        sm.current_phase = "investigation_1"
        assert sm.can_act("cast_vote") is False

    def test_discussion_allows_public_chat(self, sm: GameStateMachine) -> None:
        sm.current_phase = "discussion"
        assert sm.can_act("public_chat") is True

    def test_discussion_forbids_ask_dm(self, sm: GameStateMachine) -> None:
        sm.current_phase = "discussion"
        assert sm.can_act("ask_dm") is False

    def test_voting_allows_cast_vote(self, sm: GameStateMachine) -> None:
        sm.current_phase = "voting"
        assert sm.can_act("cast_vote") is True

    def test_voting_forbids_public_chat(self, sm: GameStateMachine) -> None:
        sm.current_phase = "voting"
        assert sm.can_act("public_chat") is False

    def test_reveal_allows_listen(self, sm: GameStateMachine) -> None:
        sm.current_phase = "reveal"
        assert sm.can_act("listen") is True

    def test_reveal_forbids_cast_vote(self, sm: GameStateMachine) -> None:
        sm.current_phase = "reveal"
        assert sm.can_act("cast_vote") is False

    def test_unknown_action_returns_false(self, sm: GameStateMachine) -> None:
        assert sm.can_act("nonexistent_action") is False


# ---------------------------------------------------------------------------
# Phase transitions
# ---------------------------------------------------------------------------


class TestAdvance:
    def test_opening_to_reading(self, sm: GameStateMachine) -> None:
        next_phase = sm.advance()
        assert next_phase == "reading"
        assert sm.current_phase == "reading"

    def test_full_sequence(self, sm: GameStateMachine) -> None:
        sequence = ["reading", "investigation_1", "discussion", "voting", "reveal"]
        for expected in sequence:
            result = sm.advance()
            assert result == expected
            assert sm.current_phase == expected

    def test_advance_from_terminal_returns_none(self, sm: GameStateMachine) -> None:
        sm.current_phase = "reveal"
        result = sm.advance()
        assert result is None
        assert sm.current_phase == "reveal"  # stays put

    def test_advance_resets_timer(self, sm: GameStateMachine) -> None:
        before = sm.started_at
        time.sleep(0.01)
        sm.advance()
        assert sm.started_at > before

    def test_advance_to_missing_phase_raises(self) -> None:
        phases = make_phases([
            {"id": "a", "type": "narration", "next": "b", "allowed_actions": set()},
        ])
        sm = GameStateMachine(phases)
        with pytest.raises(KeyError):
            sm.advance()


# ---------------------------------------------------------------------------
# Timer helpers
# ---------------------------------------------------------------------------


class TestTimer:
    def test_time_remaining_is_positive_at_start(self, sm: GameStateMachine) -> None:
        remaining = sm.time_remaining()
        assert 0 < remaining <= 120

    def test_time_remaining_decreases_over_time(self, sm: GameStateMachine) -> None:
        r1 = sm.time_remaining()
        time.sleep(0.02)
        r2 = sm.time_remaining()
        assert r2 < r1

    def test_time_remaining_never_negative(self, sm: GameStateMachine) -> None:
        sm.started_at = time.time() - 9999  # simulate long time ago
        assert sm.time_remaining() == 0.0

    def test_unlimited_phase_returns_inf(self, sm: GameStateMachine) -> None:
        sm.current_phase = "reveal"
        assert sm.time_remaining() == float("inf")

    def test_is_timed_out_false_at_start(self, sm: GameStateMachine) -> None:
        assert sm.is_timed_out() is False

    def test_is_timed_out_true_after_expiry(self, sm: GameStateMachine) -> None:
        sm.started_at = time.time() - 9999
        assert sm.is_timed_out() is True

    def test_unlimited_phase_never_times_out(self, sm: GameStateMachine) -> None:
        sm.current_phase = "reveal"
        assert sm.is_timed_out() is False


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------


class TestCurrentAndIsTerminal:
    def test_current_returns_phase_object(self, sm: GameStateMachine) -> None:
        phase = sm.current()
        assert phase.id == "opening"
        assert phase.type == "narration"

    def test_is_terminal_false_for_opening(self, sm: GameStateMachine) -> None:
        assert sm.is_terminal() is False

    def test_is_terminal_true_for_reveal(self, sm: GameStateMachine) -> None:
        sm.current_phase = "reveal"
        assert sm.is_terminal() is True

    def test_is_terminal_false_for_investigation(self, sm: GameStateMachine) -> None:
        sm.current_phase = "investigation_1"
        assert sm.is_terminal() is False


# ---------------------------------------------------------------------------
# Named tests explicitly required by spec
# ---------------------------------------------------------------------------


def test_phase_progression() -> None:
    """Full sequence: opening → reading → investigation_1 → discussion → voting → reveal."""
    sm = GameStateMachine(FULL_PHASES)
    sequence = ["reading", "investigation_1", "discussion", "voting", "reveal"]
    for expected in sequence:
        result = sm.advance()
        assert result == expected, f"Expected {expected!r}, got {result!r}"
    assert sm.current_phase == "reveal"


def test_allowed_actions() -> None:
    """cast_vote is blocked in discussion; search is blocked in voting phase."""
    sm = GameStateMachine(FULL_PHASES)

    sm.current_phase = "discussion"
    assert sm.can_act("cast_vote") is False, "cast_vote must be blocked in discussion"
    assert sm.can_act("public_chat") is True  # sanity: discussion allows public_chat

    sm.current_phase = "voting"
    assert sm.can_act("search") is False, "search must be blocked in voting"
    assert sm.can_act("cast_vote") is True  # sanity: voting allows cast_vote


def test_timeout_auto_advance() -> None:
    """Phase with duration_seconds=1 is marked timed-out after 1 second elapses;
    calling advance() then moves to the next phase (simulating ws.py auto-advance)."""
    phases = make_phases([
        {
            "id": "quick",
            "type": "narration",
            "next": "after_quick",
            "duration_seconds": 1,
            "allowed_actions": set(),
        },
        {
            "id": "after_quick",
            "type": "narration",
            "next": None,
            "duration_seconds": None,
            "allowed_actions": set(),
        },
    ])
    sm = GameStateMachine(phases)
    assert sm.is_timed_out() is False, "should not be timed out immediately"

    # Wind back the clock to simulate 2s elapsed
    sm.started_at -= 2

    assert sm.is_timed_out() is True, "should be timed out after duration expires"
    next_phase = sm.advance()
    assert next_phase == "after_quick"
    assert sm.current_phase == "after_quick"
    # Timer reset after advance
    assert sm.is_timed_out() is False


def test_cannot_advance_past_reveal() -> None:
    """advance() returns None and stays in reveal when already at the terminal phase."""
    sm = GameStateMachine(FULL_PHASES)
    sm.current_phase = "reveal"
    result = sm.advance()
    assert result is None
    assert sm.current_phase == "reveal"


def test_phase_duration_tracking() -> None:
    """time_remaining() decreases as time passes and matches elapsed seconds."""
    phases = make_phases([
        {
            "id": "timed",
            "type": "narration",
            "next": None,
            "duration_seconds": 60,
            "allowed_actions": set(),
        },
    ])
    sm = GameStateMachine(phases)
    r1 = sm.time_remaining()
    assert r1 <= 60

    # Simulate 5 seconds elapsed by winding back started_at
    sm.started_at -= 5
    r2 = sm.time_remaining()

    assert r2 < r1, "time_remaining should decrease over time"
    assert abs((r1 - r2) - 5) < 0.2, f"expected ~5s decrease, got {r1 - r2:.3f}s"
