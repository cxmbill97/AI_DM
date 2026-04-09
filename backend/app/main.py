"""FastAPI application — AI DM for 海龟汤 (Turtle Soup) lateral thinking puzzles."""

from __future__ import annotations

import uuid

import httpx
import asyncio
import json as _json

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from openai import APIError
from pydantic import BaseModel

import os

from app.auth import (
    add_favorite,
    complete_history,
    create_jwt,
    decode_jwt,
    get_user_by_id,
    has_pending_report,
    init_auth_db,
    list_favorites,
    list_history,
    list_reports,
    remove_favorite,
    submit_report,
    update_report_status,
    upsert_user,
)
from app.community import init_db, like_script, list_community_scripts, upsert_script
from app.config import settings
from app.dm import dm_turn
from app.models import (
    ChatRequest,
    ChatResponse,
    GameSession,
    Player,
    PuzzleSummary,
    PuzzleUploadResponse,
    RoomState,
    ScriptUploadResponse,
    StartRequest,
    StartResponse,
)
from app.puzzle_loader import (
    invalidate_puzzle_cache,
    invalidate_script_cache,
    load_all_puzzles,
    load_puzzle,
    load_script,
    load_scripts,
    random_puzzle,
    save_puzzle,
    save_script,
)
from app.agents.trace_store import get_traces, subscribe, unsubscribe
from app.tts import synthesize as tts_synthesize
from app.room import room_manager
from app.routers import economy_router, pet_router
from app.ws import websocket_endpoint

app = FastAPI(title="AI DM — 海龟汤")
app.include_router(economy_router.router)
app.include_router(pet_router.router)


@app.on_event("startup")
async def _startup() -> None:
    init_db()
    init_auth_db()


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


def _require_user(request: Request) -> dict:
    """Dependency: extract and validate JWT from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth.removeprefix("Bearer ").strip()
    try:
        payload = decode_jwt(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = get_user_by_id(payload["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _optional_user(request: Request) -> dict | None:
    """Dependency: like _require_user but returns None instead of raising when unauthenticated."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.removeprefix("Bearer ").strip()
    try:
        payload = decode_jwt(token)
    except ValueError:
        return None
    return get_user_by_id(payload["sub"])


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Auth — Google OAuth
# ---------------------------------------------------------------------------

@app.get("/auth/config")
async def auth_config() -> dict:
    """Returns which auth providers are available."""
    return {"google": bool(settings.google_client_id), "dev": not bool(settings.google_client_id)}


@app.get("/auth/dev-login")
async def auth_dev_login(name: str = "Dev User") -> RedirectResponse:
    """Dev-only login bypass. Always available in development; blocked in production (no JWT_SECRET set)."""
    user = upsert_user(
        provider_sub=f"dev:{name}",
        name=name,
        email=f"{name.lower().replace(' ', '.')}@dev.local",
        avatar_url="",
    )
    token = create_jwt(user["id"])
    return RedirectResponse(f"{settings.frontend_url}/?token={token}")


@app.get("/auth/dev-login/mobile")
async def auth_dev_login_mobile(name: str = "Dev User") -> RedirectResponse:
    """Dev-only mobile login bypass — redirects to aidm:// deep link."""
    user = upsert_user(
        provider_sub=f"dev:{name}",
        name=name,
        email=f"{name.lower().replace(' ', '.')}@dev.local",
        avatar_url="",
    )
    token = create_jwt(user["id"])
    return RedirectResponse(f"aidm://auth?token={token}")


@app.get("/auth/google")
async def auth_google() -> RedirectResponse:
    """Redirect browser to Google's OAuth consent screen."""
    from urllib.parse import urlencode  # noqa: PLC0415
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(url)


@app.get("/auth/google/callback")
async def auth_google_callback(code: str = "", error: str = "") -> RedirectResponse:
    """Exchange Google code for user info, issue JWT, redirect to frontend."""
    if error or not code:
        return RedirectResponse(f"{settings.frontend_url}/?error=oauth_failed")
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            return RedirectResponse(f"{settings.frontend_url}/?error=oauth_failed")
        access_token = token_resp.json().get("access_token", "")
        info_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if info_resp.status_code != 200:
            return RedirectResponse(f"{settings.frontend_url}/?error=oauth_failed")
        info = info_resp.json()
    user = upsert_user(
        provider_sub=f"google:{info['id']}",
        name=info.get("name", info.get("email", "Player")),
        email=info.get("email", ""),
        avatar_url=info.get("picture", ""),
    )
    jwt_token = create_jwt(user["id"])
    return RedirectResponse(f"{settings.frontend_url}/?token={jwt_token}")


@app.get("/auth/google/mobile")
async def auth_google_mobile() -> RedirectResponse:
    """Mobile OAuth entry — uses aidm:// redirect URI."""
    from urllib.parse import urlencode  # noqa: PLC0415
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_mobile_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(url)


@app.get("/auth/google/mobile/callback")
async def auth_google_mobile_callback(code: str = "", error: str = "") -> RedirectResponse:
    """Exchange Google code for JWT, redirect to aidm:// custom URL scheme."""
    if error or not code:
        return RedirectResponse("aidm://auth?error=oauth_failed")
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_mobile_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            return RedirectResponse("aidm://auth?error=oauth_failed")
        access_token = token_resp.json().get("access_token", "")
        info_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if info_resp.status_code != 200:
            return RedirectResponse("aidm://auth?error=oauth_failed")
        info = info_resp.json()
    user = upsert_user(
        provider_sub=f"google:{info['id']}",
        name=info.get("name", info.get("email", "Player")),
        email=info.get("email", ""),
        avatar_url=info.get("picture", ""),
    )
    jwt_token = create_jwt(user["id"])
    return RedirectResponse(f"aidm://auth?token={jwt_token}")


class AppleAuthRequest(BaseModel):
    identity_token: str
    full_name: str = ""


@app.post("/auth/apple")
async def auth_apple(req: AppleAuthRequest) -> dict:
    """Verify Apple identity token, upsert user, return JWT."""
    import base64  # noqa: PLC0415
    import json as _json  # noqa: PLC0415

    if not settings.apple_bundle_id:
        raise HTTPException(status_code=503, detail="Apple Sign-In not configured")

    # Fetch Apple's public keys
    async with httpx.AsyncClient() as client:
        keys_resp = await client.get("https://appleid.apple.com/auth/keys")
        if keys_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Could not fetch Apple public keys")
        jwks = keys_resp.json()

    # Decode header to find which key to use
    try:
        header_b64 = req.identity_token.split(".")[0]
        header_b64 += "=" * (4 - len(header_b64) % 4)
        header = _json.loads(base64.b64decode(header_b64))
        kid = header["kid"]
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Malformed identity token") from exc

    apple_key = next((k for k in jwks["keys"] if k["kid"] == kid), None)
    if apple_key is None:
        raise HTTPException(status_code=400, detail="Unknown key ID in Apple token")

    try:
        import jwt as _jwt  # noqa: PLC0415
        from jwt.algorithms import RSAAlgorithm  # noqa: PLC0415
        public_key = RSAAlgorithm.from_jwk(_json.dumps(apple_key))
        payload = _jwt.decode(
            req.identity_token,
            public_key,
            algorithms=["RS256"],
            audience=settings.apple_bundle_id,
            issuer="https://appleid.apple.com",
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid Apple token: {exc}") from exc

    apple_sub = payload["sub"]
    email = payload.get("email", f"{apple_sub}@privaterelay.appleid.com")
    name = req.full_name or email.split("@")[0]

    user = upsert_user(
        provider_sub=f"apple:{apple_sub}",
        name=name,
        email=email,
        avatar_url="",
    )
    return {"token": create_jwt(user["id"])}


@app.get("/api/me")
async def get_me(user: dict = Depends(_require_user)) -> dict:
    """Return the current authenticated user."""
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "avatar_url": user["avatar_url"],
        "created_at": user["created_at"],
    }


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------

@app.get("/api/favorites")
async def get_favorites(user: dict = Depends(_require_user)) -> list[dict]:
    return list_favorites(user["id"])


@app.post("/api/favorites/{item_type}/{item_id}", status_code=204)
async def post_favorite(item_type: str, item_id: str, user: dict = Depends(_require_user)) -> None:
    if item_type not in ("puzzle", "script", "puzzle_like", "script_like"):
        raise HTTPException(status_code=422, detail="item_type must be 'puzzle', 'script', 'puzzle_like', or 'script_like'")
    add_favorite(user["id"], item_id, item_type)


@app.delete("/api/favorites/{item_type}/{item_id}", status_code=204)
async def delete_favorite(item_type: str, item_id: str, user: dict = Depends(_require_user)) -> None:
    remove_favorite(user["id"], item_id, item_type)


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@app.get("/api/history")
async def get_history(user: dict = Depends(_require_user)) -> list[dict]:
    return list_history(user["id"])


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


@app.post("/api/puzzles/upload", response_model=PuzzleUploadResponse)
async def upload_puzzle(
    file: UploadFile = File(...),
    lang: str = Form("zh"),
) -> PuzzleUploadResponse:
    """Upload a PDF, DOCX, or TXT turtle soup puzzle and parse it with AI.

    The parsed puzzle is saved to data/puzzles/{lang}/ and becomes immediately
    available for game creation via GET /api/puzzles.
    """
    from app.agents.puzzle_parser import PuzzleParseError, PuzzleParserAgent  # noqa: PLC0415
    from app.doc_extractor import ExtractionError, UnsupportedFormatError, extract_text  # noqa: PLC0415

    lang = lang if lang in ("zh", "en") else "zh"
    content = await file.read()

    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 10 MB.")

    try:
        raw_text = extract_text(file.filename or "upload.txt", content)
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=f"File extraction failed: {exc}") from exc

    was_truncated = len(raw_text) > 24_000
    warning = "Document was truncated to 24,000 characters for AI processing." if was_truncated else None

    puzzle_id = f"upload_{lang}_{uuid.uuid4().hex[:8]}"
    agent = PuzzleParserAgent(language=lang)
    try:
        puzzle = await agent.parse(raw_text, puzzle_id)
    except PuzzleParseError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": f"Puzzle parsing failed: {exc}", "last_json": exc.last_json or ""},
        ) from exc

    save_puzzle(puzzle, lang)
    invalidate_puzzle_cache(lang)

    return PuzzleUploadResponse(
        puzzle_id=puzzle.id,
        title=puzzle.title,
        difficulty=puzzle.difficulty,
        tags=puzzle.tags,
        clue_count=len(puzzle.clues),
        key_fact_count=len(puzzle.key_facts),
        warning=warning,
    )


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
    is_public: bool = True
    lobby_mode: bool = False  # True → room stays in lobby until host starts; False → start immediately (backward compat)
    turn_mode: bool = False  # Phase 0: enable turn-based speaking (turtle_soup only)


@app.post("/api/rooms")
async def create_room(body: CreateRoomRequest = CreateRoomRequest(), user: dict | None = Depends(_optional_user)) -> dict:
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
        room = room_manager.rooms[room_id]
        room.is_public = body.is_public
        if user:
            room.host_user_id = str(user["id"])
        if not body.lobby_mode:
            room.started = True
        return {"room_id": room_id, "game_type": "murder_mystery", "script_id": script.id}

    # turtle_soup (default)
    try:
        puzzle = load_puzzle(body.puzzle_id, lang) if body.puzzle_id else random_puzzle(lang)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    room_id = room_manager.create_room(puzzle=puzzle, language=lang)
    room = room_manager.rooms[room_id]
    room.is_public = body.is_public
    room.turn_mode = body.turn_mode
    if user:
        room.host_user_id = str(user["id"])
    if not body.lobby_mode:
        room.started = True
    return {"room_id": room_id, "game_type": "turtle_soup", "puzzle_id": puzzle.id, "turn_mode": body.turn_mode}


@app.get("/api/scripts")
async def list_scripts(lang: str = "zh") -> list[dict]:
    """List available murder mystery scripts — id and title only.

    Query param: lang=zh (default) | lang=en
    """
    return [{"id": s.id, "title": s.title, "difficulty": s.metadata.difficulty, "player_count": s.metadata.player_count} for s in load_scripts(lang)]


@app.get("/api/rooms")
async def list_active_rooms() -> list[dict]:
    """List public rooms that are in the lobby (not yet started) and have at least one player."""
    import time as _time  # noqa: PLC0415

    now = _time.time()
    result = []
    for room_id, room in room_manager.rooms.items():
        if not getattr(room, "is_public", True):
            continue
        # Exclude rooms that have already started
        if room.started:
            continue
        connected = sum(1 for p in room.players.values() if p.get("connected"))
        # Exclude empty rooms (all players left)
        if connected == 0:
            continue
        total = sum(
            1 for p in room.players.values()
            if p.get("connected") or (now - p.get("last_seen", 0)) < 60
        )
        title = ""
        if room.puzzle:
            title = room.puzzle.title
        elif room.script:
            title = room.script.title
        result.append({
            "room_id": room_id,
            "game_type": room.game_type,
            "title": title,
            "player_count": total,
            "connected_count": connected,
            "max_players": room.max_players,
            "language": room.language,
        })
    return result


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


@app.post("/api/rooms/{room_id}/complete")
async def complete_room(room_id: str, body: dict, user: dict = Depends(_require_user)) -> dict:
    """Mark a room session as completed for the authenticated user."""
    outcome = body.get("outcome", "success")
    if outcome not in ("success", "failed"):
        raise HTTPException(status_code=422, detail="outcome must be 'success' or 'failed'")
    complete_history(user_id=user["id"], room_id=room_id, outcome=outcome)
    return {"ok": True}


@app.post("/api/rooms/{room_id}/start")
async def start_room(room_id: str, user: dict | None = Depends(_optional_user)) -> dict:
    """Host starts the game — sets room.started=True and broadcasts game_started to all players."""
    import asyncio as _asyncio  # noqa: PLC0415

    room = room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail=f"Room not found: {room_id!r}")
    if room.started:
        return {"ok": True, "already_started": True}
    # Verify the caller is the host (if authenticated)
    if user and room.host_user_id and str(user["id"]) != room.host_user_id:
        raise HTTPException(status_code=403, detail="Only the host can start the game")
    # Phase 0: require at least 2 players for turn-mode games
    if room.turn_mode and room.game_type == "turtle_soup":
        active = sum(1 for p in room.players.values() if p["connected"])
        if active < 2:
            raise HTTPException(status_code=422, detail="Turn mode requires at least 2 players to start")
    room.started = True
    if room.turn_mode and room.game_type == "turtle_soup":
        room.start_turns()
    event: dict = {"type": "game_started", "room_id": room_id}
    if room.turn_mode and room.turn_order:
        first_pid = room.current_turn_player_id()
        first_name = room.players[first_pid]["name"] if first_pid and first_pid in room.players else ""
        event["turn_mode"] = True
        event["first_player_id"] = first_pid
        event["first_player_name"] = first_name
    _asyncio.get_event_loop().call_soon(
        lambda: _asyncio.ensure_future(room.broadcast(event))
    )
    return {"ok": True}


class PatchRoomRequest(BaseModel):
    is_public: bool | None = None
    max_players: int | None = None


@app.patch("/api/rooms/{room_id}")
async def patch_room(room_id: str, body: PatchRoomRequest, user: dict | None = Depends(_optional_user)) -> dict:
    """Update room settings (host only). Supports is_public and max_players."""
    room = room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail=f"Room not found: {room_id!r}")
    if user and room.host_user_id and str(user["id"]) != room.host_user_id:
        raise HTTPException(status_code=403, detail="Only the host can modify room settings")
    if body.is_public is not None:
        room.is_public = body.is_public
    if body.max_players is not None:
        if not (2 <= body.max_players <= 8):
            raise HTTPException(status_code=422, detail="max_players must be between 2 and 8")
        room.max_players = body.max_players
    return {"ok": True}


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
# Agent Trace — REST + SSE endpoints
# ---------------------------------------------------------------------------


@app.get("/api/rooms/{room_id}/traces")
async def get_room_traces(room_id: str) -> list[dict]:
    """Return the last 20 agent traces for a room (newest first)."""
    if room_manager.get_room(room_id) is None:
        raise HTTPException(status_code=404, detail=f"Room not found: {room_id!r}")
    return get_traces(room_id, limit=20)


@app.get("/api/rooms/{room_id}/traces/live")
async def stream_room_traces(room_id: str) -> StreamingResponse:
    """SSE stream — emits one AgentTrace JSON per event as new traces arrive."""
    if room_manager.get_room(room_id) is None:
        raise HTTPException(status_code=404, detail=f"Room not found: {room_id!r}")

    q = subscribe(room_id)

    async def event_generator():
        yield ": connected\n\n"
        try:
            while True:
                try:
                    trace_dict = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"data: {_json.dumps(trace_dict, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            unsubscribe(room_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Player reporting endpoints
# ---------------------------------------------------------------------------

_ADMIN_USER_IDS: set[str] = set(filter(None, os.environ.get("ADMIN_USER_IDS", "").split(",")))


def _require_admin(user: dict = Depends(_require_user)) -> dict:
    if _ADMIN_USER_IDS and user["id"] not in _ADMIN_USER_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


class ReportRequest(BaseModel):
    room_id: str
    reported_player_name: str
    reason: str  # "cheating" | "harassment" | "spoiler" | "other"
    detail: str = ""
    message_text: str = ""


@app.post("/api/reports")
async def create_report(body: ReportRequest, user: dict = Depends(_require_user)) -> dict:
    """Submit a report about another player."""
    room = room_manager.get_room(body.room_id)
    if room is None:
        raise HTTPException(status_code=404, detail=f"Room not found: {body.room_id!r}")
    reported_id = room.find_player_by_name(body.reported_player_name)
    if reported_id is None:
        raise HTTPException(status_code=404, detail=f"Player '{body.reported_player_name}' not found in room")
    if reported_id == user["id"]:
        raise HTTPException(status_code=422, detail="Cannot report yourself")
    if has_pending_report(user["id"], reported_id, body.room_id):
        raise HTTPException(status_code=429, detail="You already have a pending report for this player in this room")
    report_id = submit_report(
        room_id=body.room_id,
        reporter_id=user["id"],
        reported_id=reported_id,
        reason=body.reason,
        detail=body.detail,
        message_text=body.message_text,
    )
    return {"report_id": report_id, "status": "pending"}


@app.get("/api/reports")
async def get_reports(
    status: str | None = None,
    limit: int = 50,
    _admin: dict = Depends(_require_admin),
) -> list[dict]:
    """List reports (admin only)."""
    return list_reports(status=status, limit=limit)


class PatchReportRequest(BaseModel):
    status: str  # "reviewed" | "dismissed"


@app.patch("/api/reports/{report_id}")
async def patch_report(
    report_id: str,
    body: PatchReportRequest,
    _admin: dict = Depends(_require_admin),
) -> dict:
    """Update a report's status (admin only)."""
    if body.status not in ("reviewed", "dismissed"):
        raise HTTPException(status_code=422, detail="status must be 'reviewed' or 'dismissed'")
    update_report_status(report_id, body.status)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Anomaly detection endpoint (admin)
# ---------------------------------------------------------------------------


@app.get("/api/rooms/{room_id}/anomalies")
async def get_anomalies(room_id: str, _admin: dict = Depends(_require_admin)) -> list[dict]:
    """Return anomaly flags for a room (admin only)."""
    room = room_manager.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail=f"Room not found: {room_id!r}")
    return room._anomaly_flags


# ---------------------------------------------------------------------------
# TTS endpoint
# ---------------------------------------------------------------------------


@app.get("/api/tts")
async def tts_endpoint(text: str = "", lang: str = "zh") -> Response:
    """GET /api/tts?text=…&lang=zh|en

    Returns audio/mpeg (MP3).  Max text length is enforced inside synthesize().
    No auth required — audio content is the DM's public narration text.
    Cached responses carry a 1-hour public cache header.
    """
    if not text or not text.strip():
        return Response(status_code=400)
    mp3 = await tts_synthesize(text, language=lang)
    return Response(
        content=mp3,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ---------------------------------------------------------------------------
# Phase 2 — WebSocket endpoint
# ---------------------------------------------------------------------------


@app.websocket("/ws/{room_id}")
async def ws_endpoint(
    websocket: WebSocket,
    room_id: str,
    token: str = "",
    spectate: bool = False,
) -> None:
    """WebSocket connection for multiplayer rooms.

    Query params:
      token    — JWT issued by /auth/google/callback (required)
      spectate — pass ?spectate=true to join as a read-only spectator

    Protocol:
      Client sends: {"type": "chat", "text": "..."}
      Server sends: dm_response | player_message | system | room_snapshot | error
    """
    await websocket_endpoint(websocket, room_id, token, spectate=spectate)
