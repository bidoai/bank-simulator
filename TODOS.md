# TODOS — Apex Global Bank Simulator

## P1 — High Priority

### TODO-001: Agent Context Window Management
**What:** Add sliding window or summary-based history pruning to `BankAgent`
**Why:** `BankAgent.history` grows indefinitely. In a long simulation (1+ hour), accumulated messages will approach or exceed Claude's context window, causing API errors or degraded response quality.
**Pros:** Simulation can run indefinitely; agents stay coherent
**Cons:** Pruning strategies have tradeoffs — summarize (preserves meaning, costs tokens) vs. truncate (simple, loses context) vs. sliding window (good balance)
**Context:** The `BankAgent` class (`agents/base_agent.py`) appends every message to `self.history` with no limit. The `speak()` method passes the full history to every API call. Start with a sliding window of last N messages; optionally add a summarization step using a smaller model.
**Effort:** S (human: ~2 days / CC: ~15 min) | **Priority:** P1 | **Depends on:** nothing

---

## P2 — Backlog

### TODO-002: XVA Position Field Mapping
**What:** Complete `XVAAdapter.from_positions()` — map `Position.symbol`, `.quantity`, `.avg_entry_price` to pyxva Trade fields
**Why:** Without this, XVA always shows mock data even when live trades exist in the simulation
**Pros:** Enables live XVA numbers once pyxva integration is unblocked
**Cons:** Blocked on Position schema being finalized and pyxva API being stable
**Context:** `infrastructure/xva/adapter.py` line 25 — `from_positions()` returns `[]` with TODO comment. Also: extend `from_trade()` with float leg, payment dates, day count conventions. Verify `../pyxva` API is stable before implementing.
**Effort:** S (human: ~1 day / CC: ~10 min) | **Priority:** P2 | **Depends on:** pyxva live integration (deferred scope)

### TODO-003: Model Governance AI (Quant Agent Q&A)
**What:** `/api/models/chat` endpoint + chat UI on `models.html` — the Quant agent (Dr. Yuki Tanaka) answers questions about any model card in the registry
**Why:** Transforms a static JSON registry into an interactive SR 11-7 compliance tool. "SR 11-7 compliance with AI" is a genuine fintech product category.
**Pros:** High differentiation, low cost (Quant agent already exists, Observer Q&A pattern from Expansion 4 provides the template)
**Cons:** Requires system prompt engineering for model card Q&A; needs model card JSON to be passed as context
**Context:** `model_docs/registry.json` has 6+ model cards. Pattern: user selects a model, types a question, Quant agent responds with awareness of the card's findings, validation status, and model math. Reuse Observer Q&A endpoint pattern.
**Effort:** S (human: ~3 days / CC: ~15 min) | **Priority:** P2 | **Depends on:** Observer Q&A (Expansion 4)

### TODO-004: BoardroomBroadcaster History Pagination
**What:** Cap `BoardroomBroadcaster._history` in-memory at 1,000 messages; serve older messages from SQLite via a paginated API endpoint
**Why:** Current list grows without bound. At 1KB/message, a 10-hour simulation = ~100MB in memory.
**Pros:** Stable memory usage in long-running simulations
**Cons:** Requires pagination API for dashboard to load history in pages; more complex WebSocket reconnect logic
**Context:** `api/boardroom_broadcaster.py` — `self._history: list` has no size cap. Fix: `if len(self._history) > 1000: self._history = self._history[-1000:]` and write older messages to SQLite. Add `GET /api/boardroom/history?page=N` endpoint for dashboard to load older messages.
**Effort:** S (human: ~1 day / CC: ~10 min) | **Priority:** P2 | **Depends on:** SQLite persistence (Expansion 3)

### TODO-005: pyxva Live XVA Integration
**What:** Wire `XVAAdapter.run_pipeline()` to actual simulation trades. As trades accumulate, CVA/DVA/FVA numbers on the XVA dashboard reflect real trade activity.
**Why:** Makes XVA dashboard quantitatively meaningful, not decorative
**Pros:** Completes the quantitative finance story; makes the product credible to quants
**Cons:** Depends on pyxva API stability (it's a local dep at `../pyxva`); Position schema must be finalized first
**Context:** `infrastructure/xva/adapter.py` — `run_pipeline()` works but `from_positions()` returns `[]`. Fix sequence: (1) complete TODO-002, (2) create a `SimulationXVAService` that calls `XVAAdapter.from_positions(positions)` and `run_pipeline()` on a schedule, (3) cache results in SQLite, (4) serve from `/api/xva/summary`.
**Effort:** M (human: ~1 week / CC: ~30 min) | **Priority:** P2 | **Depends on:** TODO-002, Expansion 3

---

## Not in scope (explicitly deferred)
- Multi-user / auth system (pre-v1)
- Production cloud deployment (pre-v1)
- LICENSE / CONTRIBUTING.md / GitHub Actions CI (5 min each with CC when ready)
- Real-world market data feed integration (Bloomberg/Refinitiv)

---
*Updated by /plan-eng-review on 2026-03-23*

## P1 additions from eng review

### TODO-006: Observer Q&A Endpoint ✅ DONE
**What:** `POST /api/observer/chat` + floating chat widget on all dashboard pages
**Status:** `api/observer_routes.py` is implemented. Remaining: add singleton caching, 30s timeout, and the floating chat widget in all dashboard HTML pages.
**Effort:** S (human: ~1 day / CC: ~15 min) | **Priority:** P1 | **Depends on:** nothing

### TODO-007: Scenario Engine with Live Agent Context Injection
**What:** When a scenario fires, inject market shock as context into the next agent's prompt via `_build_context_prompt()` — agents respond to the shock in character
**Why:** The Feynman moment — watching the trading desk react to a +200bp rate shock in real-time is the most compelling demo; closes the last gap between dashboards and simulation
**Pros:** Makes scenario dashboard live; no new data model needed; shock params already defined in `scenarios_routes.SCENARIOS`
**Cons:** Needs design for interleaving: ongoing meetings vs. triggered scenarios; race condition if scenario fires mid-meeting
**Context:** Add a `ScenarioState` singleton (thread-safe dataclass with current active scenario + shock params). `_build_context_prompt()` in `meeting_orchestrator.py` checks `ScenarioState.active` and appends market conditions to the prompt prefix. `POST /api/scenarios/activate` sets the active scenario. `POST /api/boardroom/start` picks it up on the next meeting. **Note:** ScenarioState is in-memory only — server restart resets it. SQLite already has the historic data; the inconsistency is acceptable for v1.
**Effort:** M (human: ~1.5 weeks / CC: ~45 min) | **Priority:** P1 | **Depends on:** nothing

### TODO-009: Voice TTS — Personality-Matched Agent Speech ✅ DONE
**What:** Each agent gets a distinct voice via Browser SpeechSynthesis API. A `TTSManager` abstraction makes it trivial to swap to ElevenLabs or OpenAI TTS later.
**Why:** Watching 16 agents argue about VaR limits is compelling — *hearing* them argue, each with a distinct voice matching their personality, is a 10x better experience.
**Pros:** Transforms the boardroom into a radio drama; no cost, no backend changes needed for the browser implementation; swap path to premium voices is designed in from day one
**Cons:** Browser voice quality varies by OS; gender/accent hints may not match on all systems (graceful fallback designed in)
**Context:** See "Voice TTS Feature" section in `docs/designs/simulation-platform.md` for full design. Implementation: (1) add `voice_profile` to `_AGENT_REGISTRY` in `api/meeting_orchestrator.py`, (2) add `TTSManager` + `BrowserTTSProvider` + `TTSQueue` to dashboard JS, (3) wire to `agent_turn` WebSocket events in `boardroom.html`, (4) mute toggle in boardroom header. Provider swap to ElevenLabs: add `POST /api/tts` endpoint + `ElevenLabsTTSProvider` JS class, change one config line.
**Effort:** S (human: ~2 days / CC: ~20 min) | **Priority:** P1 | **Depends on:** nothing
**Completed:** v0.1.0.0 (2026-03-23)

### TODO-008: Observer Singleton History Window
**What:** Observer singleton (module-level cached agent in `api/observer_routes.py`) must apply a sliding window of last N=20 messages from the day it's implemented — do not wait for the generic TODO-001.
**Why:** Observer singleton accumulates questions from all users across all sessions. Unlike boardroom agents (reset per meeting), the Observer has one persistent history that will overflow faster. A context window error on the Observer crashes the public Q&A feature.
**Pros:** Keeps Observer available indefinitely; trivial implementation (`self.history = self.history[-40:]` after each speak())
**Cons:** Observer loses memory of questions from >20 turns ago (acceptable trade-off)
**Context:** Implement when the Observer singleton is created in `api/observer_routes.py`. Set `max_history = 40` (20 user + 20 assistant messages). Apply after each `agent.speak()` call before returning the response.
**Effort:** XS (human: ~30 min / CC: ~2 min) | **Priority:** P1 | **Depends on:** Observer singleton implementation
