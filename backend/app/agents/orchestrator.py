"""AgentOrchestrator — wires the Phase 4 multi-agent pipeline together.

Pipeline (from CLAUDE.md flow diagram):

  Player message
    │
    ▼
  RouterAgent (rules, <1ms)
    │ intent
    ▼
  State machine guard: can_act(intent) ?
    │  No → return phase-blocked error
    │  Yes ↓
    ├─ "vote"     → NotImplementedError (stub)
    ├─ "npc"      → NotImplementedError (stub)
    ├─ "question" → Judge → Narrator → Safety (retry up to 2×) → return
    ├─ "accuse"   → Judge → Narrator → Safety (same path as question)
    ├─ "search"   → try_unlock_clue() → Narrator for description → return
    ├─ "chat"     → None (broadcast player message only, no DM response)
    └─ "meta"     → canned response (no LLM)

Safety retry logic:
  If Safety.check fails → regenerate Narrator response (max 2 retries).
  After 2 failed retries → return REGENERATION_FALLBACK.

This orchestrator is for murder mystery mode only.  Turtle soup still uses
dm.py.  The orchestrator does NOT touch room state directly — it returns a
Response and the WebSocket handler decides what to broadcast.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import re

from app.agents.judge import JudgeAgent, Judgment, _FALLBACK_JUDGMENT
from app.agents.narrator import (
    NarratorAgent,
    _FALLBACK_RESPONSE_ZH,
    _FALLBACK_RESPONSE_EN,
    _REGENERATION_FALLBACK_ZH,
    _REGENERATION_FALLBACK_EN,
)

# Keep old names as aliases for code that imports them directly
_FALLBACK_RESPONSE = _FALLBACK_RESPONSE_ZH
_REGENERATION_FALLBACK = _REGENERATION_FALLBACK_ZH
from app.agents.npc import NPCAgent
from app.agents.router import RouterAgent
from app.agents.safety import SafetyAgent
from app.models import Script, ScriptClue
from app.state_machine import GameStateMachine
from app.visibility import VisibleContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Response type
# ---------------------------------------------------------------------------

RESP_DM = "dm_response"
RESP_ERROR = "error"
RESP_PHASE_BLOCKED = "phase_blocked"
RESP_CLUE_FOUND = "clue_found"
RESP_NO_RESPONSE = "no_response"   # chat intent — no DM reply
RESP_META = "meta_response"


@dataclass
class OrchestratorResponse:
    """What the orchestrator returns to the WebSocket handler for broadcasting."""

    type: str          # one of RESP_* constants
    text: str | None = None
    clue: dict | None = None   # populated for RESP_CLUE_FOUND


# ---------------------------------------------------------------------------
# Intent → allowed_action mapping
# ---------------------------------------------------------------------------

# Maps router intent to the state machine action string that must be permitted.
_INTENT_TO_ACTION: dict[str, str] = {
    "question": "ask_dm",
    "accuse":   "ask_dm",
    "search":   "search",
    "vote":     "cast_vote",
    "npc":      "ask_dm",
    "chat":     "public_chat",
    # meta is always permitted (no state machine guard)
}

# ---------------------------------------------------------------------------
# Canned meta responses
# ---------------------------------------------------------------------------

_META_RESPONSES_ZH: dict[str, str] = {
    "规则": (
        "游戏规则：各阶段请按提示行事。调查阶段可向DM提问、搜查线索、询问NPC；"
        "讨论阶段可与其他玩家交流；投票阶段请选出你认为的凶手。"
    ),
    "default": (
        "当前阶段请继续推理。如有疑问，可以提问、搜查，或询问NPC。祝大家好运！"
    ),
}

_META_RESPONSES_EN: dict[str, str] = {
    "rules": (
        "Game rules: follow the prompts for each phase. During investigation you may question the DM, "
        "search for clues, or interrogate NPCs. During discussion share your deductions. "
        "During voting, name the suspect you believe is the culprit."
    ),
    "default": (
        "Keep reasoning through the case. You may ask questions, search for clues, or interrogate NPCs. Good luck!"
    ),
}

# Keep old name for backward compatibility
_META_RESPONSES = _META_RESPONSES_ZH

_MAX_SAFETY_RETRIES = 2


# ---------------------------------------------------------------------------
# AgentOrchestrator
# ---------------------------------------------------------------------------


class AgentOrchestrator:
    """Wires all Phase 4 agents together.  One instance per murder mystery room.

    Parameters
    ----------
    script : Script
        The murder mystery script — provides key_facts, NPC names, clues.
    state_machine : GameStateMachine
        The room's active state machine — used for phase guards.
    player_char_map : dict[str, str]
        Maps player_id → character_id.  Built by the room when players join
        and are assigned characters.

    Note: NPC agent and voting module are not yet implemented.  Their intent
    branches raise NotImplementedError.
    """

    def __init__(
        self,
        script: Script,
        state_machine: GameStateMachine,
        player_char_map: dict[str, str] | None = None,
        language: str = "zh",
    ) -> None:
        self._script = script
        self._sm = state_machine
        self._player_char_map: dict[str, str] = player_char_map or {}
        self._language: str = language

        # Index clues by id for O(1) lookup
        self._clues_by_id: dict[str, ScriptClue] = {c.id: c for c in script.clues}

        # Build per-player unlocked-clue tracking
        self._unlocked_clue_ids: set[str] = set()

        npc_names = [n.name for n in script.npcs]
        self.router = RouterAgent(npc_names=npc_names)
        self.judge = JudgeAgent(key_facts=script.truth.key_facts)
        self.narrator = NarratorAgent()
        self.safety = SafetyAgent(
            key_facts=script.truth.key_facts,
            character_secrets={c.id: c.secret_bio for c in script.characters},
        )

        # NPC agents — one per NPC, keyed by npc.id
        self._npc_agents: dict[str, NPCAgent] = {
            npc.id: NPCAgent(npc, self._clues_by_id) for npc in script.npcs
        }
        # NPC name → npc.id for intent dispatch
        self._npc_by_name: dict[str, str] = {npc.name: npc.id for npc in script.npcs}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def handle_message(
        self,
        player_id: str,
        message: str,
        room: Any = None,  # reserved — WebSocket room object (not yet wired)
    ) -> OrchestratorResponse | None:
        """Process a player message through the full pipeline.

        Returns
        -------
        OrchestratorResponse or None
            None means the intent is "chat" — broadcast the player message
            directly with no DM response.
        """
        phase = self._sm.current_phase

        # a) Classify intent
        classification = self.router.classify(message, phase)
        intent = classification.intent
        logger.debug(
            "Orchestrator: player=%s phase=%s intent=%s rule=%s",
            player_id, phase, intent, classification.matched_rule,
        )

        # b) Meta — always allowed, no state machine check
        if intent == "meta":
            return self._handle_meta(message, language=self._language)

        # b) State machine guard
        required_action = _INTENT_TO_ACTION.get(intent)
        if required_action and not self._sm.can_act(required_action):
            if self._language == "en":
                blocked_text = f"This action is not available in the current phase ({phase})."
            else:
                blocked_text = f"当前阶段（{phase}）不能执行此操作。"
            return OrchestratorResponse(type=RESP_PHASE_BLOCKED, text=blocked_text)

        # c-h) Route by intent
        if intent == "vote":
            # Vote messages are intercepted by ws.py before reaching here.
            # If we arrive here anyway, tell the player to use the vote UI.
            if self._language == "en":
                vote_text = 'Please use the voting panel to cast your vote (send {"type": "vote", "target": "<char_id>"}).'
            else:
                vote_text = '请使用投票功能投票（发送 {"type": "vote", "target": "<char_id>"} ）。'
            return OrchestratorResponse(type=RESP_PHASE_BLOCKED, text=vote_text)

        if intent == "npc":
            return await self._handle_npc(player_id, message)

        if intent in ("question", "accuse"):
            return await self._handle_question(player_id, message)

        if intent == "search":
            return await self._handle_search(player_id, message)

        if intent == "chat":
            return None  # broadcast player message only, no DM response

        # Unreachable — all intents handled above
        return None

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    async def _handle_question(self, player_id: str, message: str) -> OrchestratorResponse:
        """Judge → Narrator → Safety pipeline."""
        visible = self._build_visible_context(player_id)
        viewer_char_id = self._player_char_map.get(player_id)

        # Judge
        player_visible_facts = [c["content"] for c in visible.public_clues]
        judgment = await self.judge.judge(message, player_visible_facts)

        # Narrator + Safety (with retry)
        text = await self._narrate_with_safety(
            judgment=judgment,
            player_message=message,
            visible=visible,
            player_id=player_id,
            viewer_char_id=viewer_char_id,
        )
        return OrchestratorResponse(type=RESP_DM, text=text)

    async def _handle_search(self, player_id: str, message: str) -> OrchestratorResponse:
        """Try to unlock a clue, then narrate the finding."""
        phase = self._sm.current_phase
        phase_obj = self._sm.current()
        available = set(phase_obj.available_clues or [])

        # Try keyword-based clue unlock
        clue_found: ScriptClue | None = None
        for clue_id in available:
            if clue_id in self._unlocked_clue_ids:
                continue
            clue = self._clues_by_id.get(clue_id)
            if clue and any(kw in message for kw in clue.unlock_keywords):
                self._unlocked_clue_ids.add(clue_id)
                clue_found = clue
                break

        if clue_found:
            visible = self._build_visible_context(player_id)
            viewer_char_id = self._player_char_map.get(player_id)
            # Fabricate a judgment for "finding a clue" (always positive)
            judgment: Judgment = {
                "result": "Yes" if self._language == "en" else "是",
                "confidence": 1.0,
                "relevant_fact_ids": [],
            }
            # Temporarily add clue to visible context for narrator
            clue_dict = {
                "id": clue_found.id,
                "title": clue_found.title,
                "content": clue_found.content,
            }
            visible.public_clues.append(clue_dict)
            text = await self._narrate_with_safety(
                judgment=judgment,
                player_message=message,
                visible=visible,
                player_id=player_id,
                viewer_char_id=viewer_char_id,
            )
            return OrchestratorResponse(
                type=RESP_CLUE_FOUND,
                text=text,
                clue=clue_dict,
            )

        # Nothing found — nudge the player
        fallback_judgment: Judgment = {
            "result": "Irrelevant" if self._language == "en" else "无关",
            "confidence": 0.5,
            "relevant_fact_ids": [],
        }
        visible = self._build_visible_context(player_id)
        viewer_char_id = self._player_char_map.get(player_id)
        text = await self._narrate_with_safety(
            judgment=fallback_judgment,
            player_message=message,
            visible=visible,
            player_id=player_id,
            viewer_char_id=viewer_char_id,
        )
        return OrchestratorResponse(type=RESP_DM, text=text)

    async def _handle_npc(self, player_id: str, message: str) -> OrchestratorResponse:
        """Dispatch to the appropriate NPC agent."""
        npc_id = self._detect_npc_id(message)
        if npc_id and npc_id in self._npc_agents:
            text = await self._npc_agents[npc_id].respond(message)
            return OrchestratorResponse(type=RESP_DM, text=text)
        # Could not identify which NPC — fall back to question handler
        return await self._handle_question(player_id, message)

    def _detect_npc_id(self, message: str) -> str | None:
        """Return the NPC id if the message addresses a known NPC, else None."""
        # @mention: @<name>
        at_match = re.search(r"@(\S+)", message)
        if at_match:
            mention = at_match.group(1)
            for name, npc_id in self._npc_by_name.items():
                if name in mention or mention in name:
                    return npc_id
        # Direct name mention
        for name, npc_id in self._npc_by_name.items():
            if name in message:
                return npc_id
        return None

    @staticmethod
    def _handle_meta(message: str, language: str = "zh") -> OrchestratorResponse:
        """Return a canned help/rules response — no LLM call."""
        meta = _META_RESPONSES_EN if language == "en" else _META_RESPONSES_ZH
        for keyword, response in meta.items():
            if keyword != "default" and keyword in message:
                return OrchestratorResponse(type=RESP_META, text=response)
        return OrchestratorResponse(type=RESP_META, text=meta["default"])

    # ------------------------------------------------------------------
    # Narrator + Safety with retry
    # ------------------------------------------------------------------

    async def _narrate_with_safety(
        self,
        judgment: Judgment,
        player_message: str,
        visible: VisibleContext,
        player_id: str,
        viewer_char_id: str | None,
    ) -> str:
        """Run Narrator → Safety, retrying up to _MAX_SAFETY_RETRIES times."""
        phase = self._sm.current_phase

        # Inject truth only during reveal phase
        truth_for_reveal: str | None = None
        if phase == "reveal":
            truth_for_reveal = self._build_truth_reveal_text()

        regen_fallback = _REGENERATION_FALLBACK_EN if self._language == "en" else _REGENERATION_FALLBACK_ZH
        for attempt in range(_MAX_SAFETY_RETRIES + 1):
            text = await self.narrator.narrate(
                judgment=judgment,
                player_message=player_message,
                visible_context=visible,
                phase=phase,
                truth_for_reveal=truth_for_reveal,
                language=self._language,
            )
            result = await self.safety.check(
                text=text,
                audience_player_id=player_id,
                viewer_char_id=viewer_char_id,
            )
            if result["safe"]:
                return text
            logger.warning(
                "SafetyAgent blocked narrator output (attempt %d/%d): %r",
                attempt + 1, _MAX_SAFETY_RETRIES + 1,
                result.get("leaked_content", "")[:40],
            )

        # All retries exhausted — fall back to safe generic response
        logger.error(
            "Orchestrator: all %d safety retries failed for player %s — using fallback",
            _MAX_SAFETY_RETRIES + 1, player_id,
        )
        return regen_fallback

    # ------------------------------------------------------------------
    # Context builders
    # ------------------------------------------------------------------

    def _build_visible_context(self, player_id: str) -> VisibleContext:
        """Build a VisibleContext for a player in murder mystery mode.

        In Phase 4, "private clues" correspond to the character's secret_bio
        (which the player already received on join).  We keep private_clues
        empty here — the Narrator does NOT see the player's secrets.
        """
        # Surface = the opening DM script (sets the scene)
        opening_phase = self._sm.phases.get("opening")
        surface = (opening_phase.dm_script or "") if opening_phase else ""

        # Public unlocked clues (all players see these)
        public_clues = [
            {"id": c.id, "title": c.title, "content": c.content}
            for c in self._script.clues
            if c.id in self._unlocked_clue_ids
        ]

        char_id = self._player_char_map.get(player_id, "")
        return VisibleContext(
            player_id=player_id,
            player_slot=char_id,
            surface=surface,
            public_clues=public_clues,
            private_clues=[],  # Narrator is blind to character secrets
        )

    def _build_truth_reveal_text(self) -> str:
        """Build the reveal text from the script truth (only used in reveal phase)."""
        truth = self._script.truth
        culprit_char = next(
            (c for c in self._script.characters if c.id == truth.culprit), None
        )
        culprit_name = culprit_char.name if culprit_char else truth.culprit
        if self._language == "en":
            return (
                f"Culprit: {culprit_name}\n"
                f"Motive: {truth.motive}\n"
                f"Method: {truth.method}\n"
                f"Timeline: {truth.timeline}"
            )
        return (
            f"凶手：{culprit_name}\n"
            f"动机：{truth.motive}\n"
            f"手法：{truth.method}\n"
            f"时间线：{truth.timeline}"
        )
