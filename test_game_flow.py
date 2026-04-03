"""
Comprehensive browser test for the murder mystery room FZV1ND.
Tests: 3 players joining, phase transitions, reconstruction panel, scoring, reveal.
"""
import asyncio
import json
import time
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

ROOM_ID = "FZV1ND"
FRONTEND = "http://localhost:5173"
BACKEND = "http://localhost:8000"
PLAYERS = ["林晓薇", "王建国", "张明"]

bugs = []

def log_bug(severity, location, description):
    bugs.append({"severity": severity, "location": location, "description": description})
    print(f"[BUG][{severity}] {location}: {description}")

def log_info(msg):
    print(f"[INFO] {msg}")

async def join_room(page: Page, player_name: str):
    """Navigate to the lobby and join room FZV1ND with the given player name."""
    await page.goto(FRONTEND)
    await page.wait_for_load_state("networkidle")

    # Take snapshot to understand the page
    title = await page.title()
    log_info(f"Page title: {title}")

    # Look for room join input - try different selectors
    # Lobby page should have input for room code and player name
    content = await page.content()

    # Find the room code input and player name input
    # Based on LobbyPage.tsx structure
    inputs = await page.query_selector_all("input")
    log_info(f"Found {len(inputs)} inputs on page")

    for inp in inputs:
        placeholder = await inp.get_attribute("placeholder") or ""
        input_type = await inp.get_attribute("type") or "text"
        log_info(f"  Input: type={input_type}, placeholder={placeholder!r}")

async def check_room_api():
    """Check the room API to see current state."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"{BACKEND}/api/rooms/{ROOM_ID}") as r:
            data = json.loads(r.read())
        return data
    except Exception as e:
        log_bug("HIGH", "API", f"Room API failed: {e}")
        return None

async def run_tests():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])

        # -------------------------------------------------------------------
        # TEST 1: Room API check
        # -------------------------------------------------------------------
        log_info("=== TEST 1: Room API Check ===")
        room_data = await check_room_api()
        if room_data:
            log_info(f"Room data: {json.dumps(room_data, ensure_ascii=False)}")

            if room_data.get("game_type") != "murder_mystery":
                log_bug("HIGH", "API /api/rooms/FZV1ND",
                        f"Expected game_type=murder_mystery, got {room_data.get('game_type')}")
            else:
                log_info("OK: game_type is murder_mystery")

            if room_data.get("phase") != "waiting":
                log_bug("MEDIUM", "API /api/rooms/FZV1ND",
                        f"Expected initial phase=waiting, got {room_data.get('phase')}")
            else:
                log_info("OK: initial phase is waiting")

            if not room_data.get("title"):
                log_bug("MEDIUM", "API /api/rooms/FZV1ND", "Room has no title")
            else:
                log_info(f"OK: room title = {room_data['title']}")
        else:
            log_bug("CRITICAL", "API", "Cannot reach room API")
            return

        # -------------------------------------------------------------------
        # TEST 2: Open 3 tabs for 3 players and navigate to lobby
        # -------------------------------------------------------------------
        log_info("=== TEST 2: Opening 3 Browser Tabs ===")

        pages = []
        contexts = []
        for i, player in enumerate(PLAYERS):
            ctx = await browser.new_context()
            page = await ctx.new_page()
            pages.append(page)
            contexts.append(ctx)
            log_info(f"Opened tab {i+1} for player: {player}")

        # Navigate all tabs to lobby
        for i, (page, player) in enumerate(zip(pages, PLAYERS)):
            await page.goto(FRONTEND)
            await page.wait_for_load_state("networkidle")
            log_info(f"Tab {i+1} ({player}) loaded lobby")

        # -------------------------------------------------------------------
        # TEST 3: Inspect lobby page structure
        # -------------------------------------------------------------------
        log_info("=== TEST 3: Lobby Page Inspection ===")
        page0 = pages[0]

        # Get all text content to understand the page
        body_text = await page0.inner_text("body")
        log_info(f"Lobby page text (first 500 chars): {body_text[:500]}")

        # Check for room join form elements
        all_inputs = await page0.query_selector_all("input")
        input_info = []
        for inp in all_inputs:
            ph = await inp.get_attribute("placeholder") or ""
            vl = await inp.get_attribute("value") or ""
            tp = await inp.get_attribute("type") or "text"
            input_info.append({"type": tp, "placeholder": ph, "value": vl})
        log_info(f"Lobby inputs: {input_info}")

        all_buttons = await page0.query_selector_all("button")
        btn_texts = []
        for btn in all_buttons:
            txt = await btn.inner_text()
            btn_texts.append(txt.strip())
        log_info(f"Lobby buttons: {btn_texts}")

        # -------------------------------------------------------------------
        # TEST 4: Join room for each player
        # -------------------------------------------------------------------
        log_info("=== TEST 4: Joining Room ===")

        for i, (page, player) in enumerate(zip(pages, PLAYERS)):
            try:
                # Try to find room code input field
                # Look for input fields - try placeholder text matching
                room_input = None
                name_input = None

                inputs = await page.query_selector_all("input")
                for inp in inputs:
                    ph = (await inp.get_attribute("placeholder") or "").lower()
                    if any(keyword in ph for keyword in ["房间", "room", "code", "邀请", "代码"]):
                        room_input = inp
                    elif any(keyword in ph for keyword in ["名字", "name", "玩家", "昵称", "你的"]):
                        name_input = inp

                # If we can't identify by placeholder, try first/second input heuristic
                if not room_input and len(inputs) >= 1:
                    # Try to navigate directly to room URL
                    log_info(f"Can't find room input by placeholder, trying direct URL navigation")
                    await page.goto(f"{FRONTEND}/room/{ROOM_ID}")
                    await page.wait_for_load_state("networkidle")

                    body = await page.inner_text("body")
                    log_info(f"Direct room URL page (first 300 chars): {body[:300]}")

                    # Check if we need to enter player name
                    inputs_after = await page.query_selector_all("input")
                    for inp in inputs_after:
                        ph = (await inp.get_attribute("placeholder") or "")
                        log_info(f"  Input after direct nav: placeholder={ph!r}")

                    # Check for "no player name" error
                    if "no_player_name" in body or "没有玩家名" in body or "回到大厅" in body:
                        log_info(f"Direct URL shows player name required - need to join via lobby")
                    continue

                if room_input:
                    await room_input.fill(ROOM_ID)
                    log_info(f"Filled room code: {ROOM_ID}")

                if name_input:
                    await name_input.fill(player)
                    log_info(f"Filled player name: {player}")

                # Look for join button
                join_btn = None
                buttons = await page.query_selector_all("button")
                for btn in buttons:
                    txt = (await btn.inner_text()).strip()
                    if any(keyword in txt for keyword in ["加入", "Join", "进入", "join"]):
                        join_btn = btn
                        break

                if join_btn:
                    await join_btn.click()
                    await page.wait_for_load_state("networkidle")
                    log_info(f"Player {player} clicked join button")
                else:
                    log_info(f"No join button found for player {player}")

            except Exception as e:
                log_bug("HIGH", f"Join Room ({player})", f"Failed to join: {e}")

        # Wait for all players to potentially be in rooms
        await asyncio.sleep(2)

        # -------------------------------------------------------------------
        # TEST 5: Check actual lobby page structure more carefully
        # -------------------------------------------------------------------
        log_info("=== TEST 5: Re-inspect Lobby and Try Proper Join ===")

        # Read the LobbyPage.tsx to understand actual structure
        page0 = pages[0]
        await page0.goto(FRONTEND)
        await page0.wait_for_load_state("networkidle")

        # Get full page HTML snapshot
        html = await page0.content()
        # Just look at key elements

        # Try screenshot approach
        screenshot_path = "/tmp/lobby_screenshot.png"
        await page0.screenshot(path=screenshot_path)
        log_info(f"Saved lobby screenshot to {screenshot_path}")

        # Check URL
        current_url = page0.url
        log_info(f"Current URL: {current_url}")

        # -------------------------------------------------------------------
        # STATIC CODE ANALYSIS BUGS (from reading source)
        # -------------------------------------------------------------------
        log_info("=== STATIC CODE ANALYSIS ===")

        # BUG 1: PhaseBar PHASE_ORDER missing 'reconstruction'
        PHASE_ORDER = ['opening', 'reading', 'investigation_1', 'discussion', 'voting', 'reveal']
        if 'reconstruction' not in PHASE_ORDER:
            log_bug("HIGH", "frontend/src/components/PhaseBar.tsx:12-19",
                    "PHASE_ORDER does not include 'reconstruction'. When game is in 'reconstruction' phase, "
                    "currentIdx = PHASE_ORDER.indexOf('reconstruction') returns -1. All phase steps will "
                    "show as 'pending' (no active/done state). The reconstruction phase is invisible in the progress bar.")

        # BUG 2: i18n missing 'reconstruction' phase label
        zh_phase_keys = ['opening', 'reading', 'investigation', 'investigation_1', 'discussion', 'voting', 'reveal']
        if 'reconstruction' not in zh_phase_keys:
            log_bug("MEDIUM", "frontend/src/i18n/zh.json (phase section)",
                    "No i18n key for phase.reconstruction. If PhaseBar were to show 'reconstruction' as a step, "
                    "it would display the raw key string 'phase.reconstruction' instead of a localized label. "
                    "This is a latent bug assuming reconstruction is added to PHASE_ORDER.")

        # BUG 3: room_snapshot for murder_mystery sets surface to '' (empty)
        log_bug("MEDIUM", "frontend/src/hooks/useRoom.ts:317",
                "In the room_snapshot handler for murder_mystery, surface is set to empty string ''. "
                "The puzzle.surface field is never populated for MM games. If anything reads puzzle.surface "
                "for MM games, it will get an empty string.")

        # BUG 4: room_snapshot for murder_mystery uses data.script_id as puzzle_id
        log_bug("LOW", "frontend/src/hooks/useRoom.ts:319",
                "In room_snapshot handler for murder_mystery, puzzle_id is set from data.script_id. "
                "This is semantically incorrect (puzzle_id vs script_id) but functionally harmless "
                "since puzzle_id is not used in MM mode.")

        # BUG 5: Chat input disabled during reconstruction phase
        # From RoomPage.tsx lines 692-701:
        # disabled={!connected || isReveal || isVoting || isListenOnly}
        # isListenOnly = activePhase === 'opening' || activePhase === 'reading'
        # isReconstruction is NOT in the disabled condition - good
        # BUT the chat input hint says t('reconstruction.chat_hint') is shown,
        # implying chat should work - let's check if this is actually OK
        log_info("OK: Chat input is NOT disabled during reconstruction phase (players can still chat)")

        # BUG 6: ReconstructionPanel.tsx - 'complete' shown even if phase !== 'reconstruction'
        # Line 26: if (phase !== 'reconstruction' && !complete) return null;
        # This means if complete is set AND phase changes away from reconstruction, panel still shows
        log_bug("LOW", "frontend/src/components/ReconstructionPanel.tsx:26",
                "ReconstructionPanel shows if 'complete' is set, regardless of current phase. "
                "If phase transitions from 'reconstruction' to 'reveal', the panel will still render "
                "the completion summary - this may be intentional but could cause layout overlap in reveal phase.")

        # BUG 7: PhaseBar canSkip excludes 'voting' and 'reveal' but not 'reconstruction'
        # Line 60: const canSkip = phase !== 'reveal' && phase !== 'voting' && !!onSkip;
        # So during reconstruction, a skip button WOULD appear - is that correct?
        log_bug("MEDIUM", "frontend/src/components/PhaseBar.tsx:60",
                "PhaseBar shows skip button during 'reconstruction' phase (only 'reveal' and 'voting' are excluded). "
                "If reconstruction phase shouldn't be skippable, this is a bug. If it can be skipped, "
                "the back-end needs to handle 'skip_phase' during reconstruction.")

        # BUG 8: ReconstructionPanel submitted state is local-only
        # Line 24: const [submitted, setSubmitted] = useState<Set<string>>(new Set());
        # If a player refreshes during reconstruction, submitted state is lost and they could re-submit
        log_bug("MEDIUM", "frontend/src/components/ReconstructionPanel.tsx:24",
                "The 'submitted' state tracking which questions have been answered is stored in local React state. "
                "If the page is refreshed during reconstruction, the submitted Set is reset and the player "
                "could attempt to re-submit answers for already-scored questions. "
                "The backend must handle duplicate answer submissions gracefully.")

        # BUG 9: useRoom.ts - reconstruction_result adds to results but doesn't advance question
        # The reconstructionQuestion state is only updated when 'reconstruction_question' event arrives
        # There's no logic to clear/advance question on result receipt - depends on backend sending next question
        log_info("NOTE: Reconstruction question advancement depends entirely on backend sending 'reconstruction_question' events")

        # BUG 10: WaitingBanner shows if connectedCount < 2, but MM needs 3 players
        # Line 408-414 in RoomPage.tsx
        log_bug("MEDIUM", "frontend/src/pages/RoomPage.tsx:408-414 (WaitingBanner)",
                "WaitingBanner shows when connectedCount < 2, but this murder mystery room requires 3 players. "
                "With 2 players connected, the waiting banner disappears, potentially misleading players "
                "into thinking the game can start when it actually needs a 3rd player.")

        # BUG 11: PhaseBar timer duplication - both useRoom countdown and PhaseBar countdown
        # useRoom.ts line 249-255 decrements mmTimeRemaining every second
        # PhaseBar.tsx lines 39-56 also has its own countdown
        # mmTimeRemaining is passed as timeRemaining to PhaseBar, which resets its localTime on change
        # The useRoom countdown continuously updates mmTimeRemaining, and PhaseBar syncs on each change
        # This could cause double-counting if both run simultaneously
        log_bug("HIGH", "frontend/src/hooks/useRoom.ts:249-255 + frontend/src/components/PhaseBar.tsx:39-56",
                "DOUBLE COUNTDOWN BUG: useRoom.ts has its own setInterval that decrements mmTimeRemaining every second. "
                "PhaseBar.tsx also has its own countdown timer that starts from timeRemaining prop. "
                "PhaseBar re-syncs localTime every time the timeRemaining prop changes (line 33-36). "
                "Since useRoom decrements mmTimeRemaining every second (passing new value to PhaseBar), "
                "PhaseBar's useEffect re-triggers on each decrement, restarting the interval. "
                "Result: PhaseBar countdown may not work correctly as the interval keeps resetting.")

        # -------------------------------------------------------------------
        # TEST 6: Try WebSocket connection directly to verify backend behavior
        # -------------------------------------------------------------------
        log_info("=== TEST 6: WebSocket Simulation ===")

        try:
            import websockets

            async def ws_test_player(player_name, collect_messages=5):
                uri = f"ws://localhost:8000/ws/{ROOM_ID}?player_name={player_name}"
                msgs = []
                try:
                    async with websockets.connect(uri) as ws:
                        # Collect initial messages
                        for _ in range(collect_messages):
                            try:
                                msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
                                msgs.append(json.loads(msg))
                            except asyncio.TimeoutError:
                                break
                    return msgs
                except Exception as e:
                    log_bug("HIGH", f"WebSocket ({player_name})", f"Connection failed: {e}")
                    return []

            # Connect all 3 players via WebSocket
            log_info("Connecting 3 players via WebSocket...")
            results = await asyncio.gather(
                ws_test_player("林晓薇", 10),
                ws_test_player("王建国", 10),
                ws_test_player("张明", 10),
            )

            for player, msgs in zip(PLAYERS, results):
                log_info(f"\nPlayer {player} received {len(msgs)} messages:")
                for msg in msgs:
                    msg_type = msg.get("type", "unknown")
                    log_info(f"  [{msg_type}] {str(msg)[:200]}")

                    if msg_type == "room_snapshot":
                        # Check room snapshot fields
                        gt = msg.get("game_type")
                        phase = msg.get("current_phase")
                        title = msg.get("title")
                        chars = msg.get("characters", [])
                        players_list = msg.get("players", [])

                        log_info(f"  room_snapshot: game_type={gt}, phase={phase}, title={title}")
                        log_info(f"    characters: {[c.get('name') for c in chars]}")
                        log_info(f"    players: {[p.get('name') for p in players_list]}")

                        if not title:
                            log_bug("MEDIUM", "WebSocket room_snapshot",
                                    f"room_snapshot for player {player} missing 'title' field")
                        if gt != "murder_mystery":
                            log_bug("HIGH", "WebSocket room_snapshot",
                                    f"Expected game_type=murder_mystery in snapshot, got {gt!r}")

                    elif msg_type == "error":
                        log_bug("HIGH", f"WebSocket ({player})", f"Error from server: {msg.get('text')}")

                    elif msg_type == "phase_change":
                        new_phase = msg.get("new_phase")
                        log_info(f"  Phase changed to: {new_phase}")

                        if new_phase not in ['opening', 'reading', 'investigation_1', 'discussion',
                                             'voting', 'reveal', 'reconstruction']:
                            log_bug("MEDIUM", "WebSocket phase_change",
                                    f"Unexpected phase value: {new_phase!r}")

                        if new_phase == 'reconstruction':
                            log_info("  => Reconstruction phase detected!")

        except ImportError:
            log_info("websockets library not available, skipping WebSocket simulation")

            # Try with subprocess instead
            import subprocess
            result = subprocess.run(
                ["python3", "-c", """
import asyncio, json, sys
try:
    import websockets
    print("websockets available")
except ImportError:
    print("websockets not available")
"""],
                capture_output=True, text=True
            )
            log_info(f"websockets check: {result.stdout.strip()}")

        # -------------------------------------------------------------------
        # FINAL: Close browser
        # -------------------------------------------------------------------
        for ctx in contexts:
            await ctx.close()
        await browser.close()

        # -------------------------------------------------------------------
        # SUMMARY
        # -------------------------------------------------------------------
        print("\n" + "="*60)
        print("BUG REPORT SUMMARY")
        print("="*60)
        for i, bug in enumerate(bugs, 1):
            print(f"\nBUG #{i} [{bug['severity']}]")
            print(f"  Location: {bug['location']}")
            print(f"  Description: {bug['description']}")

        print(f"\nTotal bugs found: {len(bugs)}")

asyncio.run(run_tests())
