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

import dataclasses
import logging
import re
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from app.agents.judge import JudgeAgent, Judgment
from app.agents.narrator import (
    _FALLBACK_RESPONSE_ZH,
    _REGENERATION_FALLBACK_EN,
    _REGENERATION_FALLBACK_ZH,
    NarratorAgent,
)

# Keep old names as aliases for code that imports them directly
_FALLBACK_RESPONSE = _FALLBACK_RESPONSE_ZH
_REGENERATION_FALLBACK = _REGENERATION_FALLBACK_ZH
from app.agents.npc import NPCAgent  # noqa: E402
from app.agents.router import RouterAgent  # noqa: E402
from app.agents.safety import SafetyAgent  # noqa: E402
from app.agents.trace import AgentTrace, TraceStep, new_trace  # noqa: E402
from app.llm import drain_usage, reset_usage_accumulator  # noqa: E402
from app.models import Script, ScriptClue  # noqa: E402
from app.state_machine import GameStateMachine  # noqa: E402
from app.visibility import VisibleContext  # noqa: E402

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
    ) -> tuple[OrchestratorResponse | None, AgentTrace]:
        """Process a player message through the full pipeline.

        Returns
        -------
        (OrchestratorResponse or None, AgentTrace)
            OrchestratorResponse is None when intent is "chat" — caller should
            broadcast the player message directly with no DM response.
            AgentTrace is always returned for logging/display.
        """
        trace = new_trace(player_id, message)
        phase = self._sm.current_phase

        # a) Classify intent (rules-only, no LLM)
        t0 = time.time()
        classification = self.router.classify(message, phase)
        router_latency = (time.time() - t0) * 1000
        intent = classification.intent

        trace.steps.append(TraceStep(
            agent="router",
            input_summary=f"message={message[:80]!r}, phase={phase}",
            output_summary=f"intent={intent}, rule={classification.matched_rule}",
            latency_ms=router_latency,
            tokens_in=0,
            tokens_out=0,
            metadata={"intent": intent, "matched_rule": classification.matched_rule},
        ))

        logger.debug(
            "Orchestrator: player=%s phase=%s intent=%s rule=%s",
            player_id, phase, intent, classification.matched_rule,
        )

        # b) Meta and chat are always allowed — skip state machine guard
        if intent == "meta":
            return self._handle_meta(message, language=self._language), trace

        if intent == "chat":
            return None, trace  # broadcast player message only, no DM response

        # c) State machine guard (only for DM-interacting intents)
        required_action = _INTENT_TO_ACTION.get(intent)
        if required_action and not self._sm.can_act(required_action):
            if self._language == "en":
                blocked_text = f"This action is not available in the current phase ({phase})."
            else:
                blocked_text = f"当前阶段（{phase}）不能执行此操作。"
            return OrchestratorResponse(type=RESP_PHASE_BLOCKED, text=blocked_text), trace

        # c-h) Route by intent
        if intent == "vote":
            # Vote messages are intercepted by ws.py before reaching here.
            # If we arrive here anyway, tell the player to use the vote UI.
            if self._language == "en":
                vote_text = 'Please use the voting panel to cast your vote (send {"type": "vote", "target": "<char_id>"}).'
            else:
                vote_text = '请使用投票功能投票（发送 {"type": "vote", "target": "<char_id>"} ）。'
            return OrchestratorResponse(type=RESP_PHASE_BLOCKED, text=vote_text), trace

        if intent == "npc":
            return await self._handle_npc(player_id, message, trace), trace

        if intent in ("question", "accuse"):
            return await self._handle_question(player_id, message, trace), trace

        if intent == "search":
            return await self._handle_search(player_id, message, trace), trace

        # Unreachable — all intents handled above
        return None, trace

    async def handle_message_stream(
        self,
        player_id: str,
        message: str,
    ) -> AsyncGenerator[dict, None]:
        """Streaming variant of handle_message for murder mystery.

        Yields WebSocket-ready dicts:
          {type: "dm_stream_start", judgment: str, confidence: float}
          {type: "dm_stream_chunk", text: str}
          {type: "dm_stream_end", clue: dict|None, trace: dict}
          OR on safety fail:
          {type: "dm_stream_end", replace: str, clue: None, trace: dict}
        """
        return self._stream_generator(player_id, message)

    async def _stream_generator(
        self, player_id: str, message: str
    ) -> AsyncGenerator[dict, None]:
        trace = new_trace(player_id, message)
        phase = self._sm.current_phase
        logger.info("[ORCH] stream_generator: player=%s phase=%s message=%r", player_id, phase, message[:80])

        # Route (rules-only)
        t0 = time.time()
        classification = self.router.classify(message, phase)
        router_latency = (time.time() - t0) * 1000
        intent = classification.intent
        logger.info("[ORCH] router: intent=%s rule=%s latency=%.1fms", intent, classification.matched_rule, router_latency)

        trace.steps.append(TraceStep(
            agent="router",
            input_summary=f"message={message[:80]!r}, phase={phase}",
            output_summary=f"intent={intent}, rule={classification.matched_rule}",
            latency_ms=router_latency,
            tokens_in=0, tokens_out=0,
            metadata={"intent": intent},
        ))

        # Non-streaming intents — fall through to non-streaming handler
        if intent in ("meta", "chat", "vote"):
            logger.info("[ORCH] intent=%s → no DM response (non-streaming path)", intent)
            resp, _ = await self.handle_message(player_id, message)
            if resp is not None:
                logger.debug("[ORCH] non-streaming response: type=%s", resp.type)
                yield {"type": resp.type, "text": resp.text, "clue": resp.clue}
            return

        # State machine guard
        required_action = _INTENT_TO_ACTION.get(intent)
        if required_action and not self._sm.can_act(required_action):
            logger.info("[ORCH] phase_blocked: intent=%s required=%s phase=%s", intent, required_action, phase)
            blocked = (
                f"This action is not available in the current phase ({phase})."
                if self._language == "en"
                else f"当前阶段（{phase}）不能执行此操作。"
            )
            yield {"type": RESP_PHASE_BLOCKED, "text": blocked}
            return

        if intent == "npc":
            resp, _ = await self.handle_message(player_id, message)
            if resp is not None:
                yield {"type": resp.type, "text": resp.text, "clue": resp.clue}
            return

        # --- Streaming path: question / accuse / search ---
        visible = self._build_visible_context(player_id)
        viewer_char_id = self._player_char_map.get(player_id)
        player_visible_facts = [c["content"] for c in visible.public_clues]

        clue_dict: dict | None = None

        if intent == "search":
            # Try clue unlock first (rules-based)
            phase_obj = self._sm.current()
            available = set(phase_obj.available_clues or [])
            clue_found = None
            for clue_id in available:
                if clue_id in self._unlocked_clue_ids:
                    continue
                clue = self._clues_by_id.get(clue_id)
                if clue and any(kw in message for kw in clue.unlock_keywords):
                    self._unlocked_clue_ids.add(clue_id)
                    clue_found = clue
                    break
            if clue_found:
                clue_dict = {"id": clue_found.id, "title": clue_found.title, "content": clue_found.content}
                visible.public_clues.append(clue_dict)
            judgment: Judgment = {
                "result": "Yes" if self._language == "en" else "是",
                "confidence": 1.0,
                "relevant_fact_ids": [],
            } if clue_found else {
                "result": "Irrelevant" if self._language == "en" else "无关",
                "confidence": 0.5,
                "relevant_fact_ids": [],
            }
        else:
            # Judge
            logger.info("[ORCH] calling Judge: key_facts=%d, visible_facts=%d", len(self.judge._key_facts), len(player_visible_facts))
            reset_usage_accumulator()
            t0 = time.time()
            judgment = await self.judge.judge(message, player_visible_facts)
            judge_latency = (time.time() - t0) * 1000
            judge_usages = drain_usage()
            logger.info("[ORCH] Judge done: result=%s confidence=%.0f%% latency=%.0fms tokens_in=%d tokens_out=%d",
                judgment["result"], judgment["confidence"] * 100, judge_latency,
                sum(u.prompt_tokens for u in judge_usages),
                sum(u.completion_tokens for u in judge_usages),
            )
            trace.steps.append(TraceStep(
                agent="judge",
                input_summary=f"key_facts: {len(self.judge._key_facts)} items",
                output_summary=f"result={judgment['result']}, confidence={judgment['confidence']:.0%}",
                latency_ms=judge_latency,
                tokens_in=sum(u.prompt_tokens for u in judge_usages),
                tokens_out=sum(u.completion_tokens for u in judge_usages),
                metadata={"judgment": judgment["result"]},
            ))

        # Broadcast judgment immediately — player sees result before narrator finishes
        logger.info("[ORCH] yielding dm_stream_start: judgment=%s", judgment["result"])
        yield {
            "type": "dm_stream_start",
            "judgment": judgment["result"],
            "confidence": judgment["confidence"],
        }

        # Stream narrator
        phase_val = self._sm.current_phase
        truth_for_reveal = self._build_truth_reveal_text() if phase_val == "reveal" else None

        logger.info("[ORCH] starting Narrator stream: phase=%s", phase_val)
        reset_usage_accumulator()
        t0 = time.time()
        accumulated = ""
        chunk_count = 0
        try:
            stream_gen = await self.narrator.narrate_stream(
                judgment=judgment,
                player_message=message,
                visible_context=visible,
                phase=phase_val,
                truth_for_reveal=truth_for_reveal,
                language=self._language,
            )
            async for chunk in stream_gen:
                accumulated += chunk
                chunk_count += 1
                if chunk_count == 1:
                    logger.info("[ORCH] Narrator first chunk arrived: TTFT=%.0fms", (time.time() - t0) * 1000)
                yield {"type": "dm_stream_chunk", "text": chunk}
        except Exception as exc:
            logger.exception("[ORCH] Narrator stream failed: %s", exc)
            fallback = _REGENERATION_FALLBACK_EN if self._language == "en" else _REGENERATION_FALLBACK_ZH
            accumulated = fallback
            yield {"type": "dm_stream_chunk", "text": fallback}

        narrator_usages = drain_usage()
        narrator_latency = (time.time() - t0) * 1000
        logger.info("[ORCH] Narrator stream done: chars=%d chunks=%d total_latency=%.0fms tokens_in=%d tokens_out=%d",
            len(accumulated), chunk_count, narrator_latency,
            sum(u.prompt_tokens for u in narrator_usages),
            sum(u.completion_tokens for u in narrator_usages),
        )
        trace.steps.append(TraceStep(
            agent="narrator",
            input_summary=f"judgment={judgment['result']}, phase={phase_val}",
            output_summary=f"response_len={len(accumulated)} chars",
            latency_ms=narrator_latency,
            tokens_in=sum(u.prompt_tokens for u in narrator_usages),
            tokens_out=sum(u.completion_tokens for u in narrator_usages),
            metadata={"phase": phase_val},
        ))

        # Verbatim safety check on complete text
        logger.debug("[ORCH] running safety check on accumulated text: len=%d", len(accumulated))
        result = await self.safety.check(
            text=accumulated,
            audience_player_id=player_id,
            viewer_char_id=viewer_char_id,
        )
        fallback_text = _REGENERATION_FALLBACK_EN if self._language == "en" else _REGENERATION_FALLBACK_ZH

        trace_dict = dataclasses.asdict(trace)
        if result["safe"]:
            logger.info("[ORCH] safety pass → dm_stream_end (safe)")
            yield {
                "type": "dm_stream_end",
                "clue": clue_dict,
                "trace": trace_dict,
            }
        else:
            logger.warning("[ORCH] safety BLOCKED narrator output → replacing with fallback")
            yield {
                "type": "dm_stream_end",
                "replace": fallback_text,
                "clue": None,
                "trace": trace_dict,
            }

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    async def _handle_question(
        self, player_id: str, message: str, trace: AgentTrace
    ) -> OrchestratorResponse:
        """Judge → Narrator → Safety pipeline."""
        visible = self._build_visible_context(player_id)
        viewer_char_id = self._player_char_map.get(player_id)
        player_visible_facts = [c["content"] for c in visible.public_clues]

        # Judge
        reset_usage_accumulator()
        t0 = time.time()
        judgment = await self.judge.judge(message, player_visible_facts)
        judge_usages = drain_usage()
        trace.steps.append(TraceStep(
            agent="judge",
            input_summary=(
                f"key_facts: {len(self.judge._key_facts)} items; "
                f"visible_facts: {len(player_visible_facts)} items"
            ),
            output_summary=(
                f"result={judgment['result']}, "
                f"confidence={judgment['confidence']:.0%}, "
                f"relevant_facts: {len(judgment['relevant_fact_ids'])} items"
            ),
            latency_ms=(time.time() - t0) * 1000,
            tokens_in=sum(u.prompt_tokens for u in judge_usages),
            tokens_out=sum(u.completion_tokens for u in judge_usages),
            metadata={"judgment": judgment["result"]},
        ))

        # Narrator + Safety (with retry)
        text = await self._narrate_with_safety(
            judgment=judgment,
            player_message=message,
            visible=visible,
            player_id=player_id,
            viewer_char_id=viewer_char_id,
            trace=trace,
        )
        return OrchestratorResponse(type=RESP_DM, text=text)

    async def _handle_search(
        self, player_id: str, message: str, trace: AgentTrace
    ) -> OrchestratorResponse:
        """Try to unlock a clue, then narrate the finding."""
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
                trace=trace,
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
            trace=trace,
        )
        return OrchestratorResponse(type=RESP_DM, text=text)

    async def _handle_npc(
        self, player_id: str, message: str, trace: AgentTrace
    ) -> OrchestratorResponse:
        """Dispatch to the appropriate NPC agent."""
        npc_id = self._detect_npc_id(message)
        if npc_id and npc_id in self._npc_agents:
            npc_agent = self._npc_agents[npc_id]
            npc_name = next(
                (n.name for n in self._script.npcs if n.id == npc_id), npc_id
            )
            reset_usage_accumulator()
            t0 = time.time()
            text = await npc_agent.respond(message)
            npc_usages = drain_usage()
            trace.steps.append(TraceStep(
                agent="npc",
                input_summary=(
                    f"npc={npc_name!r}, "
                    f"knowledge: {len(npc_agent._knowledge_clues)} items"
                ),
                output_summary=f"response_len={len(text)} chars",
                latency_ms=(time.time() - t0) * 1000,
                tokens_in=sum(u.prompt_tokens for u in npc_usages),
                tokens_out=sum(u.completion_tokens for u in npc_usages),
                metadata={"npc_id": npc_id, "npc_name": npc_name},
            ))
            return OrchestratorResponse(type=RESP_DM, text=text)
        # Could not identify which NPC — fall back to question handler
        return await self._handle_question(player_id, message, trace)

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
        trace: AgentTrace | None = None,
    ) -> str:
        """Run Narrator → Safety, retrying up to _MAX_SAFETY_RETRIES times."""
        phase = self._sm.current_phase

        # Inject truth only during reveal phase
        truth_for_reveal: str | None = None
        if phase == "reveal":
            truth_for_reveal = self._build_truth_reveal_text()

        regen_fallback = _REGENERATION_FALLBACK_EN if self._language == "en" else _REGENERATION_FALLBACK_ZH
        for attempt in range(_MAX_SAFETY_RETRIES + 1):
            # Narrator
            reset_usage_accumulator()
            t0 = time.time()
            text = await self.narrator.narrate(
                judgment=judgment,
                player_message=player_message,
                visible_context=visible,
                phase=phase,
                truth_for_reveal=truth_for_reveal,
                language=self._language,
            )
            narrator_usages = drain_usage()
            if trace is not None:
                trace.steps.append(TraceStep(
                    agent="narrator",
                    input_summary=(
                        f"judgment={judgment['result']}, "
                        f"public_clues: {len(visible.public_clues)} items, "
                        f"phase={phase}"
                    ),
                    output_summary=f"response_len={len(text)} chars",
                    latency_ms=(time.time() - t0) * 1000,
                    tokens_in=sum(u.prompt_tokens for u in narrator_usages),
                    tokens_out=sum(u.completion_tokens for u in narrator_usages),
                    metadata={"attempt": attempt + 1, "phase": phase},
                ))

            # Safety
            reset_usage_accumulator()
            t0 = time.time()
            result = await self.safety.check(
                text=text,
                audience_player_id=player_id,
                viewer_char_id=viewer_char_id,
            )
            safety_usages = drain_usage()
            if trace is not None:
                leaked = result.get("leaked_content") or ""
                trace.steps.append(TraceStep(
                    agent="safety",
                    input_summary=(
                        f"text_len={len(text)} chars, "
                        f"key_facts: {len(self.safety._key_facts)} items"
                    ),
                    output_summary=(
                        f"safe={result['safe']}"
                        + (f", leaked={leaked[:30]!r}" if not result["safe"] else "")
                    ),
                    latency_ms=(time.time() - t0) * 1000,
                    tokens_in=sum(u.prompt_tokens for u in safety_usages),
                    tokens_out=sum(u.completion_tokens for u in safety_usages),
                    metadata={"safe": result["safe"], "attempt": attempt + 1},
                ))

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
