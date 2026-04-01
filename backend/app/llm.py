"""MiniMax LLM client via the OpenAI-compatible SDK."""

from __future__ import annotations

import json
import logging
import re
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from openai import AsyncOpenAI

from app.config import settings

MODEL = "MiniMax-M2.5"
MINIMAX_BASE_URL = "https://api.minimax.io/v1"


# ---------------------------------------------------------------------------
# Token usage tracking — ContextVar accumulator (no agent-code changes needed)
# ---------------------------------------------------------------------------


@dataclass
class Usage:
    prompt_tokens: int
    completion_tokens: int


# When set to a list, each chat() call appends a Usage record to it.
# None (default) = tracking disabled.
_usage_accumulator: ContextVar[list[Usage] | None] = ContextVar(
    "_usage_accumulator", default=None
)


def reset_usage_accumulator() -> None:
    """Start a new usage-tracking scope in the current async context.

    Call this before invoking an agent method; then call drain_usage() after
    the await returns to retrieve (and clear) all Usage records the call made.
    """
    _usage_accumulator.set([])


def drain_usage() -> list[Usage]:
    """Return accumulated Usage records and clear the list.

    Returns an empty list if the accumulator was never reset.
    """
    acc = _usage_accumulator.get(None)
    if acc is None:
        return []
    result = list(acc)
    acc.clear()
    return result

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

_llm_logger = logging.getLogger("llm")
if not _llm_logger.handlers:
    import sys
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(asctime)s [LLM] %(message)s", datefmt="%H:%M:%S"))
    _llm_logger.addHandler(_h)
    _llm_logger.setLevel(logging.INFO)
    _llm_logger.propagate = False


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

    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    _llm_logger.info(
        "LLM call → model=%s  prompt=%r",
        MODEL, last_user[:120],
    )

    t0 = time.time()
    response = await client.chat.completions.create(
        model=MODEL,
        messages=full_messages,  # type: ignore[arg-type]
    )
    elapsed = (time.time() - t0) * 1000
    raw = response.choices[0].message.content or ""

    tok_in = response.usage.prompt_tokens if response.usage else 0
    tok_out = response.usage.completion_tokens if response.usage else 0
    _llm_logger.info(
        "LLM resp  ← %.0fms  in=%d out=%d  reply=%r",
        elapsed, tok_in, tok_out, strip_think(raw)[:120],
    )

    # Append usage to the active accumulator (if one is set)
    if response.usage is not None:
        acc = _usage_accumulator.get(None)
        if acc is not None:
            acc.append(
                Usage(
                    prompt_tokens=tok_in,
                    completion_tokens=tok_out,
                )
            )
    _log_call(system_prompt, messages, raw)
    return raw
