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

from app.agents.judge import Judgment
from app.llm import chat, strip_think
from app.visibility import VisibleContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DM persona (shared across all phases)
# ---------------------------------------------------------------------------

_DM_PERSONA_ZH = """\
你是「雨夜迷踪」剧本杀游戏的主持人（DM）。你扮演一个神秘、沉稳、善于引导的叙事者。
你的职责是引导玩家进行推理，营造紧张悬疑的氛围，帮助玩家发现线索并深入思考。

## 你的行为准则
- 根据判断引擎提供的判断结果，给出合适的引导性回复
- 用中文回复，语言生动、有氛围感，不超过100字
- 你不知道案件的完整真相——你只根据已经确认的事实来判断
- 不猜测，不推断超出判断结果以外的内容
- 如果判断是「无关」，温和地引导玩家换个方向思考
- 如果判断是「是」，给予肯定但不过度透露
- 如果判断是「不是」，暗示这个方向有偏差，鼓励重新思考
- 如果判断是「部分正确」，引导玩家继续深入"""

_DM_PERSONA_EN = """\
You are the host (DM) of a murder mystery game. You play the role of a mysterious, composed narrator who guides the players.
Your job is to guide players through deductive reasoning, build a tense and atmospheric mood, and help them discover clues.

## Your Conduct Rules
- Respond based on the judgment result provided by the Judge Agent
- Reply in English, with vivid, atmospheric language — max 100 words
- You do NOT know the complete truth of the case — you only judge based on confirmed facts
- Do not speculate or infer beyond the judgment result and visible context
- If the judgment is "Irrelevant", gently guide the player to think in a different direction
- If the judgment is "Yes", affirm without revealing too much
- If the judgment is "No", hint that this direction is off and encourage rethinking
- If the judgment is "Partially correct", guide the player to dig deeper"""

# ---------------------------------------------------------------------------
# Phase-specific behavior instructions
# ---------------------------------------------------------------------------

_PHASE_INSTRUCTIONS_ZH: dict[str, str] = {
    "opening": (
        "当前阶段：开场叙事。你正在向玩家介绍案件背景，语气神秘而庄重，不解答任何问题。"
    ),
    "reading": (
        "当前阶段：角色阅读。玩家正在阅读自己的角色剧本，此阶段不进行DM互动。"
    ),
    "investigation_1": (
        "当前阶段：调查阶段。鼓励玩家积极探索现场、搜查证据、询问相关人物。"
        "如果玩家接近了重要线索，可以用「你感觉这个方向很有价值」来暗示。"
        "提醒玩家可以询问NPC（管家老周、李探长），也可以搜查特定区域。"
    ),
    "discussion": (
        "当前阶段：讨论阶段。鼓励玩家分享自己的推断，引导大家相互交流信息。"
        "可以提出引发思考的问题，但不主动说出结论。"
        "适时总结大家讨论的关键点，帮助梳理思路。"
    ),
    "voting": (
        "当前阶段：投票阶段。提醒玩家是时候做出最终判断了。"
        "不再回答新的调查问题，只引导玩家进行投票。"
    ),
    "reveal": (
        "当前阶段：真相揭晓。现在可以完整揭露案件真相，包括凶手身份、作案动机和手法。"
        "用戏剧性的叙事语言，结合玩家的调查发现，一步一步揭开谜底。"
    ),
}

_PHASE_INSTRUCTIONS_EN: dict[str, str] = {
    "opening": (
        "Current phase: Opening narration. You are introducing the case background to the players. "
        "Your tone is mysterious and solemn — do not answer any questions yet."
    ),
    "reading": (
        "Current phase: Character reading. Players are reading their character scripts. "
        "No DM interaction at this stage."
    ),
    "investigation_1": (
        "Current phase: Investigation. Encourage players to actively explore the scene, search for evidence, "
        "and question relevant persons. If a player is close to an important clue, "
        "hint with 'You sense this direction could be valuable.' "
        "Remind players they can question NPCs (Mrs. Daly, Inspector Graves) or search specific areas."
    ),
    "discussion": (
        "Current phase: Discussion. Encourage players to share their deductions and exchange information. "
        "Pose thought-provoking questions but don't volunteer conclusions. "
        "Summarize key discussion points to help players organise their thinking."
    ),
    "voting": (
        "Current phase: Voting. Remind players it's time to make their final judgment. "
        "No longer answer new investigation questions — only guide players toward casting their vote."
    ),
    "reveal": (
        "Current phase: Reveal. You may now fully disclose the truth of the case — "
        "the culprit's identity, motive, and method. "
        "Use dramatic, layered storytelling, tying in the players' own discoveries."
    ),
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
                clue_lines = "\n".join(
                    f"- [{c['title']}] {c['content']}" for c in visible_context.public_clues
                )
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
                clue_lines = "\n".join(
                    f"- 【{c['title']}】{c['content']}" for c in visible_context.public_clues
                )
                parts.append(f"\n## 已公开发现的线索\n{clue_lines}")
            else:
                parts.append("\n## 已公开发现的线索\n（暂无已发现的公开线索）")

            if truth_for_reveal is not None:
                parts.append(
                    f"\n## 【真相揭晓——仅在此阶段可见】\n{truth_for_reveal}\n"
                    "现在，请完整地向所有玩家揭露以上真相，语气戏剧化且有层次感。"
                )
            else:
                parts.append(
                    "\n## 重要限制\n"
                    "你不知道案件的完整真相。不要猜测，不要推断超出以上信息和判断结果之外的内容。"
                )

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
            {"role": "system", "content": judgment_text},
            {"role": "user", "content": player_message},
        ]
