# Apex Global Bank Simulator — User Manual

> Educational simulation of a JPMorgan-scale bank. Every number is computed by a real quantitative engine. The only thing not real is the money.

---

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env          # add ANTHROPIC_API_KEY
uvicorn api.main:app --reload  # starts on http://localhost:8000
```

Open `http://localhost:8000` for the home dashboard. All 9 panels are accessible from the nav bar.

**Cost note:** The infrastructure engines (VaR, LCR, XVA, DFAST, etc.) run entirely locally — zero API cost. The only calls that spend real Anthropic tokens are live boardroom meetings where AI agents speak. A single 6-agent meeting costs roughly $0.30–$0.80 depending on topic length.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Browser  (9 dashboards — HTML/JS, no framework)            │
│  Trading  Boardroom  XVA  Risk  Treasury  Liquidity  ...    │
└──────────────────────┬──────────────────────────────────────┘
                       │  HTTP + WebSocket
┌──────────────────────▼──────────────────────────────────────┐
│  FastAPI  (api/main.py)                                      │
│  ├── boardroom_routes   trading_routes   risk_routes        │
│  ├── xva_routes         treasury_routes  liquidity_routes   │
│  ├── capital_routes     stress_routes    models_routes      │
│  └── WebSocket: /ws/boardroom  /ws/trading  /ws/xva         │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│  Infrastructure Engines                                      │
│                                                              │
│  MARKET DATA          TRADING             RISK              │
│  MarketDataFeed  →    OMS               → RiskService       │
│  (GBM + live seed)    PositionManager     VaRCalculator     │
│  live_seed.py         GreeksCalculator    LimitManager      │
│  fred_curve.py        PnLCalculator       SA-CCREngine      │
│                                           StressedVaREngine │
│  TREASURY             COLLATERAL          LIQUIDITY         │
│  ALMEngine            VMEngine          → LCREngine         │
│  FTPEngine            SIMMEngine          NSFREngine        │
│  ALMHedgingEngine     XVAAdapter          LiquidityLadder   │
│  RAROCEngine                                                 │
│                                                              │
│  GOVERNANCE           STRESS              AGENTS            │
│  ModelRegistry        DFASTEngine         14× Claude Opus   │
│  (SR 11-7)            dfast_scenarios.py  meeting_orchestr. │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│  SQLite Databases                                            │
│  meetings.db  oms_trades.db  positions.db  events.db        │
│  governance.db  model_registry.db  var_backtest.db          │
└─────────────────────────────────────────────────────────────┘
         ↑
Live data pulled at startup:
  Yahoo Finance → equity/FX/commodity seed prices
  FRED          → SOFR/UST yield curve, ICE BofA credit spreads
  FRED          → UNRATE, GDP, S&P 500 (DFAST macro anchor)
```

---

## 1. The Capital Stack

Before a single trade is placed, the bank's capital structure determines how much risk each desk is allowed to take. Three engines define this:

### 1a. Regulatory Capital (Basel III Pillar 1)

`infrastructure/risk/regulatory_capital.py`

The **RegulatoryCapitalEngine** calculates Risk-Weighted Assets (RWA) by applying Basel III risk weights to every position's notional:

| Asset class | Risk weight |
|---|---|
| US Treasuries | 0% |
| Agency / govt bonds | 20% |
| Investment-grade corp bonds | 50% |
| Equities, CDS, equity options | 100% |
| FX spot | 8% |
| Interest rate swaps | 20% |

Total RWA feeds three capital ratios: **CET1** (Common Equity Tier 1, minimum 4.5%), **Tier 1** (minimum 6%), and **Total Capital** (minimum 8%). Apex carries a $45B CET1 base, producing ~13% CET1 on a $346B baseline RWA.

### 1b. Capital Buffer Stack

`infrastructure/risk/capital_buffers.py`

On top of the regulatory minimums sits the **Combined Buffer Requirement (CBR)**:

```
CET1 floor       4.5%
+ CCB            2.5%   (Capital Conservation Buffer — always required)
+ CCyB           0.0%   (Countercyclical — currently 0%, set by regulators)
+ G-SIB surcharge 1.5%  (Bucket 2 — global systemically important bank)
+ Pillar 2        1.0%  (Supervisory add-on)
─────────────────────────
Total CET1 requirement  9.5%
```

When CET1 falls into the buffer zone, the **Maximum Distributable Amount (MDA)** kicks in — dividends, buybacks, and discretionary bonuses are restricted by quartile (20%–100% restriction as capital erodes toward the floor).

### 1c. Economic Capital & RAROC

`infrastructure/treasury/raroc.py`

Regulatory capital tells you the minimum. Economic capital tells you the real risk cost. The **RAROCEngine** allocates capital to each desk based on its risk profile:

| Desk | EC allocation | Logic |
|---|---|---|
| EQUITY | 8% of AuM | Concentration and gap risk |
| RATES | 3% of notional | DV01-equivalent |
| FX | 6% of gross notional | — |
| CREDIT | 12% of notional | Credit premium |
| DERIVATIVES | 10% of gross notional | — |

**RAROC = (Revenue − Expected Loss − FTP Charge − OpRisk allocation) / Economic Capital**

Hurdle rate: 12%. Desks below hurdle are flagged; the output informs trading limit sizing and capital reallocation decisions.

---

## 2. Live Market Data

On every server start, before the GBM simulation begins, three live fetches anchor the system to real markets:

**Step 1 — Equity, FX, Commodity prices** (`infrastructure/market_data/live_seed.py`)

Yahoo Finance is queried for 10 of 11 simulation tickers (AAPL, MSFT, SPY, NVDA, EURUSD, GBPUSD, CL1, and others). Bond prices are derived from Treasury yields using a first-order DV01 model. The AAPL 200-strike call is priced from live spot (intrinsic + small time value). USD_IRS_5Y stays at par — no Yahoo Finance quote exists for swap rates.

**Step 2 — SOFR / UST yield curve** (`infrastructure/market_data/fred_curve.py`)

12 FRED series are fetched via the public CSV endpoint (no API key required): SOFR overnight, 4-week T-bill, 3M/6M T-bills, and DGS1 through DGS30 (1-year through 30-year Constant Maturity Treasury). These overwrite the `SOFR_OIS` dict in `ftp_dynamic.py` in-place.

**Step 3 — Credit spreads** (`fred_curve.fetch_credit_spreads()`)

ICE BofA option-adjusted spread indices (AAA/AA/A/BBB/HY) are fetched from FRED and used to:
- Scale `BANK_SPREAD_BPS` in the FTP engine (Apex is AA-rated; AA OAS = 53bps today → spreads run 51% above the benign baseline)
- Calibrate `_NORMAL_VOLS["IG_CDX"]` in stressed VaR (BBB OAS = 109bps → credit vol 9% above baseline)
- Dynamically widen LCR stress haircuts when BBB OAS exceeds 200bps

**Step 4 — GBM simulation begins**

`MarketDataFeed` ticks every 500ms using Geometric Brownian Motion seeded from the live anchors above. Every downstream engine that reads prices (VaR, Greeks, XVA, P&L) automatically uses these starting levels.

---

## 3. The Trading Floor

### 3a. Order Lifecycle

All trading flows through a single path: `POST /api/trading/orders`. Here is exactly what happens:

```
Client: POST /api/trading/orders
        { "desk": "EQUITY", "book_id": "EQ_BOOK_1",
          "ticker": "AAPL", "side": "buy", "qty": 1000 }

  1.  OMS acquires _ORDER_LOCK (mutex — orders are serialized)

  2.  MarketDataFeed.get_quote("AAPL") → bid/ask → mid price

  3.  Pre-trade VaR check
      Parametric estimate: est_var = value × desk_vol / √252 × 2.33
      If current_var + est_var ≥ hard_limit → warning flagged
      (Does not block the trade; escalates limit status to RED)

  4.  PositionManager.add_trade(desk, book_id, "AAPL", 1000, mid)
      FIFO lot tracking; returns realised P&L from any closes

  5.  GreeksCalculator.compute("AAPL", 1000, mid)
      Equity → delta = qty × price; no gamma/vega (linear instrument)

  6.  RiskService.run_snapshot()
      ├── Groups all positions by desk
      ├── Monte Carlo VaR per desk (10,000 paths, regime-aware correlation)
      ├── Firm-wide VaR
      └── LimitManager.update(VAR_EQUITY, new_var) [callbacks if status changes]

  7.  Build TradeConfirmation
      { trade_id, ticker, side, qty, fill_price, notional,
        greeks, var_before, var_after, limit_headroom_pct, limit_status,
        pre_trade_approved }

  8.  Release _ORDER_LOCK
      Async (non-blocking):
        _persist_trade() → oms_trades.db
        trading_broadcaster.broadcast_fill() → WebSocket
        xva_service.refresh() → recalculate CVA

  9.  Return TradeConfirmation to client
```

The key design point: **risk is re-snapshotted synchronously inside every trade**. The limit status you receive back reflects the post-trade position, not a stale pre-trade read.

### 3b. Position Management

`infrastructure/trading/position_manager.py`

Positions are tracked at three levels of granularity: **lot → book → desk → firm**. Within a book, FIFO lot accounting applies — selling 500 AAPL closes the oldest lot first and realises that P&L.

The desk → book hierarchy:

| Desk | Books |
|---|---|
| EQUITY | EQ_BOOK_1, EQ_BOOK_2, EQ_BOOK_3 |
| RATES | RATES_BOOK_1, RATES_BOOK_2 |
| FX | FX_BOOK_1, FX_BOOK_2 |
| CREDIT | CREDIT_BOOK_1, CREDIT_BOOK_2 |
| DERIVATIVES | DERIV_BOOK_1, DERIV_BOOK_2 |

`GET /api/trading/pnl` returns the full firm report: realised, unrealised, and total P&L per desk and per book.

### 3c. Greeks

`infrastructure/trading/greeks.py`

The Greeks engine dispatches by instrument type:

- **Equities** (AAPL, MSFT, SPY, NVDA): delta = qty × price; no gamma/vega
- **FX spot** (EURUSD, GBPUSD): delta = qty × spot_rate (USD equivalent)
- **Bonds** (US10Y, US2Y): DV01 = notional × modified_duration × 0.0001 (durations: 8.5yr and 1.9yr)
- **IRS** (USD_IRS_5Y): DV01 = qty × 0.0004 per unit
- **Options** (AAPL_CALL_200): Full Black-Scholes (T=0.25yr, r=4.5%, σ=30%)

`GET /api/trading/greeks` returns portfolio and per-book sensitivities computed from live positions and current mid prices.

### 3d. Limit Framework

`infrastructure/trading/limit_manager.py`

Sixteen risk limits are monitored in real time. Status: GREEN (<80%) → YELLOW (80–89%) → ORANGE (90–99%) → RED (≥100%) → BREACH (>120%).

Key limits:

| Limit | Hard cap | Scope |
|---|---|---|
| VAR_FIRM | $450M | Firm-wide 1-day 99% VaR |
| VAR_EQUITY | $85M | Equity desk VaR |
| VAR_RATES | $120M | Rates desk VaR |
| VAR_FX | $55M | FX desk VaR |
| VAR_CREDIT | $75M | Credit desk VaR |
| VAR_DERIV | $95M | Derivatives desk VaR |
| DV01_FIRM | $25M / bp | Portfolio interest rate sensitivity |
| EQUITY_DELTA | $2B | Net equity delta |
| VEGA_FIRM | $15M / %vol | Firm vega |
| STRESS_GFC | $2.1B | Max loss in 2008 scenario |
| STRESS_RATES_UP | $1.4B | Max loss in +200bp rates shock |

---

## 4. Risk Management

### 4a. Value at Risk

`infrastructure/risk/var_calculator.py`

Three methods are implemented. The one that runs post-trade is **Monte Carlo**:

1. Generate 10,000 correlated random return scenarios using a Cholesky decomposition of the correlation matrix
2. Scale by desk-level daily volatility (annualised vol / √252)
3. Multiply by position notionals; sum across instruments
4. VaR = 1st percentile of the P&L distribution; CVaR = mean of losses worse than VaR

**Correlation regimes:** The `CorrelationRegimeModel` maintains two 6×6 Cholesky matrices — NORMAL (equity-equity ~0.60, equity-credit ~−0.20) and STRESS (equity-equity ~0.90, equity-credit ~−0.80). The engine auto-detects the regime from recent realised returns and selects accordingly. In stress, diversification benefits collapse and VaR surges.

**Stressed VaR (SVaR):** `infrastructure/risk/stressed_var.py` recalibrates volatilities to the 2008–2009 GFC period (equity vol ×3.5, FX ×2.0, credit ×4.0, rates ×2.5) and uses the STRESS correlation matrix. Credit vol is further scaled by live BBB OAS / 100bps baseline. SVaR feeds the Basel 2.5 capital formula:

```
Total Market Risk Capital = VaR_capital + sVaR_capital
where VaR_capital = max(VaR_today, (k/60) × sum(VaR_60d))
k = 3.0 (GREEN) → 4.0 (RED)  based on backtesting exceptions
```

**VaR Backtesting:** `infrastructure/risk/var_backtest_store.py` tracks 250 trading days of hypothetical P&L vs. VaR forecasts. The traffic light system mirrors the Basel Committee standard: 0–4 exceptions (GREEN, k=3.0), 5–9 (YELLOW, k=3.4), 10+ (RED, k=4.0).

**FRTB Boundary:** `infrastructure/risk/frtb_boundary.py` classifies every position as Trading Book or Banking Book. Equities (listed), FX spot, IRS, CDS, and listed options are Trading Book. Loans, mortgages, HTM securities, and unlisted equity are Banking Book.

### 4b. Counterparty Credit Risk (SA-CCR)

`infrastructure/risk/sa_ccr.py`

The **Standardised Approach for Counterparty Credit Risk** (Basel III CRE52) computes Exposure at Default for OTC derivatives:

```
EAD = 1.4 × (RC + PFE_aggregate)

RC  = Replacement Cost (MTM proxy adjusted for collateral)
PFE = Add-on × Multiplier
Multiplier = min(1, 0.05 + 0.95 × exp((MTM − Collateral) / (2 × 0.95 × AddOn)))
```

Add-ons by asset class use Basel supervisory factors: IR (0.5–1.5% depending on tenor), FX (4%), Credit (0.38–6% by rating), Equity single-name (32%), Commodity (10–18%).

Five netting sets are pre-seeded: Goldman Sachs (IR swaps), JPMorgan (FX forwards), Deutsche Bank (CDS), BNP Paribas (equity swaps), HSBC (commodity + IR).

**CounterpartyRegistry** monitors PFE utilisation against limits for each counterparty ($800M–$2B). Status appears on the Risk dashboard's counterparty pressure table.

---

## 5. Collateral & XVA

### 5a. Collateral Framework

`infrastructure/collateral/`

Five bilateral CSAs (Credit Support Annexes) are maintained, plus one CCP-cleared relationship (LCH):

| CSA | Counterparty | Threshold | MTA | Initial Margin held |
|---|---|---|---|---|
| CSA-GS-001 | Goldman Sachs | $0 | $500k | $120M |
| CSA-JPM-001 | JPMorgan | $0 | $500k | $95M |
| CSA-DB-001 | Deutsche Bank | $0 | $1M | $75M |
| CSA-MER-001 | Meridian Capital | $10M | $1M | $0 |
| CSA-LCH-001 | LCH (CCP) | $0 | $0 | $850M |

**Variation Margin** (`vm_engine.py`): Daily MTM movements trigger margin calls when the net uncollateralised exposure exceeds the MTA. Call lifecycle: PENDING → SETTLED (T+1 bilateral, same-day CCP). The engine can simulate counterparty stress: DISPUTE (15% contested), LATE (T+3 settlement), or DEFAULT (close-out triggered).

**Initial Margin** (`simm.py`): The ISDA SIMM 2.6 model computes IM from IR DV01 sensitivities (weighted by tenor-specific risk weights, 49–77bps) and Credit CS01 sensitivities (weighted by rating, 38–369bps), aggregated with intra-bucket correlations. The total IM is `sqrt(K_IR² + K_CRQ² + 2×0.20×K_IR×K_CRQ)`.

### 5b. XVA Pipeline

`infrastructure/xva/service.py`

XVA (Cross-Valuation Adjustments) translates counterparty credit risk into a P&L charge:

```
OMS blotter (fills across desks)
    │
    ▼  SimulationXVAService._map_fills_to_pyxva_config()
    │  Desk → counterparty assignment:
    │    RATES / DERIVATIVES → Goldman Sachs, JPMorgan, Deutsche Bank
    │    FX                  → BNP Paribas, HSBC
    │    EQUITY / CREDIT     → Goldman Sachs, JPMorgan
    │
    ▼  Equity positions: CVA computed analytically
    │    CVA = LGD × spread × notional × tenor  (LGD=60%, spread=150bps)
    │
    ▼  Non-equity positions: pyxva RiskEngine
    │    Hull-White 1-Factor rates model, 2,000 Monte Carlo paths
    │    Outputs: EE profile, PFE 97.5%, CVA, DVA, FVA, KVA
    │
    ▼  Broadcast to /ws/xva + cache result
    │
    ▼  XVA Dashboard  (badge: DEMO → LIVE when OMS has fills)
```

`POST /api/xva/pre-trade` provides a parametric CVA estimate for a new trade before execution: `CVA ≈ −LGD × spread × EEPE% × notional × tenor`. Useful for pricing credit cost into new deals.

---

## 6. Treasury & ALM

The Treasury layer sits between trading and the balance sheet. It answers: *What does the bank's interest rate exposure look like, and what does it cost to fund each desk?*

### 6a. ALM Engine

`infrastructure/treasury/alm.py`

The bank's $3.2T balance sheet is segmented into 7 repricing buckets (overnight through 5Y+). The engine computes:

- **Repricing gap** per bucket (rate-sensitive assets minus liabilities)
- **NII sensitivity** to rate shocks (±100bps, ±200bps)
- **EVE sensitivity** — present value of equity under rate shocks (SVB-style +200bps warning if EVE falls >15%)

**Non-Maturity Deposits (NMD):** `infrastructure/treasury/nmd_model.py` applies behavioral modelling to $1.4T of deposits across four segments (retail checking, retail savings, commercial operating, commercial non-operating). Beta coefficients (0.15–0.75) determine how much of each rate movement is passed through to depositors, affecting the effective duration of liabilities. This feeds directly into the duration gap calculation.

### 6b. ALM Hedging Engine

`infrastructure/treasury/alm_hedging.py`

Key Rate Duration (KRD) is computed at 10 points on the curve (3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y). Each balance sheet item (loans, mortgages, securities, NMD deposits, wholesale funding, subordinated debt) has a weight distribution across those key rates.

The current duration gap of +2.2 years (assets 4.8yr, liabilities 2.6yr) means the bank is asset-sensitive: rising rates reduce economic value. The engine recommends a receive-fixed IRS at 5Y to close the gap, with sizing derived from EVE sensitivity / DV01 of the swap.

### 6c. Dynamic FTP

`infrastructure/treasury/ftp_dynamic.py`

Every desk pays an internal funding charge based on the **SOFR OIS curve + bank credit spread + instrument liquidity premium**. As of startup:

- The SOFR OIS curve is overwritten from FRED (O/N SOFR = 3.65%, 10Y = 4.31%)
- Bank spreads are scaled by live AA OAS (currently 1.51× the historical 35bps baseline)
- All-in 5Y FTP rate ≈ 3.94% + 0.91% spread = 4.85%

This ensures desk P&L is economically meaningful: a rates desk that earns 4.5% on a bond but pays 4.85% FTP is actually losing money on a risk-adjusted basis.

---

## 7. Liquidity Risk

`infrastructure/liquidity/`

Three complementary views of the bank's liquidity position:

### LCR — Liquidity Coverage Ratio

Ensures the bank can survive a 30-day stress period using only its High-Quality Liquid Asset (HQLA) buffer.

```
LCR = HQLA / Net Cash Outflows ≥ 100%

HQLA breakdown:
  Level 1 Sovereign (UST)  $280B   0% haircut
  Level 2A Agency          $95B   15% haircut
  Level 2B Corp BBB        $45B   50% haircut
  ─────────────────────────────────────────────
  Total adjusted HQLA      ≈$376B

30-day stress outflows:
  Wholesale financial books   100% outflow (major NCO driver)
  Retail stable deposits       3% outflow
  Retail less-stable          10% outflow
  Committed credit facilities 10–40% outflow
  ─────────────────────────────────────────────
  Total NCO                   ≈$580B

LCR = 376 / 580 = 64.8%  [BREACH]
```

The breach is intentional — the large wholesale financial book ($200B at 100% outflow) creates a realistic stress gap for demonstration purposes. Under a market-wide stress scenario, BBB OAS from FRED dynamically widens the L2B haircut by an additional 5%.

### NSFR — Net Stable Funding Ratio

Ensures longer-term funding stability (1-year horizon).

```
NSFR = Available Stable Funding / Required Stable Funding ≥ 100%
     = $1.6T / $1.4T = 153.6%  [COMPLIANT]
```

### Liquidity Ladder

`infrastructure/liquidity/ladder.py` breaks the balance sheet into 9 maturity buckets with behavioral overlays (deposits are stickier than contractual maturity; loans prepay). The cumulative cash gap turns positive after approximately **180 days** — the survival horizon without external funding.

---

## 8. Stress Testing (DFAST)

`infrastructure/stress/dfast_engine.py`

The engine runs a 9-quarter forward capital adequacy projection under three macro scenarios, consistent with the Fed's Dodd-Frank Act Stress Testing framework.

**Scenarios** (2025 Federal Reserve official parameters, calibrated to live macro via FRED):

| Scenario | GDP/yr | Unemployment peak | Equity shock | Rate change |
|---|---|---|---|---|
| Baseline | +2.2% | 4.1% (−0.2pp) | +3% | −30bps |
| Adverse | −0.8% | 6.4% (+2.1pp) | −15% | −280bps |
| Severely Adverse | −3.6% | 10.0% (+5.7pp) | −55% | −350bps |

**Capital equation per quarter:**
```
CET1(Q) = CET1(Q−1) + PPNI − credit_losses − trading_losses
RWA(Q)  = RWA(Q−1) × (1 + rwa_growth_rate)
CET1 ratio(Q) = CET1(Q) / RWA(Q)
```

Credit losses scale with unemployment via IFRS 9 PD overlays (β_UR = 0.06 per pp rise in unemployment). Trading losses scale with the equity shock.

`GET /api/stress/dfast/meta` returns the active scenario parameters and their source (DFAST 2025 Official / FRED).

---

## 9. Model Governance (SR 11-7)

`infrastructure/governance/model_registry.py`

The Federal Reserve's SR 11-7 guidance requires a documented lifecycle for every quantitative model: development → validation → approval → production → periodic review. The registry tracks 17 models:

| Model ID | Name | Status | Capital approved |
|---|---|---|---|
| MOD-001 | Market Risk VaR (Historical Simulation) | Production | Yes |
| MOD-002 | Monte Carlo VaR | Production | Yes |
| MOD-003 | IFRS 9 ECL Engine | Production | Yes |
| MOD-004 | Black-Scholes Option Pricer | Production | Yes |
| MOD-005 | Hull-White 1F (XVA) | Production | Yes |
| MOD-006 | LIBOR Market Model | In Validation | No |
| MOD-007 | SA-CCR | Production | Yes |
| MOD-008 | ISDA SIMM 2.6 | Production | Yes* |
| ... | ... | ... | ... |

*SIMM is marked APPROXIMATION ONLY with 4 limitation disclosures (IR-only, CRQ-only, no commodity/equity, no cross-gamma).

The **Models dashboard** shows validation status, open findings, and expiry dates. It also hosts an AI Q&A interface: ask Dr. Yuki Tanaka (model builder) or Dr. Samuel Achebe (validator) any question about a specific model — their responses are grounded in the full MDD (Model Development Document) for that model.

---

## 10. The Boardroom

`api/meeting_orchestrator.py`

The boardroom simulates a live executive committee meeting. Each agent is a **Claude Opus 4.6** instance with a deep domain-specific system prompt defining their expertise, communication style, and institutional mandate.

**14 agents:**

| Agent | Title | Domain focus |
|---|---|---|
| Alexandra Chen | CEO | Strategy, franchise risk, accountability |
| Dr. Priya Nair | CRO | Downside protection, tail scenarios, limits |
| Diana Osei | CFO | Capital allocation, earnings quality |
| Marcus Rivera | CTO | Platform resilience, technology delivery |
| Dr. Yuki Tanaka | Head of Quant Research | Model validity, calibration assumptions |
| James Okafor | Head of Global Markets | P&L, flow, market timing |
| Sarah Mitchell | CCO | Regulatory exposure, conduct risk |
| Amara Diallo | Head of Treasury & ALM | Liquidity, funding cost, NII |
| Jordan Pierce | Head of Internal Audit | 3rd line independence, adversarial |
| Margaret Okonkwo | General Counsel | ISDA netting, legal entity governance |
| Dr. Samuel Achebe | Model Validation Officer | SR 11-7 independence, findings |
| Dr. Fatima Al-Rashid | CDO | Data lineage, AI/ML risk |
| The Observer | Independent Narrator | Explains dynamics, no agenda |
| Meridian Consultant | External Advisor | Peer benchmarking, outside-in view |

**Meeting flow:**

```
1. User starts meeting with a topic (or picks from preset scenarios)
2. Orchestrator builds context prompt:
   ├─ Active market scenario (if any) — current prices, shocks
   ├─ Board meeting topic
   └─ Full transcript of prior turns (capped at last 20)
3. Each agent speaks in sequence, streaming tokens via WebSocket
4. Completed turn persisted to SQLite (MeetingStore)
5. Next agent receives full transcript including prior agent's words
6. "Board asked" injections accepted at any time (POST /api/boardroom/inject)
7. Session concludes; transcript available for replay
```

Sessions are archived to the SQLite `meetings.db` and appear in the Boardroom dashboard's session list. Inline discussions (generated outside a live meeting) can also be archived via `POST /api/boardroom/archive`.

---

## 11. Dashboard Reference

| Dashboard | URL | What it shows |
|---|---|---|
| **Home** | `/` | Platform stats, quick-launch cards, API health |
| **Boardroom** | `/boardroom` | Live agent stream, session archive, scenario injection |
| **Trading** | `/trading` | Open positions, P&L by desk, order blotter, Greeks heatmap, CCR limits |
| **XVA Analytics** | `/xva` | CVA/DVA/FVA/KVA by counterparty, PFE exposure profile, pre-trade CVA estimator |
| **Risk** | `/risk` | Limit monitor (16 limits), VaR backtesting traffic light, FRTB boundary, counterparty pressure |
| **Treasury** | `/treasury` | Repricing gap, NII/EVE sensitivity, KRD profile, hedge recommendations, FTP curve, RAROC by desk |
| **Liquidity** | `/liquidity` | LCR gauge, NSFR gauge, HQLA breakdown, maturity ladder, intraday cash flow, stress scenarios |
| **Securities Finance** | `/securities-finance` | Matched-book repo, stock borrow/loan, prime brokerage, funding watchlist |
| **Securitized Products** | `/securitized` | Agency MBS, ABS, CMBS, CLO inventory, OAS/duration/convexity, relative value screen |
| **Model Governance** | `/models` | SR 11-7 registry, validation status, AI-powered model Q&A |
| **Scenarios** | `/scenarios` | Shock designer, XVA stress comparison, DFAST 9-quarter chart |

---

## 12. Complete System Flow

```
STARTUP SEQUENCE
────────────────
Yahoo Finance → live_seed.py → MarketDataFeed._prices (10/11 tickers)
FRED           → fred_curve.py → SOFR_OIS (12 tenors) → ftp_dynamic.py
FRED           → fetch_credit_spreads() → BANK_SPREAD_BPS, IG_CDX_vol, LCR_haircuts
FRED           → dfast_scenarios.py → SCENARIOS (UNRATE, GDP, S&P 500)
MarketDataFeed.start() → GBM ticks every 500ms


TRADING FLOW (per order)
─────────────────────────
   Capital stack       Market data        Trading layer
   ┌──────────┐        ┌──────────┐       ┌──────────────────────────┐
   │Regulatory│        │LiveFeed  │       │OMS.submit_order()        │
   │Capital   │        │(GBM from │  ──►  │  pre-trade VaR check     │
   │Buffers   │  limit │live seed)│       │  PositionManager (FIFO)  │
   │RAROC     │  sizing│          │       │  GreeksCalculator        │
   └──────────┘        └──────────┘       │  RiskService.run_snapshot│
        │                                 └────────────┬─────────────┘
        │ (hard limits flow into LimitManager)         │
        │                                              ▼
        │                                    ┌─────────────────────┐
        │                                    │Risk layer           │
        │                                    │VaRCalculator (MC)   │
        │                                    │LimitManager update  │
        │                                    │StressedVaR          │
        │                                    │SA-CCREngine         │
        │                                    └────────┬────────────┘
        │                                             │
        │                                             ▼
        │                              ┌──────────────────────────┐
        │                              │Collateral & XVA          │
        │                              │VMEngine (margin calls)   │
        │                              │SIMMEngine (initial margin│
        │                              │SimulationXVAService      │
        │                              │  → CVA/DVA/FVA/KVA       │
        │                              └────────────┬─────────────┘
        │                                           │
        ▼                                           ▼
   ┌─────────────────────┐             ┌────────────────────────────┐
   │Treasury & ALM        │             │Dashboards (9 panels)       │
   │ALMEngine (NII/EVE)  │             │Real-time via WebSocket     │
   │NMDModel (deposits)  │             │  Trading  Risk  XVA        │
   │ALMHedgingEngine(KRD)│             │  Treasury Liquidity Board  │
   │DynamicFTPEngine     │             └────────────────────────────┘
   │RAROCEngine           │
   └──────────┬──────────┘
              │
              ▼
   ┌────────────────────────┐
   │Liquidity & Stress      │
   │LCREngine               │
   │NSFREngine              │
   │LiquidityLadder         │
   │DFASTEngine (9-quarter) │
   └────────────────────────┘
              │
              ▼
   ┌────────────────────────────────────────────────────────┐
   │Boardroom (14 AI agents)                                │
   │All live market data, scenario shocks, and risk metrics │
   │are injected into every agent's context prompt so their │
   │discussion reflects the current state of the bank.     │
   └────────────────────────────────────────────────────────┘
```

---

## Appendix: Key API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Server and bank status |
| `/api/trading/orders` | POST | Submit a market order |
| `/api/trading/blotter` | GET | Last 50 fills from OMS |
| `/api/trading/greeks` | GET | Live portfolio Greeks |
| `/api/trading/pnl` | GET | P&L by desk and book |
| `/api/risk/snapshot` | GET | VaR, limits, breaches |
| `/api/risk/backtesting` | GET | 250-day backtest results |
| `/api/risk/stressed-var` | GET | SVaR capital calculation |
| `/api/capital/snapshot` | GET | Full Basel III capital view |
| `/api/capital/sa-ccr` | GET | SA-CCR EAD per netting set |
| `/api/capital/buffers` | GET | CCB/CCyB/G-SIB buffer stack |
| `/api/xva/live` | GET | XVA from live OMS blotter |
| `/api/xva/pre-trade` | POST | Parametric CVA estimate |
| `/api/treasury/alm/hedge-recommendations` | GET | KRD-based hedge sizing |
| `/api/treasury/ftp/curve-dynamic` | GET | Live SOFR + bank spread curve |
| `/api/treasury/ftp/raroc` | GET | RAROC by desk |
| `/api/liquidity/lcr` | GET | Full LCR calculation |
| `/api/liquidity/nsfr` | GET | Full NSFR calculation |
| `/api/liquidity/ladder` | GET | Maturity ladder + survival horizon |
| `/api/stress/dfast` | GET | All 3 DFAST scenarios × 9 quarters |
| `/api/stress/dfast/meta` | GET | Active scenario params + source |
| `/api/models/governance/registry` | GET | Full SR 11-7 model registry |
| `/api/boardroom/start` | POST | Start a live AI meeting |
| `/api/boardroom/archive` | POST | Persist an inline discussion |
| `/api/boardroom/meetings` | GET | All past sessions |
| `/ws/boardroom` | WS | Live meeting stream |
| `/ws/trading` | WS | Live trade fills + price ticks |
| `/ws/xva` | WS | Live XVA updates |
