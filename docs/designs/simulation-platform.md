# Design: Apex Global Bank — Live Simulation Platform

*Generated from /plan-ceo-review on 2026-03-22. Branch: main. Mode: SCOPE EXPANSION.*

---

## Vision

### The 10x Version
A live, publicly accessible AI banking simulation that runs 24/7. Sixteen AI agents managing
a fictional $2T bank in real-time, reacting to market events, making decisions that move the
simulated balance sheet. Anyone opens a browser and watches JPMorgan-scale banking happen
right now — with an AI narrator explaining every Greek letter, every regulatory decision,
every tension between the CRO and the Lead Trader. Finance students use it as a textbook.
Banks use it for training. AI researchers study it as a multi-agent coordination benchmark.

### Platonic Ideal Experience
Open a URL. See a beautiful dashboard. The Observer narrates what's happening right now.
Click "stress test" and watch GFC 2008 replay in accelerated time. Every agent reacts
authentically. The CFO and CRO argue. The Trading Desk hedges. The CEO makes a capital
allocation call. Banking becomes legible to humans who've never held a Bloomberg terminal.

---

## Current State vs. Target

> **Note (updated 2026-03-23 by /plan-eng-review):** Several "Target State" items are already built. Strikethrough = done.

```
CURRENT STATE                    TARGET STATE (this plan)
─────────────────────────────    ──────────────────────────────────────────────
CLI simulation works             Simulation drives dashboard via WebSocket
  16 agents, 1 scenario            Events persist to SQLite
  No error recovery                Retry wrapper on all Anthropic calls

API layer (mock data)            API reads live simulation state
  Trading, XVA, Models, etc.       (no data_source flag — one-shot migration)

Dashboards (hardcoded data)      Dashboards update in real-time
  6 beautiful but inert pages      Observer chat widget on every page

~~All logs → /dev/null~~         ~~Structured logs to stderr (BANK_LOG=1)~~
~~[DONE: api/main.py:18-30]~~

~~No Observer Q&A~~              ~~POST /api/observer/chat~~
~~[DONE: api/observer_routes.py]~~

~~No SQLite for meetings~~       ~~SQLite persistence (meetings + turns)~~
~~[DONE: api/meeting_store.py]~~

No tests                         Integration tests + mocked Anthropic client
  (only broadcaster + store)       test_base_agent, test_observer_routes,
                                   test_scenario_state, conftest.py fixtures
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                  SimulationEngine (background thread)         │
│  MarketDataFeed (GBM) · Boardroom · 16 Agents · Observer     │
└──────────────────────────┬───────────────────────────────────┘
                           │ events: agent_msg, market_tick,
                           │         trade, risk_update
                           ▼
┌──────────────────────────────────────────────────────────────┐
│               SimulationBridge (asyncio Queue)               │
│  sync → async bridge · SQLite persistence (aiosqlite)        │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                FastAPI Web Server (api/)                      │
│  Existing route files + NEW: /api/observer/chat              │
│  WebSocket /ws/boardroom (already exists)                    │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│             Static HTML Dashboards (dashboard/)              │
│  Live via WebSocket + polling · Observer chat widget         │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                  SQLite (simulation.db)                      │
│  sessions · agent_messages · trades · market_snapshots       │
│  risk_metrics                                                │
└──────────────────────────────────────────────────────────────┘
```

**Key architectural decisions:**
- Simulation runs in a background thread (not async) — agents are sync, web server is async
- Bridge: `asyncio.run_coroutine_threadsafe()` to push events from sim thread → event loop
- Market shocks injected as system context update (not conversation messages)
- `BANK_LOG=1` env var enables structured logging to stderr

---

## Accepted Scope

| # | Feature | Effort (CC) | Status |
|---|---------|-------------|--------|
| 1 | Live Simulation Bridge | ~30 min | ACCEPTED |
| 2 | Scenario Engine with Real Market Triggers | ~45 min | ACCEPTED |
| 3 | Persistent Simulation State (SQLite) | ~30 min | ACCEPTED |
| 4 | Interactive Observer Q&A | ~15 min | ACCEPTED |

## Deferred

| Feature | Why deferred |
|---------|-------------|
| Model Governance AI (Quant Q&A) | Non-core; implement after Observer Q&A pattern established |
| Pyxva Live Integration | Blocked on Position schema lock + pyxva API stability |

---

## Build Order

> **Updated by /plan-eng-review (2026-03-23).** Steps 1, 4, 5 are done. SimulationBridge removed — extend `boardroom_worker.py` instead. Schema before tests per outside voice. Mock migration is one-shot not incremental.

1. ~~Fix `BANK_LOG` env var + stderr logging~~ **[DONE — api/main.py]**
2. Add `pytest`, `pytest-asyncio` to `requirements.txt`; create `tests/conftest.py` with `MockAnthropicClient` (configurable failures, delays, rate limits) + `mock_sleep` fixture
3. Retry wrapper in `BankAgent.speak()` — exponential backoff, 3 retries, 30s hard timeout; non-transient errors (AuthenticationError, PermissionDeniedError) skip retries immediately → `tests/test_base_agent.py`
4. ~~`SimulationBridge`~~ **[REMOVED — extend boardroom_worker.py instead]**
5. ~~SQLite schema~~ **[DONE for meetings/turns — api/meeting_store.py]**; extend schema: add trades, market_snapshots, risk_metrics tables
6. Observer singleton — lazy-init module-level cached agent in `api/observer_routes.py`; `asyncio.wait_for(timeout=30)`; apply history window (last 40 messages per TODO-008) → `tests/test_observer_routes.py`
7. `ScenarioState` singleton + `_build_context_prompt` shock injection → `tests/test_scenario_state.py`
8. Extend `boardroom_worker.py` for continuous simulation: GBM market tick loop as independent `asyncio.create_task()` (decoupled from agent calls — market clock never stalls waiting on Anthropic)
9. Replace all mock API routes with live SQLite reads — one-shot migration (not incremental; no `data_source` flag); also consolidate `sample_config()` duplication between `api/xva_routes.py` and `infrastructure/xva/adapter.py`
10. Observer chat widget — floating `position: fixed; bottom: 1rem; right: 1rem` on all 6 dashboard HTML pages
11. Commit all untracked work (api/, dashboard/, infrastructure/xva/, model_docs/)

**Deployment constraint:** Run uvicorn with `--workers 1` until mode is moved from `global _MODE` in `boardroom_routes.py` to SQLite. Multi-worker deploys will have inconsistent mode state.

---

## Critical Issues to Fix First

1. **`BankAgent.speak()` has no error handling** — one API timeout crashes the entire simulation
2. ~~**All structured logs go to `/dev/null`**~~ — **DONE** (`api/main.py:18-30`)
3. **Two copies of `sample_config()`** — fixed in step 9 (one-shot migration)
4. **Mock data indistinguishable from live data** — fixed in step 9 (one-shot migration, no flag)

---

## Voice TTS Feature

### Design

Each agent gets a **personality profile** — not a hardcoded OS voice name, but characteristics the browser uses to find the closest match. This makes it portable across macOS/Windows/Linux and trivially swappable to ElevenLabs or OpenAI TTS later.

```
┌──────────────────────────────────────────────────────────┐
│              boardroom.html (dashboard)                   │
│                                                           │
│  broadcast_agent_turn event                               │
│       │                                                   │
│       ▼                                                   │
│  TTSManager.speak(text, agentName)                        │
│       │                                                   │
│       ├─► TTSQueue (serialises turns — no overlap)        │
│       │                                                   │
│       └─► TTSProvider (interface)                         │
│               │                                           │
│               ├─► BrowserTTSProvider   ← active now       │
│               │     window.speechSynthesis                 │
│               │     SpeechSynthesisUtterance               │
│               │                                           │
│               ├─► ElevenLabsTTSProvider ← future swap     │
│               │     POST /api/tts → audio stream          │
│               │                                           │
│               └─► OpenAITTSProvider    ← future swap      │
│                     POST /api/tts → audio stream          │
└──────────────────────────────────────────────────────────┘
```

### Voice personality profiles (added to `_AGENT_REGISTRY`)

| Agent | Gender | Accent | Rate | Pitch | Rationale |
|-------|--------|--------|------|-------|-----------|
| Alexandra Chen (CEO) | female | en-US | 1.00 | 1.05 | Authoritative, clear |
| Dr. Priya Nair (CRO) | female | en-GB | 0.85 | 0.95 | Measured, serious |
| Diana Osei (CFO) | female | en-US | 0.95 | 1.00 | Precise, steady |
| Amara Diallo (Treasury) | female | en-US | 0.90 | 1.00 | Calm, analytical |
| Sarah Mitchell (Compliance) | female | en-US | 0.90 | 1.05 | Careful, deliberate |
| Isabella Rossi (Wealth) | female | en-US | 1.05 | 1.10 | Warm, personable |
| Dr. Fatima Al-Rashid (CDO) | female | en-US | 0.95 | 1.00 | Technical, confident |
| James Okafor (Trader) | male | en-US | 1.15 | 1.00 | Fast, energetic |
| Marcus Rivera (CTO) | male | en-US | 1.05 | 1.05 | Casual, enthusiastic |
| Robert Adeyemi (Credit) | male | en-GB | 0.90 | 0.95 | Deliberate, weighty |
| Dr. Yuki Tanaka (Quant) | male | en-US | 1.00 | 1.10 | Precise, slightly rapid |
| Chen Wei (Operations) | male | en-US | 0.95 | 0.95 | Methodical, even |
| Sophie Laurent (IBD) | female | en-GB | 1.05 | 1.05 | Polished, persuasive |
| Ivan Petrov (CISO) | male | en-US | 0.85 | 0.90 | Low, serious |
| Head of IBD | male | en-US | 1.00 | 1.00 | Standard |
| The Observer | male | en-US | 0.88 | 0.92 | Thoughtful, unhurried narrator |

### Browser voice selection algorithm

```javascript
function pickVoice(profile, availableVoices) {
  // Priority: accent match + gender keyword in name
  const genderHints = { female: ['female','zira','samantha','karen','victoria'],
                        male:   ['male','daniel','alex','thomas','fred'] };
  const hints = genderHints[profile.gender] || [];

  return availableVoices.find(v =>
    v.lang.startsWith(profile.accent) &&
    hints.some(h => v.name.toLowerCase().includes(h))
  ) || availableVoices.find(v => v.lang.startsWith(profile.accent))
    || availableVoices.find(v => v.lang.startsWith('en'))
    || availableVoices[0]; // absolute fallback
}
```

### Implementation steps (new build step 10b)

1. Add `voice_profile: {gender, accent, rate, pitch}` to each entry in `_AGENT_REGISTRY` (`api/meeting_orchestrator.py`)
2. `GET /api/boardroom/agents` already returns agent data — voice_profile included automatically
3. Add `TTSManager` class to `dashboard/shared.js` (or inline in `boardroom.html`):
   - `TTSQueue` — serialises utterances so agents never speak simultaneously
   - `BrowserTTSProvider` — wraps `window.speechSynthesis`
   - Provider swap point: `new TTSManager({ provider: 'browser' })`
4. In `boardroom.html` WebSocket handler: on `agent_turn` message, call `tts.speak(msg.text, msg.agent)`
5. UI controls: mute toggle (🔇/🔊) in the boardroom header; per-turn speaker icon

### Swap path to ElevenLabs / OpenAI TTS

When ready to upgrade:
1. Add `POST /api/tts` endpoint that accepts `{text, voice_id}` and proxies to provider
2. Implement `ElevenLabsTTSProvider` / `OpenAITTSProvider` in dashboard JS
3. Change `new TTSManager({ provider: 'elevenlabs' })` — one line change
4. Map each agent's `voice_profile.accent + gender` to a provider-specific voice_id

---

## Open TODOs (see TODOS.md for full detail)

- **P1** TODO-001: Agent context window management (history pruning)
- **P1** TODO-008: Observer singleton history window (apply on implementation day)
- **P1** TODO-009: Voice TTS — personality-matched speech per agent
- **P2** TODO-002: XVA Position field mapping
- **P2** TODO-003: Model governance AI (Quant Q&A)
- **P2** TODO-004: Broadcaster history pagination (cap at 1,000 in-memory)
- **P2** TODO-005: pyxva live XVA integration

---

*Eng review complete — ready to implement.*

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | CLEAR (prior session) | SCOPE EXPANSION mode, 4 expansions accepted |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | issues_found | Outside voice via Claude subagent — tick decoupling + circuit breaker gaps found |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 8 issues found, all resolved; 18 test gaps → full suite added; build order corrected |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |

**UNRESOLVED:** 0 unresolved decisions
**VERDICT:** ENG CLEARED — ready to implement. Run `/plan-design-review` before implementing the Observer chat widget UI if visual polish matters.
