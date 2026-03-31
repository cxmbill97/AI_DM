# AI DM — 海龟汤 & 剧本杀

AI-hosted deduction game platform. Supports two game modes:

- **海龟汤 (Turtle Soup)** — players ask yes/no questions to deduce a hidden truth. Single-player or multiplayer (2–4 players via WebSocket rooms).
- **剧本杀 (Murder Mystery)** — structured multi-phase investigation. Each player is assigned a character with a public bio and a private secret. An AI DM hosts the entire session: opening narration → character reading → investigation → discussion → voting → reveal.

## Prerequisites

- Python 3.12+ with [uv](https://docs.astral.sh/uv/)
- Node.js 18+ with [pnpm](https://pnpm.io/)
- A MiniMax API key (`base_url: https://api.minimax.io/v1`, model: `MiniMax-M2.5`)

## Setup

### Backend

```bash
cd backend
cp .env.example .env          # fill in MINIMAX_API_KEY
uv sync                       # install all deps (including dev)
uv run uvicorn app.main:app --reload
# REST API + WebSocket at http://localhost:8000
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
# UI at http://localhost:5173 (proxied to backend)
```

## Running Tests

```bash
cd backend

# All unit tests (mock LLM, fast — ~0.5 s)
uv run pytest tests/ -x -v

# Integration / red-team tests (real MiniMax API, slow)
uv run pytest tests/ -x -v --slow

# Targeted suites
uv run pytest tests/test_state_machine.py -x -v   # phase state machine
uv run pytest tests/test_voting.py        -x -v   # vote collection + tiebreaker
uv run pytest tests/test_agents.py        -x -v   # multi-agent pipeline (mock LLM)
uv run pytest tests/test_redteam.py       -x -v --slow  # adversarial red-team
```

Current baseline: **322 passed, 27 skipped** (slow tests skipped without `--slow`).

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI: REST endpoints + WebSocket /ws/{room_id}
│   ├── llm.py               # MiniMax client (OpenAI SDK compatible)
│   ├── models.py            # All Pydantic models (Puzzle, Script, Character, …)
│   ├── puzzle_loader.py     # Load puzzle/script JSON from data/
│   ├── room.py              # Room manager: create/join/leave, broadcast
│   ├── ws.py                # WebSocket handler: message routing, phase ticks
│   ├── intervention.py      # Phase-aware DM intervention engine
│   ├── visibility.py        # VisibilityRegistry: per-player context filter
│   ├── state_machine.py     # Deterministic phase state machine (pure, no LLM)
│   ├── voting.py            # VotingModule: one-per-player, tiebreaker, runoff
│   ├── dm.py                # Legacy single-call DM (turtle soup mode)
│   ├── npc.py               # (unused stub — NPC logic is in agents/npc.py)
│   └── agents/
│       ├── orchestrator.py  # Pipeline: Router → Judge → Narrator → Safety
│       ├── router.py        # Intent classifier (pure rules, <1 ms, no LLM)
│       ├── judge.py         # Truth judgment (sees key_facts, not culprit identity)
│       ├── narrator.py      # Response generation (never sees truth before reveal)
│       ├── safety.py        # Leak detection (sees truth + narrator output)
│       └── npc.py           # NPC agent: persona prompt + knowledge boundary
├── data/
│   ├── puzzles/             # Turtle soup puzzle JSON files
│   └── scripts/             # Murder mystery script JSON files
│       └── rain_night_001.json
├── tests/
│   ├── conftest.py          # Fixtures: MockLLM, real_llm guard, sample_puzzle
│   ├── test_dm.py           # DM correctness (turtle soup)
│   ├── test_clues.py        # Clue unlock logic
│   ├── test_room.py         # Room join/leave/broadcast
│   ├── test_intervention.py # Intervention engine: silence timer, backoff
│   ├── test_visibility.py   # VisibilityRegistry: per-player context isolation
│   ├── test_private_chat.py # Private DM chat (turtle soup)
│   ├── test_state_machine.py # Phase transitions, guards, timeout
│   ├── test_voting.py       # Vote collection, tiebreaker, runoff, edge cases
│   ├── test_agents.py       # Each agent + full pipeline (mock LLM)
│   └── test_redteam.py      # Adversarial: spoiler-proofing + Phase 4 attacks
└── pyproject.toml

frontend/
├── src/
│   ├── App.tsx              # Routes: / Lobby, /play Single-player, /room/:id Room
│   ├── api.ts               # Typed fetch() wrappers for REST endpoints
│   ├── pages/
│   │   ├── LobbyPage.tsx    # Mode tabs (海龟汤 / 剧本杀), puzzle/script picker, join room
│   │   ├── GamePage.tsx     # Single-player turtle soup Q&A
│   │   └── RoomPage.tsx     # Multiplayer: turtle soup layout + murder mystery layout
│   ├── components/
│   │   ├── PuzzleCard.tsx   # Turtle soup surface display
│   │   ├── ScriptCard.tsx   # MM character bio + private secret + personal script
│   │   ├── PhaseBar.tsx     # MM phase progress + countdown timer (warns at <30 s)
│   │   ├── VotePanel.tsx    # MM vote UI: suspect selection + animated results
│   │   ├── ChatPanel.tsx    # Chat with public/private toggle + NPC message styling
│   │   ├── CluePanel.tsx    # Shared unlocked clue cards
│   │   ├── PrivateCluePanel.tsx  # Player's private clues/secrets
│   │   ├── PlayerList.tsx   # Player roster with avatar colors + online status
│   │   └── HintBar.tsx      # Progress bar + hint display (turtle soup)
│   └── hooks/
│       ├── useChat.ts       # Single-player: REST-based Q&A
│       └── useRoom.ts       # Multiplayer: WebSocket + all MM message types
└── vite.config.ts           # Proxy /api → localhost:8000, /ws → ws://localhost:8000
```

## API Reference

### Turtle Soup

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/puzzles` | List available puzzles (id, title, difficulty, tags) |
| `POST` | `/api/start` | Start single-player session → `session_id` + `surface` |
| `POST` | `/api/chat` | Send question → DM judgment + response + truth_progress |
| `GET`  | `/health` | Health check |

### Multiplayer Rooms

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/rooms` | Create room (`game_type`, optional `puzzle_id` / `script_id`) |
| `GET`  | `/api/rooms/{room_id}` | Current room state (players, phase, title) |
| `GET`  | `/api/scripts` | List available murder mystery scripts |
| `WS`   | `/ws/{room_id}?player_name=…` | Join room (real-time multiplayer) |

### WebSocket Message Types

**Client → Server**

| `type` | Fields | Description |
|--------|--------|-------------|
| `chat` | `text` | Public message / question |
| `private_chat` | `text` | Private DM question (turtle soup) |
| `vote` | `target` | Cast vote for character id (murder mystery) |

**Server → Client**

| `type` | Description |
|--------|-------------|
| `room_snapshot` | Full state on connect (players, phase, game_type) |
| `system` | System notification |
| `player_message` | Another player's chat message |
| `dm_response` | DM answer (judgment + response for TS; text for MM) |
| `dm_intervention` | Proactive DM message (silence detection) |
| `phase_change` | MM phase advanced (new_phase, duration, description) |
| `character_assigned` | Character assigned to player |
| `character_secret` | Private: player's own secret_bio + personal_script |
| `clue_found` | A clue was discovered |
| `vote_prompt` | Voting phase started, includes candidate list |
| `vote_cast` | Anonymous vote count update |
| `vote_result` | Final tally + winner + is_correct |
| `phase_blocked` | Action not allowed in current phase |
| `private_dm_response` | Private DM reply (turtle soup only) |
| `leak_warning` | Verbatim clue leak detected in player message |
| `error` | Error message |

## Murder Mystery — How It Works

### Game Flow

```
Lobby → Create MM room (select script) → Share room code →
Players join → Characters auto-assigned (join order) →

opening     (DM narrates the case setup)
reading     (each player reads their own character script privately)
investigation_1  (ask DM, search for clues, private chat with DM)
discussion  (share reasoning publicly)
voting      (each player votes for the culprit; anonymous until all in)
reveal      (DM narrates the truth; vote tally shown)
```

### Multi-Agent Pipeline

Each player message in murder mystery mode routes through:

```
Player message
  └── RouterAgent  (rules-only, <1 ms)
        ├── vote    → VotingModule (pure logic)
        ├── search  → ClueSystem → Narrator
        ├── npc     → NPCAgent (persona + knowledge boundary)
        ├── question/accuse → Judge → Narrator → Safety (retry ×2)
        ├── meta    → Canned response (no LLM)
        └── chat    → No DM reply (intervention engine monitors)
```

**Minimum-privilege design:**
- Judge sees `key_facts` only — never `truth.culprit`
- Narrator never sees `truth` at all before reveal phase
- Safety sees truth + narrator output; blocks if leak detected
- NPC only knows clues in its `knowledge` list

### Phase State Machine

Transitions are deterministic and pure (no LLM calls):

| Phase | Duration | Allowed actions |
|-------|----------|-----------------|
| `opening` | 2 min | listen |
| `reading` | 5 min | read_script |
| `investigation_1` | 10 min | ask_dm, search, private_chat |
| `discussion` | 10 min | public_chat, private_chat |
| `voting` | 2 min | cast_vote |
| `reveal` | unlimited | listen |

Timeout always forces advance — the game never stalls. Each phase timer is visible in the UI with a warning flash when < 30 seconds remain.

### Murder Mystery Script Format

Scripts live in `backend/data/scripts/` as JSON. Key schema:

```jsonc
{
  "id": "rain_night_001",
  "title": "雨夜迷踪",
  "metadata": { "player_count": 4, "difficulty": "beginner" },
  "characters": [
    { "id": "char_a", "name": "林晓", "public_bio": "...", "secret_bio": "...", "is_culprit": false }
  ],
  "phases": [ /* phase definitions with allowed_actions, duration_seconds */ ],
  "clues": [
    { "id": "clue_001", "title": "监控时间戳", "content": "...", "unlock_keywords": ["监控"] }
  ],
  "npcs": [
    { "id": "npc_butler", "name": "管家老周", "persona": "...", "knowledge": ["clue_001"] }
  ],
  "truth": {
    "culprit": "char_c",
    "motive": "...", "method": "...", "timeline": "...",
    "key_facts": ["...", "..."]
  }
}
```

`truth.culprit` and `is_culprit` never enter any LLM prompt before the reveal phase.

## DM Intervention Engine

Runs a background tick every 5 seconds per room. Phase-aware:

- `opening`, `reading`, `reveal` — silent (no intervention)
- `voting` — vote reminder only after prolonged silence
- `investigation`, `discussion` — full silence backoff:

| Elapsed silence | Level | Behavior |
|-----------------|-------|----------|
| > 45 s | gentle | Canned encouragement (no LLM, zero cost) |
| > 90 s | nudge | LLM-generated encouragement (≤ 30 chars) |
| > 180 s | hint | LLM-generated guiding hint (≤ 50 chars, no spoilers) |

Thresholds double after each nudge (45 → 90 → 180 → 240 s cap).
Global cooldown: 15 s minimum between any two DM messages.

## Security Invariants

These are enforced at multiple layers and tested by `test_redteam.py`:

1. **Truth never leaks before reveal** — Narrator has no truth in its prompt; Safety agent double-checks every output.
2. **Cross-character secrets are isolated** — VisibilityRegistry ensures player A cannot see player B's `secret_bio`.
3. **NPC knowledge boundary** — NPCs only know clues in their `knowledge` list; the LLM cannot hallucinate unknown clue content.
4. **Phase guards are deterministic** — Actions outside a phase's `allowed_actions` are rejected before any LLM call.
5. **Voting integrity** — One vote per player, no changes after submit; tally only revealed after all votes are in.
