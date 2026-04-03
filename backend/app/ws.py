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

from app.dm import dm_proactive_message, dm_turn, dm_turn_private  # noqa: E402
from app.room import RECONNECT_WINDOW_SECS, Room, room_manager  # noqa: E402
from app.visibility import VisibilityRegistry  # noqa: E402
from app.voting import VoteError, VotingModule  # noqa: E402

# ---------------------------------------------------------------------------
# Phase display helpers
# ---------------------------------------------------------------------------

_PHASE_DESCRIPTIONS_ZH: dict[str, str] = {
    "opening": "开场叙事 — 聆听案件背景介绍",
    "reading": "角色阅读 — 阅读你的角色剧本",
    "investigation_1": "调查阶段 — 搜查线索，询问NPC，向DM提问",
    "discussion": "讨论阶段 — 与其他玩家分享推理",
    "voting": "投票阶段 — 选出你认为的凶手",
    "reveal": "真相揭晓 — 案件真相大白",
    "reconstruction": "还原阶段 — 合力回答还原问题，重建事件真相",
}

_PHASE_DESCRIPTIONS_EN: dict[str, str] = {
    "opening": "Opening — listen to the case background",
    "reading": "Reading — read your character script",
    "investigation_1": "Investigation — search for clues, question NPCs, ask the DM",
    "discussion": "Discussion — share your deductions with other players",
    "voting": "Voting — choose who you believe is the culprit",
    "reveal": "Reveal — the truth of the case is unveiled",
    "reconstruction": "Reconstruction — cooperatively answer questions to rebuild the truth",
}

# Keep old name for backward compatibility
_PHASE_DESCRIPTIONS = _PHASE_DESCRIPTIONS_ZH


def _phase_desc(phase_id: str, language: str = "zh") -> str:
    """Return phase description in the given language."""
    table = _PHASE_DESCRIPTIONS_EN if language == "en" else _PHASE_DESCRIPTIONS_ZH
    return table.get(phase_id, phase_id)


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
        "phase_description": _phase_desc(phase_id, getattr(room, "language", "zh")),
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
        "characters": [{"id": c.id, "name": c.name, "public_bio": c.public_bio} for c in room.script.characters],
        "game_mode": room.script.game_mode,
        "required_players": room.script.metadata.player_count,
    }


# ---------------------------------------------------------------------------
# Murder mystery helper: send character info on join
# ---------------------------------------------------------------------------


async def _send_mm_character_info(room: Room, player_id: str, player_name: str) -> None:
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

    # Reset skip votes and silence timer for the new phase
    room._skip_votes.clear()
    room.intervention.on_phase_change()

    phase_obj = room.state_machine.current()
    duration = phase_obj.duration_seconds
    description = _phase_desc(new_phase_id, getattr(room, "language", "zh"))

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
        _vote_lang = getattr(room, "language", "zh")
        _vote_text = "Voting time! Select the culprit you believe is guilty." if _vote_lang == "en" else "投票时间到！请选出你认为的凶手。"
        vote_prompt: dict[str, Any] = {
            "type": "vote_prompt",
            "text": _vote_text,
            "candidates": [{"id": c.id, "name": c.name, "public_bio": c.public_bio} for c in room.script.characters],
            "timestamp": time.time(),
        }
        room.message_history.append(vote_prompt)
        await room.broadcast(vote_prompt)
        # Reset intervention cooldown so reminder doesn't fire immediately
        room.intervention.record_dm_spoke()

    elif new_phase_id == "reconstruction":
        await _start_reconstruction_phase(room)

    elif new_phase_id == "reveal":
        await _do_mm_reveal(room)


async def _auto_advance_from_opening(room: Room) -> None:
    """Auto-advance opening→reading→investigation_1 so players don't wait 8 minutes.

    Opening narration plays for 10s, then reading for 15s, then investigation starts.
    Players can still skip manually via skip_phase votes.
    """
    try:
        logger.info("[AUTO-ADVANCE] waiting 10s before advancing opening phase")
        await asyncio.sleep(10)
        if room.state_machine and room.state_machine.current_phase == "opening":
            logger.info("[AUTO-ADVANCE] advancing opening → reading")
            await _advance_mm_phase(room)
        await asyncio.sleep(15)
        if room.state_machine and room.state_machine.current_phase == "reading":
            logger.info("[AUTO-ADVANCE] advancing reading → investigation_1")
            await _advance_mm_phase(room)
    except Exception as exc:
        logger.exception("[AUTO-ADVANCE] failed: %s", exc)


async def _do_mm_reveal(room: Room) -> None:
    """Generate and broadcast the dramatic truth reveal narration."""
    assert room.script is not None
    assert room.orchestrator is not None
    assert room.state_machine is not None

    truth = room.script.truth
    lang = getattr(room, "language", "zh")
    game_mode = getattr(room.script, "game_mode", "whodunit")

    if game_mode == "reconstruction":
        # Reconstruction mode: reveal full story, no culprit
        if lang == "en":
            if truth.full_story:
                truth_text = f"Full Story:\n{truth.full_story}\n\nTimeline: {truth.timeline}"
            else:
                truth_text = f"Motive: {truth.motive}\nMethod: {truth.method}\nTimeline: {truth.timeline}"
            reveal_player_msg = "The full truth is revealed"
            canned_fallback = f"Truth revealed! {truth_text}"
            error_fallback = f"The full truth:\n{truth_text}"
        else:
            if truth.full_story:
                truth_text = f"完整真相：\n{truth.full_story}\n\n时间线：{truth.timeline}"
            else:
                truth_text = f"动机：{truth.motive}\n手法：{truth.method}\n时间线：{truth.timeline}"
            reveal_player_msg = "完整真相揭晓"
            canned_fallback = f"真相揭晓！{truth_text}"
            error_fallback = f"完整真相：\n{truth_text}"
    else:
        culprit_char = next((c for c in room.script.characters if c.id == truth.culprit), None)
        culprit_name = culprit_char.name if culprit_char else truth.culprit
        if lang == "en":
            truth_text = f"Culprit: {culprit_name}\nMotive: {truth.motive}\nMethod: {truth.method}\nTimeline: {truth.timeline}"
            reveal_player_msg = "The truth is revealed"
            canned_fallback = f"The truth is out! {truth_text}"
            error_fallback = f"The culprit is {culprit_name}.\n{truth_text}"
        else:
            truth_text = f"凶手：{culprit_name}\n动机：{truth.motive}\n手法：{truth.method}\n时间线：{truth.timeline}"
            reveal_player_msg = "真相揭晓"
            canned_fallback = f"真相揭晓！{truth_text}"
            error_fallback = f"真相大白！凶手是{culprit_name}。\n{truth_text}"

    # Use the narrator directly with truth injected
    reveal_judgment: Any = {"result": "是", "confidence": 1.0, "relevant_fact_ids": []}
    player_id = next(iter(room.players), None)
    try:
        if player_id:
            visible = room.orchestrator._build_visible_context(player_id)
            text = await room.orchestrator.narrator.narrate(
                judgment=reveal_judgment,
                player_message=reveal_player_msg,
                visible_context=visible,
                phase="reveal",
                truth_for_reveal=truth_text,
            )
        else:
            # No players connected — use canned reveal text
            text = canned_fallback
    except Exception:
        logger.exception("Reveal narration failed; using canned text")
        text = error_fallback

    reveal_msg: dict[str, Any] = {
        "type": "dm_response",
        "text": text,
        "phase": "reveal",
        "timestamp": time.time(),
    }
    room.message_history.append(reveal_msg)
    await room.broadcast(reveal_msg)


# ---------------------------------------------------------------------------
# Reconstruction mode handlers
# ---------------------------------------------------------------------------


async def _start_reconstruction_phase(room: Room) -> None:
    """Broadcast the first reconstruction question when the phase begins."""
    assert room.script is not None
    assert room.state_machine is not None

    phase_obj = room.state_machine.current()
    questions = phase_obj.reconstruction_questions
    if not questions:
        return

    # Reset reconstruction state for this room
    room._reconstruction_q_index = 0
    room._reconstruction_score = 0
    room._reconstruction_answers = []

    lang = getattr(room, "language", "zh")
    total = len(questions)
    first_q = questions[0]

    if lang == "en":
        intro_text = f"Reconstruction phase begins! Answer {total} questions together to rebuild the truth."
    else:
        intro_text = f"还原阶段开始！请合力回答以下 {total} 个问题，共同还原事件真相。"

    intro_msg: dict[str, Any] = {
        "type": "dm_response",
        "text": intro_text,
        "phase": "reconstruction",
        "timestamp": time.time(),
    }
    room.message_history.append(intro_msg)
    await room.broadcast(intro_msg)

    q_msg: dict[str, Any] = {
        "type": "reconstruction_question",
        "index": 0,
        "total": total,
        "question_id": first_q.id,
        "question": first_q.question,
        "timestamp": time.time(),
    }
    room.message_history.append(q_msg)
    await room.broadcast(q_msg)


async def _handle_reconstruction_answer(room: Room, player_id: str, player_name: str, data: dict[str, Any]) -> None:
    """Process a {type:'reconstruction_answer', answer:'...'} message."""
    assert room.state_machine is not None
    assert room.script is not None
    assert room.orchestrator is not None

    if room.state_machine.current_phase != "reconstruction":
        lang = getattr(room, "language", "zh")
        err = "Not in reconstruction phase." if lang == "en" else "当前不是还原阶段。"
        await room.send_to(player_id, {"type": "error", "text": err})
        return

    phase_obj = room.state_machine.current()
    questions = phase_obj.reconstruction_questions
    if not questions:
        return

    q_index = room._reconstruction_q_index
    if q_index >= len(questions):
        return  # all questions already answered

    current_q = questions[q_index]
    player_answer = (data.get("answer") or "").strip()
    if not player_answer:
        return

    lang = getattr(room, "language", "zh")
    total = len(questions)

    # Echo player's answer as a player_message
    answer_echo: dict[str, Any] = {
        "type": "player_message",
        "player_name": player_name,
        "text": player_answer,
        "timestamp": time.time(),
    }
    room.message_history.append(answer_echo)
    await room.broadcast(answer_echo)

    # Score the answer
    async with room._lock:
        result = await room.orchestrator.score_reconstruction_answer(player_answer, current_q.answer)

    score = 2 if result == "correct" else (1 if result == "partial" else 0)
    room._reconstruction_score += score
    room._reconstruction_answers.append(
        {
            "q_id": current_q.id,
            "player_name": player_name,
            "answer": player_answer,
            "result": result,
            "score": score,
        }
    )

    # Build result text
    if result == "correct":
        if lang == "en":
            result_text = f"✓ Correct! +2 points. Reference: {current_q.answer}"
        else:
            result_text = f"✓ 正确！+2分。参考答案：{current_q.answer}"
    elif result == "partial":
        if lang == "en":
            result_text = f"△ Partially correct. +1 point. Reference: {current_q.answer}"
        else:
            result_text = f"△ 部分正确。+1分。参考答案：{current_q.answer}"
    else:
        if lang == "en":
            result_text = f"✗ Not quite. +0 points. Reference: {current_q.answer}"
        else:
            result_text = f"✗ 还差一些。+0分。参考答案：{current_q.answer}"

    result_msg: dict[str, Any] = {
        "type": "reconstruction_result",
        "question_id": current_q.id,
        "index": q_index,
        "result": result,
        "score": score,
        "total_score": room._reconstruction_score,
        "text": result_text,
        "timestamp": time.time(),
    }
    room.message_history.append(result_msg)
    await room.broadcast(result_msg)

    # Advance to next question or finish
    next_index = q_index + 1
    room._reconstruction_q_index = next_index

    if next_index < len(questions):
        next_q = questions[next_index]
        next_q_msg: dict[str, Any] = {
            "type": "reconstruction_question",
            "index": next_index,
            "total": total,
            "question_id": next_q.id,
            "question": next_q.question,
            "timestamp": time.time(),
        }
        room.message_history.append(next_q_msg)
        await room.broadcast(next_q_msg)
    else:
        # All questions answered — compute final score and advance to reveal
        max_score = total * 2
        pct = int(room._reconstruction_score / max_score * 100) if max_score > 0 else 0
        if lang == "en":
            done_text = f"All questions answered! Final score: {room._reconstruction_score}/{max_score} ({pct}%). Revealing the full truth now…"
        else:
            done_text = f"所有问题已回答完毕！最终得分：{room._reconstruction_score}/{max_score}（{pct}%）。即将揭晓完整真相……"

        done_msg: dict[str, Any] = {
            "type": "reconstruction_complete",
            "total_score": room._reconstruction_score,
            "max_score": max_score,
            "pct": pct,
            "text": done_text,
            "timestamp": time.time(),
        }
        room.message_history.append(done_msg)
        await room.broadcast(done_msg)

        # Auto-advance to reveal after a brief pause
        await asyncio.sleep(3)
        await _advance_mm_phase(room)


# ---------------------------------------------------------------------------
# Murder mystery vote handler
# ---------------------------------------------------------------------------


async def _handle_mm_vote(room: Room, player_id: str, player_name: str, data: dict[str, Any]) -> None:
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
    _vc_lang = getattr(room, "language", "zh")
    _vc_text = f"Someone voted ({count}/{total} voted)" if _vc_lang == "en" else f"有人投票了（{count}/{total} 人已投票）"
    vote_cast_msg: dict[str, Any] = {
        "type": "vote_cast",
        "text": _vc_text,
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

    _vr_lang = getattr(room, "language", "zh")
    char_name_map = {c.id: c.name for c in room.script.characters}

    if result.winner:
        winner_name = char_name_map.get(result.winner, result.winner)
        if _vr_lang == "en":
            result_text = f"Vote result: {winner_name} received the most votes!"
            result_text += " Well done — you found the real culprit!" if result.is_correct else " Unfortunately, that wasn't the killer…"
        else:
            result_text = f"投票结果：{winner_name} 获得最多票数！"
            result_text += " 恭喜大家，找到了真正的凶手！" if result.is_correct else " 很遗憾，这不是真正的凶手……"
    else:
        tied_names = (", " if _vr_lang == "en" else "、").join(char_name_map.get(c, c) for c in result.tally)
        if _vr_lang == "en":
            result_text = f"Vote result: {tied_names} are tied! The truth will be revealed directly."
        else:
            result_text = f"投票结果：{tied_names} 票数相同，平局！真相将直接揭晓。"

    vote_result_msg: dict[str, Any] = {
        "type": "vote_result",
        "status": result.status.value,
        "winner": result.winner,
        "tally": dict(result.tally),  # char_id → count (frontend resolves names)
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


async def _handle_mm_chat(room: Room, player_id: str, player_name: str, text: str) -> None:
    """Route a chat message through the orchestrator streaming pipeline."""
    assert room.orchestrator is not None

    ts = time.time()
    logger.info(
        "[MM-CHAT] room=%s player=%s phase=%s text=%r",
        room.room_id,
        player_name,
        room.state_machine.current_phase if room.state_machine else "?",
        text[:80],
    )

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

    # Run streaming orchestrator pipeline
    dm_started = False
    try:
        async with room._lock:
            logger.debug("[MM-CHAT] lock acquired, starting orchestrator stream")
            stream_gen = await room.orchestrator.handle_message_stream(player_id, text)
            async for event in stream_gen:
                event_type = event.get("type", "")
                logger.debug("[MM-CHAT] stream event: type=%s", event_type)

                if event_type == "dm_stream_start":
                    # Broadcast judgment immediately — players see result before narrator finishes
                    msg: dict[str, Any] = {
                        **event,
                        "player_name": player_name,
                        "timestamp": time.time(),
                    }
                    await room.broadcast(msg)
                    dm_started = True
                    logger.info(
                        "[MM-CHAT] dm_stream_start → judgment=%s confidence=%.0f%%",
                        event.get("judgment"),
                        (event.get("confidence", 0) * 100),
                    )

                elif event_type == "dm_stream_chunk":
                    # Stream narrator tokens to all players
                    await room.broadcast({**event, "timestamp": time.time()})

                elif event_type == "dm_stream_end":
                    # Finalize — includes trace and optional clue / replacement
                    final_msg: dict[str, Any] = {
                        **event,
                        "player_name": player_name,
                        "timestamp": time.time(),
                    }
                    room.message_history.append(final_msg)
                    await room.broadcast(final_msg)
                    room.intervention.record_dm_spoke()
                    replaced = "replace" in event
                    logger.info(
                        "[MM-CHAT] dm_stream_end clue=%s replaced=%s",
                        event.get("clue") is not None,
                        replaced,
                    )

                elif event_type in ("phase_blocked", "error"):
                    logger.info("[MM-CHAT] %s → %r", event_type, event.get("text", "")[:60])
                    await room.send_to(player_id, {**event, "timestamp": time.time()})
                    # Also clear typing for all players — they saw player_message set it
                    await room.broadcast({"type": "dm_typing", "typing": False, "timestamp": time.time()})

                else:
                    # meta_response, clue_found, no_response, etc.
                    if event_type == "no_response":
                        logger.debug("[MM-CHAT] no_response (chat intent)")
                    else:
                        logger.info("[MM-CHAT] broadcast event type=%s", event_type)
                        dm_msg: dict[str, Any] = {
                            **event,
                            "player_name": player_name,
                            "timestamp": time.time(),
                        }
                        room.message_history.append(dm_msg)
                        await room.broadcast(dm_msg)
                        room.intervention.record_dm_spoke()

            logger.debug("[MM-CHAT] stream complete dm_started=%s", dm_started)

    except NotImplementedError as exc:
        logger.warning("[MM-CHAT] orchestrator stub hit: %s", exc)
        await room.send_to(player_id, {"type": "error", "text": "该功能尚未实现，请稍候。"})
    except Exception as exc:
        logger.exception("[MM-CHAT] orchestrator stream failed for player %s: %s", player_name, exc)
        await room.send_to(player_id, {"type": "error", "text": "DM 暂时无法回应，请稍后再试。"})
    finally:
        # If no DM response was sent (chat intent / phase not started), clear typing for everyone
        if not dm_started:
            await room.broadcast({"type": "dm_typing", "typing": False, "timestamp": time.time()})


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
                _full_msg = "Room is full (max 4 players)" if getattr(room, "language", "zh") == "en" else "房间已满（最多4人）"
                await websocket.send_json({"type": "error", "text": _full_msg})
                await websocket.close(code=4429)
                return
            player_id = str(uuid.uuid4())
            room.add_player(player_id, player_name, websocket)
    else:
        if room.is_full():
            _full_msg = "Room is full (max 4 players)" if getattr(room, "language", "zh") == "en" else "房间已满（最多4人）"
            await websocket.send_json({"type": "error", "text": _full_msg})
            await websocket.close(code=4429)
            return
        player_id = str(uuid.uuid4())
        room.add_player(player_id, player_name, websocket)

    # ----------------------------------------------------------------
    # Announce presence
    # ----------------------------------------------------------------
    _lang = getattr(room, "language", "zh")
    if is_reconnect:
        _reconnect_text = f"{player_name} reconnected" if _lang == "en" else f"{player_name} 重新连接了"
        join_notice = {
            "type": "system",
            "text": _reconnect_text,
            "timestamp": time.time(),
        }
        await room.broadcast(join_notice)
        missed = room.messages_since(reconnect_timestamp)
        for msg in missed:
            await room.send_to(player_id, msg)
    else:
        _join_text = f"{player_name} joined the room" if _lang == "en" else f"{player_name} 加入了房间"
        join_notice = {
            "type": "system",
            "text": _join_text,
            "timestamp": time.time(),
        }
        room.message_history.append(join_notice)
        await room.broadcast(join_notice)

    # ----------------------------------------------------------------
    # Send room snapshot to joining player; broadcast updated player
    # list to everyone else so their "Waiting for players" banner updates.
    # ----------------------------------------------------------------
    if room.game_type == "murder_mystery":
        snapshot = _mm_snapshot(room, player_id)
        await room.send_to(player_id, snapshot)
        # Broadcast updated player list to all other players
        players_update = {
            "type": "players_update",
            "players": snapshot["players"],
        }
        for pid in room.players:
            if pid != player_id:
                await room.send_to(pid, players_update)
    else:
        players_list = [{"id": pid, "name": p["name"], "connected": p["connected"]} for pid, p in room.players.items()]
        snapshot = {
            "type": "room_snapshot",
            "game_type": "turtle_soup",
            "room_id": room_id,
            "puzzle_id": room.puzzle.id,
            "title": room.puzzle.title,
            "surface": room.puzzle.surface,
            "players": players_list,
            "phase": room.phase,
        }
        await room.send_to(player_id, snapshot)
        # Broadcast updated player list to all other players
        players_update = {
            "type": "players_update",
            "players": players_list,
        }
        for pid in room.players:
            if pid != player_id:
                await room.send_to(pid, players_update)

    # ----------------------------------------------------------------
    # Deliver join-specific private info (new joins only)
    # For reconnects: re-send character_secret and current reconstruction
    # question so the player's UI is fully restored.
    # ----------------------------------------------------------------
    if not is_reconnect:
        if room.game_type == "murder_mystery":
            await _send_mm_character_info(room, player_id, player_name)
    elif room.game_type == "murder_mystery":
        # Re-send character secret so the character panel is restored
        char_id = room._char_assignments.get(player_id)
        if char_id and room.script is not None:
            char = next((c for c in room.script.characters if c.id == char_id), None)
            if char:
                phase_reading = room.state_machine.phases.get("reading") if room.state_machine else None
                per_player_content: str | None = None
                if phase_reading and phase_reading.per_player_content:
                    per_player_content = phase_reading.per_player_content.get(char_id)
                await room.send_to(player_id, {
                    "type": "character_secret",
                    "char_id": char.id,
                    "char_name": char.name,
                    "secret_bio": char.secret_bio,
                    "personal_script": per_player_content,
                })
        # Re-send the current reconstruction question if in reconstruction phase
        if (
            room.state_machine is not None
            and room.state_machine.current_phase == "reconstruction"
            and room.script is not None
        ):
            phase_obj = room.state_machine.current()
            questions = phase_obj.reconstruction_questions
            q_index = room._reconstruction_q_index
            if questions and q_index < len(questions):
                current_q = questions[q_index]
                await room.send_to(player_id, {
                    "type": "reconstruction_question",
                    "index": q_index,
                    "total": len(questions),
                    "question_id": current_q.id,
                    "question": current_q.question,
                    "timestamp": time.time(),
                })
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
                        "clues": [{"id": pc.id, "title": pc.title, "content": pc.content} for pc in private_frags],
                    },
                )

    # ----------------------------------------------------------------
    # Murder mystery: send opening narration once a second player joins
    # ----------------------------------------------------------------
    if (
        room.game_type == "murder_mystery"
        and not room._opening_narrated
        and room.state_machine is not None
        and room.state_machine.current_phase == "opening"
        and sum(1 for p in room.players.values() if p["connected"]) >= 2
    ):
        room._opening_narrated = True
        assert room.script is not None
        opening_phase = room.state_machine.phases.get("opening")
        if opening_phase and opening_phase.dm_script:
            dm_open: dict[str, Any] = {
                "type": "dm_response",
                "text": opening_phase.dm_script,
                "phase": "opening",
                "timestamp": time.time(),
            }
            room.message_history.append(dm_open)
            await room.broadcast(dm_open)
        # Auto-advance: opening → reading → investigation_1 after short delays
        # so players don't wait the full 120s+360s before DM responds to questions
        asyncio.create_task(_auto_advance_from_opening(room))

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

                # Reconstruction answer
                if msg_type == "reconstruction_answer":
                    await _handle_reconstruction_answer(room, player_id, player_name, data)
                    continue

                # Skip-phase vote
                if msg_type == "skip_phase":
                    assert room.state_machine is not None
                    current = room.state_machine.current_phase
                    if current == "reveal":
                        # Can't skip the final phase
                        continue
                    room._skip_votes.add(player_id)
                    connected_ids = [pid for pid, p in room.players.items() if p["connected"]]
                    needed = (len(connected_ids) // 2) + 1  # simple majority
                    voted = len(room._skip_votes & set(connected_ids))
                    if voted >= needed:
                        # Simple majority reached — advance immediately
                        room._skip_votes.clear()
                        await _advance_mm_phase(room)
                    else:
                        # Broadcast vote progress so all players see it
                        await room.broadcast(
                            {
                                "type": "skip_vote_update",
                                "phase": current,
                                "voted": voted,
                                "needed": needed,
                                "timestamp": time.time(),
                            }
                        )
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
                        private_response = await dm_turn_private(room.game_session, player_id, text)
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
                await room.send_to(player_id, {"type": "system", "text": "游戏已结束，无法继续提问"})
                continue

            # Anti-leak check
            if room.puzzle.private_clues:
                registry = VisibilityRegistry(room.game_session)
                if registry.is_own_clue_verbatim(text, player_id) or registry.is_private_content_leaked(text, player_id):
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

            await room.broadcast({"type": "dm_typing", "typing": True, "timestamp": time.time()})
            try:
                async with room._lock:
                    result = await dm_turn(room.game_session, text, player_id=player_id)
            except Exception as exc:
                logger.exception("dm_turn failed for %s: %s", player_name, exc)
                await room.broadcast({"type": "dm_typing", "typing": False, "timestamp": time.time()})
                await room.send_to(
                    player_id,
                    {"type": "error", "text": "DM 暂时无法回应，请稍后再试"},
                )
                continue
            await room.broadcast({"type": "dm_typing", "typing": False, "timestamp": time.time()})

            dm_msg_ts: dict[str, Any] = {
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
        # Broadcast updated player list so other players' banners update
        players_update = {
            "type": "players_update",
            "players": [{"id": pid, "name": p["name"], "connected": p["connected"]} for pid, p in room.players.items()],
        }
        await room.broadcast(players_update)
        _maybe_cancel_tick(room)
