"""Answer evaluator with rule-based fallback and optional LLM path."""

from __future__ import annotations


async def evaluate_answer(
    puzzle_solution: str,
    key_facts: list[str],
    player_answer: str,
    llm_client=None,
) -> str:
    """Return 'correct' | 'close' | 'relevant' | 'irrelevant'.

    Rule-based fallback used when llm_client is None or on LLM exception.
    """
    if llm_client is not None:
        try:
            return await llm_client.evaluate(puzzle_solution, key_facts, player_answer)
        except Exception:
            pass  # fall through to rule-based

    return _rule_based(puzzle_solution, key_facts, player_answer)


def _rule_based(solution: str, key_facts: list[str], answer: str) -> str:
    lower = answer.lower()
    solution_lower = solution.lower()

    # Any key fact phrase appears verbatim → correct
    for fact in key_facts:
        if fact.lower() in lower:
            return "correct"

    # Core solution word(s) appear → close
    for word in solution_lower.split():
        if len(word) >= 3 and word in lower:
            return "close"

    # Long answer with some content → probably relevant
    if len(answer.strip()) >= 20:
        return "relevant"

    return "irrelevant"
