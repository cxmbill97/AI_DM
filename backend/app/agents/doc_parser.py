"""DocumentParserAgent — converts raw document text into a validated Script.

LLM strategy: single-shot structured extraction with up to MAX_RETRIES
correction passes when Pydantic validation fails.  Follows the same
agent pattern as judge.py / narrator.py — no global state.
"""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from app.llm import chat, strip_think
from app.models import Script

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ScriptParseError(Exception):
    """Raised when the LLM cannot produce a valid Script after all retries."""

    def __init__(self, message: str, last_json: str | None = None) -> None:
        super().__init__(message)
        self.last_json = last_json


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

_SCHEMA_ZH = """
{
  "id": "<由调用方提供，直接使用，不要修改>",
  "title": "<剧本标题>",
  "game_mode": "whodunit",
  "metadata": {
    "player_count": <整数>,
    "duration_minutes": <整数，若原文未说明则按人数估算：3人=40，4-5人=60，6人=90>,
    "difficulty": "beginner|intermediate|advanced",
    "age_rating": "12+"
  },
  "characters": [
    {
      "id": "char_<简短英文标识，如char_wang>",
      "name": "<角色全名>",
      "public_bio": "<公开简介，不含任何秘密，100字以内>",
      "secret_bio": "<完整秘密背景，包含该角色的隐藏信息、秘密动机>",
      "is_culprit": false
    }
  ],
  "phases": [
    {"id": "opening", "type": "narration", "next": "reading", "duration_seconds": 120,
     "allowed_actions": ["listen"], "dm_script": "<开场白>", "available_clues": null, "per_player_content": null},
    {"id": "reading", "type": "reading", "next": "investigation_1", "duration_seconds": 360,
     "allowed_actions": ["read_script"], "dm_script": null, "available_clues": null,
     "per_player_content": {"<char_id>": "<该角色完整个人剧本>"}},
    {"id": "investigation_1", "type": "investigation", "next": "discussion", "duration_seconds": 600,
     "allowed_actions": ["question", "search", "npc"], "dm_script": null,
     "available_clues": ["<clue_id_1>", "..."], "per_player_content": null},
    {"id": "discussion", "type": "discussion", "next": "voting", "duration_seconds": 300,
     "allowed_actions": ["question", "accuse"], "dm_script": null, "available_clues": null, "per_player_content": null},
    {"id": "voting", "type": "voting", "next": "reveal", "duration_seconds": 120,
     "allowed_actions": ["vote"], "dm_script": null, "available_clues": null, "per_player_content": null},
    {"id": "reveal", "type": "reveal", "next": null, "duration_seconds": null,
     "allowed_actions": [], "dm_script": "<真相揭晓>", "available_clues": null, "per_player_content": null}
  ],
  "clues": [
    {
      "id": "clue_<序号>",
      "title": "<线索名称>",
      "content": "<线索详细内容>",
      "phase_available": "investigation_1",
      "visibility": "public",
      "unlock_keywords": ["<关键词1>", "<关键词2>"]
    }
  ],
  "npcs": [],
  "truth": {
    "culprit": "<凶手角色的char_id>",
    "motive": "<作案动机>",
    "method": "<作案手法>",
    "timeline": "<事件时间线>",
    "key_facts": [
      "<独立事实，不命名凶手，用被动语态或模糊主语，至少6条>"
    ],
    "full_story": "",
    "cause_of_death": "<死因>"
  },
  "theme": {
    "primary_color": "<主色调十六进制颜色，如 #8b1a1a（血红）、#1a3a5c（深海蓝）、#2d4a1e（深林绿）>",
    "bg_tone": "<氛围基调，选择一个：dark | warm | eerie | cold | natural>",
    "era": "<时代背景，如 modern、Victorian、ancient_china、sci-fi、民国>",
    "setting": "<场景，如 manor、city_apartment、countryside、spaceship>",
    "dm_persona": "<DM角色风格，10-20字中文描述，如「冷静克制的侦探」、「神秘古雅的说书人」>"
  }
}"""

_SCHEMA_EN = """
{
  "id": "<provided by caller, use as-is>",
  "title": "<script title>",
  "game_mode": "whodunit",
  "metadata": {
    "player_count": <integer>,
    "duration_minutes": <integer, infer from player count if not stated: 3=40, 4-5=60, 6=90>,
    "difficulty": "beginner|intermediate|advanced",
    "age_rating": "12+"
  },
  "characters": [
    {
      "id": "char_<short_english_slug>",
      "name": "<character full name>",
      "public_bio": "<public bio, no secrets, under 100 words>",
      "secret_bio": "<full secret background, hidden motives, private information>",
      "is_culprit": false
    }
  ],
  "phases": [
    {"id": "opening", "type": "narration", "next": "reading", "duration_seconds": 120,
     "allowed_actions": ["listen"], "dm_script": "<opening narration>", "available_clues": null, "per_player_content": null},
    {"id": "reading", "type": "reading", "next": "investigation_1", "duration_seconds": 360,
     "allowed_actions": ["read_script"], "dm_script": null, "available_clues": null,
     "per_player_content": {"<char_id>": "<full role script for this character>"}},
    {"id": "investigation_1", "type": "investigation", "next": "discussion", "duration_seconds": 600,
     "allowed_actions": ["question", "search", "npc"], "dm_script": null,
     "available_clues": ["<clue_id_1>", "..."], "per_player_content": null},
    {"id": "discussion", "type": "discussion", "next": "voting", "duration_seconds": 300,
     "allowed_actions": ["question", "accuse"], "dm_script": null, "available_clues": null, "per_player_content": null},
    {"id": "voting", "type": "voting", "next": "reveal", "duration_seconds": 120,
     "allowed_actions": ["vote"], "dm_script": null, "available_clues": null, "per_player_content": null},
    {"id": "reveal", "type": "reveal", "next": null, "duration_seconds": null,
     "allowed_actions": [], "dm_script": "<truth reveal narration>", "available_clues": null, "per_player_content": null}
  ],
  "clues": [
    {
      "id": "clue_<number>",
      "title": "<clue name>",
      "content": "<clue detailed content>",
      "phase_available": "investigation_1",
      "visibility": "public",
      "unlock_keywords": ["<keyword1>", "<keyword2>"]
    }
  ],
  "npcs": [],
  "truth": {
    "culprit": "<culprit character's char_id>",
    "motive": "<motive>",
    "method": "<method>",
    "timeline": "<timeline of events>",
    "key_facts": [
      "<independent fact, do NOT name the culprit, use passive voice, at least 6 facts>"
    ],
    "full_story": "",
    "cause_of_death": "<cause of death>"
  },
  "theme": {
    "primary_color": "<hex color for the script's dominant tone, e.g. #8b1a1a (crimson), #1a3a5c (deep blue)>",
    "bg_tone": "<one of: dark | warm | eerie | cold | natural>",
    "era": "<time period, e.g. modern, Victorian, ancient_china, sci-fi, 1930s>",
    "setting": "<location type, e.g. manor, city_apartment, countryside, spaceship>",
    "dm_persona": "<DM voice style in 5-10 words, e.g. 'calm and clinical detective', 'theatrical Victorian storyteller'>"
  }
}"""

_SYSTEM_ZH = f"""你是剧本杀脚本解析引擎。将用户提供的剧本原文解析成以下JSON Schema的结构化数据。
只输出合法的JSON对象，不要任何解释文字。

## 输出JSON Schema

```json
{_SCHEMA_ZH}
```

## 解析规则
1. public_bio 不得包含 secret_bio 中的任何秘密信息。
2. key_facts 中每条都不得命名谁是凶手（用被动语态或模糊主语）。
3. 若原剧本无明确NPC角色，npcs 保持空数组 []。
4. unlock_keywords 提供 2-4 个玩家可能用来询问该线索的中文关键词。
5. 若剧本是还原/重建模式，game_mode 设为 "reconstruction"，culprit 为空字符串 ""，full_story 填写完整故事。
6. phases 列表必须按游戏顺序排列，最后一个 phase 的 next 为 null。
7. theme.primary_color 选择与故事氛围最匹配的颜色；theme.dm_persona 用10字内的中文描述DM的叙事风格。"""

_SYSTEM_EN = f"""You are a murder mystery script parsing engine. Convert the document text into a valid JSON object matching the schema below.
Output ONLY the JSON object — no explanation, no markdown wrapper.

## Output JSON Schema

```json
{_SCHEMA_EN}
```

## Parsing Rules
1. public_bio must NOT contain any information from secret_bio.
2. Each key_facts entry must NOT name the culprit — use passive voice or ambiguous subject.
3. If the script has no explicit NPC characters, set npcs to an empty array [].
4. unlock_keywords: provide 2-4 natural-language terms a player might use to ask about this clue.
5. If the script is a reconstruction/timeline-rebuild type, set game_mode to "reconstruction", culprit to "", full_story to the complete story.
6. The phases list must be in game order; the last phase's next must be null.
7. theme.primary_color should reflect the story's dominant mood; theme.dm_persona should be 5-10 words describing the DM narration style."""


class DocumentParserAgent:
    """Converts raw document text into a validated Script object.

    Parameters
    ----------
    language:
        "zh" or "en" — controls prompt language and output expectations.
    """

    MAX_RETRIES = 2

    def __init__(self, language: str = "zh") -> None:
        self._language = language if language in ("zh", "en") else "zh"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def parse(self, raw_text: str, script_id: str) -> Script:
        """Parse *raw_text* into a validated Script.

        Raises
        ------
        ScriptParseError
            If the LLM cannot produce a valid Script after MAX_RETRIES attempts.
        """
        truncated_text, was_truncated = self._truncate_text(raw_text)
        system_prompt = self._build_system_prompt()
        user_msg = self._build_user_message(truncated_text, script_id)

        messages: list[dict] = [{"role": "user", "content": user_msg}]
        last_json: str | None = None

        for attempt in range(self.MAX_RETRIES + 1):
            raw = await chat(system_prompt, messages)
            cleaned = strip_think(raw)

            try:
                last_json = self._extract_json(cleaned)
                data = json.loads(last_json)
                # Ensure the id from the caller is preserved
                data["id"] = script_id
                script = Script.model_validate(data)
                return script
            except (json.JSONDecodeError, ValidationError) as exc:
                if attempt < self.MAX_RETRIES:
                    # Add the assistant response + correction request
                    messages.append({"role": "assistant", "content": raw})
                    messages.append(
                        {
                            "role": "user",
                            "content": self._build_correction_message(str(exc)[:2000], last_json or cleaned),
                        }
                    )
                else:
                    raise ScriptParseError(
                        f"LLM failed to produce a valid Script after {self.MAX_RETRIES} retries: {exc}",
                        last_json=last_json,
                    ) from exc

        # Unreachable but satisfies type checker
        raise ScriptParseError("Parse failed", last_json=last_json)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        return _SYSTEM_EN if self._language == "en" else _SYSTEM_ZH

    def _build_user_message(self, raw_text: str, script_id: str) -> str:
        if self._language == "en":
            return f'Script ID to use: "{script_id}"\n\nDocument text:\n\n{raw_text}'
        return f'剧本ID（直接使用）："{script_id}"\n\n剧本原文：\n\n{raw_text}'

    @staticmethod
    def _extract_json(raw: str) -> str:
        """Extract the first JSON object from *raw*.

        Tries a fenced ```json ... ``` block first, then falls back to
        finding the outermost { ... } span.
        """
        # Fenced block
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if fenced:
            return fenced.group(1)
        # Bare object — find outermost braces
        start = raw.find("{")
        if start == -1:
            return raw
        # Walk to find matching closing brace
        depth = 0
        for i, ch in enumerate(raw[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return raw[start : i + 1]
        return raw[start:]

    @staticmethod
    def _truncate_text(text: str, max_chars: int = 24_000) -> tuple[str, bool]:
        """Truncate *text* to *max_chars*, appending a truncation notice if cut."""
        if len(text) <= max_chars:
            return text, False
        notice = "\n\n[...文档过长，已截断 / Document truncated]"
        return text[:max_chars] + notice, True

    @staticmethod
    def _build_correction_message(error: str, previous_json: str) -> str:
        return f"上一次输出存在以下错误，请修正后重新输出完整JSON（不要任何解释）：\n\n错误信息：\n{error}\n\n上一次输出：\n{previous_json}"
