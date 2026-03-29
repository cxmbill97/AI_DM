"""Pytest configuration, fixtures, and shared helpers."""

from __future__ import annotations

import json
from typing import Any

import pytest

import app.llm as llm_module
from app.models import GameSession, Puzzle
from app.puzzle_loader import load_puzzle


# ---------------------------------------------------------------------------
# --slow flag: gates real-LLM integration tests
# ---------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--slow",
        action="store_true",
        default=False,
        help="Run slow integration tests that call the real MiniMax API.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip @pytest.mark.slow tests unless --slow is passed."""
    if config.getoption("--slow"):
        return
    skip = pytest.mark.skip(reason="Pass --slow to run real-LLM integration tests")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)


# ---------------------------------------------------------------------------
# Puzzle fixture — loaded from disk (also exercises puzzle_loader)
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_puzzle() -> Puzzle:
    """Classic turtle soup puzzle, loaded from data/puzzles/classic_turtle_soup.json."""
    return load_puzzle("classic_turtle_soup")


# ---------------------------------------------------------------------------
# MockLLM — controllable fake for app.llm.chat
# ---------------------------------------------------------------------------


class MockLLM:
    """Async callable that stands in for app.llm.chat in unit tests.

    Usage in tests::

        mock_llm.set_response({"judgment": "是", "response": "对", ...})
        result = await dm_turn(session, "some question")
        assert mock_llm.call_count == 1
        assert "汤底" in mock_llm.last_system_prompt
    """

    _DEFAULT: dict[str, Any] = {
        "judgment": "无关",
        "response": "这与谜题无关，请换个角度提问。",
        "truth_progress": 0.0,
        "should_hint": False,
    }

    def __init__(self) -> None:
        self._json: str = json.dumps(self._DEFAULT)
        self._calls: list[tuple[str, list[dict]]] = []

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def set_response(self, data: dict[str, Any] | str) -> None:
        """Override the JSON the mock returns for every subsequent call."""
        self._json = json.dumps(data) if isinstance(data, dict) else data

    def reset(self) -> None:
        """Restore defaults and clear call log."""
        self._json = json.dumps(self._DEFAULT)
        self._calls.clear()

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------

    @property
    def call_count(self) -> int:
        return len(self._calls)

    @property
    def last_system_prompt(self) -> str:
        assert self._calls, "MockLLM: no calls recorded yet"
        return self._calls[-1][0]

    @property
    def last_messages(self) -> list[dict]:
        assert self._calls, "MockLLM: no calls recorded yet"
        return self._calls[-1][1]

    # ------------------------------------------------------------------
    # The actual mock callable (signature must match app.llm.chat)
    # ------------------------------------------------------------------

    async def __call__(self, system_prompt: str, messages: list[dict]) -> str:
        self._calls.append((system_prompt, messages))
        return self._json


@pytest.fixture
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> MockLLM:
    """Patch app.llm.chat with a MockLLM instance and return it.

    Tests that only need a safe default response can use::

        @pytest.mark.usefixtures("mock_llm")

    Tests that need specific responses should receive the fixture::

        async def test_foo(mock_llm, sample_puzzle):
            mock_llm.set_response({...})
    """
    mock = MockLLM()
    # Patch in app.dm (where it is imported and called), not in app.llm.
    # `from app.llm import chat` creates a local binding in app.dm; patching
    # app.llm.chat would have no effect on that already-bound name.
    monkeypatch.setattr("app.dm.chat", mock)
    return mock


# ---------------------------------------------------------------------------
# Real-LLM guard fixture — skip unless MINIMAX_API_KEY is present
# ---------------------------------------------------------------------------


@pytest.fixture
def real_llm() -> None:
    """Guard for integration tests: skip if MINIMAX_API_KEY is not set.

    Also resets the LLM client singleton so it picks up the env key
    freshly (important if mock_llm patched it in a previous test).
    """
    import os
    from pathlib import Path
    from dotenv import load_dotenv

    # Load .env so the key is available even when not exported to the shell
    load_dotenv(Path(__file__).parent.parent / ".env")

    key = os.getenv("MINIMAX_API_KEY", "")
    if not key:
        pytest.skip("MINIMAX_API_KEY not set — skipping real-LLM test")

    # Force the client to be recreated with the real key
    llm_module._client = None


# ---------------------------------------------------------------------------
# Convenience factory — creates a fresh GameSession for sample_puzzle
# ---------------------------------------------------------------------------


@pytest.fixture
def make_session(sample_puzzle: Puzzle):
    """Factory fixture: returns a callable that builds a fresh GameSession.

    Example::

        session = make_session()
        session = make_session(consecutive_misses=4)
    """

    def _factory(**kwargs: Any) -> GameSession:
        return GameSession(
            session_id="test-session",
            puzzle=sample_puzzle,
            history=[],
            **kwargs,
        )

    return _factory
