"""DM Intervention Engine — proactive speaking during multiplayer discussion.

Decides *when* the DM should speak without being asked:
- Silence timer (45s / 90s / 180s with exponential backoff)
- Explicit player request (@DM / "给我个提示" / "帮")

Only used in multiplayer rooms (ws.py manages the background tick task).
Single-player mode (main.py REST) never touches this module.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
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

# Keywords that indicate a player is explicitly addressing the DM
_EXPLICIT_KEYWORDS = ("提示", "帮我", "给我", "告诉我")


# ---------------------------------------------------------------------------
# Trigger dataclass
# ---------------------------------------------------------------------------


@dataclass
class InterventionTrigger:
    type: str  # "explicit" | "silence"
    level: str = "gentle"  # "gentle" | "nudge" | "hint"
    player_id: str | None = None


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
        self.last_dm_time: float = 0.0          # epoch of most recent DM broadcast
        self.silence_start: float = time.time()  # when the last player message arrived
        self.silence_nudge_count: int = 0        # how many silence nudges sent; drives backoff
        self.global_cooldown: float = 15.0       # minimum seconds between any DM messages

    # ------------------------------------------------------------------
    # Public interface called by ws.py
    # ------------------------------------------------------------------

    def on_player_message(self, player_id: str, text: str) -> InterventionTrigger | None:
        """Called on every player chat message.

        Resets the silence timer, then checks whether this message is an
        explicit request directed at the DM.
        Returns a trigger if the player explicitly addressed the DM,
        otherwise None (the normal dm_turn call handles the response).
        """
        self.silence_start = time.time()
        self.silence_nudge_count = 0
        return self._evaluate_explicit(player_id, text)

    def on_tick(self) -> InterventionTrigger | None:
        """Called every 5 s by the background task.

        Returns a silence trigger when players have been quiet long enough
        AND the global cooldown has elapsed.  Returns None otherwise.
        """
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
        # Increment nudge count up to cap so backoff grows after each nudge
        if self.silence_nudge_count < 4:
            self.silence_nudge_count += 1

    def random_gentle_message(self) -> str:
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
        """Map elapsed seconds to escalation level."""
        if elapsed < 90:
            return "gentle"
        if elapsed < 180:
            return "nudge"
        return "hint"

    def _evaluate_explicit(
        self, player_id: str, text: str
    ) -> InterventionTrigger | None:
        """Tier-1 fast rules — no LLM call.

        Detect when a player is explicitly addressing the DM so the DM can
        respond with higher priority.  The actual response is still generated
        by the normal dm_turn call in ws.py; this trigger is informational.
        """
        text_lower = text.lower()
        # Unambiguous DM address
        if "@dm" in text_lower:
            return InterventionTrigger(
                type="explicit", level="nudge", player_id=player_id
            )
        # "给我个提示" / "帮我" / "告诉我" — direct help requests
        if any(kw in text for kw in _EXPLICIT_KEYWORDS):
            return InterventionTrigger(
                type="explicit", level="nudge", player_id=player_id
            )
        return None
