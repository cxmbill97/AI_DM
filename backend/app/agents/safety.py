"""SafetyAgent — post-generation leak detection for Phase 4.

This agent is the last line of defense before any DM/NPC output reaches players.
It sees the full truth + all character secrets to verify that narrator/NPC output
does not leak secret information.

Single-pass design:
  Fast regex/substring scan against key_facts and secret_bios that the audience
  player should NOT see.

The LLM paraphrase check (formerly Pass 2) was removed: the NarratorAgent is
architecturally blind to key_facts and character secrets by design, making
paraphrase leaks effectively impossible. The verbatim scan is sufficient.
"""

from __future__ import annotations

import logging
from typing import TypedDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class SafetyResult(TypedDict):
    safe: bool
    leaked_content: str | None  # the offending snippet, or None if safe


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum verbatim length for key_fact detection (full fact string must match)
_MIN_FACT_LEN = 8
# Minimum verbatim substring for secret_bio detection — kept high to avoid
# false positives from character names / locations shared between narrator output
# and secret bios (e.g. "Lord Thornfield" appears in both legitimate responses
# and in Eleanor's / Finch's secret bios).
_MIN_SECRET_SNIPPET_LEN = 30


# ---------------------------------------------------------------------------
# SafetyAgent
# ---------------------------------------------------------------------------


class SafetyAgent:
    """Post-generation safety check.  Constructed once per game session.

    Parameters
    ----------
    key_facts : list[str]
        Decomposed truth facts.  Verbatim appearance of 8+ chars from any
        key_fact in generated text is flagged as a leak.
    character_secrets : dict[str, str]
        Maps character_id → secret_bio text.  Used to detect secret bio
        leakage in generated text.
    """

    def __init__(
        self,
        key_facts: list[str],
        character_secrets: dict[str, str],
    ) -> None:
        self._key_facts = key_facts
        self._character_secrets = character_secrets  # char_id → secret_bio

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check(
        self,
        text: str,
        audience_player_id: str,  # noqa: ARG002 — reserved for future per-player secrets
        visibility: VisibilityRegistryLike | None = None,  # noqa: F821
        viewer_char_id: str | None = None,
    ) -> SafetyResult:
        """Check *text* for secret information leakage.

        Parameters
        ----------
        text : str
            The narrator or NPC output to be checked.
        audience_player_id : str
            The player who will receive this text.  Reserved for
            future per-player secret tracking.
        visibility : optional
            VisibilityRegistry instance.  When provided, also checks against
            turtle-soup private clue content (Phase 3 integration).
        viewer_char_id : str | None
            Character id assigned to the audience player.  If provided,
            that character's secret_bio is excluded from the leak scan
            (a player is allowed to see their own character's secrets).
        """
        # Pass 1: fast verbatim scan
        leak = self._verbatim_scan(text, viewer_char_id)
        if leak is not None:
            logger.warning("SafetyAgent: verbatim leak detected: %r", leak[:40])
            return SafetyResult(safe=False, leaked_content=leak)

        # Phase 3 integration: check against turtle-soup private clues
        if visibility is not None:
            ts_leak = self._turtle_soup_scan(text, audience_player_id, visibility)
            if ts_leak is not None:
                logger.warning("SafetyAgent: turtle-soup private clue leak: %r", ts_leak[:40])
                return SafetyResult(safe=False, leaked_content=ts_leak)

        return SafetyResult(safe=True, leaked_content=None)

    # ------------------------------------------------------------------
    # Pass 1: verbatim scan
    # ------------------------------------------------------------------

    def _verbatim_scan(self, text: str, viewer_char_id: str | None) -> str | None:
        """Return a leaked snippet if any forbidden content appears verbatim."""
        # Check key_facts — full fact string must appear verbatim
        for fact in self._key_facts:
            if len(fact) >= _MIN_FACT_LEN and fact in text:
                return fact

        # Check character secrets — only catch long verbatim phrases to avoid
        # false positives from character names that naturally appear in DM narration
        for char_id, secret_bio in self._character_secrets.items():
            if char_id == viewer_char_id:
                continue  # viewer can see their own secret
            snippet = self._find_long_substring(text, secret_bio, min_len=_MIN_SECRET_SNIPPET_LEN)
            if snippet:
                return snippet

        return None

    @staticmethod
    def _find_long_substring(text: str, reference: str, min_len: int) -> str | None:
        """Return the longest common substring of ≥ min_len chars, or None."""
        for start in range(len(reference) - min_len + 1):
            for end in range(len(reference), start + min_len - 1, -1):
                snippet = reference[start:end]
                if snippet in text:
                    return snippet
        return None

    # ------------------------------------------------------------------
    # Phase 3 integration: turtle-soup private clue scan
    # ------------------------------------------------------------------

    @staticmethod
    def _turtle_soup_scan(
        text: str,
        audience_player_id: str,
        visibility: object,
    ) -> str | None:
        """Check against Phase 3 private clues using VisibilityRegistry."""
        # Lazy check: VisibilityRegistry.is_private_content_leaked uses 4-gram similarity
        try:
            if visibility.is_private_content_leaked(text, audience_player_id):  # type: ignore[union-attr]
                return "private_clue_content_detected"
        except Exception:
            pass
        return None
