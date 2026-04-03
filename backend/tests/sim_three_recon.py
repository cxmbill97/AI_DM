"""
Three-player reconstruction game simulation — signal_lost_001.
Connects via WebSocket, plays through all phases, logs bugs.
Run: uv run python tests/sim_three_recon.py
"""

import asyncio
import json
import time
import urllib.request
from collections import defaultdict

import websockets

HTTP = "http://localhost:8000"
BUGS: list[dict] = []


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def bug(title: str, detail: str) -> None:
    BUGS.append({"title": title, "detail": detail})
    log(f"  🐛 BUG: {title} — {detail}")


def ok(msg: str) -> None:
    log(f"  ✅ {msg}")


def http_post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{HTTP}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


class Player:
    def __init__(self, name: str, room_id: str):
        self.name = name
        self.room_id = room_id
        self.ws = None
        self._q: asyncio.Queue = asyncio.Queue()
        self.all_msgs: list[dict] = []
        self.current_phase: str | None = None
        self.phase_history: list[str] = []
        self.char_id: str | None = None
        self.char_name: str | None = None
        self.secret_bio: str | None = None
        self.personal_script: str | None = None
        self.recon_questions: list[dict] = []
        self.recon_results: list[dict] = []
        self.required_players: int = 2
        self.game_mode: str = "whodunit"

    async def connect(self) -> None:
        url = f"ws://localhost:8000/ws/{self.room_id}?player_name={self.name}"
        self.ws = await websockets.connect(url)
        asyncio.create_task(self._reader())
        log(f"  [{self.name}] connected")

    async def _reader(self) -> None:
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                self.all_msgs.append(msg)
                t = msg.get("type", "")

                if t == "room_snapshot":
                    self.current_phase = msg.get("current_phase")
                    self.required_players = msg.get("required_players", 2)
                    self.game_mode = msg.get("game_mode", "whodunit")

                elif t == "phase_change":
                    new_phase = msg["new_phase"]
                    self.current_phase = new_phase
                    self.phase_history.append(new_phase)

                elif t == "character_secret":
                    self.char_id = msg["char_id"]
                    self.char_name = msg["char_name"]
                    self.secret_bio = msg["secret_bio"]
                    self.personal_script = msg.get("personal_script")

                elif t == "character_assigned":
                    if msg["player_name"] == self.name:
                        self.char_id = msg["char_id"]
                        self.char_name = msg["char_name"]

                elif t == "reconstruction_question":
                    self.recon_questions.append(msg)

                elif t == "reconstruction_result":
                    self.recon_results.append(msg)

                await self._q.put(msg)
        except Exception:
            pass

    async def recv(self, timeout: float = 20) -> dict | None:
        try:
            return await asyncio.wait_for(self._q.get(), timeout=timeout)
        except TimeoutError:
            return None

    async def drain(self, seconds: float = 2.0) -> list[dict]:
        out = []
        deadline = time.time() + seconds
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                msg = await asyncio.wait_for(self._q.get(), timeout=remaining)
                out.append(msg)
            except TimeoutError:
                break
        return out

    async def send(self, payload: dict) -> None:
        await self.ws.send(json.dumps(payload))

    def get_all(self, msg_type: str) -> list[dict]:
        return [m for m in self.all_msgs if m.get("type") == msg_type]

    def has_received(self, msg_type: str) -> bool:
        return any(m.get("type") == msg_type for m in self.all_msgs)

    async def close(self) -> None:
        if self.ws:
            await self.ws.close()


async def wait_all_phase(players: list[Player], phase: str, timeout: float = 90) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if all(p.current_phase == phase for p in players):
            return True
        await asyncio.sleep(0.5)
    return False


async def skip_to(players: list[Player], target: str, max_skips: int = 5) -> None:
    for _ in range(max_skips):
        if all(p.current_phase == target for p in players):
            return
        for p in players:
            await p.send({"type": "skip_phase"})
        await asyncio.sleep(2)


async def run() -> None:
    log("=" * 60)
    log("THREE-PLAYER RECONSTRUCTION SIMULATION — signal_lost_001")
    log("=" * 60)

    # ──────────────────────────────────────────────────────────────
    # 1. Create room
    # ──────────────────────────────────────────────────────────────
    log("\n[1] Creating reconstruction room...")
    body = http_post("/api/rooms", {
        "game_type": "murder_mystery",
        "script_id": "signal_lost_001",
        "language": "zh",
    })
    room_id = body["room_id"]
    log(f"  room_id={room_id} game_type={body['game_type']}")
    if body.get("game_type") != "murder_mystery":
        bug("Wrong game_type returned", f"Expected murder_mystery, got {body.get('game_type')}")

    # ──────────────────────────────────────────────────────────────
    # 2. Connect all 3 players
    # ──────────────────────────────────────────────────────────────
    log("\n[2] Connecting 3 players...")
    names = ["林晓薇", "王建国", "张明"]
    players = [Player(n, room_id) for n in names]
    lin, wang, zhang = players

    for p in players:
        await p.connect()
        await asyncio.sleep(0.3)

    await asyncio.sleep(1.5)

    # CHECK: room_snapshot includes required_players and game_mode
    for p in players:
        snap = next((m for m in p.all_msgs if m.get("type") == "room_snapshot"), None)
        if snap is None:
            bug(f"[{p.name}] No room_snapshot received", "")
        else:
            if snap.get("required_players") != 3:
                bug("room_snapshot.required_players wrong",
                    f"[{p.name}] got {snap.get('required_players')}, expected 3")
            else:
                ok(f"[{p.name}] room_snapshot.required_players=3")
            if snap.get("game_mode") != "reconstruction":
                bug("room_snapshot.game_mode wrong",
                    f"[{p.name}] got {snap.get('game_mode')}, expected 'reconstruction'")
            else:
                ok(f"[{p.name}] room_snapshot.game_mode=reconstruction")

    # CHECK: all players received character_secret (private)
    await asyncio.sleep(0.5)
    for p in players:
        if p.secret_bio:
            ok(f"[{p.name}] character_secret received, char={p.char_name}")
        else:
            bug(f"[{p.name}] No character_secret received", "Player has no secret bio")

    # CHECK: all players got different characters
    assigned = {p.char_id for p in players if p.char_id}
    if len(assigned) == 3:
        ok(f"All 3 characters assigned uniquely: {assigned}")
    else:
        bug("Character assignment collision", f"Got {assigned} for 3 players")

    # ──────────────────────────────────────────────────────────────
    # 3. Opening narration fires once 2nd player joins
    # ──────────────────────────────────────────────────────────────
    log("\n[3] Waiting for opening narration...")
    await asyncio.sleep(2)
    openings = lin.get_all("dm_response")
    opening_dm = [m for m in openings if m.get("phase") == "opening"]
    if opening_dm:
        preview = opening_dm[0].get("text", "")[:60]
        ok(f"Opening DM narration received: {preview!r}…")
    else:
        bug("No opening DM narration", "Expected phase='opening' dm_response after 2nd player joins")

    # ──────────────────────────────────────────────────────────────
    # 4. Wait for auto-advance to investigation_1
    # ──────────────────────────────────────────────────────────────
    log("\n[4] Waiting for auto-advance to investigation_1 (≤60s)...")
    t0 = time.time()
    reached = await wait_all_phase(players, "investigation_1", timeout=60)
    if reached:
        ok(f"All players reached investigation_1 in {time.time()-t0:.0f}s")
    else:
        bug("Auto-advance to investigation_1 failed",
            f"lin={lin.current_phase} wang={wang.current_phase} zhang={zhang.current_phase}")
        log("  Attempting manual skip...")
        await skip_to(players, "investigation_1")

    # CHECK: phase history consistent across players
    for p in players:
        if "investigation_1" not in p.phase_history:
            bug(f"[{p.name}] missing phase_change for investigation_1",
                f"phase_history={p.phase_history}")

    # CHECK: personal_script delivered during reading phase
    for p in players:
        if p.personal_script:
            ok(f"[{p.name}] personal_script received ({len(p.personal_script)} chars)")
        else:
            bug(f"[{p.name}] No personal_script", "per_player_content not delivered")

    # ──────────────────────────────────────────────────────────────
    # 5. Investigation — ask questions, search for clues
    # ──────────────────────────────────────────────────────────────
    log("\n[5] Investigation phase — asking questions & searching clues...")
    await asyncio.sleep(1)

    # Ask a question from 林晓薇
    await lin.send({"type": "chat", "text": "梅博士为什么要破坏天线？"})
    await asyncio.sleep(0.5)

    # Check dm_typing or response
    resp = await lin.recv(timeout=25)
    dm_response_seen = False
    deadline = time.time() + 30
    while time.time() < deadline:
        msgs = await lin.drain(seconds=1.5)
        for m in msgs:
            if m.get("type") in ("dm_stream_end", "dm_response", "clue_found"):
                dm_response_seen = True
        if dm_response_seen:
            break

    if dm_response_seen:
        ok("[林晓薇] DM responded to investigation question")
    else:
        bug("DM did not respond in investigation phase",
            "No dm_stream_end/dm_response after 30s")

    # Search for a clue
    await zhang.send({"type": "chat", "text": "搜查天线控制电路"})
    await asyncio.sleep(2)
    clue_msgs = zhang.get_all("dm_stream_end") + zhang.get_all("clue_found")
    clue_found = any(m.get("clue") for m in clue_msgs)
    if clue_found:
        ok("[张明] Clue found via search")
    else:
        log("  [张明] No clue unlocked on first search (may need exact keywords)")

    # 王建国 asks NPC
    await wang.send({"type": "chat", "text": "@小青 请问23:05的闸机记录是什么？"})
    await asyncio.sleep(3)
    npc_resp = wang.get_all("dm_stream_end") + wang.get_all("dm_response")
    if npc_resp:
        ok("[王建国] NPC responded")
    else:
        bug("NPC did not respond", "No DM response after @小青 question")

    # ──────────────────────────────────────────────────────────────
    # 6. Skip to discussion
    # ──────────────────────────────────────────────────────────────
    log("\n[6] Skipping to discussion phase...")
    await skip_to(players, "discussion", max_skips=4)
    await asyncio.sleep(1)
    if all(p.current_phase == "discussion" for p in players):
        ok("All players in discussion phase")
    else:
        bug("Failed to reach discussion",
            f"lin={lin.current_phase} wang={wang.current_phase} zhang={zhang.current_phase}")

    # Players chat during discussion
    await lin.send({"type": "chat", "text": "我觉得梅博士是为了独占数据"})
    await wang.send({"type": "chat", "text": "对，我看到她背着大包离开了"})
    await zhang.send({"type": "chat", "text": "天线电路被她提前破坏了，这是蓄谋"})
    await asyncio.sleep(1.5)

    player_msgs = lin.get_all("player_message")
    if len(player_msgs) >= 3:
        ok(f"Discussion chat working — {len(player_msgs)} player messages seen by 林晓薇")
    else:
        bug("Discussion chat not delivered", f"林晓薇 only saw {len(player_msgs)} player_messages")

    # ──────────────────────────────────────────────────────────────
    # 7. Skip to reconstruction phase
    # ──────────────────────────────────────────────────────────────
    log("\n[7] Skipping to reconstruction phase...")
    await skip_to(players, "reconstruction", max_skips=4)
    await asyncio.sleep(2)
    if all(p.current_phase == "reconstruction" for p in players):
        ok("All players in reconstruction phase")
    else:
        bug("Failed to reach reconstruction",
            f"lin={lin.current_phase} wang={wang.current_phase} zhang={zhang.current_phase}")

    # CHECK: reconstruction_question broadcast on phase entry
    await asyncio.sleep(1)
    for p in players:
        if p.recon_questions:
            q0 = p.recon_questions[0]
            ok(f"[{p.name}] First reconstruction_question received: index={q0['index']} total={q0['total']}")
            if q0.get("total") != 6:
                bug("Wrong question total", f"Expected 6, got {q0.get('total')}")
        else:
            bug(f"[{p.name}] No reconstruction_question received on phase entry",
                "Expected broadcast of first question immediately")

    # CHECK: no vote_prompt (reconstruction mode should not show voting)
    for p in players:
        if p.has_received("vote_prompt"):
            bug(f"[{p.name}] vote_prompt received in reconstruction mode",
                "Reconstruction games must not trigger voting")
        else:
            ok(f"[{p.name}] No vote_prompt — correct for reconstruction mode")

    # ──────────────────────────────────────────────────────────────
    # 8. Answer all 6 reconstruction questions
    # ──────────────────────────────────────────────────────────────
    log("\n[8] Answering reconstruction questions...")

    # Answers from each player (rotating who answers)
    answers = [
        "为了独占信号数据的发现权，阻止信号向外传输",     # rq_01
        "22:00，林晓薇完成同步后梅博士亲自取走了硬盘",    # rq_02
        "梅博士指示林晓薇用自己的账号执行删除命令",        # rq_03
        "23:05，维修室后门闸机刷卡记录显示她出站",         # rq_04
        "22:30左右，张明例行巡查时发现了被短路的保险丝",   # rq_05
        "选择了没有外部摄像头覆盖的路线从维修室后门离开",  # rq_06
    ]
    answerers = [lin, wang, zhang, lin, wang, zhang]

    for i, (answer_text, answerer) in enumerate(zip(answers, answerers)):
        log(f"  Q{i+1}: {answerer.name} submitting answer...")

        # Wait for the question to arrive before submitting
        deadline = time.time() + 15
        while time.time() < deadline:
            if any(q.get("index") == i for q in answerer.recon_questions):
                break
            await asyncio.sleep(0.3)
        else:
            bug(f"Q{i+1} never arrived for {answerer.name}",
                f"recon_questions={answerer.recon_questions}")
            continue

        await answerer.send({"type": "reconstruction_answer", "answer": answer_text})
        await asyncio.sleep(0.3)

        # Wait for result
        deadline = time.time() + 30
        result_received = False
        while time.time() < deadline:
            # Check if any player received a result for this question
            for p in players:
                if any(r.get("index") == i for r in p.recon_results):
                    result_received = True
                    break
            if result_received:
                break
            await asyncio.sleep(0.5)

        if result_received:
            # Find the result
            for p in players:
                res = next((r for r in p.recon_results if r.get("index") == i), None)
                if res:
                    score = res.get("score", 0)
                    result = res.get("result", "?")
                    total = res.get("total_score", "?")
                    log(f"    Q{i+1} result: {result} (+{score}pt) running total={total}")
                    break
        else:
            bug(f"Q{i+1} result never received",
                f"No reconstruction_result for index={i} after 30s")

        # Wait for next question (unless last)
        if i < 5:
            deadline = time.time() + 10
            while time.time() < deadline:
                next_q_arrived = any(
                    any(q.get("index") == i + 1 for q in p.recon_questions)
                    for p in players
                )
                if next_q_arrived:
                    break
                await asyncio.sleep(0.3)
            else:
                bug(f"Q{i+2} never arrived after Q{i+1} was answered",
                    "reconstruction_question for next index not broadcast")

    # CHECK: reconstruction_complete broadcast
    await asyncio.sleep(2)
    for p in players:
        complete = p.get_all("reconstruction_complete")
        if complete:
            c = complete[0]
            ok(f"[{p.name}] reconstruction_complete: score={c.get('total_score')}/{c.get('max_score')} ({c.get('pct')}%)")
        else:
            bug(f"[{p.name}] No reconstruction_complete message",
                "Expected after all 6 answers")

    # CHECK: score consistency across players
    scores = []
    for p in players:
        c = p.get_all("reconstruction_complete")
        if c:
            scores.append(c[0].get("total_score"))
    if len(set(scores)) == 1:
        ok(f"Score consistent across all players: {scores[0]}/12")
    elif scores:
        bug("Score inconsistency across players", f"Scores differ: {scores}")

    # ──────────────────────────────────────────────────────────────
    # 9. Auto-advance to reveal
    # ──────────────────────────────────────────────────────────────
    log("\n[9] Waiting for auto-advance to reveal (≤10s after completion)...")
    reached_reveal = await wait_all_phase(players, "reveal", timeout=15)
    if reached_reveal:
        ok("All players reached reveal phase")
    else:
        bug("Auto-advance to reveal failed",
            f"lin={lin.current_phase} wang={wang.current_phase} zhang={zhang.current_phase}")

    # CHECK: reveal DM narration received (should contain full_story, not "凶手")
    await asyncio.sleep(5)
    dm_at_reveal = [
        m for m in lin.all_msgs
        if m.get("type") in ("dm_response", "dm_stream_end") and m.get("phase") == "reveal"
    ]
    # Also check for dm_stream_end after phase change to reveal
    reveal_idx = next(
        (i for i, m in enumerate(lin.all_msgs) if m.get("type") == "phase_change" and m.get("new_phase") == "reveal"),
        len(lin.all_msgs),
    )
    post_reveal_dm = [
        m for m in lin.all_msgs[reveal_idx:]
        if m.get("type") in ("dm_response", "dm_stream_end")
    ]

    if post_reveal_dm:
        text = post_reveal_dm[0].get("text", "")[:100]
        ok(f"Reveal narration received: {text!r}…")
        if "凶手" in text:
            bug("Reveal text mentions 凶手 in reconstruction mode",
                "Should show full_story, not culprit info")
        else:
            ok("Reveal text does not mention 凶手 — correct for reconstruction mode")
    else:
        bug("No DM narration in reveal phase",
            "Expected full_story narration after reconstruction complete")

    # CHECK: culprit not in any broadcast messages
    all_texts = " ".join(
        m.get("text", "") + m.get("response", "")
        for m in lin.all_msgs
    )
    # signal_lost_001 culprit is empty string — check no char reveals a "killer"
    if "culprit" in all_texts.lower() or "凶手是" in all_texts:
        bug("culprit info leaked in reconstruction game",
            "Culprit/killer text found in broadcast messages")
    else:
        ok("No culprit info leaked — correct for reconstruction mode")

    # ──────────────────────────────────────────────────────────────
    # 10. Phase history check
    # ──────────────────────────────────────────────────────────────
    log("\n[10] Phase history checks...")
    expected_phases = ["reading", "investigation_1", "discussion", "reconstruction", "reveal"]
    for p in players:
        missing = [ph for ph in expected_phases if ph not in p.phase_history]
        if missing:
            bug(f"[{p.name}] Missing phase_change events", f"Missing: {missing}")
        else:
            ok(f"[{p.name}] All phase transitions received: {p.phase_history}")

    # CHECK: no voting phase in reconstruction mode
    for p in players:
        if "voting" in p.phase_history:
            bug(f"[{p.name}] voting phase appeared in reconstruction game",
                "Reconstruction mode should never enter voting")

    # ──────────────────────────────────────────────────────────────
    # Summary
    # ──────────────────────────────────────────────────────────────
    await asyncio.gather(*(p.close() for p in players))
    log("\n" + "=" * 60)
    log("SIMULATION COMPLETE")
    log("=" * 60)
    if BUGS:
        log(f"\n🐛 {len(BUGS)} BUGS FOUND:")
        for i, b in enumerate(BUGS, 1):
            log(f"  [{i}] {b['title']}")
            if b["detail"]:
                log(f"       {b['detail']}")
    else:
        log("\n✅ No bugs found!")
    log("")


if __name__ == "__main__":
    asyncio.run(run())
