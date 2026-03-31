"""SafetyAgent — post-generation leak detection for Phase 4.

This agent is the last line of defense before any DM/NPC output reaches players.
It sees the full truth + all character secrets to verify that narrator/NPC output
does not leak secret information.

Two-pass design:
  Pass 1 (always): Fast regex/substring scan against key_facts and secret_bios
                   that the audience player should NOT see.
  Pass 2 (optional): Lightweight LLM call for paraphrase detection when
                     Pass 1 is inconclusive.  Only triggered for longer
                     outputs where verbatim detection is insufficient.

The Safety Agent NEVER blocks on false positives — when uncertain, it passes
with a logged warning rather than disrupting the game.  The orchestrator
handles retries and fallback responses.
"""

from __future__ import annotations

import logging
import re
from typing import TypedDict

from app.llm import chat, strip_think

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

# Minimum character n-gram length for verbatim detection
_MIN_SNIPPET_LEN = 8

# Text length threshold above which we consider an LLM second pass
# (short messages rarely contain paraphrased leaks worth the LLM cost)
_LLM_CHECK_MIN_LEN = 30

_SAFETY_SYSTEM_PROMPT = """\
你是一个内容安全检查系统，用于「剧本杀」游戏。

## 你的职责
判断以下「待检查文本」是否泄露了「禁止透露的秘密信息」。

## 判断标准
- 如果文本用任何方式（直接引用、改写、暗示）透露了秘密信息，判断为不安全
- 如果文本只讨论公开信息，判断为安全
- 对于模糊情况，偏向于判断为安全（避免误判干扰游戏）

## 输出格式（严格 JSON）
{"safe": true, "leaked_content": null}
或
{"safe": false, "leaked_content": "具体泄露的内容片段"}"""


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
        visibility: "VisibilityRegistryLike | None" = None,  # noqa: F821
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

        # Pass 2: optional LLM paraphrase check for longer outputs
        if len(text) >= _LLM_CHECK_MIN_LEN:
            llm_result = await self._llm_check(text, viewer_char_id)
            if not llm_result["safe"]:
                logger.warning(
                    "SafetyAgent: LLM paraphrase leak detected: %r",
                    (llm_result.get("leaked_content") or "")[:40],
                )
                return llm_result

        return SafetyResult(safe=True, leaked_content=None)

    # ------------------------------------------------------------------
    # Pass 1: verbatim scan
    # ------------------------------------------------------------------

    def _verbatim_scan(self, text: str, viewer_char_id: str | None) -> str | None:
        """Return a leaked snippet if any forbidden content appears verbatim."""
        # Check key_facts
        for fact in self._key_facts:
            if len(fact) >= _MIN_SNIPPET_LEN and fact in text:
                return fact

        # Check character secrets (excluding the viewer's own character)
        for char_id, secret_bio in self._character_secrets.items():
            if char_id == viewer_char_id:
                continue  # viewer can see their own secret
            snippet = self._find_long_substring(text, secret_bio, min_len=_MIN_SNIPPET_LEN)
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

    # ------------------------------------------------------------------
    # Pass 2: LLM paraphrase check
    # ------------------------------------------------------------------

    async def _llm_check(self, text: str, viewer_char_id: str | None) -> SafetyResult:
        """Use LLM for paraphrase-aware leak detection."""
        forbidden_parts = [f"- {fact}" for fact in self._key_facts]
        for char_id, secret_bio in self._character_secrets.items():
            if char_id == viewer_char_id:
                continue
            # Only include the first 80 chars of each secret to keep prompt short
            forbidden_parts.append(f"- [角色秘密] {secret_bio[:80]}…")

        if not forbidden_parts:
            return SafetyResult(safe=True, leaked_content=None)

        forbidden_block = "\n".join(forbidden_parts)
        messages = [
            {
                "role": "user",
                "content": (
                    f"## 禁止透露的秘密信息\n{forbidden_block}\n\n"
                    f"## 待检查文本\n{text}"
                ),
            }
        ]
        try:
            raw = await chat(_SAFETY_SYSTEM_PROMPT, messages)
            result_text = strip_think(raw).strip()
            # Extract JSON
            match = re.search(r"\{.*?\}", result_text, re.DOTALL)
            if match:
                import json
                data = json.loads(match.group(0))
                safe = bool(data.get("safe", True))
                leaked = data.get("leaked_content") or None
                return SafetyResult(safe=safe, leaked_content=leaked)
        except Exception as exc:
            logger.exception("SafetyAgent._llm_check failed: %s", exc)

        # On LLM failure: assume safe (avoid disrupting game on false positives)
        return SafetyResult(safe=True, leaked_content=None)
