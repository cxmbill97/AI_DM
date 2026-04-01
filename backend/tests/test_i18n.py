"""Phase 5 i18n tests — bilingual puzzle loading and DM language switching.

All tests are deterministic (no real LLM calls) unless marked @pytest.mark.slow.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from app.dm import assemble_prompt, dm_turn
from app.intervention import (
    InterventionEngine,
    _GENTLE_MESSAGES_EN,
    _GENTLE_MESSAGES_ZH,
    _VOTE_REMINDER_EN,
    _VOTE_REMINDER_ZH,
)
from app.models import GameSession, Puzzle
from app.puzzle_loader import load_all_puzzles, load_puzzle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _has_cjk(text: str) -> bool:
    """Return True if *text* contains any CJK Unified Ideograph."""
    return bool(_CJK_RE.search(text))


def _fresh_session(puzzle: Puzzle, language: str = "zh") -> GameSession:
    return GameSession(session_id="i18n-test", puzzle=puzzle, history=[], language=language)


def _make_room(language: str) -> MagicMock:
    room = MagicMock()
    room.players = {}
    room.language = language
    room.game_session = MagicMock()
    room.game_session.finished = False
    return room


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sample_en_puzzle() -> Puzzle:
    """First available English puzzle, loaded from data/puzzles/en/."""
    puzzles = load_all_puzzles("en")
    assert puzzles, "No English puzzles found — did you add data/puzzles/en/ files?"
    return puzzles[0]


# ---------------------------------------------------------------------------
# 1. Puzzle loading — per-language directories
# ---------------------------------------------------------------------------


class TestPuzzleLoading:
    def test_load_chinese_puzzles_returns_results(self) -> None:
        """load_all_puzzles('zh') returns at least one puzzle."""
        puzzles = load_all_puzzles("zh")
        assert len(puzzles) > 0, "Expected at least one Chinese puzzle"

    def test_load_chinese_puzzles_surfaces_are_chinese(self) -> None:
        """All Chinese puzzles have surface text containing CJK characters."""
        for p in load_all_puzzles("zh"):
            assert _has_cjk(p.surface), (
                f"Puzzle {p.id!r} surface has no CJK characters: {p.surface[:60]!r}"
            )

    def test_load_english_puzzles_returns_results(self) -> None:
        """load_all_puzzles('en') returns at least one puzzle."""
        puzzles = load_all_puzzles("en")
        assert len(puzzles) > 0, "Expected at least one English puzzle"

    def test_load_english_puzzles_surfaces_are_english(self) -> None:
        """All English puzzles have surface text without CJK characters."""
        for p in load_all_puzzles("en"):
            assert not _has_cjk(p.surface), (
                f"English puzzle {p.id!r} surface contains CJK: {p.surface[:80]!r}"
            )

    def test_load_nonexistent_language_returns_empty(self) -> None:
        """load_all_puzzles('fr') returns an empty list — no French data directory."""
        puzzles = load_all_puzzles("fr")
        assert puzzles == [], (
            f"Expected empty list for unsupported language 'fr', got {len(puzzles)} puzzles"
        )

    def test_zh_and_en_puzzle_ids_do_not_overlap(self) -> None:
        """Chinese and English puzzle sets are independent (no shared IDs)."""
        zh_ids = {p.id for p in load_all_puzzles("zh")}
        en_ids = {p.id for p in load_all_puzzles("en")}
        overlap = zh_ids & en_ids
        assert not overlap, f"zh and en share puzzle IDs: {overlap}"

    def test_english_puzzles_have_required_fields(self) -> None:
        """Every English puzzle has a non-empty surface, truth, key_facts, and hints."""
        for p in load_all_puzzles("en"):
            assert p.surface.strip(), f"English puzzle {p.id!r} has empty surface"
            assert p.truth.strip(), f"English puzzle {p.id!r} has empty truth"
            assert p.key_facts, f"English puzzle {p.id!r} has no key_facts"
            assert p.hints, f"English puzzle {p.id!r} has no hints"

    def test_caching_returns_same_objects(self) -> None:
        """Calling load_all_puzzles twice returns identical objects (module-level cache)."""
        first = load_all_puzzles("en")
        second = load_all_puzzles("en")
        assert first is second or [p.id for p in first] == [p.id for p in second]


# ---------------------------------------------------------------------------
# 2. DM prompt language switching — assemble_prompt
# ---------------------------------------------------------------------------


class TestAssemblePromptLanguage:
    def test_english_prompt_contains_english_rules(self, sample_en_puzzle: Puzzle) -> None:
        """assemble_prompt with lang='en' produces an English DM persona section."""
        prompt = assemble_prompt(sample_en_puzzle, lang="en")
        assert "You are the DM" in prompt

    def test_english_prompt_contains_english_judgment_values(
        self, sample_en_puzzle: Puzzle
    ) -> None:
        """English prompt specifies English judgment values (Yes/No/Irrelevant)."""
        prompt = assemble_prompt(sample_en_puzzle, lang="en")
        assert "Yes" in prompt
        assert "No" in prompt
        assert "Irrelevant" in prompt
        assert "Partially correct" in prompt

    def test_english_rules_section_has_no_cjk(self, sample_en_puzzle: Puzzle) -> None:
        """The DM rules section of an English prompt contains no CJK characters.

        We isolate the rules by taking everything before the puzzle surface appears.
        """
        prompt = assemble_prompt(sample_en_puzzle, lang="en")
        before_surface = prompt.split(sample_en_puzzle.surface)[0]
        assert not _has_cjk(before_surface), (
            f"English rules section contains CJK: {before_surface[:200]!r}"
        )

    def test_chinese_prompt_contains_chinese_rules(self, sample_puzzle: Puzzle) -> None:
        """assemble_prompt with lang='zh' produces a Chinese DM persona section."""
        prompt = assemble_prompt(sample_puzzle, lang="zh")
        before_surface = prompt.split(sample_puzzle.surface)[0]
        assert _has_cjk(before_surface), "Chinese rules section should contain CJK characters"

    def test_chinese_prompt_contains_chinese_judgment_values(
        self, sample_puzzle: Puzzle
    ) -> None:
        """Chinese prompt specifies Chinese judgment values (是/不是/无关/部分正确)."""
        prompt = assemble_prompt(sample_puzzle, lang="zh")
        assert "是" in prompt
        assert "不是" in prompt
        assert "无关" in prompt
        assert "部分正确" in prompt

    def test_both_prompts_contain_puzzle_surface(self, sample_en_puzzle: Puzzle) -> None:
        """Both English and Chinese prompts embed the puzzle surface."""
        en_prompt = assemble_prompt(sample_en_puzzle, lang="en")
        assert sample_en_puzzle.surface in en_prompt

    def test_both_prompts_contain_puzzle_truth(self, sample_en_puzzle: Puzzle) -> None:
        """Both English and Chinese prompts embed the puzzle truth (for DM judgment)."""
        en_prompt = assemble_prompt(sample_en_puzzle, lang="en")
        assert sample_en_puzzle.truth in en_prompt


# ---------------------------------------------------------------------------
# 3. dm_turn — language propagation through session.language
# ---------------------------------------------------------------------------


class TestDmTurnLanguage:
    async def test_english_session_sends_english_system_prompt(
        self, mock_llm, sample_en_puzzle: Puzzle
    ) -> None:
        """dm_turn with language='en' sends an English system prompt to the LLM."""
        mock_llm.set_response({
            "judgment": "No",
            "response": "That is not quite right, keep thinking.",
            "truth_progress": 0.0,
            "should_hint": False,
        })
        session = _fresh_session(sample_en_puzzle, language="en")
        await dm_turn(session, "Did a man die?")

        prompt = mock_llm.last_system_prompt
        assert "You are the DM" in prompt, (
            f"Expected English persona in system prompt, got: {prompt[:200]!r}"
        )

    async def test_english_session_parses_english_judgment(
        self, mock_llm, sample_en_puzzle: Puzzle
    ) -> None:
        """dm_turn correctly parses English judgment values ('Yes', 'No', etc.)."""
        for judgment in ("Yes", "No", "Irrelevant", "Partially correct"):
            mock_llm.set_response({
                "judgment": judgment,
                "response": "Keep thinking.",
                "truth_progress": 0.0,
                "should_hint": False,
            })
            session = _fresh_session(sample_en_puzzle, language="en")
            result = await dm_turn(session, "Test question")
            assert result.judgment == judgment, (
                f"Expected judgment={judgment!r}, got {result.judgment!r}"
            )

    async def test_chinese_session_sends_chinese_system_prompt(
        self, mock_llm, sample_puzzle: Puzzle
    ) -> None:
        """dm_turn with language='zh' sends a Chinese system prompt to the LLM."""
        mock_llm.set_response({
            "judgment": "无关",
            "response": "与谜题无关，请换个角度。",
            "truth_progress": 0.0,
            "should_hint": False,
        })
        session = _fresh_session(sample_puzzle, language="zh")
        await dm_turn(session, "男人去了哪里？")

        prompt = mock_llm.last_system_prompt
        before_surface = prompt.split(sample_puzzle.surface)[0]
        assert _has_cjk(before_surface), (
            f"Expected CJK in Chinese system prompt rules section, got: {before_surface[:200]!r}"
        )

    async def test_english_hint_title_is_english(
        self, mock_llm, sample_en_puzzle: Puzzle
    ) -> None:
        """Passive hint clue card in English sessions uses 'DM Hint' as title."""
        mock_llm.set_response({
            "judgment": "No",
            "response": "Not quite.",
            "truth_progress": 0.0,
            "should_hint": True,
        })
        session = _fresh_session(sample_en_puzzle, language="en")
        session.consecutive_misses = 10  # force passive hint
        result = await dm_turn(session, "Any question")

        if result.clue_unlocked is not None:
            assert result.clue_unlocked.title == "DM Hint", (
                f"Expected 'DM Hint', got {result.clue_unlocked.title!r}"
            )

    async def test_chinese_hint_title_is_chinese(
        self, mock_llm, sample_puzzle: Puzzle
    ) -> None:
        """Passive hint clue card in Chinese sessions uses 'DM 提示' as title."""
        mock_llm.set_response({
            "judgment": "不是",
            "response": "不对，换个角度想。",
            "truth_progress": 0.0,
            "should_hint": True,
        })
        session = _fresh_session(sample_puzzle, language="zh")
        session.consecutive_misses = 10
        result = await dm_turn(session, "任意问题")

        if result.clue_unlocked is not None:
            assert result.clue_unlocked.title == "DM 提示", (
                f"Expected 'DM 提示', got {result.clue_unlocked.title!r}"
            )


# ---------------------------------------------------------------------------
# 4. Intervention engine — language-aware canned messages
# ---------------------------------------------------------------------------


class TestInterventionLanguage:
    def test_english_gentle_message_from_english_list(self) -> None:
        """random_gentle_message(lang='en') always returns a message from _GENTLE_MESSAGES_EN."""
        room = _make_room("en")
        engine = InterventionEngine(room)
        for _ in range(30):
            msg = engine.random_gentle_message(lang="en")
            assert msg in _GENTLE_MESSAGES_EN, (
                f"Message {msg!r} not in English gentle messages list"
            )

    def test_english_gentle_message_has_no_cjk(self) -> None:
        """Every English gentle message is free of CJK characters."""
        for msg in _GENTLE_MESSAGES_EN:
            assert not _has_cjk(msg), f"English canned message contains CJK: {msg!r}"

    def test_chinese_gentle_message_from_chinese_list(self) -> None:
        """random_gentle_message(lang='zh') always returns a message from _GENTLE_MESSAGES_ZH."""
        room = _make_room("zh")
        engine = InterventionEngine(room)
        for _ in range(30):
            msg = engine.random_gentle_message(lang="zh")
            assert msg in _GENTLE_MESSAGES_ZH, (
                f"Message {msg!r} not in Chinese gentle messages list"
            )

    def test_chinese_gentle_messages_all_have_cjk(self) -> None:
        """Every Chinese gentle message contains CJK characters."""
        for msg in _GENTLE_MESSAGES_ZH:
            assert _has_cjk(msg), f"Chinese canned message has no CJK: {msg!r}"

    def test_vote_reminder_english_room(self) -> None:
        """_check_vote_reminder for an English room returns the English reminder string."""
        room = _make_room("en")
        engine = InterventionEngine(room)
        engine.last_dm_time = 0.0  # force cooldown pass
        trigger = engine._check_vote_reminder()
        assert trigger is not None
        assert trigger.canned_text == _VOTE_REMINDER_EN
        assert not _has_cjk(_VOTE_REMINDER_EN)

    def test_vote_reminder_chinese_room(self) -> None:
        """_check_vote_reminder for a Chinese room returns the Chinese reminder string."""
        room = _make_room("zh")
        engine = InterventionEngine(room)
        engine.last_dm_time = 0.0
        trigger = engine._check_vote_reminder()
        assert trigger is not None
        assert trigger.canned_text == _VOTE_REMINDER_ZH
        assert _has_cjk(_VOTE_REMINDER_ZH)

    def test_english_explicit_keywords_trigger_intervention(self) -> None:
        """English help keywords ('hint', 'help me') trigger explicit intervention."""
        room = _make_room("en")
        engine = InterventionEngine(room)
        for phrase in ("Can you give me a hint?", "Help me please", "Tell me something"):
            trigger = engine._evaluate_explicit("uid-1", phrase)
            assert trigger is not None, (
                f"Expected explicit trigger for English phrase {phrase!r}, got None"
            )
            assert trigger.type == "explicit"

    def test_chinese_explicit_keywords_still_work(self) -> None:
        """Chinese help keywords still trigger intervention in Chinese rooms."""
        room = _make_room("zh")
        engine = InterventionEngine(room)
        for phrase in ("给我提示吧", "帮我想想", "告诉我"):
            trigger = engine._evaluate_explicit("uid-1", phrase)
            assert trigger is not None, (
                f"Expected explicit trigger for Chinese phrase {phrase!r}, got None"
            )
            assert trigger.type == "explicit"

    def test_at_dm_triggers_in_both_languages(self) -> None:
        """@DM mention triggers explicit intervention regardless of room language."""
        for lang in ("zh", "en"):
            room = _make_room(lang)
            engine = InterventionEngine(room)
            trigger = engine._evaluate_explicit("uid-1", "@DM help!")
            assert trigger is not None, f"@DM should trigger in {lang!r} room"
            assert trigger.type == "explicit"

    def test_english_investigation_messages_are_english(self) -> None:
        """Investigation-phase gentle messages in English room are in English."""
        from app.intervention import _INVESTIGATION_MESSAGES_EN
        room = _make_room("en")
        engine = InterventionEngine(room)
        for _ in range(20):
            msg = engine.random_gentle_message(phase="investigation", lang="en")
            assert not _has_cjk(msg), (
                f"English investigation message contains CJK: {msg!r}"
            )
            assert msg in _INVESTIGATION_MESSAGES_EN
