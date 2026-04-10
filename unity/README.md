# AI DM — Unity Client

Unity 6 game client for AI Dungeon Master. Replaces the SwiftUI iOS app while connecting to the **same backend unchanged** (REST + WebSocket).

Aesthetic: Mahjong Soul style — anime character, cherry blossom background, stylised wooden button panels.

---

## Prerequisites

| Tool | Version |
|---|---|
| Unity Hub | 3.x |
| Unity Editor | 6.x (6000.x LTS) |
| iOS Build Support module | installed via Unity Hub |
| Xcode | 15+ (for iOS builds) |

---

## Opening the Project

1. Open **Unity Hub → Add → Add project from disk**
2. Select the `unity/` folder inside this repo
3. Unity will import packages from `Packages/manifest.json` — first open takes a few minutes

### Packages Installed Automatically

| Package | Source |
|---|---|
| TextMeshPro | Built-in UPM |
| Newtonsoft.Json | `com.unity.nuget.newtonsoft-json` |
| NativeWebSocket | GitHub (endel/NativeWebSocket) |
| UniTask | GitHub (Cysharp/UniTask) |
| DOTween (free) | *see below* |

### DOTween Setup (Asset Store — one-time)

DOTween is not available via UPM. Install it manually:

1. Open **Window → Asset Store** in Unity
2. Search "DOTween HOTween v2" (free tier) and import
3. After import, click **Setup DOTween** from the DOTween panel that appears

---

## Manual Scene Setup (after first open)

Unity generates `.meta` files and scene assets on first open. You need to:

### 1. Create Scenes

In the **Project** window, right-click `Assets/Scenes/` → **Create → Scene** for each:

```
Boot
Login
MainMenu
RoomBrowser
WaitingRoom
GameRoom
```

Add all 6 scenes to **Build Settings** (File → Build Settings → Add Open Scenes).

### 2. Canvas Hierarchy (each scene except Boot)

```
Canvas (Screen Space - Overlay)
  Reference resolution: 1920 × 1080, Scale With Screen Size
  └── SafeAreaPanel (anchors: 0,0 → 1,1)
       ├── TopBar
       ├── ContentArea       ← scene-specific UI
       └── BottomNavBar      ← hidden in GameRoom
```

### 3. CJK TextMeshPro Font Atlas

The game is bilingual (zh/en). Generate the Chinese character atlas:

1. **Window → TextMeshPro → Font Asset Creator**
2. Source font: `NotoSansSC-Regular.otf` (download from Google Fonts, place in `Assets/Art/Fonts/`)
3. Character Set: **Custom Range** → `4E00-9FFF` (CJK Unified Ideographs)
4. Atlas resolution: **4096 × 4096**
5. Click **Generate Font Atlas** → **Save**
6. Set this asset as the fallback on your TMP_Settings default font

### 4. Cherry Blossom Sprites

Place 1–3 petal sprites in `Assets/Art/MainMenu/` and assign them to `CherryBlossomSystem.pinkPetalSprites` in the Inspector. Any small pink ellipse sprite works as a placeholder.

### 5. Parallax Mountain Layers

Add 2–3 `RawImage` GameObjects as children of a `ParallaxRoot` under the MainMenu canvas ContentArea. Assign them to `MainMenuController.parallaxLayers`. A simple dark silhouette repeating texture works as a placeholder.

---

## Running Locally

Start the backend first:

```bash
cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

In Unity:
- `AppConfig` reads `PlayerPrefs["backend_url"]` (default: `http://localhost:8000`)
- Override in the **Settings** scene or via `PlayerPrefs.SetString("backend_url", "http://YOUR_IP:8000")` in console

---

## iOS Build

1. **File → Build Settings** → switch platform to iOS
2. **Player Settings:**
   - Bundle ID: `com.yourname.aidm`
   - URL Scheme: `aidm` (for OAuth deep link `aidm://auth?token=...`)
3. Click **Build** → open the generated Xcode project → run on device or simulator

---

## Script Reference

```
Assets/Scripts/
├── Config/
│   └── AppConfig.cs              — BaseURL, WsBaseURL from PlayerPrefs
├── Services/
│   ├── APIManager.cs             — All REST endpoints (UnityWebRequest + UniTask)
│   ├── WebSocketManager.cs       — NativeWebSocket, ping loop, retry, connection ID rotation
│   ├── AuthManager.cs            — OAuth deep link, session validation, guest token
│   └── TokenStore.cs             — PlayerPrefs JWT wrapper
├── Models/
│   ├── GameMessage.cs            — Discriminated union, Parse() factory
│   ├── RestModels.cs             — All REST response/request types
│   └── ClientMessage.cs          — Messages sent from client → server
├── Managers/
│   ├── SceneLoader.cs            — DontDestroyOnLoad, scene data passing
│   └── JwtDecoder.cs             — Base64url decode, extract "sub" claim
├── UI/
│   ├── Boot/       BootController.cs
│   ├── Login/      LoginController.cs
│   ├── MainMenu/   MainMenuController.cs, CherryBlossomSystem.cs
│   ├── RoomBrowser/ RoomBrowserController.cs, RoomCardItem.cs
│   ├── WaitingRoom/ WaitingRoomController.cs, PlayerSlotItem.cs
│   ├── GameRoom/   GameRoomController.cs, ChatMessageItem.cs
│   └── Shared/     BottomNavBar.cs, PlayerAvatar.cs
└── Utils/
    └── ColorPalette.cs           — Deterministic avatar colours, status colours
```

---

## Architecture Notes

- **Backend unchanged.** All game logic stays in FastAPI. Unity is purely a presentation layer.
- **WebSocket:** NativeWebSocket uses iOS CFNetwork under the hood — no Unity WebGL transport needed.
- **Async:** UniTask replaces `async/await` over `Task` — stays on the Unity main thread.
- **No Addressables.** Art assets are direct Project references for now; swap to Addressables if the build grows large.
- **Character art swap:** Replace the single `Image` component referenced by `MainMenuController.characterImage`. No code changes needed.
