"""DM logic unit tests — no real LLM calls, deterministic."""

from __future__ import annotations

import json

import pytest

from app.dm import (
    MISS_THRESHOLD,
    assemble_prompt,
    check_hint_needed,
    check_spoiler_leak,
    dm_turn,
    get_next_hint,
    parse_dm_response,
)
from app.llm import strip_think
from app.models import DMOutput, GameSession, Puzzle


# ===========================================================================
# Helpers
# ===========================================================================


def _valid_dm_json(**overrides) -> str:
    """Build a minimal valid DMOutput JSON string."""
    base = {
        "judgment": "无关",
        "response": "这与谜题无关。",
        "truth_progress": 0.0,
        "should_hint": False,
    }
    base.update(overrides)
    return json.dumps(base)


def _fresh_session(puzzle: Puzzle, **kwargs) -> GameSession:
    return GameSession(session_id="t", puzzle=puzzle, history=[], **kwargs)


# ===========================================================================
# 1. Prompt assembly
# ===========================================================================


class TestAssemblePrompt:
    def test_surface_present(self, sample_puzzle: Puzzle) -> None:
        prompt = assemble_prompt(sample_puzzle)
        assert sample_puzzle.surface in prompt

    def test_truth_present(self, sample_puzzle: Puzzle) -> None:
        prompt = assemble_prompt(sample_puzzle)
        assert sample_puzzle.truth in prompt

    def test_surface_appears_before_truth(self, sample_puzzle: Puzzle) -> None:
        prompt = assemble_prompt(sample_puzzle)
        assert prompt.index(sample_puzzle.surface) < prompt.index(sample_puzzle.truth)

    def test_all_key_facts_present(self, sample_puzzle: Puzzle) -> None:
        prompt = assemble_prompt(sample_puzzle)
        for fact in sample_puzzle.key_facts:
            assert fact in prompt, f"key_fact missing from prompt: {fact!r}"

    def test_truth_section_marked_secret(self, sample_puzzle: Puzzle) -> None:
        """The truth section must be labelled as classified so the LLM knows not to repeat it."""
        prompt = assemble_prompt(sample_puzzle)
        assert "绝密" in prompt

    def test_json_schema_present(self, sample_puzzle: Puzzle) -> None:
        prompt = assemble_prompt(sample_puzzle)
        assert "judgment" in prompt
        assert "truth_progress" in prompt
        assert "should_hint" in prompt

    def test_four_judgment_values_documented(self, sample_puzzle: Puzzle) -> None:
        prompt = assemble_prompt(sample_puzzle)
        for label in ("是", "不是", "无关", "部分正确"):
            assert label in prompt, f"Judgment label {label!r} missing from prompt"

    def test_surface_section_before_truth_section(self, sample_puzzle: Puzzle) -> None:
        """The 汤面 *section* header must appear before the 汤底 *section* header.
        (The word 汤底 also appears earlier in the rules, so we look for the headers.)
        """
        prompt = assemble_prompt(sample_puzzle)
        # Section headers as written by assemble_prompt
        surface_header = "汤面（玩家已知内容）"
        truth_header = "【绝密】汤底"
        assert surface_header in prompt, f"Surface section header missing: {surface_header!r}"
        assert truth_header in prompt, f"Truth section header missing: {truth_header!r}"
        assert prompt.index(surface_header) < prompt.index(truth_header)


# ===========================================================================
# 2. parse_dm_response
# ===========================================================================


class TestParseDMResponse:
    # ----- Happy paths -----

    def test_valid_json_parsed_correctly(self) -> None:
        raw = _valid_dm_json(judgment="是", truth_progress=0.4)
        out = parse_dm_response(raw)
        assert out.judgment == "是"
        assert out.truth_progress == pytest.approx(0.4)
        assert isinstance(out, DMOutput)

    def test_all_four_judgments_accepted(self) -> None:
        for j in ("是", "不是", "无关", "部分正确"):
            out = parse_dm_response(_valid_dm_json(judgment=j))
            assert out.judgment == j

    def test_should_hint_true_propagated(self) -> None:
        raw = _valid_dm_json(should_hint=True)
        out = parse_dm_response(raw)
        assert out.should_hint is True

    def test_think_tags_stripped_before_parsing(self) -> None:
        payload = _valid_dm_json(judgment="不是", truth_progress=0.1)
        raw = f"<think>内部推理……这是秘密的推理过程</think>{payload}"
        out = parse_dm_response(raw)
        assert out.judgment == "不是"
        assert out.truth_progress == pytest.approx(0.1)

    def test_multiline_think_tags_stripped(self) -> None:
        payload = _valid_dm_json(judgment="部分正确")
        raw = f"<think>\n第一行\n第二行\n</think>\n{payload}"
        out = parse_dm_response(raw)
        assert out.judgment == "部分正确"

    def test_markdown_code_fence_json(self) -> None:
        payload = _valid_dm_json(judgment="是", truth_progress=0.6)
        raw = f"```json\n{payload}\n```"
        out = parse_dm_response(raw)
        assert out.judgment == "是"
        assert out.truth_progress == pytest.approx(0.6)

    def test_bare_markdown_fence_without_language_tag(self) -> None:
        payload = _valid_dm_json(judgment="无关")
        raw = f"```\n{payload}\n```"
        out = parse_dm_response(raw)
        assert out.judgment == "无关"

    def test_think_plus_fenced_json(self) -> None:
        payload = _valid_dm_json(judgment="是")
        raw = f"<think>分析中</think>\n```json\n{payload}\n```"
        out = parse_dm_response(raw)
        assert out.judgment == "是"

    # ----- Fallback / error paths -----

    def test_plain_text_fallback_returns_safe_defaults(self) -> None:
        out = parse_dm_response("这不是JSON格式的内容，完全是纯文本。")
        assert out.judgment == "无关"
        assert out.truth_progress == 0.0
        assert out.should_hint is False

    def test_empty_string_fallback(self) -> None:
        out = parse_dm_response("")
        assert out.judgment == "无关"
        assert isinstance(out.response, str)

    def test_truncated_json_fallback(self) -> None:
        out = parse_dm_response('{"judgment": "是", "response": "对')
        # Truncated JSON is unparseable → fallback
        assert out.judgment == "无关"

    def test_fallback_response_not_empty(self) -> None:
        """The fallback must always give the player some response string."""
        out = parse_dm_response("gibberish")
        assert len(out.response) > 0

    def test_think_only_input_fallback(self) -> None:
        """A message consisting only of a think block should fall back gracefully."""
        out = parse_dm_response("<think>只有推理，没有输出</think>")
        assert out.judgment == "无关"


# ===========================================================================
# 3. strip_think (llm utility, tested here because it feeds parse_dm_response)
# ===========================================================================


class TestStripThink:
    def test_strips_single_block(self) -> None:
        assert strip_think("<think>secret</think>answer") == "answer"

    def test_strips_multiline_block(self) -> None:
        result = strip_think("<think>\nline1\nline2\n</think>result")
        assert result == "result"

    def test_no_think_tags_unchanged(self) -> None:
        text = '{"judgment": "是"}'
        assert strip_think(text) == text

    def test_empty_string(self) -> None:
        assert strip_think("") == ""


# ===========================================================================
# 4. check_spoiler_leak
# ===========================================================================


class TestCheckSpoilerLeak:
    def test_detects_verbatim_key_fact(self, sample_puzzle: Puzzle) -> None:
        # Embed the first key_fact directly in a response
        leaky = f"是的，{sample_puzzle.key_facts[0]}，这就是原因。"
        assert check_spoiler_leak(leaky, sample_puzzle) is True

    def test_detects_any_key_fact(self, sample_puzzle: Puzzle) -> None:
        for fact in sample_puzzle.key_facts:
            assert check_spoiler_leak(fact, sample_puzzle) is True

    def test_safe_response_not_flagged(self, sample_puzzle: Puzzle) -> None:
        safe = "这个问题很有意思，请继续从另一个角度思考。"
        assert check_spoiler_leak(safe, sample_puzzle) is False

    def test_partial_short_overlap_not_flagged(self, sample_puzzle: Puzzle) -> None:
        """Very short common words (< 4 chars) that happen to appear in a key_fact
        should NOT trigger a false positive if they don't form a meaningful extract."""
        # "男人" (2 chars) in isolation is far shorter than any full key_fact,
        # so the key_fact ("男人曾在海上遇难") won't be found in "男人" itself.
        assert check_spoiler_leak("男人", sample_puzzle) is False

    def test_empty_response_not_flagged(self, sample_puzzle: Puzzle) -> None:
        assert check_spoiler_leak("", sample_puzzle) is False


# ===========================================================================
# 5. check_hint_needed / get_next_hint
# ===========================================================================


class TestHintLogic:
    def test_not_needed_at_zero_misses(self, sample_puzzle: Puzzle) -> None:
        session = _fresh_session(sample_puzzle, consecutive_misses=0)
        assert check_hint_needed(session) is False

    def test_not_needed_one_below_threshold(self, sample_puzzle: Puzzle) -> None:
        session = _fresh_session(sample_puzzle, consecutive_misses=MISS_THRESHOLD - 1)
        assert check_hint_needed(session) is False

    def test_needed_at_threshold(self, sample_puzzle: Puzzle) -> None:
        session = _fresh_session(sample_puzzle, consecutive_misses=MISS_THRESHOLD)
        assert check_hint_needed(session) is True

    def test_needed_above_threshold(self, sample_puzzle: Puzzle) -> None:
        session = _fresh_session(sample_puzzle, consecutive_misses=MISS_THRESHOLD + 3)
        assert check_hint_needed(session) is True

    def test_miss_threshold_is_5(self) -> None:
        """Explicit assertion so a future change to MISS_THRESHOLD breaks loudly."""
        assert MISS_THRESHOLD == 5

    def test_get_next_hint_returns_first(self, sample_puzzle: Puzzle) -> None:
        session = _fresh_session(sample_puzzle, hint_index=0)
        hint = get_next_hint(session)
        assert hint == sample_puzzle.hints[0]
        assert session.hint_index == 1

    def test_get_next_hint_advances_index(self, sample_puzzle: Puzzle) -> None:
        session = _fresh_session(sample_puzzle, hint_index=0)
        for i, expected in enumerate(sample_puzzle.hints):
            hint = get_next_hint(session)
            assert hint == expected
            assert session.hint_index == i + 1

    def test_get_next_hint_exhausted_returns_none(self, sample_puzzle: Puzzle) -> None:
        session = _fresh_session(sample_puzzle, hint_index=len(sample_puzzle.hints))
        assert get_next_hint(session) is None

    def test_hint_index_not_incremented_when_exhausted(self, sample_puzzle: Puzzle) -> None:
        total = len(sample_puzzle.hints)
        session = _fresh_session(sample_puzzle, hint_index=total)
        get_next_hint(session)
        assert session.hint_index == total  # unchanged


# ===========================================================================
# 6. dm_turn — full pipeline with mock LLM
# ===========================================================================


class TestDMTurn:
    async def test_history_updated_with_user_and_assistant_messages(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        session = _fresh_session(sample_puzzle)
        await dm_turn(session, "男人是故意去餐厅的吗？")
        assert len(session.history) == 2
        assert session.history[0] == {"role": "user", "content": "男人是故意去餐厅的吗？"}
        assert session.history[1]["role"] == "assistant"

    async def test_raw_response_stored_in_history(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        """History must preserve the raw (think-tagged) response for multi-turn quality."""
        raw = f"<think>推理</think>{_valid_dm_json(judgment='是')}"
        mock_llm.set_response(raw)
        session = _fresh_session(sample_puzzle)
        await dm_turn(session, "测试")
        stored = session.history[1]["content"]
        assert "<think>" in stored  # raw, not stripped

    async def test_judgment_returned_correctly(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        mock_llm.set_response(_valid_dm_json(judgment="是", truth_progress=0.3))
        session = _fresh_session(sample_puzzle)
        result = await dm_turn(session, "男人遭遇过海难吗？")
        assert result.judgment == "是"
        assert result.truth_progress == pytest.approx(0.3)

    async def test_truth_progress_capped_at_1(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        mock_llm.set_response(_valid_dm_json(judgment="是", truth_progress=1.5))
        session = _fresh_session(sample_puzzle)
        result = await dm_turn(session, "测试")
        assert result.truth_progress <= 1.0

    async def test_consecutive_misses_incremented_on_wuguan(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        mock_llm.set_response(_valid_dm_json(judgment="无关"))
        session = _fresh_session(sample_puzzle)
        await dm_turn(session, "男人喜欢打篮球吗？")
        assert session.consecutive_misses == 1

    async def test_consecutive_misses_incremented_on_bushi(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        mock_llm.set_response(_valid_dm_json(judgment="不是"))
        session = _fresh_session(sample_puzzle)
        await dm_turn(session, "男人是外国人吗？")
        assert session.consecutive_misses == 1

    async def test_consecutive_misses_reset_on_shi(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        mock_llm.set_response(_valid_dm_json(judgment="是", truth_progress=0.2))
        session = _fresh_session(sample_puzzle, consecutive_misses=4)
        await dm_turn(session, "男人曾经遭遇危险？")
        assert session.consecutive_misses == 0

    async def test_consecutive_misses_reset_on_partial(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        mock_llm.set_response(_valid_dm_json(judgment="部分正确", truth_progress=0.2))
        session = _fresh_session(sample_puzzle, consecutive_misses=3)
        await dm_turn(session, "男人的妻子死了？")
        assert session.consecutive_misses == 0

    async def test_hint_given_after_miss_threshold(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        """After MISS_THRESHOLD consecutive misses, the DM must provide a hint."""
        mock_llm.set_response(_valid_dm_json(judgment="无关"))
        # One away from threshold
        session = _fresh_session(sample_puzzle, consecutive_misses=MISS_THRESHOLD - 1)
        result = await dm_turn(session, "无关的问题")
        assert result.hint is not None
        assert result.should_hint is True

    async def test_hint_given_when_llm_requests_it(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        mock_llm.set_response(_valid_dm_json(should_hint=True))
        session = _fresh_session(sample_puzzle)
        result = await dm_turn(session, "某个问题")
        assert result.hint is not None

    async def test_no_hint_when_hints_exhausted(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        mock_llm.set_response(_valid_dm_json(judgment="无关", should_hint=True))
        session = _fresh_session(
            sample_puzzle,
            hint_index=len(sample_puzzle.hints),  # all hints used
        )
        result = await dm_turn(session, "某个问题")
        assert result.hint is None
        assert result.should_hint is False

    async def test_game_finishes_when_progress_reaches_1(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        mock_llm.set_response(_valid_dm_json(judgment="是", truth_progress=1.0))
        session = _fresh_session(sample_puzzle)
        result = await dm_turn(session, "男人喝了妻子的肉？")
        assert session.finished is True
        assert result.truth == sample_puzzle.truth

    async def test_truth_not_revealed_below_1(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        mock_llm.set_response(_valid_dm_json(judgment="是", truth_progress=0.99))
        session = _fresh_session(sample_puzzle)
        result = await dm_turn(session, "接近了但没到")
        assert session.finished is False
        assert result.truth is None

    async def test_prompt_sent_to_llm_contains_surface_and_truth(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        """Verify the assembled prompt sent to the LLM has the right content."""
        session = _fresh_session(sample_puzzle)
        await dm_turn(session, "测试问题")
        system_prompt = mock_llm.last_system_prompt
        assert sample_puzzle.surface in system_prompt
        assert sample_puzzle.truth in system_prompt

    async def test_prompt_sent_exactly_once_per_turn(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        session = _fresh_session(sample_puzzle)
        await dm_turn(session, "第一个问题")
        await dm_turn(session, "第二个问题")
        assert mock_llm.call_count == 2

    async def test_history_grows_across_turns(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        session = _fresh_session(sample_puzzle)
        await dm_turn(session, "第一个问题")
        await dm_turn(session, "第二个问题")
        # 2 turns × (user + assistant) = 4 messages
        assert len(session.history) == 4

    async def test_spoiler_replaced_when_leak_detected(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        """If the LLM somehow leaks a key_fact, dm_turn must replace the response."""
        leaky_response = f"是的，{sample_puzzle.key_facts[0]}就是真相。"
        mock_llm.set_response(
            _valid_dm_json(judgment="是", response=leaky_response, truth_progress=0.5)
        )
        session = _fresh_session(sample_puzzle)
        result = await dm_turn(session, "泄露测试")
        assert result.response != leaky_response
        assert not check_spoiler_leak(result.response, sample_puzzle)

    async def test_fallback_response_on_malformed_llm_output(
        self, sample_puzzle: Puzzle, mock_llm
    ) -> None:
        """Malformed LLM output must not crash dm_turn."""
        mock_llm.set_response("这不是JSON，纯文本乱码")
        session = _fresh_session(sample_puzzle)
        result = await dm_turn(session, "某个问题")
        # Should return a safe fallback, not raise
        assert isinstance(result.response, str)
        assert result.judgment == "无关"  # fallback judgment


# ===========================================================================
# 7. Integration (real LLM — slow, skipped without --slow)
# ===========================================================================


@pytest.mark.slow
class TestDMIntegration:
    async def test_classic_puzzle_multi_turn_progress(
        self, sample_puzzle: Puzzle, real_llm
    ) -> None:
        """Walk through several known-correct deductions and confirm progress rises."""
        session = _fresh_session(sample_puzzle)

        # These questions directly probe the key_facts
        deductions = [
            "男人曾经遭遇过海难吗？",
            "男人的妻子在故事中去世了吗？",
            "当年那碗汤真的是海龟汤吗？",
        ]
        for question in deductions:
            result = await dm_turn(session, question)
            assert result.judgment in ("是", "不是", "无关", "部分正确")

        assert result.truth_progress > 0.5, (  # type: ignore[possibly-undefined]
            "After probing all key deductions, truth_progress should exceed 50%"
        )
