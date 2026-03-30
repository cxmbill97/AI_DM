# CLAUDE.md

## Commands

```bash
cd backend && uv run uvicorn app.main:app --reload          # API server (port 8000)
cd backend && uv run pytest tests/ -x -v                     # all tests (147, mock LLM)
cd backend && uv run pytest tests/test_redteam.py -x -v      # anti-spoiler red team (real API)
cd frontend && pnpm dev                                       # React dev (port 5173)
```

## Project Status — Phase 2 Complete ✓

Both phases are fully implemented and working end-to-end.

**Phase 1 (done):** Single-player Q&A at `/play`. REST-based. Hints as pseudo-clue-cards.

**Phase 2 (done):** Multiplayer rooms via WebSocket. 2-4 players, shared chat, real clue
unlock, proactive DM intervention engine, per-player stats on game-over review screen.

This is the MVP stepping stone toward a full 剧本杀 (murder mystery) AI DM.

## Architecture

```
backend/                          (FastAPI + Python 3.12 + uv)
├── app/
│   ├── main.py                   # REST endpoints + WebSocket /ws/{room_id}
│   ├── dm.py                     # DM logic: prompt assembly, response parse, hint/clue,
│   │                             #   dm_proactive_message() for silence interventions
│   ├── llm.py                    # MiniMax client via OpenAI SDK; LLM call logger
│   ├── models.py                 # Pydantic: Puzzle, Clue, GameSession, ChatMessage, etc.
│   ├── puzzle_loader.py          # Load puzzle JSON from data/puzzles/
│   ├── room.py                   # Room: join/leave/reconnect, broadcast, per-player send_lock
│   ├── ws.py                     # WebSocket handler + background tick loop (_room_tick_loop)
│   └── intervention.py           # InterventionEngine: silence timer, explicit triggers,
│                                 #   exponential backoff, cooldown, random_gentle_message()
├── data/puzzles/                  # Puzzle JSON files (v2 schema with clues[])
├── logs/llm/                      # Auto-created; one JSONL file per day of LLM call logs
├── tests/
│   ├── conftest.py                # Fixtures: mock LLM, sample puzzle
│   ├── test_dm.py                 # DM correctness: known Q→A pairs, parse fallback
│   ├── test_clues.py              # Clue unlock: passive + active, idempotency
│   ├── test_redteam.py            # Anti-spoiler adversarial prompts (real LLM, slow)
│   ├── test_room.py               # Room: join/leave, broadcast, reconnect, replay
│   └── test_intervention.py       # InterventionEngine: silence, backoff, triggers
└── pyproject.toml

frontend/                          (React 19 + Vite 8 + TypeScript, strict)
├── src/
│   ├── App.tsx                    # BrowserRouter: / Lobby, /play Single-player, /room/:id Room
│   ├── api.ts                     # fetch() wrappers; RoomPlayer / RoomState types
│   ├── pages/
│   │   ├── LobbyPage.tsx          # Create/join room; puzzle picker; single-player entry
│   │   ├── SinglePlayerPage.tsx   # Phase 1 single-player (unchanged from Phase 1)
│   │   └── RoomPage.tsx           # Phase 2 multiplayer: chat, share bar, waiting banner,
│   │                              #   DM typing indicator, multiplayer review screen
│   ├── components/
│   │   ├── PuzzleCard.tsx         # Surface story display (collapsible)
│   │   ├── ChatPanel.tsx          # Single-player message list + input
│   │   ├── CluePanel.tsx          # Unlocked clue cards with slide-in animation
│   │   ├── PlayerList.tsx         # Roster with deterministic avatar colors + online dot
│   │   └── HintBar.tsx            # Progress bar + hint display
│   └── hooks/
│       ├── useChat.ts             # Phase 1: REST-based Q&A
│       └── useRoom.ts             # Phase 2: WebSocket; exposes messages, players, clues,
│                                  #   connected, progress, truth, puzzle, error,
│                                  #   questionsByPlayer, cluesByPlayer, dmTyping, sendMessage
└── vite.config.ts                 # proxy /api → http://localhost:8000
                                   # proxy /ws  → ws://localhost:8000 (ws:true, changeOrigin:true)
```

## Key Concepts

1. **Puzzle JSON with Clues** — Each puzzle has `surface`, `truth`, `key_facts`,
   `hints` (ordered), AND `clues[]`. Clues are structured cards with id, title,
   content, and unlock_keywords. Phase 1 uses hints-as-pseudo-clues (shown as
   visual cards when player is stuck). Phase 2 adds real unlock via question matching.

2. **Clue Card System** — Two modes:
   - **Passive (Phase 1):** Hints from `hints[]` are wrapped in card UI when
     `should_hint=true`. Sequential hint delivery with visual flair.
   - **Active (Phase 2):** Clues from `clues[]` have `unlock_keywords`. When a
     player's question matches a keyword, `clue_unlocked` is set in the DM response.

3. **MiniMax API** — OpenAI SDK compatible. `base_url="https://api.minimax.io/v1"`.
   Model: `MiniMax-M2.5`. JSON output not guaranteed — always wrap parsing in
   try/except with fallback. Strip `<think>…</think>` before display; keep in history.

4. **GameSession** — In-memory, keyed by session_id (= room_id for multiplayer).
   Tracks: puzzle, history, hint_index, unlocked_clue_ids, consecutive_misses,
   truth_progress, finished.

5. **Room** — Wraps a GameSession. Holds `players` dict (id → slot with name,
   websocket, connected, last_seen, send_lock), `message_history` (replay on
   reconnect), `_lock` (serializes concurrent dm_turn calls), `intervention`
   (InterventionEngine), `_tick_task` (background silence monitor).

6. **DM Intervention Engine** — Rules-based, no extra LLM cost for gentle level:
   - `gentle` (45s silence): random canned Chinese encouragement, no LLM call
   - `nudge`  (90s silence): LLM-generated ≤30-char encouragement
   - `hint`  (180s silence): LLM-generated ≤50-char guiding hint (no spoilers)
   - Threshold doubles after each nudge (45→90→180→240s cap). Global cooldown 15s.
   - Explicit triggers: `@DM`, `提示`, `帮我`, `告诉我` in any player message.

7. **WebSocket Protocol** — Client sends `{type:"chat", text:"..."}`.
   Server sends: `room_snapshot | system | player_message | dm_response | dm_intervention | error`

## Puzzle JSON Schema (v2 — with clues)

```json
{
  "id": "turtle_001",
  "title": "夜半敲门",
  "surface": "一个人住在山顶的小屋里，半夜听见敲门声，打开门却没有人...",
  "truth": "小屋的门向外推开，门前就是悬崖。来人爬上悬崖敲门求救...",
  "key_facts": ["小屋的门向外推开", "门外就是悬崖", "..."],
  "clues": [
    {
      "id": "clue_door",
      "title": "小屋建筑图纸",
      "content": "一张泛黄的图纸显示：小屋正门采用外推式设计，门前是一段极窄的石台阶",
      "unlock_keywords": ["门", "开门", "门怎么开", "推门"]
    }
  ],
  "hints": ["想想这个门的开法有什么特别的？", "..."],
  "difficulty": "classic",
  "tags": ["经典", "物理诡计"]
}
```

## Things That Will Bite You

- **NEVER let truth appear in LLM output.** Truth goes into system prompt only.
  Post-generation `check_spoiler_leak()` scans key_facts as a safety net.
- **Clue content must not directly state the answer.** Each clue is one piece of
  evidence. Reading all clues together should not reveal the full truth.
- **MiniMax JSON output is not guaranteed.** Always try/except. Fallback: treat
  raw text as response, set judgment="无关".
- **MiniMax `<think>` tags** appear in reasoning output. `strip_think()` before
  display or parsing. Keep raw in conversation history for multi-turn quality.
- **Clue unlock matching is fuzzy.** Substring check, not exact match. "门是怎么打开的"
  matches unlock_keywords ["门", "开门"]. Future: upgrade to embedding similarity.
- **DM turn raises exceptions.** `dm_turn()` can throw APIError (MiniMax down,
  rate-limited, etc.). In ws.py the call is wrapped in try/except — sends
  "DM 暂时无法回应" error message and continues the receive loop. Do NOT let LLM
  errors propagate and kill the WebSocket.
- **WebSocket handler must always call disconnect_player().** The receive loop uses
  `finally:` (not just `except WebSocketDisconnect:`) so the player slot is freed
  even on unexpected crashes. If `connected=True` is left dangling, reconnects get
  "名字已被使用" and enter an infinite retry loop.
- **React StrictMode double-invocation.** In dev, effects run twice. `useRoom` defers
  the initial `connect()` with `setTimeout(..., 0)` so StrictMode's synchronous
  cleanup cancels the timer before any WebSocket is created.
- **Infinite retry loop.** `retriesRef.current` must NOT be reset in `ws.onopen`.
  Reset it in the `room_snapshot` handler — only after the server confirms a valid
  room. Otherwise every immediate-close cycles the counter back to 0 forever.
- **room_snapshot must include player IDs.** Iterate `room.players.items()` (not
  `.values()`) so each player object includes `"id"` matching the `RoomPlayer` type.
- **Frontend proxies /ws with `changeOrigin: true`.** Required for the Vite WS
  proxy to forward the correct Host header to uvicorn.
- **Chinese text only for game content.** Puzzle, DM speech, UI labels in Chinese.
  Code and variable names in English.

## DM Response Schema (WebSocket dm_response message)

```json
{
  "type": "dm_response",
  "player_name": "Alice",
  "judgment": "是|不是|无关|部分正确",
  "response": "DM回复文本",
  "truth_progress": 0.45,
  "clue_unlocked": null | { "id": "clue_door", "title": "...", "content": "..." },
  "hint": null | "plain-text hint string",
  "truth": null | "汤底全文 — set when truth_progress >= 1.0",
  "timestamp": 1711234567.89
}
```

## Clue Unlock Logic

```python
# Phase 2 (active — keyword match, fires every turn)
def check_clue_unlock_active(message, puzzle, unlocked_ids) -> Clue | None:
    for clue in puzzle.clues:
        if clue.id in unlocked_ids: continue
        if any(kw in message for kw in clue.unlock_keywords):
            unlocked_ids.add(clue.id)
            return clue
    return None

# Phase 1 fallback (passive — sequential hint delivery when player is stuck)
def check_clue_unlock_passive(session) -> Clue | None:
    if session.hint_index < len(session.puzzle.hints):
        # wraps hint text as Clue(id=f"hint_{n}", title="DM 提示", ...)
        ...
```

## Code Conventions

- Python: ruff format + ruff check. Type hints required. async for IO.
- TypeScript: Prettier. Strict mode. No `any` (use `unknown` + type guards or casts).
- Phase 1: REST only (`/api/start`, `/api/chat`). Phase 2: WebSocket + REST.
- State: In-memory only. No database.
- Secrets: `.env` with `MINIMAX_API_KEY`. Never commit.
- Deps: `uv` for Python, `pnpm` for frontend.
- LLM calls are logged to `backend/logs/llm/YYYY-MM-DD.jsonl` automatically.

## Testing

- **test_dm.py**: Known Q→A pairs, prompt assembly, JSON parse fallback.
- **test_clues.py**: Passive hint-as-clue delivery. Active keyword unlock.
  Clue idempotency (same clue not unlocked twice). All clues unlockable.
- **test_intervention.py**: Silence timer, exponential backoff thresholds (45/90/180/240s),
  silence levels (gentle/nudge/hint), cooldown, explicit trigger detection,
  record_dm_spoke increments nudge count, combined scenarios.
- **test_room.py**: Join/leave, broadcast, reconnect within window, message replay,
  room full rejection. Uses `monkeypatch` to disable `_ensure_tick_running` so
  background tasks don't interfere with message-order assertions.
- **test_redteam.py** (real LLM, `--slow`): 10+ adversarial prompts → assert
  zero truth leakage. Assert clue content does not appear before unlock.

## Prompt Assembly Order

1. System: DM persona + rules (是/不是/无关/部分正确 only)
2. System: surface (汤面)
3. System: truth (汤底) — TOP SECRET, never repeat or paraphrase
4. System: key_facts — for matching accuracy
5. System: unlocked_clues — titles + content so DM can reference them
6. System: locked_clue reminder — existence only, no content
7. System: JSON output schema
8. Messages: conversation history (last 20 turns)
9. User: current player question

## WebSocket Message Types

| type | direction | description |
|------|-----------|-------------|
| `room_snapshot` | S→C | Full room state on join/reconnect: puzzle, players (with id), phase |
| `system` | S→C | Player join/leave/reconnect notices |
| `player_message` | S→C | Echoed chat message from any player |
| `dm_response` | S→C | DM judgment + response; may include clue_unlocked, hint, truth |
| `dm_intervention` | S→C | Proactive DM message; reason: silence\|encouragement\|hint |
| `error` | S→C | Non-fatal error (e.g. DM API failure); WebSocket stays open |
| `chat` | C→S | Player sends a question |

## Frontend UX Details

- **Avatar colors**: deterministic 6-color palette from player name hash. Same color
  in PlayerList sidebar and chat bubbles. Defined in both `RoomPage.tsx` and
  `PlayerList.tsx` (duplicated intentionally — small helper, no shared file needed).
- **DM typing indicator**: three amber dots with bounce animation. Appears when any
  `player_message` is received; disappears when `dm_response` arrives. `dmTyping`
  state in `useRoom.ts`.
- **Share bar**: always visible below the game header. Shows room code + "复制邀请码"
  button. Falls back to clipboard copy if `navigator.share` is unavailable.
- **Waiting banner**: shows when fewer than 2 players are connected.
- **Intervention labels**: reason-specific — `hint` → "DM 💡 主动提示",
  `encouragement` → "DM 🎲 鼓励", `silence` → "DM 💬 发话了".
- **Multiplayer review screen**: replaces TruthReveal when game ends. Shows truth,
  per-player question count + clue count with avatar colors, 🏆 MVP 推理王 badge
  for player with most clues (suppressed on ties).
