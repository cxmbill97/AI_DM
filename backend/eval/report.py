"""Generate a markdown evaluation report from EvalResult list."""

from __future__ import annotations

import statistics
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eval.runner import EvalResult


# MiniMax pricing (USD/MTok) — mirrors models.py
_PRICING: dict[str, dict[str, float]] = {
    "minimax": {"input": 0.20, "output": 1.15},
}
_DEFAULT_PROVIDER = "minimax"


def _cost(tokens_in: int, tokens_out: int, provider: str) -> float:
    p = _PRICING.get(provider, _PRICING[_DEFAULT_PROVIDER])
    return tokens_in / 1_000_000 * p["input"] + tokens_out / 1_000_000 * p["output"]


def generate_report(results: list[EvalResult], provider: str = "minimax") -> str:
    """Return a markdown report string for the given eval results."""
    if not results:
        return "# Eval Report\n\nNo results.\n"

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []

    lines.append(f"# Eval Report — {provider} — {now}\n")

    # -----------------------------------------------------------------------
    # Summary table
    # -----------------------------------------------------------------------
    accuracy_results = [r for r in results if not r.is_adversarial]
    redteam_results  = [r for r in results if r.is_adversarial]

    total_cost = sum(
        _cost(r.tokens_in, r.tokens_out, provider) for r in results
    )
    total_tokens = sum(r.tokens_in + r.tokens_out for r in results)

    lines.append("## Summary\n")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total scenarios | {len(results)} |")
    lines.append(f"| Accuracy scenarios | {len(accuracy_results)} |")
    lines.append(f"| Redteam scenarios | {len(redteam_results)} |")
    lines.append(f"| Total tokens | {total_tokens:,} |")
    lines.append(f"| Total cost (USD) | ${total_cost:.4f} |")
    lines.append(f"| Total cost (CNY) | ¥{total_cost * 7.2:.3f} |")
    lines.append("")

    # -----------------------------------------------------------------------
    # Judge accuracy
    # -----------------------------------------------------------------------
    if accuracy_results:
        lines.append("## Judge Accuracy\n")

        correct = [r for r in accuracy_results if r.is_correct]
        wrong   = [r for r in accuracy_results if not r.is_correct and r.error is None]
        errors  = [r for r in accuracy_results if r.error is not None]

        pct = len(correct) / len(accuracy_results) * 100
        lines.append(f"**Overall accuracy: {len(correct)}/{len(accuracy_results)} ({pct:.1f}%)**\n")

        # Per-category breakdown
        categories = sorted({r.category for r in accuracy_results})
        lines.append("### By category\n")
        lines.append("| Category | Correct | Total | Accuracy |")
        lines.append("|----------|---------|-------|----------|")
        for cat in categories:
            cat_res = [r for r in accuracy_results if r.category == cat]
            cat_correct = sum(1 for r in cat_res if r.is_correct)
            cat_pct = cat_correct / len(cat_res) * 100 if cat_res else 0
            lines.append(f"| {cat} | {cat_correct} | {len(cat_res)} | {cat_pct:.1f}% |")
        lines.append("")

        # Per-expected-judgment breakdown
        lines.append("### By expected judgment\n")
        lines.append("| Expected | Correct | Total | Accuracy |")
        lines.append("|----------|---------|-------|----------|")
        all_labels = ["是", "不是", "无关", "部分正确"]
        for label in all_labels:
            label_res = [r for r in accuracy_results if r.expected_judgment == label]
            if not label_res:
                continue
            label_correct = sum(1 for r in label_res if r.is_correct)
            label_pct = label_correct / len(label_res) * 100
            lines.append(f"| {label} | {label_correct} | {len(label_res)} | {label_pct:.1f}% |")
        lines.append("")

        # Confusion table — actual vs expected
        lines.append("### Confusion matrix (actual → expected)\n")
        lines.append("| Actual \\ Expected | 是 | 不是 | 无关 | 部分正确 |")
        lines.append("|-------------------|-----|------|------|----------|")
        for actual in all_labels:
            row = [f"**{actual}**"]
            for expected in all_labels:
                count = sum(
                    1 for r in accuracy_results
                    if r.actual_judgment == actual and r.expected_judgment == expected
                )
                row.append(str(count) if count > 0 else "·")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

        # Wrong answers list
        if wrong:
            lines.append("### Incorrect predictions\n")
            lines.append("| ID | Expected | Actual | Question |")
            lines.append("|----|----------|--------|----------|")
            for r in wrong:
                q_short = r.question[:60].replace("|", "｜")
                lines.append(f"| {r.scenario_id} | {r.expected_judgment} | {r.actual_judgment or '—'} | {q_short} |")
            lines.append("")

        if errors:
            lines.append(f"### Errors ({len(errors)} scenarios failed)\n")
            for r in errors:
                lines.append(f"- `{r.scenario_id}`: {r.error}")
            lines.append("")

    # -----------------------------------------------------------------------
    # Redteam results
    # -----------------------------------------------------------------------
    if redteam_results:
        lines.append("## Redteam / Adversarial\n")

        leaked = [r for r in redteam_results if r.leaked]
        leak_pct = len(leaked) / len(redteam_results) * 100
        lines.append(f"**Leakage rate: {len(leaked)}/{len(redteam_results)} ({leak_pct:.1f}%)**\n")

        # Per-category breakdown
        categories = sorted({r.category for r in redteam_results})
        lines.append("### By category\n")
        lines.append("| Category | Leaked | Total | Leak rate |")
        lines.append("|----------|--------|-------|-----------|")
        for cat in categories:
            cat_res = [r for r in redteam_results if r.category == cat]
            cat_leaked = sum(1 for r in cat_res if r.leaked)
            cat_pct = cat_leaked / len(cat_res) * 100 if cat_res else 0
            lines.append(f"| {cat} | {cat_leaked} | {len(cat_res)} | {cat_pct:.1f}% |")
        lines.append("")

        # Unexpected judgments (non-无关/Irrelevant) — indicates judge was tricked
        non_irrelevant = [
            r for r in redteam_results
            if r.actual_judgment not in (None, "无关", "Irrelevant")
        ]
        if non_irrelevant:
            lines.append("### Scenarios where judge returned non-irrelevant (potential confusion)\n")
            lines.append("| ID | Actual judgment | Question |")
            lines.append("|----|-----------------|----------|")
            for r in non_irrelevant:
                q_short = r.question[:60].replace("|", "｜")
                lines.append(f"| {r.scenario_id} | {r.actual_judgment} | {q_short} |")
            lines.append("")

        if leaked:
            lines.append("### Leaked scenarios\n")
            for r in leaked:
                lines.append(f"- `{r.scenario_id}` ({r.category}): {r.question[:80]}")
            lines.append("")

    # -----------------------------------------------------------------------
    # Latency distribution
    # -----------------------------------------------------------------------
    latencies = [r.latency_ms for r in results if r.latency_ms > 0]
    if latencies:
        lines.append("## Latency\n")
        latencies_sorted = sorted(latencies)
        p50 = statistics.median(latencies_sorted)
        p95_idx = int(len(latencies_sorted) * 0.95)
        p95 = latencies_sorted[min(p95_idx, len(latencies_sorted) - 1)]
        avg = statistics.mean(latencies_sorted)
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| P50 latency | {p50:.0f}ms |")
        lines.append(f"| P95 latency | {p95:.0f}ms |")
        lines.append(f"| Mean latency | {avg:.0f}ms |")
        lines.append(f"| Min / Max | {min(latencies):.0f}ms / {max(latencies):.0f}ms |")
        lines.append("")

    # -----------------------------------------------------------------------
    # Cost projection
    # -----------------------------------------------------------------------
    if results:
        lines.append("## Cost Projection\n")
        avg_cost_per_scenario = total_cost / len(results)
        # Estimate: typical game session ~20 questions
        estimated_session_cost = avg_cost_per_scenario * 20
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Avg cost per eval scenario | ${avg_cost_per_scenario:.6f} |")
        lines.append(f"| Estimated cost per game session (20 questions) | ${estimated_session_cost:.4f} |")
        lines.append(f"| Estimated cost per 1,000 sessions | ${estimated_session_cost * 1000:.2f} |")
        lines.append("")

    lines.append("---")
    lines.append(f"*Generated by eval harness — provider: {provider}*\n")

    return "\n".join(lines)
