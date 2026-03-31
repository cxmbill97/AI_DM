# AI DM — Frontend

React + TypeScript + Vite frontend for the AI DM game platform.

## Dev

```bash
pnpm install
pnpm dev        # http://localhost:5173 (proxied to backend at :8000)
```

Vite proxies `/api/*` and `/ws/*` to `http://localhost:8000`, so the backend
must be running for anything to work.

## Key files

| File | Purpose |
|------|---------|
| `src/api.ts` | Typed `fetch()` wrappers for all REST endpoints |
| `src/hooks/useRoom.ts` | WebSocket hook — handles all message types for both game modes |
| `src/pages/LobbyPage.tsx` | Mode selection (海龟汤 / 剧本杀), puzzle/script picker, join room |
| `src/pages/RoomPage.tsx` | Multiplayer room — turtle soup layout + murder mystery 3-column layout |
| `src/components/ScriptCard.tsx` | Character bio + private secret + personal script (MM) |
| `src/components/PhaseBar.tsx` | Phase progress + countdown timer with <30 s warning |
| `src/components/VotePanel.tsx` | Voting UI + animated tally reveal |
