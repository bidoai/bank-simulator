# Apex Global Bank Simulator

> A JPMorgan-scale investment bank, fully simulated in Python — live trading infrastructure with 7-gate pre-trade enforcement, real-time capital allocation, multi-agent AI executives, Basel III capital engine, XVA suite, live FRED/Yahoo Finance market data, and 17 SR 11-7 model development documents. Powered by Claude.

---

```
                       ┌──────────────────────────────────────────────────────────┐
                       │               APEX GLOBAL BANK — LIVE SYSTEM             │
                       │                                                           │
                       │  14 AI AGENTS · 11 DASHBOARDS · 17 RISK MODELS          │
                       │  60+ REST ROUTES · 4 WEBSOCKET STREAMS                   │
                       │  7-GATE PRE-TRADE · LIVE CAPITAL ALLOCATION              │
                       └──────────────────────────────────────────────────────────┘

   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
   │  BOARDROOM  │   │   TRADING   │   │    RISK     │   │     XVA     │
   │             │   │             │   │             │   │             │
   │  14 agents  │   │  7-gate OMS │   │  VaR · sVaR │   │ CVA DVA FVA │
   │  debating   │   │  RAROC gate │   │  FRTB-SA    │   │ MVA ColVA   │
   │  in real    │   │  Greeks     │   │  Basel III  │   │ KVA  PFE    │
   │  time       │   │  Positions  │   │  Suspension │   │             │
   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘

   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
   │  CAPITAL    │   │  TREASURY   │   │   MODELS    │   │  SEC-FIN /  │
   │             │   │             │   │             │   │  SECURITIZED│
   │  CET1 alloc │   │  ALM · FTP  │   │  SR 11-7    │   │             │
   │  RWA budget │   │  NII · EVE  │   │  17 MDDs    │   │  Repo · SBL │
   │  RAROC      │   │  Repricing  │   │  Registry   │   │  MBS · CLO  │
   │  Suspension │   │  FRED rates │   │  AI Q&A     │   │  ABS · CMBS │
   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘
```

---

## What This Is

Apex Global Bank is a complete simulation of a JPMorgan-scale institution: trading desks with hard pre-trade enforcement, real-time capital allocation, Basel III regulatory capital, treasury and ALM, XVA on live derivatives, IFRS 9 credit loss, AML monitoring, and a boardroom full of opinionated AI executives — all running on a single laptop.

**Every system enforces constraints.** The OMS runs seven sequential pre-trade gates before booking any order — VaR headroom, DV01, equity delta, single-name concentration, Large Exposure (CRE70), RWA budget against the desk's capital allocation, and RAROC. An order that fails any gate returns HTTP 422 with a precise rejection reason. Desks that breach a RED limit are automatically suspended; the CRO must lift the suspension via API.

**Capital is live.** The CFO allocates $45B CET1 top-down to business lines and then to individual desks. Every booked trade consumes incremental RWA (notional × Basel SA risk weight), tracked in real time per desk and counterparty. The CET1 ratio moves as trades are booked. A desk that exhausts its RWA budget cannot trade until the CFO reallocates capital.

**Market data is real.** At startup, the system fetches live equity prices from Yahoo Finance, the full UST/SOFR yield curve from FRED (12 tenors), ICE BofA OAS credit spreads (AAA through HY), and official 2025 DFAST scenario parameters. These seed the GBM simulation, calibrate FTP rates, adjust stressed VaR volatilities, and set LCR stress haircuts.

**The AI agents are genuine.** Fourteen `claude-opus-4-6` instances with deep domain-specific system prompts — they disagree, push back, and respond to live market data injected into the meeting context. They are not wrappers around scripts.

**Built for:** learning, demos, research, and understanding what a fully-instrumented bank looks like from the inside.

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

# 4. Or run a boardroom meeting from the CLI
python main.py
```

**Full test suite:**
```bash
uv run --with fastapi --with pytest-asyncio --with httpx --with structlog \
       --with numpy --with scipy --with anthropic --with aiosqlite pytest -q
```

---

## Dashboards

Eleven single-page dashboards, all with live WebSocket feeds and a floating Observer Q&A widget:

| Dashboard | Route | What You See |
|-----------|-------|--------------|
| **Home** | `/` | System overview, agent roster, quick-launch cards |
| **Boardroom** | `/boardroom` | Live agent debate stream, scenario launcher, session archive |
| **Trading** | `/trading` | OMS blotter, real-time P&L, Greeks heatmap, position book, booking ticket |
| **Risk** | `/risk` | VaR by desk, FRTB capital, Basel III ratios, limit utilisation, backtesting traffic light |
| **XVA** | `/xva` | CVA/DVA/FVA/MVA/ColVA, PFE exposure profile, live badge (DEMO→LIVE) |
| **Capital** | (via `/risk`) | Allocation framework, RWA consumption by desk, RAROC, suspension log |
| **Treasury** | `/treasury` | ALM repricing gap, NII/EVE sensitivity, FTP curve, SOFR live rates |
| **Liquidity** | `/liquidity` | LCR/NSFR ratios, intraday monitor, liquidity ladder, stress scenarios |
| **Securities Finance** | `/securities-finance` | Repo ladders, stock borrow/loan, prime financing, margin calls, trade booking |
| **Securitized Products** | `/securitized` | Agency MBS/ABS/CMBS/CLO inventory, OAS, effective duration, convexity, trade booking |
| **Model Governance** | `/models` | SR 11-7 registry, 17 MDDs, findings tracker, AI-powered model Q&A |
| **Scenarios** | `/scenarios` | Market stress launcher, DFAST CET1 chart, SIMM stress, AML scanner |

---

## Agent Roster

Fourteen `claude-opus-4-6` instances, each with a distinct system prompt, voice, and domain mandate:

| Agent | Role | Lens |
|-------|------|------|
| **Alexandra Chen** | CEO | Strategy, accountability, franchise risk |
| **Dr. Priya Nair** | CRO | Downside protection, tail scenarios, limit discipline |
| **Diana Osei** | CFO | Capital allocation, RAROC, earnings, investor obligations |
| **Marcus Rivera** | CTO | Platform resilience, delivery risk, engineering leverage |
| **Dr. Yuki Tanaka** | Head of Quant Research | Model validity, calibration, mathematical assumptions |
| **James Okafor** | Head of Global Markets | P&L, flow, market timing, client franchise |
| **Sarah Mitchell** | Chief Compliance Officer | Regulatory exposure, conduct, AML controls |
| **Amara Diallo** | Head of Treasury & ALM | Liquidity, funding cost, balance-sheet efficiency |
| **Jordan Pierce** | Head of Internal Audit | Independent 3LoD, adversarial, reports to Audit Committee |
| **Margaret Okonkwo** | General Counsel | ISDA netting, regulatory self-reporting, legal entity governance |
| **Dr. Samuel Achebe** | Model Validation Officer | SR 11-7 independence, findings, compensating controls |
| **Dr. Fatima Al-Rashid** | Chief Data Officer | Data lineage, governance, AI/ML risk |
| **The Observer** | Independent Narrator | Explains what's happening to the reader — no agenda |
| **Meridian Consultant** | External Advisor | Outside-in perspective, peer benchmarking |

Agents respond to live market shocks injected via the scenario engine. Each has a distinct browser TTS voice.

---

## Pre-Trade Risk Control

Every order submitted to the OMS runs seven sequential gates before any position is booked. The first failure blocks the trade with HTTP 422 and a precise rejection message.

| Gate | Check | Limit Source |
|------|-------|-------------|
| **0** | Desk suspension | `LimitActionEngine` — desk suspended on any RED breach |
| **1** | VaR headroom | `LimitManager` — parametric VaR estimate vs desk hard limit |
| **2** | DV01 / CS01 | `GreeksCalculator` — firm DV01 limit (rates/credit desks) |
| **3** | Equity delta | `LimitManager` — net equity delta vs $2B desk limit |
| **4** | Concentration | `ConcentrationRiskMonitor` — single-name % > 5% of book |
| **5** | Large Exposure | `LargeExposuresEngine` — CRE70: 25% Tier 1 (15% G-SIB) per counterparty |
| **6** | RWA budget | `CapitalConsumptionTracker` + `CapitalAllocationFramework` — desk RWA headroom |
| **7** | RAROC | `RAROCEngine` — incremental RAROC < 12% hurdle while desk below hurdle |

Gate 7 can be bypassed with `override_raroc: true` in the order request (for strategic/hedging trades). Gate 0 requires CRO action (`POST /api/risk/suspensions/{desk}/lift`).

After booking, the OMS re-runs a Monte Carlo VaR snapshot, records incremental RWA in the consumption tracker, and updates the desk's notional limit (for SecFin/Securitized desks).

### Limit Escalation (P4)

When any limit changes status, the `LimitActionEngine` fires the appropriate escalation:

| Status | Action |
|--------|--------|
| YELLOW (80–89%) | Desk Head alerted — logged to action log |
| ORANGE (90–99%) | Head of Trading alerted |
| RED (≥ 100%) | Desk auto-suspended; CRO alerted. OMS gate 0 blocks all new orders. |
| BREACH (≥ 120%) | CEO + Board Risk Committee alerted. |

Status improvement auto-lifts the suspension. Manual lift: `POST /api/risk/suspensions/{desk}/lift`.

---

## Capital Management

### Allocation Framework (P3)

The CFO allocates the firm's $45B CET1 top-down. Each desk has a CET1 budget and a derived RWA budget (= CET1 / 4.5% minimum ratio):

```
Firm CET1 ($45B)
├── MARKETS           30%  → $13.5B CET1  → $300B RWA budget
│   ├── EQUITY        30%  → $4.05B CET1  → $90B  RWA budget
│   ├── RATES         35%  → $4.73B CET1  → $105B RWA budget
│   ├── FX            10%  → $1.35B CET1  → $30B  RWA budget
│   ├── CREDIT        15%  → $2.03B CET1  → $45B  RWA budget
│   ├── DERIVATIVES    7%  → $0.95B CET1  → $21B  RWA budget
│   └── COMMODITIES    3%  → $0.41B CET1  → $9B   RWA budget
├── SECURITIES_FINANCE 13% → $5.85B CET1  → $130B RWA budget
│   ├── SECURITIES_FINANCE 70% → $4.10B CET1 → $91B RWA budget
│   └── SECURITIZED       30% → $1.76B CET1 → $39B RWA budget
├── TREASURY_ALM      20%  → $9.0B CET1   → $200B RWA budget
├── CREDIT_LENDING    25%  → $11.25B CET1 → $250B RWA budget
└── OPERATIONAL_BUFFER 12% → $5.4B CET1   (non-tradeable)
```

The CFO can reallocate between desks: `POST /api/capital/reallocate`.

### RWA Consumption Tracker (P2)

Every booked trade records incremental RWA (notional × Basel SA risk weight) to a per-desk accumulator. The live CET1 ratio is derived from the $346B baseline RWA plus all incremental trading-book RWA. View at `GET /api/capital/consumption`.

### RAROC Gate (P6)

Incremental RAROC is estimated pre-trade using desk-specific spread assumptions, expected loss, and FTP charge. The gate only fires when both conditions hold: the incremental trade is below the 12% hurdle rate AND the desk portfolio is already below hurdle. Bypass with `override_raroc: true`.

---

## Live Market Data

At startup, before the GBM simulation begins, the system fetches live data from three external sources:

| Source | Data | Used By |
|--------|------|---------|
| **Yahoo Finance** | Live prices for all 11 simulation tickers (AAPL, MSFT, NVDA, GOOGL, US10Y, US2Y, EURUSD, GBPUSD, CL1, AAPL_CALL_200, SPY) | GBM seed prices, Greeks, VaR |
| **FRED** | 12-tenor SOFR/UST yield curve (3M bill → 30Y bond) | FTP engine, ALM engine, repo ladder |
| **FRED** | ICE BofA OAS indices: AAA/AA/A/BBB/HY | Bank spread calibration, stressed VaR vol, LCR haircuts |
| **FRED** | DFAST 2025 official macro parameters (UNRATE, GDP, SP500, 3M bill) | DFAST scenario starting point |

If any fetch fails, the system falls back to static seeds — startup always succeeds. The data integrations are in `infrastructure/market_data/`.

---

## Infrastructure Stack

Every module is a real quantitative system — not a stub.

### Trading & Capital
| Module | Description |
|--------|-------------|
| `OMS` | 7-gate pre-trade enforcement; FIFO fill at live mid price; blotter with 1,000-trade memory |
| `PositionManager` | Real-time book positions, FIFO cost basis, realized/unrealized PnL |
| `LimitManager` | 22 hard limits: VaR by desk, DV01, equity delta, vega, concentration, stress, SecFin notional |
| `LimitActionEngine` | Escalation callbacks: YELLOW→ORANGE→RED→BREACH; auto-suspend; CRO lift workflow |
| `GreeksCalculator` | BSM Greeks for options, DV01 for rates/bonds, CS01 for credit, delta-1 for FX/equity |
| `CapitalAllocationFramework` | Top-down $45B CET1 → business lines → desks; CFO reallocation; RWA budget per desk |
| `CapitalConsumptionTracker` | Per-trade RWA accumulator; live CET1 ratio; by-desk and by-counterparty breakdown |

### Risk
| Module | Description |
|--------|-------------|
| `VaRCalculator` | Historical (250-day), parametric delta-normal, Monte Carlo Cholesky (regime-aware) |
| `CorrelationRegimeModel` | 2-state HMM proxy: NORMAL/STRESS 6×6 matrices; auto-switches on realized cross-asset correlation |
| `StressedVaREngine` | GFC 2008–09 calibration (3.5× equity vol, 4× credit spread); sVaR multiplier; IMA exception tracking |
| `RegulatoryCapitalEngine` | Basel III SA: CET1/Tier1/Total/Leverage ratios; SA-CCR EAD; OpRisk BIA; 72.5% output floor |
| `CapitalBufferEngine` | CCB 2.5%, CCyB, G-SIB surcharge 1.5%, Pillar 2 add-on; MDA calculation |
| `ConcentrationRiskMonitor` | Single-name (5% of book), sector (25%), geography (40%) limits with HHI |
| `LargeExposuresEngine` | Basel CRE70: 25% Tier 1 per counterparty (15% for G-SIBs); early warning at 10% |
| `CounterpartyRegistry` | Ratings, ISDA flags, PFE limits, credit spreads calibrated to rating bucket |
| `RiskService` | Orchestrates: positions → Monte Carlo VaR → limit update → Greeks → concentration → snapshot |
| `RAROCEngine` | EC sizing by asset class; RAROC = (revenue - EL - FTP - OpRisk) / EC; portfolio and desk level |

### Treasury
| Module | Description |
|--------|-------------|
| `ALMEngine` | NII/EVE sensitivity (±100/200bps), 7-bucket repricing gap, SVB-style duration warning |
| `FTPEngine` | Matched-maturity OIS + liquidity premium; desk-level FTP-adjusted P&L |
| `DynamicFTPEngine` | FRED-calibrated: live SOFR/UST curve overwrites static OIS; live bank AA spread scales premium |
| `RAROCEngine` | Desk-level economic capital; hurdle rate 12%; RORWA density analysis |
| `BalanceSheetOptimizer` | Below-hurdle desk identification; CCP clearing, compression, collateral upgrade recommendations |

### Credit & Compliance
| Module | Description |
|--------|-------------|
| `IFRS9ECLEngine` | Stage 1/2/3 ECL on 50-obligor portfolio; PIT PD via GDP/unemployment macro overlay |
| `DFASTEngine` | 9-quarter CET1 projection under baseline/adverse/severely adverse; 2025 official Fed parameters |
| `AMLTransactionMonitor` | 6 rule typologies: structuring, velocity, round-dollar, layering, geography, sanctions |

### Collateral
| Module | Description |
|--------|-------------|
| `VMEngine` | Daily VM lifecycle across 5 CSAs: call → receipt → dispute → settlement → default |
| `SIMMEngine` | ISDA SIMM 2.6: IR, CRQ, CRNQ, EQ, FX, CMT risk classes; pre-nets same-tenor DV01 |
| `CollateralStressScenarios` | COVID Week, Lehman Event, Gilt Crisis — IM uplift and liquidity call quantified |

### XVA
| Module | Description |
|--------|-------------|
| `SimulationXVAService` | Live CVA/DVA/FVA/MVA/ColVA/KVA via pyxva; auto-refreshes on every trade submit |
| `XVAAdapter` | Maps OMS fills to pyxva trade config by product type (IRS, FX fwd, bond, option, CDS) |
| `XVABroadcaster` | WebSocket push to dashboard; DEMO→LIVE badge |

### Securities Finance & Securitized Products
| Module | Description |
|--------|-------------|
| `SecuritiesFinanceService` | 4 books: Matched Repo, Equity Finance, Prime Brokerage, Collateral Upgrade; stress scenarios |
| `RepoLadder` | FRED-priced repo ladder across tenors; live repricing; margin call engine |
| `SecuritizedProductsService` | Agency MBS/ABS/CMBS/CLO analytics: OAS, effective duration, convexity, relative value, stress |
| `MBSAnalyticsEngine` | PSA prepayment model, Ho-Lee rate paths (100 paths), OAS bisection, 7-scenario analysis |
| OMS SecFin booking | `POST /api/securities-finance/book-trade` — draws from SECURITIES_FINANCE capital pool |
| OMS Securitized booking | `POST /api/securitized/book-trade` — draws from SECURITIZED capital pool |

### Infrastructure Foundation
| Module | Description |
|--------|-------------|
| `EventLog` | Append-only SQLite audit trail; every trade, limit breach, and capital action |
| `InstrumentMaster` | ISIN/CUSIP/product-type registry; 9 seeded instruments |
| `PositionSnapshots` | SQLite-backed position persistence — survives process restarts |
| `APIMetrics` | Daily token spend tracker with $10 alert threshold |
| `ModelRegistry` | SR 11-7 governance lifecycle: status, validator, findings, use authorization |
| `RiskPositionReader` | CQRS second-line read path — replays EventLog independently of PositionManager for 3LoD |

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

Every MDD includes: theoretical basis, mathematical specification, implementation details, validation methodology, limitations, Section 7 use authorization (authorized and prohibited uses, approval chain), and open findings.

The `/models` dashboard surfaces all of this with an AI-powered Q&A: ask Dr. Yuki Tanaka (model builder) or Dr. Samuel Achebe (independent validator) anything about a model — they answer in character from the MDD.

**Model documents:** `model_docs/*.md` (markdown) · `model_docs/latex/*.tex` (LaTeX source) · `model_docs/pdfs/*.pdf` (compiled)

---

## Scenario Engine

Pre-built boardroom scenarios that inject structured market shocks into agent context:

| Scenario | File | Description |
|----------|------|-------------|
| **Founding Board Meeting** | `scenarios/founding_board_meeting.py` | Bank launch — capital deployment, governance, strategic priorities |
| **Consulting Review** | `scenarios/consulting_review_meeting.py` | Meridian Consulting presents findings; management responds |
| **Collateral Mechanics** | `scenarios/collateral_mechanics_meeting.py` | VM call spike, SIMM recalibration, counterparty dispute |
| **Model Risk Remediation** | `scenarios/model_risk_remediation_meeting.py` | Post-audit stakeholder response: SVaR breach, ARRC violation |

`POST /api/scenarios/activate` injects a structured shock into the next agent prompt — agents respond in character without breaking persona.

---

## API Surface

17 route modules, 60+ endpoints, 4 WebSocket streams:

```
# Trading & Capital
POST /api/trading/orders            Submit a market order (7-gate pre-trade check)
GET  /api/trading/blotter           Live OMS blotter with full trade history
GET  /api/trading/greeks            Aggregated Greeks by desk
GET  /api/trading/pnl               Realized + unrealized P&L by desk
GET  /api/capital/allocation        CFO capital allocation — CET1 and RWA budget per desk
GET  /api/capital/consumption       Live RWA consumed per desk (incremental from booked trades)
POST /api/capital/reallocate        CFO intra-quarter desk reallocation
GET  /api/capital/snapshot          Full Basel III capital adequacy (SA-CCR + OpRisk + output floor)
GET  /api/capital/ratios            CET1 / Tier 1 / Total Capital / Leverage
GET  /api/capital/large-exposures   CRE70 counterparty exposure vs 25% T1 limit

# Risk
GET  /api/risk/snapshot             VaR snapshot across all desks (Monte Carlo)
GET  /api/risk/limits               Live limit utilisation (22 limits)
GET  /api/risk/suspensions          Suspended desks and escalation log
POST /api/risk/suspensions/{desk}/lift  CRO desk reinstatement
GET  /api/risk/stressed-var         Stressed VaR calibrated to GFC 2008
GET  /api/risk/ima-status           IMA approval status — exception zone + capital multiplier
GET  /api/risk/independence-check   3LoD CQRS alignment check (EventLog vs PositionManager)

# Treasury
GET  /api/treasury/alm/report       NII/EVE/repricing-gap summary
GET  /api/treasury/ftp/adjusted-pnl FTP-adjusted P&L by desk
GET  /api/treasury/ftp/curve        Live SOFR/UST curve (FRED-calibrated)
GET  /api/stress/dfast              9-quarter DFAST CET1 trajectory
GET  /api/stress/dfast/meta         Active DFAST parameters and data sources

# Collateral & XVA
GET  /api/collateral/simm           SIMM IM by counterparty and risk class
GET  /api/collateral/stress         COVID / Lehman / Gilt Crisis scenarios
GET  /api/xva/summary               Live CVA/DVA/FVA/MVA/ColVA/KVA
GET  /api/xva/pfe                   PFE exposure profile by counterparty

# Securities Finance & Securitized
POST /api/securities-finance/book-trade   Book repo / stock-borrow / prime trade
GET  /api/securities-finance/repo-ladder  Live FRED-priced repo ladder
POST /api/securities-finance/margin/shock Simulate collateral price move, trigger margin calls
POST /api/securitized/book-trade          Book Agency MBS / ABS / CMBS / CLO trade
GET  /api/securitized/mbs-analytics       Live OAS, duration, convexity (PSA + Ho-Lee)

# Compliance & Credit
GET  /api/credit/ecl/portfolio      IFRS 9 ECL summary (50-obligor portfolio)
GET  /api/compliance/aml/stats      AML alert rate and SAR conversion
POST /api/compliance/aml/screen     Screen a transaction against all 6 rule typologies

# Models & Governance
GET  /api/models/registry           Full SR 11-7 model registry
GET  /api/models/{id}/mdd           Model Development Document markdown
GET  /api/models/{id}/pdf           Compiled MDD PDF download
POST /api/models/chat               AI model Q&A — SSE streaming (Dr. Tanaka / Dr. Achebe)

# WebSocket Streams
WS   /ws/boardroom                  Agent turn stream (JSON, each turn labelled by agent)
WS   /ws/market-data                Live price ticks (500ms GBM, 11 tickers)
WS   /ws/xva                        CVA/DVA/FVA live updates on trade submit
WS   /ws/risk                       Risk snapshot push after each trade
```

Full route documentation in [`docs/architecture.md`](docs/architecture.md).

---

## Order Lifecycle

```
Browser / API client
        │
        ▼
POST /api/trading/orders
        │
        ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │                     7-GATE PRE-TRADE CHECK                     │
  │                                                                 │
  │  0. Desk suspended?        → 422 if suspended                  │
  │  1. VaR headroom           → 422 if projected util ≥ 100%      │
  │  2. DV01 / CS01 limit      → 422 if firm DV01 breached         │
  │  3. Equity delta limit     → 422 if net delta > $2B            │
  │  4. Single-name conc.      → 422 if name > 5% of portfolio     │
  │  5. Large Exposure CRE70   → 422 if counterparty > 25% Tier 1  │
  │  6. RWA budget             → 422 if desk RWA headroom < 0      │
  │  7. RAROC gate             → 422 if below hurdle (overridable) │
  └─────────────────────────────────────────────────────────────────┘
        │ All gates pass
        ▼
  PositionManager.add_trade()   — FIFO lot accounting
        │
  GreeksCalculator.compute()    — BSM / DV01 / CS01 for this trade
        │
  RiskService.run_snapshot()    — Monte Carlo VaR → limit update
        │
  CapitalConsumptionTracker     — record incremental RWA
        │
  LimitActionEngine             — check callbacks → suspend if RED
        │
  SecFin/Securitized notional   — update NOTIONAL_SECFIN limit
        │
  SQLite persist + WS broadcast — blotter, XVA refresh, risk push
        │
        ▼
  TradeConfirmation (JSON)
  {trade_id, fill_price, notional, greeks, var_before, var_after,
   limit_status, limit_headroom_pct, pre_trade_message}
```

---

## Architecture

```
                    ┌────────────────────────────────────────┐
                    │       Browser (11 dashboard pages)     │
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
          │  14 BankAgents │  │ VaR ·     │  │ OMS · ALM · FTP │
          │  claude-opus   │  │ Capital · │  │ SIMM · XVA · ECL│
          │  4.6           │  │ Collat ·  │  │ AML · Sec-Fin · │
          │                │  │ DFAST     │  │ RAROC · Suspend │
          └────────────────┘  └───────────┘  └────────┬────────┘
                                                       │
                                   ┌───────────────────▼────────────────────┐
                                   │         External Data Sources           │
                                   │  Yahoo Finance · FRED · pyxva (local)  │
                                   └───────────────────┬────────────────────┘
                                                       │
                                            ┌──────────▼──────────┐
                                            │  SQLite Databases    │
                                            │  positions.db        │
                                            │  oms_trades.db       │
                                            │  events.db (audit)   │
                                            │  instruments.db      │
                                            │  boardroom.db        │
                                            │  metrics.db          │
                                            └─────────────────────-┘
```

Single-process, no message queue, no microservices. Every component is a Python singleton wired at startup. The EventLog provides an append-only audit trail; the `RiskPositionReader` replays it independently of `PositionManager` for 3LoD separation.

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
  main.py                    FastAPI app factory, lifespan, all router registration
  oms_routes.py              Order submission, blotter, trade history (SQLite)
  risk_routes.py             VaR, limits, suspensions, counterparties, 3LoD check
  capital_routes.py          Basel III, RWA, allocation, consumption, reallocate
  treasury_routes.py         ALM, FTP, NII/EVE sensitivity, repo ladder
  collateral_routes.py       CSA, VM calls, SIMM, stress scenarios
  xva_routes.py              CVA/DVA/FVA, PFE, live XVA broadcaster
  securities_finance_routes.py  Repo/SBL analytics + trade booking
  securitized_routes.py      MBS/ABS analytics + trade booking
  stress_routes.py           DFAST 9-quarter projections
  credit_routes.py           IFRS 9 ECL, stage classification
  compliance_routes.py       AML alerts, SAR stats, transaction screening
  models_routes.py           SR 11-7 registry, MDD serving, AI model Q&A
  liquidity_routes.py        LCR, NSFR, intraday monitor, liquidity ladder
  boardroom_routes.py        Boardroom session management + archive
  scenarios_routes.py        Scenario launcher and market shock injection
  trading_routes.py          (shadow-routed by oms_routes; static mock backup)

infrastructure/
  trading/                   OMS, PositionManager, LimitManager, LimitActionEngine, Greeks
  risk/                      VaRCalculator, CorrelationRegimeModel, RegulatoryCapitalEngine,
                             CapitalAllocationFramework, CapitalConsumptionTracker,
                             LimitActionEngine, ConcentrationRisk, LargeExposures, SA-CCR
  treasury/                  ALMEngine, FTPEngine, DynamicFTPEngine, RAROCEngine, BalanceSheetOptimizer
  collateral/                VMEngine, SIMMEngine, CollateralStressScenarios
  credit/                    IFRS9ECLEngine
  stress/                    DFASTEngine
  compliance/                AMLTransactionMonitor
  xva/                       SimulationXVAService, XVAAdapter, XVABroadcaster
  securities_finance/        SecuritiesFinanceService, RepoLadder, MarginEngine
  securitized_products/      SecuritizedProductsService, MBSAnalyticsEngine
  market_data/               MarketDataFeed (GBM), LiveSeed (Yahoo Finance), FREDCurve
  governance/                ModelRegistry (SR 11-7 lifecycle)
  events/                    EventLog (append-only SQLite), EventBus
  reference/                 InstrumentMaster (ISIN/CUSIP registry)
  persistence/               PositionSnapshots (restart-safe)
  metrics/                   APIMetrics (daily token spend)

model_docs/
  registry.json              17-model SR 11-7 registry
  mdd_*.md                   Markdown MDDs
  latex/                     LaTeX source for all MDDs
  pdfs/                      Compiled PDFs

dashboard/                   11 HTML/JS single-page dashboards + shared_nav.js
scenarios/                   Four runnable boardroom scenarios
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
| Dashboard API calls | Zero | All risk/capital/XVA endpoints are local computation |

Rules enforced in code:
- `BankAgent.__init__` requires `max_history` — prevents unbounded context growth
- `BoardroomBroadcaster._history` capped at 200 messages
- `GET /api/metrics/api` — check daily spend before long runs
- `ANTHROPIC_API_KEY` in `.env` only — never committed

---

## Environment Variables

```bash
ANTHROPIC_API_KEY=sk-ant-...    # required — agent calls and model Q&A
```

Everything else — ports, DB paths, tick intervals, risk limits, FTP rates, capital allocation percentages — is configured in code. See [`CLAUDE.md`](CLAUDE.md) for project-specific development conventions.

---

## Research Documents

The `model_docs/pdfs/` directory contains compiled research papers alongside the MDDs:

| Document | Description |
|----------|-------------|
| `bank_quant_operating_model_v1.0.pdf` | Full quantitative operating model: all 17 models, infrastructure, governance |
| `balance_sheet_optimization_v1.0.pdf` | 22-page deep dive: constrained NLP formulation, capital/liquidity/ALM/RAROC math |

---

*Educational and demonstration project. Not connected to real financial infrastructure.*
