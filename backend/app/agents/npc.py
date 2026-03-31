"""NPCAgent — in-character response generator for Phase 4 murder mystery NPCs.

Each NPC has a persona prompt and a knowledge boundary (list of clue IDs it
knows about).  The NPC can only answer questions about clues in its knowledge
list — if asked about something outside its knowledge, it says so in character.

Design (from CLAUDE.md):
- NPC sees own persona + own knowledge boundary only.
- Cannot see other NPCs' knowledge or any character's secret_bio.
- VisibilityRegistry is enforced at the orchestrator level (orchestrator passes
  only the relevant clue content into this agent's prompt).
"""

from __future__ import annotations

import logging

from app.llm import chat, strip_think
from app.models import NPC, ScriptClue

logger = logging.getLogger(__name__)

_NPC_FALLBACK = "这个……我不太清楚，恕我无法回答。"

# Speech style descriptions injected into the system prompt
_SPEECH_STYLES: dict[str, str] = {
    "formal_elderly": (
        "你说话语气礼貌、沉稳，偶尔带着老一辈人的措辞习惯，"
        "不轻易主动透露信息，但被直接追问时会如实作答。"
    ),
    "curt_official": (
        "你说话简洁直接，具有刑警的职业风格，不喜欢绕弯子，"
        "对合理的推断会给出明确的肯定或否定，对尚未查明的事项会说「等待进一步核查」。"
    ),
}

_DEFAULT_STYLE = "你说话自然，用中文回答。"


class NPCAgent:
    """In-character NPC responder.  One instance per NPC per game session.

    Parameters
    ----------
    npc : NPC
        The NPC model (name, persona, knowledge list, speech_style).
    clues_by_id : dict[str, ScriptClue]
        Full clue index.  Only clues in npc.knowledge are injected into the prompt.
    """

    def __init__(self, npc: NPC, clues_by_id: dict[str, ScriptClue]) -> None:
        self._npc = npc
        self._knowledge_clues: list[ScriptClue] = [
            clues_by_id[cid] for cid in npc.knowledge if cid in clues_by_id
        ]
        self._system_prompt = self._build_system_prompt()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def respond(self, player_message: str) -> str:
        """Generate an in-character response to *player_message*."""
        messages = [{"role": "user", "content": player_message}]
        try:
            raw = await chat(self._system_prompt, messages)
            text = strip_think(raw).strip()
            return text if text else _NPC_FALLBACK
        except Exception as exc:
            logger.exception("NPCAgent.respond failed for %s: %s", self._npc.name, exc)
            return _NPC_FALLBACK

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        style_desc = _SPEECH_STYLES.get(self._npc.speech_style, _DEFAULT_STYLE)

        if self._knowledge_clues:
            clue_lines = "\n".join(
                f"- 【{c.title}】{c.content}" for c in self._knowledge_clues
            )
            knowledge_block = f"\n## 你掌握的案件信息\n{clue_lines}"
        else:
            knowledge_block = "\n## 你掌握的案件信息\n（你对案件细节所知甚少）"

        return (
            f"你是「{self._npc.name}」，一个正在参与推理游戏的NPC角色，你必须完全保持角色扮演。\n\n"
            f"## 你的角色背景\n{self._npc.persona}\n\n"
            f"## 你的说话风格\n{style_desc}\n"
            f"{knowledge_block}\n\n"
            "## 行为准则\n"
            "- 始终用第一人称，保持角色，用中文回答，每次回复不超过80字\n"
            "- 只谈论你知道的信息范围内的事，对不知道的事用角色方式表达不知\n"
            "- 不要主动过度透露，被直接追问时才给出具体信息\n"
            "- 不要破坏角色扮演，不要承认自己是AI或NPC"
        )
