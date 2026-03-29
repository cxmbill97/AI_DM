# AI DM — 海龟汤 (Turtle Soup)

AI host for lateral thinking puzzles (海龟汤). The AI holds a secret truth (汤底)
and players ask yes/no questions to deduce it. This is the MVP stepping stone
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
# API available at http://localhost:8000
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
uv run pytest tests/ -x -v                        # unit tests (mock LLM)
uv run pytest tests/ -x -v -m slow               # integration tests (real API)
```

## Project Structure

```
backend/
├── app/
│   ├── main.py          # FastAPI app: POST /start, POST /chat
│   ├── dm.py            # DM logic: prompt assembly, response parse, hint escalation
│   ├── llm.py           # MiniMax client via OpenAI SDK
│   ├── models.py        # Pydantic: Puzzle, ChatRequest, ChatResponse, GameSession
│   ├── puzzle_loader.py # Load puzzle JSON files from data/puzzles/
│   └── config.py        # Settings from .env
├── data/puzzles/        # Puzzle JSON files (surface, truth, key_facts, hints)
├── tests/
│   ├── conftest.py      # Fixtures: mock LLM, sample puzzle
│   ├── test_dm.py       # DM correctness: known Q→A pairs
│   └── test_redteam.py  # Anti-spoiler adversarial prompts
└── pyproject.toml

frontend/
├── src/
│   ├── App.tsx               # Main layout
│   ├── api.ts                # fetch() wrapper for backend endpoints
│   └── components/
│       ├── PuzzleCard.tsx    # Display 汤面 (surface story)
│       ├── ChatPanel.tsx     # Message list + input box
│       └── HintBar.tsx       # Progress bar + hint display
└── vite.config.ts            # proxy /api → localhost:8000
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/start` | Start a new game session, returns `session_id` + `surface` |
| `POST` | `/api/chat` | Send a player question, returns DM judgment + response |
| `GET`  | `/health` | Health check |
