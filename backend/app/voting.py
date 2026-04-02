"""VotingModule — deterministic vote collection and resolution for Phase 4.

Design (from CLAUDE.md):
- Pure logic, no LLM calls, no async IO.
- One vote per player, enforced here.
- Votes are secret until all collected (or reveal is called).
- Tiebreaker: when two or more candidates are tied, a runoff is required.
- The state machine enforces: voting only in voting phase.  VotingModule does
  NOT check the phase — that guard lives in the orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class VoteStatus(StrEnum):
    OPEN = "open"  # still collecting votes
    DECIDED = "decided"  # one winner found, no tie
    TIE = "tie"  # tie — runoff needed
    RUNOFF = "runoff"  # runoff vote in progress
    RUNOFF_TIE = "runoff_tie"  # runoff still tied → random/DM decides
    CLOSED = "closed"  # final result recorded


class VoteError(Exception):
    """Raised for invalid voting actions (duplicate vote, wrong phase, etc.)."""


@dataclass
class VoteResult:
    """Immutable result returned after all votes are in."""

    status: VoteStatus
    winner: str | None  # character_id of the winner, or None if unresolved tie
    tally: dict[str, int]  # character_id → vote count (only tied candidates in runoff)
    is_correct: bool = False  # set by caller after comparing with truth.culprit


class VotingModule:
    """Collects and resolves player votes.  One instance per game session.

    Parameters
    ----------
    player_ids : list[str]
        All player IDs expected to vote.  Used to determine when voting is complete.
    culprit_id : str
        The correct answer (truth.culprit).  Used only for is_correct calculation —
        NEVER exposed to players before reveal.
    """

    def __init__(self, player_ids: list[str], culprit_id: str) -> None:
        if not player_ids:
            raise ValueError("VotingModule requires at least one player")
        self._player_ids: frozenset[str] = frozenset(player_ids)
        self._culprit_id = culprit_id

        # player_id → character_id (the suspect they voted for)
        self._votes: dict[str, str] = {}
        # During runoff: only these candidates are eligible
        self._runoff_candidates: frozenset[str] = frozenset()
        self._runoff_votes: dict[str, str] = {}

        self.status: VoteStatus = VoteStatus.OPEN

    # ------------------------------------------------------------------
    # Public API — voting actions
    # ------------------------------------------------------------------

    def cast_vote(self, player_id: str, target_character_id: str) -> None:
        """Record a vote from *player_id* for *target_character_id*.

        Raises
        ------
        VoteError
            If the player is unknown, has already voted, or voting is not open.
        """
        if self.status not in (VoteStatus.OPEN, VoteStatus.RUNOFF):
            raise VoteError(f"Voting is not open (status={self.status.value})")
        if player_id not in self._player_ids:
            raise VoteError(f"Unknown player: {player_id!r}")

        if self.status == VoteStatus.OPEN:
            if player_id in self._votes:
                raise VoteError(f"Player {player_id!r} has already voted")
            self._votes[player_id] = target_character_id
        else:  # RUNOFF
            if player_id in self._runoff_votes:
                raise VoteError(f"Player {player_id!r} has already voted in the runoff")
            if target_character_id not in self._runoff_candidates:
                raise VoteError(f"Invalid runoff candidate: {target_character_id!r}. Choose from: {sorted(self._runoff_candidates)}")
            self._runoff_votes[player_id] = target_character_id

    def all_voted(self) -> bool:
        """Return True if every expected player has voted in the current round."""
        if self.status == VoteStatus.RUNOFF:
            return set(self._runoff_votes.keys()) == self._player_ids
        return set(self._votes.keys()) == self._player_ids

    def resolve(self) -> VoteResult:
        """Tally votes and determine the outcome.

        Must be called after all_voted() returns True.  Updates self.status.

        Returns
        -------
        VoteResult
            If there is a clear winner: status=DECIDED, winner=<char_id>.
            If there is a tie: status=TIE, winner=None, tally=tied candidates only.
            After a runoff: status=DECIDED or RUNOFF_TIE.
        """
        if not self.all_voted():
            raise VoteError("Cannot resolve: not all players have voted yet")

        if self.status == VoteStatus.OPEN:
            tally = self._count(self._votes)
            return self._resolve_tally(tally, after_runoff=False)
        elif self.status == VoteStatus.RUNOFF:
            tally = self._count(self._runoff_votes)
            return self._resolve_tally(tally, after_runoff=True)
        else:
            raise VoteError(f"resolve() called in unexpected status: {self.status.value}")

    def start_runoff(self, candidates: list[str]) -> None:
        """Begin a runoff vote restricted to *candidates*.

        Called by the orchestrator after resolve() returns status=TIE.
        Resets runoff ballot.
        """
        if not candidates:
            raise VoteError("Runoff requires at least one candidate")
        self._runoff_candidates = frozenset(candidates)
        self._runoff_votes = {}
        self.status = VoteStatus.RUNOFF

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def vote_count(self) -> int:
        """Number of votes cast in the current round."""
        if self.status == VoteStatus.RUNOFF:
            return len(self._runoff_votes)
        return len(self._votes)

    def get_tally(self) -> dict[str, int]:
        """Current tally (public, for display after reveal)."""
        if self.status == VoteStatus.RUNOFF:
            return self._count(self._runoff_votes)
        return self._count(self._votes)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _count(self, votes: dict[str, str]) -> dict[str, int]:
        """Build a character_id → vote_count dict from a votes mapping."""
        tally: dict[str, int] = {}
        for target in votes.values():
            tally[target] = tally.get(target, 0) + 1
        return tally

    def _resolve_tally(self, tally: dict[str, int], *, after_runoff: bool) -> VoteResult:
        if not tally:
            # Edge case: no votes cast at all
            self.status = VoteStatus.CLOSED
            return VoteResult(status=VoteStatus.CLOSED, winner=None, tally=tally)

        max_votes = max(tally.values())
        winners = [cid for cid, cnt in tally.items() if cnt == max_votes]

        if len(winners) == 1:
            winner = winners[0]
            self.status = VoteStatus.CLOSED
            return VoteResult(
                status=VoteStatus.DECIDED,
                winner=winner,
                tally=tally,
                is_correct=(winner == self._culprit_id),
            )

        # Tie
        if after_runoff:
            self.status = VoteStatus.RUNOFF_TIE
            return VoteResult(
                status=VoteStatus.RUNOFF_TIE,
                winner=None,
                tally={cid: cnt for cid, cnt in tally.items() if cnt == max_votes},
            )

        self.status = VoteStatus.TIE
        return VoteResult(
            status=VoteStatus.TIE,
            winner=None,
            tally={cid: cnt for cid, cnt in tally.items() if cnt == max_votes},
        )
