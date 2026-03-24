# Changelog

All notable changes to Apex Global Bank Simulator are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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

