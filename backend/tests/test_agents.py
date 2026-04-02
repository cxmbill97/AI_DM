"""Tests for Phase 4 multi-agent pipeline.

Coverage:
- RouterAgent: intent classification for all 7 intents
- JudgeAgent: output parsing, fallback on LLM failure
- NarratorAgent: output with mocked LLM, fallback on failure
- SafetyAgent: verbatim detection, viewer exclusion, LLM check
- AgentOrchestrator: full pipeline with mocked LLM, phase guard, each intent branch

These tests use mock LLM (no real API calls) except where marked @pytest.mark.slow.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.agents.judge import _FALLBACK_JUDGMENT, JudgeAgent
from app.agents.narrator import _FALLBACK_RESPONSE, _REGENERATION_FALLBACK, NarratorAgent
from app.agents.orchestrator import (
    RESP_CLUE_FOUND,
    RESP_DM,
    RESP_META,
    RESP_PHASE_BLOCKED,
    AgentOrchestrator,
)
from app.agents.router import RouterAgent
from app.agents.safety import SafetyAgent
from app.models import NPC, Character, Phase, Script, ScriptClue, ScriptMetadata, ScriptTruth
from app.state_machine import GameStateMachine
from app.visibility import VisibleContext

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

KEY_FACTS = [
    "死者威士忌杯中含有安眠药成分",
    "死者系被人在昏迷状态下推倒撞上壁炉石台致死",
    "22:13走廊监控记录到浅色衣物人影朝书房方向行走",
]

CHARACTER_SECRETS = {
    "char_su": "与死者存在长达十年的秘密婚外情，并育有一名未对外公开的孩子，案发当晚曾单独与死者见面",
    "char_chen": "欠死者三百万债务，曾多次恳求宽限还款期限但均遭死者拒绝，案发前一天再次被催款",
    "char_shen": "是死者私生女，案发当晚在死者威士忌中秘密投入安眠药后趁其昏迷推倒致死",
}


def _make_visible(player_id: str = "p1", char_id: str = "char_su") -> VisibleContext:
    return VisibleContext(
        player_id=player_id,
        player_slot=char_id,
        surface="欢迎来到雨夜迷踪",
        public_clues=[],
        private_clues=[],
    )


# ---------------------------------------------------------------------------
# Minimal Script fixture
# ---------------------------------------------------------------------------


def _make_script() -> Script:
    phases = [
        Phase(
            id="opening",
            type="narration",
            next="investigation_1",
            duration_seconds=120,
            allowed_actions={"listen"},
            dm_script="欢迎来到雨夜迷踪",
        ),
        Phase(
            id="investigation_1",
            type="investigation",
            next="discussion",
            duration_seconds=600,
            allowed_actions={"ask_dm", "search", "private_chat"},
            available_clues=["clue_001"],
        ),
        Phase(
            id="discussion",
            type="discussion",
            next="voting",
            duration_seconds=600,
            allowed_actions={"public_chat", "private_chat"},
        ),
        Phase(
            id="voting",
            type="voting",
            next="reveal",
            duration_seconds=120,
            allowed_actions={"cast_vote"},
        ),
        Phase(
            id="reveal",
            type="reveal",
            next=None,
            duration_seconds=None,
            allowed_actions={"listen"},
        ),
    ]
    characters = [
        Character(
            id="char_su",
            name="苏雅",
            public_bio="知名女演员",
            secret_bio=CHARACTER_SECRETS["char_su"],
            is_culprit=False,
        ),
        Character(
            id="char_shen",
            name="沈清",
            public_bio="别墅管理人",
            secret_bio=CHARACTER_SECRETS["char_shen"],
            is_culprit=True,
        ),
    ]
    clues = [
        ScriptClue(
            id="clue_001",
            title="毒理检验报告",
            content="威士忌杯含有安眠药",
            phase_available="investigation_1",
            visibility="public",
            unlock_keywords=["毒", "药", "威士忌"],
        ),
    ]
    npcs = [
        NPC(
            id="npc_butler",
            name="管家老周",
            persona="沉稳老管家",
            knowledge=["clue_001"],
            speech_style="formal_elderly",
        ),
    ]
    truth = ScriptTruth(
        culprit="char_shen",
        motive="私生女动机",
        method="投药后推倒",
        timeline="22:00投药，22:20推倒",
        key_facts=KEY_FACTS,
    )
    return Script(
        id="test_001",
        title="测试剧本",
        metadata=ScriptMetadata(
            player_count=2,
            duration_minutes=20,
            difficulty="beginner",
        ),
        characters=characters,
        phases=phases,
        clues=clues,
        npcs=npcs,
        truth=truth,
    )


# ---------------------------------------------------------------------------
# RouterAgent
# ---------------------------------------------------------------------------


class TestRouterAgent:
    def setup_method(self) -> None:
        self.router = RouterAgent(npc_names=["管家老周", "李探长"])

    def test_vote_intent_slash_vote(self) -> None:
        c = self.router.classify("/vote char_shen", "voting")
        assert c.intent == "vote"

    def test_vote_intent_chinese(self) -> None:
        c = self.router.classify("投票给沈清", "voting")
        assert c.intent == "vote"

    def test_npc_intent_by_name(self) -> None:
        c = self.router.classify("管家老周，你当晚在哪里？", "investigation_1")
        assert c.intent == "npc"

    def test_npc_intent_by_at_mention(self) -> None:
        c = self.router.classify("@李探长 请问现场情况", "investigation_1")
        assert c.intent == "npc"

    def test_accuse_intent(self) -> None:
        c = self.router.classify("凶手是沈清", "discussion")
        assert c.intent == "accuse"

    def test_question_intent_question_mark(self) -> None:
        c = self.router.classify("死者是什么时候死的?", "investigation_1")
        assert c.intent == "question"

    def test_question_intent_ma(self) -> None:
        c = self.router.classify("威士忌杯有毒吗", "investigation_1")
        assert c.intent == "question"

    def test_search_intent(self) -> None:
        c = self.router.classify("我要搜查书房", "investigation_1")
        assert c.intent == "search"

    def test_meta_intent(self) -> None:
        c = self.router.classify("规则", "opening")
        assert c.intent == "meta"

    def test_chat_intent_default(self) -> None:
        c = self.router.classify("好的我明白了", "discussion")
        assert c.intent == "chat"

    def test_matched_rule_populated(self) -> None:
        c = self.router.classify("/vote x", "voting")
        assert c.matched_rule != ""

    def test_accuse_before_question_priority(self) -> None:
        # "凶手是X吗" has accuse framing → accuse wins over question
        c = self.router.classify("凶手是沈清吗", "discussion")
        assert c.intent == "accuse"


# ---------------------------------------------------------------------------
# JudgeAgent (mocked LLM)
# ---------------------------------------------------------------------------


class TestJudgeAgent:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.judge = JudgeAgent(key_facts=KEY_FACTS)
        self.mock_calls: list[tuple[str, list]] = []

        async def fake_chat(system: str, messages: list) -> str:
            self.mock_calls.append((system, messages))
            return self._response

        self._response = json.dumps(
            {
                "result": "是",
                "confidence": 0.9,
                "relevant_fact_ids": ["fact_0"],
            }
        )
        monkeypatch.setattr("app.agents.judge.chat", fake_chat)

    async def test_judge_returns_correct_result(self) -> None:
        judgment = await self.judge.judge("死者是被毒死的吗")
        assert judgment["result"] == "是"
        assert judgment["confidence"] == pytest.approx(0.9)
        assert "fact_0" in judgment["relevant_fact_ids"]

    async def test_judge_calls_llm_once(self) -> None:
        await self.judge.judge("威士忌杯有问题吗")
        assert len(self.mock_calls) == 1

    async def test_judge_key_facts_in_system_prompt(self) -> None:
        await self.judge.judge("some question")
        system_prompt = self.mock_calls[0][0]
        assert KEY_FACTS[0] in system_prompt

    async def test_judge_fallback_on_llm_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def failing_chat(*_: Any) -> str:
            raise RuntimeError("network error")

        monkeypatch.setattr("app.agents.judge.chat", failing_chat)
        judgment = await self.judge.judge("any question")
        assert judgment == _FALLBACK_JUDGMENT

    async def test_judge_handles_markdown_fenced_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fenced_chat(*_: Any) -> str:
            return '```json\n{"result":"不是","confidence":0.7,"relevant_fact_ids":[]}\n```'

        monkeypatch.setattr("app.agents.judge.chat", fenced_chat)
        judgment = await self.judge.judge("test")
        assert judgment["result"] == "不是"

    async def test_judge_invalid_result_normalised_to_wuguan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def bad_chat(*_: Any) -> str:
            return json.dumps({"result": "UNKNOWN", "confidence": 0.5, "relevant_fact_ids": []})

        monkeypatch.setattr("app.agents.judge.chat", bad_chat)
        judgment = await self.judge.judge("test")
        assert judgment["result"] == "无关"

    async def test_judge_confidence_clamped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def extreme_chat(*_: Any) -> str:
            return json.dumps({"result": "是", "confidence": 99.0, "relevant_fact_ids": []})

        monkeypatch.setattr("app.agents.judge.chat", extreme_chat)
        judgment = await self.judge.judge("test")
        assert judgment["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# NarratorAgent (mocked LLM)
# ---------------------------------------------------------------------------


class TestNarratorAgent:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.narrator = NarratorAgent()
        self._response = "这是一个很有意思的线索，值得深入探讨。"
        self.mock_calls: list[tuple[str, list]] = []

        async def fake_chat(system: str, messages: list) -> str:
            self.mock_calls.append((system, messages))
            return self._response

        monkeypatch.setattr("app.agents.narrator.chat", fake_chat)

    async def test_narrator_returns_text(self) -> None:
        judgment = {"result": "是", "confidence": 0.9, "relevant_fact_ids": ["fact_0"]}
        text = await self.narrator.narrate(
            judgment=judgment,
            player_message="威士忌杯有毒吗",
            visible_context=_make_visible(),
            phase="investigation_1",
        )
        assert text == self._response

    async def test_narrator_without_truth(self) -> None:
        judgment = {"result": "无关", "confidence": 0.3, "relevant_fact_ids": []}
        await self.narrator.narrate(
            judgment=judgment,
            player_message="随便问问",
            visible_context=_make_visible(),
            phase="investigation_1",
            truth_for_reveal=None,
        )
        system_prompt = self.mock_calls[0][0]
        # Truth section should NOT appear
        assert "真相揭晓" not in system_prompt

    async def test_narrator_with_truth_in_reveal(self) -> None:
        judgment = {"result": "是", "confidence": 1.0, "relevant_fact_ids": []}
        truth_text = "凶手：沈清\n动机：私生女\n手法：投药"
        await self.narrator.narrate(
            judgment=judgment,
            player_message="真相是什么",
            visible_context=_make_visible(),
            phase="reveal",
            truth_for_reveal=truth_text,
        )
        system_prompt = self.mock_calls[0][0]
        assert "真相揭晓" in system_prompt
        assert "沈清" in system_prompt

    async def test_narrator_fallback_on_empty_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def empty_chat(*_: Any) -> str:
            return ""

        monkeypatch.setattr("app.agents.narrator.chat", empty_chat)
        judgment = {"result": "无关", "confidence": 0.0, "relevant_fact_ids": []}
        text = await self.narrator.narrate(
            judgment=judgment,
            player_message="test",
            visible_context=_make_visible(),
            phase="investigation_1",
        )
        assert text == _FALLBACK_RESPONSE

    async def test_narrator_fallback_on_llm_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def failing_chat(*_: Any) -> str:
            raise RuntimeError("timeout")

        monkeypatch.setattr("app.agents.narrator.chat", failing_chat)
        judgment = {"result": "是", "confidence": 0.8, "relevant_fact_ids": []}
        text = await self.narrator.narrate(
            judgment=judgment,
            player_message="test",
            visible_context=_make_visible(),
            phase="investigation_1",
        )
        assert text == _FALLBACK_RESPONSE


# ---------------------------------------------------------------------------
# SafetyAgent
# ---------------------------------------------------------------------------


class TestSafetyAgent:
    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        self.safety = SafetyAgent(
            key_facts=KEY_FACTS,
            character_secrets=CHARACTER_SECRETS,
        )

    async def test_safe_text_passes(self) -> None:
        result = await self.safety.check(
            text="今晚的晚宴气氛很奇怪，每个人都有秘密。",
            audience_player_id="p1",
        )
        assert result["safe"] is True

    async def test_verbatim_key_fact_blocked(self) -> None:
        # Include a key_fact verbatim (>= 8 chars)
        text = f"我知道{KEY_FACTS[0]}，这就是关键。"
        result = await self.safety.check(
            text=text,
            audience_player_id="p1",
        )
        assert result["safe"] is False
        assert result["leaked_content"] is not None

    async def test_viewer_own_secret_not_blocked(self) -> None:
        # char_su is viewing — their own secret should not be flagged
        text = f"我自己的秘密：{CHARACTER_SECRETS['char_su']}"
        result = await self.safety.check(
            text=text,
            audience_player_id="p1",
            viewer_char_id="char_su",
        )
        assert result["safe"] is True

    async def test_other_player_secret_blocked(self) -> None:
        # char_su viewing, but text contains char_chen's secret verbatim (30+ chars)
        secret_snippet = CHARACTER_SECRETS["char_chen"]  # 30+ chars, > _MIN_SECRET_SNIPPET_LEN
        text = f"陈博的情况：{secret_snippet}"
        result = await self.safety.check(
            text=text,
            audience_player_id="p1",
            viewer_char_id="char_su",
        )
        assert result["safe"] is False

    async def test_short_safe_text(self) -> None:
        # Short text with no forbidden content
        result = await self.safety.check(
            text="ok",
            audience_player_id="p1",
        )
        assert result["safe"] is True

    async def test_long_safe_text_no_llm(self) -> None:
        # Verbatim-clean long text should pass without needing LLM (LLM removed)
        long_text = "这是一段足够长的文本，没有任何违禁内容在其中。探案中，每位玩家都在努力寻找真相。"
        result = await self.safety.check(text=long_text, audience_player_id="p1")
        assert result["safe"] is True


# ---------------------------------------------------------------------------
# AgentOrchestrator — pipeline integration (mock LLM)
# ---------------------------------------------------------------------------


class TestOrchestratorPipeline:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.script = _make_script()
        self.sm = GameStateMachine(self.script.phases)
        # Advance to investigation phase where most actions are allowed
        self.sm.advance()  # opening → investigation_1
        self.orchestrator = AgentOrchestrator(
            script=self.script,
            state_machine=self.sm,
            player_char_map={"p1": "char_su", "p2": "char_shen"},
        )
        # Patch chat to return safe narrator text + safe safety result
        self._judge_response = json.dumps(
            {
                "result": "是",
                "confidence": 0.85,
                "relevant_fact_ids": ["fact_0"],
            }
        )
        self._narrator_response = "这是一个很重要的发现，值得深入探讨。"
        self._safety_response = json.dumps({"safe": True, "leaked_content": None})
        self._call_count = 0

        async def fake_chat(system: str, messages: list) -> str:
            self._call_count += 1
            # Route by content: Judge uses JSON-only output; Narrator uses natural language
            if "判断引擎" in system or "真相判断引擎" in system:
                return self._judge_response
            if "安全检查" in system or "禁止透露" in (messages[0].get("content") if messages else ""):
                return self._safety_response
            return self._narrator_response

        monkeypatch.setattr("app.agents.judge.chat", fake_chat)
        monkeypatch.setattr("app.agents.narrator.chat", fake_chat)

    async def test_question_intent_returns_dm_response(self) -> None:
        response, trace = await self.orchestrator.handle_message("p1", "威士忌杯有毒吗")
        assert response is not None
        assert response.type == RESP_DM
        assert response.text is not None
        assert any(s.agent == "judge" for s in trace.steps)

    async def test_accuse_intent_returns_dm_response(self) -> None:
        response, trace = await self.orchestrator.handle_message("p1", "凶手是沈清")
        assert response is not None
        assert response.type == RESP_DM
        assert trace.steps[0].agent == "router"

    async def test_chat_intent_returns_none(self) -> None:
        self.sm.current_phase = "discussion"
        response, trace = await self.orchestrator.handle_message("p1", "好的大家继续")
        assert response is None
        assert trace.steps[0].agent == "router"

    async def test_meta_intent_returns_meta_response(self) -> None:
        response, trace = await self.orchestrator.handle_message("p1", "规则")
        assert response is not None
        assert response.type == RESP_META

    async def test_search_with_keyword_returns_clue_found(self) -> None:
        response, trace = await self.orchestrator.handle_message("p1", "我要搜查威士忌杯")
        assert response is not None
        assert response.type == RESP_CLUE_FOUND
        assert response.clue is not None
        assert response.clue["id"] == "clue_001"

    async def test_search_without_keyword_returns_dm_response(self) -> None:
        response, trace = await self.orchestrator.handle_message("p1", "我搜查窗帘")
        assert response is not None
        assert response.type == RESP_DM

    async def test_search_clue_not_found_twice(self) -> None:
        # First search finds it
        await self.orchestrator.handle_message("p1", "搜查威士忌")
        # Second search for the same clue returns DM response (already unlocked)
        response, trace = await self.orchestrator.handle_message("p1", "再查一下威士忌")
        assert response is not None
        assert response.type == RESP_DM  # clue already unlocked

    async def test_phase_blocked_when_action_not_allowed(self) -> None:
        # In investigation_1, cast_vote is not allowed → vote intent is blocked
        response, trace = await self.orchestrator.handle_message("p1", "我投沈清")
        assert response is not None
        assert response.type == RESP_PHASE_BLOCKED

    async def test_phase_guard_ask_dm_blocked_in_discussion(self) -> None:
        # ask_dm is not in discussion allowed actions
        self.sm.current_phase = "discussion"
        response, trace = await self.orchestrator.handle_message("p1", "威士忌杯有毒吗")
        assert response is not None
        assert response.type == RESP_PHASE_BLOCKED

    async def test_meta_always_allowed_regardless_of_phase(self) -> None:
        self.sm.current_phase = "reveal"
        response, trace = await self.orchestrator.handle_message("p1", "规则")
        assert response is not None
        assert response.type == RESP_META

    async def test_safety_retry_uses_fallback_after_max_retries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Make safety.check always return unsafe by patching the method directly
        from app.agents.safety import SafetyResult

        async def always_unsafe(text: str, **_: Any) -> SafetyResult:
            return SafetyResult(safe=False, leaked_content="leaked secret")

        monkeypatch.setattr(self.orchestrator.safety, "check", always_unsafe)

        response, trace = await self.orchestrator.handle_message("p1", "死者是怎么死的？")
        assert response is not None
        assert response.type == RESP_DM
        assert response.text == _REGENERATION_FALLBACK
        # Safety steps should appear (one per retry attempt)
        safety_steps = [s for s in trace.steps if s.agent == "safety"]
        assert len(safety_steps) == 3  # _MAX_SAFETY_RETRIES + 1


# ---------------------------------------------------------------------------
# NPCAgent tests
# ---------------------------------------------------------------------------


class TestNPCAgent:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.agents.npc import NPCAgent as _NPCAgent

        self._NPCAgent = _NPCAgent
        self._clues_by_id = {
            "clue_001": ScriptClue(
                id="clue_001",
                title="监控时间戳",
                content="大厅监控显示22:13有人影经过",
                phase_available="investigation_1",
                visibility="public",
                unlock_keywords=["监控"],
            ),
            "clue_002": ScriptClue(
                id="clue_002",
                title="指纹报告",
                content="书房门把手上发现不明指纹",
                phase_available="investigation_1",
                visibility="private",
                unlock_keywords=["指纹"],
            ),
        }
        self._butler_npc = NPC(
            id="npc_butler",
            name="管家老周",
            persona="60岁，在宅邸服务30年，说话恭敬但偶尔透露关键信息",
            knowledge=["clue_001"],  # knows clue_001 only, NOT clue_002
            speech_style="formal_elderly",
        )
        self.npc_agent = _NPCAgent(self._butler_npc, self._clues_by_id)
        self._captured_system: list[str] = []

        async def fake_chat(system: str, messages: list) -> str:
            self._captured_system.append(system)
            return "老爷那晚十点左右就上楼了，老朽在门口守着。"

        monkeypatch.setattr("app.agents.npc.chat", fake_chat)

    async def test_npc_stays_in_character(self) -> None:
        """NPC responds and system prompt contains persona and name."""
        response = await self.npc_agent.respond("你当晚在哪里？")
        assert response  # got something back
        system = self.npc_agent._system_prompt
        assert "管家老周" in system
        assert "30年" in system  # persona text
        # Speech style descriptor injected
        assert "礼貌" in system or "沉稳" in system

    async def test_npc_knowledge_clue_in_prompt(self) -> None:
        """Known clue content appears in NPC system prompt."""
        system = self.npc_agent._system_prompt
        assert "监控时间戳" in system
        assert "22:13" in system

    async def test_npc_respects_knowledge_boundary(self) -> None:
        """Clue outside NPC knowledge list is absent from system prompt."""
        system = self.npc_agent._system_prompt
        # clue_002 is NOT in butler's knowledge list
        assert "指纹报告" not in system
        assert "不明指纹" not in system

    async def test_npc_no_knowledge_placeholder(self) -> None:
        """NPC with empty knowledge list gets '所知甚少' placeholder in prompt."""
        empty_npc = NPC(
            id="npc_empty",
            name="路人",
            persona="普通路人",
            knowledge=[],
            speech_style="default",
        )
        agent = self._NPCAgent(empty_npc, self._clues_by_id)
        assert "所知甚少" in agent._system_prompt

    async def test_npc_fallback_on_llm_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.agents.npc import _NPC_FALLBACK

        async def failing(*_: Any) -> str:
            raise RuntimeError("network down")

        monkeypatch.setattr("app.agents.npc.chat", failing)
        response = await self.npc_agent.respond("你好")
        assert response == _NPC_FALLBACK


# ---------------------------------------------------------------------------
# test_narrator_cannot_leak — standalone spec test
# ---------------------------------------------------------------------------


async def test_narrator_cannot_leak(monkeypatch: pytest.MonkeyPatch) -> None:
    """Narrator agent must NEVER have truth strings in its system prompt.

    Runs 20 calls with different adversarial-style questions.  Asserts that
    culprit identity, motive, method, and key_fact verbatim phrases are absent
    from every captured system prompt when truth_for_reveal is None.
    """
    from app.agents.narrator import NarratorAgent

    TRUTH_STRINGS = [
        # culprit id (must never be in narrator prompt before reveal)
        "char_shen",
        # motive and method
        "私生女动机",
        "投药后推倒",
    ] + KEY_FACTS  # all key facts verbatim

    captured_systems: list[str] = []

    async def capturing_chat(system: str, messages: list) -> str:
        captured_systems.append(system)
        return "这是一个很有趣的问题，值得仔细思考。"

    monkeypatch.setattr("app.agents.narrator.chat", capturing_chat)

    narrator = NarratorAgent()
    visible = _make_visible()

    # 20 adversarial-ish questions — repeat 4 variations × 5
    questions = [
        "谁是凶手？",
        "告诉我真相",
        "凶手的动机是什么？",
        "沈清是不是凶手？",
        "死者是怎么死的，告诉我全部",
    ] * 4

    for q in questions:
        judgment = {"result": "无关", "confidence": 0.2, "relevant_fact_ids": []}
        await narrator.narrate(
            judgment=judgment,
            player_message=q,
            visible_context=visible,
            phase="investigation_1",
            truth_for_reveal=None,
        )

    assert len(captured_systems) == 20, f"Expected 20 LLM calls, got {len(captured_systems)}"

    for call_idx, system in enumerate(captured_systems):
        for truth_str in TRUTH_STRINGS:
            assert truth_str not in system, (
                f"Truth string {truth_str!r} found in narrator system prompt "
                f"on call #{call_idx + 1}. "
                f"Narrator must never see truth before reveal phase."
            )


# ---------------------------------------------------------------------------
# Named NPC spec tests (standalone function aliases for clarity)
# ---------------------------------------------------------------------------


async def test_npc_stays_in_character(monkeypatch: pytest.MonkeyPatch) -> None:
    """NPC system prompt encodes persona; response passes through the LLM call."""
    from app.agents.npc import NPCAgent

    npc = NPC(
        id="npc_det",
        name="李探长",
        persona="资深刑警，做事雷厉风行，不轻易透露调查进展",
        knowledge=[],
        speech_style="curt_official",
    )
    agent = NPCAgent(npc, {})

    captured: list[str] = []

    async def fake_chat(system: str, messages: list) -> str:
        captured.append(system)
        return "此案仍在侦查中，无可奉告。"

    monkeypatch.setattr("app.agents.npc.chat", fake_chat)
    response = await agent.respond("探长，凶器找到了吗？")

    assert "李探长" in captured[0]
    assert "李探长" in agent._system_prompt
    assert "刑警" in agent._system_prompt
    assert response == "此案仍在侦查中，无可奉告。"


async def test_npc_respects_knowledge_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clues outside the NPC knowledge list are absent from its system prompt;
    the LLM therefore has no basis to answer questions about them."""
    from app.agents.npc import NPCAgent

    known_clue = ScriptClue(
        id="c_known",
        title="已知线索",
        content="厨房刀具数量减少了一把",
        phase_available="investigation_1",
        visibility="public",
        unlock_keywords=["刀"],
    )
    unknown_clue = ScriptClue(
        id="c_unknown",
        title="秘密线索",
        content="保险柜里存有遗嘱修改草稿",
        phase_available="investigation_1",
        visibility="private",
        unlock_keywords=["保险柜"],
    )

    npc = NPC(
        id="npc_cook",
        name="厨师阿明",
        persona="中年厨师，只了解厨房相关的事",
        knowledge=["c_known"],  # does NOT know c_unknown
        speech_style="default",
    )
    clues_by_id = {"c_known": known_clue, "c_unknown": unknown_clue}
    agent = NPCAgent(npc, clues_by_id)

    # Known clue MUST be in prompt
    assert "厨房刀具" in agent._system_prompt
    # Unknown clue must NOT be in prompt
    assert "保险柜" not in agent._system_prompt
    assert "遗嘱修改" not in agent._system_prompt
