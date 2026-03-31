"""DM Intervention Engine — proactive speaking during multiplayer discussion.

Decides *when* the DM should speak without being asked:
- Silence timer (45s / 90s / 180s with exponential backoff)
- Explicit player request (@DM / "给我个提示" / "帮")

Phase-aware behaviour (murder mystery):
  - "opening" / "reading" : no interventions
  - "investigation"       : clue-reminder canned messages; full silence backoff
  - "discussion"          : full intervention (silence, imbalance, nudge)
  - "voting"              : only a "请尽快投票" reminder when timeout is near
  - "reveal"              : no interventions

Only used in multiplayer rooms (ws.py manages the background tick task).
Single-player mode (main.py REST) never touches this module.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.room import Room

# ---------------------------------------------------------------------------
# Canned gentle messages (no LLM call — zero cost)
# ---------------------------------------------------------------------------

_GENTLE_MESSAGES = [
    "大家有什么想法吗？",
    "这个问题可以从另一个角度想想~",
    "别忘了已经发现的线索哦",
    "有没有什么细节被忽略了？",
    "大家慢慢想，不着急~",
    "思路卡住了？换个方向试试",
]

_INVESTIGATION_MESSAGES = [
    "还有线索没有发现哦，试试搜查关键地点或物品。",
    "可以向NPC提问，他们也许知道一些重要信息。",
    "不同的玩家可以分工搜查不同区域。",
    "别忘了观察现场细节，每一个线索都可能是关键。",
]

_VOTE_REMINDER = "投票时间快到了，请大家尽快做出判断，发送投票消息！"

# Keywords that indicate a player is explicitly addressing the DM
_EXPLICIT_KEYWORDS = ("提示", "帮我", "给我", "告诉我")

# Phases where no intervention should occur
_SILENT_PHASES = frozenset({"opening", "reading", "reveal"})


# ---------------------------------------------------------------------------
# Trigger dataclass
# ---------------------------------------------------------------------------


@dataclass
class InterventionTrigger:
    type: str  # "explicit" | "silence" | "vote_reminder"
    level: str = "gentle"  # "gentle" | "nudge" | "hint"
    player_id: str | None = None
    canned_text: str | None = None  # pre-built text for vote reminders


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class InterventionEngine:
    """Per-room intervention state machine.

    Instantiated once per Room and kept alive for the room's lifetime.
    The background tick loop (in ws.py) calls on_tick() every 5 seconds.
    Every player chat message calls on_player_message().
    """

    def __init__(self, room: "Room") -> None:
        self.room = room
        self.last_dm_time: float = 0.0
        self.silence_start: float = time.time()
        self.silence_nudge_count: int = 0
        self.global_cooldown: float = 15.0

    # ------------------------------------------------------------------
    # Public interface called by ws.py
    # ------------------------------------------------------------------

    def on_player_message(self, player_id: str, text: str) -> InterventionTrigger | None:
        """Called on every player chat message.

        Resets the silence timer, then checks whether this message is an
        explicit request directed at the DM.
        """
        self.silence_start = time.time()
        self.silence_nudge_count = 0
        return self._evaluate_explicit(player_id, text)

    def on_tick(self, phase: str | None = None) -> InterventionTrigger | None:
        """Called every 5 s by the background task.

        Parameters
        ----------
        phase : str | None
            Current phase id for murder mystery rooms, or None for turtle soup.
            When provided, phase-specific intervention logic applies.
        """
        # Phases with no interventions at all
        if phase in _SILENT_PHASES:
            return None

        # Voting phase: only a late-timeout reminder, no silence backoff
        if phase == "voting":
            return self._check_vote_reminder()

        # Investigation and discussion: full silence backoff
        elapsed = time.time() - self.silence_start
        if elapsed < self.silence_threshold():
            return None
        if not self.cooldown_ok():
            return None
        return InterventionTrigger(
            type="silence",
            level=self.silence_level(elapsed),
        )

    def record_dm_spoke(self) -> None:
        """Call after every DM broadcast (response or intervention)."""
        self.last_dm_time = time.time()
        if self.silence_nudge_count < 4:
            self.silence_nudge_count += 1

    def random_gentle_message(self, phase: str | None = None) -> str:
        """Return a canned gentle message, phase-aware for murder mystery."""
        if phase == "investigation":
            return random.choice(_INVESTIGATION_MESSAGES)
        return random.choice(_GENTLE_MESSAGES)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def cooldown_ok(self) -> bool:
        return (time.time() - self.last_dm_time) >= self.global_cooldown

    def silence_threshold(self) -> float:
        """Exponential backoff: 45 s → 90 s → 180 s → 240 s cap."""
        base = 45.0
        return min(base * (2 ** self.silence_nudge_count), 240.0)

    def silence_level(self, elapsed: float) -> str:
        if elapsed < 90:
            return "gentle"
        if elapsed < 180:
            return "nudge"
        return "hint"

    def _check_vote_reminder(self) -> InterventionTrigger | None:
        """Return a vote reminder trigger if cooldown allows."""
        if not self.cooldown_ok():
            return None
        return InterventionTrigger(
            type="vote_reminder",
            level="gentle",
            canned_text=_VOTE_REMINDER,
        )

    def _evaluate_explicit(
        self, player_id: str, text: str
    ) -> InterventionTrigger | None:
        """Tier-1 fast rules — no LLM call."""
        text_lower = text.lower()
        if "@dm" in text_lower:
            return InterventionTrigger(type="explicit", level="nudge", player_id=player_id)
        if any(kw in text for kw in _EXPLICIT_KEYWORDS):
            return InterventionTrigger(type="explicit", level="nudge", player_id=player_id)
        return None
