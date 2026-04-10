"""Phase 2: AI-assisted answer evaluator with rule-based fallback."""
from __future__ import annotations

VERDICT = str  # "irrelevant" | "relevant" | "close" | "correct"


def _rule_based(puzzle_solution: str, key_facts: list[str], answer: str) -> VERDICT:
    ans = answer.lower()
    sol = puzzle_solution.lower()
    if any(kf.lower() in ans for kf in key_facts if kf):
        return "correct"
    if any(word in ans for word in sol.split() if len(word) > 3):
        return "close"
    if len(ans.split()) >= 3:
        return "relevant"
    return "irrelevant"


async def evaluate_answer(
    puzzle_solution: str,
    key_facts: list[str],
    player_answer: str,
    llm_client=None,
) -> VERDICT:
    if llm_client is not None:
        try:
            resp = await llm_client.evaluate(puzzle_solution, key_facts, player_answer)
            if resp in ("irrelevant", "relevant", "close", "correct"):
                return resp
        except Exception:
            pass
    return _rule_based(puzzle_solution, key_facts, player_answer)
