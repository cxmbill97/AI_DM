"""Deterministic phase state machine for murder mystery (Phase 4).

Design principles (from CLAUDE.md):
- Transitions are PURE: no LLM calls, no async IO, no side effects.
- advance() is only called by the room orchestrator, never by the LLM.
- The state machine owns: allowed actions, phase transitions, timers.
- LLM agents propose actions; the runtime validates here before executing.

Usage::

    sm = GameStateMachine(script.phases)
    if sm.can_act("ask_dm"):
        ...
    if sm.is_timed_out():
        next_phase = sm.advance()
"""

from __future__ import annotations

import time

from app.models import Phase


class GameStateMachine:
    """Phase state machine loaded from a Script's phases list.

    Attributes
    ----------
    current_phase : str
        ID of the active phase.
    phases : dict[str, Phase]
        All phases indexed by id (built from the script's phase list).
    started_at : float
        Unix timestamp when the current phase began.
    """

    def __init__(self, phases: list[Phase]) -> None:
        if not phases:
            raise ValueError("GameStateMachine requires at least one phase")
        # Build index preserving list order; first phase is the starting phase.
        self.phases: dict[str, Phase] = {p.id: p for p in phases}
        self.current_phase: str = phases[0].id
        self.started_at: float = time.time()

    # ------------------------------------------------------------------
    # Action guard — called before any LLM dispatch
    # ------------------------------------------------------------------

    def can_act(self, action: str) -> bool:
        """Return True if *action* is permitted in the current phase."""
        return action in self.phases[self.current_phase].allowed_actions

    # ------------------------------------------------------------------
    # Phase transition
    # ------------------------------------------------------------------

    def advance(self) -> str | None:
        """Move to the next phase and return its id, or None if game over.

        Resets the phase timer.  Must be called only by the room orchestrator
        after all pre-conditions are satisfied (clues found, votes collected,
        or timeout fired).  This method has no side effects beyond mutating
        current_phase and started_at.
        """
        next_id = self.phases[self.current_phase].next
        if next_id is None:
            return None  # already at the terminal phase
        if next_id not in self.phases:
            raise KeyError(f"Phase {next_id!r} referenced by {self.current_phase!r} does not exist")
        self.current_phase = next_id
        self.started_at = time.time()
        return next_id

    # ------------------------------------------------------------------
    # Timer helpers
    # ------------------------------------------------------------------

    def time_remaining(self) -> float:
        """Seconds until the current phase times out.

        Returns float('inf') if the current phase has no duration limit.
        Never returns a negative number.
        """
        duration = self.phases[self.current_phase].duration_seconds
        if duration is None:
            return float("inf")
        elapsed = time.time() - self.started_at
        return max(0.0, duration - elapsed)

    def is_timed_out(self) -> bool:
        """Return True if the current phase has exceeded its duration."""
        return self.time_remaining() <= 0

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def current(self) -> Phase:
        """Return the Phase object for the current phase."""
        return self.phases[self.current_phase]

    def is_terminal(self) -> bool:
        """Return True if the current phase has no successor (game over)."""
        return self.phases[self.current_phase].next is None
