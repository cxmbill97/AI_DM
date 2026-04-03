"""
Two-player murder mystery simulation.
Each player has a dedicated reader task feeding into an asyncio.Queue.
Run: uv run python tests/sim_two_players.py
"""

import asyncio
import json
import time
import urllib.request
from collections import defaultdict

import websockets

HTTP = "http://localhost:8000"
BASE = "ws://localhost:8000"

BUGS: list[dict] = []


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def bug(title: str, detail: str):
    BUGS.append({"title": title, "detail": detail})
    log(f"  🐛 BUG: {title} — {detail}")


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


def http_get(path: str) -> dict:
    with urllib.request.urlopen(f"{HTTP}{path}") as r:
        return json.loads(r.read())


class Player:
    def __init__(self, name: str, room_id: str):
        self.name = name
        self.room_id = room_id
        self.ws = None
        self._q: asyncio.Queue = asyncio.Queue()
        self._reader_task = None
        self.all_msgs: list[dict] = []
        self.phase_history: list[str] = []
        self.char_id = None
        self.char_name = None
        self.type_counts: dict[str, int] = defaultdict(int)

    async def connect(self):
        url = f"{BASE}/ws/{self.room_id}?player_name={self.name}"
        self.ws = await websockets.connect(url)
        self._reader_task = asyncio.create_task(self._read_loop())
        log(f"  [{self.name}] connected")

    async def _read_loop(self):
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                self.all_msgs.append(msg)
                t = msg.get("type", "?")
                self.type_counts[t] += 1
                if t == "phase_change":
                    self.phase_history.append(msg.get("new_phase"))
                elif t == "character_secret":
                    self.char_id = msg.get("char_id")
                    self.char_name = msg.get("char_name")
                await self._q.put(msg)
        except Exception:
            pass

    async def recv(self, timeout=20) -> dict | None:
        try:
            return await asyncio.wait_for(self._q.get(), timeout=timeout)
        except TimeoutError:
            return None

    async def drain(self, seconds=2.0) -> list[dict]:
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

    async def wait_for(self, msg_type: str, timeout=40) -> dict | None:
        deadline = time.time() + timeout
        # Check already-received messages first
        for m in self.all_msgs:
            if m.get("type") == msg_type:
                return m
        while time.time() < deadline:
            msg = await self.recv(timeout=min(3, deadline - time.time()))
            if msg is None:
                continue
            if msg.get("type") == msg_type:
                return msg
        return None

    def has_received(self, msg_type: str) -> bool:
        return any(m.get("type") == msg_type for m in self.all_msgs)

    def get_all(self, msg_type: str) -> list[dict]:
        return [m for m in self.all_msgs if m.get("type") == msg_type]

    @property
    def current_phase(self) -> str | None:
        return self.phase_history[-1] if self.phase_history else None

    async def send(self, msg: dict):
        await self.ws.send(json.dumps(msg))

    async def close(self):
        if self._reader_task:
            self._reader_task.cancel()
        if self.ws:
            await self.ws.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def wait_both_phase(alice: Player, bob: Player, phase: str, timeout=60) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        await asyncio.sleep(0.5)
        if alice.current_phase == phase and bob.current_phase == phase:
            return True
    return False


async def skip_to_phase(alice: Player, bob: Player, target: str, max_skips=6):
    for _ in range(max_skips):
        if alice.current_phase == target:
            return True
        await alice.send({"type": "skip_phase"})
        await bob.send({"type": "skip_phase"})
        reached = await wait_both_phase(alice, bob, target, timeout=10)
        if reached:
            return True
    return alice.current_phase == target


# ---------------------------------------------------------------------------
# Main simulation
# ---------------------------------------------------------------------------


async def run():
    log("=" * 60)
    log("TWO-PLAYER MURDER MYSTERY SIMULATION")
    log("=" * 60)

    # 1. Create room
    log("\n[1] Creating room (en_thornfield_001, English)...")
    body = http_post("/api/rooms", {"game_type": "murder_mystery", "script_id": "en_thornfield_001", "language": "en"})
    room_id = body["room_id"]
    log(f"  Room ID: {room_id}")

    alice = Player("Alice", room_id)
    bob = Player("Bob", room_id)
    await alice.connect()
    await asyncio.sleep(0.3)
    await bob.connect()

    # 2. Initial snapshots
    log("\n[2] Checking initial snapshots and character assignment...")
    alice_snap = await alice.wait_for("room_snapshot", timeout=8)
    bob_snap = await bob.wait_for("room_snapshot", timeout=8)

    for name, snap in [("Alice", alice_snap), ("Bob", bob_snap)]:
        if not snap:
            bug(f"{name} missing room_snapshot", "room_snapshot not received on join")
        else:
            log(f"  {name}: game_type={snap.get('game_type')} phase={snap.get('current_phase')}")

    alice_secret = await alice.wait_for("character_secret", timeout=8)
    bob_secret = await bob.wait_for("character_secret", timeout=8)

    for name, secret in [("Alice", alice_secret), ("Bob", bob_secret)]:
        if not secret:
            bug(f"{name} missing character_secret", "character_secret not received on join")
        else:
            log(f"  {name} char: {secret.get('char_name')} (id={secret.get('char_id')}) secret_len={len(secret.get('secret_bio', ''))}")

    if alice_secret and bob_secret:
        if alice_secret.get("char_id") == bob_secret.get("char_id"):
            bug("Duplicate character assignment", f"Both assigned char_id={alice_secret.get('char_id')}")
        else:
            log("  Characters distinct — OK")

    # CHECK: character_assigned broadcast (both should see each other's assignment)
    alice_char_assigns = alice.get_all("character_assigned")
    bob_char_assigns = bob.get_all("character_assigned")
    if len(alice_char_assigns) < 1:
        bug("Alice missing character_assigned broadcast", "Should see at least own assignment broadcast")
    if len(bob_char_assigns) < 1:
        bug("Bob missing character_assigned broadcast", "Should see at least own assignment broadcast")

    # 3. Wait for auto-advance to investigation_1
    log("\n[3] Waiting for auto-advance to investigation_1 (opening→reading→investigation)...")
    t0 = time.time()
    reached = await wait_both_phase(alice, bob, "investigation_1", timeout=60)
    if not reached:
        bug("Auto-advance to investigation_1 failed", f"Phase stuck at alice={alice.current_phase} bob={bob.current_phase}")
        log("  Attempting manual skip...")
        await skip_to_phase(alice, bob, "investigation_1")
    else:
        log(f"  Reached investigation_1 in {time.time() - t0:.0f}s — OK")

    # CHECK: both players see same phase_change events
    if alice.phase_history != bob.phase_history:
        bug("Phase history mismatch", f"Alice={alice.phase_history} Bob={bob.phase_history}")
    else:
        log(f"  Phase history consistent: {alice.phase_history}")

    # CHECK: opening DM narration received
    opening_dm = alice.get_all("dm_response")
    if not opening_dm:
        bug("No opening DM narration", "Expected dm_response during opening phase")
    else:
        log(f"  Opening narration received ({len(opening_dm)} DM messages so far) — OK")

    # 4. Alice asks a question (DM broadcast check)
    log("\n[4] Alice asks a question — checking broadcast to Bob...")
    pre_alice_dm_count = len(alice.get_all("dm_response")) + len(alice.get_all("dm_stream_end"))
    pre_bob_dm_count = len(bob.get_all("dm_response")) + len(bob.get_all("dm_stream_end"))

    t_ask = time.time()
    await alice.send({"type": "chat", "text": "Who was the last person to see Lord Thornfield?"})

    # Wait for DM response on both sides
    alice_got_dm, bob_got_dm = False, False
    deadline = time.time() + 35
    while time.time() < deadline and not (alice_got_dm and bob_got_dm):
        await asyncio.sleep(0.3)
        alice_new = len(alice.get_all("dm_response")) + len(alice.get_all("dm_stream_end"))
        bob_new = len(bob.get_all("dm_response")) + len(bob.get_all("dm_stream_end"))
        alice_got_dm = alice_new > pre_alice_dm_count
        bob_got_dm = bob_new > pre_bob_dm_count

    dm_latency = time.time() - t_ask
    log(f"  DM response latency: {dm_latency:.1f}s")
    if dm_latency > 20:
        bug("High DM latency", f"{dm_latency:.1f}s (threshold 20s) — pipeline may be slow")

    if not alice_got_dm:
        bug("Alice did not receive DM response", "Asking player did not get DM reply")
    else:
        log("  Alice received DM response — OK")

    if not bob_got_dm:
        bug("Bob did not receive DM response (broadcast)", "Non-asking player did not see DM reply")
    else:
        log("  Bob received DM response (broadcast) — OK")

    # CHECK: player_name present in DM response
    dm_msgs = alice.get_all("dm_response") + alice.get_all("dm_stream_end")
    dm_with_text = [m for m in dm_msgs if m.get("text") or m.get("response")]
    if dm_with_text and not dm_with_text[-1].get("player_name"):
        bug("DM response missing player_name", "UI cannot render 'reply to Alice' without player_name field")
    elif dm_with_text:
        log(f"  DM player_name={dm_with_text[-1].get('player_name')!r} — OK")

    # CHECK: DM response has non-empty text
    if dm_with_text:
        text = dm_with_text[-1].get("text") or dm_with_text[-1].get("response") or ""
        if not text.strip():
            bug("DM response has empty text", "dm_response arrived with blank text field")
        else:
            log(f"  DM text preview: {text[:80]!r}")

    # 5. Bob asks a question (reverse broadcast check)
    log("\n[5] Bob asks — Alice should also see the DM reply...")
    pre_alice2 = len(alice.get_all("dm_response")) + len(alice.get_all("dm_stream_end"))
    pre_bob2 = len(bob.get_all("dm_response")) + len(bob.get_all("dm_stream_end"))

    await bob.send({"type": "chat", "text": "Was a weapon found near the body?"})

    alice_saw_bob_dm, bob_got_own_dm = False, False
    deadline2 = time.time() + 35
    while time.time() < deadline2 and not (alice_saw_bob_dm and bob_got_own_dm):
        await asyncio.sleep(0.3)
        alice_saw_bob_dm = (len(alice.get_all("dm_response")) + len(alice.get_all("dm_stream_end"))) > pre_alice2
        bob_got_own_dm = (len(bob.get_all("dm_response")) + len(bob.get_all("dm_stream_end"))) > pre_bob2

    if not bob_got_own_dm:
        bug("Bob did not receive reply to own question", "Bob's dm_response not delivered")
    else:
        log("  Bob got reply to own question — OK")
    if not alice_saw_bob_dm:
        bug("Alice did not see Bob's DM reply", "DM broadcast broke for observer")
    else:
        log("  Alice saw Bob's DM reply (broadcast) — OK")

    # 6. Phase_blocked test: vote during investigation
    log("\n[6] phase_blocked: vote during investigation_1...")
    pre_errors = len(alice.get_all("phase_blocked"))
    await alice.send({"type": "vote", "target": "char_001"})
    await asyncio.sleep(3)
    if len(alice.get_all("phase_blocked")) <= pre_errors:
        bug("Vote not blocked in investigation_1", "Expected phase_blocked, got none")
    else:
        log("  Vote correctly blocked in investigation_1 — OK")

    # 7. Plain chat during investigation (should NOT be blocked)
    log("\n[7] Plain chat during investigation (should broadcast, no DM reply)...")
    pre_player_msgs_bob = len(bob.get_all("player_message"))
    await alice.send({"type": "chat", "text": "I think the butler did it."})
    await asyncio.sleep(2)
    if len(bob.get_all("player_message")) <= pre_player_msgs_bob:
        bug("Plain chat not broadcast during investigation", "Bob did not receive Alice's plain chat message")
    else:
        log("  Plain chat broadcast to Bob — OK")
    # Also check Alice didn't get a phase_blocked for plain chat
    phase_blocked_after = len(alice.get_all("phase_blocked"))
    if phase_blocked_after > pre_errors + 1:  # +1 from the vote above
        bug("Plain chat triggered phase_blocked", "chat intent should never be blocked by state machine")

    # 8. Skip to voting
    log("\n[8] Skipping to voting phase...")
    for _ in range(6):
        if alice.current_phase == "voting":
            break
        await alice.send({"type": "skip_phase"})
        await bob.send({"type": "skip_phase"})
        await asyncio.sleep(3)
        await alice.drain(0.5)
        await bob.drain(0.5)

    log(f"  Alice phase: {alice.current_phase}  Bob phase: {bob.current_phase}")
    if alice.current_phase != "voting":
        bug("Could not reach voting phase via skip", f"Stuck at {alice.current_phase}")

    # 9. Voting
    log("\n[9] Both players cast votes...")
    # Get char ids from snapshot
    char_ids = []
    for m in alice.all_msgs:
        if m.get("type") == "room_snapshot" and m.get("characters"):
            char_ids = [c["id"] for c in m["characters"]]
            break
    if not char_ids:
        bug("No characters in snapshot", "Cannot vote without char_ids")
        char_ids = ["char_001"]

    log(f"  Available chars: {char_ids}")
    target = char_ids[0]

    pre_cast_a = len(alice.get_all("vote_cast"))
    pre_cast_b = len(bob.get_all("vote_cast"))

    await alice.send({"type": "vote", "target": target})
    await asyncio.sleep(1)
    await bob.send({"type": "vote", "target": target})
    await asyncio.sleep(2)

    # CHECK: vote_cast broadcast to both
    if len(alice.get_all("vote_cast")) <= pre_cast_a:
        bug("Alice missing vote_cast", "vote_cast not delivered after voting")
    else:
        log(f"  Alice got {len(alice.get_all('vote_cast')) - pre_cast_a} vote_cast — OK")
    if len(bob.get_all("vote_cast")) <= pre_cast_b:
        bug("Bob missing vote_cast", "vote_cast not delivered after voting")
    else:
        log(f"  Bob got {len(bob.get_all('vote_cast')) - pre_cast_b} vote_cast — OK")

    # CHECK: vote_result after all votes
    deadline3 = time.time() + 15
    while time.time() < deadline3:
        if alice.has_received("vote_result") and bob.has_received("vote_result"):
            break
        await asyncio.sleep(0.5)

    if not alice.has_received("vote_result"):
        bug("Alice missing vote_result", "vote_result not received after all players voted")
    else:
        vr = alice.get_all("vote_result")[0]
        log(f"  vote_result: winner={vr.get('winner')} is_correct={vr.get('is_correct')} tally={vr.get('tally')} — OK")
        if not vr.get("tally"):
            bug("vote_result has empty tally", "tally should map char_id → vote count")
    if not bob.has_received("vote_result"):
        bug("Bob missing vote_result", "vote_result not broadcast to Bob")

    # 10. Reveal phase
    log("\n[10] Waiting for reveal phase + truth narration...")
    reached_reveal = await wait_both_phase(alice, bob, "reveal", timeout=15)
    if not reached_reveal:
        bug("Reveal phase not reached after voting", f"Alice={alice.current_phase} Bob={bob.current_phase}")
    else:
        log("  Reveal phase reached — OK")

    # Wait for DM truth narration in reveal
    pre_dm_reveal = len(alice.get_all("dm_response")) + len(alice.get_all("dm_stream_end"))
    deadline4 = time.time() + 30
    while time.time() < deadline4:
        total = len(alice.get_all("dm_response")) + len(alice.get_all("dm_stream_end"))
        if total > pre_dm_reveal:
            break
        await asyncio.sleep(0.5)

    reveal_narrations = [m for m in alice.all_msgs if m.get("type") in ("dm_response", "dm_stream_end") and alice.all_msgs.index(m) >= pre_dm_reveal]
    if not reveal_narrations:
        bug("No truth narration in reveal phase", "Expected DM to narrate the truth after voting")
    else:
        text = reveal_narrations[0].get("text", "")[:100]
        log(f"  Reveal narration preview: {text!r} — OK")

    # Bob should also get it
    if not bob.has_received("dm_response") and not bob.has_received("dm_stream_end"):
        bug("Bob missing reveal narration", "Truth narration not broadcast to Bob")

    # 11. Double-vote check (Alice tries to vote again)
    log("\n[11] Double-vote check (Alice votes again in reveal)...")
    await alice.send({"type": "vote", "target": char_ids[0]})
    await asyncio.sleep(2)
    extra_blocks = [m for m in alice.all_msgs[-5:] if m.get("type") in ("phase_blocked", "error", "system")]
    if not extra_blocks:
        log("  No error for double-vote in reveal — may be silently ignored (OK if phase is reveal)")
    else:
        log(f"  Double-vote handled: {extra_blocks[0].get('type')} — OK")

    # Final
    await alice.drain(1)
    await bob.drain(1)
    await alice.close()
    await bob.close()

    log("\n" + "=" * 60)
    log("SIMULATION COMPLETE")
    log(f"  Alice msg types: {dict(alice.type_counts)}")
    log(f"  Bob msg types:   {dict(bob.type_counts)}")
    log(f"  Phase history:   {alice.phase_history}")
    log("=" * 60)

    if BUGS:
        log(f"\n🐛  {len(BUGS)} BUG(S) FOUND:")
        for i, b in enumerate(BUGS, 1):
            log(f"  {i}. [{b['title']}]")
            log(f"     {b['detail']}")
    else:
        log("\n✅  No bugs found — all checks passed")

    return BUGS


if __name__ == "__main__":
    asyncio.run(run())
