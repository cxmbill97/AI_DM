"""Agent trace — lightweight decision log for the multi-agent pipeline.

One AgentTrace is produced per player message.  Each agent invocation in the
pipeline (Router → Judge → Narrator → Safety, or NPC branch) appends one
TraceStep.  The trace is returned alongside OrchestratorResponse so callers
can log, surface, or discard it without affecting game logic.

Sanitisation rules for input_summary (no secrets):
  - Router:   full message + phase (the message is already public player input)
  - Judge:    fact *counts* only — never the fact text itself
  - Narrator: judgment value + clue/fact counts
  - Safety:   char count of text being checked + fact count
  - NPC:      NPC name + knowledge clue count
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Pricing constants (USD per 1 M tokens, MiniMax M2.5)
# ---------------------------------------------------------------------------

PRICING_USD_PER_MTOK: dict[str, float] = {
    "input": 0.20,
    "output": 1.15,
}


# ---------------------------------------------------------------------------
# Core dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TraceStep:
    """A single agent invocation within the pipeline."""

    agent: str           # "router" | "judge" | "narrator" | "safety" | "npc"
    input_summary: str   # sanitised — no secret content
    output_summary: str  # sanitised output description
    latency_ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentTrace:
    """Complete decision log for one player message."""

    message_id: str
    player_id: str
    player_message: str
    timestamp: float
    steps: list[TraceStep] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def total_latency_ms(self) -> float:
        return sum(s.latency_ms for s in self.steps)

    @property
    def total_tokens(self) -> int:
        return sum(s.tokens_in + s.tokens_out for s in self.steps)

    @property
    def total_cost_usd(self) -> float:
        tokens_in = sum(s.tokens_in for s in self.steps)
        tokens_out = sum(s.tokens_out for s in self.steps)
        return (
            tokens_in * PRICING_USD_PER_MTOK["input"]
            + tokens_out * PRICING_USD_PER_MTOK["output"]
        ) / 1_000_000

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for JSON broadcast."""
        return {
            "message_id": self.message_id,
            "player_id": self.player_id,
            "player_message": self.player_message,
            "timestamp": self.timestamp,
            "total_latency_ms": round(self.total_latency_ms, 2),
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "steps": [
                {
                    "agent": s.agent,
                    "input_summary": s.input_summary,
                    "output_summary": s.output_summary,
                    "latency_ms": round(s.latency_ms, 2),
                    "tokens_in": s.tokens_in,
                    "tokens_out": s.tokens_out,
                    "metadata": s.metadata,
                }
                for s in self.steps
            ],
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def new_trace(player_id: str, player_message: str) -> AgentTrace:
    """Create a fresh AgentTrace for one player message."""
    return AgentTrace(
        message_id=str(uuid.uuid4()),
        player_id=player_id,
        player_message=player_message,
        timestamp=time.time(),
    )
