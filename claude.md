# CLAUDE.md

## Commands

```bash
cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0   # API (port 8000)
cd backend && uv run pytest tests/ -x -v                             # all tests
cd backend && uv run pytest tests/ -x -v --ignore=tests/test_eval.py # skip slow LLM tests
cd backend && uv run python -m eval --scenarios all                  # eval harness
cd backend && uv run python -m mcp_server                            # MCP server (stdio)
cd frontend && pnpm dev --host 0.0.0.0                               # UI (port 5173)
./start.sh                                                            # one-command startup
```

## Project Overview

AI-powered game master for multiplayer social deduction games: Turtle Soup (海龟汤)
and Murder Mystery (剧本杀). Bilingual (zh/en). Multi-agent architecture with
minimum-privilege context isolation.

**Completed phases:**

- Phase 1: Single-player turtle soup
- Phase 2: Multiplayer + clue system + DM intervention
- Phase 3: VisibilityRegistry + per-player private clues
- Phase 4: 剧本杀 + multi-agent pipeline + voting + NPC
- Phase 5: Bilingual (zh/en) + LAN access
- Phase 6: Remote access (ngrok/cloudflare) + demo packaging + 3-player reconstruction mode
- Phase 7: Agent Trace + Eval Harness (114 scenarios) + MCP Server
- Phase 8: Auth (Google/Apple OAuth + JWT) + community library + script/puzzle upload
- Phase 9: iOS native app (SwiftUI) + multiplayer lobby (ready-up flow)

**All phases complete. No active next phase.**

**Core principle: Deterministic State > LLM Output.**

## Architecture

```
backend/
├── app/
│   ├── main.py             # FastAPI app + all REST endpoints
│   ├── llm.py              # LLM client wrapper (MiniMax/OpenAI-compatible)
│   ├── models.py           # Pydantic data models
│   ├── puzzle_loader.py    # Load/list puzzles and scripts from disk
│   ├── room.py             # Room state + lobby fields (started, max_players, host, ready_players)
│   ├── ws.py               # WebSocket multiplayer handler + lobby WS events
│   ├── visibility.py       # Per-player private clue access control
│   ├── intervention.py     # DM hint injection heuristics
│   ├── state_machine.py    # Phase transitions
│   ├── voting.py           # Vote tallying, tie resolution, runoffs
│   ├── auth.py             # Google/Apple OAuth, JWT, SQLite user/favorites/history
│   ├── community.py        # Community script metadata (likes, author) — SQLite
│   ├── doc_extractor.py    # PDF/DOCX/TXT file text extraction
│   ├── config.py           # Settings (env vars, JWT secret, Google client id, etc.)
│   ├── npc.py
│   ├── dm.py               # Single-player DM turn logic
│   └── agents/
│       ├── orchestrator.py     # Pipeline + trace collection
│       ├── router.py
│       ├── judge.py
│       ├── narrator.py
│       ├── safety.py
│       ├── doc_parser.py       # LLM-based script parser (PDF/DOCX → script JSON)
│       ├── puzzle_parser.py    # LLM-based puzzle parser (raw text → puzzle JSON)
│       └── trace.py            # TraceStep, AgentTrace dataclasses
├── eval/                        # Evaluation harness
│   ├── __main__.py              # CLI entry: python -m eval
│   ├── scenarios.py             # EvalScenario dataclass + loader
│   ├── runner.py                # Run scenarios against agents, collect results
│   ├── report.py                # Generate markdown report from results
│   ├── data/
│   │   ├── judge_scenarios.json     # 58 scenarios (48 accuracy + 10 edge_case)
│   │   └── redteam_scenarios.json   # 56 adversarial prompts
│   └── reports/                 # Generated reports (gitignored except examples)
├── mcp_server/                  # MCP Server
│   ├── __main__.py              # Entry: python -m mcp_server
│   └── server.py                # FastMCP server with game tools
├── data/
│   ├── puzzles/{zh,en}/         # Turtle soup puzzle JSON files
│   ├── scripts/{zh,en}/         # Murder mystery script JSON files
│   ├── auth.db                  # SQLite: users, favorites, history
│   └── community.db             # SQLite: community script metadata
└── tests/
    ├── test_agents.py           # Judge, narrator, safety, router agents
    ├── test_auth.py             # Auth endpoints and JWT flow
    ├── test_room.py             # Multiplayer game flow
    ├── test_room_lobby.py       # Lobby ready-up and host-start flow
    ├── test_state_machine.py    # Phase transitions
    ├── test_voting.py           # Vote tallying and tie resolution
    ├── test_visibility.py       # Per-player clue visibility
    ├── test_clues.py            # Clue unlock logic
    ├── test_redteam.py          # Safety agent redteam prompts
    ├── test_trace.py            # Trace collection, sanitization, cost
    ├── test_eval.py             # Eval harness (slow: requires MINIMAX_API_KEY)
    ├── test_mcp.py              # MCP server tool tests
    ├── test_i18n.py             # Bilingual response checks
    ├── test_intervention.py     # DM hint injection
    ├── test_private_chat.py     # Private clue chat
    ├── test_dm.py               # Single-player DM logic
    ├── test_latency.py          # Latency benchmarks
    ├── sim_two_players.py       # Live two-player murder mystery simulation
    └── sim_three_recon.py       # Live three-player reconstruction simulation

frontend/
├── src/
│   ├── auth.tsx                 # AuthContext + AuthProvider + useAuth hook
│   ├── api.ts                   # REST + auth/favorites/history API calls
│   ├── App.tsx                  # Routes: Lobby, Login, Profile, Room, SinglePlayer
│   ├── pages/
│   │   ├── LobbyPage.tsx        # Sidebar layout, card grid, favorites, theme switcher
│   │   ├── LoginPage.tsx        # Google OAuth login
│   │   ├── ProfilePage.tsx      # Favorites tab + history tab
│   │   ├── RoomPage.tsx         # Multiplayer game UI (WebSocket)
│   │   └── SinglePlayerPage.tsx # Single-player turtle soup UI
│   ├── components/
│   │   ├── ChatPanel.tsx
│   │   ├── CluePanel.tsx
│   │   ├── HintBar.tsx
│   │   ├── LanguageToggle.tsx
│   │   ├── PhaseBar.tsx
│   │   ├── PlayerList.tsx
│   │   ├── PrivateCluePanel.tsx
│   │   ├── PuzzleCard.tsx
│   │   ├── PuzzleUploadModal.tsx    # Upload puzzle (text → LLM parse → save)
│   │   ├── ReconstructionPanel.tsx  # 3-player reconstruction phase UI
│   │   ├── ScriptCard.tsx
│   │   ├── ScriptUploadModal.tsx    # Upload script (PDF/DOCX/TXT → LLM parse → save)
│   │   ├── TracePanel.tsx           # Expandable agent decision trace (debug)
│   │   └── VotePanel.tsx
│   ├── hooks/
│   │   ├── useRoom.ts           # WebSocket state hook (main multiplayer logic)
│   │   └── useTraceSetting.ts
│   └── i18n/
│       ├── en.json
│       ├── zh.json
│       └── index.tsx
└── ...

ios/                             # Native iOS app (SwiftUI)
├── AIDungeonMaster.xcodeproj/
└── AIDungeonMaster/
    ├── App/                     # Entry point, tab bar, content view
    ├── Auth/                    # Google + Apple OAuth login view/viewmodel
    ├── Home/                    # Home feed
    ├── Explore/                 # Browse puzzles/scripts
    ├── Lobby/                   # Game lobby + WaitingRoom (ready-up flow)
    ├── Room/                    # WebSocket gameplay view/viewmodel
    ├── Activity/                # Activity feed
    ├── Profile/                 # User profile + favorites
    ├── Saved/                   # Saved games
    ├── Settings/
    ├── Models/                  # Shared Swift model types
    └── Services/
        ├── APIService.swift         # REST API calls
        ├── WebSocketService.swift   # WS connection
        └── KeychainService.swift    # JWT token storage
```

## REST API Endpoints

```
GET  /health
GET  /auth/config                          # returns Google client_id for frontend
GET  /auth/dev-login                       # dev-only token (no OAuth)
GET  /auth/google                          # redirect to Google OAuth
GET  /auth/google/callback                 # OAuth callback → JWT
GET  /auth/google/mobile                   # mobile OAuth flow
GET  /auth/google/mobile/callback
POST /auth/apple                           # Apple Sign-In → JWT
GET  /api/me                               # current user profile
GET  /api/favorites                        # user's favorited puzzles/scripts
POST /api/favorites/{item_type}/{item_id}  # add favorite
DEL  /api/favorites/{item_type}/{item_id}  # remove favorite
GET  /api/history                          # user's game history
GET  /api/puzzles                          # list puzzles (?lang=zh|en)
POST /api/puzzles/upload                   # upload raw text → LLM parse → save puzzle
POST /api/start                            # create single-player session
POST /api/chat                             # single-player DM turn
GET  /api/scripts                          # list scripts (?lang=zh|en)
POST /api/scripts/upload                   # upload PDF/DOCX/TXT → LLM parse → save script
GET  /api/rooms                            # list active rooms
POST /api/rooms                            # create multiplayer room
GET  /api/rooms/{room_id}                  # room state
POST /api/rooms/{room_id}/start            # host starts the game (lobby → playing)
POST /api/rooms/{room_id}/complete         # mark game complete
PATCH /api/rooms/{room_id}                 # update room settings
GET  /api/community/scripts                # list community-uploaded scripts
POST /api/community/scripts/{id}/like      # like a community script
WS   /ws/{room_id}                         # multiplayer WebSocket
```

## Key Concepts

1. **Agent Trace:**
   Each player message produces an AgentTrace — a list of TraceSteps recording
   every agent's input, output, latency, and token usage. Traces are:
   - Returned in WebSocket/REST responses (optional field, hidden by default)
   - Displayed in a collapsible TracePanel in the frontend
   - Stored in game_events for replay
   - Used by the eval harness for automated scoring

   ```python
   @dataclass
   class TraceStep:
       agent: str          # "router" | "judge" | "narrator" | "safety"
       input_summary: str  # truncated input for display (no secrets)
       output_summary: str # truncated output
       latency_ms: float
       tokens_in: int
       tokens_out: int
       metadata: dict      # agent-specific: judgment, confidence, matched_facts, etc.

   @dataclass
   class AgentTrace:
       message_id: str
       player_id: str
       steps: list[TraceStep]
       total_latency_ms: float
       total_tokens: int
       total_cost: float   # calculated from provider pricing
   ```

   IMPORTANT: TraceStep.input_summary for Judge must NOT include raw key_facts
   or truth. Show only: "key_facts: 5 items" or similar. The trace is visible
   to players in debug mode — it must not leak secrets.

2. **Auth System:**
   JWT-based auth. Google and Apple OAuth supported. SQLite-backed user store
   (`data/auth.db`). Token is passed as `?token=` query param on WebSocket and
   `Authorization: Bearer` on REST. Auth is optional — unauthenticated users can
   still play, but can't use favorites or history.

3. **Multiplayer Lobby:**
   Room lifecycle: `lobby → playing → voting → reconstruction → finished`.
   Room gains fields: `host_player_id`, `max_players`, `ready_players`, `started`.
   Host calls `POST /api/rooms/{id}/start` to move from lobby to playing. WS events:
   `lobby_update` (player ready state), `game_started` (transition to play phase).

4. **Script/Puzzle Upload:**
   Users can upload raw text (puzzle) or PDF/DOCX/TXT (script). The backend extracts
   text via `doc_extractor.py`, then passes it to `puzzle_parser.py` or `doc_parser.py`
   (LLM agents) to produce a structured JSON. The parsed content is saved to disk and
   registered in `community.db`.

5. **Eval Harness:**
   Offline batch evaluation. Loads scenarios from JSON, runs them through agents,
   computes metrics, outputs markdown report.

   Metrics:
   - Judge accuracy: exact match against expected_judgment
   - Leakage rate: % of adversarial prompts where key_facts appear in output
   - Safety catch rate: % of leaks caught by Safety Agent
   - End-to-end leak rate: leaks that escape the full pipeline
   - Latency: P50/P95 per agent and total
   - Cost: per-scenario and projected per-session

   Latest results (2026-04-01, minimax): 58.6% judge accuracy, 7.1% leak rate.
   Known gap: 40% leak rate in `indirect_extraction` subcategory.

   CLI: `python -m eval --scenarios all`
   Output: `eval/reports/{provider}_{date}.md`

6. **MCP Server:**
   Exposes the game engine as MCP tools via stdio transport. Any MCP-compatible
   client (Claude Desktop, Cursor, custom agent) can play the game.

   Tools:
   - list_puzzles(language) → [{id, title, difficulty, tags}]
   - list_scripts(language) → [{id, title, player_count, difficulty, duration}]
   - start_game(puzzle_id, language, player_name) → {session_id, title, surface, instructions}
   - ask_question(session_id, question) → {judgment, response, progress, trace}
   - get_game_status(session_id) → {progress, hints, unlocked_clues, finished}

   Uses FastMCP library. Single-player mode only (no WebSocket multiplayer via MCP).
   The MCP server is a thin wrapper around existing game logic — no new game code.

## Things That Will Bite You

- **Trace input_summary must be sanitized.** Players can toggle trace view in the
  frontend. If Judge's input_summary contains key_facts text, you've leaked secrets
  via the debug panel. Show counts and IDs, not content.
- **Auth is optional everywhere.** All game endpoints work without a token. Auth
  only gates favorites and history. Don't add hard auth requirements to game logic.
- **Two SQLite databases, not one.** `auth.db` holds users/favorites/history.
  `community.db` holds community script metadata. Keep them separate.
- **Lobby WS events are backward-compatible.** Clients that don't understand
  `lobby_update` or `game_started` must not crash. Check the backward-compat flag.
- **Eval harness must use real LLM calls, not mocks.** The whole point is measuring
  actual provider behavior. Mark eval tests as slow, don't run in normal CI.
- **Eval scenarios need deterministic structure.** Each scenario has ONE correct
  expected_judgment. Ambiguous questions should be excluded or marked "flexible".
- **MCP stdio transport blocks.** The MCP server runs as a separate process, not
  inside the FastAPI server. It imports game logic but has its own entry point.
- **iOS uses Keychain for JWT storage.** Never store the token in UserDefaults.
- **All previous caveats still apply.**

## Design Decisions Log

- **Trace as dataclass, not OpenTelemetry:** Our trace is game-specific (agent steps,
  not HTTP spans). OTel adds dependency weight and conceptual overhead.
- **Eval harness as a Python module, not a separate tool:** `python -m eval` keeps
  it in the same repo with direct imports of agent code.
- **MCP single-player only:** Multiplayer requires WebSocket state management that
  doesn't map cleanly to MCP's request-response tool model.
- **Auth is optional, not enforced:** Game is playable without login. Auth unlocks
  personalization (favorites, history) but is never a gate on gameplay.
- **Two SQLite DBs:** auth.db and community.db are intentionally separate to keep
  user PII isolated from community metadata. Easier to wipe/reset independently.
- **Script upload via LLM parse, not rigid schema:** Raw documents vary too much in
  format. An LLM parse step (doc_parser.py) is more robust than regex extraction.
