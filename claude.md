# CLAUDE.md

## Commands

```bash
cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0   # LAN-accessible API
cd backend && uv run pytest tests/ -x -v                             # all tests
cd frontend && pnpm dev --host 0.0.0.0                               # LAN-accessible UI
```

## Project Overview

AI-powered game master for multiplayer social deduction games: Turtle Soup (海龟汤)
and Murder Mystery (剧本杀). Supports Chinese and English.

**Completed phases:**

- Phase 1: Single-player turtle soup with pseudo-clue cards
- Phase 2: Multiplayer WebSocket rooms, clue unlock, DM intervention engine
- Phase 3: Collaborative reasoning — VisibilityRegistry, per-player private clues
- Phase 4: Simple 剧本杀 — state machine, multi-agent pipeline (Router/Judge/
  Narrator/Safety), voting, NPC agents

**Next: Phase 5 — English language support + LAN multiplayer access**
Bilingual UI (zh/en toggle). English puzzles and scripts. Other devices on the
same network can join rooms by visiting the host’s LAN IP.

**Core principle: Deterministic State > LLM Output.**

## Architecture

```
backend/
├── app/
│   ├── main.py                 # FastAPI: REST + WebSocket, host=0.0.0.0
│   ├── llm.py                  # MiniMax client via OpenAI SDK
│   ├── models.py               # All Pydantic models
│   ├── puzzle_loader.py        # Load puzzle/script JSON (zh + en)
│   ├── room.py                 # Room manager
│   ├── ws.py                   # WebSocket handler
│   ├── visibility.py           # VisibilityRegistry
│   ├── intervention.py         # DM intervention engine
│   ├── state_machine.py        # Phase state machine
│   ├── voting.py               # Vote collection + resolution
│   ├── npc.py                  # NPC agent
│   ├── agents/
│   │   ├── orchestrator.py     # Pipeline: Router → Judge → Narrator → Safety
│   │   ├── router.py           # Intent classifier (rules, no LLM)
│   │   ├── judge.py            # Truth judgment (sees key_facts, not truth)
│   │   ├── narrator.py         # Response gen (CANNOT see truth)
│   │   └── safety.py           # Leak detection
│   └── dm.py                   # Legacy single-call DM (turtle soup)
├── data/
│   ├── puzzles/
│   │   ├── zh/                 # Chinese turtle soup puzzles
│   │   └── en/                 # [Phase 5] English turtle soup puzzles
│   └── scripts/
│       ├── zh/                 # Chinese murder mystery scripts
│       └── en/                 # [Phase 5] English murder mystery scripts
├── tests/
└── pyproject.toml

frontend/
├── src/
│   ├── App.tsx
│   ├── i18n/                   # [Phase 5] Internationalization
│   │   ├── index.ts            # i18n setup, language detection, toggle
│   │   ├── zh.json             # Chinese UI strings
│   │   └── en.json             # English UI strings
│   ├── components/
│   │   ├── ChatPanel.tsx
│   │   ├── PuzzleCard.tsx
│   │   ├── ScriptCard.tsx
│   │   ├── CluePanel.tsx
│   │   ├── PrivateCluePanel.tsx
│   │   ├── ProgressBar.tsx
│   │   ├── PlayerList.tsx
│   │   ├── PhaseBar.tsx
│   │   ├── VotePanel.tsx
│   │   └── LanguageToggle.tsx  # [Phase 5] zh/en switch button
│   ├── hooks/
│   ├── pages/
│   └── api.ts                  # Uses relative URLs (works on any host)
└── vite.config.ts              # proxy + host=0.0.0.0
```

## Key Concepts (updated for Phase 5)

1-6: Same as v6 (VisibilityRegistry, Intervention, State Machine, Multi-Agent,
Voting, NPC). All still apply.

1. **[Phase 5] Bilingual Support (zh/en):**
- UI strings: i18n JSON files, toggle component. No hardcoded Chinese in .tsx.
- Game content: separate puzzle/script directories per language (data/puzzles/zh/,
  data/puzzles/en/). Puzzles load by language prefix.
- DM prompts: Narrator system prompt switches language based on room setting.
  Judge + Safety work language-agnostic (they deal with facts, not prose).
- Room has a `language: "zh" | "en"` field set on creation.
1. **[Phase 5] LAN Access:**
- Backend: `uvicorn --host 0.0.0.0` exposes on all network interfaces.
- Frontend: `vite dev --host 0.0.0.0` + relative API URLs (no hardcoded localhost).
- Room sharing: display `http://{LAN_IP}:5173/room/{room_id}` as join link.
- No auth, no HTTPS — this is local/LAN only, not public internet.

## Things That Will Bite You (Phase 5 additions)

- **api.ts must use relative URLs.** `fetch("/api/chat")` not
  `fetch("http://localhost:8000/api/chat")`. The Vite proxy handles routing.
  If any URL is hardcoded to localhost, other devices cannot reach the backend.
- **Vite proxy only works in dev mode.** For production build (pnpm build),
  you need either: (a) serve frontend from FastAPI static files, or (b) set
  up a reverse proxy. For LAN demo, dev mode with –host is sufficient.
- **WebSocket URL must also be relative or use the current hostname.**
  `new WebSocket(\`ws://${window.location.host}/ws/${roomId}`)`— NOT`ws://localhost:8000/ws/…`. This is the #1 bug when going from localhost
  to LAN.
- **i18n: DM narration language depends on room setting, not browser locale.**
  All players in a room get the same language DM. Mixed-language rooms not supported.
- **English puzzles must be original or properly attributed.** Classic lateral
  thinking puzzles (albatross soup, etc.) are public domain. Murder mystery
  scripts should be original.
- **All previous “Things That Will Bite You” still apply.** Especially: truth
  never in Narrator prompt, state machine transitions pure, is_culprit stripped.

## Design Decisions Log (updated)

All previous decisions still apply, plus:

- **i18n via JSON files, not a framework like react-i18next:** We have <100 UI
  strings. A simple useLanguage() hook + JSON import is lighter than adding a
  dependency. Can upgrade to react-i18next later if string count grows.
- **LAN access via 0.0.0.0 binding, not tunneling (ngrok/cloudflare):** This is
  for local playtesting with friends, not public deployment. Zero setup, zero cost.
  For public demo, deploy to a cloud VM later.
- **Separate content directories per language (not one file with translations):**
  Puzzles are creative content, not 1:1 translations. English puzzles may differ
  entirely from Chinese ones. Keeping them separate is cleaner.