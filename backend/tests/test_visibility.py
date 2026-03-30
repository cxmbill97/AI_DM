"""Unit tests for Phase 3 VisibilityRegistry — information isolation.

All tests are deterministic (no LLM calls).  They verify:
  - Each player sees only their own private clues, not other players'.
  - DM context contains truth + full key_facts + all-player summary.
  - Leak detection catches verbatim copies but allows paraphrases.
  - Registry handles partial player counts gracefully.
"""

from __future__ import annotations

import pytest

from app.models import GameSession, PrivateClue, Puzzle
from app.puzzle_loader import load_puzzle
from app.visibility import VisibilityRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def collab_puzzle() -> Puzzle:
    """lighthouse_secret has 3 player slots with distinct private clues."""
    return load_puzzle("lighthouse_secret")


@pytest.fixture
def two_player_session(collab_puzzle: Puzzle) -> GameSession:
    """Session with two players assigned to player_1 and player_2."""
    return GameSession(
        session_id="vis-test",
        puzzle=collab_puzzle,
        history=[],
        player_slot_map={"uid-A": "player_1", "uid-B": "player_2"},
    )


@pytest.fixture
def full_session(collab_puzzle: Puzzle) -> GameSession:
    """Session with all three slots filled."""
    return GameSession(
        session_id="vis-full",
        puzzle=collab_puzzle,
        history=[],
        player_slot_map={
            "uid-A": "player_1",
            "uid-B": "player_2",
            "uid-C": "player_3",
        },
    )


# ---------------------------------------------------------------------------
# 1. Players see different clues
# ---------------------------------------------------------------------------


class TestDifferentPlayersSeeTheirOwnClues:
    def test_player_1_has_player_1_clue(self, two_player_session: GameSession) -> None:
        reg = VisibilityRegistry(two_player_session)
        ctx = reg.get_visible_context("uid-A")

        assert ctx.player_slot == "player_1"
        priv_ids = {c["id"] for c in ctx.private_clues}
        assert "priv_bank_record" in priv_ids

    def test_player_2_has_player_2_clue(self, two_player_session: GameSession) -> None:
        reg = VisibilityRegistry(two_player_session)
        ctx = reg.get_visible_context("uid-B")

        assert ctx.player_slot == "player_2"
        priv_ids = {c["id"] for c in ctx.private_clues}
        assert "priv_diary_fragment" in priv_ids

    def test_player_1_does_not_see_player_2_clue(
        self, two_player_session: GameSession
    ) -> None:
        reg = VisibilityRegistry(two_player_session)
        ctx = reg.get_visible_context("uid-A")

        priv_ids = {c["id"] for c in ctx.private_clues}
        assert "priv_diary_fragment" not in priv_ids

    def test_player_2_does_not_see_player_1_clue(
        self, two_player_session: GameSession
    ) -> None:
        reg = VisibilityRegistry(two_player_session)
        ctx = reg.get_visible_context("uid-B")

        priv_ids = {c["id"] for c in ctx.private_clues}
        assert "priv_bank_record" not in priv_ids

    def test_each_player_gets_exactly_one_private_clue(
        self, full_session: GameSession
    ) -> None:
        reg = VisibilityRegistry(full_session)
        for uid in ("uid-A", "uid-B", "uid-C"):
            ctx = reg.get_visible_context(uid)
            assert len(ctx.private_clues) == 1, (
                f"{uid} expected 1 private clue, got {len(ctx.private_clues)}"
            )

    def test_all_three_players_see_different_clue_ids(
        self, full_session: GameSession
    ) -> None:
        reg = VisibilityRegistry(full_session)
        seen = set()
        for uid in ("uid-A", "uid-B", "uid-C"):
            ids = frozenset(c["id"] for c in reg.get_visible_context(uid).private_clues)
            assert ids.isdisjoint(seen), f"Duplicate clue id seen for {uid}"
            seen |= ids


# ---------------------------------------------------------------------------
# 2. Public context contains no other players' private content
# ---------------------------------------------------------------------------


class TestPublicContextHasNoOtherPrivateInfo:
    def test_visible_context_private_clues_are_only_own(
        self, two_player_session: GameSession
    ) -> None:
        """private_clues in VisibleContext must only contain this player's clues."""
        puzzle = two_player_session.puzzle
        reg = VisibilityRegistry(two_player_session)

        # Build a set of all clue ids that do NOT belong to player_1
        player_1_ids = {pc.id for pc in puzzle.private_clues.get("player_1", [])}
        non_player_1_ids = {
            pc.id
            for slot, pcs in puzzle.private_clues.items()
            for pc in pcs
            if slot != "player_1"
        }

        ctx_a = reg.get_visible_context("uid-A")  # player_1
        visible_ids = {c["id"] for c in ctx_a.private_clues}

        # Must not contain any other player's clue id
        assert visible_ids.isdisjoint(non_player_1_ids), (
            f"Other players' clue ids found in player_1 visible context: "
            f"{visible_ids & non_player_1_ids}"
        )

    def test_visible_context_content_does_not_include_other_content(
        self, two_player_session: GameSession
    ) -> None:
        """The actual content text from another player's clue must not appear."""
        puzzle = two_player_session.puzzle
        reg = VisibilityRegistry(two_player_session)

        # Get player_2's clue content
        p2_content = puzzle.private_clues["player_2"][0].content

        ctx_a = reg.get_visible_context("uid-A")  # player_1
        all_visible_text = " ".join(c["content"] for c in ctx_a.private_clues)

        assert p2_content not in all_visible_text

    def test_public_clues_are_empty_before_any_unlock(
        self, two_player_session: GameSession
    ) -> None:
        reg = VisibilityRegistry(two_player_session)
        ctx = reg.get_visible_context("uid-A")
        assert ctx.public_clues == []

    def test_public_clues_appear_after_unlock(
        self, collab_puzzle: Puzzle
    ) -> None:
        # Unlock one of the public clues
        unlocked_id = collab_puzzle.clues[0].id
        session = GameSession(
            session_id="vis-unlock",
            puzzle=collab_puzzle,
            history=[],
            player_slot_map={"uid-A": "player_1"},
            unlocked_clue_ids={unlocked_id},
        )
        reg = VisibilityRegistry(session)
        ctx_a = reg.get_visible_context("uid-A")

        assert len(ctx_a.public_clues) == 1
        assert ctx_a.public_clues[0]["id"] == unlocked_id

        ctx_b_unknown = reg.get_visible_context("uid-unknown")  # no slot
        assert len(ctx_b_unknown.public_clues) == 1  # public clues visible to all


# ---------------------------------------------------------------------------
# 3. DM context has full picture
# ---------------------------------------------------------------------------


class TestDMContextHasFullPicture:
    def test_dm_context_includes_truth(self, two_player_session: GameSession) -> None:
        reg = VisibilityRegistry(two_player_session)
        dm_ctx = reg.get_dm_context()
        assert dm_ctx.truth == two_player_session.puzzle.truth
        assert len(dm_ctx.truth) > 0

    def test_dm_context_includes_key_facts(self, two_player_session: GameSession) -> None:
        reg = VisibilityRegistry(two_player_session)
        dm_ctx = reg.get_dm_context()
        assert dm_ctx.key_facts == two_player_session.puzzle.key_facts
        assert len(dm_ctx.key_facts) > 0

    def test_dm_context_summary_mentions_all_slots(
        self, two_player_session: GameSession
    ) -> None:
        """Summary must reference every slot that has private clues."""
        reg = VisibilityRegistry(two_player_session)
        dm_ctx = reg.get_dm_context()

        # lighthouse_secret has player_1, player_2, player_3 in private_clues dict
        for slot in two_player_session.puzzle.private_clues:
            assert slot in dm_ctx.all_private_summary, (
                f"Slot {slot!r} not mentioned in DM summary"
            )

    def test_dm_context_summary_mentions_clue_titles(
        self, two_player_session: GameSession
    ) -> None:
        """Summary must include the title of each private clue (for DM awareness)."""
        puzzle = two_player_session.puzzle
        reg = VisibilityRegistry(two_player_session)
        dm_ctx = reg.get_dm_context()

        for slot, pcs in puzzle.private_clues.items():
            for pc in pcs:
                assert pc.title in dm_ctx.all_private_summary, (
                    f"Title {pc.title!r} missing from DM summary"
                )

    def test_dm_context_locked_ids_correct_before_any_unlock(
        self, two_player_session: GameSession
    ) -> None:
        reg = VisibilityRegistry(two_player_session)
        dm_ctx = reg.get_dm_context()
        puzzle = two_player_session.puzzle

        expected_locked = {c.id for c in puzzle.clues}
        assert set(dm_ctx.public_clues_locked_ids) == expected_locked
        assert dm_ctx.public_clues_unlocked == []

    def test_dm_context_unlocked_ids_move_to_unlocked_list(
        self, collab_puzzle: Puzzle
    ) -> None:
        clue_id = collab_puzzle.clues[0].id
        session = GameSession(
            session_id="dm-unlock",
            puzzle=collab_puzzle,
            history=[],
            player_slot_map={"uid-A": "player_1"},
            unlocked_clue_ids={clue_id},
        )
        reg = VisibilityRegistry(session)
        dm_ctx = reg.get_dm_context()

        assert any(c["id"] == clue_id for c in dm_ctx.public_clues_unlocked)
        assert clue_id not in dm_ctx.public_clues_locked_ids


# ---------------------------------------------------------------------------
# 4. Leak detection
# ---------------------------------------------------------------------------


class TestLeakDetection:
    def test_verbatim_own_clue_detected_as_verbatim(
        self, two_player_session: GameSession
    ) -> None:
        """is_own_clue_verbatim catches near-exact copy of own private clue content."""
        puzzle = two_player_session.puzzle
        p1_content = puzzle.private_clues["player_1"][0].content
        reg = VisibilityRegistry(two_player_session)

        assert reg.is_own_clue_verbatim(p1_content, "uid-A"), (
            "Own clue verbatim paste should be flagged"
        )

    def test_paraphrase_of_own_clue_not_flagged_as_verbatim(
        self, two_player_session: GameSession
    ) -> None:
        """A short paraphrase of own clue topic is allowed — only raw paste is blocked."""
        reg = VisibilityRegistry(two_player_session)
        # Short, topically-related question — not a verbatim copy
        paraphrase = "我觉得守望者收过钱"
        assert not reg.is_own_clue_verbatim(paraphrase, "uid-A")

    def test_verbatim_other_player_clue_detected_as_leak(
        self, two_player_session: GameSession
    ) -> None:
        """is_private_content_leaked catches near-exact copy of another player's clue."""
        puzzle = two_player_session.puzzle
        p2_content = puzzle.private_clues["player_2"][0].content
        reg = VisibilityRegistry(two_player_session)

        assert reg.is_private_content_leaked(p2_content, "uid-A"), (
            "Verbatim paste of another player's clue must be flagged as a leak"
        )

    def test_paraphrase_of_other_clue_not_blocked(
        self, two_player_session: GameSession
    ) -> None:
        """A natural paraphrase of another player's topic is allowed in public chat."""
        reg = VisibilityRegistry(two_player_session)
        paraphrase = "我觉得那个守望者心里很愧疚"
        assert not reg.is_private_content_leaked(paraphrase, "uid-A")

    def test_own_clue_not_flagged_by_cross_player_check(
        self, two_player_session: GameSession
    ) -> None:
        """is_private_content_leaked must NOT flag a player's own clue content."""
        puzzle = two_player_session.puzzle
        p1_content = puzzle.private_clues["player_1"][0].content
        reg = VisibilityRegistry(two_player_session)

        # uid-A is player_1; p1_content is their own — must not be blocked as "other leak"
        assert not reg.is_private_content_leaked(p1_content, "uid-A")

    def test_short_message_not_leaked(self, two_player_session: GameSession) -> None:
        """Very short messages have insufficient 4-grams to trigger the similarity check."""
        reg = VisibilityRegistry(two_player_session)
        assert not reg.is_private_content_leaked("是", "uid-A")
        assert not reg.is_private_content_leaked("不知道", "uid-A")

    def test_unrelated_message_not_leaked(self, two_player_session: GameSession) -> None:
        """Completely unrelated text does not trigger leak detection."""
        reg = VisibilityRegistry(two_player_session)
        unrelated = "今天天气很好，我们一起去散步吧，路上可以聊聊谜题"
        assert not reg.is_private_content_leaked(unrelated, "uid-A")

    def test_symmetry_player_2_own_not_flagged(
        self, two_player_session: GameSession
    ) -> None:
        """Mirror: uid-B (player_2) is not flagged for their own clue."""
        puzzle = two_player_session.puzzle
        p2_content = puzzle.private_clues["player_2"][0].content
        reg = VisibilityRegistry(two_player_session)
        assert not reg.is_private_content_leaked(p2_content, "uid-B")

    def test_symmetry_player_1_clue_flagged_for_player_2(
        self, two_player_session: GameSession
    ) -> None:
        """uid-B (player_2) pasting player_1's content should be detected."""
        puzzle = two_player_session.puzzle
        p1_content = puzzle.private_clues["player_1"][0].content
        reg = VisibilityRegistry(two_player_session)
        assert reg.is_private_content_leaked(p1_content, "uid-B")


# ---------------------------------------------------------------------------
# 5. Fewer players than puzzle slots
# ---------------------------------------------------------------------------


class TestFewerPlayersThanSlots:
    def test_two_players_in_three_slot_puzzle_no_error(
        self, collab_puzzle: Puzzle
    ) -> None:
        """Only player_1 and player_2 joined; player_3 slot is unused — no crash."""
        session = GameSession(
            session_id="partial",
            puzzle=collab_puzzle,
            history=[],
            player_slot_map={"uid-A": "player_1", "uid-B": "player_2"},
        )
        reg = VisibilityRegistry(session)

        # Both present players get their clues
        ctx_a = reg.get_visible_context("uid-A")
        ctx_b = reg.get_visible_context("uid-B")
        assert len(ctx_a.private_clues) == 1
        assert len(ctx_b.private_clues) == 1

    def test_player_3_slot_unused_absent_from_visible_contexts(
        self, collab_puzzle: Puzzle
    ) -> None:
        """player_3 clues are not visible to player_1 or player_2."""
        session = GameSession(
            session_id="partial-2",
            puzzle=collab_puzzle,
            history=[],
            player_slot_map={"uid-A": "player_1", "uid-B": "player_2"},
        )
        puzzle = collab_puzzle
        p3_ids = {pc.id for pc in puzzle.private_clues.get("player_3", [])}

        reg = VisibilityRegistry(session)
        for uid in ("uid-A", "uid-B"):
            ctx = reg.get_visible_context(uid)
            visible_ids = {c["id"] for c in ctx.private_clues}
            assert visible_ids.isdisjoint(p3_ids), (
                f"{uid} can see player_3 clue(s): {visible_ids & p3_ids}"
            )

    def test_dm_context_still_summarises_all_slots(
        self, collab_puzzle: Puzzle
    ) -> None:
        """DM summary lists all slots defined in the puzzle, even un-filled ones."""
        session = GameSession(
            session_id="partial-3",
            puzzle=collab_puzzle,
            history=[],
            player_slot_map={"uid-A": "player_1", "uid-B": "player_2"},
        )
        reg = VisibilityRegistry(session)
        dm_ctx = reg.get_dm_context()

        # All three slots exist in the puzzle; summary should mention all of them
        for slot in collab_puzzle.private_clues:
            assert slot in dm_ctx.all_private_summary

    def test_unknown_player_id_gets_empty_private_clues(
        self, two_player_session: GameSession
    ) -> None:
        """A player_id not in player_slot_map gets no private clues (no crash)."""
        reg = VisibilityRegistry(two_player_session)
        ctx = reg.get_visible_context("uid-GHOST")
        assert ctx.player_slot == ""
        assert ctx.private_clues == []

    def test_puzzle_without_private_clues_gives_empty_contexts(
        self,
    ) -> None:
        """Standard puzzles (no private_clues field) work without errors."""
        puzzle = load_puzzle("classic_turtle_soup")
        session = GameSession(
            session_id="no-priv",
            puzzle=puzzle,
            history=[],
            player_slot_map={"uid-A": "player_1"},
        )
        reg = VisibilityRegistry(session)
        ctx = reg.get_visible_context("uid-A")
        dm_ctx = reg.get_dm_context()

        assert ctx.private_clues == []
        assert dm_ctx.all_private_summary == ""

    def test_one_player_in_puzzle(self, collab_puzzle: Puzzle) -> None:
        """A single player can still use a collaborative puzzle — gets their slot's clues."""
        session = GameSession(
            session_id="solo-collab",
            puzzle=collab_puzzle,
            history=[],
            player_slot_map={"uid-solo": "player_1"},
        )
        reg = VisibilityRegistry(session)
        ctx = reg.get_visible_context("uid-solo")
        assert ctx.player_slot == "player_1"
        assert len(ctx.private_clues) == 1
