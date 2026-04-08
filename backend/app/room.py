"""Multiplayer room manager — supports both turtle soup (Phase 2-3) and
murder mystery (Phase 4).

game_type="turtle_soup"  → uses Puzzle + GameSession + InterventionEngine
game_type="murder_mystery" → uses Script + GameStateMachine + AgentOrchestrator + VotingModule
"""

from __future__ import annotations

import asyncio
import random
import string
import time
from typing import TYPE_CHECKING, Any

from app.intervention import InterventionEngine
from app.models import HINTS_PER_GAME, GameSession, Puzzle, Script

if TYPE_CHECKING:
    from fastapi import WebSocket

    from app.agents.orchestrator import AgentOrchestrator
    from app.state_machine import GameStateMachine
    from app.voting import VotingModule

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_PLAYERS = 6
RECONNECT_WINDOW_SECS = 60  # grace period to reclaim a disconnected seat
# HINTS_PER_GAME is defined in models.py (imported above) so RoomState can reference it

# Turn-based timing constants (Phase 0)
TURN_HINT_SECS = 20    # warn + offer hint after this many seconds of inactivity
TURN_TIMEOUT_SECS = 30  # auto-skip after this many seconds of inactivity


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------


class Room:
    """A single multiplayer game room.

    Supports both turtle_soup and murder_mystery game types.
    turtle_soup fields (puzzle, game_session) are None for murder_mystery rooms,
    and vice versa.
    """

    def __init__(
        self,
        room_id: str,
        puzzle: Puzzle | None = None,
        script: Script | None = None,
        language: str = "zh",
    ) -> None:
        if puzzle is None and script is None:
            raise ValueError("Room requires either a puzzle or a script")

        self.room_id = room_id
        self.language: str = language
        self.game_type: str = "murder_mystery" if script is not None else "turtle_soup"

        # ---- Turtle soup state ----
        self.puzzle: Puzzle | None = puzzle
        self.game_session: GameSession | None = None

        # ---- Murder mystery state ----
        self.script: Script | None = script
        self.state_machine: GameStateMachine | None = None
        self.orchestrator: AgentOrchestrator | None = None
        self.voting: VotingModule | None = None
        # player_id → character_id (assigned in join order)
        self._char_assignments: dict[str, str] = {}
        # True once the opening narration has been broadcast
        self._opening_narrated: bool = False
        # player_ids who voted to skip the current phase; reset on phase change
        self._skip_votes: set[str] = set()
        # Reconstruction mode state
        self._reconstruction_q_index: int = 0  # current question index
        self._reconstruction_score: int = 0  # accumulated score (0-12 for 6 questions)
        self._reconstruction_answers: list[dict] = []  # {q_id, player_name, answer, result, score}

        # ---- Shared state ----
        # player_id → PlayerSlot dict
        self.players: dict[str, dict[str, Any]] = {}

        # Full chronological log; used to replay missed messages on reconnect
        self.message_history: list[dict[str, Any]] = []

        # Serialize concurrent DM turns / orchestrator calls
        self._lock = asyncio.Lock()

        # Proactive DM intervention engine
        self.intervention = InterventionEngine(self)

        # Background tick task — created and cancelled by ws.py
        self._tick_task: asyncio.Task | None = None

        # ---- Lobby state ----
        self.started: bool = False
        self.host_user_id: str | None = None   # set by main.py after creation
        self.host_player_id: str | None = None  # set to first player that joins
        self.ready_players: set[str] = set()    # player_ids who clicked Ready
        # max_players: script specifies it for murder_mystery, turtle_soup caps at 4
        self.max_players: int = (
            script.metadata.player_count if script is not None else 4
        )

        # ---- Phase 0: Turn-based system ----
        # Enabled by passing turn_mode=True when creating the room.
        self.turn_mode: bool = False
        # Ordered list of player_ids for turn rotation (populated on game start).
        self.turn_order: list[str] = []
        # Index into turn_order pointing at the player whose turn it is.
        self.current_turn_index: int = 0
        # Wall-clock timestamp when the current turn began (None = not started).
        self.turn_started_at: float | None = None
        # Whether the 20-second hint warning has already been sent this turn.
        self._turn_hint_sent: bool = False
        # player_id of the player who solved the puzzle (None until game over).
        self.winner_player_id: str | None = None

        # ---- Phase 1: Hint system ----
        self.hints_remaining: int = HINTS_PER_GAME

        # ---- Phase 1: Skip system ----
        # player_ids who voted to skip the current turtle-soup puzzle
        self._puzzle_skip_votes: set[str] = set()

        # ---- Phase 1: Spectators ----
        self.spectators: dict[str, dict[str, Any]] = {}  # player_id → slot dict

        # ---- Phase 1: Player reporting (in-memory, per room) ----
        self.reports: list[dict[str, Any]] = []

        # ---- Phase 1: Anomaly detection ----
        # Simple substring flags (per player) and LLM-based detector
        self.suspicious_flags: dict[str, list[dict[str, Any]]] = {}
        self._anomaly_flags: list[dict[str, Any]] = []
        self._anomaly_detector: Any | None = None  # AnomalyDetector, lazily initialised

        # ---- Phase 2: Per-turn scoring ----
        self.player_scores: dict[str, int] = {}
        self.player_turn_counts: dict[str, int] = {}
        self._scores: dict[str, int] = {}  # verdict-based scores (record_turn_score)
        self.mvp_player_id: str | None = None

        # Initialise type-specific components
        if puzzle is not None:
            self.game_session = GameSession(
                session_id=room_id,
                puzzle=puzzle,
                history=[],
                language=language,
            )

        if script is not None:
            from app.agents.orchestrator import AgentOrchestrator
            from app.state_machine import GameStateMachine

            self.state_machine = GameStateMachine(script.phases)
            self.orchestrator = AgentOrchestrator(
                script=script,
                state_machine=self.state_machine,
                player_char_map={},
                language=language,
            )

    # ------------------------------------------------------------------
    # Player management
    # ------------------------------------------------------------------

    def _active_player_count(self) -> int:
        """Count players that are connected OR within the reconnect window."""
        now = time.time()
        return sum(1 for p in self.players.values() if p["connected"] or (now - p["last_seen"]) < RECONNECT_WINDOW_SECS)

    def is_full(self) -> bool:
        return self._active_player_count() >= self.max_players

    def find_player_by_name(self, name: str) -> str | None:
        """Return the player_id for a given name, or None."""
        for pid, p in self.players.items():
            if p["name"] == name:
                return pid
        return None

    def _assign_player_slot(self, player_id: str) -> str:
        """Assign the next available player_N slot (turtle soup only)."""
        assert self.game_session is not None
        used = set(self.game_session.player_slot_map.values())
        n = 1
        while f"player_{n}" in used:
            n += 1
        slot = f"player_{n}"
        self.game_session.player_slot_map[player_id] = slot
        return slot

    def _assign_character(self, player_id: str) -> str | None:
        """Assign the next available character to a player (murder mystery only).

        Characters are assigned in the order they appear in script.characters.
        Returns the assigned character_id, or None if all characters are taken.
        """
        if self.script is None:
            return None
        assigned = set(self._char_assignments.values())
        for char in self.script.characters:
            if char.id not in assigned:
                self._char_assignments[player_id] = char.id
                # Keep orchestrator's player_char_map in sync
                if self.orchestrator is not None:
                    self.orchestrator._player_char_map[player_id] = char.id
                return char.id
        return None  # all characters already assigned

    def add_player(self, player_id: str, name: str, websocket: WebSocket) -> None:
        self.players[player_id] = {
            "name": name,
            "websocket": websocket,
            "connected": True,
            "last_seen": time.time(),
            "send_lock": asyncio.Lock(),
        }
        if self.host_player_id is None:
            self.host_player_id = player_id
        if self.game_type == "turtle_soup":
            self._assign_player_slot(player_id)
        else:
            self._assign_character(player_id)

    def reconnect_player(self, player_id: str, websocket: WebSocket) -> None:
        slot = self.players[player_id]
        slot["websocket"] = websocket
        slot["connected"] = True
        slot["last_seen"] = time.time()

    def disconnect_player(self, player_id: str) -> None:
        slot = self.players.get(player_id)
        if slot:
            slot["connected"] = False
            slot["websocket"] = None
            slot["last_seen"] = time.time()

    def messages_since(self, timestamp: float) -> list[dict[str, Any]]:
        """Return all messages logged after *timestamp* (for reconnect replay)."""
        return [m for m in self.message_history if m.get("timestamp", 0) > timestamp]

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    async def _send_to_slot(self, slot: dict[str, Any], message: dict[str, Any]) -> None:
        """Send *message* to one player slot, holding that slot's send_lock."""
        if not slot["connected"] or slot["websocket"] is None:
            return
        try:
            async with slot["send_lock"]:
                await slot["websocket"].send_json(message)
        except Exception:
            pass

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send *message* as JSON to every currently-connected player and spectator."""
        all_slots = list(self.players.values()) + list(self.spectators.values())
        await asyncio.gather(*(self._send_to_slot(slot, message) for slot in all_slots))

    async def send_to(self, player_id: str, message: dict[str, Any]) -> None:
        """Send *message* to a single player only."""
        slot = self.players.get(player_id)
        if slot:
            await self._send_to_slot(slot, message)

    # ------------------------------------------------------------------
    # Phase 0: Turn-based helpers
    # ------------------------------------------------------------------

    def current_turn_player_id(self) -> str | None:
        """Return the player_id whose turn it currently is, or None if turn mode is off."""
        if not self.turn_mode or not self.turn_order:
            return None
        return self.turn_order[self.current_turn_index % len(self.turn_order)]

    def start_turns(self) -> None:
        """Initialise the turn order from currently-connected players and start the first turn.

        Must be called once when the host starts the game in turn_mode.
        Players are added in join order (dict insertion order, Python 3.7+).
        """
        self.turn_order = list(self.players.keys())
        self.current_turn_index = 0
        self.turn_started_at = time.time()
        self._turn_hint_sent = False

    def advance_turn(self) -> str | None:
        """Advance to the next player in the rotation and reset the turn timer.

        Returns the new current player_id, or None if turn_order is empty.
        """
        if not self.turn_order:
            return None
        self.current_turn_index = (self.current_turn_index + 1) % len(self.turn_order)
        self.turn_started_at = time.time()
        self._turn_hint_sent = False
        return self.current_turn_player_id()

    def turn_elapsed(self) -> float:
        """Seconds elapsed since the current turn started (0.0 if not started)."""
        if self.turn_started_at is None:
            return 0.0
        return time.time() - self.turn_started_at

    # ------------------------------------------------------------------
    # Phase 2: Per-turn scoring
    # ------------------------------------------------------------------

    def record_score(self, player_id: str, points: int) -> None:
        """Add *points* to *player_id*'s total and increment their turn count."""
        self.player_scores[player_id] = self.player_scores.get(player_id, 0) + points
        self.player_turn_counts[player_id] = self.player_turn_counts.get(player_id, 0) + 1

    def record_turn_score(
        self,
        player_id: str,
        verdict: str,
        hints_used: int = 0,
        elapsed_seconds: float = 30,
    ) -> int:
        """Score one turn by verdict, applying hint penalty and speed bonus.

        Returns the points awarded this turn.
        """
        base = {"irrelevant": 0, "relevant": 1, "close": 3, "correct": 10}.get(verdict, 0)
        penalty = hints_used  # −1 per hint
        bonus = 1 if elapsed_seconds < 10 else 0
        points = max(0, base - penalty) + bonus
        self._scores[player_id] = self._scores.get(player_id, 0) + points
        return points

    def get_player_scores(self) -> dict[str, int]:
        """Return verdict-based scores for all players."""
        return dict(self._scores)

    def get_leaderboard(self) -> list[dict[str, Any]]:
        """Return players sorted by total score desc (ties broken by fewest turns)."""
        rows = []
        for pid, score in self.player_scores.items():
            turns = self.player_turn_counts.get(pid, 0)
            name = self.players.get(pid, {}).get("name", pid)
            avg = round(score / turns, 2) if turns else 0.0
            rows.append({"player_id": pid, "player_name": name, "score": score, "turns": turns, "avg": avg})
        rows.sort(key=lambda r: (-r["score"], r["turns"]))
        return rows

    def compute_mvp(self) -> dict[str, Any] | None:
        """Return the player with the highest score (fewest turns on tie), or None.

        Uses _scores (verdict-based) for tiebreaking when player_scores are equal.
        Stores the winner's player_id in self.mvp_player_id.
        """
        all_scores = {**self.player_scores}
        for pid in self._scores:
            if pid not in all_scores:
                all_scores[pid] = 0
        if not all_scores:
            return None
        best_id = max(
            all_scores,
            key=lambda pid: (
                all_scores[pid],
                self._scores.get(pid, 0),
                -self.player_turn_counts.get(pid, 0),
            ),
        )
        self.mvp_player_id = best_id
        return {
            "player_id": best_id,
            "player_name": self.players.get(best_id, {}).get("name", best_id),
            "score": all_scores[best_id],
            "turns": self.player_turn_counts.get(best_id, 0),
        }

    # ------------------------------------------------------------------
    # Phase 1: Spectators
    # ------------------------------------------------------------------

    def add_spectator(self, player_id: str, name: str, websocket: Any) -> None:
        self.spectators[player_id] = {
            "name": name,
            "websocket": websocket,
            "connected": True,
            "last_seen": time.time(),
            "send_lock": asyncio.Lock(),
        }

    def disconnect_spectator(self, player_id: str) -> None:
        slot = self.spectators.get(player_id)
        if slot:
            slot["connected"] = False
            slot["websocket"] = None
            slot["last_seen"] = time.time()

    def reconnect_spectator(self, player_id: str, websocket: Any) -> None:
        slot = self.spectators.get(player_id)
        if slot:
            slot["websocket"] = websocket
            slot["connected"] = True
            slot["last_seen"] = time.time()

    @property
    def spectator_count(self) -> int:
        return sum(1 for s in self.spectators.values() if s["connected"])

    # ------------------------------------------------------------------
    # Phase 1: Anomaly detection
    # ------------------------------------------------------------------

    def get_anomaly_detector(self) -> Any | None:
        """Lazily create and return an AnomalyDetector for this room (turtle soup only)."""
        if self._anomaly_detector is not None:
            return self._anomaly_detector
        if self.puzzle is None or self.game_session is None:
            return None
        from app.anomaly import AnomalyDetector  # avoid circular import at module level
        self._anomaly_detector = AnomalyDetector(
            key_facts=self.puzzle.key_facts,
            truth=self.puzzle.truth,
        )
        return self._anomaly_detector

    # ------------------------------------------------------------------
    # Phase helpers (murder mystery)
    # ------------------------------------------------------------------

    def current_mm_phase(self) -> str | None:
        """Return the current phase id for murder mystery rooms, else None."""
        if self.state_machine is not None:
            return self.state_machine.current_phase
        return None

    def is_mm_game_over(self) -> bool:
        """True when the murder mystery has reached its terminal phase."""
        if self.state_machine is not None:
            return self.state_machine.is_terminal()
        return False

    # ------------------------------------------------------------------
    # Phase 1: Hint system
    # ------------------------------------------------------------------

    def use_hint(self, player_id: str) -> str | None:
        """Consume one hint token and return the next hint text.

        Returns None if the hint budget is exhausted, the puzzle has no hints,
        or all hints have already been given.
        Only valid for turtle_soup rooms.
        """
        if self.game_type != "turtle_soup":
            return None
        if self.hints_remaining <= 0:
            return None
        if self.puzzle is None or not self.puzzle.hints:
            return None
        idx = self.game_session.hint_index if self.game_session else 0
        if idx >= len(self.puzzle.hints):
            return None
        hint_text = self.puzzle.hints[idx]
        self.hints_remaining -= 1
        if self.game_session:
            self.game_session.hint_index = idx + 1
        return hint_text

    # ------------------------------------------------------------------
    # Phase 1: Skip system
    # ------------------------------------------------------------------

    def vote_skip_puzzle(self, player_id: str) -> bool:
        """Record a skip vote from *player_id*.

        Returns True when a majority (>50%) of active players have voted to
        skip and clears the vote set.  Only active players may vote; the call
        is idempotent (duplicate votes from the same player are ignored).
        """
        if player_id not in self.players:
            return False
        self._puzzle_skip_votes.add(player_id)
        active = self._active_player_count()
        if active > 0 and len(self._puzzle_skip_votes) > active / 2:
            self._puzzle_skip_votes.clear()
            return True
        return False

    def skip_votes_count(self) -> int:
        """Return current number of skip votes for the active puzzle."""
        return len(self._puzzle_skip_votes)

    def reset_to_puzzle(self, puzzle: Puzzle) -> None:
        """Swap in a new puzzle and reset all turtle-soup state.

        Called by ws.py after a successful skip vote.  Resets hint budget,
        skip votes, and the game session so the new puzzle starts fresh.
        """
        if self.game_type != "turtle_soup":
            return
        self.puzzle = puzzle
        self.game_session = GameSession(
            session_id=self.room_id,
            puzzle=puzzle,
            history=[],
            language=self.language,
        )
        for pid in self.players:
            self._assign_player_slot(pid)
        self.hints_remaining = HINTS_PER_GAME
        self._puzzle_skip_votes.clear()

    # ------------------------------------------------------------------
    # Phase 1: Player reporting
    # ------------------------------------------------------------------

    def report_player(self, reporter_id: str, target_id: str, reason: str) -> dict[str, Any]:
        """Store a report from *reporter_id* against *target_id*.

        Returns the stored report dict.
        """
        report: dict[str, Any] = {
            "reporter_id": reporter_id,
            "target_id": target_id,
            "reason": reason,
            "timestamp": time.time(),
        }
        self.reports.append(report)
        return report

    def get_reports(self, requester_id: str) -> list[dict[str, Any]]:
        """Return all reports.  Only the room host receives them; others get []."""
        if requester_id != self.host_player_id:
            return []
        return list(self.reports)

    # ------------------------------------------------------------------
    # Phase 1: Anomaly detection
    # ------------------------------------------------------------------

    def check_anomaly(self, player_id: str, text: str) -> list[str]:
        """Check whether *text* contains key phrases from the puzzle solution.

        Uses simple case-insensitive substring matching against puzzle.key_facts.
        Matched phrases are stored in suspicious_flags[player_id] and returned.
        Returns an empty list when no anomaly is detected or the room has no puzzle.
        """
        if self.puzzle is None:
            return []
        matched = [fact for fact in self.puzzle.key_facts if fact.lower() in text.lower()]
        if matched:
            if player_id not in self.suspicious_flags:
                self.suspicious_flags[player_id] = []
            self.suspicious_flags[player_id].append({
                "text": text,
                "matched_phrases": matched,
                "timestamp": time.time(),
            })
        return matched

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def phase(self) -> str:
        """High-level phase string for the room state endpoint."""
        if self.game_type == "turtle_soup":
            if self.game_session and self.game_session.finished:
                return "finished"
        elif self.game_type == "murder_mystery":
            if self.is_mm_game_over():
                return "finished"
        if any(p["connected"] for p in self.players.values()):
            return "playing"
        return "waiting"


# ---------------------------------------------------------------------------
# RoomManager — module-level singleton
# ---------------------------------------------------------------------------


class RoomManager:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}

    def _new_room_id(self) -> str:
        chars = string.ascii_uppercase + string.digits
        while True:
            rid = "".join(random.choices(chars, k=6))
            if rid not in self.rooms:
                return rid

    def create_room(
        self,
        puzzle: Puzzle | None = None,
        script: Script | None = None,
        language: str = "zh",
    ) -> str:
        """Create a new room, return its room_id.

        Pass exactly one of puzzle (turtle_soup) or script (murder_mystery).
        Passing puzzle as the first positional argument still works for
        backward compatibility with turtle_soup callers.
        """
        room_id = self._new_room_id()
        self.rooms[room_id] = Room(room_id, puzzle=puzzle, script=script, language=language)
        return room_id

    def get_room(self, room_id: str) -> Room | None:
        return self.rooms.get(room_id)


# Module-level singleton — imported by ws.py and main.py
room_manager = RoomManager()
