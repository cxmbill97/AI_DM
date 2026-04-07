"""PuzzleParserAgent — parse uploaded text into a Puzzle using the LLM.

Single-shot parse with up to 2 correction retries on Pydantic validation failure.
Analogous to DocumentParserAgent but targets the simpler Puzzle schema.
"""

from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError

from app.llm import chat
from app.models import Puzzle

logger = logging.getLogger(__name__)

_SCHEMA_COMMENT_ZH = """\
输出一个严格符合以下 JSON schema 的对象（不含注释）:
{
  "id": "<puzzle_id 参数原样填入>",
  "title": "谜题标题（简短，不超过20字）",
  "surface": "汤面：呈现给玩家的神秘场景，不包含答案，100-300字",
  "truth": "汤底：完整真相解释，包含所有关键细节，100-500字",
  "key_facts": [
    "用于匹配玩家提问的独立事实条目（每条15字以内）",
    "每个关键事实独立成条，不要提及凶手/凶器（如适用）直到玩家推断出来"
  ],
  "hints": [
    "第一级提示（最轻微）",
    "第二级提示（稍明显）",
    "第三级提示（较明显，但仍不泄露答案）"
  ],
  "clues": [
    {
      "id": "clue_001",
      "title": "线索名称",
      "content": "线索内容（揭露真相的一个方面，不直接给出答案）",
      "unlock_keywords": ["关键词1", "关键词2", "关键词3"]
    }
  ],
  "private_clues": {},
  "difficulty": "简单 | 中等 | 困难",
  "tags": ["标签1", "标签2"]
}

解析规则：
1. surface 必须是悬疑的场景描述，不能包含答案
2. truth 必须完整解释所有谜团
3. key_facts 每条是独立的事实，用于判断玩家的提问是否正确，不要列举 surface 里已经明显给出的事实
4. hints 按从轻到重排列，不少于2条，不超过5条
5. clues 每条线索揭示真相的一个片段，unlock_keywords 是2-4个自然语言词组
6. tags 从 ["悬疑", "推理", "心理", "科学", "历史", "生活", "恐怖", "温情", "社会"] 中选择
7. 如果原文没有提供足够信息，根据原文内容合理推断补全"""

_SCHEMA_COMMENT_EN = """\
Output a JSON object strictly matching this schema (no comments):
{
  "id": "<use the puzzle_id parameter as-is>",
  "title": "Puzzle title (short, ≤20 chars)",
  "surface": "The scenario shown to players — mysterious, no answer, 100-300 words",
  "truth": "Full truth explanation with all key details, 100-500 words",
  "key_facts": [
    "Independent fact used to evaluate player questions (≤20 words each)",
    "Each fact is standalone; do not name culprit/method until player deduces it"
  ],
  "hints": [
    "Hint level 1 (subtle)",
    "Hint level 2 (clearer)",
    "Hint level 3 (more explicit, but no direct answer)"
  ],
  "clues": [
    {
      "id": "clue_001",
      "title": "Clue name",
      "content": "Clue content (reveals one aspect of the truth without giving it away)",
      "unlock_keywords": ["keyword1", "keyword2", "keyword3"]
    }
  ],
  "private_clues": {},
  "difficulty": "beginner | intermediate | hard",
  "tags": ["mystery", "logic", "science", "psychology", "history", "crime"]
}

Rules:
1. surface must be suspenseful — never reveal the answer
2. truth must fully explain all mysteries
3. key_facts: each is one atomic fact for evaluating player guesses; don't repeat obvious surface info
4. hints: 2-5 hints, from subtle to more explicit, never giving the answer outright
5. clues: each reveals one truth fragment; unlock_keywords are 2-4 natural-language terms
6. If the source text lacks details, infer and fill in plausibly based on what is there"""

_SYSTEM_ZH = f"""\
你是一个海龟汤（Turtle Soup/汤面汤底）谜题解析引擎。
从用户提供的原始文本中提取或推断谜题结构，输出完整 JSON。

{_SCHEMA_COMMENT_ZH}

只输出 JSON，不要任何额外文字、markdown 代码块或注释。"""

_SYSTEM_EN = f"""\
You are a Turtle Soup lateral-thinking puzzle parser.
Extract or infer the puzzle structure from the raw text and output complete JSON.

{_SCHEMA_COMMENT_EN}

Output ONLY the JSON object — no markdown fences, no extra text."""

_CORRECTION_ZH = """\
上面的 JSON 未能通过 Pydantic 验证，错误如下：

{error}

请修正所有错误并重新输出完整的 JSON 对象（不含注释或代码块）。
之前的 JSON：
{prev_json}"""

_CORRECTION_EN = """\
The JSON above failed Pydantic validation with these errors:

{error}

Fix all errors and output the complete corrected JSON object (no fences, no commentary).
Previous JSON:
{prev_json}"""


class PuzzleParseError(Exception):
    def __init__(self, message: str, last_json: str | None = None) -> None:
        super().__init__(message)
        self.last_json = last_json


class PuzzleParserAgent:
    MAX_RETRIES = 2

    def __init__(self, language: str = "zh") -> None:
        self._language = language
        self._system = _SYSTEM_ZH if language == "zh" else _SYSTEM_EN

    async def parse(self, raw_text: str, puzzle_id: str) -> Puzzle:
        """Parse *raw_text* into a validated Puzzle. Raises PuzzleParseError on failure."""
        text, _ = self._truncate_text(raw_text)
        user_msg = self._build_user_message(text, puzzle_id)
        messages: list[dict] = [{"role": "user", "content": user_msg}]

        last_json = ""
        for attempt in range(self.MAX_RETRIES + 1):
            raw = await chat(self._system, messages)
            last_json = self._extract_json(raw)
            try:
                data = json.loads(last_json)
                data["id"] = puzzle_id  # enforce correct id
                return Puzzle.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as exc:
                if attempt == self.MAX_RETRIES:
                    raise PuzzleParseError(str(exc), last_json) from exc
                err_msg = str(exc)[:2000]
                tmpl = _CORRECTION_ZH if self._language == "zh" else _CORRECTION_EN
                correction = tmpl.format(error=err_msg, prev_json=last_json[:3000])
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": correction})
                logger.warning("PuzzleParserAgent attempt %d failed: %s", attempt + 1, err_msg[:200])

        raise PuzzleParseError("Max retries exceeded", last_json)  # unreachable

    @staticmethod
    def _truncate_text(text: str, max_chars: int = 24_000) -> tuple[str, bool]:
        if len(text) <= max_chars:
            return text, False
        return text[:max_chars], True

    @staticmethod
    def _extract_json(raw: str) -> str:
        """Strip <think> tags and markdown fences, return the inner JSON string."""
        # Remove <think>...</think>
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        # Try ```json ... ``` or ``` ... ```
        m = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
        if m:
            return m.group(1).strip()
        # Try first { ... } block
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1:
            return raw[start : end + 1]
        return raw

    def _build_user_message(self, text: str, puzzle_id: str) -> str:
        if self._language == "zh":
            return f"puzzle_id: {puzzle_id}\n\n原始文本：\n{text}"
        return f"puzzle_id: {puzzle_id}\n\nRaw text:\n{text}"
