"""FastAPI application — AI DM for 海龟汤 (Turtle Soup) lateral thinking puzzles."""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import APIError
from pydantic import BaseModel

from app.dm import dm_turn
from app.models import (
    ChatRequest,
    ChatResponse,
    GameSession,
    Player,
    PuzzleSummary,
    RoomState,
    StartRequest,
    StartResponse,
)
from app.puzzle_loader import load_all_puzzles, load_puzzle, random_puzzle
from app.room import room_manager
from app.ws import websocket_endpoint

app = FastAPI(title="AI DM — 海龟汤")


@app.exception_handler(APIError)
async def openai_api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    """Surface MiniMax/OpenAI API errors as readable 502 responses."""
    return JSONResponse(
        status_code=502,
        content={"detail": f"LLM API error: {exc.message}"},
    )

# ---------------------------------------------------------------------------
# CORS — allow the Vite dev server and any localhost origin during development
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory session store  { session_id: GameSession }
# ---------------------------------------------------------------------------
_sessions: dict[str, GameSession] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_session(session_id: str) -> GameSession:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id!r}")
    return session


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/puzzles", response_model=list[PuzzleSummary])
async def list_puzzles() -> list[PuzzleSummary]:
    """List available puzzles — id, title, difficulty, tags only (no truth)."""
    return [
        PuzzleSummary(
            id=p.id,
            title=p.title,
            difficulty=p.difficulty,
            tags=p.tags,
        )
        for p in load_all_puzzles()
    ]


@app.post("/api/start", response_model=StartResponse)
async def start_game(body: StartRequest = StartRequest()) -> StartResponse:
    """Create a new game session.

    Pass `puzzle_id` to choose a specific puzzle, or omit for a random one.
    Returns `session_id` + the 汤面 (surface story). The truth is never returned.
    """
    try:
        puzzle = load_puzzle(body.puzzle_id) if body.puzzle_id else random_puzzle()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    session_id = str(uuid.uuid4())
    session = GameSession(
        session_id=session_id,
        puzzle=puzzle,
        history=[],
    )
    _sessions[session_id] = session

    return StartResponse(
        session_id=session_id,
        puzzle_id=puzzle.id,
        title=puzzle.title,
        surface=puzzle.surface,
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest) -> ChatResponse:
    """Submit a player question and receive the DM's judgment + response.

    The DM will respond with 是 / 不是 / 无关 / 部分正确 and a guiding remark.
    """
    session = _get_session(body.session_id)

    if session.finished:
        raise HTTPException(status_code=400, detail="Game is already finished.")

    if not body.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty.")

    return await dm_turn(session, body.message.strip())


# ---------------------------------------------------------------------------
# Phase 2 — Multiplayer room REST endpoints
# ---------------------------------------------------------------------------


class CreateRoomRequest(BaseModel):
    puzzle_id: str | None = None  # None → random puzzle


@app.post("/api/rooms")
async def create_room(body: CreateRoomRequest = CreateRoomRequest()) -> dict:
    """Create a new multiplayer room.

    Returns {room_id} — players then connect via WebSocket /ws/{room_id}.
    """
    try:
        puzzle = load_puzzle(body.puzzle_id) if body.puzzle_id else random_puzzle()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    room_id = room_manager.create_room(puzzle)
    return {"room_id": room_id}


@app.get("/api/rooms/{room_id}", response_model=RoomState)
async def get_room(room_id: str) -> RoomState:
    """Return current room state: players, puzzle surface, phase."""
    room = room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail=f"Room not found: {room_id!r}")

    players = [
        Player(id=pid, name=p["name"], connected=p["connected"])
        for pid, p in room.players.items()
    ]
    return RoomState(
        room_id=room_id,
        puzzle_id=room.puzzle.id,
        title=room.puzzle.title,
        surface=room.puzzle.surface,
        players=players,
        phase=room.phase,
    )


# ---------------------------------------------------------------------------
# Phase 2 — WebSocket endpoint
# ---------------------------------------------------------------------------


@app.websocket("/ws/{room_id}")
async def ws_endpoint(
    websocket: WebSocket,
    room_id: str,
    player_name: str = "",
) -> None:
    """WebSocket connection for multiplayer rooms.

    Query params:
      player_name  — display name (required)

    Protocol:
      Client sends: {"type": "chat", "text": "..."}
      Server sends: dm_response | player_message | system | room_snapshot | error
    """
    await websocket_endpoint(websocket, room_id, player_name)
