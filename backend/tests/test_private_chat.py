"""Tests for Phase 3 private chat behavior.

All tests are deterministic (mock LLM).  They verify:
  - dm_turn_private uses the asking player's per-player context.
  - dm_turn_private does NOT modify session.history.
  - Public DM never leaks another player's private clue content.
  - Private response is only sent to the asking player (not broadcast).
"""

from __future__ import annotations

import json

import pytest

from app.dm import assemble_prompt_for_player, dm_turn, dm_turn_private
from app.models import GameSession
from app.puzzle_loader import load_puzzle
from app.visibility import VisibilityRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def collab_puzzle():
    """lighthouse_secret has 3 player slots with distinct private clues."""
    return load_puzzle("lighthouse_secret")


@pytest.fixture
def collab_session(collab_puzzle):
    """Session with player_1=uid-A, player_2=uid-B, player_3=uid-C."""
    return GameSession(
        session_id="priv-chat-test",
        puzzle=collab_puzzle,
        history=[],
        player_slot_map={
            "uid-A": "player_1",
            "uid-B": "player_2",
            "uid-C": "player_3",
        },
    )


# ---------------------------------------------------------------------------
# Private chat: per-player context used in system prompt
# ---------------------------------------------------------------------------


class TestPrivateDMUsesPlayerContext:
    """dm_turn_private builds a prompt that includes the asking player's private clue."""

    async def test_system_prompt_includes_own_private_clue(
        self, mock_llm, collab_session, collab_puzzle
    ):
        """Player A's private clue content appears in the system prompt for Player A."""
        mock_llm.set_response(
            {"judgment": "无关", "response": "继续思考吧", "truth_progress": 0.1,
             "should_hint": False, "audience": "private"}
        )
        await dm_turn_private(collab_session, "uid-A", "我手里的信息说明什么？")
        system_prompt = mock_llm.last_system_prompt

        # Player A is player_1 — bank record content must appear in prompt
        assert "南海贸易" in system_prompt or "银行账户" in system_prompt, (
            "Player A's private clue (bank record) not found in system prompt"
        )

    async def test_system_prompt_excludes_other_player_clue(
        self, mock_llm, collab_session, collab_puzzle
    ):
        """Player A's system prompt must NOT contain Player B's diary fragment content."""
        mock_llm.set_response(
            {"judgment": "无关", "response": "继续思考吧", "truth_progress": 0.1,
             "should_hint": False, "audience": "private"}
        )
        await dm_turn_private(collab_session, "uid-A", "我手里的信息说明什么？")
        system_prompt = mock_llm.last_system_prompt

        # Player B's clue-specific content must not appear in Player A's prompt
        assert "字迹潦草" not in system_prompt, (
            "Player B's private clue content leaked into Player A's private prompt"
        )
        assert "钱算什么" not in system_prompt, (
            "Player B's private clue content leaked into Player A's private prompt"
        )

    async def test_system_prompt_has_private_audience_flag(
        self, mock_llm, collab_session
    ):
        """Private chat prompt must include the private audience instruction."""
        mock_llm.set_response(
            {"judgment": "无关", "response": "好的", "truth_progress": 0.0,
             "should_hint": False, "audience": "private"}
        )
        await dm_turn_private(collab_session, "uid-B", "日记里说了什么意思？")
        system_prompt = mock_llm.last_system_prompt

        assert "私密对话" in system_prompt, (
            "Private audience instruction missing from private chat system prompt"
        )
        assert "private" in system_prompt.lower(), (
            "audience=private marker missing from private chat system prompt"
        )

    async def test_player_b_private_clue_in_prompt_for_player_b(
        self, mock_llm, collab_session
    ):
        """Player B's diary fragment must appear in their own private chat prompt."""
        mock_llm.set_response(
            {"judgment": "无关", "response": "好的", "truth_progress": 0.0,
             "should_hint": False, "audience": "private"}
        )
        await dm_turn_private(collab_session, "uid-B", "我的线索是什么含义？")
        system_prompt = mock_llm.last_system_prompt

        assert "日记" in system_prompt, (
            "Player B's private clue (diary) not found in their own private prompt"
        )

    async def test_all_player_summary_in_private_prompt(
        self, mock_llm, collab_session
    ):
        """Private chat prompt still includes the all-players summary (DM awareness)."""
        mock_llm.set_response(
            {"judgment": "无关", "response": "好的", "truth_progress": 0.0,
             "should_hint": False, "audience": "private"}
        )
        await dm_turn_private(collab_session, "uid-A", "其他人知道什么？")
        system_prompt = mock_llm.last_system_prompt

        # Summary section should mention other player slots
        assert "player_2" in system_prompt or "player_3" in system_prompt, (
            "All-player summary missing from private chat system prompt"
        )


# ---------------------------------------------------------------------------
# Private chat: history isolation
# ---------------------------------------------------------------------------


class TestPrivateChatHistoryIsolation:
    """dm_turn_private must not modify session.history."""

    async def test_history_unchanged_after_private_turn(
        self, mock_llm, collab_session
    ):
        """Session history has the same length before and after a private chat."""
        mock_llm.set_response(
            {"judgment": "无关", "response": "好的", "truth_progress": 0.0,
             "should_hint": False, "audience": "private"}
        )
        collab_session.history.append({"role": "user", "content": "之前的问题"})
        collab_session.history.append({"role": "assistant", "content": "之前的回答"})
        history_before = len(collab_session.history)

        await dm_turn_private(collab_session, "uid-A", "私问：银行记录说明了什么？")

        assert len(collab_session.history) == history_before, (
            "dm_turn_private must not append to session.history"
        )

    async def test_shared_history_not_contaminated_across_private_turns(
        self, mock_llm, collab_session
    ):
        """Two consecutive private chats from different players don't bleed into history."""
        mock_llm.set_response(
            {"judgment": "无关", "response": "好的", "truth_progress": 0.0,
             "should_hint": False, "audience": "private"}
        )
        await dm_turn_private(collab_session, "uid-A", "A的私问")
        await dm_turn_private(collab_session, "uid-B", "B的私问")

        # History should still be empty (nothing was in it to start)
        assert len(collab_session.history) == 0, (
            "Private chat exchanges must not pollute session.history"
        )

    async def test_private_chat_uses_existing_history_as_read_only_context(
        self, mock_llm, collab_session
    ):
        """dm_turn_private passes existing history to LLM but does not extend it."""
        mock_llm.set_response(
            {"judgment": "无关", "response": "好的", "truth_progress": 0.0,
             "should_hint": False, "audience": "private"}
        )
        collab_session.history.append({"role": "user", "content": "公开问题"})
        collab_session.history.append({"role": "assistant", "content": "公开回答"})

        await dm_turn_private(collab_session, "uid-A", "私密问题")

        # The messages passed to LLM should include the existing history + private msg
        last_messages = mock_llm.last_messages
        assert any(m["content"] == "公开问题" for m in last_messages), (
            "dm_turn_private should pass existing history as context to LLM"
        )
        assert any(m["content"] == "私密问题" for m in last_messages), (
            "dm_turn_private should include the private message in LLM messages"
        )

        # But history itself must be unchanged
        assert len(collab_session.history) == 2, (
            "dm_turn_private must not extend session.history"
        )

    async def test_private_turn_returns_string(self, mock_llm, collab_session):
        """dm_turn_private returns a plain string, not a ChatResponse."""
        mock_llm.set_response(
            {"judgment": "是", "response": "你的线索很关键！", "truth_progress": 0.5,
             "should_hint": False, "audience": "private"}
        )
        result = await dm_turn_private(collab_session, "uid-A", "银行记录意味着贿赂吗？")
        assert isinstance(result, str), "dm_turn_private must return str"
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Public DM: other player's private clue not leaked
# ---------------------------------------------------------------------------


class TestPublicDMDoesNotLeakPrivate:
    """Public dm_turn with player_id must not reveal another player's clue."""

    async def test_public_prompt_does_not_include_other_player_clue_content(
        self, mock_llm, collab_session
    ):
        """Player A's public question builds a prompt that excludes Player B's content."""
        mock_llm.set_response(
            {"judgment": "无关", "response": "继续思考", "truth_progress": 0.0,
             "should_hint": False, "audience": "public"}
        )
        await dm_turn(collab_session, "守望者为什么那样做？", player_id="uid-A")
        system_prompt = mock_llm.last_system_prompt

        # Player B's diary fragment content must NOT be in player A's public prompt
        assert "字迹潦草" not in system_prompt, (
            "Player B's private clue content leaked into Player A's public prompt"
        )
        assert "日记残页" not in system_prompt or "仅供DM参考" in system_prompt, (
            "Player B's private clue title appeared in Player A's public prompt context"
        )

    async def test_public_prompt_includes_own_private_clue(
        self, mock_llm, collab_session
    ):
        """Player A's public chat prompt DOES include their own private clue."""
        mock_llm.set_response(
            {"judgment": "无关", "response": "继续思考", "truth_progress": 0.0,
             "should_hint": False, "audience": "public"}
        )
        await dm_turn(collab_session, "账户里的钱是什么来源？", player_id="uid-A")
        system_prompt = mock_llm.last_system_prompt

        # Player A is player_1 — their bank record clue should be in the prompt
        assert "银行账户" in system_prompt or "南海贸易" in system_prompt, (
            "Player A's own private clue should appear in their public chat prompt"
        )

    async def test_public_dm_audience_instruction_present(
        self, mock_llm, collab_session
    ):
        """Public chat prompt must instruct DM to only use public + own private info."""
        mock_llm.set_response(
            {"judgment": "无关", "response": "继续思考", "truth_progress": 0.0,
             "should_hint": False, "audience": "public"}
        )
        await dm_turn(collab_session, "守望者和船有什么关系？", player_id="uid-A")
        system_prompt = mock_llm.last_system_prompt

        assert "公开对话" in system_prompt, (
            "Public audience instruction missing from public chat prompt"
        )
        assert "绝对不得" in system_prompt, (
            "Leak prevention instruction missing from public chat prompt"
        )

    async def test_public_dm_summary_only_has_titles_not_content(
        self, mock_llm, collab_session
    ):
        """The all-player summary in a public prompt must contain titles, not clue content."""
        mock_llm.set_response(
            {"judgment": "无关", "response": "继续思考", "truth_progress": 0.0,
             "should_hint": False, "audience": "public"}
        )
        await dm_turn(collab_session, "灯塔为何熄灭？", player_id="uid-A")
        system_prompt = mock_llm.last_system_prompt

        # Summary should mention titles (e.g. "守望者日记残页") but not the
        # body content (e.g. "字迹潦草") of other players' clues.
        assert "日记残页" in system_prompt, (
            "DM summary should include Player B's clue title"
        )
        assert "字迹潦草" not in system_prompt, (
            "DM summary must not include Player B's private clue content"
        )

    async def test_no_player_id_falls_back_to_standard_prompt(
        self, mock_llm, collab_session
    ):
        """dm_turn without player_id uses the standard (non-per-player) prompt."""
        mock_llm.set_response(
            {"judgment": "无关", "response": "继续思考", "truth_progress": 0.0,
             "should_hint": False}
        )
        await dm_turn(collab_session, "守望者死了吗？")
        system_prompt = mock_llm.last_system_prompt

        # Standard prompt does not have per-player sections
        assert "当前提问玩家的私有线索" not in system_prompt, (
            "Standard prompt should not include per-player sections when player_id is absent"
        )


# ---------------------------------------------------------------------------
# Private response not broadcast (prompt-level verification)
# ---------------------------------------------------------------------------


class TestPrivateResponseNotBroadcast:
    """Verify that dm_turn_private is not a public broadcast by checking
    that it does not update shared session state.

    Note: the WebSocket broadcast behavior itself is tested in test_room.py
    (integration layer).  Here we confirm the contract at the dm layer:
    private turns leave no trace in shared state.
    """

    async def test_game_session_consecutive_misses_not_incremented(
        self, mock_llm, collab_session
    ):
        """Private chat should not affect session.consecutive_misses."""
        mock_llm.set_response(
            {"judgment": "无关", "response": "好的", "truth_progress": 0.0,
             "should_hint": False, "audience": "private"}
        )
        collab_session.consecutive_misses = 2
        await dm_turn_private(collab_session, "uid-A", "私问")
        assert collab_session.consecutive_misses == 2, (
            "dm_turn_private must not alter session.consecutive_misses"
        )

    async def test_game_session_not_finished_after_private_chat(
        self, mock_llm, collab_session
    ):
        """Even if the private DM mock returns truth_progress=1.0, session must not finish."""
        mock_llm.set_response(
            {"judgment": "是", "response": "你完全猜对了！", "truth_progress": 1.0,
             "should_hint": False, "audience": "private"}
        )
        await dm_turn_private(collab_session, "uid-A", "守望者是被良心折磨死的吗？")
        assert not collab_session.finished, (
            "dm_turn_private must not mark session as finished — no game state changes"
        )

    async def test_unlocked_clue_ids_not_modified_by_private_chat(
        self, mock_llm, collab_session
    ):
        """Private chat must not unlock clue cards."""
        mock_llm.set_response(
            {"judgment": "是", "response": "灯塔是被关掉的", "truth_progress": 0.4,
             "should_hint": False, "audience": "private"}
        )
        initial_unlocked = set(collab_session.unlocked_clue_ids)
        # Use keyword that would trigger unlock in public chat
        await dm_turn_private(collab_session, "uid-A", "灯塔为什么熄灭？灯的问题？")
        assert collab_session.unlocked_clue_ids == initial_unlocked, (
            "dm_turn_private must not unlock clue cards"
        )

    async def test_history_length_unchanged_after_multiple_private_chats(
        self, mock_llm, collab_session
    ):
        """Multiple private chats from different players don't accumulate in history."""
        mock_llm.set_response(
            {"judgment": "无关", "response": "好的", "truth_progress": 0.0,
             "should_hint": False, "audience": "private"}
        )
        for player_id in ["uid-A", "uid-B", "uid-C"]:
            await dm_turn_private(collab_session, player_id, "私密问题")

        assert len(collab_session.history) == 0, (
            "Three private chats must leave history empty"
        )
