# Auth, UI Redesign & Profile Page — Design Spec

**Date:** 2026-04-03  
**Status:** Approved

---

## Scope

Three features delivered together because they share the auth layer:

1. **Google OAuth login** — required to use the app
2. **UI Redesign** — sidebar layout, card grid, SVG icons throughout
3. **Profile page** — favorites (bookmarked puzzles/scripts) + play history

WeChat login is explicitly out of scope for this iteration.

---

## 1. Auth — Google OAuth

### Flow

```
User visits app (no token)
  → LoginPage renders (Google sign-in button only)
  → Click → GET /auth/google
  → Redirect to Google consent screen
  → Google calls GET /auth/google/callback?code=...
  → Backend exchanges code for id_token, extracts (sub, name, email, avatar_url)
  → Upsert user row in SQLite users table
  → Issue signed JWT (HS256, 30-day expiry), return as JSON
  → Frontend stores token in localStorage under key "ai_dm_token"
  → AuthContext validates token on load, fetches /api/me
  → App renders normally
```

### Backend

**New dependency:** `authlib>=1.3.0`, `httpx>=0.28.1` (already in dev deps — move to main)

**New SQLite table** (added to `community.py` or a new `auth.py`):

```sql
CREATE TABLE IF NOT EXISTS users (
  id          TEXT PRIMARY KEY,        -- uuid4
  google_sub  TEXT UNIQUE NOT NULL,
  name        TEXT NOT NULL,
  email       TEXT NOT NULL,
  avatar_url  TEXT NOT NULL DEFAULT '',
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_favorites (
  user_id   TEXT NOT NULL,
  item_id   TEXT NOT NULL,             -- puzzle_id or script_id
  item_type TEXT NOT NULL,             -- "puzzle" | "script"
  saved_at  TEXT NOT NULL,
  PRIMARY KEY (user_id, item_id, item_type)
);

CREATE TABLE IF NOT EXISTS room_history (
  id           TEXT PRIMARY KEY,       -- uuid4
  user_id      TEXT NOT NULL,
  room_id      TEXT NOT NULL,
  game_type    TEXT NOT NULL,          -- "turtle_soup" | "murder_mystery"
  title        TEXT NOT NULL,
  player_count INTEGER NOT NULL DEFAULT 0,
  played_at    TEXT NOT NULL
);
```

**New file:** `backend/app/auth.py`

- `init_auth_db()` — creates the three tables above; called at startup alongside `init_db()`
- `upsert_user(google_sub, name, email, avatar_url) -> dict` — insert/update, return user row
- `create_jwt(user_id) -> str` — signs HS256 token, 30-day expiry
- `decode_jwt(token) -> dict` — verifies and decodes; raises `ValueError` on invalid/expired
- `get_current_user(request) -> dict` — reads `Authorization: Bearer <token>` header, returns user dict; raises `HTTPException(401)` if missing or invalid
- `add_favorite(user_id, item_id, item_type)` / `remove_favorite(...)` / `list_favorites(user_id)`
- `add_history(user_id, room_id, game_type, title, player_count)`
- `list_history(user_id, limit=50)`

**New endpoints in `main.py`:**

```
GET  /auth/google                        → redirect to Google
GET  /auth/google/callback               → exchange code, return {token, user}
GET  /api/me                             → return current user (auth required)
POST /api/favorites/{item_type}/{item_id}  → add favorite
DELETE /api/favorites/{item_type}/{item_id} → remove favorite
GET  /api/favorites                      → list favorites
GET  /api/history                        → list room history
```

**Room history logging:** `ws.py` calls `add_history()` when a player joins a room (on `room_snapshot` send). The `player_name` WebSocket query param is replaced by reading the user's name from the JWT; the backend decodes the `token` query param instead of `player_name`. Unauthenticated WebSocket connections are rejected with a `4001` close code.

**JWT secret:** Read from `config.py` → env var `JWT_SECRET`. If not set, generate a random one at startup with a warning (dev mode only).

**Google credentials:** `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` env vars. `GOOGLE_REDIRECT_URI` defaults to `http://localhost:8000/auth/google/callback`.

### Frontend

**New file:** `frontend/src/auth.tsx` — `AuthContext` + `AuthProvider` + `useAuth()` hook

```ts
interface AuthUser {
  id: string;
  name: string;
  email: string;
  avatar_url: string;
}

interface AuthContext {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
  logout: () => void;
}
```

- On mount: reads `localStorage.getItem("ai_dm_token")`, calls `GET /api/me` to validate; sets `user` or clears token if invalid/expired
- `logout()` clears localStorage, resets state
- `AuthProvider` wraps the entire app in `App.tsx`

**New page:** `frontend/src/pages/LoginPage.tsx`

- Shown when `user === null && !loading`
- Same dark atmospheric design as the rest of the app
- Single centered card: logo, tagline, "Sign in with Google" button (real Google SVG, links to `GET /auth/google`)
- No name input — auth replaces the current manual name flow

**Protected routing:** `App.tsx` wraps routes in a check — if `!user && !loading`, render `<LoginPage />` instead of the route tree.

**`apiFetch` update:** Automatically attaches `Authorization: Bearer <token>` header for all `/api/*` calls.

**Google callback handling:** `GET /auth/google/callback` returns a redirect to `/?token=<jwt>`. Frontend reads the `token` query param on mount in `AuthProvider`, stores it, then strips it from the URL.

---

## 2. UI Redesign

### Layout

Replace the current full-width stacked lobby with a **two-panel layout**:

```
┌──────────────────────────────────────────────┐
│ Sidebar (220px fixed) │ Main content (flex 1) │
│                       │                       │
│  Logo                 │  Join Room strip       │
│  User avatar + stats  │  Section header        │
│  Nav links            │  Tabs                  │
│  ─────────────────    │  Card grid             │
│  Settings             │                        │
│  Google sign-in btn   │                        │
└──────────────────────────────────────────────┘
```

### Sidebar nav links

- Lobby (grid icon) — active state: gold background
- History (clock icon)
- Profile (user icon)
- Favorites (heart icon)
- ── Settings ──
- Language (sun/globe icon)
- Theme picker (inline colour swatches, 5 options)

### Game cards

Each card:
- **Thumbnail (100px tall):** Abstract SVG radial gradient + geometric lines, colour keyed to difficulty/type. No emoji, no photos.
- **Type badge** (bottom-left of thumb): "Turtle Soup" (gold) | "Murder Mystery" (purple)
- **Body:** title, difficulty pill + tag pills, Solo + Create Room buttons
- **Favorite button:** heart icon top-right of card (filled when saved, outline when not). Only shown when logged in.

### Color theme switcher

5 swatches in the sidebar settings section. Selection stored in `localStorage("ai_dm_theme")` and applied as a `data-theme` attribute on `<html>`. CSS vars defined per theme:

| Key     | --bg      | --surface  | --gold   |
|---------|-----------|------------|----------|
| dark    | #0d0d12   | #16161f    | #c4a35a  |
| warm    | #110d08   | #1a1208    | #d4a05a  |
| eerie   | #080d08   | #0f150f    | #6adc6a  |
| cold    | #080d14   | #0e1420    | #60a5fa  |
| natural | #0c100a   | #141a12    | #a3c45a  |

### SVG icon library

Use **Lucide** (`lucide-react` package). Replace all emoji in: sidebar nav, phase bar, upload modals, clue panel, player list, vote panel.

### Responsive

Sidebar collapses to a bottom tab bar on mobile (< 640px). Card grid switches to single column.

---

## 3. Profile Page

**Route:** `/profile`  
**File:** `frontend/src/pages/ProfilePage.tsx`

### Header

- Google avatar (circular, 56px)
- Display name + email
- Member since date
- Stat chips: "N games played" · "N favorites"

### Tabs: Favorites | History

**Favorites tab:**
- Same card grid as lobby
- Heart icon on each card is filled (active)
- Clicking unfavorites (calls `DELETE /api/favorites/...`, removes from list)
- Empty state: "No favorites yet — browse the lobby to save games"

**History tab:**
- Chronological list (newest first)
- Each row: game title, type badge (Turtle Soup / Murder Mystery), player count, date
- Empty state: "No games played yet"

### Favorite button in lobby

- Heart icon (Lucide `Heart`) top-right corner of every game card, visible when logged in
- Filled gold = saved; outline = not saved
- `POST /api/favorites/{type}/{id}` on click; `DELETE` on second click
- Optimistic update (instant UI toggle, revert on API error)

---

## Files Changed / Created

### Backend

| File | Change |
|------|--------|
| `backend/app/auth.py` | New — JWT, user CRUD, favorites, history |
| `backend/app/main.py` | Add auth endpoints, call `init_auth_db()` at startup, log history on room join |
| `backend/app/config.py` | Add `JWT_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` |
| `backend/app/ws.py` | Accept `token` query param instead of `player_name`; reject unauthenticated connections; log room history on join |
| `backend/pyproject.toml` | Add `authlib>=1.3.0` |

### Frontend

| File | Change |
|------|--------|
| `frontend/src/auth.tsx` | New — AuthContext, AuthProvider, useAuth |
| `frontend/src/pages/LoginPage.tsx` | New — login gate |
| `frontend/src/pages/ProfilePage.tsx` | New — favorites + history |
| `frontend/src/App.tsx` | Wrap with AuthProvider, add /profile route, add login gate |
| `frontend/src/api.ts` | Attach Bearer token to all requests; add favorites/history/me API calls |
| `frontend/src/pages/LobbyPage.tsx` | Adopt sidebar layout; card grid; heart buttons; remove manual name input |
| `frontend/src/pages/RoomPage.tsx` | Use `user.name` from auth; pass `token` query param to WebSocket instead of `player_name` |
| `frontend/src/index.css` | Full redesign — sidebar layout, card grid, theme system, Lucide icons |
| `frontend/src/i18n/zh.json` | Add auth/profile/favorites/history keys |
| `frontend/src/i18n/en.json` | Add auth/profile/favorites/history keys |
| `frontend/package.json` | Add `lucide-react` |

---

## Error Cases

| Condition | Handling |
|-----------|----------|
| Google OAuth fails / user denies | Redirect to `/?error=oauth_failed`, LoginPage shows error message |
| JWT expired | `apiFetch` gets 401, `AuthContext` clears token, user sees LoginPage |
| Favorite API fails | Optimistic update reverted, no toast (silent) |
| History logging fails | Swallowed silently — non-critical |

---

## Out of Scope

- WeChat login
- Email/password auth
- Admin panel
- iOS app
