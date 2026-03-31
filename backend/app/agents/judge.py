"""JudgeAgent — truth-judgment engine for Phase 4 murder mystery.

Minimum-privilege design (from CLAUDE.md):
- Receives decomposed key_facts, NOT the raw truth object.
- Does NOT receive truth.culprit or any character's is_culprit field.
- Outputs ONLY a structured judgment — no natural language response.
- The Narrator receives the judgment and generates the actual DM reply.

The key_facts are strings like "死者威士忌杯中含有安眠药成分" — they describe
events without naming who did them.  This means even if the Judge prompt is
extracted, it does not reveal the killer's identity.
"""

from __future__ import annotations

import json
import logging
from typing import TypedDict

from app.llm import chat, strip_think

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

_JUDGMENT_SCHEMA = """{
  "result": "是|不是|无关|部分正确",
  "confidence": 0.85,
  "relevant_fact_ids": ["fact_2", "fact_5"]
}"""


class Judgment(TypedDict):
    result: str             # "是" | "不是" | "无关" | "部分正确"
    confidence: float       # 0.0–1.0
    relevant_fact_ids: list[str]  # e.g. ["fact_0", "fact_3"]


_FALLBACK_JUDGMENT: Judgment = {
    "result": "无关",
    "confidence": 0.0,
    "relevant_fact_ids": [],
}

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_INTRO = """\
你是一个真相判断引擎，专门用于「剧本杀」推理游戏。

## 你的职责
根据已知的案件事实，判断玩家的陈述或提问是否与事实吻合。
你只输出结构化的判断结果，不生成任何自然语言解释或对话。

## 判断标准
- 「是」：玩家陈述与已知事实完全吻合
- 「不是」：玩家陈述与已知事实明确矛盾
- 「部分正确」：玩家陈述部分正确，但有细节偏差或遗漏
- 「无关」：玩家陈述与已知事实无法判断关联，或陈述超出已知事实范围

## 重要限制
- 你只知道以下列出的「已知事实」，不推测事实之外的内容
- 即使玩家问到某个事实，如果该事实不在你的已知事实列表中，判断为「无关」
- 输出必须是严格的 JSON，不得包含任何其他内容"""


# ---------------------------------------------------------------------------
# JudgeAgent
# ---------------------------------------------------------------------------


class JudgeAgent:
    """Truth-judgment engine.  Constructed once per game session.

    Parameters
    ----------
    key_facts : list[str]
        Decomposed facts from ScriptTruth.key_facts.  NO culprit identity.
        These are the only facts the Judge is allowed to use for judgment.
    """

    def __init__(self, key_facts: list[str]) -> None:
        self._key_facts = key_facts
        # Pre-build the facts block and fact_id → content map for logging
        self._fact_lines = "\n".join(
            f"[fact_{i}] {fact}" for i, fact in enumerate(key_facts)
        )
        self._system_prompt = self._build_system_prompt()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def judge(
        self,
        message: str,
        player_visible_facts: list[str] | None = None,
    ) -> Judgment:
        """Evaluate *message* against the known key_facts.

        Parameters
        ----------
        message : str
            The player's question or statement.
        player_visible_facts : list[str] | None
            Fact strings the player has already confirmed or unlocked.
            Used to give the Judge context about what the player already knows,
            so it can correctly answer follow-up questions.
        """
        messages = self._build_messages(message, player_visible_facts or [])
        try:
            raw = await chat(self._system_prompt, messages)
            return self._parse(raw)
        except Exception as exc:
            logger.exception("JudgeAgent.judge failed: %s", exc)
            return _FALLBACK_JUDGMENT

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        return f"""{_SYSTEM_INTRO}

## 已知事实列表（你只能基于这些事实做出判断）
{self._fact_lines}

## 输出格式（严格 JSON，不含任何其他内容）
{_JUDGMENT_SCHEMA}

字段说明：
- result: 必须是「是」「不是」「无关」「部分正确」之一
- confidence: 0.0到1.0，你对该判断的置信度
- relevant_fact_ids: 与判断相关的事实编号列表（如 ["fact_0", "fact_2"]）"""

    def _build_messages(
        self,
        message: str,
        player_visible_facts: list[str],
    ) -> list[dict]:
        """Build the messages list for the LLM call."""
        content_parts = []
        if player_visible_facts:
            visible_block = "\n".join(f"- {f}" for f in player_visible_facts)
            content_parts.append(
                f"【玩家已知信息（供参考）】\n{visible_block}"
            )
        content_parts.append(f"【玩家陈述/问题】\n{message}")
        return [{"role": "user", "content": "\n\n".join(content_parts)}]

    @staticmethod
    def _parse(raw: str) -> Judgment:
        """Extract a Judgment from the LLM response."""
        text = strip_think(raw).strip()

        # Strip markdown fences if present
        fenced = __import__("re").search(r"```(?:json)?\s*(\{.*?\})\s*```", text, __import__("re").DOTALL)
        if fenced:
            text = fenced.group(1)
        # Find first JSON object
        match = __import__("re").search(r"\{.*?\}", text, __import__("re").DOTALL)
        if match:
            text = match.group(0)

        data = json.loads(text)
        result = str(data.get("result", "无关"))
        if result not in ("是", "不是", "无关", "部分正确"):
            result = "无关"
        confidence = float(data.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
        relevant = [str(f) for f in data.get("relevant_fact_ids", [])]
        return Judgment(result=result, confidence=confidence, relevant_fact_ids=relevant)
