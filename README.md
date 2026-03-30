# AI DM — 海龟汤 (Turtle Soup)

AI host for lateral thinking puzzles (海龟汤). The AI holds a secret truth (汤底)
and players ask yes/no questions to deduce it. Supports both single-player and
multiplayer (2–4 players via WebSocket rooms). This is the MVP stepping stone
toward a full 剧本杀 (murder mystery) AI DM.

## Prerequisites

- Python 3.12+ with [uv](https://docs.astral.sh/uv/)
- Node.js 18+ with [pnpm](https://pnpm.io/)
- A MiniMax API key

## Setup

### Backend

```bash
cd backend
cp .env.example .env          # then fill in MINIMAX_API_KEY
uv sync                       # install all deps (including dev)
uv run uvicorn app.main:app --reload
# API + WebSocket available at http://localhost:8000
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
# UI available at http://localhost:5173
```

## Running Tests

```bash
cd backend
uv run pytest tests/ -x -v                        # all unit tests (mock LLM)
uv run pytest tests/ -x -v -m slow               # integration tests (real API)
uv run pytest tests/test_room.py -x -v            # multiplayer room tests
uv run pytest tests/test_intervention.py -x -v    # DM intervention engine tests
uv run pytest tests/test_redteam.py -x -v         # anti-spoiler red team (real API)
```

## Project Structure

```
backend/
├── app/
│   ├── main.py          # FastAPI app: REST + WebSocket /ws/{room_id}
│   ├── dm.py            # DM logic: prompt assembly, response parse, hint/clue, proactive messages
│   ├── llm.py           # MiniMax client via OpenAI SDK
│   ├── models.py        # Pydantic: Puzzle, Clue, GameSession, ChatMessage
│   ├── puzzle_loader.py # Load puzzle JSON from data/puzzles/
│   ├── room.py          # Room manager: join/leave, broadcast, WebSocket state
│   ├── ws.py            # WebSocket handler + background tick loop
│   ├── intervention.py  # DM intervention engine: silence timer, explicit triggers
│   └── config.py        # Settings from .env
├── data/puzzles/        # Puzzle JSON files (surface, truth, key_facts, hints, clues)
├── tests/
│   ├── conftest.py           # Fixtures: mock LLM, sample puzzle
│   ├── test_dm.py            # DM correctness: known Q→A pairs
│   ├── test_clues.py         # Clue unlock logic (passive + active)
│   ├── test_room.py          # Multiplayer room: join/leave, broadcast, reconnect
│   ├── test_intervention.py  # Intervention engine: silence timer, backoff, triggers
│   └── test_redteam.py       # Anti-spoiler adversarial prompts
└── pyproject.toml

frontend/
├── src/
│   ├── App.tsx                    # Routes: / Lobby, /play Single-player, /room/:id Room
│   ├── api.ts                     # fetch() wrapper for REST endpoints
│   ├── pages/
│   │   ├── LobbyPage.tsx          # Create/join room; puzzle picker for single-player
│   │   ├── SinglePlayerPage.tsx   # Single-player Q&A (Phase 1)
│   │   └── RoomPage.tsx           # Multiplayer room: chat, clues, player list
│   ├── components/
│   │   ├── PuzzleCard.tsx         # Surface story display
│   │   ├── ChatPanel.tsx          # Single-player message list + input
│   │   ├── CluePanel.tsx          # Unlocked clue cards
│   │   ├── PlayerList.tsx         # Player roster with avatar colors + online status
│   │   └── HintBar.tsx            # Progress bar + hint display
│   └── hooks/
│       ├── useChat.ts             # Single-player: REST polling
│       └── useRoom.ts             # Multiplayer: WebSocket connection + per-player stats
└── vite.config.ts                 # proxy /api → localhost:8000, /ws → ws://localhost:8000
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/puzzles` | List available puzzles |
| `POST` | `/api/start` | Start a single-player session, returns `session_id` + `surface` |
| `POST` | `/api/chat` | Send a question (single-player), returns DM judgment + response |
| `POST` | `/api/rooms` | Create a multiplayer room, returns `room_id` |
| `WS`   | `/ws/{room_id}?player_name=…` | Join a room; real-time multiplayer |
| `GET`  | `/health` | Health check |

## Multiplayer Flow

1. One player creates a room from the Lobby (picks a puzzle → clicks "创建房间").
2. The room code (6 chars) is shown in the game header with a "复制邀请码" button.
3. Other players join by entering the code in the Lobby.
4. The game starts automatically once ≥ 2 players are connected.
5. All players share a single chat thread. The DM responds to each question and
   may speak proactively if the room goes quiet (silence timer with exponential backoff).
6. When the truth is deduced, a review screen shows per-player question counts,
   clues unlocked, and a 🏆 MVP 推理王 badge for the top clue finder.

## DM Intervention Engine

The intervention engine runs a background tick every 5 seconds per room and fires
proactive DM messages when players are stuck:

| Elapsed silence | Level | Behavior |
|-----------------|-------|----------|
| > 45 s | gentle | Random canned encouragement (no LLM call) |
| > 90 s | nudge | LLM-generated encouragement (≤ 30 chars) |
| > 180 s | hint | LLM-generated guiding hint (≤ 50 chars, no spoilers) |

Thresholds double after each DM nudge (45 → 90 → 180 → 240 s cap).
Global cooldown: 15 s minimum between any two DM messages.
Explicit triggers: `@DM`, `提示`, `帮我`, `告诉我` in any player message.
