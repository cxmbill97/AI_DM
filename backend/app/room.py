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
from app.models import GameSession, Puzzle, Script

if TYPE_CHECKING:
    from fastapi import WebSocket

    from app.agents.orchestrator import AgentOrchestrator
    from app.state_machine import GameStateMachine
    from app.voting import VotingModule

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_PLAYERS = 4
RECONNECT_WINDOW_SECS = 60  # grace period to reclaim a disconnected seat


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
        # max_players: script specifies it for murder_mystery, turtle_soup defaults 4
        self.max_players: int = (
            script.metadata.player_count if script is not None else 4
        )

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
        """Send *message* as JSON to every currently-connected player."""
        await asyncio.gather(*(self._send_to_slot(slot, message) for slot in self.players.values()))

    async def send_to(self, player_id: str, message: dict[str, Any]) -> None:
        """Send *message* to a single player only."""
        slot = self.players.get(player_id)
        if slot:
            await self._send_to_slot(slot, message)

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
