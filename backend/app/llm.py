"""MiniMax LLM client via the OpenAI-compatible SDK."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from openai import AsyncOpenAI

from app.config import settings

MODEL = "MiniMax-M2.5"
MINIMAX_BASE_URL = "https://api.minimax.io/v1"

# ---------------------------------------------------------------------------
# LLM call logger — writes one JSON-lines file per day to logs/llm/
# ---------------------------------------------------------------------------

_LOG_DIR = Path(__file__).parent.parent / "logs" / "llm"


def _get_llm_logger() -> logging.Logger:
    """Return a logger that appends JSON records to logs/llm/YYYY-MM-DD.jsonl."""
    logger = logging.getLogger("llm_calls")
    if logger.handlers:
        return logger  # already configured

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = _LOG_DIR / f"{datetime.now():%Y-%m-%d}.jsonl"

    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger


def _log_call(system_prompt: str, messages: list[dict], raw_response: str) -> None:
    """Append one JSON-lines record with the full input/output for this LLM call."""
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "model": MODEL,
        "system_prompt": system_prompt,
        "messages": messages,
        "raw_response": raw_response,
    }
    _get_llm_logger().debug(json.dumps(record, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=MINIMAX_BASE_URL,
            api_key=settings.minimax_api_key,
        )
    return _client


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def strip_think(text: str) -> str:
    """Remove <think>…</think> reasoning blocks from LLM output.

    The raw text (with tags intact) should be kept in conversation history
    for multi-turn reasoning quality; use this function only before display
    or parsing.
    """
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


# ---------------------------------------------------------------------------
# Main call
# ---------------------------------------------------------------------------


async def chat(system_prompt: str, messages: list[dict]) -> str:
    """Call MiniMax and return the **raw** response string.

    The raw string may contain <think>…</think> blocks.
    Callers must:
    - Store the raw string in conversation history (preserves reasoning).
    - Call strip_think() before parsing JSON or displaying to the user.

    Every call is logged to logs/llm/YYYY-MM-DD.jsonl for prompt tuning.
    """
    client = _get_client()
    full_messages: list[dict] = [{"role": "system", "content": system_prompt}] + messages
    response = await client.chat.completions.create(
        model=MODEL,
        messages=full_messages,  # type: ignore[arg-type]
    )
    raw = response.choices[0].message.content or ""
    _log_call(system_prompt, messages, raw)
    return raw
