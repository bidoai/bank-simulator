# Changelog

All notable changes to Apex Global Bank Simulator are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.2.0.0] - 2026-03-25

### Added
- **OMS + Trade Execution Pipeline**: end-to-end demo — click a button → fill at mid price → Greeks → VaR before/after → live dashboard update (`infrastructure/trading/oms.py`, `api/oms_routes.py`)
- **GreeksCalculator**: Black-Scholes for equity options, DV01 for bonds/IRS, delta-1 for equities and FX; aggregates per-book and portfolio greeks on demand (`infrastructure/trading/greeks.py`)
- **TradingBroadcaster**: WebSocket singleton for `/ws/trading` pushing fill, tick, and positions events to the trading dashboard (`api/trading_broadcaster.py`)
- **MarketDataFeed subscription**: ticks now mark-to-market all positions and broadcast live price updates to connected clients
- **SQLite OMS persistence**: every filled order is written to `data/oms_trades.db` via aiosqlite in a fire-and-forget background task
- **New agents**: Jordan Pierce (Internal Audit), Margaret Okonkwo (General Counsel), Dr. Samuel Achebe (Model Validation Officer), plus CDO/CISO/Ops/risk-desk stubs
- **Risk engines**: two-regime correlation model, SA RWA regulatory capital, concentration risk monitor (`infrastructure/risk/`)
- **Credit & Compliance modules**: IFRS 9 ECL engine (Stage 1/2/3 classification), AML transaction monitor with pattern detection (`infrastructure/credit/`, `infrastructure/compliance/`)
- **Treasury modules**: FTP engine (tenor-matched swap rates), ALM engine (NII/EVE sensitivity and duration gap) (`infrastructure/treasury/`)
- **Infrastructure foundation**: event log, instrument master reference data, position snapshots, API metrics (`infrastructure/events/`, `infrastructure/reference/`, `infrastructure/metrics/`, `infrastructure/persistence/`)
- **Consulting scenario**: Meridian Consulting advisory board meeting with full scenario script (`agents/consulting/`, `scenarios/consulting_review_meeting.py`)
- **Shared navigation**: universal fixed navbar injected by `dashboard/shared_nav.js` across all 6 dashboard pages; brand click navigates to home

### Changed
- Trading dashboard (`dashboard/trading.html`): replaced mock hardcoded data with live OMS; added 6 demo trade buttons, manual trade form, confirmation modal with Greeks + VaR before/after; WebSocket-driven updates (30s polling fallback)
- `api/main.py`: lifespan now starts MarketDataFeed, wires OMS, subscribes tick callbacks, initialises all new infrastructure singletons; oms_routes registered before trading_routes for endpoint shadowing
- `infrastructure/market_data/feed_handler.py`: added NVDA and US2Y to SEED_PRICES; `stop()` made async

### Fixed
- `api/oms_routes.py`: `_DB_PATH` changed from relative string to absolute `Path(__file__)` anchor
- `infrastructure/trading/oms.py`: ZeroDivisionError guard when `hard_limit == 0`; `_fills` list capped at 1,000 entries
- `api/trading_broadcaster.py`: `broadcast_positions` now uses independent `_last_positions` throttle (was sharing `_last_tick`, suppressing tick messages when positions were broadcast)
- `.gitignore`: added `.DS_Store` rule; untracked stale `.DS_Store` from repo root

---

## [0.1.1.0] - 2026-03-24

### Added
- 18 new tests for boardroom API routes (`tests/test_boardroom_routes.py`) covering all endpoints and `_auto_title()` helper

### Changed
- `api/main.py`: replaced deprecated `@app.on_event("startup")` with FastAPI `lifespan` context manager
- `api/meeting_orchestrator.py`: capped `_build_context_prompt()` transcript to last 20 turns (TODO-001 partial fix — prevents unbounded context growth)

### Fixed
- `api/boardroom_broadcaster.py`: `connect()` now replays history before adding client to the broadcast set, preventing out-of-order message delivery on join

---

## [0.1.0.0] - 2026-03-23

### Added
- FastAPI backend (`api/`) with boardroom, observer, trading, XVA, models, and scenarios routes
- WebSocket boardroom broadcaster with in-memory history and dead-client pruning (`api/boardroom_broadcaster.py`)
- SQLite-backed meeting store with WAL mode, per-connection isolation, and full pagination (`api/meeting_store.py`)
- Multi-agent boardroom orchestrator streaming token-by-token via thread pool + asyncio queue (`api/meeting_orchestrator.py`)
- Observer Q&A endpoint (`POST /api/observer/chat`) — ask the Independent Narrator anything about the simulation
- Boardroom Claude Code mode: queue-based meeting flow with `inject-turn` endpoint for assistant-driven sessions
- Voice TTS feature in `dashboard/boardroom.html`: personality-matched speech per agent via Browser SpeechSynthesis API
  - `BrowserTTSProvider` with gender/accent/rate/pitch voice selection algorithm
  - `TTSManager` with single swap-point for future ElevenLabs or OpenAI TTS upgrade
  - Mute toggle (🔊/🔇) in boardroom header; auto-hides on unsupported browsers
  - 9 agent voice profiles added to `_AGENT_REGISTRY` in `api/meeting_orchestrator.py`
  - `voice_profile` now returned by `GET /api/boardroom/agents`
- 85 tests across 4 test files (broadcaster, meeting store, orchestrator, observer routes)
- `tests/conftest.py` with `MockAnthropicClient` fixture (configurable responses/failures)

### Changed
- Updated `docs/designs/simulation-platform.md`: corrected current-state table, added Voice TTS design section, revised build order (SimulationBridge removed, schema before tests), added deployment constraint note
- `TODOS.md`: TODO-006 marked done, added TODO-008 (Observer history window, P1) and TODO-009 (Voice TTS swap path, P1)
- `requirements.txt`: added `pytest>=7.0`, `pytest-asyncio>=0.23`

### Fixed
- `boardroom_routes.py`: `get_history()` now returns a copy of `_history` (not a live reference)
- `meeting_orchestrator.py` + `observer_routes.py`: replaced deprecated `asyncio.get_event_loop()` with `asyncio.get_running_loop()` (Python 3.12 compatibility)
- `boardroom_routes.py`: `list_agents()` now includes `voice_profile` in each agent entry
- `boardroom.html`: `esc()` HTML-escape function now encodes single quotes (`'` → `&#39;`), fixing XSS in `onclick` interpolation
- `boardroom.html`: WebSocket ping `setInterval` is now cleared on each reconnect, preventing interval accumulation across disconnects

