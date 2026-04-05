# TODOS — Apex Global Bank Simulator

## P1 — High Priority

### TODO-001: Agent Context Window Management ✅ DONE
**What:** Add sliding window or summary-based history pruning to `BankAgent`
**Context:** `BankAgent.__init__` now accepts `max_history: int = 0` (0 = unlimited, backward compatible). After each `speak()` / `stream_speak()`, history is trimmed to the last `max_history` messages. Observer singleton hardcodes 40 messages (20 turns). Orchestrator transcript context was already capped at 20 turns.
**Completed:** v0.1.1.0

---

## P2 — Backlog

### TODO-002: XVA Position Field Mapping ✅ DONE
**What:** Complete `XVAAdapter.from_positions()` — map `Position.symbol`, `.quantity`, `.avg_entry_price` to pyxva Trade fields
**Context:** `SimulationXVAService._map_fills_to_pyxva_config()` in `infrastructure/xva/service.py` maps OMS blotter fills to pyxva config. Equity tickers (AAPL/MSFT/SPY/NVDA) excluded from pyxva; CVA computed analytically. Non-equity tickers routed by product type (IRS, FX forward, bond, options).
**Completed:** v0.3.0.0

### TODO-003: Model Governance AI (Quant Agent Q&A) ✅ DONE
**What:** `/api/models/chat` endpoint + chat UI on `models.html` — multi-persona Q&A on model cards
**Context:** `api/models_routes.py` — `POST /api/models/chat` with model_id allowlist from `registry.json`. Dr. Yuki Tanaka answers for BSM/HW1F/LMM (APEX-MDL-0004/0005/0006); Dr. Samuel Achebe for all others. SSE streaming, system prompt includes full model card JSON + MDD markdown content.
**Completed:** v0.3.0.0

### TODO-004: BoardroomBroadcaster History Cap ✅ DONE
**What:** Cap `BoardroomBroadcaster._history` at 200 messages
**Context:** `api/boardroom_broadcaster.py` — `_MAX_HISTORY = 200` with cap enforced at lines 98-99 and 149-150.
**Completed:** v0.1.x (pre-existing, confirmed by eng review)

### TODO-005: pyxva Live XVA Integration ✅ DONE
**What:** Wire `XVAAdapter.run_pipeline()` to actual simulation trades
**Context:** `infrastructure/xva/service.py` (stream-b) — `SimulationXVAService` with asyncio.Lock guard, auto-refresh on OMS trade submit, cached results. `XVABroadcaster` pushes live updates via `/ws/xva`. Dashboard badge switches DEMO → LIVE.
**Completed:** v0.3.0.0

---

### TODO-010: Risk Integration Layer ✅ DONE
**What:** `RiskService` + `CounterpartyRegistry` + `/api/risk/*` endpoints — closes the control loop between PositionManager, VaRCalculator, and LimitManager
**Context:** Three new files: `infrastructure/risk/risk_service.py` (wires all three systems, runs MC VaR per desk, updates limits), `infrastructure/risk/counterparty_registry.py` (formal counterparty data with ratings, ISDA flags, PFE limits), `api/risk_routes.py` (7 REST endpoints: snapshot, limits, counterparties, positions, on-demand VaR). Decided in market risk boardroom session 2026-03-24.
**Completed:** v0.1.2.0

### TODO-011: Greeks Pipeline (DV01, Vega, CS01) ✅ DONE
**What:** Pricer layer between PositionManager and risk metrics. DV01 for fixed income, Black-Scholes Greeks for equity derivatives, CS01 for CDS.
**Context:** `infrastructure/trading/greeks.py` — `GreeksCalculator` with BSM for options, DV01 for bonds/IRS, delta-1 for equities/FX. Aggregates per-book and portfolio. Exposed via `GET /api/trading/greeks` (live from real positions).
**Completed:** v0.2.0.0

### TODO-012: Stressed VaR + FRTB Backtesting ✅ DONE
**What:** Historical market data store for 2007-2009 GFC and 2020 COVID windows. Continuous backtesting runner to track IMA exceptions.
**Context:** `infrastructure/risk/var_backtest_store.py` — SQLite-backed 252-day seeded history, traffic-light zone (Green 0-4, Yellow 5-9, Red 10+ exceptions), capital multiplier k. `infrastructure/risk/stressed_var.py` — sVaR calibrated to 2008-09 crisis (3.5× equity vol, 4× credit spread vol). New endpoints: `POST /api/risk/backtesting/observation` (record daily P&L vs VaR), `GET /api/risk/ima-status` (IMA approval status — RED zone triggers SA revert recommendation, ref Basel 2.5 MAR99).
**Completed:** v0.3.1.0

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

### TODO-025: Collateral Simulation Module ✅ DONE
**What:** `infrastructure/collateral/` — CSA/CollateralAccount/MarginCall data model, VMEngine with daily margin call lifecycle, SIMM approximation (IR + CRQ risk classes), three named stress scenarios (COVID Week, Lehman Event, Gilt Crisis). Seven REST endpoints at `/api/collateral/*`.
**Context:** Decided in collateral mechanics boardroom session 2026-03-26. Five seeded CSAs (Goldman Sachs, JPMorgan, Deutsche Bank, Meridian Capital, LCH cleared). SIMM pre-nets same-tenor DV01 before aggregation. VM engine handles threshold band, MTA gating, dispute/late/default behaviour flags, close-out netting. Collateral module sits between PositionManager and XVAAdapter — fixes CVA error introduced by TODO-002/005. 45 tests, all green.
**Completed:** v0.1.4.0

---

## Phase 2 — Still open (60-180 day plan)

### TODO-022: Legal Entity / Booking Model ✅ DONE
**What:** `models/legal_entity.py` — 4 Apex legal entities with jurisdiction, regime, netting flag. `DESK_ENTITY` maps trading desks to booking entities. `GET /api/risk/entities` endpoint.
**Completed:** v0.3.0.0

### TODO-023: 3LoD Independent Data Layer (CQRS) ✅ DONE
**What:** `PositionManager.add_trade()` now publishes `TradeBooked` to EventLog. `RiskPositionReader.rebuild()` replays only those events — pure second-line read path. `GET /api/risk/independence-check` compares PositionManager notional vs RiskPositionReader notional; returns ALIGNED/DIVERGED.
**Completed:** v0.3.0.0

### TODO-024: DFAST/CCAR Stress Testing Framework ✅ DONE
**What:** `infrastructure/stress/dfast_engine.py` — 9-quarter CET1 projection under baseline/adverse/severely_adverse scenarios. `GET /api/stress/dfast` and `/api/stress/dfast/{scenario}`. DFAST panel in `dashboard/scenarios.html` with Plotly CET1 chart + Basel 4.5% minimum line.
**Completed:** v0.3.0.0

### TODO-026: OMS Hardening ✅ DONE
**What:** Harden the OMS for concurrent use.
**Context:** `api/oms_routes.py` — module-level `_ORDER_LOCK = asyncio.Lock()` serialises concurrent `submit_order` calls. `oms.submit_order()` offloaded to `run_in_executor` so Monte Carlo risk snapshot (~100ms) no longer blocks the event loop. `_persist_trade` now awaited (not fire-and-forget) so SQLite write failures surface. Pre-trade (parametric VaR) vs post-trade (Monte Carlo) methodology mismatch remains documented in `infrastructure/trading/oms.py` — methodology alignment is P4 work.
**Completed:** v0.3.1.0

### TODO-027: Treasury Route Repair + State Ownership Hardening ✅ DONE
**What:** Fix all three treasury route failures and enforce single PositionManager ownership.
**Context:**
- `_get_positions()` was calling nonexistent `risk_service.get_snapshot()` (AttributeError swallowed) → now calls `risk_service.position_manager.get_all_positions()` directly
- `/ftp/adjusted-pnl` was constructing a detached `PositionManager()` (empty, never saw a trade) and calling `.values()` on a list → removed; desk P&L now comes from `risk_service.get_position_report()["by_desk"]`
- Dead `PnLCalculator` import removed
- FTP engine `calculate_desk_charges()` was grouping by `book_id` and using `pos.get("ticker")` — changed to group by `desk` and use `pos.get("instrument")` to match live position schema
- All blanket `except Exception: return []` removed; errors now surface as proper HTTP 500s
- `infrastructure/persistence/position_snapshots.py` field names aligned: `ticker` → `instrument`, `realized_pnl`/`unrealized_pnl` → `realised_pnl`/`unrealised_pnl`
**Completed:** 2026-03-26 (feature/clickable-landing-cards)

### TODO-028: Docs Reconciliation ✅ DONE
**What:** Align CLAUDE.md, README.md, and docs/architecture.md with actual code.
**Context:**
- CLAUDE.md: fixed uvicorn entrypoint (`api.app:app` → `api.main:app`), fixed broadcaster cap (1,000 → 200)
- docs/architecture.md: full rewrite — startup sequence, all 40+ routes, WebSocket message shapes, all data flows, DB schemas, singleton map, risk limit table, Greeks table, agent roster
- README.md: created (was missing)
**Completed:** 2026-03-26

---

## Not in scope (explicitly deferred)
- Multi-user / auth system (pre-v1)
- Production cloud deployment (pre-v1)
- LICENSE / CONTRIBUTING.md / GitHub Actions CI (5 min each with CC when ready)
- Real-world market data feed integration (Bloomberg/Refinitiv)

---

## v0.3.x MDD Suite Completions (feature/v03-xva-live-mdd-suite)

### TODO-031: MDD Registry Reconciliation ✅ DONE
**What:** Fix registry.json discrepancies flagged by the audit scenario.
**Context:**
- AML-F2 severity corrected from "minor" → "major" (MDD said Major, registry said Minor)
- AML-F3 (FATF grey-list refresh lag, Minor) added; `open_findings` 2→3
- CRM-F2 (20-day lookback lag, Major) and CRM-F3 (US-centric proxies, Minor) added; `open_findings` 1→3
- Registry `tier1_models` updated 13→16 to reflect 3 new MDDs
**Completed:** 2026-04-04

### TODO-032: Section 7 (Use Authorization) — All MDDs ✅ DONE
**What:** Added SR 11-7-compliant Section 7 to all 9 existing MDD markdown files.
**Context:** Each Section 7 includes Authorized Uses, Prohibited Uses, Authorized Users table, Approval Chain table, and Use Conditions. Content is model-specific and references open findings as use constraints. Files updated: mdd_var_irc, mdd_svar, mdd_frtb_sa, mdd_black_scholes, mdd_hull_white, mdd_sofr_lmm, mdd_ifrs9_ecl, mdd_aml_rbm, mdd_correlation_regime.
**Completed:** 2026-04-04

### TODO-033: Three New MDDs ✅ DONE
**What:** Created missing MDDs called out in the audit scenario as critical gaps.
**Context:**
- `mdd_dfast_v1.0.md` — APEX-MDL-0015. 9-quarter CET1 projection model; macro satellite, PPNR model, market loss channel. 3 open findings.
- `mdd_collateral_simm_v1.0.md` — APEX-MDL-0016. VM lifecycle + SIMM 2.6 IM (6 risk classes) + 3 stress scenarios. Covers COLL-F2 (CVA integration gap). 3 open findings.
- `mdd_alm_ftp_v1.0.md` — APEX-MDL-0017. NII/EVE sensitivity, 7-bucket repricing gap, behavioural deposit model, matched-maturity FTP with OIS+liquidity premium. 3 open findings.
All three added to registry.json.
**Completed:** 2026-04-04

### TODO-034: Balance Sheet Optimization PDF ✅ DONE
**What:** 22-page quantitative reference document on bank balance sheet optimization.
**Context:** Covers the full constrained optimization problem (multi-period NLP), capital optimization (RWA minimization, RAROC, EC allocation), liquidity optimization (LCR/NSFR, HQLA), ALM (NII/EVE, duration gap, convexity), FTP (matched-maturity, liquidity premium), stress testing (DFAST integration, reverse stress), technology requirements (calculator stack, compute, dashboards), and revenue generation mechanisms. LaTeX source: `model_docs/latex/balance_sheet_optimization_v1.0.tex`. Compiled PDF: `model_docs/pdfs/balance_sheet_optimization_v1.0.pdf`.
**Completed:** 2026-04-04

---

## Phase 3 — Product Expansion

### TODO-029: Securities Finance Lifecycle ✅ DONE
**What:** Extend the seeded securities-finance desk into a live lifecycle: repo ladders, margin events, stock-borrow availability, and client term repricing.
**Context:** `infrastructure/securities_finance/lifecycle.py` — `RepoLadder` (4-tenor O/N/1W/1M/3M repo book with live FRED rate pricing, repricing trigger on >2bps move), `MarginEngine` (4 counterparty accounts with daily VM lifecycle, margin call simulation via `POST /api/securities-finance/margin/shock`). New endpoints: `GET /api/securities-finance/repo-ladder`, `POST /api/securities-finance/repo-ladder/reprice`, `GET /api/securities-finance/margin`, `POST /api/securities-finance/margin/shock`.
**Completed:** v0.3.1.0

### TODO-030: Agency MBS Analytics Engine ✅ DONE
**What:** Add a true agency MBS pricing engine: rate paths, prepayment model, pathwise cash flows, OAS, effective duration, and convexity.
**Context:** `infrastructure/securitized_products/mbs_analytics.py` — PSA prepayment model (100% PSA baseline, speed-adjustable), Ho-Lee short-rate paths (100 paths), pathwise cash flow generator, OAS bisection solver (±50bp effective duration/convexity bump-and-reprice), 7-scenario analysis (±50/100/200bps). `GET /api/securitized/mbs-analytics` returns live OAS + effective duration + convexity for FNMA 5.5 TBA and Specified Pool LLB 5.0.
**Completed:** v0.3.1.0

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
