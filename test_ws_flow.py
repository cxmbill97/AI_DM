"""
WebSocket-based full game flow test for murder mystery room FZV1ND.
Uses 3 concurrent WebSocket connections to simulate 3 players.
"""
import asyncio
import json
import time
import websockets

ROOM_ID = "FZV1ND"
BACKEND = "http://localhost:8000"
PLAYERS = ["林晓薇", "王建国", "张明"]

bugs = []
all_events = {p: [] for p in PLAYERS}

def log_bug(severity, location, description):
    bugs.append({"severity": severity, "location": location, "description": description})
    print(f"\n[BUG][{severity}] {location}:\n  {description}")

def log_info(msg):
    print(f"[INFO] {msg}")

async def player_session(player_name, duration=30):
    """Connect as a player and collect all events for duration seconds."""
    uri = f"ws://localhost:8000/ws/{ROOM_ID}?player_name={player_name}"
    events = []
    try:
        async with websockets.connect(uri) as ws:
            log_info(f"{player_name}: Connected to WebSocket")
            start = time.time()
            while time.time() - start < duration:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    msg = json.loads(raw)
                    events.append(msg)
                    msg_type = msg.get("type", "unknown")
                    # Print key events
                    if msg_type in ("room_snapshot", "phase_change", "character_assigned",
                                    "character_secret", "reconstruction_question",
                                    "reconstruction_result", "reconstruction_complete",
                                    "phase_change", "vote_prompt", "vote_result",
                                    "system", "error"):
                        preview = str(msg)[:300]
                        log_info(f"  [{player_name}][{msg_type}] {preview}")
                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed as e:
                    log_info(f"  [{player_name}] Connection closed: {e}")
                    break
    except Exception as e:
        log_bug("HIGH", f"WebSocket ({player_name})", f"Connection error: {e}")
    return events

async def player_session_with_answers(player_name, duration=120):
    """Connect as player and answer reconstruction questions."""
    uri = f"ws://localhost:8000/ws/{ROOM_ID}?player_name={player_name}"
    events = []
    reconstruction_questions = []
    try:
        async with websockets.connect(uri) as ws:
            log_info(f"{player_name}: Connected")
            start = time.time()
            while time.time() - start < duration:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    msg = json.loads(raw)
                    events.append(msg)
                    msg_type = msg.get("type", "unknown")

                    if msg_type == "reconstruction_question":
                        q = msg.get("question", "")
                        q_id = msg.get("question_id", "")
                        idx = msg.get("index", 0)
                        total = msg.get("total", 0)
                        reconstruction_questions.append(msg)
                        log_info(f"  [{player_name}] RECONSTRUCTION Q{idx+1}/{total}: {q[:100]}")

                        # Submit answer after short delay (only player 1 submits)
                        if player_name == "林晓薇":
                            await asyncio.sleep(0.5)
                            answer_payload = json.dumps({"type": "reconstruction_answer", "answer": "测试答案"})
                            await ws.send(answer_payload)
                            log_info(f"  [{player_name}] Submitted answer for question {idx+1}")

                    elif msg_type == "reconstruction_result":
                        log_info(f"  [{player_name}] RESULT: {msg}")

                    elif msg_type == "reconstruction_complete":
                        log_info(f"  [{player_name}] COMPLETE: {msg}")

                    elif msg_type in ("phase_change", "room_snapshot", "character_assigned",
                                     "character_secret", "system", "error"):
                        preview = str(msg)[:300]
                        log_info(f"  [{player_name}][{msg_type}] {preview}")

                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed as e:
                    log_info(f"  [{player_name}] Connection closed: {e}")
                    break
    except Exception as e:
        log_bug("HIGH", f"WebSocket ({player_name})", f"Connection error: {e}")

    return events, reconstruction_questions

async def run_full_game_test():
    log_info("=== FULL GAME FLOW TEST ===")
    log_info("Connecting all 3 players simultaneously...")

    # First, check current room state
    import urllib.request
    with urllib.request.urlopen(f"{BACKEND}/api/rooms/{ROOM_ID}") as r:
        room_state = json.loads(r.read())
    log_info(f"Room state before test: phase={room_state['phase']}, players={[p['name'] for p in room_state['players']]}")

    # Run all 3 players concurrently
    results = await asyncio.gather(
        player_session_with_answers("林晓薇", duration=90),
        player_session_with_answers("王建国", duration=90),
        player_session_with_answers("张明", duration=90),
    )

    events_by_player = {
        "林晓薇": results[0][0],
        "王建国": results[1][0],
        "张明": results[2][0],
    }
    questions_by_player = {
        "林晓薇": results[0][1],
        "王建国": results[1][1],
        "张明": results[2][1],
    }

    log_info("\n=== EVENT ANALYSIS ===")

    # Analyze events for each player
    for player, events in events_by_player.items():
        log_info(f"\n--- Player: {player} ---")
        log_info(f"Total events received: {len(events)}")

        types_seen = [e.get("type") for e in events]
        type_counts = {}
        for t in types_seen:
            type_counts[t] = type_counts.get(t, 0) + 1
        log_info(f"Event types: {type_counts}")

        # Check for room_snapshot
        snapshots = [e for e in events if e.get("type") == "room_snapshot"]
        if not snapshots:
            log_bug("HIGH", f"WebSocket ({player})",
                    "Player never received room_snapshot - cannot get initial game state")
        else:
            snap = snapshots[0]
            log_info(f"  room_snapshot received: phase={snap.get('current_phase')}, chars={len(snap.get('characters', []))}")

            # Check for expected fields
            if not snap.get("title"):
                log_bug("MEDIUM", f"room_snapshot ({player})", "Missing 'title' field")
            if not snap.get("characters"):
                log_bug("HIGH", f"room_snapshot ({player})", "Missing 'characters' field in MM snapshot")
            if snap.get("game_type") != "murder_mystery":
                log_bug("HIGH", f"room_snapshot ({player})", f"Wrong game_type: {snap.get('game_type')}")

        # Check for character_assigned
        char_assigns = [e for e in events if e.get("type") == "character_assigned"]
        if not char_assigns and any(e.get("type") == "phase_change" for e in events):
            log_bug("HIGH", f"WebSocket ({player})",
                    "No character_assigned event received, but phase changes occurred")

        # Check for character_secret
        char_secrets = [e for e in events if e.get("type") == "character_secret"]
        if not char_secrets:
            log_bug("MEDIUM", f"WebSocket ({player})",
                    "No character_secret event received - player won't know their private info")

        # Check phase transitions
        phase_changes = [e for e in events if e.get("type") == "phase_change"]
        if phase_changes:
            phases_seen = [e.get("new_phase") for e in phase_changes]
            log_info(f"  Phase transitions: {phases_seen}")

            # Check reconstruction
            if "reconstruction" in phases_seen:
                log_info(f"  => Reconstruction phase appeared!")
            else:
                log_info(f"  => Reconstruction phase NOT seen yet (may need more time)")

        # Check opening narration received
        opening_events = [e for e in events if e.get("type") in ("system", "dm_response") and
                          e.get("type") == "system"]
        if opening_events:
            log_info(f"  System messages received: {len(opening_events)}")
            first_sys = opening_events[0]
            log_info(f"  First system msg: {first_sys.get('text', '')[:100]}")

    # Cross-player analysis
    log_info("\n=== CROSS-PLAYER ANALYSIS ===")

    # Check all players saw same phase transitions
    for player in PLAYERS:
        phases = [e.get("new_phase") for e in events_by_player[player] if e.get("type") == "phase_change"]
        log_info(f"  {player} phases: {phases}")

    # Check if any player received events the others didn't
    p1_types = set(e.get("type") for e in events_by_player["林晓薇"])
    for player in ["王建国", "张明"]:
        other_types = set(e.get("type") for e in events_by_player[player])
        p1_only = p1_types - other_types
        other_only = other_types - p1_types
        if p1_only:
            log_bug("MEDIUM", f"Event consistency",
                    f"Player 林晓薇 received event types {p1_only} that {player} did not")
        if other_only:
            log_bug("MEDIUM", f"Event consistency",
                    f"Player {player} received event types {other_only} that 林晓薇 did not")

    return events_by_player

async def run_static_analysis():
    """Run static code analysis for additional bugs."""
    log_info("\n=== STATIC CODE ANALYSIS ===")

    # BUG: PhaseBar PHASE_ORDER missing 'reconstruction'
    PHASE_ORDER = ['opening', 'reading', 'investigation_1', 'discussion', 'voting', 'reveal']
    log_bug("HIGH", "frontend/src/components/PhaseBar.tsx:12-19",
            "PHASE_ORDER = ['opening','reading','investigation_1','discussion','voting','reveal'] "
            "does NOT include 'reconstruction'. When phase='reconstruction', indexOf returns -1, "
            "so all phase steps render as 'pending'. The active step indicator is completely broken "
            "during reconstruction. Players see no progress.")

    # BUG: i18n missing reconstruction phase label
    log_bug("MEDIUM", "frontend/src/i18n/zh.json + en.json",
            "No translation key for 'phase.reconstruction'. Even if PHASE_ORDER is fixed, "
            "t('phase.reconstruction') will fall back to the raw key string.")

    # BUG: Double countdown timer
    log_bug("HIGH", "useRoom.ts:249-255 (setInterval) + PhaseBar.tsx:33-56 (useEffect + setInterval)",
            "DOUBLE COUNTDOWN: useRoom.ts runs its own countdown (mmTimeRemaining -= 1 per second). "
            "PhaseBar.tsx also has an interval-based countdown from timeRemaining prop. "
            "PhaseBar's sync useEffect (lines 33-36) resets localTime every time timeRemaining changes. "
            "Since useRoom's interval changes mmTimeRemaining every second, PhaseBar's countdown effect "
            "re-fires every second, restarting the interval. The PhaseBar interval never runs more than "
            "1 second before being cleared and restarted. Net effect: PhaseBar only ever counts down "
            "the useRoom counter, but creates a new interval object every second (memory/CPU waste).")

    # BUG: WaitingBanner threshold wrong for 3-player games
    log_bug("MEDIUM", "frontend/src/pages/RoomPage.tsx:408-414",
            "WaitingBanner disappears when connectedCount >= 2. But murder mystery requires 3 players. "
            "With 2/3 players connected, banner disappears and players may think game is ready.")

    # BUG: room_snapshot surface field empty for MM
    log_bug("MEDIUM", "frontend/src/hooks/useRoom.ts:317",
            "For murder_mystery room_snapshot, puzzle.surface is hardcoded as '' (empty string). "
            "The opening narration text is never exposed in the puzzle info sidebar for MM games.")

    # BUG: ReconstructionPanel skip button exposed
    log_bug("MEDIUM", "frontend/src/components/PhaseBar.tsx:60",
            "canSkip = phase !== 'reveal' && phase !== 'voting'. "
            "During 'reconstruction' phase, canSkip=true and skip button shows. "
            "Clicking skip sends {type:'skip_phase'} to backend during reconstruction. "
            "Need to verify backend handles this correctly (or add 'reconstruction' to exclusion list).")

    # BUG: Reconstruction submitted state lost on refresh
    log_bug("MEDIUM", "frontend/src/components/ReconstructionPanel.tsx:24",
            "submitted = useState<Set<string>>(new Set()) - local state only. "
            "Page refresh resets it, allowing re-submission of answered questions. "
            "Backend must deduplicate by question_id.")

    # BUG: reveal phase - full_story check
    log_info("Checking reveal phase behavior...")

    # BUG: ReconstructionPanel visible in reveal phase if complete=true
    log_bug("LOW", "frontend/src/components/ReconstructionPanel.tsx:26",
            "Condition: if (phase !== 'reconstruction' && !complete) return null. "
            "When complete is set AND phase becomes 'reveal', panel renders in reveal view. "
            "Right sidebar in reveal phase shows both ReconstructionPanel summary and "
            "the 'Back to Lobby' button stacked. Could be visually cluttered.")

async def main():
    # Run static analysis first
    await run_static_analysis()

    # Run live WebSocket test
    log_info("\n" + "="*60)
    log_info("LIVE WEBSOCKET TEST")
    log_info("="*60)
    await run_full_game_test()

    # Final report
    log_info("\n" + "="*70)
    log_info("FINAL BUG REPORT")
    log_info("="*70)
    for i, bug in enumerate(bugs, 1):
        log_info(f"\nBUG #{i} [{bug['severity']}]")
        log_info(f"  Location: {bug['location']}")
        log_info(f"  Description: {bug['description']}")

    high = sum(1 for b in bugs if b["severity"] == "HIGH")
    med = sum(1 for b in bugs if b["severity"] == "MEDIUM")
    low = sum(1 for b in bugs if b["severity"] == "LOW")
    log_info(f"\nTotals: {len(bugs)} bugs ({high} HIGH, {med} MEDIUM, {low} LOW)")

asyncio.run(main())
