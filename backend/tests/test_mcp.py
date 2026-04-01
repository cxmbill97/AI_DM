"""Tests for the MCP server tools.

Tests call the tool functions directly — no MCP protocol layer needed.
All game-logic calls (dm_turn) are mocked so no real LLM calls are made.

Mark live-LLM tests with @pytest.mark.slow; they are excluded from normal CI.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.models import ChatResponse, Clue
from mcp_server.server import (
    _sessions,
    ask_question,
    get_game_status,
    list_puzzles,
    list_scripts,
    start_game,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_sessions():
    """Ensure a clean session store before each test."""
    _sessions.clear()
    yield
    _sessions.clear()


def _fake_chat_response(
    judgment: str = "不是",
    response: str = "不对，再想想。",
    truth_progress: float = 0.1,
    clue: Clue | None = None,
    hint: str | None = None,
    truth: str | None = None,
) -> ChatResponse:
    return ChatResponse(
        judgment=judgment,
        response=response,
        truth_progress=truth_progress,
        should_hint=hint is not None,
        hint=hint,
        truth=truth,
        clue_unlocked=clue,
    )


# ---------------------------------------------------------------------------
# list_puzzles
# ---------------------------------------------------------------------------


def test_list_puzzles_zh():
    results = list_puzzles(language="zh")
    assert isinstance(results, list)
    assert len(results) > 0
    first = results[0]
    assert "id" in first
    assert "title" in first
    assert "difficulty" in first
    assert "tags" in first


def test_list_puzzles_en():
    results = list_puzzles(language="en")
    assert isinstance(results, list)
    assert len(results) > 0


def test_list_puzzles_unknown_language_returns_empty_or_list():
    # Should not raise; may return empty list if no zh/en default
    results = list_puzzles(language="fr")
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# list_scripts
# ---------------------------------------------------------------------------


def test_list_scripts_zh():
    results = list_scripts(language="zh")
    assert isinstance(results, list)
    assert len(results) > 0
    first = results[0]
    assert "id" in first
    assert "title" in first
    assert "player_count" in first
    assert "difficulty" in first


def test_list_scripts_en():
    results = list_scripts(language="en")
    assert isinstance(results, list)
    assert len(results) > 0


# ---------------------------------------------------------------------------
# start_game
# ---------------------------------------------------------------------------


def test_start_game_random_zh():
    result = start_game(language="zh")
    assert "session_id" in result
    assert "title" in result
    assert "surface" in result
    assert "instructions" in result
    assert result["session_id"] in _sessions


def test_start_game_random_en():
    result = start_game(language="en")
    assert result["session_id"] in _sessions
    assert "en" in result["instructions"].lower() or "yes" in result["instructions"].lower()


def test_start_game_specific_puzzle():
    # Pick the first available zh puzzle
    puzzles = list_puzzles("zh")
    puzzle_id = puzzles[0]["id"]
    result = start_game(puzzle_id=puzzle_id, language="zh")
    session = _sessions[result["session_id"]]
    assert session.puzzle.id == puzzle_id


def test_start_game_unknown_puzzle_raises():
    with pytest.raises(ValueError, match="not found"):
        start_game(puzzle_id="does_not_exist", language="zh")


def test_start_game_invalid_language_falls_back_to_zh():
    result = start_game(language="xx")
    session = _sessions[result["session_id"]]
    assert session.language == "zh"


def test_start_game_creates_independent_sessions():
    r1 = start_game(language="zh")
    r2 = start_game(language="zh")
    assert r1["session_id"] != r2["session_id"]
    assert len(_sessions) == 2


# ---------------------------------------------------------------------------
# ask_question (mocked dm_turn)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ask_question_basic():
    game = start_game(language="zh")
    sid = game["session_id"]

    fake = _fake_chat_response(judgment="不是", response="不对，再想想。", truth_progress=0.1)
    with patch("mcp_server.server.dm_turn", new=AsyncMock(return_value=fake)):
        result = await ask_question(sid, "死者是被枪击中的吗？")

    assert result["judgment"] == "不是"
    assert result["response"] == "不对，再想想。"
    assert result["truth_progress"] == pytest.approx(0.1)
    assert result["clue_unlocked"] is None
    assert result["game_over"] is False
    assert result["truth"] is None


@pytest.mark.asyncio
async def test_ask_question_with_clue():
    game = start_game(language="zh")
    sid = game["session_id"]

    clue = Clue(id="c1", title="重要线索", content="内容", unlock_keywords=[])
    fake = _fake_chat_response(judgment="是", truth_progress=0.5, clue=clue)
    with patch("mcp_server.server.dm_turn", new=AsyncMock(return_value=fake)):
        result = await ask_question(sid, "这和水有关系吗？")

    assert result["clue_unlocked"] == "重要线索"


@pytest.mark.asyncio
async def test_ask_question_game_over():
    game = start_game(language="zh")
    sid = game["session_id"]
    session = _sessions[sid]

    fake = _fake_chat_response(
        judgment="是",
        truth_progress=1.0,
        truth="真正的真相在这里",
    )
    # dm_turn sets session.finished = True internally; simulate it
    async def _finishing_dm_turn(s, q, **kw):
        s.finished = True
        return fake

    with patch("mcp_server.server.dm_turn", new=_finishing_dm_turn):
        result = await ask_question(sid, "我知道真相了！")

    assert result["game_over"] is True
    assert result["truth"] == "真正的真相在这里"


@pytest.mark.asyncio
async def test_ask_question_already_finished_raises():
    game = start_game(language="zh")
    sid = game["session_id"]
    _sessions[sid].finished = True

    with pytest.raises(ValueError, match="already finished"):
        await ask_question(sid, "再问一个")


@pytest.mark.asyncio
async def test_ask_question_empty_question_raises():
    game = start_game(language="zh")
    with pytest.raises(ValueError, match="empty"):
        await ask_question(game["session_id"], "   ")


@pytest.mark.asyncio
async def test_ask_question_unknown_session_raises():
    with pytest.raises(ValueError, match="Session not found"):
        await ask_question("00000000-0000-0000-0000-000000000000", "test")


# ---------------------------------------------------------------------------
# get_game_status
# ---------------------------------------------------------------------------


def test_get_game_status_initial():
    game = start_game(language="zh")
    status = get_game_status(game["session_id"])

    assert "title" in status
    assert status["questions_asked"] == 0
    assert status["hints_used"] == 0
    assert status["unlocked_clues"] == []
    assert status["finished"] is False
    assert status["truth"] is None


def test_get_game_status_finished():
    game = start_game(language="zh")
    sid = game["session_id"]
    _sessions[sid].finished = True

    status = get_game_status(sid)
    assert status["finished"] is True
    assert status["truth"] is not None  # puzzle.truth is revealed when finished


def test_get_game_status_unknown_session_raises():
    with pytest.raises(ValueError, match="Session not found"):
        get_game_status("no-such-session")


@pytest.mark.asyncio
async def test_full_game_flow_mocked():
    """End-to-end: start → ask → status → ask (finish) → status."""
    game = start_game(language="en", player_name="TestBot")
    sid = game["session_id"]
    assert "surface" in game

    fake_mid = _fake_chat_response(
        judgment="No", response="That is not correct.", truth_progress=0.3
    )

    async def _mid_dm(session, q, **kw):
        # simulate dm_turn appending to history (so questions_asked counts correctly)
        session.history.append({"role": "user", "content": q})
        session.history.append({"role": "assistant", "content": '{"truth_progress": 0.3}'})
        return fake_mid

    with patch("mcp_server.server.dm_turn", new=_mid_dm):
        r = await ask_question(sid, "Was it a car accident?")
    assert r["truth_progress"] == pytest.approx(0.3)

    status = get_game_status(sid)
    assert status["questions_asked"] == 1

    fake_end = _fake_chat_response(
        judgment="Yes", response="Exactly right!", truth_progress=1.0, truth="The full truth."
    )

    async def _end(s, q, **kw):
        s.finished = True
        return fake_end

    with patch("mcp_server.server.dm_turn", new=_end):
        r2 = await ask_question(sid, "He poisoned himself?")

    assert r2["game_over"] is True
    final = get_game_status(sid)
    assert final["finished"] is True
    assert final["truth"] is not None


# ---------------------------------------------------------------------------
# Slow integration tests (real LLM — require MINIMAX_API_KEY)
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.asyncio
async def test_start_and_ask_real_llm(real_llm: None) -> None:
    """Start a game and ask a real question — verifies end-to-end LLM path."""
    game = start_game(language="zh")
    sid = game["session_id"]
    assert "surface" in game
    assert game["surface"]  # non-empty puzzle surface

    result = await ask_question(sid, "这和食物有关吗")
    assert "judgment" in result
    assert result["judgment"] in ("是", "不是", "无关", "部分正确")
    assert "response" in result
    assert result["response"]
    assert 0.0 <= result["truth_progress"] <= 1.0


@pytest.mark.slow
@pytest.mark.asyncio
async def test_game_status_tracks_questions(real_llm: None) -> None:
    """Ask 2 questions — get_game_status must report questions_asked == 2."""
    game = start_game(language="zh")
    sid = game["session_id"]

    await ask_question(sid, "这个谜题和死亡有关吗")
    await ask_question(sid, "这和交通工具有关吗")

    status = get_game_status(sid)
    assert status["questions_asked"] == 2


@pytest.mark.slow
@pytest.mark.asyncio
async def test_reveal_truth_on_finished_game(real_llm: None) -> None:
    """get_game_status exposes truth once the game is marked finished."""
    game = start_game(language="zh")
    sid = game["session_id"]

    # Force game to finished state
    _sessions[sid].finished = True

    status = get_game_status(sid)
    assert status["finished"] is True
    assert status["truth"] is not None
    assert len(status["truth"]) > 0  # non-empty truth string
