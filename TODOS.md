# TODOS — Apex Global Bank Simulator

## P1 — High Priority

### TODO-001: Agent Context Window Management ✅ DONE
**What:** Add sliding window or summary-based history pruning to `BankAgent`
**Context:** `BankAgent.__init__` now accepts `max_history: int = 0` (0 = unlimited, backward compatible). After each `speak()` / `stream_speak()`, history is trimmed to the last `max_history` messages. Observer singleton hardcodes 40 messages (20 turns). Orchestrator transcript context was already capped at 20 turns.
**Completed:** v0.1.1.0

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

### TODO-010: Risk Integration Layer ✅ DONE
**What:** `RiskService` + `CounterpartyRegistry` + `/api/risk/*` endpoints — closes the control loop between PositionManager, VaRCalculator, and LimitManager
**Context:** Three new files: `infrastructure/risk/risk_service.py` (wires all three systems, runs MC VaR per desk, updates limits), `infrastructure/risk/counterparty_registry.py` (formal counterparty data with ratings, ISDA flags, PFE limits), `api/risk_routes.py` (7 REST endpoints: snapshot, limits, counterparties, positions, on-demand VaR). Decided in market risk boardroom session 2026-03-24.
**Completed:** v0.1.2.0

### TODO-011: Greeks Pipeline (DV01, Vega, CS01) — P2
**What:** Pricer layer between PositionManager and risk metrics. DV01 for fixed income, Black-Scholes Greeks for equity derivatives, CS01 for CDS. Required to make sensitivity limits (DV01 $25M/bp, vega $15M/1%vol) enforceable.
**Effort:** M | **Priority:** P2 | **Depends on:** nothing

### TODO-012: Stressed VaR + FRTB Backtesting — P2
**What:** Historical market data store for 2007-2009 GFC and 2020 COVID windows. Continuous backtesting runner to track IMA exceptions (3 in 250 days triggers revert to Standardised Approach).
**Effort:** M | **Priority:** P2 | **Depends on:** market data feed

### TODO-013: Correlation Regime Model ✅ DONE
**What:** Two correlation matrices (normal / stress regime) with HMM-proxy regime detection from realized cross-asset vol.
**Context:** `infrastructure/risk/correlation_regime.py` — `CorrelationRegimeModel` with 6×6 NORMAL and STRESS Cholesky matrices. Stress regime: equity-equity ~0.90, equity-credit ~-0.80. `var_calculator.py` updated to auto-detect regime; stress VaR materially higher in adverse scenarios.
**Completed:** v0.1.3.0

---

## Phase 1 additions from Meridian Consulting review (v0.1.3.0)

### TODO-014: Infrastructure Foundation ✅ DONE
**What:** Event log, instrument master, position snapshot persistence, API spend metrics
**Context:** `infrastructure/events/event_log.py` — append-only SQLite event log (audit trail). `infrastructure/reference/instrument_master.py` — ISIN/CUSIP/product_type registry seeded with 9 instruments. `infrastructure/persistence/position_snapshots.py` — position state survives process restarts. `infrastructure/metrics/api_metrics.py` — daily spend tracker with $10 alert threshold. `GET /api/metrics/api`, `/api/metrics/api/alert`, `POST /api/metrics/api/reset`.
**Completed:** v0.1.3.0

### TODO-015: New Agents — Internal Audit, General Counsel, Model Validation ✅ DONE
**What:** Three new agents closing critical 3LoD and legal gaps identified by Meridian Consulting.
**Context:** Jordan Pierce (Head of Internal Audit) — independent 3rd line, reports to Audit Committee, adversarial standing. Margaret Okonkwo (General Counsel) — GC/Corporate Secretary, ISDA netting authority, legal entity governance. Dr. Samuel Achebe (Model Validation Officer) — SR 11-7 independence, adversarial to Quant Researcher. CDO, CISO, Operations, and 4 risk desk officer skeletons completed with factory functions.
**Completed:** v0.1.3.0

### TODO-016: Regulatory Capital Engine ✅ DONE
**What:** Basel III Standardised Approach RWA calculation with full capital ratio suite.
**Context:** `infrastructure/risk/regulatory_capital.py` — SA risk weights by product type, CET1/Tier1/Total/Leverage ratios, $45B CET1 capital base, $346B baseline RWA (13% CET1). `GET /api/capital/{snapshot,rwa,ratios,concentration}`, `POST /api/capital/stress`.
**Completed:** v0.1.3.0

### TODO-017: Concentration Risk Monitor ✅ DONE
**What:** Single-name (5%), sector (25%), geography (40%) concentration limit framework with HHI index.
**Context:** `infrastructure/risk/concentration_risk.py` — `ConcentrationRiskMonitor` with breach detection across all three dimensions. Included in `/api/capital/concentration`.
**Completed:** v0.1.3.0

### TODO-018: IFRS 9 ECL Engine ✅ DONE
**What:** Stage 1/2/3 Expected Credit Loss calculation on the loan portfolio.
**Context:** `infrastructure/credit/ifrs9_ecl.py` — Stage 1 = 12m PD×LGD×EAD, Stage 2 = lifetime ECL, Stage 3 = LGD×EAD. 50-obligor sample portfolio, ~1.5-3% ECL coverage ratio. `GET /api/credit/ecl/{portfolio,obligors,stage}`, `POST /api/credit/ecl/scenario`.
**Completed:** v0.1.3.0

### TODO-019: AML Transaction Monitor ✅ DONE
**What:** Rule-based AML screening — 6 rule types, sanctions watchlist, in-memory alert store.
**Context:** `infrastructure/compliance/aml_monitor.py` — sanctions match, large tx ($10M threshold), structuring detection, velocity limits, round number flags, unusual pattern. `GET /api/compliance/aml/{alerts,stats}`, `POST /api/compliance/aml/screen`, `PATCH alerts/{id}`.
**Completed:** v0.1.3.0

### TODO-020: FTP Engine ✅ DONE
**What:** Fund Transfer Pricing — tenor-matched USD swap rate + product liquidity premiums per desk.
**Context:** `infrastructure/treasury/ftp.py` — `SwapCurve` with linear interpolation across 9 tenor points, `DeskFTPCharge` per book_id, `FTPEngine.get_adjusted_pnl()` produces net P&L after funding cost. `GET /api/treasury/ftp/{summary,adjusted-pnl,curve}`.
**Completed:** v0.1.3.0

### TODO-021: ALM Engine ✅ DONE
**What:** Asset-Liability Management — NII/EVE sensitivity, repricing gap schedule, SVB-style warning.
**Context:** `infrastructure/treasury/alm.py` — 7-bucket repricing gap schedule with behavioral deposit model (70% core, 5yr tenor). NII sensitivity: +200bps → +$6.8B (asset-sensitive bank). EVE sensitivity: +200bps → -$26B (-8.8% equity, no SVB warning at current 0.41yr duration gap). `GET /api/treasury/alm/{report,nii-sensitivity,eve-sensitivity,repricing-gap}`.
**Completed:** v0.1.3.0

---

## Phase 2 — Still open (60-180 day plan)

### TODO-022: Legal Entity / Booking Model — P1
**What:** Add `legal_entity_id` foreign key to Trade and Position. Entity registry with jurisdiction, regulatory regime, ISDA flags. Netting set construction at entity level.
**Why:** XVA netting calculations are wrong without entity structure. Required before TODO-005.
**Effort:** M | **Priority:** P1 | **Depends on:** TODO-014 (event log)

### TODO-023: 3LoD Independent Data Layer (CQRS) — P1
**What:** RiskService becomes an independent event consumer, building its own risk position from the canonical event stream rather than sharing PositionManager state with the trading desk.
**Why:** Victoria Ashworth finding: "second line reads from the same data as first line — that is a control failure."
**Effort:** M | **Priority:** P1 | **Depends on:** TODO-014 (event log)

### TODO-024: DFAST/CCAR Stress Testing Framework — P2
**What:** Multi-year forward capital adequacy projection under baseline, adverse, severely adverse scenarios. Uses regulatory_capital engine + scenario generator.
**Effort:** M | **Priority:** P2 | **Depends on:** TODO-016

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

### TODO-007: Scenario Engine with Live Agent Context Injection ✅ DONE
**What:** When a scenario fires, inject market shock as context into the next agent's prompt via `_build_context_prompt()` — agents respond to the shock in character
**Context:** `api/scenario_state.py` — thread-safe `_ScenarioState` singleton with `activate()` / `deactivate()` / `snapshot()`. New endpoints: `POST /api/scenarios/activate`, `DELETE /api/scenarios/activate`, `GET /api/scenarios/active`. `_build_context_prompt()` in `meeting_orchestrator.py` checks `scenario_state.snapshot()` and prepends the active scenario block with human-readable shock descriptions.
**Completed:** v0.1.1.0

### TODO-009: Voice TTS — Personality-Matched Agent Speech ✅ DONE
**What:** Each agent gets a distinct voice via Browser SpeechSynthesis API. A `TTSManager` abstraction makes it trivial to swap to ElevenLabs or OpenAI TTS later.
**Why:** Watching 16 agents argue about VaR limits is compelling — *hearing* them argue, each with a distinct voice matching their personality, is a 10x better experience.
**Pros:** Transforms the boardroom into a radio drama; no cost, no backend changes needed for the browser implementation; swap path to premium voices is designed in from day one
**Cons:** Browser voice quality varies by OS; gender/accent hints may not match on all systems (graceful fallback designed in)
**Context:** See "Voice TTS Feature" section in `docs/designs/simulation-platform.md` for full design. Implementation: (1) add `voice_profile` to `_AGENT_REGISTRY` in `api/meeting_orchestrator.py`, (2) add `TTSManager` + `BrowserTTSProvider` + `TTSQueue` to dashboard JS, (3) wire to `agent_turn` WebSocket events in `boardroom.html`, (4) mute toggle in boardroom header. Provider swap to ElevenLabs: add `POST /api/tts` endpoint + `ElevenLabsTTSProvider` JS class, change one config line.
**Effort:** S (human: ~2 days / CC: ~20 min) | **Priority:** P1 | **Depends on:** nothing
**Completed:** v0.1.0.0 (2026-03-23)

### TODO-008: Observer Singleton History Window ✅ DONE
**What:** Observer singleton with 40-message history cap
**Context:** `api/observer_routes.py` now has a module-level `_observer` singleton created on first request. History trimmed to `_OBSERVER_MAX_HISTORY = 40` after each `speak()` call.
**Completed:** v0.1.1.0
