import asyncio, pytest
from unittest.mock import AsyncMock
from app.evaluator import evaluate_answer, _rule_based

def test_correct(): assert _rule_based("cap died", ["cap died"], "the cap died") == "correct"
def test_close(): assert _rule_based("cap died", [], "cap was there") == "close"
def test_relevant(): assert _rule_based("mystery", [], "something happened here today") == "relevant"
def test_irrelevant(): assert _rule_based("mystery", [], "yes") == "irrelevant"
def test_llm():
    m = AsyncMock(); m.evaluate = AsyncMock(return_value="close")
    assert asyncio.run(evaluate_answer("s", ["f"], "a", m)) == "close"
def test_fallback():
    m = AsyncMock(); m.evaluate = AsyncMock(side_effect=Exception())
    assert asyncio.run(evaluate_answer("mystery", [], "something happened here today", m)) == "relevant"
