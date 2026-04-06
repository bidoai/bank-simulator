# Apex Global Bank Simulator

> A JPMorgan-scale investment bank, fully simulated — live trading infrastructure, multi-agent AI executives, Basel III capital engine, XVA suite, and 17 SR 11-7 model development documents. Powered by Claude.

---

```
                       ┌─────────────────────────────────────────────────────────┐
                       │              APEX GLOBAL BANK — LIVE SYSTEM             │
                       │                                                         │
                       │   14 AI AGENTS  ·  9 DASHBOARDS  ·  17 RISK MODELS     │
                       │   50+ REST ROUTES  ·  4 WEBSOCKET STREAMS               │
                       └─────────────────────────────────────────────────────────┘

   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
   │  BOARDROOM   │   │   TRADING    │   │     RISK     │   │     XVA      │
   │              │   │              │   │              │   │              │
   │  14 agents   │   │  OMS + PnL   │   │  VaR · SVaR  │   │ CVA DVA FVA  │
   │  debating    │   │  Greeks      │   │  FRTB-SA     │   │ MVA ColVA    │
   │  in real     │   │  Positions   │   │  Basel III   │   │ KVA  PFE     │
   │  time        │   │  Limits      │   │  Stress      │   │              │
   └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘

   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
   │  COLLATERAL  │   │   TREASURY   │   │   MODELS     │   │  SEC-FIN /   │
   │              │   │              │   │              │   │  SECURITIZED │
   │  VM · IM     │   │  ALM · FTP   │   │  SR 11-7     │   │              │
   │  SIMM 2.6    │   │  NII · EVE   │   │  17 MDDs     │   │  Repo · SBL  │
   │  Stress      │   │  Repricing   │   │  Registry    │   │  MBS · CLO   │
   │  Scenarios   │   │  Gap         │   │  Q&A (AI)    │   │  ABS · CMBS  │
   └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
```

---

## What This Is

Apex Global Bank is a complete simulation of a JPMorgan-scale institution: trading desks, risk models, capital management, treasury, compliance, and a boardroom full of opinionated executives — all running on a single laptop.

Every system is real. The OMS enforces pre-trade VaR limits — orders that would push a desk above its hard limit are rejected with HTTP 422. The capital engine computes CET1 using Basel III risk weights. The DFAST engine projects CET1 under a 9-quarter severely adverse scenario. The XVA suite calculates CVA/DVA/FVA on live derivatives positions using per-counterparty credit spreads calibrated to credit ratings. The 17 registered models each have a full SR 11-7 Model Development Document with open findings, use authorizations, and validation status.

The AI agents are not wrappers around a script — they are genuine `claude-opus-4-6` instances with deep domain-specific system prompts. They disagree, push back, and respond to live market data injected into the meeting context.

**Built for:** learning, demos, research, and exploring what a fully-instrumented bank looks like from the inside.

---

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# → set ANTHROPIC_API_KEY=sk-ant-...

# 3. Start the dashboard server
uvicorn api.main:app --reload
open http://localhost:8000

# 4. Or run a boardroom meeting from the CLI (no browser needed)
python main.py
```

**Full test suite:**
```bash
uv run --with fastapi --with pytest-asyncio --with httpx --with structlog --with numpy --with anthropic pytest -q
```

---

## Dashboards

Nine single-page dashboards, all with live WebSocket feeds and a floating Observer Q&A widget:

| Dashboard | Route | What You See |
|-----------|-------|--------------|
| **Home** | `/` | System overview, agent roster, quick-launch cards |
| **Boardroom** | `/boardroom` | Live agent debate stream, scenario launcher, session archive |
| **Trading** | `/trading` | OMS blotter, real-time P&L, Greeks heatmap, position book |
| **XVA** | `/xva` | CVA/DVA/FVA/MVA/ColVA, PFE exposure profile, live badge (DEMO→LIVE) |
| **Risk** | `/risk` | VaR by desk, FRTB capital, Basel III ratios, backtesting traffic light |
| **Securities Finance** | `/securities-finance` | Repo ladders, stock borrow/loan, prime financing, balance-sheet usage |
| **Securitized Products** | `/securitized` | MBS/ABS/CMBS/CLO inventory, OAS, effective duration, convexity, stress |
| **Model Governance** | `/models` | SR 11-7 registry, 17 MDDs, findings tracker, AI-powered model Q&A |
| **Scenarios** | `/scenarios` | Market stress launcher, DFAST CET1 chart, SIMM stress, AML scanner |

---

## Agent Roster

Fourteen `claude-opus-4-6` instances, each with a distinct system prompt, voice profile, and color:

| Agent | Role | Lens |
|-------|------|------|
| **Alexandra Chen** | CEO | Strategy, accountability, franchise risk |
| **Dr. Priya Nair** | CRO | Downside protection, tail scenarios, limit discipline |
| **Diana Osei** | CFO | Capital allocation, earnings, investor obligations |
| **Marcus Rivera** | CTO | Platform resilience, delivery risk, engineering leverage |
| **Dr. Yuki Tanaka** | Head of Quant Research | Model validity, calibration, assumptions |
| **James Okafor** | Head of Global Markets | P&L, flow, market timing, client franchise |
| **Sarah Mitchell** | Chief Compliance Officer | Regulatory exposure, conduct, controls |
| **Amara Diallo** | Head of Treasury & ALM | Liquidity, funding cost, balance-sheet efficiency |
| **Jordan Pierce** | Head of Internal Audit | Independent 3LoD, adversarial, reports to Audit Committee |
| **Margaret Okonkwo** | General Counsel | ISDA netting, regulatory self-reporting, legal entity governance |
| **Dr. Samuel Achebe** | Model Validation Officer | SR 11-7 independence, findings, compensating controls |
| **Dr. Fatima Al-Rashid** | Chief Data Officer | Data lineage, governance, AI/ML risk |
| **The Observer** | Independent Narrator | Explains what's happening to the reader — no agenda |
| **Meridian Consultant** | External Advisor | Outside-in perspective, peer benchmarking |

Agents respond to live market shocks injected via the scenario engine. Each has a distinct browser TTS voice (swap to ElevenLabs in one config line).

---

## Infrastructure Stack

Every module is a real quantitative system — not stubs:

### Trading
| Module | Description |
|--------|-------------|
| `OMS` | FIFO order management, partial fills, pre-trade VaR gate |
| `PositionManager` | Real-time book positions, realized/unrealized PnL |
| `LimitManager` | 20 hard limits across desks, Greeks, and concentration |
| `GreeksCalculator` | BSM Greeks for options, DV01 for rates, CS01 for credit, delta-1 for FX/equity |
| `OrderBook` | Bid/ask simulation per instrument |
| `PnLCalculator` | Mark-to-market with 11-ticker 500ms GBM market data feed |

### Risk
| Module | Description |
|--------|-------------|
| `VaRCalculator` | Historical (250-day), parametric delta-normal, Monte Carlo Cholesky (regime-aware) |
| `CorrelationRegimeModel` | 2-state HMM proxy: NORMAL/STRESS 6×6 matrices; auto-switches based on realized equity-credit correlation |
| `RegulatoryCapitalEngine` | Basel III SA: CET1/Tier1/Total/Leverage ratios, SA-CCR, OpRisk BIA, FRTB-SA sensitivity capital |
| `ConcentrationRiskMonitor` | Single-name (25% CET1), sector (25% TA), geography (40% TA) limits with HHI |
| `CounterpartyRegistry` | Formal counterparty data: ratings, ISDA flags, PFE limits |
| `RiskService` | Orchestrates snapshot → VaR → limits → capital in one call |

### Treasury
| Module | Description |
|--------|-------------|
| `ALMEngine` | NII/EVE sensitivity (±100/200bps), 7-bucket repricing gap, SVB-style duration warning |
| `FTPEngine` | Matched-maturity OIS + liquidity premium; desk-level FTP-adjusted P&L |
| `SwapCurve` | 9-tenor OIS curve with linear interpolation |

### Credit & Compliance
| Module | Description |
|--------|-------------|
| `IFRS9ECLEngine` | Stage 1/2/3 ECL on 50-obligor portfolio; PIT PD via GDP/unemployment macro overlay |
| `DFASTEngine` | 9-quarter CET1 projection under baseline/adverse/severely adverse; Plotly chart |
| `AMLTransactionMonitor` | 6 rule typologies (structuring, velocity, round-dollar, layering, geography, PEP) |

### Collateral
| Module | Description |
|--------|-------------|
| `VMEngine` | Daily VM lifecycle across 5 CSAs: call → receipt → dispute → settlement → default |
| `SIMMEngine` | ISDA SIMM 2.6: IR, CRQ, CRNQ, EQ, FX, CMT risk classes |
| `CollateralStressScenarios` | COVID Week, Lehman Event, Gilt Crisis — IM uplift and liquidity call quantified |

### XVA
| Module | Description |
|--------|-------------|
| `SimulationXVAService` | Live CVA/DVA/FVA via pyxva integration; auto-refreshes on trade submit |
| `XVABroadcaster` | WebSocket push to dashboard; DEMO→LIVE badge |
| `XVAAdapter` | Maps OMS fills to pyxva trade config by product type |

### Securities Finance & Securitized Products
| Module | Description |
|--------|-------------|
| `SecuritiesFinanceService` | Repo, stock borrow/loan, prime financing; balance-sheet and funding metrics |
| `SecuritizedProductsService` | Agency MBS/ABS/CMBS/CLO analytics: OAS, effective duration, convexity, stress |

### Infrastructure Foundation
| Module | Description |
|--------|-------------|
| `EventLog` | Append-only SQLite audit trail; every trade, limit breach, and capital action |
| `InstrumentMaster` | ISIN/CUSIP/product-type registry; 9 seeded instruments |
| `PositionSnapshots` | SQLite-backed position persistence — survives process restarts |
| `APIMetrics` | Daily token spend tracker with $10 alert threshold |
| `ModelRegistry` | SR 11-7 governance lifecycle: status, validator, findings, use authorization |

---

## Model Governance

17 registered models under SR 11-7, each with a complete Model Development Document:

| ID | Model | Tier | Status | Open Findings |
|----|-------|------|--------|---------------|
| APEX-MDL-0001 | Market Risk VaR | 1 | Validated | 2 |
| APEX-MDL-0002 | Stressed VaR (SVaR) | 1 | In Validation | 1 |
| APEX-MDL-0003 | FRTB Standardised Approach | 1 | Draft | 3 |
| APEX-MDL-0004 | Black-Scholes-Merton | 1 | Validated | 2 |
| APEX-MDL-0005 | Hull-White 1F | 1 | In Validation | 2 |
| APEX-MDL-0006 | SOFR / LMM Term Rate | 1 | Draft | 3 |
| APEX-MDL-0007 | IFRS 9 ECL | 1 | Validated | 1 |
| APEX-MDL-0008 | AML Transaction Monitoring | 2 | Validated | 3 |
| APEX-MDL-0009 | Correlation Regime Model | 1 | Validated | 3 |
| APEX-MDL-0010 | CVA Engine | 1 | In Validation | 3 |
| APEX-MDL-0011 | FVA Engine | 1 | Draft | 0 |
| APEX-MDL-0012 | MVA Engine | 1 | Draft | 0 |
| APEX-MDL-0013 | ColVA Engine | 1 | Draft | 0 |
| APEX-MDL-0014 | PFE / CCR Exposure Engine | 1 | Draft | 2 |
| APEX-MDL-0015 | DFAST / Stress Testing | 1 | In Validation | 3 |
| APEX-MDL-0016 | Collateral / SIMM Engine | 1 | In Validation | 3 |
| APEX-MDL-0017 | ALM / FTP Engine | 1 | In Validation | 3 |

Every MDD includes: theoretical basis, mathematical specification, implementation details, validation methodology, model limitations, **Section 7 use authorization** (authorized uses, prohibited uses, approval chain), and open findings.

The `/models` dashboard surfaces all of this with an AI-powered Q&A: ask Dr. Yuki Tanaka (model builder) or Dr. Samuel Achebe (validator) anything about a model — they answer in character from the MDD.

**Model documents:** `model_docs/*.md` (markdown) · `model_docs/latex/*.tex` (LaTeX source) · `model_docs/pdfs/*.pdf` (compiled)

---

## Scenario Engine

Pre-built boardroom scenarios that inject real agent context:

| Scenario | File | Description |
|----------|------|-------------|
| **Founding Board Meeting** | `scenarios/founding_board_meeting.py` | Bank launch — capital deployment, governance, strategic priorities |
| **Consulting Review** | `scenarios/consulting_review_meeting.py` | Meridian Consulting presents findings; management responds |
| **Collateral Mechanics** | `scenarios/collateral_mechanics_meeting.py` | VM call spike, SIMM recalibration, counterparty dispute |
| **Model Risk Remediation** | `scenarios/model_risk_remediation_meeting.py` | Post-audit stakeholder response: SVaR breach, ARRC violation, 833 undocumented models |

The scenario engine (`POST /api/scenarios/activate`) injects a structured shock into the next agent prompt — agents respond to the market event in character without breaking their persona.

---

## API Surface

17 route modules, 50+ endpoints, 4 WebSocket streams:

```
GET  /api/risk/snapshot              VaR snapshot across all desks
GET  /api/risk/limits                Live limit utilisation
GET  /api/capital/ratios             CET1 / Tier1 / Total / Leverage
POST /api/capital/stress             Ad-hoc capital stress scenario
GET  /api/stress/dfast               9-quarter DFAST CET1 trajectory
GET  /api/treasury/alm/report        NII/EVE/repricing-gap summary
GET  /api/treasury/ftp/adjusted-pnl  FTP-adjusted P&L by desk
GET  /api/collateral/simm            SIMM IM by counterparty and risk class
GET  /api/collateral/stress          COVID/Lehman/Gilt Crisis IM stress
GET  /api/models/registry            Full SR 11-7 model registry
GET  /api/models/{id}/pdf            Download compiled MDD PDF
POST /api/models/chat                AI model Q&A (SSE streaming)
GET  /api/credit/ecl/portfolio       IFRS 9 ECL summary
GET  /api/compliance/aml/stats       AML alert rate and SAR conversion
POST /api/compliance/aml/screen      Screen a transaction against all rules
GET  /api/trading/greeks             Live Greeks by desk
GET  /api/boardroom/archive          Paginated boardroom session archive
WS   /ws/boardroom                   Agent turn stream (JSON)
WS   /ws/market-data                 Live price ticks (500ms)
WS   /ws/xva                         CVA/DVA/FVA live updates
WS   /ws/risk                        Risk snapshot push
```

Full route list in [`docs/architecture.md`](docs/architecture.md).

---

## Architecture

```
                    ┌────────────────────────────────────────┐
                    │        Browser (9 dashboard pages)     │
                    │   HTML/JS · WebSocket · SSE streaming  │
                    └───────────────┬────────────────────────┘
                                    │ HTTP / WS
                    ┌───────────────▼────────────────────────┐
                    │       FastAPI  (api/main.py)           │
                    │  17 route modules · 4 WS broadcasters  │
                    └──┬────────────┬──────────┬─────────────┘
                       │            │          │
          ┌────────────▼──┐  ┌──────▼────┐  ┌─▼──────────────┐
          │  Orchestrator  │  │  Risk     │  │  Infrastructure │
          │  (Boardroom)   │  │  Service  │  │  Engines        │
          │                │  │           │  │                 │
          │  14 BankAgents │  │ VaR · Cap │  │ OMS · ALM · FTP │
          │  claude-opus   │  │ Collat    │  │ SIMM · XVA · ECL│
          │  4.6           │  │ DFAST     │  │ AML · Sec-Fin   │
          └────────────────┘  └───────────┘  └────────┬────────┘
                                                       │
                                            ┌──────────▼──────────┐
                                            │  SQLite Databases    │
                                            │                      │
                                            │  positions.db        │
                                            │  events.db (audit)   │
                                            │  instruments.db      │
                                            │  boardroom.db        │
                                            │  metrics.db          │
                                            │  governance.db       │
                                            └─────────────────────-┘
```

Single-process, no message queue, no microservices. Every component is a Python singleton wired together at startup. The event log provides an append-only audit trail for the 3LoD independence check.

See [`docs/architecture.md`](docs/architecture.md) for the full breakdown: startup sequence, all route signatures, WebSocket message schemas, data flow diagrams, DB schemas, and singleton ownership map.

---

## Repository Layout

```
agents/
  base_agent.py              BankAgent base class (max_history, stream_speak)
  executive/                 CEO, CFO, CRO, CTO, CDO, CISO
  markets/                   Lead Trader, Quant Researcher, Head of Markets
  risk_desk/                 Model Validation, Model Risk Officer, Risk Officers
  legal/                     General Counsel
  audit/                     Internal Audit
  narrator/                  The Observer
  consulting/                Meridian Consultant

api/
  main.py                    FastAPI app factory, router registration, startup
  boardroom_routes.py        Boardroom session management + archive
  models_routes.py           SR 11-7 registry, MDD serving, AI model Q&A
  risk_routes.py             VaR, limits, counterparties, 3LoD independence
  capital_routes.py          Basel III: ratios, RWA, stress, concentration
  trading_routes.py          Positions, Greeks, blotter, market data
  treasury_routes.py         ALM, FTP, NII/EVE sensitivity
  collateral_routes.py       CSA, VM calls, SIMM, stress scenarios
  stress_routes.py           DFAST 9-quarter projections
  credit_routes.py           IFRS 9 ECL, stage classification
  compliance_routes.py       AML alerts, SAR stats, transaction screening
  xva_routes.py              CVA/DVA/FVA, PFE, live XVA broadcaster
  ...

infrastructure/
  trading/                   OMS, PositionManager, LimitManager, Greeks, PnL
  risk/                      VaRCalculator, CorrelationRegimeModel, RegulatoryCapitalEngine
  treasury/                  ALMEngine, FTPEngine, SwapCurve
  collateral/                VMEngine, SIMMEngine, CollateralStressScenarios
  credit/                    IFRS9ECLEngine
  stress/                    DFASTEngine
  compliance/                AMLTransactionMonitor
  xva/                       SimulationXVAService, XVAAdapter, XVABroadcaster
  securities_finance/        SecuritiesFinanceService
  securitized_products/      SecuritizedProductsService
  governance/                ModelRegistry (SR 11-7 lifecycle)
  events/                    EventLog (append-only SQLite audit trail)
  market_data/               MarketDataFeed (GBM simulation, 500ms ticks)
  reference/                 InstrumentMaster (ISIN/CUSIP registry)
  persistence/               PositionSnapshots (restart-safe)
  metrics/                   APIMetrics (daily token spend)

model_docs/
  registry.json              17-model SR 11-7 registry
  mdd_*.md                   Markdown MDDs (all 9 original + 3 new)
  latex/                     LaTeX source for all MDDs + research papers
  pdfs/                      Compiled PDFs

scenarios/                   Four runnable boardroom scenarios
dashboard/                   Nine HTML/JS single-page dashboards
orchestrator/                Boardroom conductor + meeting session manager
docs/                        Architecture writeup, design documents
```

---

## Cost Model

Every `agent.speak()` call is a `claude-opus-4-6` API call — real tokens, real cost.

| Pattern | Cost | When to use |
|---------|------|-------------|
| Sequential boardroom turns | Low — one call per turn | Default for all discussions |
| Parallel multi-agent | High — N calls at once | Genuinely independent parallel work only |
| Observer narration | Low — single call | After each meeting section |
| Scenario injection | Zero (context only) | Inject market shocks without agent calls |

Rules enforced in code:
- `BankAgent.__init__` requires `max_history` — prevents unbounded context growth
- `BoardroomBroadcaster._history` capped at 200 messages
- `POST /api/metrics/api/reset` to clear daily spend counter
- `ANTHROPIC_API_KEY` in `.env` only — never committed

Check spend before long runs: `GET /api/metrics/api`

---

## Environment Variables

```bash
ANTHROPIC_API_KEY=sk-ant-...    # required — all agent and model Q&A calls
```

Everything else (ports, DB paths, tick intervals, risk limits, FTP rates) is configured in code. See [`CLAUDE.md`](CLAUDE.md) for project-specific development conventions.

---

## Open Items

| ID | Description | Priority |
|----|-------------|----------|
| TODO-012 | Historical stress data store for FRTB backtesting (GFC 2008, COVID 2020) | P2 |
| TODO-026 | OMS hardening: asyncio.Lock, thread-pool for MC VaR, pre/post-trade VaR consistency | P3 |
| TODO-029 | Securities Finance lifecycle: event-driven repo/margin state vs. static seeded metrics | P3 |
| TODO-030 | Agency MBS analytics: rate paths, prepayment model, OAS, effective duration from model | P3 |

See [`TODOS.md`](TODOS.md) for the full history including completed items and implementation notes.

---

## Research Documents

The `model_docs/pdfs/` directory contains compiled research papers:

| Document | Description |
|----------|-------------|
| `bank_quant_operating_model_v1.0.pdf` | Full quantitative operating model: all 17 models, infrastructure, governance |
| `balance_sheet_optimization_v1.0.pdf` | 22-page deep dive: constrained NLP formulation, capital/liquidity/ALM/RAROC math, calculator stack, revenue analysis |

---

*Educational and demonstration project. Not connected to real financial infrastructure.*
