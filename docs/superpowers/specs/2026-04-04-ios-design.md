# AI DM — iOS App Design Spec

## Overview

A native SwiftUI iOS app with full feature parity to the web frontend. Connects to the existing FastAPI backend over REST + WebSocket. Targets local LAN during development; production backend URL swapped at release.

**Architecture:** MVVM + async/await. Each screen has an ObservableObject ViewModel. Shared service singletons for networking, WebSocket, and Keychain. No third-party dependencies beyond Apple's built-in frameworks.

**Auth:** Google Sign-In (ASWebAuthenticationSession + custom URL scheme) + Sign in with Apple (native). JWT stored in Keychain.

---

## Project Location

```
ios/                          ← Xcode project, lives at repo root
└── AIDungeonMaster/
```

Added to `.gitignore`: `ios/AIDungeonMaster.xcodeproj/xcuserdata/`, `ios/DerivedData/`

---

## File Structure

```
ios/AIDungeonMaster/
├── App/
│   └── AIDungeonMasterApp.swift     @main entry; injects AuthViewModel as environment object
├── Config/
│   └── AppConfig.swift              baseURL — reads from UserDefaults in DEBUG, hardcoded in RELEASE
├── Services/
│   ├── APIService.swift             All REST calls. Generic request<T:Decodable> async throws.
│   │                                Attaches Authorization: Bearer <token> automatically.
│   ├── WebSocketService.swift       URLSessionWebSocketTask wrapper.
│   │                                Publishes GameMessage via AsyncStream. Auto-reconnects.
│   └── KeychainService.swift        save(token:) / loadToken() / deleteToken() via Security framework.
├── Auth/
│   ├── AuthViewModel.swift          Holds User? state. googleSignIn() / appleSignIn() / signOut().
│   │                                On launch: loads token from Keychain, calls GET /api/me to validate.
│   └── LoginView.swift              Google button (ASWebAuthenticationSession) + Sign in with Apple button.
├── Lobby/
│   ├── LobbyViewModel.swift         Fetches puzzles + scripts. Handles search, tab filter, favorites toggle.
│   ├── LobbyView.swift              TabView tab. List of GameCardViews. Join-room sheet.
│   └── GameCardView.swift           Card with title, difficulty, tags. Action sheet: Solo / Create Room.
├── Room/
│   ├── RoomViewModel.swift          Owns WebSocketService. Handles all inbound GameMessage types.
│   │                                Exposes messages[], players[], phase, clues to View.
│   └── RoomView.swift               Full-screen. ScrollView chat + input bar + clue drawer.
├── Profile/
│   ├── ProfileViewModel.swift       Fetches favorites + history. handleUnfavorite().
│   └── ProfileView.swift            Avatar, stat chips. Segmented control: Favorites | History.
├── Settings/
│   └── SettingsView.swift           Language picker (zh/en). Backend URL field (DEBUG only). Sign out.
└── Models/
    └── Models.swift                 Codable structs: User, PuzzleSummary, ScriptSummary,
                                     GameMessage, RoomSnapshot, FavoriteItem, HistoryItem.
```

---

## Auth Flow

### Google Sign-In
1. User taps "Sign in with Google"
2. `ASWebAuthenticationSession` opens `http://<backend>/auth/google/mobile`
3. Backend redirects to Google OAuth consent
4. Google redirects to `http://<backend>/auth/google/mobile/callback?code=...`
5. Backend exchanges code, upserts user, issues JWT, redirects to `aidm://auth?token=<jwt>`
6. iOS intercepts `aidm://` URL scheme, extracts token, stores in Keychain
7. `AuthViewModel` calls `GET /api/me` to populate `User` state

### Sign in with Apple
1. User taps "Sign in with Apple" (ASAuthorizationController)
2. Apple returns `identityToken` (JWT signed by Apple)
3. App posts `{ identity_token, full_name }` to `POST /auth/apple`
4. Backend verifies token with Apple's public keys (PyJWT + `cryptography`), upserts user, returns `{ token: <jwt> }`
5. App stores JWT in Keychain, calls `GET /api/me`

### Session persistence
- On cold launch: `KeychainService.loadToken()` → `GET /api/me` → if 401, show LoginView
- Sign out: delete Keychain token, clear `AuthViewModel.user`

### Dev login (DEBUG only)
`LoginView` shows a dev login text field only in `#if DEBUG` builds — never shown in TestFlight or App Store builds. This prevents App Store reviewers from seeing a non-standard auth path.

### WebSocket token security note
The JWT is passed as a URL query parameter (`?token=<jwt>`) which appears in server logs. This is standard practice for WebSocket auth (headers cannot be set during the HTTP upgrade handshake in iOS). Mitigate by: ensuring backend logs redact the token field, and keeping token lifetime short (current: 30 days — acceptable).

---

## Networking

### APIService
```swift
func request<T: Decodable>(_ path: String, method: String = "GET", body: Encodable? = nil) async throws -> T
```
- Base URL from `AppConfig.baseURL`
- Attaches `Authorization: Bearer <token>` from Keychain on every call
- Throws `APIError.unauthorized` on 401 (AuthViewModel observes → shows LoginView)
- Throws `APIError.httpError(statusCode, message)` for other non-2xx

### WebSocketService
```swift
class WebSocketService: ObservableObject {
    func connect(roomId: String, token: String) async
    func send(_ message: ClientMessage) async throws
    var stream: AsyncStream<GameMessage> { get }
    func disconnect()
}
```
- URL: `ws://<backend>/ws/<roomId>?token=<jwt>`
- Reconnects automatically on unexpected disconnect (exponential backoff, max 3 retries)
- Parses inbound JSON into `GameMessage` enum

### AppConfig
```swift
struct AppConfig {
    static var baseURL: String {
        #if DEBUG
        // Simulator default: localhost. On device: type your LAN IP in Settings → Backend URL.
        UserDefaults.standard.string(forKey: "backend_url") ?? "http://localhost:8000"
        #else
        "https://your-production-domain.com"  // replace before App Store submission
        #endif
    }
}
```

---

## Models

```swift
// --- REST response models ---
struct User: Codable { let id, name, email, avatar_url, created_at: String }
struct PuzzleSummary: Codable { let id, title, difficulty: String; let tags: [String] }
struct ScriptSummary: Codable { let id, title, difficulty, game_mode: String }
struct FavoriteItem: Codable { let item_id, item_type, saved_at: String }
struct HistoryItem: Codable { let id, room_id, game_type, title, played_at: String; let player_count: Int }

// --- WebSocket payload structs (match backend models.py exactly) ---
struct CluePayload: Codable { let id, title, content: String; let unlock_keywords: [String] }

struct DmResponsePayload: Codable {
    let player_name: String
    let judgment: String        // "是" | "否" | "部分正确" | "无关"
    let response: String        // DM's narrative reply
    let truth_progress: Double  // 0.0–1.0
    let clue_unlocked: CluePayload?
    let hint: String?
    let truth: String?          // non-nil when game is solved
    let timestamp: Double
}

struct PlayerMessagePayload: Codable {
    let player_name: String
    let text: String
    let timestamp: Double
}

struct SystemPayload: Codable { let text: String }

struct PlayerInfo: Codable { let id, name: String; let character: String? }

struct RoomSnapshotPayload: Codable {
    let room_id: String
    let game_type: String           // "turtle_soup" | "murder_mystery"
    let phase: String
    let current_phase: String?      // MM only
    let phase_description: String?  // MM only
    let players: [PlayerInfo]
    let clues: [CluePayload]        // unlocked clues (full objects, not strings)
    let time_remaining: Int?        // MM phase timer, seconds
}

struct ErrorPayload: Codable { let message: String }

// --- GameMessage: inbound discriminated union on "type" field ---
// Swift Codable cannot auto-synthesize this — use a custom decoder:
enum GameMessage {
    case dmResponse(DmResponsePayload)
    case playerMessage(PlayerMessagePayload)
    case system(SystemPayload)
    case roomSnapshot(RoomSnapshotPayload)
    case error(ErrorPayload)
}

extension GameMessage: Decodable {
    private enum TypeKey: String, Codable {
        case dm_response, player_message, system, room_snapshot, error
    }
    private struct TypeWrapper: Decodable { let type: TypeKey }

    init(from decoder: Decoder) throws {
        let wrapper = try TypeWrapper(from: decoder)
        let container = try decoder.singleValueContainer()
        switch wrapper.type {
        case .dm_response:    self = .dmResponse(try container.decode(DmResponsePayload.self))
        case .player_message: self = .playerMessage(try container.decode(PlayerMessagePayload.self))
        case .system:         self = .system(try container.decode(SystemPayload.self))
        case .room_snapshot:  self = .roomSnapshot(try container.decode(RoomSnapshotPayload.self))
        case .error:          self = .error(try container.decode(ErrorPayload.self))
        }
    }
}

// --- Outbound (client → server) ---
struct ClientMessage: Codable { let type: String; let text: String }
// Usage: ClientMessage(type: "chat", text: userInput)
```

---

## Backend Changes Required

| Change | File | Details |
|--------|------|---------|
| `GET /auth/google/mobile` | `main.py` | Same as `/auth/google` but uses `GOOGLE_MOBILE_REDIRECT_URI` (redirects to `aidm://auth?token=...`) |
| `GET /auth/google/mobile/callback` | `main.py` | Exchanges code, upserts user, redirects to `aidm://auth?token=<jwt>` |
| `POST /auth/apple` | `main.py` | Body: `{identity_token: str, full_name: str}`. Fetches Apple JWKS from `https://appleid.apple.com/auth/keys`, verifies RS256 JWT, checks `aud == apple_bundle_id`, upserts user with `sub = "apple:{sub}"`, returns `{token: <jwt>}` |
| `GOOGLE_MOBILE_REDIRECT_URI` | `config.py` | Default: `http://localhost:8000/auth/google/mobile/callback` |
| `apple_bundle_id` | `config.py` | Bundle ID as `aud` claim for Apple token verification (e.g. `com.yourname.aidm`) |
| `cryptography` dep | `pyproject.toml` | Required for Apple RS256 JWT verification (PyJWT uses it) |
| DB: `google_sub` → `provider_sub` | `auth.py` + migration | Rename `google_sub` column to `provider_sub` so Apple users (`apple:<sub>`) and Google users (`google:<sub>`) share the same table cleanly. Add `ALTER TABLE users RENAME COLUMN google_sub TO provider_sub` migration in `init_auth_db`. |

### Google Cloud Console
Add `http://localhost:8000/auth/google/mobile/callback` as an additional authorized redirect URI.

### Xcode
- Register URL scheme `aidm` in Info.plist → URL Types (identifier: `com.yourname.aidm`, schemes: `aidm`)
- Add ATS exception in Info.plist for LAN HTTP (dev builds only):
  ```xml
  <key>NSAppTransportSecurity</key>
  <dict>
    <key>NSAllowsLocalNetworking</key><true/>
  </dict>
  ```
  `NSAllowsLocalNetworking` permits `*.local` and LAN IPs without allowing arbitrary internet HTTP — safe for App Store review.

---

## Navigation

```
ContentView
└── if user == nil → LoginView
└── else → TabView
    ├── Tab 1: LobbyView
    │   └── NavigationStack
    │       └── .sheet(JoinRoomView)
    │       └── .fullScreenCover(RoomView)  ← presented on Solo or Create Room
    ├── Tab 2: ProfileView
    └── Tab 3: SettingsView
```

---

## Settings Screen

- Language: Picker (中文 / English) — stored in `UserDefaults["lang"]`, passed as `?lang=` query param on all API calls
- `#if DEBUG`: "Backend URL" TextField — edits `UserDefaults["backend_url"]`
- Sign Out button

---

## Error Handling

- 401 from any API call → `AuthViewModel` clears user → LoginView shown automatically
- WebSocket disconnect → RoomViewModel shows "Reconnecting..." banner, retries silently
- Network offline → show inline error in each ViewModel's `errorMessage: String?`

---

## Out of Scope

- Push notifications (can be added post-launch)
- Android (React Native would be the path if needed later)
- App Store submission steps (TestFlight first)
- Offline mode
