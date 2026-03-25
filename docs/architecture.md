# Apex Global Bank — System Architecture

## Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         APEX GLOBAL BANK                            │
│                     AI Agent Simulator v0.2                         │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────── AGENT LAYER ────────────────────────────────┐
│                                                                     │
│  EXECUTIVE         MARKETS              CONTROL        NARRATOR     │
│  ─────────         ───────              ───────        ────────     │
│  CEO               Lead Trader          CRO            Observer     │
│  CTO               Trading Desk         Compliance     (narrates    │
│  CFO               Quant Research       CDO             for reader) │
│                    Market Maker         CISO                        │
│                    Head of IBD          Credit                      │
│                                                                     │
│  3LoD / LEGAL                           ADVISORY                    │
│  ────────────                           ────────                    │
│  Head of Internal Audit                 Meridian Consulting         │
│  General Counsel                        (external board session)    │
│  Model Validation Officer                                           │
└─────────────────────────────────────────────────────────────────────┘
              │              │              │
              ▼              ▼              ▼
┌───────────────────── ORCHESTRATOR ──────────────────────────────────┐
│  Boardroom — facilitates multi-agent discussion sessions            │
│  • Turn management          • Cross-agent context injection         │
│  • Observer narration       • Scenario state injection              │
│  • Transcript export        • SQLite-backed meeting history         │
└─────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌───────────────────── INFRASTRUCTURE ───────────────────────────────┐
│                                                                     │
│  MARKET DATA              TRADING              RISK                 │
│  ──────────               ───────              ────                 │
│  FeedHandler (GBM)        OMS (singleton)      RiskService          │
│  Quote/OHLCV              PositionManager      VaRCalculator (MC)   │
│  MarketDepth              GreeksCalculator     LimitManager         │
│  11 instruments           TradingBroadcaster   CounterpartyRegistry │
│                                                CorrelationRegime    │
│                                                ConcentrationRisk    │
│                                                RegulatoryCapital    │
│                                                                     │
│  CREDIT / COMPLIANCE      TREASURY             REFERENCE            │
│  ────────────────────     ────────             ─────────            │
│  IFRS9 ECL Engine         FTP Engine           InstrumentMaster     │
│  AML Monitor              ALM Engine           EventLog             │
│                                                PositionSnapshots    │
└─────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌───────────────────────── MODELS ────────────────────────────────────┐
│  Instrument · Trade · TradeConfirmation · Position · RiskMetrics    │
│  MarketData · MeetingTurn · BookPosition                            │
└─────────────────────────────────────────────────────────────────────┘
```

## Agents

### Current Roster

| Agent | Model | Role |
|-------|-------|------|
| CEO (Alexandra Chen) | Claude Opus 4.6 | Strategic vision, capital allocation |
| CTO (Marcus Rivera) | Claude Opus 4.6 | Technology architecture, AI platform |
| CRO (Dr. Priya Nair) | Claude Opus 4.6 | Risk framework, VaR, stress testing |
| Lead Trader (James Okafor) | Claude Opus 4.6 | Trading strategy, desk management |
| Trading Desk | Claude Opus 4.6 | Live execution, book management |
| Quant (Dr. Yuki Tanaka) | Claude Opus 4.6 | Pricing/risk models, alpha research |
| Compliance (Sarah Mitchell) | Claude Opus 4.6 | Regulatory compliance, AML/KYC |
| Head of Internal Audit (Jordan Pierce) | Claude Opus 4.6 | 3rd line — independent audit, Audit Committee |
| General Counsel (Margaret Okonkwo) | Claude Opus 4.6 | GC/Corporate Secretary, ISDA, legal entity |
| Model Validation Officer (Dr. Samuel Achebe) | Claude Opus 4.6 | SR 11-7 independent validation |
| Observer | Claude Opus 4.6 | Narrator — explains banking to the reader |

Stub agents (factory functions, not yet deployed): CDO, CISO, Head of Operations, Head of Credit, Head of Market Risk, Head of Rates, Head of Equity Derivatives.

## Infrastructure

### Market Data Feed
- **GBM simulation**: Geometric Brownian Motion price generation, 500ms tick interval
- **Instruments**: 11 instruments (equities: AAPL/MSFT/SPY/NVDA; FX: EURUSD/GBPUSD; rates: US10Y/US2Y; options: AAPL_CALL_200; IRS: USD_IRS_5Y)
- **Subscribers**: Callback pattern — OMS and PositionManager mark-to-market on every tick

### Order Management System (OMS)
- **Submit order**: fill at mid price → pre-trade VaR check → book position → compute Greeks → re-run Monte Carlo VaR snapshot → TradeConfirmation
- **SQLite persistence**: every fill written to `data/oms_trades.db` via aiosqlite
- **WebSocket**: fills, ticks, and position updates pushed to `/ws/trading` clients via `TradingBroadcaster`
- **Blotter**: capped at 1,000 in-memory entries; GET /api/trading/blotter

### Greeks Calculator
- **Equities**: delta = qty × price (delta-1)
- **Bonds (US10Y duration=8.5, US2Y duration=1.9)**: DV01 per bp
- **FX**: USD notional delta
- **Equity options** (`_CALL_` / `_PUT_` in ticker): full Black-Scholes (T=0.25, σ=0.30, r=0.045, multiplier=100)
- **IRS (USD_IRS_5Y)**: DV01 = qty × 0.0004
- Aggregates per-book and portfolio on demand

### Risk Engine
- **VaR**: Monte Carlo (2,000 paths), 99% confidence, 1-day horizon; parametric for pre-trade checks
- **Regime-aware**: normal vs stress correlation matrices (HMM-proxy detection via realized cross-asset vol)
- **Limits**: desk-level VaR limits updated on every trade; headroom % returned in TradeConfirmation
- **Regulatory capital**: Basel III SA RWA with CET1/Tier1/Total/Leverage ratios
- **Concentration risk**: single-name 5%, sector 25%, geography 40% limits with HHI

### Credit & Compliance
- **IFRS 9 ECL**: Stage 1/2/3 classification, 50-obligor sample portfolio, ~1.5-3% coverage ratio
- **AML Monitor**: 6 rule types (sanctions, large-tx, structuring, velocity, round-number, unusual pattern)

### Treasury
- **FTP Engine**: tenor-matched USD swap rate + product liquidity premiums per desk
- **ALM Engine**: 7-bucket repricing gap, NII/EVE sensitivity (+200bps scenarios), behavioral deposit model

## API

```
GET  /api/boardroom/meetings        — list all past boardroom sessions (SQLite)
GET  /api/boardroom/meetings/{id}   — meeting detail + turns
POST /api/boardroom/meetings        — start a new meeting
POST /api/observer/chat             — ask the Observer anything about the simulation
POST /api/trading/orders            — submit a market order (real OMS execution)
GET  /api/trading/blotter           — live blotter from OMS
GET  /api/trading/greeks            — portfolio and per-book Greeks from real positions
GET  /api/trading/pnl               — P&L from PositionManager
GET  /api/risk/snapshot             — full risk snapshot (VaR, limits, positions)
GET  /api/capital/ratios            — Basel III capital ratios
GET  /api/credit/ecl/portfolio      — IFRS 9 ECL summary
GET  /api/compliance/aml/alerts     — AML alerts
GET  /api/treasury/alm/report       — ALM NII/EVE report
WS   /ws/boardroom                  — real-time boardroom transcript stream
WS   /ws/trading                    — fill / tick / positions events
```

## Running the Simulator

```bash
# Install dependencies
pip install -r requirements.txt

# Configure API key
cp .env.example .env
# Edit .env: ANTHROPIC_API_KEY=sk-ant-...

# Start the API server (all 6 dashboard panels)
uvicorn api.main:app --reload

# Open in browser
open http://localhost:8000

# Run founding board meeting (standalone CLI)
python main.py

# List agents
python main.py --list-agents
```

## Dashboard Pages

| Page | URL | Description |
|------|-----|-------------|
| Home | `/` | Landing page with system overview |
| Boardroom | `/boardroom` | Live multi-agent AI boardroom meeting |
| Trading | `/trading` | Trade execution demo + live OMS blotter |
| XVA | `/xva` | CVA/DVA/FVA analytics |
| Models | `/models` | SR 11-7 model governance registry |
| Scenarios | `/scenarios` | Market stress scenario launcher |

## Learning Objectives

After exploring the simulator, you will understand:

1. **Bank structure**: Front/middle/back office divisions and how they interact
2. **Revenue model**: Net interest margin, trading P&L, fee income
3. **Risk management**: VaR (parametric vs Monte Carlo), Greeks, correlation regimes, limit frameworks
4. **Trade lifecycle**: OMS → fill → Greeks → VaR re-run → limit check → blotter → WebSocket broadcast
5. **Regulatory capital**: Basel III SA RWA, CET1 ratios, leverage ratio
6. **Credit risk**: IFRS 9 ECL staging, PD/LGD/EAD framework
7. **Treasury management**: FTP pricing, ALM/NII/EVE sensitivity, duration gap
8. **Compliance**: AML transaction monitoring, three lines of defense
9. **AI in banking**: Multi-agent simulation, cost model, agent persona design
