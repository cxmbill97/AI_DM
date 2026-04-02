"""Visibility layer for Phase 3 information asymmetry.

Each player in a multiplayer room may hold private clue fragments that other
players must NOT see.  This module enforces that boundary:

  VisibilityRegistry   — the main public class; call get_visible_context() to
                         get a player's personalised view and get_dm_context()
                         for the full truth-facing prompt context.

  VisibleContext        — what a single player is allowed to see
  DMContext             — full context given to the DM LLM (truth + all clues)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import GameSession, PrivateClue

# ---------------------------------------------------------------------------
# Data-transfer objects
# ---------------------------------------------------------------------------


@dataclass
class VisibleContext:
    """Everything a single player is permitted to see."""

    player_id: str
    player_slot: str  # "player_1", "player_2", …
    surface: str  # 汤面
    public_clues: list[dict]  # unlocked public clues (id, title, content)
    private_clues: list[dict]  # this player's private fragments (id, title, content)


@dataclass
class DMContext:
    """Full context given to the DM LLM — includes truth and ALL clues."""

    surface: str
    truth: str
    key_facts: list[str]
    public_clues_unlocked: list[dict]  # unlocked public clue dicts
    public_clues_locked_ids: list[str]  # ids of clues not yet unlocked
    all_private_summary: str  # collapsed single string for DM awareness


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class VisibilityRegistry:
    """Enforces information boundaries for a single game session.

    Usage::

        registry = VisibilityRegistry(session)
        ctx = registry.get_visible_context(player_id)    # player's view
        dm_ctx = registry.get_dm_context()               # for LLM prompt
        leaked = registry.is_private_content_leaked(text, player_id)
    """

    def __init__(self, session: GameSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_visible_context(self, player_id: str) -> VisibleContext:
        """Return what *player_id* is allowed to see."""
        session = self._session
        puzzle = session.puzzle

        player_slot = session.player_slot_map.get(player_id, "")

        # Public unlocked clues
        public_clues = [
            {"id": c.id, "title": c.title, "content": c.content}
            for c in puzzle.clues
            if c.id in session.unlocked_clue_ids
        ]

        # Private clues for this player's slot only
        private_frags: list[PrivateClue] = puzzle.private_clues.get(player_slot, [])
        private_clues = [
            {"id": pc.id, "title": pc.title, "content": pc.content}
            for pc in private_frags
        ]

        return VisibleContext(
            player_id=player_id,
            player_slot=player_slot,
            surface=puzzle.surface,
            public_clues=public_clues,
            private_clues=private_clues,
        )

    def get_dm_context(self) -> DMContext:
        """Return the full context the DM LLM needs to judge questions."""
        session = self._session
        puzzle = session.puzzle

        unlocked = [
            {"id": c.id, "title": c.title, "content": c.content}
            for c in puzzle.clues
            if c.id in session.unlocked_clue_ids
        ]
        locked_ids = [c.id for c in puzzle.clues if c.id not in session.unlocked_clue_ids]

        return DMContext(
            surface=puzzle.surface,
            truth=puzzle.truth,
            key_facts=puzzle.key_facts,
            public_clues_unlocked=unlocked,
            public_clues_locked_ids=locked_ids,
            all_private_summary=self._get_all_private_summary(),
        )

    def is_own_clue_verbatim(self, text: str, player_id: str, threshold: float = 0.6) -> bool:
        """Return True if *text* is a near-verbatim copy of this player's own private clue.

        Blocks players from copy-pasting their raw clue content into public chat.
        They should describe information in their own words (higher threshold than
        cross-player leak detection, since topical overlap is expected).
        """
        session = self._session
        puzzle = session.puzzle
        slot = session.player_slot_map.get(player_id, "")
        for pc in puzzle.private_clues.get(slot, []):
            if self._similarity_check(text, pc.content, threshold=threshold):
                return True
        return False

    def is_private_content_leaked(self, text: str, viewer_player_id: str) -> bool:
        """Return True if *text* contains private content belonging to another player.

        Uses character 4-gram similarity to catch paraphrased leaks, not just
        exact string matches.
        """
        session = self._session
        puzzle = session.puzzle

        viewer_slot = session.player_slot_map.get(viewer_player_id, "")

        for slot, frags in puzzle.private_clues.items():
            if slot == viewer_slot:
                continue  # own private clues are fine
            for pc in frags:
                if self._similarity_check(text, pc.content):
                    return True
        return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_all_private_summary(self) -> str:
        """Collapse all private clue fragments into a single DM-awareness string.

        The DM needs to know what private information exists (so it can judge
        whether a player's question could only come from their private clue)
        but we don't need full detail — a brief slot→title list is enough.
        """
        puzzle = self._session.puzzle
        if not puzzle.private_clues:
            return ""

        lines: list[str] = []
        for slot, frags in sorted(puzzle.private_clues.items()):
            titles = "、".join(pc.title for pc in frags)
            lines.append(f"{slot}: {titles}")
        return "各玩家私有线索（仅供DM参考）：\n" + "\n".join(lines)

    @staticmethod
    def _similarity_check(text: str, reference: str, threshold: float = 0.4) -> bool:
        """Return True if *text* shares ≥ threshold of 4-grams with *reference*.

        Character 4-grams work well for Chinese text where word boundaries are
        implicit.  Threshold 0.4 catches paraphrased content while allowing
        thematic overlap between questions and clue topics.
        """
        if not text or not reference:
            return False

        def ngrams(s: str, n: int = 4) -> set[str]:
            return {s[i : i + n] for i in range(len(s) - n + 1)}

        ref_grams = ngrams(reference)
        if not ref_grams:
            return False

        txt_grams = ngrams(text)
        overlap = len(txt_grams & ref_grams) / len(ref_grams)
        return overlap >= threshold
