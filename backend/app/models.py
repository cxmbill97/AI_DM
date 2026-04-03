"""Pydantic models for puzzles, requests, responses, and game state."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Pricing constants (USD per 1 M tokens, MiniMax M2.5)
# ---------------------------------------------------------------------------

PRICING: dict[str, dict[str, float]] = {
    "minimax": {
        "input": 0.20,  # USD per 1 M input tokens
        "output": 1.15,  # USD per 1 M output tokens
    }
}


# ---------------------------------------------------------------------------
# Agent trace models (Pydantic — for JSON serialisation in API responses)
# ---------------------------------------------------------------------------


class TraceStep(BaseModel):
    """One agent invocation within the multi-agent pipeline."""

    agent: str  # "router" | "judge" | "narrator" | "safety" | "npc"
    input_summary: str  # sanitised — no secret content
    output_summary: str
    latency_ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTrace(BaseModel):
    """Complete decision log produced for one player message."""

    message_id: str
    player_id: str
    player_message: str
    timestamp: float
    steps: list[TraceStep] = Field(default_factory=list)
    total_latency_ms: float = 0.0
    total_tokens: int = 0
    total_cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# Puzzle schema (mirrors the JSON files in data/puzzles/)
# ---------------------------------------------------------------------------


class Clue(BaseModel):
    """A discoverable clue that unlocks when the player asks about the right topic.

    unlock_keywords: 2-4 Chinese words that, when appearing in a player's question,
    signal that this clue should be revealed.  Matching happens in dm.py.
    """

    id: str
    title: str
    content: str  # the clue text shown to the player — reveals ONE aspect of truth
    unlock_keywords: list[str]  # e.g. ["海难", "船", "遇难"]


class PrivateClue(BaseModel):
    """A private clue fragment given exclusively to one player slot.

    Unlike Clue, PrivateClue has no unlock_keywords — it is distributed
    directly on room join based on the player's assigned slot (player_1,
    player_2 …).  Content must NEVER appear in another player's LLM prompt
    or in any public broadcast.
    """

    id: str
    title: str
    content: str  # shown only to the assigned player


class Puzzle(BaseModel):
    id: str
    title: str
    surface: str  # 汤面 — shown to the player
    truth: str  # 汤底 — TOP SECRET, never sent to frontend
    key_facts: list[str]  # decomposed truths used for matching
    hints: list[str]  # escalating hints (Phase 1 fallback, unchanged)
    clues: list[Clue] = []  # discoverable clues (Phase 2); old JSONs without this still load
    private_clues: dict[str, list[PrivateClue]] = {}  # slot → clues, e.g. {"player_1": [...]}
    difficulty: str  # e.g. "简单" / "中等" / "困难"
    tags: list[str]


# ---------------------------------------------------------------------------
# API request / response schemas
# ---------------------------------------------------------------------------


class StartRequest(BaseModel):
    puzzle_id: str | None = None  # None → random puzzle
    language: str = "zh"  # "zh" | "en"


class StartResponse(BaseModel):
    session_id: str
    puzzle_id: str
    title: str
    surface: str  # 汤面 only — truth is NEVER returned


class ChatRequest(BaseModel):
    session_id: str
    message: str  # player's yes/no question


class ChatResponse(BaseModel):
    judgment: str  # 是 / 不是 / 无关 / 部分正确
    response: str  # DM's reply (Chinese)
    truth_progress: float  # 0.0–1.0, how much has been deduced
    should_hint: bool
    hint: str | None = None  # only present when a hint is given
    truth: str | None = None  # populated when truth_progress >= 1.0 (game over)
    clue_unlocked: Clue | None = None  # newly unlocked clue this turn, if any
    trace: AgentTrace | None = None  # agent decision log (multi-agent path only)


class PuzzleSummary(BaseModel):
    """Safe puzzle info for the public /api/puzzles listing — no truth field."""

    id: str
    title: str
    difficulty: str
    tags: list[str]


# ---------------------------------------------------------------------------
# Multiplayer room models
# ---------------------------------------------------------------------------


class Player(BaseModel):
    id: str
    name: str
    connected: bool = True


class RoomState(BaseModel):
    """Safe room info returned by GET /api/rooms/{room_id} — no truth field."""

    room_id: str
    puzzle_id: str
    title: str
    surface: str  # 汤面 — safe to expose
    players: list[Player]
    phase: str  # "waiting" | "playing" | "finished"
    game_type: str = "turtle_soup"  # "turtle_soup" | "murder_mystery"


# ---------------------------------------------------------------------------
# WebSocket message types
# ---------------------------------------------------------------------------


class WsInboundChat(BaseModel):
    """Message sent from a player to the server."""

    type: Literal["chat"]
    text: str


class WsSystemMessage(BaseModel):
    """Server → all clients: join/leave/error notifications."""

    type: Literal["system"] = "system"
    text: str


class WsPlayerMessage(BaseModel):
    """Server → all clients: echo of what a player said (so everyone sees the question)."""

    type: Literal["player_message"] = "player_message"
    player_name: str
    text: str
    timestamp: float


class WsDMResponse(BaseModel):
    """Server → all clients: DM judgment + response after a player's question."""

    type: Literal["dm_response"] = "dm_response"
    player_name: str  # who asked
    judgment: str
    response: str
    truth_progress: float
    clue_unlocked: Clue | None = None
    hint: str | None = None
    truth: str | None = None  # populated when game is won
    timestamp: float


class WsClueNotification(BaseModel):
    """Server → all clients: a clue was just unlocked (also embedded in WsDMResponse)."""

    type: Literal["clue_unlocked"] = "clue_unlocked"
    clue: Clue


# ---------------------------------------------------------------------------
# Internal DM structured output (parsed from LLM JSON)
# ---------------------------------------------------------------------------


class DMOutput(BaseModel):
    judgment: str
    response: str
    truth_progress: float
    should_hint: bool
    audience: str = "public"  # "public" | "private"


# ---------------------------------------------------------------------------
# In-memory game session
# ---------------------------------------------------------------------------


class GameSession(BaseModel):
    session_id: str
    puzzle: Puzzle
    history: list[dict]  # OpenAI-format message dicts (raw, with <think> preserved)
    hint_index: int = 0
    consecutive_misses: int = 0
    finished: bool = False
    unlocked_clue_ids: set[str] = set()  # ids of clues the player has earned so far
    player_slot_map: dict[str, str] = {}  # player_id → "player_1" / "player_2" …
    language: str = "zh"  # "zh" | "en" — DM prompt language


# ---------------------------------------------------------------------------
# Murder mystery models (Phase 4)
# ---------------------------------------------------------------------------


class Character(BaseModel):
    """A player character in a murder mystery script.

    secret_bio and is_culprit are NEVER sent to any LLM prompt or frontend
    until the reveal phase.  The is_culprit field is stripped from character
    data before it leaves the server; only the reveal phase handler reads it.
    """

    id: str
    name: str
    public_bio: str  # shown to all players in the lobby
    secret_bio: str  # shown only to the assigned player (VisibilityRegistry)
    is_culprit: bool = False


class ReconstructionQuestion(BaseModel):
    """One question in a reconstruction-mode script."""

    id: str
    question: str
    answer: str  # expected answer used for scoring


class Phase(BaseModel):
    """One phase in the murder mystery flow.

    allowed_actions: set of action strings that the state machine permits.
    duration_seconds: None means the phase is manually advanced (no timeout).
    per_player_content: character_id → private script text shown only to that player.
    available_clues: clue IDs that can be unlocked during this phase.
    dm_script: canned DM narration text (used for opening/reveal phases).
    reconstruction_questions: ordered Q&A for reconstruction-mode scripts.
    """

    id: str
    type: str  # "narration" | "reading" | "investigation" | "discussion" | "voting" | "reveal" | "reconstruction"
    next: str | None  # id of the next phase, or None if this is the last
    duration_seconds: int | None = None
    allowed_actions: set[str] = set()
    dm_script: str | None = None
    available_clues: list[str] | None = None
    per_player_content: dict[str, str] | None = None  # char_id → text
    reconstruction_questions: list[ReconstructionQuestion] = []


class ScriptClue(BaseModel):
    """A discoverable clue in a murder mystery script.

    Differs from the turtle-soup Clue in that it carries phase_available
    and visibility metadata for the state machine to enforce.
    """

    id: str
    title: str
    content: str
    phase_available: str  # phase id when this clue becomes discoverable
    visibility: str = "public"  # "public" | "private"
    unlock_keywords: list[str] = []


class NPC(BaseModel):
    """A non-player character managed by the NPC agent.

    knowledge lists clue IDs this NPC is aware of.  The NPC agent's prompt
    only includes the content of clues in this list — the NPC cannot answer
    questions about clues it doesn't know (VisibilityRegistry enforces this).
    """

    id: str
    name: str
    persona: str  # description of personality and role
    knowledge: list[str]  # clue ids this NPC knows about
    speech_style: str  # e.g. "formal_elderly", "curt_official"


class ScriptTruth(BaseModel):
    """The ground truth for a murder mystery or reconstruction script.

    CRITICAL: culprit field NEVER enters any LLM prompt before reveal phase.
    Judge Agent receives decomposed key_facts, not this object.
    For reconstruction mode, culprit is empty string and full_story is set.
    """

    culprit: str = ""  # character id of the killer; empty for reconstruction mode
    motive: str
    method: str
    timeline: str
    key_facts: list[str] = []  # decomposed facts for Judge Agent (no culprit identity)
    full_story: str = ""  # complete story for reconstruction mode reveal
    cause_of_death: str = ""  # optional detail for reconstruction mode


class ScriptMetadata(BaseModel):
    player_count: int
    duration_minutes: int
    difficulty: str  # "beginner" | "intermediate" | "advanced"
    age_rating: str = "12+"


class ScriptTheme(BaseModel):
    """Visual and narrative theme generated for each script.

    Used by the frontend to apply per-script CSS colour variables and by
    NarratorAgent to adopt a script-specific DM voice.
    """

    primary_color: str = "#c4a35a"  # hex colour for accent / primary UI
    bg_tone: str = "dark"  # "dark" | "warm" | "eerie" | "cold" | "natural"
    era: str = ""  # e.g. "modern", "Victorian", "ancient China", "sci-fi"
    setting: str = ""  # e.g. "manor house", "spaceship", "countryside villa"
    dm_persona: str = ""  # personality hint for NarratorAgent, e.g. "calm and clinical detective"


class Script(BaseModel):
    """A complete murder mystery script loaded from data/scripts/.

    Phases are stored as a list (preserving order) and indexed by id for
    the state machine.  The state machine takes script.phases directly.
    game_mode: "whodunit" | "reconstruction"
    """

    id: str
    title: str
    game_mode: str = "whodunit"  # "whodunit" | "reconstruction"
    metadata: ScriptMetadata
    characters: list[Character]
    phases: list[Phase]
    clues: list[ScriptClue]
    npcs: list[NPC]
    truth: ScriptTruth
    theme: ScriptTheme = Field(default_factory=ScriptTheme)


class VoteRecord(BaseModel):
    """One player's vote during the voting phase."""

    player_id: str
    target_character_id: str
    timestamp: float


# ---------------------------------------------------------------------------
# Script ingestion response
# ---------------------------------------------------------------------------


class ScriptUploadResponse(BaseModel):
    """Returned by POST /api/scripts/upload on success."""

    script_id: str
    title: str
    player_count: int
    difficulty: str
    game_mode: str
    character_names: list[str]
    phase_count: int
    clue_count: int
    warning: str | None = None  # e.g. "text truncated to 24000 chars"
