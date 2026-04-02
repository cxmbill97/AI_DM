"""NarratorAgent — atmospheric DM response generator for Phase 4.

Minimum-privilege design (CRITICAL, from CLAUDE.md):
- This agent is DELIBERATELY BLIND to truth and key_facts.
- Constructor accepts NO truth, NO key_facts, NO culprit identity.
- It generates DM responses based solely on:
    - The judgment result from JudgeAgent
    - The player's visible context (public info + their own unlocked clues)
    - Phase-specific behavior instructions
- The only exception is the reveal phase, where truth is explicitly injected
  by the orchestrator as a controlled one-time disclosure.

This means that even if this agent's prompt is extracted, it cannot reveal
the truth — because it genuinely does not have it.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from app.agents.judge import Judgment
from app.llm import chat, chat_stream, strip_think
from app.visibility import VisibleContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DM persona (shared across all phases)
# ---------------------------------------------------------------------------

_DM_PERSONA_ZH = """\
剧本杀DM，神秘沉稳的叙事者。根据判断结果给出引导性回复，中文，不超过80字，语言有氛围感。
是→肯定引导，不是→暗示偏差，部分正确→鼓励深入，无关→温和换方向。
不知道完整真相，不推测判断结果以外的内容。"""

_DM_PERSONA_EN = """\
Murder mystery DM — mysterious, composed narrator. Reply in English ≤80 words, atmospheric.
Yes→affirm, No→hint off-track, Partially correct→dig deeper, Irrelevant→redirect gently.
You don't know the full truth. Don't speculate beyond the judgment."""

# ---------------------------------------------------------------------------
# Phase-specific behavior instructions
# ---------------------------------------------------------------------------

_PHASE_INSTRUCTIONS_ZH: dict[str, str] = {
    "opening": "开场叙事阶段，介绍案件背景，语气神秘庄重，不解答问题。",
    "reading": "角色阅读阶段，不进行DM互动。",
    "investigation_1": "调查阶段。鼓励探索、搜查、询问NPC。接近线索时可暗示「这方向有价值」。",
    "discussion": "讨论阶段。鼓励分享推断、相互交流。提出思考性问题，适时总结关键点。",
    "voting": "投票阶段。引导玩家做最终判断，不再回答调查问题。",
    "reveal": "真相揭晓阶段。完整揭露凶手、动机、手法，叙事戏剧化有层次感。",
}

_PHASE_INSTRUCTIONS_EN: dict[str, str] = {
    "opening": "Opening narration — introduce the case, mysterious tone, no questions answered.",
    "reading": "Character reading phase — no DM interaction.",
    "investigation_1": "Investigation. Encourage exploring, searching, questioning NPCs. Hint 'This direction looks promising' when close.",
    "discussion": "Discussion. Encourage sharing deductions. Pose questions, summarise key points.",
    "voting": "Voting phase. Guide players to final judgment; don't answer new investigation questions.",
    "reveal": "Reveal phase. Fully disclose culprit, motive, method — dramatic layered storytelling.",
}

_DEFAULT_PHASE_INSTRUCTION_ZH = "引导玩家继续推理，维持紧张悬疑的氛围。"
_DEFAULT_PHASE_INSTRUCTION_EN = "Guide the players to continue reasoning and maintain a tense, atmospheric mood."

# ---------------------------------------------------------------------------
# Fallback responses
# ---------------------------------------------------------------------------

_FALLBACK_RESPONSE_ZH = "让我们继续讨论……案件的真相就在细节之中。"
_FALLBACK_RESPONSE_EN = "Let us continue… the truth of the case lies in the details."
_REGENERATION_FALLBACK_ZH = "这是一个很有意思的角度，让我们继续深入探讨。"
_REGENERATION_FALLBACK_EN = "That's an intriguing angle — let's explore it further."

# Keep old names as aliases for backward compatibility
_DM_PERSONA = _DM_PERSONA_ZH
_PHASE_INSTRUCTIONS = _PHASE_INSTRUCTIONS_ZH
_DEFAULT_PHASE_INSTRUCTION = _DEFAULT_PHASE_INSTRUCTION_ZH
_FALLBACK_RESPONSE = _FALLBACK_RESPONSE_ZH
_REGENERATION_FALLBACK = _REGENERATION_FALLBACK_ZH


# ---------------------------------------------------------------------------
# NarratorAgent
# ---------------------------------------------------------------------------


class NarratorAgent:
    """Atmospheric DM response generator.  Deliberately blind to truth.

    No constructor parameters — the agent has no access to truth or key_facts.
    Truth is injected ONLY by the orchestrator during the reveal phase as an
    explicit controlled disclosure.
    """

    def __init__(self) -> None:
        pass  # Deliberately empty — no truth, no key_facts

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def narrate(
        self,
        judgment: Judgment,
        player_message: str,
        visible_context: VisibleContext,
        phase: str,
        dm_style: str = "atmospheric",
        truth_for_reveal: str | None = None,
        language: str = "zh",
    ) -> str:
        """Generate an atmospheric DM response.

        Parameters
        ----------
        judgment : Judgment
            Result from JudgeAgent.  The narrator bases its response on this.
        player_message : str
            The original player message (for context).
        visible_context : VisibleContext
            What the asking player is allowed to see.
        phase : str
            Current phase id — drives phase-specific behavior.
        dm_style : str
            Future extension (e.g. "atmospheric", "direct").  Currently unused.
        truth_for_reveal : str | None
            ONLY provided by orchestrator during reveal phase.  If None,
            this agent has no knowledge of the truth whatsoever.
        language : str
            "zh" or "en" — controls DM narration language.
        """
        fallback = _FALLBACK_RESPONSE_EN if language == "en" else _FALLBACK_RESPONSE_ZH
        system_prompt = self._build_system_prompt(
            phase=phase,
            visible_context=visible_context,
            truth_for_reveal=truth_for_reveal,
            language=language,
        )
        messages = self._build_messages(judgment, player_message, language=language)
        try:
            raw = await chat(system_prompt, messages)
            text = strip_think(raw).strip()
            return text if text else fallback
        except Exception as exc:
            logger.exception("NarratorAgent.narrate failed: %s", exc)
            return fallback

    async def narrate_stream(
        self,
        judgment: Judgment,
        player_message: str,
        visible_context: VisibleContext,
        phase: str,
        truth_for_reveal: str | None = None,
        language: str = "zh",
    ) -> AsyncGenerator[str, None]:
        """Stream the narrator response token-by-token.

        Yields string chunks.  The caller should accumulate them for safety
        checks; <think> filtering is handled inside chat_stream().
        """
        system_prompt = self._build_system_prompt(
            phase=phase,
            visible_context=visible_context,
            truth_for_reveal=truth_for_reveal,
            language=language,
        )
        messages = self._build_messages(judgment, player_message, language=language)
        return chat_stream(system_prompt, messages)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_system_prompt(
        self,
        phase: str,
        visible_context: VisibleContext,
        truth_for_reveal: str | None,
        language: str = "zh",
    ) -> str:
        if language == "en":
            parts = [_DM_PERSONA_EN]
            phase_instruction = _PHASE_INSTRUCTIONS_EN.get(phase, _DEFAULT_PHASE_INSTRUCTION_EN)
            parts.append(f"\n## Current Phase Behavior\n{phase_instruction}")

            if visible_context.surface:
                parts.append(f"\n## Case Background (known to all players)\n{visible_context.surface}")

            if visible_context.public_clues:
                clue_lines = "\n".join(f"- [{c['title']}] {c['content']}" for c in visible_context.public_clues)
                parts.append(f"\n## Publicly Discovered Clues\n{clue_lines}")
            else:
                parts.append("\n## Publicly Discovered Clues\n(No public clues discovered yet.)")

            if truth_for_reveal is not None:
                parts.append(
                    f"\n## [TRUTH REVEAL — visible only at this phase]\n{truth_for_reveal}\n"
                    "Now reveal the full truth to all players in dramatic, layered storytelling."
                )
            else:
                parts.append(
                    "\n## Important Constraint\n"
                    "You do NOT know the complete truth of the case. "
                    "Do not speculate beyond the information and judgment result above."
                )
        else:
            parts = [_DM_PERSONA_ZH]
            phase_instruction = _PHASE_INSTRUCTIONS_ZH.get(phase, _DEFAULT_PHASE_INSTRUCTION_ZH)
            parts.append(f"\n## 当前阶段行为\n{phase_instruction}")

            if visible_context.surface:
                parts.append(f"\n## 案件背景（所有玩家已知）\n{visible_context.surface}")

            if visible_context.public_clues:
                clue_lines = "\n".join(f"- 【{c['title']}】{c['content']}" for c in visible_context.public_clues)
                parts.append(f"\n## 已公开发现的线索\n{clue_lines}")
            else:
                parts.append("\n## 已公开发现的线索\n（暂无已发现的公开线索）")

            if truth_for_reveal is not None:
                parts.append(f"\n## 【真相揭晓——仅在此阶段可见】\n{truth_for_reveal}\n现在，请完整地向所有玩家揭露以上真相，语气戏剧化且有层次感。")
            else:
                parts.append("\n## 重要限制\n你不知道案件的完整真相。不要猜测，不要推断超出以上信息和判断结果之外的内容。")

        return "\n".join(parts)

    @staticmethod
    def _build_messages(judgment: Judgment, player_message: str, language: str = "zh") -> list[dict]:
        """Build the messages list including the judgment result."""
        if language == "en":
            judgment_text = (
                f"[Judge Agent Result]\n"
                f"- Judgment: {judgment['result']}\n"
                f"- Confidence: {judgment['confidence']:.0%}\n"
                f"- Relevant fact IDs: {', '.join(judgment['relevant_fact_ids']) or 'none'}"
            )
        else:
            judgment_text = (
                f"【判断引擎结果】\n"
                f"- 判断：{judgment['result']}\n"
                f"- 置信度：{judgment['confidence']:.0%}\n"
                f"- 相关事实编号：{', '.join(judgment['relevant_fact_ids']) or '无'}"
            )
        return [
            {"role": "user", "content": f"{judgment_text}\n\n{player_message}"},
        ]
