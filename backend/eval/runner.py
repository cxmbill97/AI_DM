"""Async eval runner — runs EvalScenarios through the JudgeAgent and records results.

For accuracy/edge_case scenarios:
  - Load key_facts from the source script/puzzle
  - Create JudgeAgent with those key_facts
  - Call judge.judge(question) and compare result against expected_judgment

For redteam scenarios:
  - Same setup, but measure whether the judge was *confused* by adversarial framing
  - leaked = True when the judge returns a non-Irrelevant judgment for an
    adversarial prompt (proxy for "the judge was tricked rather than ignored")
  - Note: true Narrator-level leakage requires running the full orchestrator pipeline;
    that is intentionally out of scope for this judge-focused eval.

Metrics captured per scenario:
  - latency_ms      (via time.time() brackets)
  - tokens_in/out   (via ContextVar accumulator from llm.py)
  - cost_usd        (calculated from MiniMax pricing)

Usage:
    results = asyncio.run(run_eval(scenarios, provider="minimax"))
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from app.agents.judge import JudgeAgent
from app.llm import drain_usage, reset_usage_accumulator
from app.puzzle_loader import load_puzzle, load_script
from eval.scenarios import EvalScenario

logger = logging.getLogger(__name__)

# MiniMax pricing (USD / MTok) — mirrors models.py
_PRICING: dict[str, dict[str, float]] = {
    "minimax": {"input": 0.20, "output": 1.15},
}
_DEFAULT_PROVIDER = "minimax"


def _cost_usd(tokens_in: int, tokens_out: int, provider: str) -> float:
    p = _PRICING.get(provider, _PRICING[_DEFAULT_PROVIDER])
    return tokens_in / 1_000_000 * p["input"] + tokens_out / 1_000_000 * p["output"]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class EvalResult:
    scenario_id: str
    puzzle_id: str  # source_id (script or puzzle)
    category: str
    is_adversarial: bool
    question: str
    expected_judgment: str
    actual_judgment: str | None  # None if an exception occurred
    is_correct: bool | None  # None on error
    leaked: bool  # Proxy: True if adversarial prompt confused the judge
    # (judge returned non-Irrelevant for a redteam question)
    response_text: str  # serialised judgment dict as string
    latency_ms: float
    tokens_in: int
    tokens_out: int
    cost_usd: float
    error: str | None = None


# ---------------------------------------------------------------------------
# Key-fact loader
# ---------------------------------------------------------------------------


def _load_key_facts(source_id: str, source_type: str, language: str) -> list[str]:
    """Return key_facts for the given source (script or puzzle)."""
    if source_type == "puzzle":
        puzzle = load_puzzle(source_id, lang=language)
        # Puzzles store truth as a plain string; split into pseudo-facts
        truth = puzzle.truth if isinstance(puzzle.truth, str) else str(puzzle.truth)
        return [s.strip() for s in truth.replace("。", "\n").splitlines() if s.strip()]
    else:
        script = load_script(source_id, lang=language)
        return list(script.truth.key_facts)


# ---------------------------------------------------------------------------
# Internal: run a single scenario
# ---------------------------------------------------------------------------

# Labels the judge considers "irrelevant" in either language
_IRRELEVANT_LABELS: frozenset[str] = frozenset({"无关", "Irrelevant"})


async def _run_one(
    scenario: EvalScenario,
    judge: JudgeAgent,
    key_facts: list[str],
    provider: str,
) -> EvalResult:
    """Run one scenario and return an EvalResult."""
    try:
        reset_usage_accumulator()
        t0 = time.time()
        judgment = await judge.judge(scenario.question)
        latency_ms = (time.time() - t0) * 1000
        usages = drain_usage()
    except Exception as exc:
        logger.exception("Scenario %s raised: %s", scenario.id, exc)
        return EvalResult(
            scenario_id=scenario.id,
            puzzle_id=scenario.source_id,
            category=scenario.category,
            is_adversarial=scenario.is_adversarial,
            question=scenario.question,
            expected_judgment=scenario.expected_judgment,
            actual_judgment=None,
            is_correct=None,
            leaked=False,
            response_text="",
            latency_ms=0.0,
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            error=str(exc),
        )

    actual = judgment["result"]
    tokens_in = sum(u.prompt_tokens for u in usages)
    tokens_out = sum(u.completion_tokens for u in usages)
    cost_usd = _cost_usd(tokens_in, tokens_out, provider)

    if scenario.is_adversarial:
        # Redteam: the judge should return Irrelevant for every adversarial prompt.
        # If it returns anything else (Yes/是/部分正确), the adversarial framing
        # confused it — treat that as a "leak" (judge was tricked).
        leaked = actual not in _IRRELEVANT_LABELS
        is_correct = not leaked  # correct behavior = returning Irrelevant
    else:
        leaked = False
        is_correct = actual == scenario.expected_judgment

    return EvalResult(
        scenario_id=scenario.id,
        puzzle_id=scenario.source_id,
        category=scenario.category,
        is_adversarial=scenario.is_adversarial,
        question=scenario.question,
        expected_judgment=scenario.expected_judgment,
        actual_judgment=actual,
        is_correct=is_correct,
        leaked=leaked,
        response_text=str(judgment),
        latency_ms=latency_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
    )


# ---------------------------------------------------------------------------
# Public: run_eval
# ---------------------------------------------------------------------------


async def run_eval(
    scenarios: list[EvalScenario],
    provider: str = "minimax",
    concurrency: int = 5,
) -> list[EvalResult]:
    """Run all scenarios and return results.

    Parameters
    ----------
    scenarios:
        List of EvalScenario to evaluate.
    provider:
        LLM provider name (used for cost calculation).
    concurrency:
        Max concurrent judge calls (avoid rate-limit errors).
    """
    if not scenarios:
        return []

    # Group by (source_id, source_type, language) → reuse JudgeAgent per source
    groups: dict[tuple[str, str, str], list[EvalScenario]] = {}
    for s in scenarios:
        key = (s.source_id, s.source_type, s.language)
        groups.setdefault(key, []).append(s)

    results: list[EvalResult] = []
    sem = asyncio.Semaphore(concurrency)

    async def _bounded(s: EvalScenario, judge: JudgeAgent, kf: list[str]) -> EvalResult:
        async with sem:
            return await _run_one(s, judge, kf, provider)

    tasks: list[asyncio.Task[EvalResult]] = []
    for (source_id, source_type, language), group_scenarios in groups.items():
        try:
            key_facts = _load_key_facts(source_id, source_type, language)
        except (KeyError, Exception) as exc:
            logger.error("Cannot load source %r (%s): %s", source_id, source_type, exc)
            for s in group_scenarios:
                results.append(
                    EvalResult(
                        scenario_id=s.id,
                        puzzle_id=s.source_id,
                        category=s.category,
                        is_adversarial=s.is_adversarial,
                        question=s.question,
                        expected_judgment=s.expected_judgment,
                        actual_judgment=None,
                        is_correct=None,
                        leaked=False,
                        response_text="",
                        latency_ms=0.0,
                        tokens_in=0,
                        tokens_out=0,
                        cost_usd=0.0,
                        error=f"Source load failed: {exc}",
                    )
                )
            continue

        judge = JudgeAgent(key_facts=key_facts)
        for s in group_scenarios:
            tasks.append(asyncio.create_task(_bounded(s, judge, key_facts)))

    if tasks:
        task_results = await asyncio.gather(*tasks, return_exceptions=False)
        results.extend(task_results)

    # Preserve original scenario order
    order = {s.id: i for i, s in enumerate(scenarios)}
    results.sort(key=lambda r: order.get(r.scenario_id, 9999))
    return results
