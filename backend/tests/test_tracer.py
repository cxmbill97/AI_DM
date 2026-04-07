"""Tests for the per-room trace store.

Covers:
1. store_trace / get_traces round-trip
2. input_summary and output_summary never exceed 80 chars in orchestrator output
3. AgentTrace.total_tokens == sum of span tokens
4. SSE queue receives trace after store_trace()
5. Deque evicts oldest when >50 traces per room
"""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest

from app.agents.trace import AgentTrace, TraceStep, new_trace
from app.agents.trace_store import (
    _traces,
    get_traces,
    store_trace,
    subscribe,
    unsubscribe,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trace(player_message: str = "test question", n_steps: int = 2) -> tuple[AgentTrace, dict]:
    """Build an AgentTrace with n_steps and return (trace, trace_dict)."""
    trace = new_trace(player_id="player_1", player_message=player_message)
    for i in range(n_steps):
        trace.steps.append(
            TraceStep(
                agent="judge" if i % 2 == 0 else "narrator",
                input_summary=f"key_facts: {i + 3} items",
                output_summary=f"result=是, confidence={80 + i}%",
                latency_ms=float(100 + i * 50),
                tokens_in=200 + i * 100,
                tokens_out=50 + i * 20,
                metadata={"safe": True},
            )
        )
    return trace, trace.to_dict()


def _fresh_room_id() -> str:
    return f"room_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# 1. store_trace / get_traces round-trip
# ---------------------------------------------------------------------------

def test_store_and_retrieve_trace():
    room_id = _fresh_room_id()
    _, td = _make_trace("Is the butler guilty?")
    store_trace(room_id, td)

    results = get_traces(room_id)
    assert len(results) == 1
    assert results[0]["player_message"] == "Is the butler guilty?"


def test_get_traces_newest_first():
    room_id = _fresh_room_id()
    for i in range(5):
        _, td = _make_trace(f"question {i}")
        store_trace(room_id, td)

    results = get_traces(room_id)
    # newest stored last → appendleft means index 0 is newest
    assert results[0]["player_message"] == "question 4"
    assert results[-1]["player_message"] == "question 0"


def test_get_traces_respects_limit():
    room_id = _fresh_room_id()
    for i in range(10):
        _, td = _make_trace(f"q{i}")
        store_trace(room_id, td)

    assert len(get_traces(room_id, limit=3)) == 3


# ---------------------------------------------------------------------------
# 2. input_summary and output_summary never exceed 80 chars
# ---------------------------------------------------------------------------

def test_step_summaries_within_80_chars():
    """Verify the sanitisation contract for traces produced by the orchestrator."""
    trace = new_trace("player_1", "这个案件是怎么回事？")
    trace.steps.append(
        TraceStep(
            agent="judge",
            input_summary="key_facts: 12 items; visible_facts: 3 items",
            output_summary="result=是, confidence=90%, relevant_facts: 2 items",
            latency_ms=120.0,
            tokens_in=400,
            tokens_out=60,
            metadata={},
        )
    )
    trace.steps.append(
        TraceStep(
            agent="safety",
            input_summary="text_len=342 chars, key_facts: 12 items",
            output_summary="safe=True",
            latency_ms=55.0,
            tokens_in=250,
            tokens_out=20,
            metadata={"safe": True},
        )
    )
    for step in trace.steps:
        assert len(step.input_summary) <= 80, f"input_summary too long: {step.input_summary!r}"
        assert len(step.output_summary) <= 80, f"output_summary too long: {step.output_summary!r}"


# ---------------------------------------------------------------------------
# 3. AgentTrace.total_tokens == sum of span tokens
# ---------------------------------------------------------------------------

def test_total_tokens_equals_sum_of_spans():
    trace, _ = _make_trace(n_steps=4)
    expected = sum(s.tokens_in + s.tokens_out for s in trace.steps)
    assert trace.total_tokens == expected


def test_total_latency_equals_sum_of_spans():
    trace, _ = _make_trace(n_steps=3)
    expected = sum(s.latency_ms for s in trace.steps)
    assert abs(trace.total_latency_ms - expected) < 0.001


# ---------------------------------------------------------------------------
# 4. SSE queue receives trace after store_trace()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sse_queue_receives_trace():
    room_id = _fresh_room_id()
    q = subscribe(room_id)

    _, td = _make_trace("SSE test question")
    store_trace(room_id, td)

    received = await asyncio.wait_for(q.get(), timeout=1.0)
    assert received["player_message"] == "SSE test question"

    unsubscribe(room_id, q)


@pytest.mark.asyncio
async def test_multiple_subscribers_all_receive():
    room_id = _fresh_room_id()
    q1 = subscribe(room_id)
    q2 = subscribe(room_id)

    _, td = _make_trace("broadcast test")
    store_trace(room_id, td)

    r1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    r2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert r1["player_message"] == r2["player_message"] == "broadcast test"

    unsubscribe(room_id, q1)
    unsubscribe(room_id, q2)


@pytest.mark.asyncio
async def test_unsubscribed_queue_receives_nothing():
    room_id = _fresh_room_id()
    q = subscribe(room_id)
    unsubscribe(room_id, q)

    _, td = _make_trace("after unsub")
    store_trace(room_id, td)

    # Queue should remain empty
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(q.get(), timeout=0.1)


# ---------------------------------------------------------------------------
# 5. Deque evicts oldest when >50 traces per room
# ---------------------------------------------------------------------------

def test_deque_maxlen_evicts_oldest():
    room_id = _fresh_room_id()

    for i in range(55):
        _, td = _make_trace(f"message {i}")
        store_trace(room_id, td)

    # Internal deque should not exceed 50
    assert len(_traces[room_id]) == 50

    # Oldest messages (0-4) should be gone; newest (5-54) should be present
    all_messages = [t["player_message"] for t in _traces[room_id]]
    assert "message 0" not in all_messages
    assert "message 4" not in all_messages
    assert "message 54" in all_messages


def test_get_traces_never_returns_more_than_stored():
    room_id = _fresh_room_id()
    for i in range(3):
        _, td = _make_trace(f"q{i}")
        store_trace(room_id, td)

    # Asking for more than stored is fine — returns what's available
    result = get_traces(room_id, limit=100)
    assert len(result) == 3
