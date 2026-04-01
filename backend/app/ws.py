"""WebSocket handler for multiplayer rooms.

Supports two game types:
  turtle_soup    → existing dm.py flow (Phase 2-3, unchanged)
  murder_mystery → agents/orchestrator.py flow (Phase 4)

Murder mystery additions:
  - Character assignment sent to each player on join
  - Per-player secret_bio sent via private message
  - Phase timeout background task → auto-advance, broadcast phase_change
  - Vote messages ({type:"vote", target:"<char_id>"}) handled inline
  - Reveal phase → automatic truth narration broadcast
  - Phase-aware intervention (reading=silent, voting=reminder only, etc.)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

from app.dm import dm_proactive_message, dm_turn, dm_turn_private
from app.room import RECONNECT_WINDOW_SECS, Room, room_manager
from app.visibility import VisibilityRegistry
from app.voting import VoteError, VotingModule

# ---------------------------------------------------------------------------
# Phase display helpers
# ---------------------------------------------------------------------------

_PHASE_DESCRIPTIONS: dict[str, str] = {
    "opening":         "开场叙事 — 聆听案件背景介绍",
    "reading":         "角色阅读 — 阅读你的角色剧本",
    "investigation_1": "调查阶段 — 搜查线索，询问NPC，向DM提问",
    "discussion":      "讨论阶段 — 与其他玩家分享推理",
    "voting":          "投票阶段 — 选出你认为的凶手",
    "reveal":          "真相揭晓 — 案件真相大白",
}


# ---------------------------------------------------------------------------
# Murder mystery helper: build room snapshot for MM
# ---------------------------------------------------------------------------


def _mm_snapshot(room: Room, player_id: str) -> dict[str, Any]:
    """Build a room_snapshot payload for a murder mystery room."""
    assert room.script is not None
    assert room.state_machine is not None

    phase_id = room.state_machine.current_phase
    time_remaining = room.state_machine.time_remaining()

    return {
        "type": "room_snapshot",
        "game_type": "murder_mystery",
        "room_id": room.room_id,
        "script_id": room.script.id,
        "title": room.script.title,
        "current_phase": phase_id,
        "phase_description": _PHASE_DESCRIPTIONS.get(phase_id, phase_id),
        "time_remaining": None if time_remaining == float("inf") else int(time_remaining),
        "players": [
            {
                "id": pid,
                "name": p["name"],
                "connected": p["connected"],
                "character": room._char_assignments.get(pid),
            }
            for pid, p in room.players.items()
        ],
        # Public character list — no secret_bio, no is_culprit
        "characters": [
            {"id": c.id, "name": c.name, "public_bio": c.public_bio}
            for c in room.script.characters
        ],
    }


# ---------------------------------------------------------------------------
# Murder mystery helper: send character info on join
# ---------------------------------------------------------------------------


async def _send_mm_character_info(
    room: Room, player_id: str, player_name: str
) -> None:
    """Broadcast public character assignment + send private secret_bio."""
    assert room.script is not None
    assert room.state_machine is not None

    char_id = room._char_assignments.get(player_id)
    if char_id is None:
        return  # no more characters available

    char = next((c for c in room.script.characters if c.id == char_id), None)
    if char is None:
        return

    # Public: tell everyone who got which character
    pub_msg: dict[str, Any] = {
        "type": "character_assigned",
        "player_name": player_name,
        "char_id": char.id,
        "char_name": char.name,
        "public_bio": char.public_bio,
        "timestamp": time.time(),
    }
    room.message_history.append(pub_msg)
    await room.broadcast(pub_msg)

    # Private: send secret_bio + personal script only to this player
    phase_reading = room.state_machine.phases.get("reading")
    per_player_content: str | None = None
    if phase_reading and phase_reading.per_player_content:
        per_player_content = phase_reading.per_player_content.get(char_id)

    private_msg: dict[str, Any] = {
        "type": "character_secret",
        "char_id": char.id,
        "char_name": char.name,
        "secret_bio": char.secret_bio,
        "personal_script": per_player_content,
    }
    await room.send_to(player_id, private_msg)


# ---------------------------------------------------------------------------
# Murder mystery helper: phase transition
# ---------------------------------------------------------------------------


async def _advance_mm_phase(room: Room) -> None:
    """Advance the murder mystery state machine and broadcast the change."""
    assert room.state_machine is not None
    assert room.script is not None

    new_phase_id = room.state_machine.advance()
    if new_phase_id is None:
        return  # already terminal

    phase_obj = room.state_machine.current()
    duration = phase_obj.duration_seconds
    description = _PHASE_DESCRIPTIONS.get(new_phase_id, new_phase_id)

    phase_msg: dict[str, Any] = {
        "type": "phase_change",
        "new_phase": new_phase_id,
        "duration": duration,
        "description": description,
        "timestamp": time.time(),
    }
    room.message_history.append(phase_msg)
    await room.broadcast(phase_msg)

    # Phase-specific setup on entry
    if new_phase_id == "opening":
        # Send the opening DM script
        if phase_obj.dm_script:
            dm_msg: dict[str, Any] = {
                "type": "dm_response",
                "text": phase_obj.dm_script,
                "phase": "opening",
                "timestamp": time.time(),
            }
            room.message_history.append(dm_msg)
            await room.broadcast(dm_msg)

    elif new_phase_id == "voting":
        # Lazy-create the VotingModule now that all players are in
        player_ids = list(room.players.keys())
        room.voting = VotingModule(
            player_ids=player_ids,
            culprit_id=room.script.truth.culprit,
        )
        vote_prompt: dict[str, Any] = {
            "type": "vote_prompt",
            "text": "投票时间到！请选出你认为的凶手，发送 {\"type\": \"vote\", \"target\": \"<char_id>\"} 。",
            "candidates": [
                {"id": c.id, "name": c.name, "public_bio": c.public_bio}
                for c in room.script.characters
            ],
            "timestamp": time.time(),
        }
        room.message_history.append(vote_prompt)
        await room.broadcast(vote_prompt)

    elif new_phase_id == "reveal":
        await _do_mm_reveal(room)


async def _do_mm_reveal(room: Room) -> None:
    """Generate and broadcast the dramatic truth reveal narration."""
    assert room.script is not None
    assert room.orchestrator is not None
    assert room.state_machine is not None

    truth = room.script.truth
    culprit_char = next(
        (c for c in room.script.characters if c.id == truth.culprit), None
    )
    culprit_name = culprit_char.name if culprit_char else truth.culprit
    truth_text = (
        f"凶手：{culprit_name}\n"
        f"动机：{truth.motive}\n"
        f"手法：{truth.method}\n"
        f"时间线：{truth.timeline}"
    )

    # Use the narrator directly with truth injected
    reveal_judgment: Any = {"result": "是", "confidence": 1.0, "relevant_fact_ids": []}
    player_id = next(iter(room.players), None)
    try:
        if player_id:
            from app.visibility import VisibleContext
            visible = room.orchestrator._build_visible_context(player_id)
            text = await room.orchestrator.narrator.narrate(
                judgment=reveal_judgment,
                player_message="真相揭晓",
                visible_context=visible,
                phase="reveal",
                truth_for_reveal=truth_text,
            )
        else:
            # No players connected — use canned reveal text
            text = f"真相揭晓！{truth_text}"
    except Exception:
        logger.exception("Reveal narration failed; using canned text")
        text = f"真相大白！凶手是{culprit_name}。\n{truth_text}"

    reveal_msg: dict[str, Any] = {
        "type": "dm_response",
        "text": text,
        "phase": "reveal",
        "timestamp": time.time(),
    }
    room.message_history.append(reveal_msg)
    await room.broadcast(reveal_msg)


# ---------------------------------------------------------------------------
# Murder mystery vote handler
# ---------------------------------------------------------------------------


async def _handle_mm_vote(
    room: Room, player_id: str, player_name: str, data: dict[str, Any]
) -> None:
    """Process a {type:"vote", target:"<char_id>"} message."""
    assert room.state_machine is not None

    # Guard: only in voting phase
    if room.state_machine.current_phase != "voting":
        await room.send_to(
            player_id,
            {"type": "error", "text": "当前不是投票阶段。"},
        )
        return

    target = (data.get("target") or "").strip()
    if not target:
        await room.send_to(
            player_id,
            {"type": "error", "text": "请指定投票对象（target 字段）。"},
        )
        return

    # Lazy-create VotingModule if phase was entered without advancing through it
    if room.voting is None:
        assert room.script is not None
        room.voting = VotingModule(
            player_ids=list(room.players.keys()),
            culprit_id=room.script.truth.culprit,
        )

    try:
        room.voting.cast_vote(player_id, target)
    except VoteError as exc:
        await room.send_to(player_id, {"type": "error", "text": str(exc)})
        return

    count = room.voting.vote_count()
    total = len(room.players)

    # Anonymous broadcast
    vote_cast_msg: dict[str, Any] = {
        "type": "vote_cast",
        "text": f"有人投票了（{count}/{total} 人已投票）",
        "count": count,
        "total": total,
        "timestamp": time.time(),
    }
    room.message_history.append(vote_cast_msg)
    await room.broadcast(vote_cast_msg)

    # All voted → tally and advance
    if room.voting.all_voted():
        await _resolve_mm_votes(room)


async def _resolve_mm_votes(room: Room) -> None:
    """Tally votes, broadcast results, and advance to reveal."""
    assert room.voting is not None
    assert room.script is not None

    result = room.voting.resolve()

    # Build readable tally
    char_name_map = {c.id: c.name for c in room.script.characters}
    tally_readable = {
        char_name_map.get(cid, cid): cnt for cid, cnt in result.tally.items()
    }

    if result.winner:
        winner_name = char_name_map.get(result.winner, result.winner)
        result_text = f"投票结果：{winner_name} 获得最多票数！"
        if result.is_correct:
            result_text += " 恭喜大家，找到了真正的凶手！"
        else:
            result_text += " 很遗憾，这不是真正的凶手……"
    else:
        tied = "、".join(char_name_map.get(c, c) for c in result.tally)
        result_text = f"投票结果：{tied} 票数相同，平局！真相将直接揭晓。"

    vote_result_msg: dict[str, Any] = {
        "type": "vote_result",
        "status": result.status.value,
        "winner": result.winner,
        "tally": tally_readable,
        "is_correct": result.is_correct,
        "text": result_text,
        "timestamp": time.time(),
    }
    room.message_history.append(vote_result_msg)
    await room.broadcast(vote_result_msg)

    # Advance to reveal
    await _advance_mm_phase(room)


# ---------------------------------------------------------------------------
# Murder mystery chat handler
# ---------------------------------------------------------------------------


async def _handle_mm_chat(
    room: Room, player_id: str, player_name: str, text: str
) -> None:
    """Route a chat message through the orchestrator pipeline."""
    assert room.orchestrator is not None

    ts = time.time()

    # Reset intervention silence timer
    room.intervention.on_player_message(player_id, text)

    # Echo to all players
    player_msg: dict[str, Any] = {
        "type": "player_message",
        "player_name": player_name,
        "text": text,
        "timestamp": ts,
    }
    room.message_history.append(player_msg)
    await room.broadcast(player_msg)

    # Run orchestrator pipeline
    try:
        async with room._lock:
            orch_response = await room.orchestrator.handle_message(player_id, text)
    except NotImplementedError as exc:
        logger.warning("Orchestrator stub hit: %s", exc)
        await room.send_to(
            player_id,
            {"type": "error", "text": "该功能尚未实现，请稍候。"},
        )
        return
    except Exception as exc:
        logger.exception("Orchestrator failed for player %s: %s", player_name, exc)
        await room.send_to(
            player_id,
            {"type": "error", "text": "DM 暂时无法回应，请稍后再试。"},
        )
        return

    if orch_response is None:
        # "chat" intent — player-to-player, no DM reply; already echoed above
        return

    dm_msg: dict[str, Any] = {
        "type": orch_response.type,
        "text": orch_response.text,
        "clue": orch_response.clue,
        "timestamp": time.time(),
    }
    room.message_history.append(dm_msg)

    if orch_response.type == "clue_found":
        # Clue found messages are broadcast to all (public clues)
        await room.broadcast(dm_msg)
    else:
        # DM response, phase_blocked, error → send only to asking player
        await room.send_to(player_id, dm_msg)

    room.intervention.record_dm_spoke()


# ---------------------------------------------------------------------------
# Background tick loop (one per room)
# ---------------------------------------------------------------------------


async def _room_tick_loop(room: Room) -> None:
    """Check for silence/phase timeout every 5 seconds."""
    try:
        while True:
            await asyncio.sleep(5)

            if not any(p["connected"] for p in room.players.values()):
                continue

            if room.game_type == "murder_mystery":
                await _mm_tick(room)
            else:
                await _ts_tick(room)

    except asyncio.CancelledError:
        pass


async def _mm_tick(room: Room) -> None:
    """Tick logic for murder mystery rooms."""
    assert room.state_machine is not None

    if room.is_mm_game_over():
        return

    # Phase timeout → auto-advance
    if room.state_machine.is_timed_out():
        await _advance_mm_phase(room)
        return

    # Phase-aware intervention
    phase = room.state_machine.current_phase
    trigger = room.intervention.on_tick(phase=phase)
    if trigger is None:
        return

    if trigger.canned_text:
        text = trigger.canned_text
    else:
        text = room.intervention.random_gentle_message(phase=phase, lang=room.language)

    intervention_msg: dict[str, Any] = {
        "type": "dm_intervention",
        "text": text,
        "reason": trigger.type,
        "timestamp": time.time(),
    }
    room.message_history.append(intervention_msg)
    await room.broadcast(intervention_msg)
    room.intervention.record_dm_spoke()


async def _ts_tick(room: Room) -> None:
    """Tick logic for turtle soup rooms (unchanged from Phase 3)."""
    if not room.game_session or room.game_session.finished:
        return

    trigger = room.intervention.on_tick()
    if trigger is None:
        return

    ts = time.time()

    if trigger.level == "gentle":
        text = room.intervention.random_gentle_message(lang=room.language)
        msg: dict[str, Any] = {
            "type": "dm_intervention",
            "text": text,
            "reason": "silence",
            "timestamp": ts,
        }
    else:
        async with room._lock:
            text = await dm_proactive_message(room.game_session, trigger.level)
        reason = "hint" if trigger.level == "hint" else "encouragement"
        msg = {
            "type": "dm_intervention",
            "text": text,
            "reason": reason,
            "timestamp": ts,
        }

    room.message_history.append(msg)
    await room.broadcast(msg)
    room.intervention.record_dm_spoke()


def _ensure_tick_running(room: Room) -> None:
    if room._tick_task is None or room._tick_task.done():
        room._tick_task = asyncio.create_task(_room_tick_loop(room))


def _maybe_cancel_tick(room: Room) -> None:
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
            await websocket.send_json({"type": "error", "text": f"名字「{player_name}」已被使用"})
            await websocket.close(code=4409)
            return
        gap = time.time() - slot["last_seen"]
        if gap <= RECONNECT_WINDOW_SECS:
            is_reconnect = True
            player_id = existing_id
            reconnect_timestamp = slot["last_seen"]
            room.reconnect_player(player_id, websocket)
        else:
            if room.is_full():
                await websocket.send_json({"type": "error", "text": "房间已满（最多4人）"})
                await websocket.close(code=4429)
                return
            player_id = str(uuid.uuid4())
            room.add_player(player_id, player_name, websocket)
    else:
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
        join_notice = {
            "type": "system",
            "text": f"{player_name} 重新连接了",
            "timestamp": time.time(),
        }
        await room.broadcast(join_notice)
        missed = room.messages_since(reconnect_timestamp)
        for msg in missed:
            await room.send_to(player_id, msg)
    else:
        join_notice = {
            "type": "system",
            "text": f"{player_name} 加入了房间",
            "timestamp": time.time(),
        }
        room.message_history.append(join_notice)
        await room.broadcast(join_notice)

    # ----------------------------------------------------------------
    # Send room snapshot
    # ----------------------------------------------------------------
    if room.game_type == "murder_mystery":
        snapshot = _mm_snapshot(room, player_id)
    else:
        snapshot = {
            "type": "room_snapshot",
            "game_type": "turtle_soup",
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
    # Deliver join-specific private info (new joins only)
    # ----------------------------------------------------------------
    if not is_reconnect:
        if room.game_type == "murder_mystery":
            await _send_mm_character_info(room, player_id, player_name)
        else:
            # Turtle soup: deliver private clues
            assert room.game_session is not None
            assert room.puzzle is not None
            player_slot = room.game_session.player_slot_map.get(player_id, "")
            private_frags = room.puzzle.private_clues.get(player_slot, [])
            if private_frags:
                await room.send_to(
                    player_id,
                    {
                        "type": "private_clue",
                        "slot": player_slot,
                        "clues": [
                            {"id": pc.id, "title": pc.title, "content": pc.content}
                            for pc in private_frags
                        ],
                    },
                )

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

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await room.send_to(player_id, {"type": "error", "text": "无效的消息格式（需要 JSON）"})
                continue

            msg_type = data.get("type")

            # ============================================================
            # MURDER MYSTERY routing
            # ============================================================
            if room.game_type == "murder_mystery":
                # Vote message
                if msg_type == "vote":
                    await _handle_mm_vote(room, player_id, player_name, data)
                    continue

                # Chat / question / search → orchestrator
                if msg_type == "chat":
                    text = (data.get("text") or "").strip()
                    if not text:
                        continue
                    if room.is_mm_game_over():
                        await room.send_to(
                            player_id,
                            {"type": "system", "text": "游戏已结束。"},
                        )
                        continue
                    await _handle_mm_chat(room, player_id, player_name, text)
                    continue

                # Ignore unknown types silently
                continue

            # ============================================================
            # TURTLE SOUP routing (existing Phase 2-3 logic, unchanged)
            # ============================================================

            # Private chat
            if msg_type == "private_chat":
                text = (data.get("text") or "").strip()
                if not text:
                    continue
                assert room.game_session is not None
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
                    logger.exception("dm_turn_private failed for %s: %s", player_name, exc)
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
                continue

            text = (data.get("text") or "").strip()
            if not text:
                continue

            assert room.game_session is not None
            assert room.puzzle is not None

            if room.game_session.finished:
                await room.send_to(
                    player_id, {"type": "system", "text": "游戏已结束，无法继续提问"}
                )
                continue

            # Anti-leak check
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
            room.intervention.on_player_message(player_id, text)

            player_msg_ts: dict[str, Any] = {
                "type": "player_message",
                "player_name": player_name,
                "text": text,
                "timestamp": ts,
            }
            room.message_history.append(player_msg_ts)
            await room.broadcast(player_msg_ts)

            try:
                async with room._lock:
                    result = await dm_turn(room.game_session, text, player_id=player_id)
            except Exception as exc:
                logger.exception("dm_turn failed for %s: %s", player_name, exc)
                await room.send_to(
                    player_id,
                    {"type": "error", "text": "DM 暂时无法回应，请稍后再试"},
                )
                continue

            dm_msg_ts: dict[str, Any] = {
                "type": "dm_response",
                "player_name": player_name,
                "judgment": result.judgment,
                "response": result.response,
                "truth_progress": result.truth_progress,
                "clue_unlocked": result.clue_unlocked.model_dump()
                    if result.clue_unlocked else None,
                "hint": result.hint,
                "truth": result.truth,
                "timestamp": time.time(),
            }
            room.message_history.append(dm_msg_ts)
            await room.broadcast(dm_msg_ts)
            room.intervention.record_dm_spoke()

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("Unexpected error in WebSocket handler for %s: %s", player_name, exc)
    finally:
        room.disconnect_player(player_id)
        leave_notice = {
            "type": "system",
            "text": f"{player_name} 断开连接",
            "timestamp": time.time(),
        }
        room.message_history.append(leave_notice)
        await room.broadcast(leave_notice)
        _maybe_cancel_tick(room)
