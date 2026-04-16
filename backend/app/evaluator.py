"""Phase 2: AI-assisted answer evaluator with rule-based fallback."""
from __future__ import annotations

VERDICT = str  # "irrelevant" | "relevant" | "close" | "correct"


def _rule_based(puzzle_solution: str, key_facts: list[str], answer: str) -> VERDICT:
    # Compare the player's answer against the reference solution text only.
    # Do NOT match against raw key_facts — that would confirm secret fact content
    # to the player (key_facts are internal truth markers, not display text).
    ans = answer.lower()
    sol = puzzle_solution.lower()
    sol_words = [w for w in sol.split() if len(w) > 3]
    if not sol_words:
        return "relevant" if len(ans.split()) >= 2 else "irrelevant"
    match_count = sum(1 for w in sol_words if w in ans)
    ratio = match_count / len(sol_words)
    if ratio >= 0.5:
        return "correct"
    if ratio > 0:
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
