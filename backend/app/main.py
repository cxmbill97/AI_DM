"""FastAPI application — AI DM for 海龟汤 (Turtle Soup) lateral thinking puzzles."""

from __future__ import annotations

import uuid

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from openai import APIError
from pydantic import BaseModel

from app.community import init_db, like_script, list_community_scripts, upsert_script
from app.dm import dm_turn
from app.models import (
    ChatRequest,
    ChatResponse,
    GameSession,
    Player,
    PuzzleSummary,
    RoomState,
    ScriptUploadResponse,
    StartRequest,
    StartResponse,
)
from app.puzzle_loader import (
    invalidate_script_cache,
    load_all_puzzles,
    load_puzzle,
    load_script,
    load_scripts,
    random_puzzle,
    save_script,
)
from app.room import room_manager
from app.ws import websocket_endpoint

app = FastAPI(title="AI DM — 海龟汤")


@app.on_event("startup")
async def _startup() -> None:
    init_db()


@app.exception_handler(APIError)
async def openai_api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    """Surface MiniMax/OpenAI API errors as readable 502 responses."""
    return JSONResponse(
        status_code=502,
        content={"detail": f"LLM API error: {exc.message}"},
    )


# ---------------------------------------------------------------------------
# CORS — allow all origins for LAN dev access (not for production)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
async def list_puzzles(lang: str = "zh") -> list[PuzzleSummary]:
    """List available puzzles — id, title, difficulty, tags only (no truth).

    Query param: lang=zh (default) | lang=en
    """
    return [
        PuzzleSummary(
            id=p.id,
            title=p.title,
            difficulty=p.difficulty,
            tags=p.tags,
        )
        for p in load_all_puzzles(lang)
    ]


@app.post("/api/start", response_model=StartResponse)
async def start_game(body: StartRequest = StartRequest()) -> StartResponse:
    """Create a new game session.

    Pass `puzzle_id` to choose a specific puzzle, or omit for a random one.
    Returns `session_id` + the 汤面 (surface story). The truth is never returned.
    """
    lang = body.language if body.language in ("zh", "en") else "zh"
    try:
        puzzle = load_puzzle(body.puzzle_id, lang) if body.puzzle_id else random_puzzle(lang)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    session_id = str(uuid.uuid4())
    session = GameSession(
        session_id=session_id,
        puzzle=puzzle,
        history=[],
        language=lang,
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
    game_type: str = "turtle_soup"  # "turtle_soup" | "murder_mystery"
    puzzle_id: str | None = None  # turtle_soup: None → random puzzle
    script_id: str | None = None  # murder_mystery: required
    language: str = "zh"  # "zh" | "en"


@app.post("/api/rooms")
async def create_room(body: CreateRoomRequest = CreateRoomRequest()) -> dict:
    """Create a new multiplayer room.

    For turtle_soup: pass puzzle_id (or omit for random).
    For murder_mystery: pass game_type="murder_mystery" and script_id.
    Pass language="en" for an English-language room.
    Returns {room_id, game_type} — players then connect via WebSocket /ws/{room_id}.
    """
    lang = body.language if body.language in ("zh", "en") else "zh"

    if body.game_type == "murder_mystery":
        if not body.script_id:
            raise HTTPException(status_code=422, detail="script_id is required for murder_mystery")
        try:
            script = load_script(body.script_id, lang)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        room_id = room_manager.create_room(script=script, language=lang)
        return {"room_id": room_id, "game_type": "murder_mystery", "script_id": script.id}

    # turtle_soup (default)
    try:
        puzzle = load_puzzle(body.puzzle_id, lang) if body.puzzle_id else random_puzzle(lang)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    room_id = room_manager.create_room(puzzle=puzzle, language=lang)
    return {"room_id": room_id, "game_type": "turtle_soup", "puzzle_id": puzzle.id}


@app.get("/api/scripts")
async def list_scripts(lang: str = "zh") -> list[dict]:
    """List available murder mystery scripts — id and title only.

    Query param: lang=zh (default) | lang=en
    """
    return [{"id": s.id, "title": s.title, "difficulty": s.metadata.difficulty, "player_count": s.metadata.player_count} for s in load_scripts(lang)]


@app.get("/api/rooms/{room_id}", response_model=RoomState)
async def get_room(room_id: str) -> RoomState:
    """Return current room state: players, puzzle surface, phase."""
    room = room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail=f"Room not found: {room_id!r}")

    players = [Player(id=pid, name=p["name"], connected=p["connected"]) for pid, p in room.players.items()]
    if room.game_type == "murder_mystery":
        assert room.script is not None
        return RoomState(
            room_id=room_id,
            puzzle_id=room.script.id,
            title=room.script.title,
            surface=room.script.phases[0].dm_script or room.script.title,
            players=players,
            phase=room.phase,
            game_type="murder_mystery",
        )
    assert room.puzzle is not None
    return RoomState(
        room_id=room_id,
        puzzle_id=room.puzzle.id,
        title=room.puzzle.title,
        surface=room.puzzle.surface,
        players=players,
        phase=room.phase,
        game_type="turtle_soup",
    )


# ---------------------------------------------------------------------------
# Script ingestion — upload + AI parse
# ---------------------------------------------------------------------------

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@app.post("/api/scripts/upload", response_model=ScriptUploadResponse)
async def upload_script(
    file: UploadFile = File(...),
    lang: str = Form("zh"),
    author: str = Form(""),
) -> ScriptUploadResponse:
    """Upload a PDF, DOCX, or TXT murder mystery script and parse it with AI.

    The parsed script is saved to data/scripts/{lang}/ and becomes immediately
    available for room creation via GET /api/scripts.

    Form fields:
      file — the document (PDF, DOCX, or TXT)
      lang — "zh" (default) or "en"
    """
    import uuid  # noqa: PLC0415

    from app.agents.doc_parser import DocumentParserAgent, ScriptParseError  # noqa: E402
    from app.doc_extractor import ExtractionError, UnsupportedFormatError, extract_text  # noqa: E402

    lang = lang if lang in ("zh", "en") else "zh"
    content = await file.read()

    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10 MB.")

    # Extract text
    try:
        raw_text = extract_text(file.filename or "upload.txt", content)
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=f"File extraction failed: {exc}") from exc

    # Detect truncation
    was_truncated = len(raw_text) > 24_000
    warning = "Document was truncated to 24,000 characters for AI processing." if was_truncated else None

    # Parse with LLM
    script_id = f"upload_{lang}_{uuid.uuid4().hex[:8]}"
    agent = DocumentParserAgent(language=lang)
    try:
        script = await agent.parse(raw_text, script_id)
    except ScriptParseError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": f"Script parsing failed: {exc}", "last_json": exc.last_json or ""},
        ) from exc

    # Persist and invalidate cache
    save_script(script, lang)
    invalidate_script_cache(lang)

    # Register in community metadata
    upsert_script(
        script_id=script.id,
        title=script.title,
        author=author.strip() or "匿名",
        difficulty=script.metadata.difficulty,
        player_count=script.metadata.player_count,
        game_mode=script.game_mode,
        lang=lang,
    )

    return ScriptUploadResponse(
        script_id=script.id,
        title=script.title,
        player_count=script.metadata.player_count,
        difficulty=script.metadata.difficulty,
        game_mode=script.game_mode,
        character_names=[c.name for c in script.characters],
        phase_count=len(script.phases),
        clue_count=len(script.clues),
        warning=warning,
    )


# ---------------------------------------------------------------------------
# Community library endpoints
# ---------------------------------------------------------------------------


@app.get("/api/community/scripts")
async def community_scripts(
    lang: str = "zh",
    search: str = "",
    difficulty: str = "",
    game_mode: str = "",
    limit: int = 50,
) -> list[dict]:
    """List community-uploaded scripts with author, likes, and filter support."""
    return list_community_scripts(
        lang=lang or None,
        search=search or None,
        difficulty=difficulty or None,
        game_mode=game_mode or None,
        limit=limit,
    )


@app.post("/api/community/scripts/{script_id}/like")
async def like_script_endpoint(script_id: str) -> dict:
    """Increment like count for a script. Returns new count."""
    new_count = like_script(script_id)
    return {"script_id": script_id, "likes": new_count}


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
