"""WebSocket handler for multiplayer rooms.

Flow per connection
-------------------
1. Look up room.  If missing → accept + send error + close.
2. Determine if this is a fresh join or a reconnect (same name within 60 s).
3. Accept the WebSocket, then broadcast system join/reconnect message.
4. On reconnect, replay missed messages so the returning player catches up.
5. Ensure the per-room silence-tick background task is running.
6. Receive loop: parse JSON, route {type:"chat"} through DM, broadcast result.
7. On disconnect: mark slot disconnected, broadcast leave notice.
   Cancel tick task when no connected players remain.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

from app.dm import dm_proactive_message, dm_turn, dm_turn_private
from app.room import RECONNECT_WINDOW_SECS, Room, room_manager
from app.visibility import VisibilityRegistry


# ---------------------------------------------------------------------------
# Background silence-tick loop (one per room)
# ---------------------------------------------------------------------------


async def _room_tick_loop(room: Room) -> None:
    """Check for silence intervention every 5 seconds.

    Runs until the game finishes or the task is cancelled (room emptied).
    Gentle-level interventions use canned strings (no LLM call).
    Nudge/hint interventions call the LLM via dm_proactive_message.
    """
    try:
        while not room.game_session.finished:
            await asyncio.sleep(5)

            # Don't intervene if no one is connected
            if not any(p["connected"] for p in room.players.values()):
                continue

            trigger = room.intervention.on_tick()
            if trigger is None:
                continue

            ts = time.time()

            if trigger.level == "gentle":
                # Canned message — zero LLM cost
                text = room.intervention.random_gentle_message()
                intervention_msg: dict = {
                    "type": "dm_intervention",
                    "text": text,
                    "reason": "silence",
                    "timestamp": ts,
                }
            else:
                # LLM call for nudge / hint — serialized with dm_turn lock
                async with room._lock:
                    text = await dm_proactive_message(
                        room.game_session, trigger.level
                    )
                reason = "hint" if trigger.level == "hint" else "encouragement"
                intervention_msg = {
                    "type": "dm_intervention",
                    "text": text,
                    "reason": reason,
                    "timestamp": ts,
                }

            room.message_history.append(intervention_msg)
            await room.broadcast(intervention_msg)
            room.intervention.record_dm_spoke()

    except asyncio.CancelledError:
        pass  # Normal shutdown — tick task cancelled by disconnect handler


def _ensure_tick_running(room: Room) -> None:
    """Start the room tick task if it isn't already running."""
    if room._tick_task is None or room._tick_task.done():
        room._tick_task = asyncio.create_task(_room_tick_loop(room))


def _maybe_cancel_tick(room: Room) -> None:
    """Cancel the tick task when no connected players remain."""
    if any(p["connected"] for p in room.players.values()):
        return
    if room._tick_task and not room._tick_task.done():
        room._tick_task.cancel()
        room._tick_task = None


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    player_name: str,
) -> None:
    """Entry point called from main.py's @app.websocket route."""

    # Always accept first so we can send a proper error payload before closing.
    await websocket.accept()

    room = room_manager.get_room(room_id)
    if room is None:
        await websocket.send_json({"type": "error", "text": f"房间 {room_id} 不存在"})
        await websocket.close(code=4404)
        return

    player_name = player_name.strip()
    if not player_name:
        await websocket.send_json({"type": "error", "text": "玩家名不能为空"})
        await websocket.close(code=4400)
        return

    # ----------------------------------------------------------------
    # Determine join / reconnect / reject
    # ----------------------------------------------------------------
    player_id: str
    is_reconnect = False
    reconnect_timestamp: float = 0.0

    existing_id = room.find_player_by_name(player_name)
    if existing_id is not None:
        slot = room.players[existing_id]
        if slot["connected"]:
            # Name already active in the room
            await websocket.send_json({"type": "error", "text": f"名字「{player_name}」已被使用"})
            await websocket.close(code=4409)
            return
        # Disconnected slot — check reconnect window
        gap = time.time() - slot["last_seen"]
        if gap <= RECONNECT_WINDOW_SECS:
            is_reconnect = True
            player_id = existing_id
            reconnect_timestamp = slot["last_seen"]
            room.reconnect_player(player_id, websocket)
        else:
            # Window expired — treat as a brand-new player in the same slot
            if room.is_full():
                await websocket.send_json({"type": "error", "text": "房间已满（最多4人）"})
                await websocket.close(code=4429)
                return
            player_id = str(uuid.uuid4())
            room.add_player(player_id, player_name, websocket)
    else:
        # Completely new player
        if room.is_full():
            await websocket.send_json({"type": "error", "text": "房间已满（最多4人）"})
            await websocket.close(code=4429)
            return
        player_id = str(uuid.uuid4())
        room.add_player(player_id, player_name, websocket)

    # ----------------------------------------------------------------
    # Announce presence
    # ----------------------------------------------------------------
    if is_reconnect:
        join_notice = {"type": "system", "text": f"{player_name} 重新连接了", "timestamp": time.time()}
        await room.broadcast(join_notice)
        # Replay messages the player missed while disconnected
        missed = room.messages_since(reconnect_timestamp)
        for msg in missed:
            await room.send_to(player_id, msg)
    else:
        join_notice = {"type": "system", "text": f"{player_name} 加入了房间", "timestamp": time.time()}
        room.message_history.append(join_notice)
        await room.broadcast(join_notice)

    # ----------------------------------------------------------------
    # Send current room snapshot so the new player sees the puzzle
    # ----------------------------------------------------------------
    snapshot = {
        "type": "room_snapshot",
        "room_id": room_id,
        "puzzle_id": room.puzzle.id,
        "title": room.puzzle.title,
        "surface": room.puzzle.surface,
        "players": [
            {"id": pid, "name": p["name"], "connected": p["connected"]}
            for pid, p in room.players.items()
        ],
        "phase": room.phase,
    }
    await room.send_to(player_id, snapshot)

    # ----------------------------------------------------------------
    # Deliver this player's private clues (new joins only, not reconnects)
    # Private clues are never stored in message_history — they must not
    # appear in reconnect replay and must never reach other players.
    # ----------------------------------------------------------------
    if not is_reconnect:
        slot = room.game_session.player_slot_map.get(player_id, "")
        private_frags = room.puzzle.private_clues.get(slot, [])
        if private_frags:
            private_clue_msg = {
                "type": "private_clue",
                "slot": slot,
                "clues": [
                    {"id": pc.id, "title": pc.title, "content": pc.content}
                    for pc in private_frags
                ],
            }
            await room.send_to(player_id, private_clue_msg)

    # ----------------------------------------------------------------
    # Ensure silence-tick background task is running
    # ----------------------------------------------------------------
    _ensure_tick_running(room)

    # ----------------------------------------------------------------
    # Receive loop
    # ----------------------------------------------------------------
    try:
        while True:
            raw = await websocket.receive_text()

            # Parse JSON
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await room.send_to(player_id, {"type": "error", "text": "无效的消息格式（需要 JSON）"})
                continue

            msg_type = data.get("type")

            # ---- Private chat: player whispers directly to DM ----
            if msg_type == "private_chat":
                text = (data.get("text") or "").strip()
                if not text:
                    continue
                if room.game_session.finished:
                    await room.send_to(
                        player_id,
                        {"type": "system", "text": "游戏已结束，无法继续提问"},
                    )
                    continue
                try:
                    async with room._lock:
                        private_response = await dm_turn_private(
                            room.game_session, player_id, text
                        )
                except Exception as exc:
                    logger.exception("dm_turn_private failed for player %s: %s", player_name, exc)
                    await room.send_to(
                        player_id,
                        {"type": "error", "text": "DM 暂时无法回应，请稍后再试"},
                    )
                    continue
                await room.send_to(
                    player_id,
                    {
                        "type": "private_dm_response",
                        "response": private_response,
                        "timestamp": time.time(),
                    },
                )
                continue

            if msg_type != "chat":
                # Ignore unknown message types silently
                continue

            text = (data.get("text") or "").strip()
            if not text:
                continue

            if room.game_session.finished:
                await room.send_to(player_id, {"type": "system", "text": "游戏已结束，无法继续提问"})
                continue

            # ---- Anti-leak: block near-verbatim private clue in public chat ----
            if room.puzzle.private_clues:
                registry = VisibilityRegistry(room.game_session)
                if registry.is_own_clue_verbatim(text, player_id) or \
                        registry.is_private_content_leaked(text, player_id):
                    await room.send_to(
                        player_id,
                        {
                            "type": "leak_warning",
                            "text": "请用自己的话描述你知道的信息，不要直接展示原始线索哦～",
                            "timestamp": time.time(),
                        },
                    )
                    continue

            ts = time.time()

            # --- Intervention engine: reset silence timer ---
            room.intervention.on_player_message(player_id, text)

            # Echo the question to all players
            player_msg: dict = {
                "type": "player_message",
                "player_name": player_name,
                "text": text,
                "timestamp": ts,
            }
            room.message_history.append(player_msg)
            await room.broadcast(player_msg)

            # Route through DM — serialized so concurrent questions don't race
            try:
                async with room._lock:
                    result = await dm_turn(room.game_session, text, player_id=player_id)
            except Exception as exc:
                logger.exception("dm_turn failed for player %s: %s", player_name, exc)
                await room.send_to(
                    player_id,
                    {"type": "error", "text": "DM 暂时无法回应，请稍后再试"},
                )
                continue

            # Build broadcast payload
            dm_msg: dict = {
                "type": "dm_response",
                "player_name": player_name,
                "judgment": result.judgment,
                "response": result.response,
                "truth_progress": result.truth_progress,
                "clue_unlocked": result.clue_unlocked.model_dump() if result.clue_unlocked else None,
                "hint": result.hint,
                "truth": result.truth,
                "timestamp": time.time(),
            }
            room.message_history.append(dm_msg)
            await room.broadcast(dm_msg)

            # Record that the DM just spoke (resets intervention cooldown)
            room.intervention.record_dm_spoke()

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("Unexpected error in WebSocket handler for %s: %s", player_name, exc)
    finally:
        # Always clean up the player slot so the name is freed for reconnect.
        room.disconnect_player(player_id)
        leave_notice = {
            "type": "system",
            "text": f"{player_name} 断开连接",
            "timestamp": time.time(),
        }
        room.message_history.append(leave_notice)
        await room.broadcast(leave_notice)

        # Cancel tick task when room is fully empty
        _maybe_cancel_tick(room)
