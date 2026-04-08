# AI DM — Product Roadmap

This roadmap outlines the planned evolution of AI DM from core gameplay validation through a production-ready, monetized platform.

---

## Phase 0: Core Validation (MVP Gameplay)

**Goal:** Validate whether "Lateral Thinking Puzzle (Sea Turtle Soup) + turn-based speaking" is fun

### Core Features
- Implement a minimal puzzle pool (predefined questions)
- Multiplayer rooms (2–6 players)
- Turn-based speaking system (30 seconds per player)
- Timeout handling (no response after 20s → allow hint or skip)
- Basic answer evaluation (host or simple system judgment: relevant / irrelevant / close)

### Core Game Flow
- Create room / join room
- Game start → turn-based Q&A → game end
- Basic win condition (player who solves the puzzle wins)

---

## Phase 1: Gameplay Improvements

**Goal:** Make the game engaging and prevent stagnation

### Mechanics Enhancements
- Hint system (limited usage)
- Skip system (vote to skip)
- Spectator mode (increase social engagement)

### Anti-Disruption Mechanisms (Important)
- Prevent experienced players from ruining gameplay:
  - Hide puzzle sources
  - Player reporting system
  - Simple AI-based anomaly detection for suspicious answers

---

## Phase 2: Lightweight AI Integration

**Goal:** Use AI as an assistive layer, not a core dependency

### AI Features
- AI-assisted answer evaluation (relevant / irrelevant / close)
- Per-turn performance scoring
- MVP selection (based on answer quality + solving outcome)

---

## Phase 3: Visual & Social Layer

**Goal:** Improve retention and user engagement

### Avatar System
- Player avatars
- Turn highlight (focus on active player)
- Basic animations (correct / incorrect feedback)

### UI Style
- Cartoon / stylized UI
- Basic emotes or expressions

---

## Phase 4: Economy System (Monetization Foundation) ✅ Complete

**Goal:** Introduce gacha + cosmetics

### Core Economy
- In-game currency (earned via matches)
- Basic shop (cosmetics)

### Gacha System
- Randomized character / cosmetic pulls
- Rarity tiers (R / SR / SSR)
- Pity system (guaranteed rewards over time)

---

## Phase 5: Pet + AI System (Differentiation Layer)

**Goal:** Build unique gameplay features

### Pet System
- Pet progression (levels / experience)
- Bring pets into matches

### Pet Abilities
- Provide hints (limited uses)
- Different pets have different abilities

### LLM-powered Pets
- Each pet uses a lightweight model
- No access to other players' information (fairness constraint)
- Upgrades improve reasoning / hint quality

---

## Phase 6: UGC + Content Ecosystem

**Goal:** Scale content through users

### UGC Features
- User-generated puzzle submission
- Moderation system (AI + manual)
- Rating / upvote system

### Dynamic Difficulty
- Match puzzles based on player skill level
- Prioritize high-rated content

### Content Governance
- Periodic removal of low-rated puzzles
- Reporting and blacklist system

---

## Phase 7: Retention Systems

**Goal:** Encourage recurring usage

### Task System
- Daily tasks
- Weekly tasks
- Monthly events

### Reward Systems
- Login rewards
- Streak rewards
- Leaderboards (lightweight implementation)

---

## Phase 8: Advanced Systems

**Goal:** Transition from demo to production-ready product

### Advanced AI
- Improved semantic answer evaluation
- Automatic puzzle generation

### Matchmaking
- Skill-based player matching
- New player protection

### Real-time Infrastructure
- WebSocket-based synchronization
- Latency optimization

---

## Summary: Core Execution Path

> Validate gameplay → Turn-based interaction + scoring → Avatars + animations → Gacha cosmetics (monetization) → Pet + LLM system (differentiation) → UGC ecosystem (scalability)

## Key Recommendations

1. **Do not start with LLM-based pets** — high cost and complexity, low validation value. Defer to Phase 5.
2. **The single most critical validation point:** whether turn-based lateral thinking gameplay is actually engaging.
3. **Monetization path is straightforward:** Gacha + cosmetics + avatars is a proven model.
