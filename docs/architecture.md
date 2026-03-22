# Apex Global Bank — System Architecture

## Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         APEX GLOBAL BANK                            │
│                     AI Agent Simulator v1.0                         │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────────────── AGENT LAYER ────────────────────────────────┐
│                                                                     │
│  EXECUTIVE         MARKETS              CONTROL        NARRATOR     │
│  ─────────         ───────              ───────        ────────     │
│  CEO               Lead Trader          CRO            Observer     │
│  CTO               Trading Desk         Compliance     (narrates    │
│  [CFO]             Quant Research       [CDO]           for reader) │
│                    [Market Maker]       [CISO]                      │
│                    [Head of IBD]        [Credit]                    │
│                                                                     │
│  [] = proposed future agents                                        │
└─────────────────────────────────────────────────────────────────────┘
              │              │              │
              ▼              ▼              ▼
┌───────────────────── ORCHESTRATOR ──────────────────────────────────┐
│  Boardroom — facilitates multi-agent discussion sessions            │
│  • Turn management          • Cross-agent context injection         │
│  • Observer narration       • Transcript export                     │
└─────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌───────────────────── INFRASTRUCTURE ───────────────────────────────┐
│                                                                     │
│  MARKET DATA              TRADING              RISK                 │
│  ──────────               ───────              ────                 │
│  FeedHandler (GBM)        OrderBook (CLOB)     VaRCalculator        │
│  Quote/OHLCV              ExecutionEngine      StressTester         │
│  MarketDepth              PositionManager      LimitManager         │
│                           AlgoEngine           PnLCalculator        │
│                                                                     │
│  COMPLIANCE                                                         │
│  ──────────                                                         │
│  AMLMonitor               KYCEngine            RegulatoryReporter   │
└─────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌───────────────────────── MODELS ────────────────────────────────────┐
│  Instrument · Trade · Position · RiskMetrics · MarketData           │
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
| Trading Desk | Claude Opus 4.6 | Live execution, book management, real-time hedging |
| Quant (Dr. Yuki Tanaka) | Claude Opus 4.6 | Pricing/risk models, alpha research |
| Compliance (Sarah Mitchell) | Claude Opus 4.6 | Regulatory compliance, AML/KYC |
| Observer | Claude Opus 4.6 | Narrator — explains banking to the reader |

### Proposed Additional Agents

| Agent | Priority | Rationale |
|-------|----------|-----------|
| CFO | High | Capital allocation, P&L reporting, investor relations |
| Chief Credit Officer | High | Loan portfolio — often >50% of bank revenue |
| Head of Operations | High | Settlement, clearing — the hidden machinery |
| Head of Treasury | High | Liquidity, funding, balance sheet management |
| CDO | Medium | Data governance — the AI fuel |
| CISO | Medium | Cyber risk — existential threat |
| Head of Investment Banking | Medium | Advisory revenue — M&A, ECM, DCM |
| Head of Wealth Management | Medium | Fee income — private banking |

## Infrastructure

### Market Data Feed
- **GBM simulation**: Geometric Brownian Motion price generation
- **Instruments**: 9 instruments across equities, FX, rates, commodities
- **Tick interval**: Configurable (default 500ms)
- **Subscribers**: Callback pattern — agents register to receive quotes

### Order Book
- **Type**: Central Limit Order Book (CLOB)
- **Priority**: Price-time (best price wins; ties go to earliest order)
- **Order types**: Market, Limit (Stop and Algo planned)
- **Thread safety**: Single-threaded asyncio model

### Risk Engine
- **VaR methods**: Historical Simulation, Parametric, Monte Carlo
- **Confidence**: 99% (regulatory standard)
- **Horizon**: 1-day (regulatory) or 10-day (Basel)
- **Stress scenarios**: GFC 2008, COVID 2020, Rates Shock, Geopolitical

## Running the Simulator

```bash
# Install dependencies
pip install -r requirements.txt

# Configure API key
cp .env.example .env
# Edit .env: ANTHROPIC_API_KEY=sk-ant-...

# Run founding board meeting
python main.py

# List agents
python main.py --list-agents

# Dry run (no API calls)
python main.py --dry-run

# Custom export path
python main.py --export my_transcript.md
```

## Learning Objectives

After running the founding board meeting scenario, you will understand:

1. **Bank structure**: The functional divisions (front/middle/back office) and how they interact
2. **Revenue model**: How banks actually make money (NIM, trading, fees)
3. **Risk management**: VaR, stress testing, Greeks, and why they matter
4. **Trading operations**: Market-making, order flow, hedging, and execution
5. **Regulatory framework**: Basel III, Dodd-Frank, MiFID II at a conceptual level
6. **AI in banking**: Where it creates value and where it creates new risks
7. **Technology**: Why banking technology is so complex (latency, reliability, legacy debt)
8. **Compliance**: AML/KYC, the three lines of defense, and what happens when it fails
