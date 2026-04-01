"""FastMCP server — exposes the AI deduction game engine as MCP tools.

Single-player turtle soup only.  Murder mystery (which requires WebSocket
state management and multi-player synchronisation) is not supported via MCP.

Tools
-----
list_puzzles    — browse available turtle soup puzzles
list_scripts    — browse available murder mystery scripts (metadata only)
start_game      — start a turtle soup session
ask_question    — ask a yes/no question during a game
get_game_status — check progress, clues found, and whether the game is over

Run with: python -m mcp_server  (stdio transport)
"""

from __future__ import annotations

import uuid
from typing import Any

from fastmcp import FastMCP

from app.dm import dm_turn
from app.models import GameSession, Puzzle
from app.puzzle_loader import (
    load_all_puzzles,
    load_puzzle,
    load_scripts,
    random_puzzle,
)

# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="AI Deduction Game Master",
    instructions=(
        "You are connected to an AI-powered lateral thinking puzzle game (海龟汤 / "
        "Turtle Soup). Use the available tools to browse puzzles, start a game, "
        "and ask yes/no questions to deduce the hidden truth. "
        "The DM will answer each question with: Yes / No / Irrelevant / Partially correct. "
        "Keep asking questions until truth_progress reaches 1.0. "
        "For best results, ask focused factual questions rather than guessing the answer directly."
    ),
)

# ---------------------------------------------------------------------------
# In-memory session store  { session_id: GameSession }
# ---------------------------------------------------------------------------

_sessions: dict[str, GameSession] = {}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_session(session_id: str) -> GameSession:
    session = _sessions.get(session_id)
    if session is None:
        raise ValueError(f"Session not found: {session_id!r}. Call start_game first.")
    return session


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_puzzles(language: str = "zh") -> list[dict[str, Any]]:
    """List available turtle soup puzzles.

    Args:
        language: "zh" for Chinese puzzles, "en" for English puzzles.

    Returns:
        A list of puzzles with id, title, difficulty, and tags.
        Use the `id` field when calling `start_game`.
    """
    puzzles = load_all_puzzles(language)
    return [
        {
            "id": p.id,
            "title": p.title,
            "difficulty": p.difficulty,
            "tags": p.tags,
        }
        for p in puzzles
    ]


@mcp.tool()
def list_scripts(language: str = "zh") -> list[dict[str, Any]]:
    """List available murder mystery scripts (metadata only — not playable via MCP).

    Murder mystery requires multi-player WebSocket coordination and is not
    supported through this MCP interface.  This tool is provided for browsing only.

    Args:
        language: "zh" for Chinese scripts, "en" for English scripts.

    Returns:
        A list of scripts with id, title, player_count, and difficulty.
    """
    scripts = load_scripts(language)
    return [
        {
            "id": s.id,
            "title": s.title,
            "player_count": s.metadata.player_count,
            "difficulty": s.metadata.difficulty,
            "duration_minutes": s.metadata.duration_minutes,
        }
        for s in scripts
    ]


@mcp.tool()
def start_game(
    puzzle_id: str | None = None,
    language: str = "zh",
    player_name: str = "Player",
) -> dict[str, Any]:
    """Start a new turtle soup game session.

    Args:
        puzzle_id: ID of the puzzle to play (from list_puzzles).
                   Omit or pass null to get a random puzzle.
        language:  "zh" for Chinese, "en" for English.
        player_name: Your display name (cosmetic only).

    Returns:
        session_id  — pass this to ask_question and get_game_status
        title       — puzzle title
        surface     — the mystery scenario (what you know at the start)
        instructions — brief reminder of how to play
    """
    lang = language if language in ("zh", "en") else "zh"

    try:
        puzzle: Puzzle = load_puzzle(puzzle_id, lang) if puzzle_id else random_puzzle(lang)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc

    session_id = str(uuid.uuid4())
    session = GameSession(
        session_id=session_id,
        puzzle=puzzle,
        history=[],
        language=lang,
    )
    _sessions[session_id] = session

    if lang == "en":
        instructions = (
            "Ask yes/no questions to deduce the truth. "
            "I will answer: Yes / No / Irrelevant / Partially correct. "
            "When you think you know the full answer, state it — truth_progress will reach 1.0."
        )
    else:
        instructions = (
            "通过提问是非题来推断谜题的真相。"
            "DM 会回答：是 / 不是 / 无关 / 部分正确。"
            "当你认为推断出了完整答案时，直接陈述出来 — truth_progress 将达到 1.0。"
        )

    return {
        "session_id": session_id,
        "title": puzzle.title,
        "surface": puzzle.surface,
        "player_name": player_name,
        "instructions": instructions,
    }


@mcp.tool()
async def ask_question(session_id: str, question: str) -> dict[str, Any]:
    """Ask a yes/no question during a turtle soup game.

    Args:
        session_id: The session ID returned by start_game.
        question:   Your yes/no question or deduction statement.
                    Good questions are specific and factual.
                    Example: "Was the man alone when he died?"

    Returns:
        judgment      — Yes / No / Irrelevant / Partially correct
                        (or 是 / 不是 / 无关 / 部分正确 for Chinese games)
        response      — DM's brief reply or guiding remark
        truth_progress — float 0.0–1.0; game ends when this reaches 1.0
        clue_unlocked — title of a newly discovered clue, or null
        hint          — an escalation hint if you have been stuck, or null
        game_over     — true when the game is finished
        truth         — the full truth revealed when game_over is true, else null
    """
    session = _get_session(session_id)

    if session.finished:
        raise ValueError(
            "Game is already finished. "
            "Call get_game_status to see the result, or start_game to play again."
        )

    question = question.strip()
    if not question:
        raise ValueError("Question cannot be empty.")

    result = await dm_turn(session, question)

    return {
        "judgment": result.judgment,
        "response": result.response,
        "truth_progress": result.truth_progress,
        "clue_unlocked": result.clue_unlocked.title if result.clue_unlocked else None,
        "hint": result.hint,
        "game_over": session.finished,
        "truth": result.truth,
    }


@mcp.tool()
def get_game_status(session_id: str) -> dict[str, Any]:
    """Get the current status of an ongoing game session.

    Args:
        session_id: The session ID returned by start_game.

    Returns:
        title          — puzzle title
        truth_progress — float 0.0–1.0 (how much of the truth has been deduced)
        questions_asked — number of questions asked so far
        hints_used     — number of hints consumed
        unlocked_clues — list of discovered clue titles
        finished       — whether the game is over
        truth          — the full truth if the game is finished, else null
    """
    session = _get_session(session_id)
    return {
        "title": session.puzzle.title,
        "truth_progress": _latest_progress(session),
        "questions_asked": sum(1 for m in session.history if m["role"] == "user"),
        "hints_used": session.hint_index,
        "unlocked_clues": [
            next(
                (c.title for c in session.puzzle.clues if c.id == cid),
                cid,  # fallback to id if not found (e.g. hint pseudo-clues)
            )
            for cid in sorted(session.unlocked_clue_ids)
        ],
        "finished": session.finished,
        "truth": session.puzzle.truth if session.finished else None,
    }


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _latest_progress(session: GameSession) -> float:
    """Extract the most recent truth_progress value from DM responses in history."""
    import json
    import re
    for msg in reversed(session.history):
        if msg.get("role") != "assistant":
            continue
        text = msg.get("content", "")
        # Strip <think> tags first
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        # Try to find truth_progress in the JSON blob
        match = re.search(r'"truth_progress"\s*:\s*([0-9.]+)', text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
    return 0.0
