"""EvalScenario dataclass and JSON loader.

Each scenario targets the JudgeAgent and has a ground-truth expected judgment.
Adversarial (redteam) scenarios expect the judge to return '无关' / 'Irrelevant'
and are additionally tested for key-fact leakage in the raw output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DATA_DIR = Path(__file__).parent / "data"

JudgmentLabel = Literal["是", "不是", "无关", "部分正确"]
CategoryLabel = Literal["accuracy", "edge_case", "redteam"]


@dataclass(frozen=True)
class EvalScenario:
    id: str
    source_id: str  # script ID (e.g. "rain_night_001") or puzzle ID
    source_type: str  # "script" | "puzzle"
    language: str  # "zh" | "en"
    question: str
    expected_judgment: str  # JudgmentLabel
    category: str  # CategoryLabel
    is_adversarial: bool


def load_scenarios(
    path: Path | str,
    category_filter: str | None = None,
) -> list[EvalScenario]:
    """Load scenarios from a JSON file.

    Parameters
    ----------
    path:
        Absolute or relative path to the scenarios JSON file.
    category_filter:
        If given, only return scenarios where category == category_filter.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    scenarios: list[EvalScenario] = []
    for item in data:
        s = EvalScenario(
            id=item["id"],
            source_id=item["source_id"],
            source_type=item.get("source_type", "script"),
            language=item.get("language", "zh"),
            question=item["question"],
            expected_judgment=item["expected_judgment"],
            category=item["category"],
            is_adversarial=item.get("is_adversarial", False),
        )
        if category_filter is None or s.category == category_filter:
            scenarios.append(s)
    return scenarios


def load_all_scenarios(
    subset: str = "all",
) -> list[EvalScenario]:
    """Load scenarios from the bundled data files.

    Parameters
    ----------
    subset:
        "all"      → accuracy + edge_case + redteam
        "accuracy" → accuracy + edge_case only (no adversarial)
        "redteam"  → redteam only
    """
    scenarios: list[EvalScenario] = []

    judge_path = DATA_DIR / "judge_scenarios.json"
    redteam_path = DATA_DIR / "redteam_scenarios.json"

    if subset in ("all", "accuracy"):
        if judge_path.exists():
            scenarios.extend(load_scenarios(judge_path))

    if subset in ("all", "redteam"):
        if redteam_path.exists():
            scenarios.extend(load_scenarios(redteam_path))

    return scenarios
