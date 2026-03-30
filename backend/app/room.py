"""Multiplayer room manager for Phase 2 海龟汤.

Each room holds 2-4 players sharing a single GameSession.  All DM responses
and clue unlocks are broadcast to every connected player.
"""

from __future__ import annotations

import asyncio
import random
import string
import time
from typing import TYPE_CHECKING, Any

from app.intervention import InterventionEngine
from app.models import GameSession, Puzzle

if TYPE_CHECKING:
    from fastapi import WebSocket

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_PLAYERS = 4
RECONNECT_WINDOW_SECS = 60  # grace period to reclaim a disconnected seat


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------


class Room:
    """A single multiplayer game room."""

    def __init__(self, room_id: str, puzzle: Puzzle) -> None:
        self.room_id = room_id
        self.puzzle = puzzle

        # player_id → PlayerSlot dict
        # PlayerSlot keys: name, websocket, connected, last_seen (epoch float)
        self.players: dict[str, dict[str, Any]] = {}

        # Shared game session — all players contribute to the same progress
        self.game_session = GameSession(
            session_id=room_id,
            puzzle=puzzle,
            history=[],
        )

        # Full chronological log; used to replay missed messages on reconnect
        self.message_history: list[dict[str, Any]] = []

        # Serialize concurrent DM turns so two simultaneous questions don't race
        self._lock = asyncio.Lock()

        # Proactive DM intervention engine (multiplayer only)
        self.intervention = InterventionEngine(self)

        # Background silence-tick task — created and cancelled by ws.py
        self._tick_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Player management
    # ------------------------------------------------------------------

    def _active_player_count(self) -> int:
        """Count players that are connected OR within the reconnect window."""
        now = time.time()
        return sum(
            1
            for p in self.players.values()
            if p["connected"] or (now - p["last_seen"]) < RECONNECT_WINDOW_SECS
        )

    def is_full(self) -> bool:
        return self._active_player_count() >= MAX_PLAYERS

    def find_player_by_name(self, name: str) -> str | None:
        """Return the player_id for a given name, or None."""
        for pid, p in self.players.items():
            if p["name"] == name:
                return pid
        return None

    def add_player(self, player_id: str, name: str, websocket: "WebSocket") -> None:
        self.players[player_id] = {
            "name": name,
            "websocket": websocket,
            "connected": True,
            "last_seen": time.time(),
            # Serialize concurrent sends to this player's socket.
            # Starlette WebSocket is NOT safe for concurrent writes from multiple coroutines.
            "send_lock": asyncio.Lock(),
        }

    def reconnect_player(self, player_id: str, websocket: "WebSocket") -> None:
        slot = self.players[player_id]
        slot["websocket"] = websocket
        slot["connected"] = True
        slot["last_seen"] = time.time()
        # Keep the existing send_lock — no need to recreate it

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
        """Send *message* to one player slot, holding that slot's send_lock.

        Acquiring the per-player lock prevents two concurrent coroutines from
        writing to the same WebSocket at the same time (which corrupts the stream).
        """
        if not slot["connected"] or slot["websocket"] is None:
            return
        try:
            async with slot["send_lock"]:
                await slot["websocket"].send_json(message)
        except Exception:
            # Send failure → the socket is gone; the receive loop will handle
            # the formal disconnect via WebSocketDisconnect.
            pass

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send *message* as JSON to every currently-connected player."""
        # Fire all sends concurrently; each one is individually lock-guarded.
        await asyncio.gather(
            *(self._send_to_slot(slot, message) for slot in self.players.values())
        )

    async def send_to(self, player_id: str, message: dict[str, Any]) -> None:
        """Send *message* to a single player only."""
        slot = self.players.get(player_id)
        if slot:
            await self._send_to_slot(slot, message)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def phase(self) -> str:
        if self.game_session.finished:
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

    def create_room(self, puzzle: Puzzle) -> str:
        """Create a new room, return its room_id."""
        room_id = self._new_room_id()
        self.rooms[room_id] = Room(room_id, puzzle)
        return room_id

    def get_room(self, room_id: str) -> Room | None:
        return self.rooms.get(room_id)


# Module-level singleton — imported by ws.py and main.py
room_manager = RoomManager()
