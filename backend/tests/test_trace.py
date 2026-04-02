"""Tests for Phase 7 agent trace collection.

Coverage:
- Trace steps produced for every pipeline agent (router, judge, narrator, safety)
- total_latency_ms matches sum of step latencies
- Token counts populated for LLM agents, zero for rules-based router
- input_summary sanitisation: no raw key_facts or truth text
- Cost calculation from token counts
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.agents.orchestrator import AgentOrchestrator
from app.agents.trace import PRICING_USD_PER_MTOK, AgentTrace
from app.llm import Usage, _usage_accumulator
from app.models import (
    NPC,
    Character,
    Phase,
    Script,
    ScriptClue,
    ScriptMetadata,
    ScriptTruth,
)
from app.state_machine import GameStateMachine

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

KEY_FACTS = [
    "死者威士忌杯中含有安眠药成分",
    "死者系被人在昏迷状态下推倒撞上壁炉石台致死",
    "22:13走廊监控记录到浅色衣物人影朝书房方向行走",
]

TRUTH_TEXT = "凶手是沈清，动机是私生女身份，手法是投药后推倒"

CHARACTER_SECRETS = {
    "char_su":   "与死者有秘密子女关系",
    "char_shen": "是死者私生女，在威士忌中投入安眠药",
}

# Simulate realistic token counts for each fake LLM call
_FAKE_TOKENS_IN = 150
_FAKE_TOKENS_OUT = 60


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_script() -> Script:
    phases = [
        Phase(id="opening", type="narration", next="investigation_1",
              duration_seconds=120, allowed_actions={"listen"},
              dm_script="欢迎来到雨夜迷踪"),
        Phase(id="investigation_1", type="investigation", next="discussion",
              duration_seconds=600, allowed_actions={"ask_dm", "search", "private_chat"},
              available_clues=["clue_001"]),
    ]
    characters = [
        Character(id="char_su", name="苏雅", public_bio="演员",
                  secret_bio=CHARACTER_SECRETS["char_su"], is_culprit=False),
        Character(id="char_shen", name="沈清", public_bio="管理人",
                  secret_bio=CHARACTER_SECRETS["char_shen"], is_culprit=True),
    ]
    clues = [
        ScriptClue(id="clue_001", title="毒理报告", content="威士忌含安眠药",
                   phase_available="investigation_1", visibility="public",
                   unlock_keywords=["毒", "药", "威士忌"]),
    ]
    npcs = [
        NPC(id="npc_butler", name="管家老周", persona="沉稳老管家",
            knowledge=["clue_001"], speech_style="formal_elderly"),
    ]
    truth = ScriptTruth(
        culprit="char_shen", motive="私生女动机", method="投药后推倒",
        timeline="22:00投药，22:20推倒", key_facts=KEY_FACTS,
    )
    return Script(
        id="test_001", title="测试剧本",
        metadata=ScriptMetadata(player_count=2, duration_minutes=20, difficulty="beginner"),
        characters=characters, phases=phases, clues=clues, npcs=npcs, truth=truth,
    )


@pytest.fixture()
def orchestrator_with_trace(monkeypatch: pytest.MonkeyPatch):
    """Orchestrator with a fake LLM that populates the usage accumulator."""
    script = _make_script()
    sm = GameStateMachine(script.phases)
    sm.advance()  # opening → investigation_1

    orch = AgentOrchestrator(
        script=script,
        state_machine=sm,
        player_char_map={"p1": "char_su"},
    )

    _judge_resp = json.dumps({"result": "是", "confidence": 0.85,
                               "relevant_fact_ids": ["fact_0"]})
    _narrator_resp = "这是一个很有意思的线索。"
    _safety_resp = json.dumps({"safe": True, "leaked_content": None})

    async def fake_chat(system: str, messages: list[dict]) -> str:
        # Populate the usage accumulator exactly as the real chat() does
        acc = _usage_accumulator.get(None)
        if acc is not None:
            acc.append(Usage(
                prompt_tokens=_FAKE_TOKENS_IN,
                completion_tokens=_FAKE_TOKENS_OUT,
            ))
        if "判断引擎" in system or "truth judgment" in system.lower():
            return _judge_resp
        if "安全" in system or "safe" in system.lower():
            return _safety_resp
        return _narrator_resp

    monkeypatch.setattr("app.agents.judge.chat", fake_chat)
    monkeypatch.setattr("app.agents.narrator.chat", fake_chat)

    return orch


# ---------------------------------------------------------------------------
# Test: all expected steps present
# ---------------------------------------------------------------------------


async def test_trace_has_all_steps(orchestrator_with_trace: AgentOrchestrator) -> None:
    """A 'question' intent must produce router → judge → narrator → safety steps."""
    _, trace = await orchestrator_with_trace.handle_message("p1", "威士忌杯里有问题吗")

    agent_names = [s.agent for s in trace.steps]
    assert "router" in agent_names, "router step missing"
    assert "judge" in agent_names, "judge step missing"
    assert "narrator" in agent_names, "narrator step missing"
    assert "safety" in agent_names, "safety step missing"


async def test_trace_step_order(orchestrator_with_trace: AgentOrchestrator) -> None:
    """Router must be the first step; judge, narrator, safety follow in order."""
    _, trace = await orchestrator_with_trace.handle_message("p1", "死者是被毒死的吗")

    assert trace.steps[0].agent == "router", "First step must be router"

    agent_order = [s.agent for s in trace.steps]
    judge_idx = agent_order.index("judge")
    narrator_idx = agent_order.index("narrator")
    safety_idx = agent_order.index("safety")
    assert judge_idx < narrator_idx < safety_idx, (
        "Pipeline order violated: expected judge < narrator < safety"
    )


async def test_trace_meta_only_router(orchestrator_with_trace: AgentOrchestrator) -> None:
    """Meta intent short-circuits after router — no LLM steps."""
    _, trace = await orchestrator_with_trace.handle_message("p1", "规则")
    agent_names = [s.agent for s in trace.steps]
    assert "router" in agent_names
    assert "judge" not in agent_names
    assert "narrator" not in agent_names


# ---------------------------------------------------------------------------
# Test: latency accounting
# ---------------------------------------------------------------------------


async def test_trace_latency_sum(orchestrator_with_trace: AgentOrchestrator) -> None:
    """total_latency_ms must equal the sum of individual step latencies."""
    _, trace = await orchestrator_with_trace.handle_message("p1", "监控拍到什么了")

    step_total = sum(s.latency_ms for s in trace.steps)
    # total_latency_ms is a computed property — should always match exactly
    assert trace.total_latency_ms == pytest.approx(step_total, abs=1e-6)


async def test_trace_step_latencies_positive(orchestrator_with_trace: AgentOrchestrator) -> None:
    """Every step should record a positive latency (even very fast ones)."""
    _, trace = await orchestrator_with_trace.handle_message("p1", "书房有拖拽痕迹吗")
    for step in trace.steps:
        assert step.latency_ms >= 0, f"Step {step.agent} has negative latency"


# ---------------------------------------------------------------------------
# Test: token counts
# ---------------------------------------------------------------------------


async def test_trace_tokens_counted(orchestrator_with_trace: AgentOrchestrator) -> None:
    """LLM agents must have token counts > 0; the rules-based router must have 0."""
    _, trace = await orchestrator_with_trace.handle_message("p1", "威士忌杯有毒吗")

    router_step = next(s for s in trace.steps if s.agent == "router")
    assert router_step.tokens_in == 0, "Router makes no LLM call — tokens_in must be 0"
    assert router_step.tokens_out == 0, "Router makes no LLM call — tokens_out must be 0"

    judge_step = next(s for s in trace.steps if s.agent == "judge")
    assert judge_step.tokens_in > 0, "Judge must record input tokens"
    assert judge_step.tokens_out > 0, "Judge must record output tokens"

    narrator_step = next(s for s in trace.steps if s.agent == "narrator")
    assert narrator_step.tokens_in > 0, "Narrator must record input tokens"
    assert narrator_step.tokens_out > 0, "Narrator must record output tokens"


async def test_trace_total_tokens_sum(orchestrator_with_trace: AgentOrchestrator) -> None:
    """total_tokens must equal the sum of all step (tokens_in + tokens_out)."""
    _, trace = await orchestrator_with_trace.handle_message("p1", "死者是男性吗")

    expected = sum(s.tokens_in + s.tokens_out for s in trace.steps)
    assert trace.total_tokens == expected


# ---------------------------------------------------------------------------
# Test: input_summary sanitisation (no secrets)
# ---------------------------------------------------------------------------


async def test_trace_input_sanitized_judge(orchestrator_with_trace: AgentOrchestrator) -> None:
    """Judge input_summary must NOT contain raw key_fact text.

    Allowed: counts like "key_facts: 3 items"
    Forbidden: any of the actual KEY_FACTS strings
    """
    _, trace = await orchestrator_with_trace.handle_message("p1", "威士忌杯里有什么")

    judge_step = next(s for s in trace.steps if s.agent == "judge")
    for fact in KEY_FACTS:
        # We check for the first 10 chars of each fact — a shorter substring
        # catches partial leaks too
        assert fact[:10] not in judge_step.input_summary, (
            f"Judge input_summary leaked key_fact: {fact[:20]!r}"
        )


async def test_trace_input_sanitized_narrator(orchestrator_with_trace: AgentOrchestrator) -> None:
    """Narrator input_summary must show only judgment value and counts — no truth text."""
    _, trace = await orchestrator_with_trace.handle_message("p1", "凶手和别墅有关吗")

    narrator_step = next(s for s in trace.steps if s.agent == "narrator")
    # Truth text must not appear
    assert TRUTH_TEXT not in narrator_step.input_summary

    # Should contain the judgment value
    assert "judgment=" in narrator_step.input_summary


async def test_trace_input_sanitized_safety(orchestrator_with_trace: AgentOrchestrator) -> None:
    """Safety input_summary must show only char counts — no key_fact text."""
    _, trace = await orchestrator_with_trace.handle_message("p1", "死者的饮品被动了手脚吗")

    safety_step = next(s for s in trace.steps if s.agent == "safety")
    for fact in KEY_FACTS:
        assert fact[:10] not in safety_step.input_summary, (
            f"Safety input_summary leaked key_fact fragment: {fact[:20]!r}"
        )
    # Should describe the text in terms of length / counts
    assert "text_len" in safety_step.input_summary or "key_facts" in safety_step.input_summary


# ---------------------------------------------------------------------------
# Test: cost calculation
# ---------------------------------------------------------------------------


async def test_trace_cost_calculated(orchestrator_with_trace: AgentOrchestrator) -> None:
    """total_cost_usd must be > 0 and match the per-token pricing formula."""
    _, trace = await orchestrator_with_trace.handle_message("p1", "书房地毯有问题吗")

    assert trace.total_cost_usd > 0, "total_cost_usd should be positive when tokens are consumed"

    tokens_in = sum(s.tokens_in for s in trace.steps)
    tokens_out = sum(s.tokens_out for s in trace.steps)
    expected_usd = (
        tokens_in * PRICING_USD_PER_MTOK["input"]
        + tokens_out * PRICING_USD_PER_MTOK["output"]
    ) / 1_000_000
    assert trace.total_cost_usd == pytest.approx(expected_usd, rel=1e-6)


async def test_trace_cost_zero_when_no_tokens() -> None:
    """A trace with no LLM calls (only router) should have zero cost."""
    from app.agents.trace import new_trace, TraceStep

    trace = new_trace("p1", "rules")
    trace.steps.append(TraceStep(
        agent="router",
        input_summary="message='rules', phase=opening",
        output_summary="intent=meta",
        latency_ms=0.5,
        tokens_in=0,
        tokens_out=0,
    ))
    assert trace.total_cost_usd == 0.0


# ---------------------------------------------------------------------------
# Test: to_dict serialisation
# ---------------------------------------------------------------------------


async def test_trace_to_dict_structure(orchestrator_with_trace: AgentOrchestrator) -> None:
    """to_dict() must produce a JSON-serialisable dict with expected top-level keys."""
    import json as json_mod

    _, trace = await orchestrator_with_trace.handle_message("p1", "威士忌杯含有药物成分吗")
    d = trace.to_dict()

    # Must be serialisable
    json_str = json_mod.dumps(d)
    assert len(json_str) > 0

    # Required top-level keys
    for key in ("message_id", "player_id", "player_message", "timestamp",
                "total_latency_ms", "total_tokens", "total_cost_usd", "steps"):
        assert key in d, f"Missing key in trace dict: {key!r}"

    # Steps must be a list of dicts with required fields
    assert isinstance(d["steps"], list)
    assert len(d["steps"]) > 0
    for step in d["steps"]:
        for field in ("agent", "input_summary", "output_summary",
                      "latency_ms", "tokens_in", "tokens_out"):
            assert field in step, f"Missing step field: {field!r}"
