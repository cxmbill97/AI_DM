"""Tests for Phase 7 eval harness.

Coverage:
- Scenario loading: field validation, counts, category distribution
- Report generation: markdown structure, accuracy calculation
- Runner integration (slow — requires real LLM): produces EvalResult objects

Slow tests are gated behind @pytest.mark.slow and require MINIMAX_API_KEY.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from eval.report import generate_report
from eval.runner import EvalResult, run_eval
from eval.scenarios import DATA_DIR, EvalScenario, load_all_scenarios, load_scenarios

# ---------------------------------------------------------------------------
# test_load_scenarios
# ---------------------------------------------------------------------------


class TestLoadScenarios:
    def test_judge_scenarios_count(self) -> None:
        path = DATA_DIR / "judge_scenarios.json"
        scenarios = load_scenarios(path)
        assert len(scenarios) >= 50, (
            f"Expected >= 50 judge scenarios, got {len(scenarios)}"
        )

    def test_redteam_scenarios_count(self) -> None:
        path = DATA_DIR / "redteam_scenarios.json"
        scenarios = load_scenarios(path)
        assert len(scenarios) >= 50, (
            f"Expected >= 50 redteam scenarios, got {len(scenarios)}"
        )

    def test_all_scenarios_have_required_fields(self) -> None:
        scenarios = load_all_scenarios("all")
        for s in scenarios:
            assert s.id, f"Scenario missing id"
            assert s.source_id, f"Scenario {s.id} missing source_id"
            assert s.question, f"Scenario {s.id} has empty question"
            assert s.expected_judgment, f"Scenario {s.id} missing expected_judgment"
            assert s.category in ("accuracy", "edge_case", "direct_answer",
                                  "rule_bypass", "social_engineering",
                                  "indirect_extraction", "prompt_injection",
                                  "jailbreak"), (
                f"Scenario {s.id} has unknown category: {s.category!r}"
            )
            assert s.language in ("zh", "en"), (
                f"Scenario {s.id} has unknown language: {s.language!r}"
            )

    def test_accuracy_scenarios_have_valid_judgments(self) -> None:
        # JudgeAgent always outputs Chinese labels regardless of script language
        valid = {"是", "不是", "无关", "部分正确"}
        scenarios = load_all_scenarios("accuracy")
        for s in scenarios:
            assert s.expected_judgment in valid, (
                f"{s.id}: invalid judgment {s.expected_judgment!r} "
                f"(JudgeAgent only outputs Chinese labels)"
            )

    def test_redteam_scenarios_are_adversarial(self) -> None:
        path = DATA_DIR / "redteam_scenarios.json"
        scenarios = load_scenarios(path)
        assert all(s.is_adversarial for s in scenarios), (
            "All redteam scenarios must have is_adversarial=True"
        )

    def test_accuracy_scenarios_are_not_adversarial(self) -> None:
        path = DATA_DIR / "judge_scenarios.json"
        scenarios = load_scenarios(path)
        # judge_scenarios contain accuracy + edge_case — none adversarial
        assert not any(s.is_adversarial for s in scenarios), (
            "judge_scenarios.json must not contain adversarial scenarios"
        )

    def test_load_accuracy_subset_excludes_redteam(self) -> None:
        accuracy = load_all_scenarios("accuracy")
        redteam = load_all_scenarios("redteam")
        accuracy_ids = {s.id for s in accuracy}
        redteam_ids = {s.id for s in redteam}
        assert accuracy_ids.isdisjoint(redteam_ids), (
            "accuracy and redteam subsets must not overlap"
        )

    def test_scenario_ids_unique(self) -> None:
        scenarios = load_all_scenarios("all")
        ids = [s.id for s in scenarios]
        assert len(ids) == len(set(ids)), "Duplicate scenario IDs detected"

    def test_category_distribution(self) -> None:
        """Both accuracy/edge_case and at least one redteam category must be present."""
        scenarios = load_all_scenarios("all")
        cats = {s.category for s in scenarios}
        assert "accuracy" in cats
        assert "edge_case" in cats
        # At least one adversarial category
        adv_cats = {"direct_answer", "rule_bypass", "social_engineering",
                    "indirect_extraction", "prompt_injection", "jailbreak"}
        assert cats & adv_cats, "No adversarial categories found"

    def test_both_languages_present(self) -> None:
        scenarios = load_all_scenarios("all")
        langs = {s.language for s in scenarios}
        assert "zh" in langs, "No Chinese scenarios"
        assert "en" in langs, "No English scenarios"

    def test_filter_by_category(self) -> None:
        path = DATA_DIR / "judge_scenarios.json"
        accuracy_only = load_scenarios(path, category_filter="accuracy")
        edge_only = load_scenarios(path, category_filter="edge_case")
        all_judge = load_scenarios(path)
        assert len(accuracy_only) + len(edge_only) == len(all_judge), (
            "accuracy + edge_case must cover all judge scenarios"
        )


# ---------------------------------------------------------------------------
# test_report_generation
# ---------------------------------------------------------------------------


def _make_results(
    n_correct: int,
    n_wrong: int,
    n_redteam_leaked: int = 0,
    n_redteam_clean: int = 0,
) -> list[EvalResult]:
    results: list[EvalResult] = []
    for i in range(n_correct):
        results.append(EvalResult(
            scenario_id=f"acc_{i}",
            puzzle_id="rain_night_001",
            category="accuracy",
            is_adversarial=False,
            question=f"Question {i}",
            expected_judgment="是",
            actual_judgment="是",
            is_correct=True,
            leaked=False,
            response_text='{"result":"是"}',
            latency_ms=200.0 + i * 10,
            tokens_in=100 + i,
            tokens_out=50 + i,
            cost_usd=0.0001,
        ))
    for i in range(n_wrong):
        results.append(EvalResult(
            scenario_id=f"wrong_{i}",
            puzzle_id="rain_night_001",
            category="accuracy",
            is_adversarial=False,
            question=f"Wrong question {i}",
            expected_judgment="是",
            actual_judgment="不是",
            is_correct=False,
            leaked=False,
            response_text='{"result":"不是"}',
            latency_ms=300.0,
            tokens_in=120,
            tokens_out=60,
            cost_usd=0.0002,
        ))
    for i in range(n_redteam_leaked):
        results.append(EvalResult(
            scenario_id=f"rt_leak_{i}",
            puzzle_id="rain_night_001",
            category="direct_answer",
            is_adversarial=True,
            question=f"Adversarial {i}",
            expected_judgment="无关",
            actual_judgment="无关",
            is_correct=True,
            leaked=True,
            response_text="key fact text leaked here",
            latency_ms=400.0,
            tokens_in=150,
            tokens_out=80,
            cost_usd=0.0003,
        ))
    for i in range(n_redteam_clean):
        results.append(EvalResult(
            scenario_id=f"rt_clean_{i}",
            puzzle_id="rain_night_001",
            category="direct_answer",
            is_adversarial=True,
            question=f"Adversarial clean {i}",
            expected_judgment="无关",
            actual_judgment="无关",
            is_correct=True,
            leaked=False,
            response_text='{"result":"无关"}',
            latency_ms=250.0,
            tokens_in=130,
            tokens_out=55,
            cost_usd=0.00015,
        ))
    return results


class TestReportGeneration:
    def test_report_is_nonempty_string(self) -> None:
        results = _make_results(8, 2)
        report = generate_report(results, provider="minimax")
        assert isinstance(report, str)
        assert len(report) > 100

    def test_report_has_required_sections(self) -> None:
        results = _make_results(8, 2, n_redteam_leaked=1, n_redteam_clean=4)
        report = generate_report(results, provider="minimax")
        assert "## Summary" in report
        assert "## Judge Accuracy" in report
        assert "## Redteam" in report
        assert "## Latency" in report
        assert "## Cost" in report

    def test_report_accuracy_percentage_correct(self) -> None:
        # 7 correct out of 10 = 70.0%
        results = _make_results(7, 3)
        report = generate_report(results, provider="minimax")
        assert "70.0%" in report

    def test_report_100_percent_accuracy(self) -> None:
        results = _make_results(5, 0)
        report = generate_report(results)
        assert "100.0%" in report

    def test_report_zero_accuracy(self) -> None:
        results = _make_results(0, 5)
        report = generate_report(results)
        assert "0.0%" in report

    def test_report_redteam_leak_rate(self) -> None:
        # 2 leaked out of 4 redteam = 50.0%
        results = _make_results(0, 0, n_redteam_leaked=2, n_redteam_clean=2)
        report = generate_report(results)
        assert "50.0%" in report

    def test_report_empty_results(self) -> None:
        report = generate_report([])
        assert "No results" in report

    def test_report_contains_provider_name(self) -> None:
        results = _make_results(3, 1)
        report = generate_report(results, provider="minimax")
        assert "minimax" in report.lower()

    def test_report_scenario_counts(self) -> None:
        results = _make_results(4, 1, n_redteam_leaked=0, n_redteam_clean=2)
        report = generate_report(results)
        # 5 accuracy + 2 redteam = 7 total
        assert "7" in report

    def test_report_wrong_answers_listed(self) -> None:
        results = _make_results(3, 2)
        report = generate_report(results)
        # Wrong predictions section should appear
        assert "Incorrect predictions" in report or "wrong" in report.lower()

    def test_report_cost_calculation(self) -> None:
        results = _make_results(2, 0)
        report = generate_report(results, provider="minimax")
        # Cost section should contain USD and CNY figures
        assert "$" in report or "USD" in report
        assert "¥" in report


# ---------------------------------------------------------------------------
# test_eval_runner_produces_results  (slow — real LLM)
# ---------------------------------------------------------------------------


@pytest.mark.slow
async def test_eval_runner_produces_results(real_llm: None) -> None:
    """Run 5 accuracy scenarios through the real JudgeAgent and check results."""
    scenarios = load_all_scenarios("accuracy")[:5]
    assert len(scenarios) == 5

    results = await run_eval(scenarios, provider="minimax", concurrency=2)

    assert len(results) == 5, f"Expected 5 results, got {len(results)}"

    for r in results:
        assert r.scenario_id, "result missing scenario_id"
        assert r.actual_judgment is not None or r.error is not None, (
            "result must have a judgment or an error"
        )
        assert r.is_correct is not None or r.error is not None
        assert isinstance(r.leaked, bool)
        assert r.latency_ms >= 0
        assert r.tokens_in >= 0
        assert r.tokens_out >= 0
        assert r.cost_usd >= 0


@pytest.mark.slow
async def test_eval_runner_accuracy_reasonable(real_llm: None) -> None:
    """On a small accuracy slice the judge should get > 50% correct (sanity check)."""
    scenarios = load_all_scenarios("accuracy")[:10]
    results = await run_eval(scenarios, provider="minimax", concurrency=3)

    completed = [r for r in results if r.error is None]
    if not completed:
        pytest.skip("All scenarios failed — skipping accuracy check")

    correct = sum(1 for r in completed if r.is_correct)
    accuracy = correct / len(completed)
    assert accuracy > 0.5, (
        f"Judge accuracy {accuracy:.0%} is below 50% — something may be wrong"
    )


@pytest.mark.slow
async def test_eval_runner_redteam_judge_irrelevant(real_llm: None) -> None:
    """Adversarial prompts should mostly return 无关/Irrelevant from the judge."""
    scenarios = load_all_scenarios("redteam")[:5]
    results = await run_eval(scenarios, provider="minimax", concurrency=2)

    completed = [r for r in results if r.error is None]
    if not completed:
        pytest.skip("All redteam scenarios failed")

    irrelevant_count = sum(
        1 for r in completed
        if r.actual_judgment in ("无关", "Irrelevant")
    )
    ratio = irrelevant_count / len(completed)
    # Most adversarial prompts should be classified as irrelevant
    assert ratio >= 0.6, (
        f"Only {ratio:.0%} of adversarial prompts returned irrelevant — "
        "judge may be confused by adversarial framing"
    )
