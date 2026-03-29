"""Pydantic models for puzzles, requests, responses, and game state."""

from __future__ import annotations

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Puzzle schema (mirrors the JSON files in data/puzzles/)
# ---------------------------------------------------------------------------


class Puzzle(BaseModel):
    id: str
    title: str
    surface: str  # 汤面 — shown to the player
    truth: str  # 汤底 — TOP SECRET, never sent to frontend
    key_facts: list[str]  # decomposed truths used for matching
    hints: list[str]  # escalating hints
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


class PuzzleSummary(BaseModel):
    """Safe puzzle info for the public /api/puzzles listing — no truth field."""

    id: str
    title: str
    difficulty: str
    tags: list[str]


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
