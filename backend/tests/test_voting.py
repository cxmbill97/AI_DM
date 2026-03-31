"""Tests for VotingModule — Phase 4 deterministic vote collection and resolution.

Covers:
- Basic vote casting and retrieval
- One-vote-per-player enforcement
- Unknown player rejection
- all_voted() tracking
- resolve() with a clear winner
- resolve() with a tie → TIE status
- start_runoff() + runoff voting
- Runoff with a winner
- Runoff tie (RUNOFF_TIE)
- is_correct flag matches culprit_id
- Edge cases: no votes, single player
"""

from __future__ import annotations

import pytest

from app.voting import VoteError, VoteResult, VoteStatus, VotingModule


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


PLAYERS = ["p1", "p2", "p3", "p4"]
CULPRIT = "char_shen"


@pytest.fixture
def vm() -> VotingModule:
    return VotingModule(player_ids=PLAYERS, culprit_id=CULPRIT)


# ---------------------------------------------------------------------------
# Basic voting
# ---------------------------------------------------------------------------


class TestBasicVoting:
    def test_initial_status_is_open(self, vm: VotingModule) -> None:
        assert vm.status == VoteStatus.OPEN

    def test_cast_vote_succeeds(self, vm: VotingModule) -> None:
        vm.cast_vote("p1", "char_su")
        assert vm.vote_count() == 1

    def test_all_players_can_vote(self, vm: VotingModule) -> None:
        for i, player in enumerate(PLAYERS):
            vm.cast_vote(player, f"char_{i}")
        assert vm.vote_count() == 4

    def test_all_voted_false_before_everyone_votes(self, vm: VotingModule) -> None:
        vm.cast_vote("p1", "char_su")
        assert vm.all_voted() is False

    def test_all_voted_true_after_everyone_votes(self, vm: VotingModule) -> None:
        for player in PLAYERS:
            vm.cast_vote(player, CULPRIT)
        assert vm.all_voted() is True

    def test_get_tally_reflects_votes(self, vm: VotingModule) -> None:
        vm.cast_vote("p1", "char_su")
        vm.cast_vote("p2", "char_su")
        vm.cast_vote("p3", "char_shen")
        tally = vm.get_tally()
        assert tally["char_su"] == 2
        assert tally["char_shen"] == 1


# ---------------------------------------------------------------------------
# Validation — duplicate vote, unknown player
# ---------------------------------------------------------------------------


class TestVoteValidation:
    def test_duplicate_vote_raises(self, vm: VotingModule) -> None:
        vm.cast_vote("p1", "char_su")
        with pytest.raises(VoteError, match="already voted"):
            vm.cast_vote("p1", "char_su")

    def test_unknown_player_raises(self, vm: VotingModule) -> None:
        with pytest.raises(VoteError, match="Unknown player"):
            vm.cast_vote("stranger", "char_su")

    def test_voting_when_closed_raises(self, vm: VotingModule) -> None:
        for player in PLAYERS:
            vm.cast_vote(player, CULPRIT)
        vm.resolve()  # closes the vote
        with pytest.raises(VoteError, match="not open"):
            vm.cast_vote("p1", CULPRIT)


# ---------------------------------------------------------------------------
# Resolve — clear winner
# ---------------------------------------------------------------------------


class TestResolveWinner:
    def test_majority_winner_decided(self, vm: VotingModule) -> None:
        vm.cast_vote("p1", CULPRIT)
        vm.cast_vote("p2", CULPRIT)
        vm.cast_vote("p3", CULPRIT)
        vm.cast_vote("p4", "char_su")
        result = vm.resolve()
        assert result.status == VoteStatus.DECIDED
        assert result.winner == CULPRIT

    def test_decided_sets_status_closed(self, vm: VotingModule) -> None:
        for player in PLAYERS:
            vm.cast_vote(player, CULPRIT)
        vm.resolve()
        assert vm.status == VoteStatus.CLOSED

    def test_correct_culprit_is_correct_true(self, vm: VotingModule) -> None:
        for player in PLAYERS:
            vm.cast_vote(player, CULPRIT)
        result = vm.resolve()
        assert result.is_correct is True

    def test_wrong_culprit_is_correct_false(self, vm: VotingModule) -> None:
        for player in PLAYERS:
            vm.cast_vote(player, "char_su")
        result = vm.resolve()
        assert result.is_correct is False

    def test_resolve_before_all_voted_raises(self, vm: VotingModule) -> None:
        vm.cast_vote("p1", CULPRIT)
        with pytest.raises(VoteError, match="not all players"):
            vm.resolve()

    def test_tally_in_result(self, vm: VotingModule) -> None:
        vm.cast_vote("p1", CULPRIT)
        vm.cast_vote("p2", CULPRIT)
        vm.cast_vote("p3", "char_su")
        vm.cast_vote("p4", "char_su")
        # This will be a tie, but we inspect the tally field
        result = vm.resolve()
        assert result.tally[CULPRIT] == 2
        assert result.tally["char_su"] == 2


# ---------------------------------------------------------------------------
# Resolve — tie
# ---------------------------------------------------------------------------


class TestResolveTie:
    def test_two_way_tie_returns_tie_status(self, vm: VotingModule) -> None:
        vm.cast_vote("p1", CULPRIT)
        vm.cast_vote("p2", CULPRIT)
        vm.cast_vote("p3", "char_su")
        vm.cast_vote("p4", "char_su")
        result = vm.resolve()
        assert result.status == VoteStatus.TIE
        assert result.winner is None

    def test_tie_tally_contains_only_tied_candidates(self, vm: VotingModule) -> None:
        vm.cast_vote("p1", CULPRIT)
        vm.cast_vote("p2", CULPRIT)
        vm.cast_vote("p3", "char_su")
        vm.cast_vote("p4", "char_su")
        result = vm.resolve()
        assert set(result.tally.keys()) == {CULPRIT, "char_su"}

    def test_three_way_tie(self) -> None:
        vm = VotingModule(player_ids=["p1", "p2", "p3"], culprit_id=CULPRIT)
        vm.cast_vote("p1", "char_a")
        vm.cast_vote("p2", "char_b")
        vm.cast_vote("p3", "char_c")
        result = vm.resolve()
        assert result.status == VoteStatus.TIE
        assert len(result.tally) == 3

    def test_tie_sets_status_to_tie(self, vm: VotingModule) -> None:
        vm.cast_vote("p1", CULPRIT)
        vm.cast_vote("p2", CULPRIT)
        vm.cast_vote("p3", "char_su")
        vm.cast_vote("p4", "char_su")
        vm.resolve()
        assert vm.status == VoteStatus.TIE


# ---------------------------------------------------------------------------
# Runoff voting
# ---------------------------------------------------------------------------


class TestRunoff:
    def _setup_tie(self, vm: VotingModule) -> None:
        vm.cast_vote("p1", CULPRIT)
        vm.cast_vote("p2", CULPRIT)
        vm.cast_vote("p3", "char_su")
        vm.cast_vote("p4", "char_su")
        vm.resolve()  # → TIE

    def test_start_runoff_changes_status(self, vm: VotingModule) -> None:
        self._setup_tie(vm)
        vm.start_runoff([CULPRIT, "char_su"])
        assert vm.status == VoteStatus.RUNOFF

    def test_runoff_resets_ballot(self, vm: VotingModule) -> None:
        self._setup_tie(vm)
        vm.start_runoff([CULPRIT, "char_su"])
        assert vm.vote_count() == 0

    def test_runoff_invalid_candidate_raises(self, vm: VotingModule) -> None:
        self._setup_tie(vm)
        vm.start_runoff([CULPRIT, "char_su"])
        with pytest.raises(VoteError, match="Invalid runoff candidate"):
            vm.cast_vote("p1", "char_chen")

    def test_runoff_valid_candidate_accepted(self, vm: VotingModule) -> None:
        self._setup_tie(vm)
        vm.start_runoff([CULPRIT, "char_su"])
        vm.cast_vote("p1", CULPRIT)
        assert vm.vote_count() == 1

    def test_runoff_duplicate_vote_raises(self, vm: VotingModule) -> None:
        self._setup_tie(vm)
        vm.start_runoff([CULPRIT, "char_su"])
        vm.cast_vote("p1", CULPRIT)
        with pytest.raises(VoteError, match="already voted"):
            vm.cast_vote("p1", CULPRIT)

    def test_runoff_winner_decided(self, vm: VotingModule) -> None:
        self._setup_tie(vm)
        vm.start_runoff([CULPRIT, "char_su"])
        vm.cast_vote("p1", CULPRIT)
        vm.cast_vote("p2", CULPRIT)
        vm.cast_vote("p3", CULPRIT)
        vm.cast_vote("p4", "char_su")
        result = vm.resolve()
        assert result.status == VoteStatus.DECIDED
        assert result.winner == CULPRIT
        assert result.is_correct is True

    def test_runoff_tie_returns_runoff_tie(self, vm: VotingModule) -> None:
        self._setup_tie(vm)
        vm.start_runoff([CULPRIT, "char_su"])
        vm.cast_vote("p1", CULPRIT)
        vm.cast_vote("p2", CULPRIT)
        vm.cast_vote("p3", "char_su")
        vm.cast_vote("p4", "char_su")
        result = vm.resolve()
        assert result.status == VoteStatus.RUNOFF_TIE
        assert result.winner is None

    def test_start_runoff_empty_candidates_raises(self, vm: VotingModule) -> None:
        self._setup_tie(vm)
        with pytest.raises(VoteError, match="at least one candidate"):
            vm.start_runoff([])


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_player_game(self) -> None:
        vm = VotingModule(player_ids=["solo"], culprit_id=CULPRIT)
        vm.cast_vote("solo", CULPRIT)
        assert vm.all_voted() is True
        result = vm.resolve()
        assert result.status == VoteStatus.DECIDED
        assert result.winner == CULPRIT

    def test_no_players_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one player"):
            VotingModule(player_ids=[], culprit_id=CULPRIT)

    def test_all_vote_for_different_candidates(self) -> None:
        vm = VotingModule(player_ids=["p1", "p2"], culprit_id=CULPRIT)
        vm.cast_vote("p1", "char_a")
        vm.cast_vote("p2", "char_b")
        result = vm.resolve()
        assert result.status == VoteStatus.TIE


# ---------------------------------------------------------------------------
# Named tests explicitly required by spec (standalone functions)
# ---------------------------------------------------------------------------


def test_cast_vote_success() -> None:
    vm = VotingModule(player_ids=["p1", "p2"], culprit_id=CULPRIT)
    vm.cast_vote("p1", "char_x")
    assert vm.vote_count() == 1


def test_double_vote_rejected() -> None:
    vm = VotingModule(player_ids=["p1", "p2"], culprit_id=CULPRIT)
    vm.cast_vote("p1", "char_x")
    with pytest.raises(VoteError, match="already voted"):
        vm.cast_vote("p1", "char_x")


def test_invalid_target_rejected() -> None:
    """Unknown player id must be rejected."""
    vm = VotingModule(player_ids=["p1"], culprit_id=CULPRIT)
    with pytest.raises(VoteError, match="Unknown player"):
        vm.cast_vote("unknown_stranger", "char_x")


def test_correct_identification() -> None:
    """Voting for the true culprit yields is_correct=True."""
    vm = VotingModule(player_ids=["p1", "p2"], culprit_id=CULPRIT)
    vm.cast_vote("p1", CULPRIT)
    vm.cast_vote("p2", CULPRIT)
    result = vm.resolve()
    assert result.is_correct is True


def test_wrong_identification() -> None:
    """Voting for an innocent character yields is_correct=False."""
    vm = VotingModule(player_ids=["p1", "p2"], culprit_id=CULPRIT)
    vm.cast_vote("p1", "char_innocent")
    vm.cast_vote("p2", "char_innocent")
    result = vm.resolve()
    assert result.is_correct is False


def test_tally_with_tie() -> None:
    """Two-way tie yields TIE status, no winner, and correct vote counts."""
    vm = VotingModule(player_ids=["p1", "p2", "p3", "p4"], culprit_id=CULPRIT)
    vm.cast_vote("p1", CULPRIT)
    vm.cast_vote("p2", CULPRIT)
    vm.cast_vote("p3", "char_su")
    vm.cast_vote("p4", "char_su")
    result = vm.resolve()
    assert result.status == VoteStatus.TIE
    assert result.winner is None
    assert result.tally[CULPRIT] == 2
    assert result.tally["char_su"] == 2


def test_all_voted_check() -> None:
    """all_voted() transitions False → False → True as each player votes."""
    vm = VotingModule(player_ids=["p1", "p2", "p3"], culprit_id=CULPRIT)
    vm.cast_vote("p1", "char_x")
    assert vm.all_voted() is False
    vm.cast_vote("p2", "char_x")
    assert vm.all_voted() is False
    vm.cast_vote("p3", "char_x")
    assert vm.all_voted() is True
