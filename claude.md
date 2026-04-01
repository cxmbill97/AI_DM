# CLAUDE.md

## Commands

```bash
cd backend && uv run uvicorn app.main:app --reload --host 0.0.0.0   # API (port 8000)
cd backend && uv run pytest tests/ -x -v                             # all tests
cd backend && uv run python -m eval.run --scenarios 50               # eval harness
cd backend && uv run python -m mcp_server                            # MCP server (stdio)
cd frontend && pnpm dev --host 0.0.0.0                               # UI (port 5173)
./start.sh                                                            # one-command startup
```

## Project Overview

AI-powered game master for multiplayer social deduction games: Turtle Soup (海龟汤)
and Murder Mystery (剧本杀). Bilingual (zh/en). Multi-agent architecture with
minimum-privilege context isolation.

**Completed phases:**

- Phase 1: Single-player turtle soup
- Phase 2: Multiplayer + clue system + DM intervention
- Phase 3: VisibilityRegistry + per-player private clues
- Phase 4: 剧本杀 + multi-agent pipeline + voting + NPC
- Phase 5: Bilingual (zh/en) + LAN access
- Phase 6: Remote access (ngrok/cloudflare) + demo packaging

**Next: Phase 7 — Observability, Evaluation, MCP**
Three additions that make the agent system inspectable, measurable, and interoperable:

1. Agent Trace: per-message decision trace visible in frontend
1. Eval Harness: automated scoring with markdown report output
1. MCP Server: expose game engine as MCP tools for any compatible client

**Core principle: Deterministic State > LLM Output.**

## Architecture

```
backend/
├── app/
│   ├── main.py
│   ├── llm.py
│   ├── models.py
│   ├── puzzle_loader.py
│   ├── room.py
│   ├── ws.py
│   ├── visibility.py
│   ├── intervention.py
│   ├── state_machine.py
│   ├── voting.py
│   ├── npc.py
│   ├── agents/
│   │   ├── orchestrator.py     # Pipeline + trace collection
│   │   ├── router.py
│   │   ├── judge.py
│   │   ├── narrator.py
│   │   ├── safety.py
│   │   └── trace.py            # [Phase 7] TraceStep, AgentTrace dataclasses
│   └── dm.py
├── eval/                        # [Phase 7] Evaluation harness
│   ├── __main__.py              # CLI entry: python -m eval.run
│   ├── scenarios.py             # EvalScenario dataclass + loader
│   ├── runner.py                # Run scenarios against agents, collect results
│   ├── report.py                # Generate markdown report from results
│   ├── data/
│   │   ├── judge_scenarios.json     # 50+ (question, expected_judgment) pairs
│   │   └── redteam_scenarios.json   # 50+ adversarial prompts
│   └── reports/                 # Generated reports (gitignored except examples)
│       └── .gitkeep
├── mcp_server/                  # [Phase 7] MCP Server
│   ├── __main__.py              # Entry: python -m mcp_server
│   └── server.py                # FastMCP server with game tools
├── data/
│   ├── puzzles/{zh,en}/
│   └── scripts/{zh,en}/
├── tests/
│   ├── ...existing tests...
│   ├── test_trace.py            # [Phase 7] Trace collection tests
│   ├── test_eval.py             # [Phase 7] Eval harness tests
│   └── test_mcp.py              # [Phase 7] MCP server tool tests
└── pyproject.toml

frontend/
├── src/
│   ├── components/
│   │   ├── ...existing components...
│   │   └── TracePanel.tsx       # [Phase 7] Expandable agent decision trace
│   └── ...
└── ...
```

## Key Concepts

1-9: Same as v8. All implemented and tested.

1. **[Phase 7] Agent Trace:**
   Each player message produces an AgentTrace — a list of TraceSteps recording
   every agent’s input, output, latency, and token usage. Traces are:
- Returned in WebSocket/REST responses (optional field, hidden by default)
- Displayed in a collapsible TracePanel in the frontend
- Stored in game_events for replay
- Used by the eval harness for automated scoring
   
   ```python
   @dataclass
   class TraceStep:
       agent: str          # "router" | "judge" | "narrator" | "safety"
       input_summary: str  # truncated input for display (no secrets)
       output_summary: str # truncated output
       latency_ms: float
       tokens_in: int
       tokens_out: int
       metadata: dict      # agent-specific: judgment, confidence, matched_facts, etc.
   
   @dataclass
   class AgentTrace:
       message_id: str
       player_id: str
       steps: list[TraceStep]
       total_latency_ms: float
       total_tokens: int
       total_cost: float   # calculated from provider pricing
   ```
   
   IMPORTANT: TraceStep.input_summary for Judge must NOT include raw key_facts
   or truth. Show only: “key_facts: 5 items” or similar. The trace is visible
   to players in debug mode — it must not leak secrets.
1. **[Phase 7] Eval Harness:**
   Offline batch evaluation. Loads scenarios from JSON, runs them through agents,
   computes metrics, outputs markdown report.
   
   Metrics:
- Judge accuracy: exact match against expected_judgment
- Leakage rate: % of adversarial prompts where key_facts appear in output
- Safety catch rate: % of leaks caught by Safety Agent
- End-to-end leak rate: leaks that escape the full pipeline
- Latency: P50/P95 per agent and total
- Cost: per-scenario and projected per-session
   
   CLI: `python -m eval.run --scenarios 50 --provider minimax`
   Output: `eval/reports/{provider}_{date}.md`
1. **[Phase 7] MCP Server:**
   Exposes the game engine as MCP tools via stdio transport. Any MCP-compatible
   client (Claude Desktop, Cursor, custom agent) can play the game.
   
   Tools:
- list_puzzles(language) → [{id, title}]
- list_scripts(language) → [{id, title}]
- start_game(puzzle_id | script_id, language, player_name) → {session_id, surface}
- ask_question(session_id, question) → {judgment, response, clue_unlocked, trace}
- get_status(session_id) → {phase, progress, unlocked_clues, players}
- cast_vote(session_id, target_character_id) → {result}
   
   Uses FastMCP library. Single-player mode only (no WebSocket multiplayer via MCP).
   The MCP server is a thin wrapper around existing game logic — no new game code.

## Things That Will Bite You (Phase 7 additions)

- **Trace input_summary must be sanitized.** Players can toggle trace view in the
  frontend. If Judge’s input_summary contains key_facts text, you’ve leaked secrets
  via the debug panel. Show counts and IDs, not content.
- **Eval harness must use real LLM calls, not mocks.** The whole point is measuring
  actual provider behavior. Mark eval tests as slow, don’t run in normal CI.
- **Eval scenarios need deterministic structure.** Each scenario has ONE correct
  expected_judgment. Ambiguous questions (where “是” and “部分正确” are both
  defensible) should be excluded or marked as “flexible” with multiple accepted answers.
- **MCP stdio transport blocks.** The MCP server runs as a separate process, not
  inside the FastAPI server. It imports game logic but has its own entry point.
- **FastMCP requires Python 3.10+.** Should be fine (we’re on 3.12).
- **All previous caveats still apply.**

## Design Decisions Log (updated)

All previous decisions still apply, plus:

- **Trace as dataclass, not OpenTelemetry:** Our trace is game-specific (agent steps,
  not HTTP spans). OTel adds dependency weight and conceptual overhead. A simple
  dataclass serialized to JSON is more readable and directly useful in the frontend.
- **Eval harness as a Python module, not a separate tool:** `python -m eval.run` keeps
  it in the same repo with direct imports of agent code. No need for a separate
  eval framework.
- **MCP single-player only:** Multiplayer requires WebSocket state management that
  doesn’t map cleanly to MCP’s request-response tool model. MCP serves as a
  “play via any AI client” mode, not a replacement for the web UI.