"""Pydantic models for puzzles, requests, responses, and game state."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Puzzle schema (mirrors the JSON files in data/puzzles/)
# ---------------------------------------------------------------------------


class Clue(BaseModel):
    """A discoverable clue that unlocks when the player asks about the right topic.

    unlock_keywords: 2-4 Chinese words that, when appearing in a player's question,
    signal that this clue should be revealed.  Matching happens in dm.py.
    """

    id: str
    title: str
    content: str  # the clue text shown to the player — reveals ONE aspect of truth
    unlock_keywords: list[str]  # e.g. ["海难", "船", "遇难"]


class Puzzle(BaseModel):
    id: str
    title: str
    surface: str  # 汤面 — shown to the player
    truth: str  # 汤底 — TOP SECRET, never sent to frontend
    key_facts: list[str]  # decomposed truths used for matching
    hints: list[str]  # escalating hints (Phase 1 fallback, unchanged)
    clues: list[Clue] = []  # discoverable clues (Phase 2); old JSONs without this still load
    difficulty: str  # e.g. "简单" / "中等" / "困难"
    tags: list[str]


# ---------------------------------------------------------------------------
# API request / response schemas
# ---------------------------------------------------------------------------


class StartRequest(BaseModel):
    puzzle_id: str | None = None  # None → random puzzle


class StartResponse(BaseModel):
    session_id: str
    puzzle_id: str
    title: str
    surface: str  # 汤面 only — truth is NEVER returned


class ChatRequest(BaseModel):
    session_id: str
    message: str  # player's yes/no question


class ChatResponse(BaseModel):
    judgment: str  # 是 / 不是 / 无关 / 部分正确
    response: str  # DM's reply (Chinese)
    truth_progress: float  # 0.0–1.0, how much has been deduced
    should_hint: bool
    hint: str | None = None  # only present when a hint is given
    truth: str | None = None  # populated when truth_progress >= 1.0 (game over)
    clue_unlocked: Clue | None = None  # newly unlocked clue this turn, if any


class PuzzleSummary(BaseModel):
    """Safe puzzle info for the public /api/puzzles listing — no truth field."""

    id: str
    title: str
    difficulty: str
    tags: list[str]


# ---------------------------------------------------------------------------
# Multiplayer room models
# ---------------------------------------------------------------------------


class Player(BaseModel):
    id: str
    name: str
    connected: bool = True


class RoomState(BaseModel):
    """Safe room info returned by GET /api/rooms/{room_id} — no truth field."""

    room_id: str
    puzzle_id: str
    title: str
    surface: str  # 汤面 — safe to expose
    players: list[Player]
    phase: str  # "waiting" | "playing" | "finished"


# ---------------------------------------------------------------------------
# WebSocket message types
# ---------------------------------------------------------------------------


class WsInboundChat(BaseModel):
    """Message sent from a player to the server."""

    type: Literal["chat"]
    text: str


class WsSystemMessage(BaseModel):
    """Server → all clients: join/leave/error notifications."""

    type: Literal["system"] = "system"
    text: str


class WsPlayerMessage(BaseModel):
    """Server → all clients: echo of what a player said (so everyone sees the question)."""

    type: Literal["player_message"] = "player_message"
    player_name: str
    text: str
    timestamp: float


class WsDMResponse(BaseModel):
    """Server → all clients: DM judgment + response after a player's question."""

    type: Literal["dm_response"] = "dm_response"
    player_name: str  # who asked
    judgment: str
    response: str
    truth_progress: float
    clue_unlocked: Clue | None = None
    hint: str | None = None
    truth: str | None = None  # populated when game is won
    timestamp: float


class WsClueNotification(BaseModel):
    """Server → all clients: a clue was just unlocked (also embedded in WsDMResponse)."""

    type: Literal["clue_unlocked"] = "clue_unlocked"
    clue: Clue


# ---------------------------------------------------------------------------
# Internal DM structured output (parsed from LLM JSON)
# ---------------------------------------------------------------------------


class DMOutput(BaseModel):
    judgment: str
    response: str
    truth_progress: float
    should_hint: bool


# ---------------------------------------------------------------------------
# In-memory game session
# ---------------------------------------------------------------------------


class GameSession(BaseModel):
    session_id: str
    puzzle: Puzzle
    history: list[dict]  # OpenAI-format message dicts (raw, with <think> preserved)
    hint_index: int = 0
    consecutive_misses: int = 0
    finished: bool = False
    unlocked_clue_ids: set[str] = set()  # ids of clues the player has earned so far
