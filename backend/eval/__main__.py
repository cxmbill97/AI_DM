"""CLI entry point for the eval harness.

Usage:
    python -m eval [options]

Options:
    --provider    LLM provider name (default: minimax)
    --scenarios   Which scenarios to run: all | accuracy | redteam  (default: all)
    --concurrency Max parallel judge calls (default: 5)
    --output      Output path for the markdown report (optional; auto-generated if omitted)
    --dry-run     Print scenario count and exit without calling the LLM
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the backend/ directory is on sys.path when invoked as a script
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from eval.report import generate_report  # noqa: E402
from eval.runner import run_eval  # noqa: E402
from eval.scenarios import load_all_scenarios  # noqa: E402

REPORTS_DIR = Path(__file__).parent / "reports"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m eval.run",
        description="AI-DM eval harness — batch judge accuracy + redteam evaluation",
    )
    p.add_argument(
        "--provider",
        default="minimax",
        help="LLM provider name (for cost calculation). Default: minimax",
    )
    p.add_argument(
        "--scenarios",
        choices=["all", "accuracy", "redteam"],
        default="all",
        help="Which scenario set to run. Default: all",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Max concurrent judge calls. Default: 5",
    )
    p.add_argument(
        "--output",
        default=None,
        help="Output path for the markdown report. Auto-generated if omitted.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print scenario count and first 5 scenario IDs, then exit.",
    )
    return p


async def _main(args: argparse.Namespace) -> int:
    scenarios = load_all_scenarios(subset=args.scenarios)

    if not scenarios:
        print("No scenarios found. Check eval/data/ directory.", file=sys.stderr)
        return 1

    print(f"Loaded {len(scenarios)} scenarios (subset={args.scenarios})")

    if args.dry_run:
        for s in scenarios[:5]:
            print(f"  [{s.category}] {s.id}: {s.question[:60]!r}")
        if len(scenarios) > 5:
            print(f"  ... and {len(scenarios) - 5} more")
        return 0

    print(f"Running eval with provider={args.provider}, concurrency={args.concurrency} ...")
    results = await run_eval(
        scenarios,
        provider=args.provider,
        concurrency=args.concurrency,
    )

    # Summarise to stdout
    accuracy_results = [r for r in results if not r.is_adversarial and r.error is None]
    redteam_results = [r for r in results if r.is_adversarial and r.error is None]
    errors = [r for r in results if r.error is not None]

    if accuracy_results:
        correct = sum(1 for r in accuracy_results if r.is_correct)
        pct = correct / len(accuracy_results) * 100
        print(f"Judge accuracy : {correct}/{len(accuracy_results)} ({pct:.1f}%)")

    if redteam_results:
        leaked = sum(1 for r in redteam_results if r.leaked)
        leak_pct = leaked / len(redteam_results) * 100
        print(f"Redteam leakage: {leaked}/{len(redteam_results)} ({leak_pct:.1f}%)")

    if errors:
        print(f"Errors         : {len(errors)} scenarios failed")

    total_cost = sum(r.cost_usd for r in results)
    print(f"Total cost     : ${total_cost:.4f} (¥{total_cost * 7.2:.3f})")

    # Generate markdown report
    report_md = generate_report(results, provider=args.provider)

    if args.output:
        out_path = Path(args.output)
    else:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.utcnow().strftime("%Y%m%d_%H%M")
        out_path = REPORTS_DIR / f"{args.provider}_{date_str}.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_md, encoding="utf-8")
    print(f"Report written : {out_path}")

    return 0


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
