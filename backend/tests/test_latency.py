"""Real-LLM latency benchmarks for the AI DM pipeline.

These tests make actual API calls to MiniMax and measure where time is spent.
They are marked ``slow`` and are excluded from normal CI runs.

Run manually:
    cd backend && uv run pytest tests/test_latency.py -v -s --timeout=120

Results are printed as a table at the end of the run.
"""

from __future__ import annotations

import statistics
import time
from typing import Any

import pytest

from app.agents.judge import JudgeAgent
from app.agents.narrator import NarratorAgent
from app.agents.orchestrator import AgentOrchestrator
from app.llm import chat, chat_stream
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
from app.visibility import VisibleContext

pytestmark = pytest.mark.slow

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_KEY_FACTS = [
    "死者威士忌杯中含有安眠药成分",
    "死者系被人在昏迷状态下推倒撞上壁炉石台致死",
    "22:13走廊监控记录到浅色衣物人影朝书房方向行走",
    "沈清当晚在22:00至22:30期间行踪不明",
    "威士忌杯上仅发现沈清的指纹",
]

_QUESTIONS = [
    "威士忌杯里有问题吗",
    "死者是被毒死的吗",
    "22点之后走廊有人经过吗",
]


# ---------------------------------------------------------------------------
# Helper: measure a single LLM chat() call
# ---------------------------------------------------------------------------

async def _time_chat(system: str, user: str) -> dict[str, Any]:
    """Return {latency_ms, tokens_in_est, response_len}."""
    messages = [{"role": "user", "content": user}]
    t0 = time.perf_counter()
    raw = await chat(system, messages)
    elapsed = (time.perf_counter() - t0) * 1000
    return {
        "latency_ms": elapsed,
        "response_len": len(raw),
    }


# ---------------------------------------------------------------------------
# Helper: measure TTFT + total for chat_stream()
# ---------------------------------------------------------------------------

async def _time_stream(system: str, user: str) -> dict[str, Any]:
    """Return {ttft_ms, total_ms, chunks, total_chars}."""
    messages = [{"role": "user", "content": user}]
    t0 = time.perf_counter()
    ttft_ms: float | None = None
    chunks = 0
    total_chars = 0

    gen = chat_stream(system, messages)
    async for chunk in gen:
        if ttft_ms is None:
            ttft_ms = (time.perf_counter() - t0) * 1000
        chunks += 1
        total_chars += len(chunk)

    total_ms = (time.perf_counter() - t0) * 1000
    return {
        "ttft_ms": ttft_ms or total_ms,
        "total_ms": total_ms,
        "chunks": chunks,
        "total_chars": total_chars,
    }


# ---------------------------------------------------------------------------
# Test 1: Raw LLM latency (chat blocking)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_raw_chat_latency() -> None:
    """Measure baseline blocking chat() latency with a short prompt."""
    system = "你是一个助手，用一句话简短回答。"
    user = "1加1等于几？"

    results = []
    for _ in range(3):
        r = await _time_chat(system, user)
        results.append(r["latency_ms"])

    p50 = statistics.median(results)
    _print_section("Raw chat() latency (3 calls)", [
        ("P50 ms", f"{p50:.0f}"),
        ("Min ms", f"{min(results):.0f}"),
        ("Max ms", f"{max(results):.0f}"),
    ])
    # Sanity: at least got a response
    assert p50 > 0


# ---------------------------------------------------------------------------
# Test 2: Streaming TTFT vs total
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_ttft() -> None:
    """Measure time-to-first-token vs total time for chat_stream()."""
    system = "你是一个语言生动的叙述者，回复不超过80字。"
    user = "描述一个神秘的雨夜场景。"

    ttfts = []
    totals = []
    for _ in range(3):
        r = await _time_stream(system, user)
        ttfts.append(r["ttft_ms"])
        totals.append(r["total_ms"])

    _print_section("chat_stream() latency (3 calls)", [
        ("TTFT P50 ms",  f"{statistics.median(ttfts):.0f}"),
        ("TTFT min ms",  f"{min(ttfts):.0f}"),
        ("Total P50 ms", f"{statistics.median(totals):.0f}"),
        ("Total min ms", f"{min(totals):.0f}"),
    ])
    assert statistics.median(ttfts) > 0
    assert statistics.median(totals) >= statistics.median(ttfts)


# ---------------------------------------------------------------------------
# Test 3: Judge latency (real API)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_judge_latency() -> None:
    """Measure JudgeAgent.judge() latency across multiple questions."""
    judge = JudgeAgent(key_facts=_KEY_FACTS)

    latencies = []
    for q in _QUESTIONS:
        t0 = time.perf_counter()
        judgment = await judge.judge(q)
        elapsed = (time.perf_counter() - t0) * 1000
        latencies.append(elapsed)
        assert judgment["result"] in ("是", "不是", "无关", "部分正确")

    _print_section(f"JudgeAgent latency ({len(_QUESTIONS)} questions)", [
        ("P50 ms", f"{statistics.median(latencies):.0f}"),
        ("Min ms", f"{min(latencies):.0f}"),
        ("Max ms", f"{max(latencies):.0f}"),
        ("Avg ms", f"{statistics.mean(latencies):.0f}"),
    ])


# ---------------------------------------------------------------------------
# Test 4: Narrator streaming TTFT (real API)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_narrator_stream_ttft() -> None:
    """Measure NarratorAgent.narrate_stream() TTFT (what the player sees first)."""
    from app.agents.judge import Judgment

    narrator = NarratorAgent()
    visible = VisibleContext(player_id="p1", player_slot="player_1", surface="雨夜别墅命案", public_clues=[], private_clues=[])

    judgment: Judgment = {"result": "是", "confidence": 0.9, "relevant_fact_ids": ["fact_0"]}

    ttfts = []
    totals = []
    for q in _QUESTIONS:
        t0 = time.perf_counter()
        gen = await narrator.narrate_stream(
            judgment=judgment,
            player_message=q,
            visible_context=visible,
            phase="investigation_1",
        )
        ttft_ms = None
        total_chars = 0
        async for chunk in gen:
            if ttft_ms is None:
                ttft_ms = (time.perf_counter() - t0) * 1000
            total_chars += len(chunk)
        total_ms = (time.perf_counter() - t0) * 1000
        ttfts.append(ttft_ms or total_ms)
        totals.append(total_ms)

    _print_section(f"NarratorAgent stream TTFT ({len(_QUESTIONS)} messages)", [
        ("TTFT P50 ms",  f"{statistics.median(ttfts):.0f}"),
        ("TTFT min ms",  f"{min(ttfts):.0f}"),
        ("Total P50 ms", f"{statistics.median(totals):.0f}"),
        ("Total min ms", f"{min(totals):.0f}"),
    ])


# ---------------------------------------------------------------------------
# Test 5: Full orchestrator pipeline — end-to-end latency breakdown
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
                  secret_bio="与死者有秘密关系", is_culprit=False),
        Character(id="char_shen", name="沈清", public_bio="管理人",
                  secret_bio="是死者私生女，投下安眠药", is_culprit=True),
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
        timeline="22:00投药，22:20推倒", key_facts=_KEY_FACTS,
    )
    return Script(
        id="test_latency", title="延迟测试剧本",
        metadata=ScriptMetadata(player_count=2, duration_minutes=20, difficulty="beginner"),
        characters=characters, phases=phases, clues=clues, npcs=npcs, truth=truth,
    )


@pytest.mark.asyncio
async def test_orchestrator_streaming_latency() -> None:
    """Measure end-to-end player-visible latency using handle_message_stream().

    Records:
    - Time to dm_stream_start (= Judge latency — when player sees judgment badge)
    - Time to first dm_stream_chunk (= TTFT — when player sees first word)
    - Time to dm_stream_end (= total latency)
    """
    script = _make_script()
    sm = GameStateMachine(script.phases)
    sm.advance()  # opening → investigation_1

    orch = AgentOrchestrator(
        script=script,
        state_machine=sm,
        player_char_map={"p1": "char_su"},
    )

    questions = ["威士忌杯里有问题吗", "死者是被毒死的吗"]
    rows = []

    for q in questions:
        t0 = time.perf_counter()
        t_start: float | None = None
        t_first_chunk: float | None = None
        t_end: float | None = None

        stream_gen = await orch.handle_message_stream("p1", q)
        async for event in stream_gen:
            now = time.perf_counter()
            etype = event.get("type")
            if etype == "dm_stream_start" and t_start is None:
                t_start = (now - t0) * 1000
            elif etype == "dm_stream_chunk" and t_first_chunk is None:
                t_first_chunk = (now - t0) * 1000
            elif etype == "dm_stream_end":
                t_end = (now - t0) * 1000

        rows.append({
            "question": q[:12],
            "judge_ms": f"{t_start:.0f}" if t_start else "n/a",
            "ttft_ms":  f"{t_first_chunk:.0f}" if t_first_chunk else "n/a",
            "total_ms": f"{t_end:.0f}" if t_end else "n/a",
        })

    print("\n")
    print("=" * 65)
    print("  ORCHESTRATOR STREAMING LATENCY BREAKDOWN")
    print("=" * 65)
    print(f"  {'Question':<14}  {'Judge→badge':>12}  {'TTFT':>8}  {'Total':>8}")
    print("-" * 65)
    for r in rows:
        print(f"  {r['question']:<14}  {r['judge_ms']:>12}ms  {r['ttft_ms']:>7}ms  {r['total_ms']:>7}ms")
    print("=" * 65)
    print("  Judge→badge = when judgment badge appears (Judge LLM done)")
    print("  TTFT        = when first word streams to player")
    print("  Total       = dm_stream_end (narrator fully streamed)")
    print("=" * 65)

    assert len(rows) == len(questions)


# ---------------------------------------------------------------------------
# Test 6: Judge system prompt size analysis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_judge_prompt_size() -> None:
    """Inspect Judge system prompt size and estimate token overhead."""
    judge = JudgeAgent(key_facts=_KEY_FACTS)
    prompt = judge._system_prompt

    # Rough token estimate: 1 token ≈ 2.5 CJK chars or 4 Latin chars
    cjk_chars = sum(1 for c in prompt if '\u4e00' <= c <= '\u9fff')
    latin_chars = len(prompt) - cjk_chars
    estimated_tokens = cjk_chars // 2 + latin_chars // 4

    _print_section("Judge system prompt analysis", [
        ("Total chars",       str(len(prompt))),
        ("CJK chars",         str(cjk_chars)),
        ("Estimated tokens",  str(estimated_tokens)),
        ("Key facts count",   str(len(_KEY_FACTS))),
        ("Chars per fact",    f"{cjk_chars / max(len(_KEY_FACTS), 1):.0f} avg"),
    ])

    # The prompt should be reasonable — flag if surprisingly large
    assert len(prompt) < 3000, (
        f"Judge system prompt is {len(prompt)} chars — consider trimming"
    )


# ---------------------------------------------------------------------------
# Utility: pretty-print a section table
# ---------------------------------------------------------------------------

def _print_section(title: str, rows: list[tuple[str, str]]) -> None:
    width = 55
    print("\n")
    print("=" * width)
    print(f"  {title}")
    print("-" * width)
    for label, value in rows:
        print(f"  {label:<28} {value:>20}")
    print("=" * width)
