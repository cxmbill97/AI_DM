# CLAUDE.md

## Commands

```bash
cd backend && uv run uvicorn app.main:app --reload          # API server (port 8000)
cd backend && uv run pytest tests/ -x -v                     # all tests
cd backend && uv run pytest tests/test_redteam.py -x -v      # anti-spoiler
cd frontend && pnpm dev                                       # React dev (port 5173)
```

## Project Overview

AI-powered game master evolving from Turtle Soup (海龟汤) to full Murder Mystery
(剧本杀). The system hosts structured multi-player deduction games where an AI DM
manages phases, clues, secrets, and fair play.

**Completed phases:**

- Phase 1: Single-player turtle soup Q&A with pseudo-clue cards
- Phase 2: Multiplayer rooms, real clue unlock, DM intervention engine
- Phase 3: Collaborative reasoning — VisibilityRegistry, private clues per player,
  per-player DM prompts, private chat, anti-leak detection

**Next: Phase 4 — Simple 剧本杀 (Murder Mystery)**
One short script (4 players, ~40 min). Full flow: opening → character assignment →
reading → investigation → discussion → voting → reveal → review. Each player has a
character with public bio, secret backstory, and hidden motives. AI DM hosts the
entire session. Multi-agent split: Judge, Narrator, Safety as separate agents with
minimum-privilege context.

**Core principle: Deterministic State > LLM Output.**
The state machine owns phase transitions, clue permissions, and vote tallying.
LLM agents propose actions; the runtime validates and executes.

## Architecture

```
backend/
├── app/
│   ├── main.py                 # FastAPI: REST + WebSocket /ws/{room_id}
│   ├── llm.py                  # MiniMax client via OpenAI SDK
│   ├── models.py               # All Pydantic models
│   ├── puzzle_loader.py        # Load puzzle/script JSON
│   ├── room.py                 # Room manager: create/join/leave, broadcast
│   ├── ws.py                   # WebSocket handler: message routing
│   ├── visibility.py           # VisibilityRegistry: per-player context filter
│   ├── intervention.py         # DM intervention engine
│   ├── state_machine.py        # [Phase 4] Phase state machine + transition guards
│   ├── voting.py               # [Phase 4] Vote collection, resolution, tiebreaker
│   ├── agents/                 # [Phase 4] Multi-agent DM pipeline
│   │   ├── orchestrator.py     # Pipeline: Router → Judge → Narrator → Safety
│   │   ├── router.py           # Intent classifier (rules, no LLM)
│   │   ├── judge.py            # Truth judgment (sees truth, outputs structured judgment)
│   │   ├── narrator.py         # Response generation (CANNOT see truth)
│   │   └── safety.py           # Leak detection (sees truth + narrator output)
│   ├── dm.py                   # Legacy single-call DM (kept for turtle soup mode)
│   └── npc.py                  # [Phase 4] NPC agent: persona prompt, in-character response
├── data/
│   ├── puzzles/                # Turtle soup puzzles (Phase 1-3)
│   └── scripts/                # [Phase 4] Murder mystery script JSON files
│       └── rain_night_001.json
├── tests/
│   ├── test_dm.py
│   ├── test_clues.py
│   ├── test_redteam.py
│   ├── test_room.py
│   ├── test_intervention.py
│   ├── test_visibility.py
│   ├── test_state_machine.py   # [Phase 4] Phase transitions, guards, timeout
│   ├── test_voting.py          # [Phase 4] Vote logic, tiebreaker, edge cases
│   ├── test_agents.py          # [Phase 4] Each agent independently + pipeline
│   └── conftest.py
└── pyproject.toml

frontend/
├── src/
│   ├── App.tsx
│   ├── components/
│   │   ├── ChatPanel.tsx        # Public/private toggle, player name colors
│   │   ├── PuzzleCard.tsx       # Turtle soup surface (Phase 1-3)
│   │   ├── ScriptCard.tsx       # [Phase 4] Character bio + phase description
│   │   ├── CluePanel.tsx        # Shared unlocked clues
│   │   ├── PrivateCluePanel.tsx  # Player's private clues/secrets
│   │   ├── ProgressBar.tsx
│   │   ├── PlayerList.tsx
│   │   ├── PhaseBar.tsx         # [Phase 4] Current phase + timer + phase progress
│   │   └── VotePanel.tsx        # [Phase 4] Vote UI: select suspect, confirm, results
│   ├── hooks/
│   │   ├── useChat.ts
│   │   └── useRoom.ts
│   ├── pages/
│   │   ├── LobbyPage.tsx        # Create/join + mode select (turtle soup vs 剧本杀)
│   │   ├── GamePage.tsx         # Single-player turtle soup
│   │   └── RoomPage.tsx         # Multiplayer (turtle soup + 剧本杀)
│   └── api.ts
└── vite.config.ts
```

## Key Concepts

1. **VisibilityRegistry:** Maps (player_id, phase) → visible context. Each player
   sees: public info + own character secrets + phase-appropriate clues. DM sees full
   picture. Public chat uses public-only context. Private chat includes player’s
   own secrets. Implemented and tested.
1. **DM Intervention Engine:** Tier 1 rules + Tier 2 lightweight LLM. Silence
   detection with exponential backoff. Canned gentle nudges (zero LLM cost).
   Only active in multiplayer. Implemented and tested.
1. **[Phase 4] State Machine:** Deterministic phase transitions with guards.
   Each phase defines: allowed actions, duration, next phase, DM behavior mode.
   LLM cannot trigger transitions directly — it proposes via tool_use, state
   machine validates. Timer-based auto-advance on timeout.
1. **[Phase 4] Multi-Agent Pipeline:** Fat DM split into 4 specialized agents:
- Router: intent classification (pure rules, no LLM, <1ms)
- Judge: evaluates player question/action against truth (sees truth, outputs
  structured judgment — NOT natural language)
- Narrator: generates Chinese DM dialogue (CANNOT see truth — minimum privilege.
  Receives only: judgment result + player visible context + unlocked clues)
- Safety: scans narrator output for truth leakage (sees truth + output)
  Pipeline orchestrated by native Python async, not LangGraph.
1. **[Phase 4] Voting:** Each player casts one vote for suspected culprit.
   Votes are secret until all collected. Tiebreaker: runoff vote between tied
   candidates. State machine enforces: voting only in voting phase, one vote
   per player, no changing after submit.
1. **[Phase 4] NPC Agent:** Key NPCs have persona prompts (name, personality,
   speech style, knowledge boundary). NPC responses are generated by a separate
   LLM call with that NPC’s persona. NPC also filtered by VisibilityRegistry —
   NPC cannot reveal info the NPC character shouldn’t know.
1. **MiniMax API:** OpenAI SDK compatible. `base_url="https://api.minimax.io/v1"`.
   Model: “MiniMax-M2.5”. JSON not guaranteed — always try/except.
   Strip `<think>` tags before display, preserve in history.

## Murder Mystery Script Schema (Phase 4)

```json
{
  "id": "script_001",
  "title": "雨夜迷踪",
  "metadata": {
    "player_count": 4,
    "duration_minutes": 40,
    "difficulty": "beginner",
    "age_rating": "12+"
  },
  "characters": [
    {
      "id": "char_a",
      "name": "林晓",
      "public_bio": "知名画家，案发当晚在场",
      "secret_bio": "与死者有财务纠纷，欠债50万（仅本人可见）",
      "is_culprit": false
    }
  ],
  "phases": [
    {
      "id": "opening",
      "type": "narration",
      "next": "reading",
      "duration_seconds": 120,
      "dm_script": "各位玩家，欢迎来到今晚的推理之旅...",
      "allowed_actions": ["listen"]
    },
    {
      "id": "reading",
      "type": "reading",
      "next": "investigation_1",
      "duration_seconds": 300,
      "allowed_actions": ["read_script"],
      "per_player_content": {"char_a": "你的角色剧本...", "char_b": "..."}
    },
    {
      "id": "investigation_1",
      "type": "investigation",
      "next": "discussion",
      "duration_seconds": 600,
      "allowed_actions": ["ask_dm", "search", "private_chat"],
      "available_clues": ["clue_001", "clue_002", "clue_003"]
    },
    {
      "id": "discussion",
      "type": "discussion",
      "next": "voting",
      "duration_seconds": 600,
      "allowed_actions": ["public_chat", "private_chat"]
    },
    {
      "id": "voting",
      "type": "voting",
      "next": "reveal",
      "duration_seconds": 120,
      "allowed_actions": ["cast_vote"]
    },
    {
      "id": "reveal",
      "type": "reveal",
      "next": null,
      "allowed_actions": ["listen"]
    }
  ],
  "clues": [
    {
      "id": "clue_001",
      "title": "监控时间戳",
      "content": "大厅监控显示 22:13 有人影经过",
      "phase_available": "investigation_1",
      "visibility": "private",
      "unlock_keywords": ["监控", "摄像头", "时间"]
    }
  ],
  "npcs": [
    {
      "id": "npc_butler",
      "name": "管家老周",
      "persona": "60岁，在宅邸服务30年，说话恭敬但偶尔透露关键信息",
      "knowledge": ["clue_001", "clue_003"],
      "speech_style": "formal_elderly"
    }
  ],
  "truth": {
    "culprit": "char_c",
    "motive": "死者发现了 char_c 的秘密身份...",
    "method": "在书房用...",
    "timeline": "21:00 晚宴开始... 22:13 char_c 经过大厅..."
  }
}
```

CRITICAL: `truth.culprit` and `is_culprit` NEVER enter any LLM prompt until
reveal phase. Not even Judge Agent — Judge receives key_facts decomposed from
truth, not the raw truth object with culprit field.

## State Machine Design

```python
PHASES = {
    "opening":         Phase(next="reading",         timeout=120,  actions={"listen"}),
    "reading":         Phase(next="investigation_1",  timeout=300,  actions={"read_script"}),
    "investigation_1": Phase(next="discussion",       timeout=600,  actions={"ask_dm", "search", "private_chat"}),
    "discussion":      Phase(next="voting",           timeout=600,  actions={"public_chat", "private_chat"}),
    "voting":          Phase(next="reveal",           timeout=120,  actions={"cast_vote"}),
    "reveal":          Phase(next=None,               timeout=None, actions={"listen"}),
}

def can_act(action: str, current_phase: str) -> bool:
    return action in PHASES[current_phase].actions

def advance(current_phase: str) -> str | None:
    return PHASES[current_phase].next
```

Guards:

- advance(“investigation_1”) requires: all mandatory clues discovered OR timeout
- advance(“discussion”) requires: DM deems discussion sufficient OR timeout
- advance(“voting”) requires: all players voted OR timeout
- Timeout always forces advance — game never stalls

State machine transitions are PURE — no LLM calls, no network IO inside.

## Multi-Agent Pipeline

```
Player message
  │
  ▼
Router Agent (rules, no LLM, <1ms)
  │ classify intent: "question" | "search" | "accuse" | "vote" | "chat" | "meta"
  │
  ├─ intent == "vote" ────→ VotingModule (no LLM, pure logic)
  │
  ├─ intent == "search" ──→ State machine check (allowed in this phase?)
  │                          → ClueSystem (keyword match → unlock)
  │                          → Narrator (describe finding)
  │
  ├─ intent == "question" ─→ Judge Agent (sees key_facts, outputs judgment)
  │                          → Narrator Agent (sees judgment + visible context, NOT truth)
  │                          → Safety Agent (sees truth + narrator output, blocks if leak)
  │
  ├─ intent == "chat" ────→ No DM response (player-to-player, intervention engine monitors)
  │
  └─ intent == "meta" ────→ Canned response (rules FAQ, phase info, no LLM)
```

Each agent is a Python class with its own system prompt. Orchestrator calls
them sequentially with async/await. No framework needed.

Key minimum-privilege boundaries:

- Router: sees message text only
- Judge: sees key_facts + player question. Does NOT see truth.culprit directly.
  Receives decomposed facts: “门向外推开” “门前是悬崖” — not “char_c is the killer”
- Narrator: sees judgment + visible context + unlocked clues. CANNOT see truth.
- Safety: sees truth + narrator output. Binary output: safe/leaked.
- NPC: sees own persona + own knowledge boundary. Cannot see other NPCs’ knowledge.

## Things That Will Bite You

- **NEVER let truth.culprit enter ANY LLM prompt before reveal phase.** Decompose
  truth into key_facts for Judge. Narrator never sees truth at all.
- **State machine transitions must be PURE.** No LLM calls, no async IO inside
  transition logic. LLM proposes via tool intent → state machine validates separately.
- **is_culprit field must be stripped** from character data before sending to any
  agent or frontend. Only the reveal phase handler reads it.
- **Voting is a state machine concern, not an LLM concern.** Vote collection,
  validation (one per player, correct phase), tally, and tiebreaker are all
  deterministic code. LLM only generates the reveal narration after votes are in.
- **NPC knowledge boundary is enforced by VisibilityRegistry.** NPC “管家老周”
  knows clue_001 and clue_003 but NOT clue_002. If player asks the butler about
  clue_002’s topic, NPC says “这个我不清楚” — because its prompt doesn’t have that info.
- **Phase timeout auto-advances.** If discussion runs out, voting starts whether
  players are ready or not. Frontend must show countdown timer clearly.
- **MiniMax JSON not guaranteed.** try/except everywhere. `<think>` tags: strip
  before display, preserve in history.
- **Public DM/NPC responses must NEVER contain another player’s secret_bio.**
  VisibilityRegistry + Safety Agent double-check.
- **WebSocket message ordering.** asyncio.Queue per room. Serialize state-mutating ops.

## Prompt Assembly Order (Phase 4 — per agent)

**Judge Agent:**

1. System: “You judge whether a player’s question/statement aligns with known facts.
   Output ONLY: {judgment, confidence, relevant_fact_ids}. No natural language.”
1. System: key_facts list (decomposed from truth, NO culprit identity)
1. System: current phase + allowed context for this phase
1. User: player’s message

**Narrator Agent:**

1. System: DM persona + phase-specific behavior rules
1. System: judgment result from Judge (e.g., “是, confidence:0.9”)
1. System: player’s visible context (from VisibilityRegistry — public + own secrets)
1. System: unlocked clues this player has seen
1. System: “You do NOT know the truth. Generate an in-character DM response.”
1. Messages: recent conversation history (public or private depending on context)
1. User: player’s original message

**NPC Agent:**

1. System: NPC persona (name, personality, speech style)
1. System: NPC knowledge boundary (only clues this NPC knows about)
1. System: “Stay in character. If asked about things you don’t know, say so in character.”
1. Messages: recent conversation involving this NPC
1. User: player’s message directed at this NPC

**Safety Agent:**

1. System: truth (full), key_facts, all character secret_bios
1. System: “Check if the following text leaks any secret information.”
1. User: narrator/NPC output text
1. Output: {safe: bool, leaked_content: str | null}

## Testing Approach

- **State machine (no LLM):** Transitions, guards, timeout, allowed actions per phase
- **Voting (no LLM):** Collection, one-per-player, tiebreaker, edge cases
- **Each agent independently:** Judge accuracy, Narrator cannot leak (it has no truth),
  Safety catches leaks, Router classifies correctly
- **Pipeline integration (mock LLM):** Full message flow through all agents
- **Red team (real LLM):** Cross-player leaks, social engineering, NPC boundary probing,
  phase-inappropriate actions
- **All previous Phase 1-3 tests must still pass**

## Design Decisions Log

- **MiniMax as primary LLM:** OpenAI SDK compatible, cheap, good Chinese, China-ready.
- **Hints-as-pseudo-clues (A+C pattern):** Phase 1 UI trick, Phase 2+ real unlock.
- **Native Python orchestrator over LangGraph:** Agent flow is pipeline, not graph.
  No conditional loops, no checkpoint, no dynamic routing. Revisit if NPC-to-NPC
  dialogue needed.
- **Intervention: canned strings for gentle level:** 90% zero-cost interventions.
- **Judge sees key_facts, not raw truth:** Extra safety layer. Even if Judge prompt
  is extracted, it doesn’t contain “X is the killer.”
- **Turtle soup mode preserved:** All Phase 1-3 functionality still works. Script
  mode is a new game type, not a replacement.