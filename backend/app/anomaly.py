"""AI-based anomaly detection for suspicious answers.

Runs a lightweight LLM check when a player gives a high-progress answer to
detect whether the answer contains insider knowledge (e.g. the player looked
up the solution). Fires asynchronously and never blocks the game flow.
"""

from __future__ import annotations

import json
import logging
from typing import TypedDict

from app.llm import chat, strip_think

logger = logging.getLogger(__name__)

# Only check answers that reach this truth_progress threshold
_MIN_PROGRESS_TO_CHECK = 0.6


class AnomalyResult(TypedDict):
    suspicious: bool
    confidence: float  # 0.0–1.0
    reason: str


class AnomalyDetector:
    """Detect suspiciously accurate answers using a lightweight LLM prompt."""

    def __init__(self, key_facts: list[str], truth: str) -> None:
        self._key_facts = key_facts
        self._truth = truth

    async def check(
        self,
        player_message: str,
        judgment: str,
        truth_progress: float,
    ) -> AnomalyResult:
        """Return an AnomalyResult.

        Fast path: if truth_progress < threshold, returns non-suspicious immediately
        without making an LLM call.
        On any LLM error, returns non-suspicious (safe default).
        """
        if truth_progress < _MIN_PROGRESS_TO_CHECK:
            return {"suspicious": False, "confidence": 0.0, "reason": "below threshold"}

        system_prompt = (
            "You are a game integrity monitor for a lateral thinking puzzle game. "
            "Your job is to detect if a player's question/answer looks like they already know "
            "the solution (e.g. they looked it up online) rather than deducing it through play. "
            "You will be given a few key facts about the puzzle answer and the player's message. "
            "Respond ONLY with valid JSON matching: "
            '{"suspicious": bool, "confidence": 0.0-1.0, "reason": "brief explanation"}'
        )

        facts_summary = "; ".join(self._key_facts[:5])  # limit to 5 facts to keep cost low
        user_content = (
            f"Key facts (partial): {facts_summary}\n"
            f"Player message: {player_message}\n"
            f"DM judgment: {judgment}\n\n"
            "Does this message look like the player has insider knowledge of the answer? "
            "Consider: Does it use very specific phrasing from the answer? "
            "Does it jump directly to an obscure detail without buildup? "
            "Or is it a natural deduction from earlier clues?"
        )

        try:
            raw = await chat(system_prompt, [{"role": "user", "content": user_content}])
            text = strip_think(raw)
            # Extract JSON from the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON found in response")
            data = json.loads(text[start:end])
            return {
                "suspicious": bool(data.get("suspicious", False)),
                "confidence": float(data.get("confidence", 0.0)),
                "reason": str(data.get("reason", "")),
            }
        except Exception as exc:
            logger.warning("Anomaly check failed: %s", exc)
            return {"suspicious": False, "confidence": 0.0, "reason": f"check error: {exc}"}
