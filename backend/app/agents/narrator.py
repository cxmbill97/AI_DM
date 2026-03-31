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

_DM_PERSONA = """\
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

# ---------------------------------------------------------------------------
# Phase-specific behavior instructions
# ---------------------------------------------------------------------------

_PHASE_INSTRUCTIONS: dict[str, str] = {
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

_DEFAULT_PHASE_INSTRUCTION = (
    "引导玩家继续推理，维持紧张悬疑的氛围。"
)

# ---------------------------------------------------------------------------
# Fallback responses
# ---------------------------------------------------------------------------

_FALLBACK_RESPONSE = "让我们继续讨论……案件的真相就在细节之中。"
_REGENERATION_FALLBACK = "这是一个很有意思的角度，让我们继续深入探讨。"


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
        """
        system_prompt = self._build_system_prompt(
            phase=phase,
            visible_context=visible_context,
            truth_for_reveal=truth_for_reveal,
        )
        messages = self._build_messages(judgment, player_message)
        try:
            raw = await chat(system_prompt, messages)
            text = strip_think(raw).strip()
            return text if text else _FALLBACK_RESPONSE
        except Exception as exc:
            logger.exception("NarratorAgent.narrate failed: %s", exc)
            return _FALLBACK_RESPONSE

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_system_prompt(
        self,
        phase: str,
        visible_context: VisibleContext,
        truth_for_reveal: str | None,
    ) -> str:
        parts = [_DM_PERSONA]

        # Phase-specific behavior
        phase_instruction = _PHASE_INSTRUCTIONS.get(phase, _DEFAULT_PHASE_INSTRUCTION)
        parts.append(f"\n## 当前阶段行为\n{phase_instruction}")

        # Player's visible context — public scene + unlocked clues
        if visible_context.surface:
            parts.append(f"\n## 案件背景（所有玩家已知）\n{visible_context.surface}")

        if visible_context.public_clues:
            clue_lines = "\n".join(
                f"- 【{c['title']}】{c['content']}" for c in visible_context.public_clues
            )
            parts.append(f"\n## 已公开发现的线索\n{clue_lines}")
        else:
            parts.append("\n## 已公开发现的线索\n（暂无已发现的公开线索）")

        # CRITICAL: truth section — only present in reveal phase
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
    def _build_messages(judgment: Judgment, player_message: str) -> list[dict]:
        """Build the messages list including the judgment result."""
        # Judgment result as a user-facing context message
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
