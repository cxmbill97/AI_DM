# Multiplayer Lobby Design

**Date:** 2026-04-05  
**Status:** Approved

## Summary

Replace the Solo/Public `GameModeSheet` with a direct Play → Lobby flow. Every game starts in a private waiting room (lobby) where the host can invite friends via a share link or room ID, adjust player slots, toggle public visibility, and start the game when ready.

---

## User Flow

1. User taps **Play** on any game card (Home, Saved, Activity, Explore)
2. App calls `POST /api/rooms` with `is_public: false` → receives `room_id`
3. App navigates to `LobbyView(roomId:)`
4. Host shares the room via iOS share sheet (nav bar share icon) or by copying the room ID
5. Friends open the deep link `aidm://room/{id}` or enter the room ID manually → land in `LobbyView`
6. Each non-host player taps **I'm Ready**; host sees their status update in real-time
7. Host taps **Start Game** (enabled at any time, even solo) → backend transitions room to active, all lobby clients navigate to `RoomView`
8. Optionally, host toggles **Make Public** to list the room in the Explore tab

---

## Screens

### LobbyView

**Nav bar:**
- Left: back chevron (dismisses lobby, room is abandoned)
- Center: game title + "Waiting for players…" subtitle
- Right: LOBBY badge + share icon (`square.and.arrow.up` SF Symbol, gold)

**Room ID card:**
- Large monospace gold room ID (e.g. `A7X-92K`)
- Copy button (copies ID to clipboard)
- Share button in nav bar opens native iOS share sheet via `ShareLink` with pre-built invite text:
  ```
  🎲 Join my AI DM game "{title}"!
  Room ID: {id}
  aidm://room/{id}
  ```

**Player slots:**
- Section header: "Players (N / M)"
- Slot count:
  - Murder mystery: locked to `script.player_count` (no stepper)
  - Turtle soup: host sees `−` / `+` stepper, range 2–4, default 4
- Filled slot: avatar circle + name + HOST badge (if host) + ready indicator (green ✓ or gray dot)
- Empty slot: dashed border, `+` icon, "Waiting for player…" text
- Host is always auto-marked ready on join

**Make Public toggle** (host only):
- Off by default
- When toggled on: calls `PATCH /api/rooms/{id}` with `{"is_public": true}`; room appears in Explore

**Bottom action button:**
- Host: **Start Game** (gold, always enabled) — calls `POST /api/rooms/{id}/start`
- Guest (not ready): **I'm Ready** (gold) — sends `{"type": "ready"}` over WebSocket
- Guest (ready): **Ready ✓** (dimmed, disabled) + subtitle "Waiting for host to start…"

---

## LobbyViewModel

```swift
@MainActor
final class LobbyViewModel: ObservableObject {
    let roomId: String
    let gameTitle: String
    let isHost: Bool

    @Published var players: [LobbyPlayer] = []     // joined players with ready status
    @Published var slotCount: Int = 4               // adjustable for turtle soup
    @Published var isPublic: Bool = false
    @Published var gameStarted: Bool = false        // triggers navigation to RoomView
    @Published var errorMessage: String?

    // WebSocket connection (same pattern as RoomViewModel)
    func connect() async { ... }
    func disconnect() { ... }

    func markReady() { /* send {"type":"ready"} */ }
    func startGame() async { /* POST /api/rooms/{id}/start */ }
    func togglePublic(_ value: Bool) async { /* PATCH /api/rooms/{id} */ }
    func updateSlotCount(_ count: Int) async { /* PATCH /api/rooms/{id} with max_players */ }
}

struct LobbyPlayer: Identifiable {
    let id: String
    let name: String
    let isHost: Bool
    var isReady: Bool
}
```

**WebSocket events handled:**
| Event | Action |
|-------|--------|
| `room_snapshot` | Populate initial player list and slot count |
| `player_joined` | Append new `LobbyPlayer` (isReady: false) |
| `player_ready` | Set `isReady = true` for that player |
| `game_started` | Set `gameStarted = true` → triggers NavigationStack push to `RoomView` |
| `system` | Ignore in lobby (already shown in RoomView) |

---

## Backend Changes

### New endpoints

**`POST /api/rooms/{room_id}/start`** (auth required, host only)
- Validates caller is the room creator
- Sets `room.started = True`
- Broadcasts `{"type": "game_started"}` to all WebSocket clients in the room
- Returns `{"ok": true}`

**`PATCH /api/rooms/{room_id}`** (auth required, host only)
- Body: `{"is_public": bool}` and/or `{"max_players": int}`
- Updates `room.is_public` and/or `room.max_players`
- Returns `{"ok": true}`

### Modified WebSocket events (`ws.py`)

**`player_joined`** — new structured event broadcast when any player connects to a room that has not yet started:
```json
{"type": "player_joined", "player_id": "...", "player_name": "..."}
```

**`player_ready`** — new event broadcast when a player sends `{"type": "ready"}`:
```json
{"type": "player_ready", "player_id": "...", "player_name": "..."}
```

**`game_started`** — broadcast by `/start` endpoint:
```json
{"type": "game_started"}
```

### Room model (`room.py`)

Add fields:
```python
self.started: bool = False
self.max_players: int = 4   # overrides script.player_count for turtle soup
```

`GET /api/rooms` (Explore) already filters `if not room.is_public`. Add: also filter `if room.started` (started rooms don't appear in Explore).

### Deep link handler

`AIDungeonMasterApp.swift` — handle `aidm://room/{id}`:
- If user is authenticated: navigate to `LobbyView(roomId: id, isHost: false)`
- If not authenticated: save pending room ID, redirect to login, then navigate after auth

---

## Files Changed

| File | Change |
|------|--------|
| `Home/GameModeSheet.swift` | **Delete** |
| `Home/HomeView.swift` | Remove sheet state, call `createAndNavigate()` directly on Play tap |
| `Saved/SavedView.swift` | Same — remove sheet, direct `createAndNavigate()` |
| `Activity/ActivityView.swift` | Same |
| `Lobby/LobbyView.swift` | **New** — lobby waiting room screen |
| `Lobby/LobbyViewModel.swift` | **New** — WebSocket + REST logic for lobby |
| `Models/Models.swift` | Add `LobbyPlayer`, `LobbyStartedPayload` WebSocket models |
| `Services/APIService.swift` | Add `startRoom()`, `patchRoom()` methods |
| `App/AIDungeonMasterApp.swift` | Add `aidm://room/{id}` deep link handler |
| `backend/app/main.py` | Add `POST /rooms/{id}/start`, `PATCH /rooms/{id}` |
| `backend/app/room.py` | Add `started`, `max_players` fields |
| `backend/app/ws.py` | Broadcast `player_joined`, `player_ready`, `game_started` events |

---

## Out of Scope

- Kick player from lobby (host moderation)
- Lobby chat before game starts
- Reconnecting to an in-progress game after disconnect (existing behavior unchanged)
