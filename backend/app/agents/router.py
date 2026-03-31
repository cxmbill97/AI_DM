"""RouterAgent — pure rules-based intent classifier.

Design constraints (from CLAUDE.md):
- NO LLM call. Must be <1ms.
- Classifies message text + current phase into a typed Intent.
- Only sees the raw message string — no game context, no truth.

Intent priority order (first match wins):
  1. vote    — explicit /vote command or 我投
  2. npc     — @mention or NPC name detected
  3. accuse  — accusation framing (凶手是/我认为/我判断)
  4. question — interrogative markers (? 吗 呢 什么 为什么 是不是 …)
  5. search  — investigation actions (搜 查 看 检查 调查)
  6. meta    — game-help keywords (规则 怎么玩 帮助 help)
  7. chat    — default (player-to-player, orchestrator broadcasts with no DM reply)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Intent = str  # one of the literals below — kept as str for easy JSON serialisation
INTENTS = frozenset({"vote", "npc", "accuse", "question", "search", "meta", "chat"})


@dataclass(frozen=True)
class Classification:
    """Result of RouterAgent.classify()."""

    intent: Intent
    raw_message: str
    matched_rule: str  # human-readable label for logging/testing


# ---------------------------------------------------------------------------
# Pattern constants
# ---------------------------------------------------------------------------

# Vote: /vote … OR 我投 … OR 投票给 …
_RE_VOTE = re.compile(r"^/vote\b|^我投\b|投票给", re.IGNORECASE)

# Accusation: confident culprit statement (not a question)
_RE_ACCUSE = re.compile(
    r"凶手是|我认为.*是凶手|我判断.*是凶手|一定是.*杀|肯定是.*杀|就是.*干的"
)

# Interrogative question markers
_RE_QUESTION = re.compile(r"\?|？|吗|呢|什么|为什么|怎么|是不是|有没有|能不能|是否")

# Investigation / search actions
_RE_SEARCH = re.compile(r"搜|查|看|检查|调查|找|翻|搜索|搜查")

# Meta / help request
_RE_META = re.compile(r"规则|怎么玩|帮助|help|怎么用|流程|说明|指引", re.IGNORECASE)


# ---------------------------------------------------------------------------
# RouterAgent
# ---------------------------------------------------------------------------


class RouterAgent:
    """Pure rules-based intent classifier.  Instantiate once per room/session.

    Parameters
    ----------
    npc_names : list[str]
        Display names of NPCs in the current script (e.g. ["管家老周", "李探长"]).
        Used to detect @NPC mentions and direct-name queries.
    """

    def __init__(self, npc_names: list[str] | None = None) -> None:
        self._npc_names: list[str] = npc_names or []
        # Build a compiled pattern for NPC detection if names are provided
        if self._npc_names:
            pattern_parts = [re.escape(name) for name in self._npc_names]
            # Also match @<anything> as NPC prefix
            pattern_parts.append(r"@\S+")
            self._re_npc: re.Pattern | None = re.compile("|".join(pattern_parts))
        else:
            self._re_npc = re.compile(r"@\S+")  # fallback: @mentions only

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, message: str, current_phase: str) -> Classification:  # noqa: ARG002
        """Classify *message* into an Intent.

        *current_phase* is accepted for future phase-specific overrides (e.g.
        force "vote" intent during voting phase) but is not used in the base
        implementation — the orchestrator enforces phase guards separately.
        """
        text = message.strip()

        # 1. Vote
        if _RE_VOTE.search(text):
            return Classification(intent="vote", raw_message=message, matched_rule="vote_pattern")

        # 2. NPC — @mention or NPC name in message
        if self._re_npc and self._re_npc.search(text):
            return Classification(intent="npc", raw_message=message, matched_rule="npc_mention")

        # 3. Accuse — confident culprit statement (check before question to catch
        #    "凶手是X吗" as accuse, not question — accusation framing takes priority)
        if _RE_ACCUSE.search(text):
            return Classification(intent="accuse", raw_message=message, matched_rule="accuse_pattern")

        # 4. Question — interrogative markers
        if _RE_QUESTION.search(text):
            return Classification(intent="question", raw_message=message, matched_rule="question_marker")

        # 5. Search / investigation action
        if _RE_SEARCH.search(text):
            return Classification(intent="search", raw_message=message, matched_rule="search_keyword")

        # 6. Meta / help
        if _RE_META.search(text):
            return Classification(intent="meta", raw_message=message, matched_rule="meta_keyword")

        # 7. Default → player-to-player chat (no DM response)
        return Classification(intent="chat", raw_message=message, matched_rule="default_chat")
