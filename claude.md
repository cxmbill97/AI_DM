# CLAUDE.md

## Commands

```bash
cd backend && uv run uvicorn app.main:app --reload          # API server (port 8000)
cd backend && uv run pytest tests/ -x -v                     # all tests
cd backend && uv run pytest tests/test_redteam.py -x -v      # anti-spoiler red team
cd frontend && pnpm dev                                       # React dev (port 5173)
```

## Project Overview

AI-powered host for “Turtle Soup” (海龟汤) lateral thinking puzzles, evolving toward
a full 剧本杀 (murder mystery) AI DM system.

**Current state (Phase 2 complete):**

- Single-player REST mode + multiplayer WebSocket rooms (2-4 players)
- Clue card system: passive (hint-as-card) + active (keyword unlock)
- DM intervention engine: silence detection, explicit triggers, cooldowns
- Anti-spoiler defense: prompt engineering + post-generation regex safety net

**Next: Phase 3 — Collaborative reasoning with information asymmetry.**
Each player gets different private clue fragments. VisibilityRegistry controls
what each player can see. DM gives per-player responses. This is the bridge to
full 剧本杀 where every player holds different secrets.

**Core principle: Deterministic State > LLM Output.**

## Architecture

```
backend/
├── app/
│   ├── main.py               # FastAPI: REST endpoints + WebSocket /ws/{room_id}
│   ├── dm.py                  # DM logic: prompt assembly, response parse, clue unlock
│   ├── llm.py                 # MiniMax client via OpenAI SDK
│   ├── models.py              # Pydantic: Puzzle, Clue, GameSession, Room, Player
│   ├── puzzle_loader.py       # Load puzzle JSON from data/puzzles/
│   ├── room.py                # Room manager: create/join/leave, broadcast, state
│   ├── ws.py                  # WebSocket handler: message routing, DM calls
│   ├── intervention.py        # DM intervention engine: silence, triggers, cooldowns
│   ├── visibility.py          # [Phase 3] VisibilityRegistry: per-player context filter
│   └── agents/                # [Phase 4] Multi-agent split
│       ├── router.py          # [Phase 4] Intent classifier (rules, no LLM)
│       ├── judge.py           # [Phase 4] Truth judgment (sees truth, outputs 1 word)
│       ├── narrator.py        # [Phase 4] Response generation (CANNOT see truth)
│       └── safety.py          # [Phase 4] Leak detection (sees truth + output)
├── data/puzzles/               # Puzzle JSON files (surface, truth, clues, private_clues)
├── tests/
│   ├── test_dm.py              # DM correctness
│   ├── test_clues.py           # Clue unlock logic (passive + active)
│   ├── test_redteam.py         # Anti-spoiler adversarial tests
│   ├── test_room.py            # Multiplayer room tests
│   ├── test_intervention.py    # Intervention engine tests
│   ├── test_visibility.py      # [Phase 3] Per-player visibility isolation
│   └── conftest.py
└── pyproject.toml

frontend/
├── src/
│   ├── App.tsx                 # Routes: / → Lobby, /play → SinglePlayer, /room/:id → Room
│   ├── components/
│   │   ├── ChatPanel.tsx       # Messages + input (public/private toggle in Phase 3)
│   │   ├── PuzzleCard.tsx      # Surface story display
│   │   ├── CluePanel.tsx       # Unlocked shared clue cards
│   │   ├── ProgressBar.tsx     # truth_progress 0-100
│   │   ├── PlayerList.tsx      # Players in room with online/offline status
│   │   └── PrivateCluePanel.tsx # [Phase 3] "我的秘密线索" — only this player sees
│   ├── hooks/
│   │   ├── useChat.ts          # Single-player REST
│   │   └── useRoom.ts          # Multiplayer WebSocket
│   ├── pages/
│   │   ├── LobbyPage.tsx       # Create/join room or single-player
│   │   ├── RoomPage.tsx        # Multiplayer game
│   │   └── GamePage.tsx        # Single-player game (original)
│   └── api.ts
└── vite.config.ts
```

## Key Concepts

1. **Clue Card System (two modes):**
- Passive: hints[] wrapped as visual cards when should_hint=true (sequential)
- Active: clues[] unlocked when player message matches unlock_keywords
  Both modes coexist — active fires first, passive is fallback.
1. **DM Intervention Engine:**
- Tier 1 (rules, <1ms): @DM mention, “提示”/“线索”/“帮” keywords, silence >45s
- Tier 2 (lightweight LLM): only when Tier 1 returns “maybe”
- Gentle silence (canned strings, no LLM) → Nudge → Hint (LLM call)
- Cooldown: 15s global. Exponential backoff on silence: 45s → 90s → 180s → 240s cap.
- Only active in multiplayer rooms, not single-player.
1. **MiniMax API:** OpenAI SDK compatible. `base_url="https://api.minimax.io/v1"`.
   Model: “MiniMax-M2.5”. JSON output not guaranteed — always try/except with fallback.
   Strip `<think>` tags before display, preserve in conversation history.
1. **GameSession / Room:** Sessions are in-memory dicts. Room holds shared puzzle,
   player list, message history, unlocked_clue_ids. Single-player uses REST,
   multiplayer uses WebSocket. Both share DM logic in dm.py.
1. **[Phase 3] VisibilityRegistry:** Maps (player_id) → visible context. Each player
   sees: public surface + own private clues + shared unlocked clues. DM sees full
   picture (all players’ clues + truth) to judge fairly, but responds based on the
   asking player’s visible context only. Public chat responses use only public info.
   Private chat responses can reference the player’s own private clues.
1. **[Phase 4] Multi-Agent Split:** Current “fat DM” single LLM call becomes a
   pipeline of specialized agents. Key insight: Narrator Agent CANNOT see truth
   (minimum privilege). Judge Agent sees truth but only outputs one word.
   Using native Python orchestrator pattern, not LangGraph — our agent flow is a
   pipeline not a graph, framework overhead not justified for current complexity.

## Puzzle JSON Schema

```json
{
  "id": "turtle_001",
  "title": "夜半敲门",
  "surface": "一个人住在山顶的小屋里...",
  "truth": "小屋的门向外推开，门前就是悬崖...",
  "key_facts": ["小屋的门向外推开", "门外就是悬崖", ...],
  "clues": [
    {"id": "clue_door", "title": "小屋建筑图纸",
     "content": "一张泛黄的图纸显示：正门采用外推式设计...",
     "unlock_keywords": ["门", "开门", "推门"]}
  ],
  "hints": ["想想这个门的开法有什么特别的？", ...],
  "private_clues": {
    "player_1": [{"id": "priv_a1", "title": "...", "content": "..."}],
    "player_2": [{"id": "priv_b1", "title": "...", "content": "..."}]
  },
  "difficulty": "classic",
  "tags": ["经典", "物理诡计"]
}
```

`private_clues` is optional — standard puzzles omit it (Phase 1/2 mode).
When present, room assigns player slots on join order.

## Things That Will Bite You

- **NEVER let truth appear in LLM output.** Truth is in system prompt for judgment.
  Post-generation regex scans key_facts as safety net.
- **Clue content must not state the full answer.** Each clue hints at one aspect.
  If reading all clues together reveals everything, they’re too explicit.
- **MiniMax JSON output is not guaranteed.** Always try/except. Fallback: raw text
  as response, judgment=“unknown”.
- **MiniMax `<think>` tags:** Strip before display, preserve in history.
- **Clue unlock matching is fuzzy.** Keyword-in-message, not exact match.
  “门是怎么打开的” should match [“门”, “开门”].
- **WebSocket messages NOT ordered across players.** asyncio.Queue per room.
  DM serializes state-mutating operations.
- **Intervention background task MUST be cancelled** when room is destroyed.
  Otherwise asyncio task leak.
- **[Phase 3] Public DM response must NEVER contain another player’s private clue.**
  This is the #1 invariant. Post-generation check using VisibilityRegistry.
- **[Phase 3] Leak detection uses similarity, not exact match.** Paraphrasing own
  clue is OK and encouraged. Only block near-verbatim copy (>50% overlap).
- **Chinese text for game content.** Code and variable names in English.

## DM Response Schema

```json
{
  "judgment": "是|不是|无关|部分正确",
  "response": "DM回复文本",
  "truth_progress": 45,
  "should_hint": false,
  "clue_unlocked": null | {"id": "...", "title": "...", "content": "..."},
  "audience": "public"
}
```

Phase 3 adds: `audience: "public" | "private"` — private responses only sent to
the asking player.

## Prompt Assembly Order

1. System: DM persona + rules (是/不是/无关/部分正确)
1. System: surface (汤面, public)
1. System: truth (汤底, TOP SECRET — never repeat)
1. System: key_facts (for matching accuracy)
1. System: unlocked shared clues (can reference in response)
1. System: [Phase 3] THIS player’s private clues (from VisibilityRegistry)
1. System: [Phase 3] Summary of what each player knows (titles only, not content)
1. System: [Phase 3] “In PUBLIC chat, only use public info + this player’s clues.
   NEVER reveal other players’ private info.”
1. System: locked clue IDs (DM knows they exist, cannot reveal content)
1. System: JSON output schema
1. Messages: conversation history
1. User: current player message

## Testing Approach

- **Unit (no LLM):** State machine, clue unlock, intervention triggers, cooldowns
- **Integration (mock LLM):** DM flow with deterministic mock responses
- **Red team (real LLM, mark slow):** Adversarial prompts → zero truth leakage
- **Room tests:** Join/leave, broadcast, concurrent messages, reconnection
- **[Phase 3] Visibility tests:** Different players see different things, public
  DM never leaks private info, cross-player leak attempts blocked

## Design Decisions Log

- **MiniMax over Claude/GPT for MVP:** OpenAI SDK compatible, cheap, good Chinese,
  domestic (China-ready). Provider abstraction layer planned for Phase 4+.
- **Hints-as-pseudo-clues (A+C pattern):** Phase 1 wraps hints as card UI. Phase 2
  adds real keyword-triggered unlock. Both coexist.
- **Native Python orchestrator over LangGraph:** Agent flow is a pipeline, not a
  graph. No conditional loops, no checkpoint/resume, no dynamic routing. Framework
  overhead not justified. Will reconsider if NPC-to-NPC dynamic dialogue is needed.
- **Intervention engine: canned strings for gentle level:** 90% of interventions
  are zero-cost. Only nudge/hint level triggers LLM call.