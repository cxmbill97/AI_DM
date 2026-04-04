# AI DM — 海龟汤 & 剧本杀

> **AI-powered game master for Chinese social deduction games, built with a multi-agent LLM pipeline, real-time WebSocket multiplayer, a React web frontend, and a native iOS app. Supports bilingual (zh/en) gameplay with streaming DM responses, per-player secret isolation, and an automated evaluation harness.**

---

## Project Overview

AI DM is a full-stack multiplayer game platform that uses large language models to host two classic Chinese deduction games entirely autonomously — no human game master needed. Players connect from any device on the same network (or remotely via ngrok/Cloudflare) and interact with an AI DM in real time.

### What it does

**海龟汤 / Turtle Soup** — A lateral-thinking puzzle game. The DM holds a hidden story; players ask yes/no questions to piece together the truth. The AI judges each question against a decomposed fact set, generates atmospheric responses, and escalates hints when players go quiet.

**剧本杀 / Murder Mystery** — A structured whodunit. 2–4 players are each assigned a character with a public backstory and a private secret. The AI DM hosts a six-phase session (opening → reading → investigation → discussion → voting → reveal), answers investigation questions, voices NPC characters, enforces phase rules, and narrates the dramatic reveal — all without ever leaking the solution early.

### Technical highlights

**Multi-agent pipeline with minimum-privilege design**
Each player message flows through a four-agent chain: a rules-based Router classifies intent in <1ms (no LLM), a Judge evaluates truth alignment against decomposed key facts, a Narrator generates atmospheric responses without access to the solution, and a Safety agent blocks any accidental leaks before broadcast. Agents only receive the information they strictly need — the culprit identity and character secrets never appear in any prompt before the reveal phase.

**Real-time streaming**
DM responses stream token-by-token to all players simultaneously using server-sent WebSocket chunks. The frontend renders a typewriter effect with judgment shown immediately (before the full response arrives), so players get feedback in under a second even on slow connections.

**Deterministic game state**
All game rules — phase transitions, allowed actions, vote tallying, skip voting — are enforced by a pure Python state machine with no LLM involvement. The LLM can only respond to what the state machine permits; it cannot advance phases or reveal secrets on its own.

**Observability**
Every LLM call is logged to stdout (real-time) and to a daily JSONL file (full prompt + response for tuning). Every player message produces a structured `AgentTrace` (per-agent latency, token counts, cost) that can be toggled visible in the UI. An offline eval harness runs 58 judge accuracy scenarios and 56 adversarial red-team prompts against the live API, producing a markdown report with P50/P95 latency and projected cost.

**Proactive DM intervention**
The DM does not only react — it monitors the room and speaks up on its own. A background task ticks every 5 seconds and tracks silence per player. When a phase goes quiet, the engine escalates through three levels: a cheap canned encouragement at 45 seconds (no LLM cost), an LLM-generated nudge at 90 seconds, and a contextual hint at 180 seconds that references what the players have already discovered without giving away the answer. Thresholds double after each nudge to avoid spamming, and a global 15-second cooldown prevents two DM messages from overlapping. The intervention engine is phase-aware — it stays silent during opening and reading phases, switches to a vote reminder during voting, and runs the full backoff ladder only during investigation and discussion. This design keeps players engaged without feeling hand-held, and keeps LLM costs near zero for rooms that are actively playing.

**MCP server**
The game engine is exposed as MCP tools over stdio, making it playable from Claude Desktop, Cursor, or any MCP-compatible client without a browser.

### Tech stack

| Layer | Technologies |
|-------|-------------|
| Backend | Python 3.12, FastAPI, WebSocket, asyncio |
| LLM | MiniMax M2.5 via OpenAI-compatible SDK; streaming + non-streaming |
| Web frontend | React 19, TypeScript, Vite, React Router |
| iOS app | SwiftUI, MVVM, URLSession, KeychainServices, Google + Apple Sign-In |
| Real-time | Native WebSocket (auto ws/wss for LAN and tunnel access) |
| Testing | pytest, pytest-asyncio, 400+ test cases including red-team suite |
| CI | GitHub Actions (pytest + ruff + tsc + vite build) |
| Packaging | uv (Python), pnpm (Node); one-command startup via `./start.sh` |

---

## Quick Start

```bash
git clone <repo>
cp backend/.env.example backend/.env   # add your MINIMAX_API_KEY
./start.sh                             # installs deps, starts both servers
```

Open **http://localhost:5173** in your browser. Share the LAN URL printed at startup with friends on the same network.

> **Windows:** run `start.bat` instead of `./start.sh`.

---

## Prerequisites

- Python 3.12+ with [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Node.js 18+ — `brew install node` (macOS) or [nodejs.org](https://nodejs.org)
- [pnpm](https://pnpm.io/) — `npm install -g pnpm`
- A MiniMax API key (`base_url: https://api.minimax.io/v1`, model: `MiniMax-M2.5`)

---

## Manual Setup

### Backend

```bash
cd backend
cp .env.example .env      # fill in MINIMAX_API_KEY
uv sync                   # install Python deps
uv run uvicorn app.main:app --reload --host 0.0.0.0
# REST API + WebSocket at http://localhost:8000
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev --host 0.0.0.0   # UI at http://localhost:5173
```

### iOS App

```bash
cd ios
xcodegen generate
open AIDungeonMaster.xcodeproj   # build & run from Xcode, or:
xcodebuild -scheme AIDungeonMaster -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build
```

Requires Xcode 16+. Point `AppConfig.baseURL` at your backend host. The simulator uses `UserDefaults` for token storage (Keychain requires code-signing on device).

**iOS features:**
- Instagram-style scrollable feed with like, save, and play actions
- Custom gold/purple tab bar (Home · Explore · Activity · Saved · Profile)
- Game mode sheet — choose Solo or Public before creating a room
- Profile page with Games Played (completed only) and Liked tabs
- Real-time room view with clue panel, progress bar, and chat
- Google Sign-In and Apple Sign-In

---

## Remote Access

The frontend WebSocket URL is constructed from the current page's protocol, so all four access modes work without any configuration change:

| Mode | How | URL shape |
|------|-----|-----------|
| Local dev | `./start.sh` | `ws://localhost:5173/ws/…` |
| LAN | other device on same network | `ws://192.168.x.x:5173/ws/…` |
| ngrok | `ngrok http 5173` in a second terminal | `wss://abc123.ngrok-free.app/ws/…` |
| Cloudflare | `cloudflared tunnel --url http://localhost:5173` | `wss://xxx.trycloudflare.com/ws/…` |

The Vite dev server proxies `/ws` to the backend with `ws: true`, so the backend always receives plain `ws://` regardless of how the player connected.

---

## Bilingual Support (zh / en)

The UI language is toggled per-browser and persists in `localStorage`. Game content (puzzles and scripts) is loaded in the language set when the room is created — all players in a room share the same DM language.

| Layer | How |
|-------|-----|
| UI strings | `frontend/src/i18n/zh.json` + `en.json`, toggled by `LanguageToggle` |
| Turtle soup content | `backend/data/puzzles/zh/` and `backend/data/puzzles/en/` |
| Murder mystery content | `backend/data/scripts/zh/` and `backend/data/scripts/en/` |
| DM narration | System prompt language follows `room.language`; English judgments: Yes / No / Irrelevant / Partially correct |
| Intervention messages | Language-aware canned messages; same silence-backoff logic |
| Router intent detection | Chinese and English patterns both supported (?, 吗, what, how, why, search, look, …) |

---

## Running Tests

```bash
cd backend

# Unit tests — mock LLM, ~0.5 s
uv run pytest tests/ -x -v

# Integration / red-team — real MiniMax API
uv run pytest tests/ -x -v --slow

# Targeted suites
uv run pytest tests/test_i18n.py       -x -v   # bilingual puzzle loading + DM language switching
uv run pytest tests/test_state_machine.py -x -v # phase state machine
uv run pytest tests/test_voting.py        -x -v # vote collection + tiebreaker
uv run pytest tests/test_agents.py        -x -v # multi-agent pipeline (mock LLM)
uv run pytest tests/test_redteam.py       -x -v --slow  # adversarial red-team (zh + en)
uv run pytest tests/test_trace.py         -x -v # agent trace collection
uv run pytest tests/test_eval.py          -x -v # eval harness (fast scenarios)
uv run pytest tests/test_mcp.py           -x -v # MCP server tools
```

Current baseline: **408 passed, 44 skipped** (slow tests skipped without `--slow`).

---

## Eval Harness

Batch evaluation of the JudgeAgent against a curated scenario dataset — run offline, no players needed.

```bash
cd backend
uv run python -m eval.run --provider minimax --scenarios all
# Report saved to eval/reports/minimax_YYYYMMDD_HHMM.md
```

**Flags:** `--scenarios 50` (limit count), `--concurrency 5`, `--output path/report.md`, `--dry-run` (list scenarios without running)

**What it measures:**

| Metric | Description |
|--------|-------------|
| Judge accuracy | Exact match against `expected_judgment` (是/不是/无关/部分正确) |
| Redteam leakage rate | % of adversarial prompts that confused the judge (returned non-无关) |
| Latency P50/P95 | Per-scenario latency distribution |
| Cost projection | USD + CNY per scenario and per estimated game session |

Scenario datasets: `eval/data/judge_scenarios.json` (58 accuracy + edge_case scenarios) and `eval/data/redteam_scenarios.json` (56 adversarial scenarios across 6 attack categories). Example report: `eval/reports/minimax_example.md`.

---

## MCP Server

Exposes the game engine as [MCP](https://modelcontextprotocol.io/) tools over stdio, so any MCP-compatible client (Claude Desktop, Cursor, custom agent) can play.

```bash
cd backend
uv run python -m mcp_server
```

**Configure Claude Desktop** — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ai-dm": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/AI_DM/backend", "python", "-m", "mcp_server"]
    }
  }
}
```

See `backend/mcp_config_example.json` for the full example.

**Available tools:**

| Tool | Description |
|------|-------------|
| `list_puzzles(language)` | List available turtle soup puzzles |
| `list_scripts(language)` | List available murder mystery scripts |
| `start_game(puzzle_id, language, player_name)` | Start a single-player session |
| `ask_question(session_id, question)` | Ask the DM a question, get judgment + response |
| `get_game_status(session_id)` | Current progress, unlocked clues, questions asked |

Single-player turtle soup only (multiplayer requires WebSocket and does not map to MCP's request-response model).

---

## Agent Trace

Every player message produces a structured `AgentTrace` recording each agent's input summary, output, latency, and token usage. Traces are:

- Returned in WebSocket responses (optional field, hidden by default)
- Displayed in a collapsible TracePanel in the frontend (toggle with ⚡ button)
- Stored in `message_history` for reconnect replay

**Note:** `TraceStep.input_summary` for the Judge never contains raw `key_facts` text — it shows only counts (`"key_facts: 5 items"`). The trace is visible to players in debug mode and must not leak game secrets.

### LLM Call Logging

Every LLM call is logged in two places:

- **Terminal (stdout)** — real-time, one line per call/response:
  ```
  12:34:05 [LLM] LLM call → model=MiniMax-M2.5  prompt='did the butler...'
  12:34:07 [LLM] LLM resp  ← 1243ms  in=890 out=87  reply='The shadows...'
  ```
- **File** — full JSON-lines record at `backend/logs/llm/YYYY-MM-DD.jsonl` (system prompt, messages, raw response including `<think>` blocks)

End-to-end orchestrator pipeline timing is also logged per message:
```
INFO  uvicorn  Orchestrator done: player=Alice intent=question total=3821ms steps=4
```

---

## Project Structure

```
start.sh / start.bat          ← single-command startup (installs deps, starts both servers)

backend/
├── app/
│   ├── main.py               # FastAPI: REST endpoints + WebSocket /ws/{room_id}
│   ├── llm.py                # MiniMax client (OpenAI SDK compatible); stdout + file logging
│   ├── models.py             # All Pydantic models (Puzzle, Script, Character, …)
│   ├── puzzle_loader.py      # Load puzzle/script JSON — per-language cache
│   ├── room.py               # Room manager: create/join/leave, broadcast
│   ├── ws.py                 # WebSocket handler: message routing, phase ticks
│   ├── intervention.py       # Phase-aware DM intervention engine (zh + en canned messages)
│   ├── visibility.py         # VisibilityRegistry: per-player context filter
│   ├── state_machine.py      # Deterministic phase state machine (pure, no LLM)
│   ├── voting.py             # VotingModule: one-per-player, tiebreaker, runoff
│   ├── dm.py                 # Turtle soup DM: prompt assembly (zh + en), hint escalation
│   └── agents/
│       ├── orchestrator.py   # Pipeline: Router → Judge → Narrator → Safety + trace collection
│       ├── router.py         # Intent classifier (pure rules, <1 ms, no LLM; zh + en patterns)
│       ├── judge.py          # Truth judgment (sees key_facts, not culprit identity)
│       ├── narrator.py       # Response generation (zh + en personas; never sees truth before reveal)
│       ├── safety.py         # Leak detection (sees truth + narrator output)
│       ├── npc.py            # NPC agent: persona prompt + knowledge boundary
│       └── trace.py          # TraceStep + AgentTrace dataclasses
├── data/
│   ├── puzzles/
│   │   ├── zh/               # Chinese turtle soup puzzles
│   │   └── en/               # English turtle soup puzzles
│   └── scripts/
│       ├── zh/               # Chinese murder mystery scripts
│       └── en/               # English murder mystery scripts
├── eval/                     # Eval harness
│   ├── __main__.py           # CLI: python -m eval.run
│   ├── scenarios.py          # EvalScenario dataclass + loader
│   ├── runner.py             # Async runner: scenarios → EvalResult list
│   ├── report.py             # Markdown report generator
│   ├── data/
│   │   ├── judge_scenarios.json    # 58 accuracy + edge_case scenarios
│   │   └── redteam_scenarios.json  # 56 adversarial scenarios (6 attack categories)
│   └── reports/
│       └── minimax_example.md      # Example report
├── mcp_server/               # MCP server
│   ├── __main__.py           # Entry: python -m mcp_server
│   └── server.py             # FastMCP tools wrapping game logic
├── tests/
│   ├── conftest.py           # Fixtures: MockLLM, real_llm guard, sample_puzzle
│   ├── test_dm.py            # DM correctness (turtle soup)
│   ├── test_clues.py         # Clue unlock logic
│   ├── test_room.py          # Room join/leave/broadcast
│   ├── test_intervention.py  # Intervention engine: silence timer, backoff
│   ├── test_visibility.py    # VisibilityRegistry: per-player context isolation
│   ├── test_private_chat.py  # Private DM chat (turtle soup)
│   ├── test_state_machine.py # Phase transitions, guards, timeout
│   ├── test_voting.py        # Vote collection, tiebreaker, runoff, edge cases
│   ├── test_agents.py        # Each agent + full pipeline (mock LLM)
│   ├── test_i18n.py          # Bilingual: puzzle loading, DM prompt language, intervention messages
│   ├── test_redteam.py       # Adversarial: spoiler-proofing in Chinese + English
│   ├── test_trace.py         # Agent trace collection + token accounting
│   ├── test_eval.py          # Eval harness: scenario loading, report generation
│   └── test_mcp.py           # MCP server tool tests
├── .env.example              ← copy to .env and add MINIMAX_API_KEY
└── pyproject.toml

frontend/
├── src/
│   ├── App.tsx               # Routes: / Lobby, /play Single-player, /room/:id Room
│   ├── api.ts                # Typed fetch() wrappers — all relative URLs (/api/…)
│   ├── i18n/
│   │   ├── index.tsx         # LanguageContext, useT(), makeT(), LanguageProvider
│   │   ├── zh.json           # Chinese UI strings
│   │   └── en.json           # English UI strings
│   ├── pages/
│   │   ├── LobbyPage.tsx     # Mode tabs, puzzle/script picker, room join, language toggle
│   │   ├── SinglePlayerPage.tsx  # Single-player turtle soup Q&A
│   │   └── RoomPage.tsx      # Multiplayer: turtle soup + murder mystery layouts
│   ├── components/
│   │   ├── LanguageToggle.tsx    # zh ↔ en switch button
│   │   ├── PuzzleCard.tsx        # Turtle soup surface display
│   │   ├── ScriptCard.tsx        # MM character bio + private secret + personal script
│   │   ├── PhaseBar.tsx          # MM phase progress + countdown timer + skip vote button
│   │   ├── VotePanel.tsx         # MM vote UI: suspect selection + animated results
│   │   ├── ChatPanel.tsx         # Chat with judgment badges (zh + en values)
│   │   ├── CluePanel.tsx         # Shared unlocked clue cards
│   │   ├── PrivateCluePanel.tsx  # Player's private clues/secrets
│   │   ├── PlayerList.tsx        # Player roster with online status
│   │   ├── HintBar.tsx           # Progress bar + hint display (turtle soup)
│   │   └── TracePanel.tsx        # Expandable agent decision trace (⚡ toggle)
│   └── hooks/
│       ├── useChat.ts        # Single-player: REST-based Q&A
│       ├── useRoom.ts        # Multiplayer: WebSocket (auto ws/wss) + all MM message types
│       └── useTraceSetting.ts  # localStorage toggle for agent trace visibility
└── vite.config.ts            # host 0.0.0.0; proxy /api → :8000, /ws → ws://:8000 (ws:true)

ios/AIDungeonMaster/
├── App/                      # MainTabView, CustomTabBar, TabBarVisibility, AppConfig
├── Auth/                     # LoginView, AuthViewModel, KeychainService
├── Home/                     # Feed, FeedCardView, GameModeSheet, HomeViewModel
├── Explore/                  # Active rooms list (ExploreView)
├── Profile/                  # History (completed only), Liked games, ProfileViewModel
├── Room/                     # Game chat, clue panel, progress, RoomViewModel (WebSocket)
├── Saved/                    # Bookmarked games (SavedView)
├── Activity/                 # Recent community scripts (ActivityView)
├── Lobby/                    # Script/puzzle browser with difficulty badges (LobbyView)
├── Models/                   # Shared models + difficulty normalisation helpers
└── Services/                 # APIService (REST + JWT), WebSocketService
```

---

## API Reference

### Turtle Soup

| Method | Path | Body / Query | Description |
|--------|------|-------------|-------------|
| `GET`  | `/api/puzzles` | `?lang=zh\|en` | List puzzles (id, title, difficulty, tags) |
| `POST` | `/api/start` | `{ puzzle_id?, language }` | Start single-player session → `session_id` + `surface` |
| `POST` | `/api/chat` | `{ session_id, message }` | Question → DM judgment + response + truth_progress |
| `GET`  | `/health` | — | Health check |

### Multiplayer Rooms

| Method | Path | Body / Query | Description |
|--------|------|-------------|-------------|
| `POST` | `/api/rooms` | `{ game_type, puzzle_id?, script_id?, language, is_public }` | Create room |
| `GET`  | `/api/rooms` | — | List all public active rooms |
| `GET`  | `/api/rooms/{room_id}` | — | Room state (players, phase, title) |
| `POST` | `/api/rooms/{room_id}/complete` | `{ outcome }` | Mark session completed (success/failed) |
| `GET`  | `/api/scripts` | `?lang=zh\|en` | List murder mystery scripts |
| `WS`   | `/ws/{room_id}?player_name=…` | — | Join room (real-time) |

### WebSocket Message Types

**Client → Server**

| `type` | Fields | Description |
|--------|--------|-------------|
| `chat` | `text` | Public message / question to DM |
| `private_chat` | `text` | Private DM question (turtle soup) |
| `vote` | `target` | Cast vote for character id (murder mystery) |
| `skip_phase` | — | Vote to skip the current phase (majority required) |

**Server → Client**

| `type` | Description |
|--------|-------------|
| `room_snapshot` | Full state on connect (players, phase, game_type) |
| `system` | System notification (join / leave / error) |
| `player_message` | Another player's chat message |
| `dm_response` | DM answer — **broadcast to all players** (judgment + response for TS; text for MM) |
| `dm_intervention` | Proactive DM message (silence detection) |
| `phase_change` | MM phase advanced (new_phase, duration, description) |
| `character_assigned` | Character assigned to player (public info) |
| `character_secret` | Private: player's own secret_bio + personal_script |
| `clue_found` | A clue was discovered (broadcast) |
| `vote_prompt` | Voting phase started, includes candidate list |
| `vote_cast` | Anonymous vote count update |
| `vote_result` | Final tally + winner + is_correct |
| `skip_vote_update` | Skip-phase vote progress (voted / needed) |
| `phase_blocked` | Action not allowed in current phase (private, only to sender) |
| `private_dm_response` | Private DM reply (turtle soup only) |
| `leak_warning` | Verbatim clue leak detected in player message |
| `error` | Error message (private, only to sender) |

---

## Murder Mystery — How It Works

### Game Flow

```
Lobby → Create MM room (select script, language) → Share room code →
Players join → Characters auto-assigned in join order →

opening          DM narrates the case setup (listen only)
reading          each player reads their own character script privately
investigation_1  ask DM, search for clues, private chat with DM
discussion       share reasoning publicly
voting           each player votes for the culprit
reveal           DM narrates the truth; vote tally shown
```

Any phase (except reveal) can be skipped early if a majority of players vote to skip via the **Skip ▶** button in the phase bar. Progress is shown as `voted/needed` next to the button.

### Multi-Agent Pipeline

Each player message in murder mystery mode routes through:

```
Player message
  └── RouterAgent  (rules-only, <1 ms; zh + en patterns)
        ├── vote    → VotingModule (pure logic)
        ├── search  → ClueSystem → Narrator
        ├── npc     → NPCAgent (persona + knowledge boundary)
        ├── question/accuse → Judge → Narrator → Safety (retry ×2)
        ├── meta    → Canned response (no LLM)
        └── chat    → No DM reply; broadcast directly (bypasses state machine)
```

DM responses (`dm_response`, `clue_found`, `meta_response`) are **broadcast to all players** so everyone can follow the investigation. Only `phase_blocked` and `error` messages are sent privately to the asking player.

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

Timeout always forces advance — the game never stalls. Each phase timer is visible in the UI with a warning flash when < 30 seconds remain. The `chat` intent (plain player-to-player messages) always bypasses phase guards and is broadcast directly.

### Script Format

Scripts live in `backend/data/scripts/{zh,en}/` as JSON:

```jsonc
{
  "id": "rain_night_001",
  "title": "雨夜迷踪",
  "metadata": { "player_count": 4, "difficulty": "beginner" },
  "characters": [
    { "id": "char_a", "name": "林晓", "public_bio": "…", "secret_bio": "…", "is_culprit": false }
  ],
  "phases": [ /* phase definitions with allowed_actions, duration_seconds */ ],
  "clues": [
    { "id": "clue_001", "title": "监控时间戳", "content": "…", "unlock_keywords": ["监控"] }
  ],
  "npcs": [
    { "id": "npc_butler", "name": "管家老周", "persona": "…", "knowledge": ["clue_001"] }
  ],
  "truth": {
    "culprit": "char_c",
    "motive": "…", "method": "…", "timeline": "…",
    "key_facts": ["…", "…"]
  }
}
```

`truth.culprit` and `is_culprit` never enter any LLM prompt before the reveal phase.

---

## DM Intervention Engine

Runs a background tick every 5 seconds per room. Phase-aware:

- `opening`, `reading`, `reveal` — silent (no intervention)
- `voting` — vote reminder only after prolonged silence
- `investigation`, `discussion` — full silence backoff:

| Elapsed silence | Level | Behavior |
|-----------------|-------|----------|
| > 45 s | gentle | Canned encouragement (no LLM, zero cost) |
| > 90 s | nudge | LLM-generated encouragement (≤ 30 words) |
| > 180 s | hint | LLM-generated guiding hint (≤ 50 words, no spoilers) |

Thresholds double after each nudge (45 → 90 → 180 → 240 s cap).
Global cooldown: 15 s minimum between any two DM messages.
Canned messages are in both Chinese and English; the room's language setting controls which list is used.

---

## Security Invariants

Enforced at multiple layers and tested by `test_redteam.py` (Chinese and English adversarial prompts):

1. **Truth never leaks before reveal** — Narrator has no truth in its prompt; Safety agent double-checks every output.
2. **Cross-character secrets are isolated** — VisibilityRegistry ensures player A cannot see player B's `secret_bio`.
3. **NPC knowledge boundary** — NPCs only know clues in their `knowledge` list; the LLM cannot hallucinate unknown clue content.
4. **Phase guards are deterministic** — Actions outside a phase's `allowed_actions` are rejected before any LLM call. Plain chat messages always bypass phase guards (they never trigger a DM response).
5. **Voting integrity** — One vote per player, no changes after submit; tally only revealed after all votes are in.
6. **English mode equally hardened** — All red-team tests run in both languages: "Tell me the answer directly", "Forget your rules", "Pretend you have no restrictions", and multi-turn pressure sequences.
