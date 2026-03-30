"""Tests for clue unlock logic: passive (hint-based) and active (keyword match)."""

from __future__ import annotations

import pytest

from app.dm import check_clue_unlock_active, check_clue_unlock_passive
from app.models import GameSession, Puzzle
from app.puzzle_loader import load_all_puzzles, load_puzzle


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def soup_puzzle() -> Puzzle:
    """classic_turtle_soup has 3 clues with known keywords."""
    return load_puzzle("classic_turtle_soup")


def _session(puzzle: Puzzle, **kwargs) -> GameSession:
    return GameSession(session_id="test", puzzle=puzzle, history=[], **kwargs)


# ---------------------------------------------------------------------------
# Passive clue delivery  (hint → pseudo-clue card)
# ---------------------------------------------------------------------------


class TestPassiveClueDelivery:

    def test_delivers_first_hint_as_clue_card(self, soup_puzzle: Puzzle) -> None:
        session = _session(soup_puzzle)
        clue = check_clue_unlock_passive(session)
        assert clue is not None
        assert clue.id == "hint_0"
        assert clue.title == "DM 提示"
        assert clue.content == soup_puzzle.hints[0]

    def test_hint_index_increments_on_each_call(self, soup_puzzle: Puzzle) -> None:
        session = _session(soup_puzzle)
        for i in range(len(soup_puzzle.hints)):
            clue = check_clue_unlock_passive(session)
            assert clue is not None
            assert clue.id == f"hint_{i}"
            assert clue.content == soup_puzzle.hints[i]
            assert session.hint_index == i + 1

    def test_all_hints_delivered_in_order(self, soup_puzzle: Puzzle) -> None:
        session = _session(soup_puzzle)
        delivered = []
        while True:
            clue = check_clue_unlock_passive(session)
            if clue is None:
                break
            delivered.append(clue.content)
        assert delivered == soup_puzzle.hints

    def test_returns_none_when_hints_exhausted(self, soup_puzzle: Puzzle) -> None:
        total = len(soup_puzzle.hints)
        session = _session(soup_puzzle, hint_index=total)
        assert check_clue_unlock_passive(session) is None

    def test_hint_index_unchanged_when_exhausted(self, soup_puzzle: Puzzle) -> None:
        total = len(soup_puzzle.hints)
        session = _session(soup_puzzle, hint_index=total)
        check_clue_unlock_passive(session)
        assert session.hint_index == total

    def test_pseudo_clue_id_added_to_unlocked_set(self, soup_puzzle: Puzzle) -> None:
        session = _session(soup_puzzle)
        clue = check_clue_unlock_passive(session)
        assert clue is not None
        assert clue.id in session.unlocked_clue_ids

    def test_unlock_keywords_empty_on_pseudo_clue(self, soup_puzzle: Puzzle) -> None:
        """Pseudo-clue cards have no unlock_keywords (they are hint-triggered)."""
        session = _session(soup_puzzle)
        clue = check_clue_unlock_passive(session)
        assert clue is not None
        assert clue.unlock_keywords == []


# ---------------------------------------------------------------------------
# Active clue unlock  (keyword match against player message)
# ---------------------------------------------------------------------------


class TestActiveClueUnlock:

    def test_keyword_match_returns_correct_clue(self, soup_puzzle: Puzzle) -> None:
        # clue_shipwreck has keywords ["海难", "船", "遇难", "大海", "漂流"]
        unlocked: set[str] = set()
        clue = check_clue_unlock_active("这艘船是怎么沉的", soup_puzzle, unlocked)
        assert clue is not None
        assert clue.id == "clue_shipwreck"

    def test_keyword_match_adds_clue_to_unlocked_set(self, soup_puzzle: Puzzle) -> None:
        unlocked: set[str] = set()
        check_clue_unlock_active("这艘船是怎么沉的", soup_puzzle, unlocked)
        assert "clue_shipwreck" in unlocked

    def test_no_match_returns_none(self, soup_puzzle: Puzzle) -> None:
        unlocked: set[str] = set()
        clue = check_clue_unlock_active("今天天气怎么样", soup_puzzle, unlocked)
        assert clue is None

    def test_no_match_does_not_modify_unlocked_set(self, soup_puzzle: Puzzle) -> None:
        unlocked: set[str] = set()
        check_clue_unlock_active("今天天气怎么样", soup_puzzle, unlocked)
        assert len(unlocked) == 0

    def test_idempotency_same_clue_not_returned_twice(self, soup_puzzle: Puzzle) -> None:
        """Once a clue is in unlocked_ids, asking the same keyword returns None."""
        unlocked: set[str] = set()
        first = check_clue_unlock_active("这艘船是怎么沉的", soup_puzzle, unlocked)
        assert first is not None
        assert first.id == "clue_shipwreck"

        second = check_clue_unlock_active("这艘船是怎么沉的", soup_puzzle, unlocked)
        # clue_shipwreck already unlocked; no other clue has "船"
        assert second is None or second.id != "clue_shipwreck"

    def test_idempotency_pre_populated_unlocked_set(self, soup_puzzle: Puzzle) -> None:
        """If caller pre-populates unlocked_ids, that clue is skipped."""
        unlocked = {"clue_shipwreck"}
        clue = check_clue_unlock_active("船", soup_puzzle, unlocked)
        # clue_shipwreck already unlocked; should not be returned
        assert clue is None or clue.id != "clue_shipwreck"

    def test_fuzzy_substring_match(self, soup_puzzle: Puzzle) -> None:
        """Keyword match is substring-based — keyword embedded in a sentence still works."""
        unlocked: set[str] = set()
        # "妻子" is in clue_wife's unlock_keywords
        clue = check_clue_unlock_active("那个男人的妻子后来怎样了", soup_puzzle, unlocked)
        assert clue is not None
        assert clue.id == "clue_wife"

    def test_second_keyword_also_matches(self, soup_puzzle: Puzzle) -> None:
        """Any keyword in the list can trigger the unlock — not just the first one."""
        unlocked: set[str] = set()
        # "漂流" is the 5th keyword for clue_shipwreck
        clue = check_clue_unlock_active("他们在海上漂流了多久", soup_puzzle, unlocked)
        assert clue is not None
        assert clue.id == "clue_shipwreck"

    def test_all_clues_unlockable(self, soup_puzzle: Puzzle) -> None:
        """Every clue must be reachable by sending its first unlock_keyword as a message."""
        unlocked: set[str] = set()
        for clue in soup_puzzle.clues:
            keyword = clue.unlock_keywords[0]
            result = check_clue_unlock_active(keyword, soup_puzzle, unlocked)
            assert result is not None, (
                f"Clue {clue.id!r} is unreachable — "
                f"keyword {keyword!r} returned None (unlocked so far: {unlocked})"
            )
            assert clue.id in unlocked, (
                f"Clue {clue.id!r} not added to unlocked set after keyword match"
            )

    def test_all_clues_unlockable_across_all_puzzles(self) -> None:
        """Every clue in every puzzle must be reachable via at least one of its keywords."""
        for puzzle in load_all_puzzles():
            unlocked: set[str] = set()
            for clue in puzzle.clues:
                keyword = clue.unlock_keywords[0]
                result = check_clue_unlock_active(keyword, puzzle, unlocked)
                assert result is not None, (
                    f"Puzzle {puzzle.id!r}: clue {clue.id!r} unreachable "
                    f"via keyword {keyword!r}"
                )
                assert clue.id in unlocked


# ---------------------------------------------------------------------------
# Clue content safety  (unit-level — no LLM required)
# ---------------------------------------------------------------------------


class TestClueContentSafety:

    def test_clue_content_not_in_system_prompt_before_unlock(
        self, soup_puzzle: Puzzle
    ) -> None:
        """Locked clue content must never appear in the assembled system prompt."""
        from app.dm import assemble_prompt

        # No clues unlocked yet
        prompt = assemble_prompt(soup_puzzle, unlocked_clue_ids=set())
        for clue in soup_puzzle.clues:
            assert clue.content not in prompt, (
                f"Locked clue {clue.id!r} content leaked into system prompt!\n"
                f"Content: {clue.content!r}"
            )

    def test_unlocked_clue_content_appears_in_system_prompt(
        self, soup_puzzle: Puzzle
    ) -> None:
        """After a clue is unlocked it should be visible in the assembled prompt
        so the DM can reference it."""
        from app.dm import assemble_prompt

        first_clue = soup_puzzle.clues[0]
        prompt = assemble_prompt(
            soup_puzzle, unlocked_clue_ids={first_clue.id}
        )
        assert first_clue.content in prompt, (
            f"Unlocked clue {first_clue.id!r} content missing from system prompt"
        )

    def test_other_clues_still_locked_after_partial_unlock(
        self, soup_puzzle: Puzzle
    ) -> None:
        """Unlocking one clue must not expose other clues' content in the prompt."""
        from app.dm import assemble_prompt

        first_clue = soup_puzzle.clues[0]
        prompt = assemble_prompt(
            soup_puzzle, unlocked_clue_ids={first_clue.id}
        )
        for clue in soup_puzzle.clues[1:]:
            assert clue.content not in prompt, (
                f"Still-locked clue {clue.id!r} content appeared after partial unlock"
            )
