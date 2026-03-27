# Apex Global Bank — System Architecture (v0.2.0.0)

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         APEX GLOBAL BANK SIMULATOR                          │
│               AI-native JP-Morgan-scale bank — educational/demo             │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────── AGENT LAYER ────────────────────────────────┐
│                                                                             │
│  EXECUTIVE             MARKETS              CONTROL             NARRATOR     │
│  ─────────             ───────              ───────             ────────     │
│  CEO (Alexandra Chen)  Lead Trader          CRO (Priya Nair)   Observer     │
│  CTO (Marcus Rivera)   (James Okafor)       CCO (S.Mitchell)               │
│  CFO (Diana Osei)      Quant Researcher     CDO (Fatima)                    │
│  CCO Credit            (Dr. Yuki Tanaka)    CISO (Ivan)                     │
│  Head of Treasury                                                           │
│  (Amara Diallo)                                                             │
│                                                                             │
│  3LoD / LEGAL                               ADVISORY                        │
│  ────────────                               ────────                        │
│  Jordan Pierce (Audit) Margaret Okonkwo     Meridian Consulting             │
│  Dr. Samuel Achebe     (General Counsel)    (external board)                │
│  (Model Validation)                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────── ORCHESTRATOR ───────────────────────────────────┐
│  Boardroom (orchestrator/boardroom.py)                                      │
│  • Turn management + cross-agent context injection                          │
│  • Observer narration  • Scenario state injection                           │
│  • Transcript export   • SQLite-backed meeting history (MeetingStore)       │
└─────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────── API LAYER ──────────────────────────────────────┐
│  FastAPI (api/main.py)  +  WebSocket hubs  +  route modules                │
│                                                                             │
│  boardroom_routes  oms_routes     risk_routes    treasury_routes            │
│  observer_routes   trading_routes capital_routes credit_routes              │
│  xva_routes        collateral_routes scenarios_routes compliance_routes     │
│  securities_finance_routes  securitized_routes                              │
│  models_routes     metrics_routes                                           │
│                                                                             │
│  WS /ws/boardroom (BoardroomBroadcaster, 200-msg history cap)               │
│  WS /ws/trading   (TradingBroadcaster)                                      │
└─────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────── INFRASTRUCTURE ─────────────────────────────────┐
│                                                                             │
│  MARKET DATA          TRADING                RISK                          │
│  ───────────          ───────                ────                          │
│  FeedHandler(GBM)     OMS ──────────────▶   RiskService (singleton owner) │
│  Quote/OHLCV          PositionManager ◀───   VaRCalculator (MC/hist/param) │
│  11 instruments       GreeksCalculator        LimitManager (20 limits)     │
│  500ms ticks          LimitManager            CounterpartyRegistry         │
│                       TradingBroadcaster       CorrelationRegimeModel       │
│                                               ConcentrationRiskMonitor     │
│                                               RegulatoryCapital (Basel III)│
│                                                                             │
│  TREASURY             CREDIT/COMPLIANCE       COLLATERAL (v0.1.4.0)        │
│  ────────             ────────────────        ──────────────────────        │
│  FTPEngine            IFRS9ECLEngine          CSA / CollateralAccount      │
│  ALMEngine            AMLTransactionMonitor   VMEngine / SIMM              │
│                                               StressScenarios              │
│                                                                             │
│  SECURITIES FINANCE   SECURITIZED PRODUCTS                                  │
│  ──────────────────   ─────────────────────                                 │
│  Repo / stock-loan    Agency MBS / ABS / CMBS / CLO desk view              │
│  Prime financing      OAS / duration / convexity / stress analytics        │
│                                                                             │
│  REFERENCE / PERSISTENCE / EVENTS                                           │
│  ────────────────────────────────                                           │
│  InstrumentMaster     PositionSnapshotStore   EventLog (append-only)       │
│  APIMetrics                                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌──────────────────────────── DATA LAYER ─────────────────────────────────────┐
│  SQLite databases (data/)                                                   │
│  meetings.db  oms_trades.db  events.db  instruments.db                     │
│  position_snapshots.db  collateral.db                                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Application Startup Sequence

`uvicorn api.main:app --reload` triggers the FastAPI lifespan in strict order:

```
1.  MeetingStore.initialize()          → data/meetings.db + schema
2.  mkdir data/
3.  EventLog singleton                 → data/events.db + schema
4.  InstrumentMaster singleton         → data/instruments.db + seed 9 instruments
5.  MarketDataFeed(SEED_PRICES)
    └─ asyncio.ensure_future(feed.start())   ← 500ms GBM tick loop in background
6.  oms.set_feed(feed)                 → wires live quotes into OMS
7.  risk_service.add_sample_positions()
    └─ 9 seed trades: AAPL, MSFT, NVDA, US10Y, US2Y, EURUSD, GBPUSD, HYEM_ETF, SPX_CALL
8.  await _init_db()                   → data/oms_trades.db + schema
9.  Register route modules (graceful try/except around each):
    boardroom → xva → models → scenarios →
    oms_routes (before trading_routes — shadows /blotter, /greeks, /pnl, /ccr) →
    trading → observer → risk → capital → treasury → credit →
    compliance → metrics → collateral
```

Shutdown: `feed.stop()` gracefully halts the GBM loop.

---

## 3. Singleton Ownership

Every stateful service is a module-level singleton. There is no DI container — singletons reference each other by direct import.

| Singleton | Module | Notes |
|-----------|--------|-------|
| `risk_service` | `infrastructure.risk.risk_service` | Owns `PositionManager` + `LimitManager` |
| `oms` | `infrastructure.trading.oms` | Writes through `risk_service.position_manager` |
| `broadcaster` | `api.boardroom_broadcaster` | WebSocket hub — 200-msg history cap |
| `trading_broadcaster` | `api.trading_broadcaster` | WebSocket hub for fills + ticks |
| `store` | `api.meeting_store` | SQLite meeting persistence |
| `scenario_state` | `api.scenario_state` | Thread-safe active scenario holder |
| `_feed` | created in `api.main` lifespan | GBM market data feed |
| `event_log` | `infrastructure.events.event_log` | Append-only audit SQLite |
| `instrument_master` | `infrastructure.reference.instrument_master` | ISIN/ticker registry |
| `snapshot_store` | `infrastructure.persistence.position_snapshots` | Position write-through |
| `counterparty_registry` | `infrastructure.risk.counterparty_registry` | 5 seeded counterparties |
| `_observer` | `api.observer_routes` | Lazy — created on first `/api/observer/chat` |

**State ownership rule**: `PositionManager` is owned exclusively by `risk_service`. The OMS writes through it. All read paths (treasury, risk, OMS routes) call `risk_service.position_manager.*`. No second `PositionManager()` is ever constructed after startup.

---

## 4. API Route Inventory

### Trading / OMS

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/trading/orders` | Submit market order → `TradeConfirmation` |
| `GET`  | `/api/trading/blotter` | Last 50 fills from OMS |
| `GET`  | `/api/trading/greeks` | Portfolio + per-book Greeks |
| `GET`  | `/api/trading/pnl` | Firm P&L by desk and book |
| `GET`  | `/api/trading/ccr` | Counterparty credit risk |

### Boardroom & Observer

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/boardroom/meetings` | List all sessions |
| `GET`  | `/api/boardroom/meetings/{id}` | Session detail + turns |
| `GET`  | `/api/boardroom/meetings/{id}/transcript` | Export as JSON |
| `POST` | `/api/boardroom/start` | Start new meeting |
| `POST` | `/api/boardroom/agent/speak` | Streaming agent response (SSE) |
| `POST` | `/api/observer/chat` | Observer Q&A |

### Risk

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/risk/snapshot` | VaR + limits + breach report |
| `GET`  | `/api/risk/limits` | All limit utilization |
| `GET`  | `/api/risk/limits/{name}` | Single limit detail |
| `GET`  | `/api/risk/counterparties` | Counterparty credit data |
| `GET`  | `/api/risk/positions` | Current positions |
| `POST` | `/api/risk/var` | On-demand VaR calculation |

### Regulatory Capital

| Method | Path |
|--------|------|
| `GET`  | `/api/capital/snapshot` |
| `GET`  | `/api/capital/rwa` |
| `GET`  | `/api/capital/ratios` |
| `GET`  | `/api/capital/concentration` |
| `POST` | `/api/capital/stress` |

### Treasury

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/treasury/ftp/summary` | FTP charges by desk |
| `GET`  | `/api/treasury/ftp/adjusted-pnl` | P&L net of funding cost |
| `GET`  | `/api/treasury/ftp/curve` | Swap curve snapshot |
| `GET`  | `/api/treasury/alm/report` | Full ALM report |
| `GET`  | `/api/treasury/alm/nii-sensitivity` | NII by rate scenario |
| `GET`  | `/api/treasury/alm/eve-sensitivity` | EVE by rate scenario |
| `GET`  | `/api/treasury/alm/repricing-gap` | 7-bucket repricing schedule |

### Securities Finance

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/securities-finance/overview` | Top-line funding and margin view |
| `GET`  | `/api/securities-finance/books` | Repo / prime / stock-loan books |
| `GET`  | `/api/securities-finance/inventory` | Lendable inventory and specials |
| `GET`  | `/api/securities-finance/client-financing` | Client financing book |
| `GET`  | `/api/securities-finance/stress` | Balance-sheet stress view |

### Securitized Products

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/securitized/overview` | Desk OAS / duration / sector mix |
| `GET`  | `/api/securitized/inventory` | Inventory across agency and spread sleeves |
| `GET`  | `/api/securitized/relative-value` | Net carry / OAS screen |
| `GET`  | `/api/securitized/stress` | Rates + vol + spread shock |
| `GET`  | `/api/securitized/pipeline` | Build roadmap for the desk |

### Credit

| Method | Path |
|--------|------|
| `GET`  | `/api/credit/ecl/portfolio` |
| `GET`  | `/api/credit/ecl/obligors` |
| `GET`  | `/api/credit/ecl/stage` |
| `POST` | `/api/credit/ecl/scenario` |

### Compliance / AML

| Method | Path |
|--------|------|
| `GET`  | `/api/compliance/aml/alerts` |
| `GET`  | `/api/compliance/aml/stats` |
| `POST` | `/api/compliance/aml/screen` |
| `PATCH`| `/api/compliance/aml/alerts/{id}` |

### Collateral (v0.1.4.0)

| Method | Path |
|--------|------|
| `GET`  | `/api/collateral/csa` |
| `GET`  | `/api/collateral/csa/{id}` |
| `GET`  | `/api/collateral/accounts` |
| `GET`  | `/api/collateral/margin-calls` |
| `POST` | `/api/collateral/margin-call` |
| `POST` | `/api/collateral/stress` |

### XVA

| Method | Path |
|--------|------|
| `GET`  | `/api/xva/summary` |
| `GET`  | `/api/xva/pfe` |
| `GET`  | `/api/xva/netting-sets` |

### Model Governance

| Method | Path |
|--------|------|
| `GET`  | `/api/models/registry` |
| `GET`  | `/api/models/registry/{model_id}` |
| `POST` | `/api/models/chat` |

### Scenarios & Metrics

| Method | Path |
|--------|------|
| `GET`  | `/api/scenarios/list` |
| `POST` | `/api/scenarios/activate` |
| `DELETE` | `/api/scenarios/activate` |
| `GET`  | `/api/scenarios/active` |
| `GET`  | `/api/metrics/api` |
| `POST` | `/api/metrics/api/reset` |

### WebSocket Endpoints

- `WS /ws/boardroom` — live boardroom stream
- `WS /ws/trading` — fill / tick / position events

---

## 5. WebSocket Message Shapes

### `/ws/boardroom`

```
Client → Server:
  {"type": "ping"}

Server → Client:
  {"type": "history",    "messages": [...]}
      ↑ replayed immediately on connect (last 200 turns)

  {"type": "turn_start", "agent": "Alexandra Chen", "color": "#e3b341", "title": "CEO"}
  {"type": "token",      "agent": "Alexandra Chen", "token": "Hello "}
      ↑ streamed token-by-token during agent generation
  {"type": "turn_end",   "agent": "Alexandra Chen"}

  {"type": "agent_turn", "agent": "...", "text": "...", "color": "...", "timestamp": "..."}
      ↑ complete turn (stored in history, used for late-joiner replay)

  {"type": "system", "message": "Meeting started", "timestamp": "..."}
```

### `/ws/trading`

```
Server → Client:
  {"type": "fill",      "trade_id": "...", "ticker": "AAPL", "side": "BUY",
                         "qty": 5000, "fill_price": 185.5, "notional": 927500,
                         "desk": "EQUITY", "book_id": "EQ_BOOK_1",
                         "var_before": 12000000, "var_after": 13200000,
                         "limit_status": "GREEN", "greeks": {...}}

  {"type": "tick",      "ticker": "AAPL", "bid": 185.4, "ask": 185.6, "mid": 185.5}

  {"type": "positions", "positions": [{"instrument": "AAPL", "quantity": 5000,
                                        "unrealised_pnl": 2500, ...}]}

  {"type": "greeks",    "book_id": "EQ_BOOK_1", "delta": 5000, "gamma": 50,
                         "vega": 1200, "dv01": 0, ...}
```

---

## 6. Core Data Flows

### 6.1 Trade Execution (critical path)

```
HTTP POST /api/trading/orders
  {desk, book_id, ticker, side, qty}
  │
  └─ oms_routes.submit_order(OrderRequest)
     │
     └─ oms.submit_order(desk, book_id, ticker, side, qty)
        │
        ├─ MarketDataFeed.get_quote(ticker)
        │   └─ Quote(bid, ask, mid, timestamp)
        │
        ├─ _pre_trade_check(desk, qty, fill_price)
        │   ├─ VaRCalculator.parametric_var(notional, vol)
        │   ├─ LimitManager.get_limit("VAR_" + desk).headroom
        │   └─ (approved: bool, message: str, est_var: float)
        │
        ├─ var_before = LimitManager.get_limit(desk_limit).current_value
        │
        ├─ risk_service.position_manager.add_trade(desk, book_id, ticker, ±qty, price)
        │   └─ BookSummary._get_or_create_book(book_id)
        │      └─ BookPosition.apply_trade(qty, price)
        │         ├─ Closing? → consume _lots FIFO → realised P&L
        │         ├─ Opening? → _lots.append([qty, price])
        │         └─ _update_avg_cost() from remaining lots
        │
        ├─ GreeksCalculator.compute(ticker, qty, price, current_prices)
        │   ├─ Equity  → delta = qty × price
        │   ├─ Bond    → DV01 = face × duration × 0.0001
        │   ├─ FX      → delta = qty × rate
        │   └─ Option  → Black-Scholes (scipy.stats.norm)
        │
        ├─ risk_service.run_snapshot()
        │   ├─ position_manager.get_all_positions()   ← flat list
        │   ├─ Group by desk
        │   ├─ Per desk: VaRCalculator.monte_carlo_var(positions, vols)
        │   │   ├─ CorrelationRegimeModel → normal or stress 6×6 matrix
        │   │   ├─ 1,000 correlated scenarios (multivariate normal)
        │   │   ├─ VaR  = abs(percentile(pnl, 1%))
        │   │   └─ CVaR = abs(mean of worst 1%)
        │   ├─ LimitManager.update("VAR_" + desk, new_var)
        │   └─ LimitManager.update("VAR_FIRM", firm_var)
        │
        ├─ var_after, limit_status (GREEN / YELLOW / ORANGE / RED)
        │
        └─ TradeConfirmation returned to route handler
           │
           ├─ asyncio.create_task(_persist_trade(conf_dict))
           │   └─ INSERT INTO oms_trades ...
           │
           └─ asyncio.create_task(trading_broadcaster.broadcast_fill(conf_dict))
               └─ {"type": "fill", ...} → all /ws/trading subscribers
```

### 6.2 Market Data Feed → Mark-to-Market → WebSocket

```
MarketDataFeed.start()  [async background task, 500ms cadence]
  │
  └─ For each of 11 tickers every 500ms:
     ├─ S(t+dt) = S(t) × exp((μ - 0.5σ²)dt + σ√dt × Z)   [GBM]
     ├─ Quote(bid, ask, mid, timestamp)
     ├─ Store in quote history
     └─ Fire subscriber callbacks:
        │
        ├─ mark_to_market_callback(ticker, new_price)
        │   └─ position_manager.mark_to_market(ticker, new_price)
        │      └─ BookPosition.mark_to_market(new_price)
        │         └─ unrealised_pnl = quantity × (new_price - avg_cost)
        │
        └─ trading_broadcaster.broadcast_tick(ticker, quote)
            └─ {"type": "tick", "ticker": "...", "mid": ...} → /ws/trading
```

### 6.3 Boardroom Meeting (API-driven)

```
POST /api/boardroom/start  {title, topic, agents: [...]}
  │
  └─ meeting_orchestrator._run_meeting_session(meeting_id, ...)
     │
     ├─ For each agent_name: _load_agent(name, anthropic_client)
     │   └─ Lazy import + instantiate BankAgent(system_prompt, ...)
     │
     └─ For each turn:
        ├─ scenario_state.snapshot()         ← inject any active shocks
        ├─ agent.speak(prompt)               ← one claude-opus-4-6 API call
        │   ├─ history.append({role: user, content: prompt})
        │   ├─ anthropic.messages.create(model, messages, system)
        │   ├─ history.append({role: assistant, content: reply})
        │   └─ trim history to max_history (sliding window)
        │
        ├─ boardroom_broadcaster.broadcast_agent_turn(name, text, color)
        │   ├─ Append to _history (pop oldest if > 200)
        │   └─ JSON send to all /ws/boardroom subscribers
        │
        └─ meeting_store.add_turn(meeting_id, name, text, color)
            └─ INSERT INTO meeting_turns
```

### 6.4 Risk Snapshot

```
Triggered by: OMS after every trade  OR  GET /api/risk/snapshot
  │
  └─ risk_service.run_snapshot()
     ├─ position_manager.get_all_positions()   ← flat list of BookPosition dicts
     ├─ Group positions by desk
     ├─ Per desk:
     │   ├─ VaRCalculator.monte_carlo_var(desk_positions, desk_vols)
     │   │   ├─ correlation_regime.get_matrix()   ← normal vs stress
     │   │   ├─ np.random.multivariate_normal(0, Σ, 1000)
     │   │   ├─ pnl_i = Σ(notional_j × scenario_ij × vol_j)
     │   │   └─ VaR = abs(percentile(1%)), CVaR = abs(mean worst 1%)
     │   └─ LimitManager.update("VAR_" + desk, var)
     ├─ Firm-wide VaR → LimitManager.update("VAR_FIRM", ...)
     └─ Return {snapshot_time, var_by_desk, limit_summary, breaches, warnings}
```

### 6.5 Treasury FTP

```
GET /api/treasury/ftp/summary
GET /api/treasury/ftp/adjusted-pnl
  │
  ├─ _get_positions()
  │   └─ risk_service.position_manager.get_all_positions()
  │       └─ [{book_id, desk, instrument, quantity, notional, avg_cost, ...}]
  │
  ├─ ftp_engine.calculate_desk_charges(positions)
  │   ├─ Group by pos["desk"]
  │   ├─ Per position:
  │   │   ├─ product_type = PRODUCT_MAP.get(instrument, "default")
  │   │   ├─ tenor = PRODUCT_TENOR[product_type]
  │   │   └─ accumulate notional + tenor-weighted notional
  │   └─ Per desk:
  │       ├─ avg_tenor = tenor_weighted_notional / total_notional
  │       ├─ ftp_rate = SwapCurve.get_rate(avg_tenor) + liquidity_premium
  │       └─ DeskFTPCharge(desk, notional, ftp_rate, daily/annual charge)
  │
  └─ (for adjusted-pnl) _get_desk_pnl()
      └─ risk_service.get_position_report()["by_desk"]
          └─ Join with FTP charges → net P&L per desk
```

### 6.6 XVA Pipeline (current state: partially stubbed)

```
GET /api/xva/summary
  │
  └─ XVAAdapter.run_pipeline(config)
     ├─ from_positions([])          ← TODO-002: stub, returns []
     ├─ If pyxva available:
     │   └─ pyxva.RiskEngine(config).run(market_data) → CVA/DVA/FVA/PFE
     └─ Fallback: _sample_results()
         └─ {CVA: -$485K, DVA: +$210K, FVA: -$95K, pfe_profile: hump-shaped}
```

### 6.7 Collateral VM Lifecycle (not yet wired to live runtime)

```
CollateralService.run_daily_margin_call_lifecycle()
  │
  └─ For each seeded CSA (5 counterparties):
     ├─ SIMM(positions under netting set)
     │   ├─ Pre-net same-tenor DV01 buckets
     │   ├─ Aggregate IR + CRQ risk classes
     │   └─ SIMM_IM = Σ risk classes
     ├─ net_exposure = MTM - received_collateral + independent_amount
     ├─ If net > threshold + MTA:
     │   ├─ MarginCall(direction=OUTBOUND, amount, due=today+1, status=PENDING)
     │   └─ EventLog.append("collateral_margin_call", csa_id, payload)
     └─ stress_scenarios.apply(CSA) → haircut + shock → adequacy check
```

---

## 7. Key Data Models

### `BookPosition` — live position record (source of truth)

```python
book_id:    str
desk:       str
instrument: str          # canonical field name (NOT "ticker")
quantity:   float        # signed: + long, − short
avg_cost:   float        # weighted avg of remaining FIFO lots
last_price: float        # current mark from GBM feed
currency:   str          # "USD"
_lots:      list[[qty, price]]  # FIFO lot queue (private)

# Derived
unrealised_pnl = quantity × (last_price − avg_cost)
notional       = abs(quantity × last_price)
```

### `TradeConfirmation` — OMS response

```python
trade_id, uti, ticker, side, quantity, fill_price, notional,
desk, book_id, executed_at,
greeks: {delta, gamma, vega, theta, rho, dv01},
var_before, var_after,
limit_headroom_pct, limit_status,     # GREEN / YELLOW / ORANGE / RED
pre_trade_approved: bool,
pre_trade_message: str
```

### `VaRResult`

```python
book_id, confidence_level, horizon_days,
var_amount, cvar_amount,
method: str,    # "monte_carlo" | "historical" | "parametric"
computed_at
```

### `Limit` — risk limit with live utilization

```python
name:          str       # e.g. "VAR_EQUITY"
hard_limit:    float
current_value: float     # updated every run_snapshot()
unit:          str
desk:          str
# Derived
utilisation_pct = abs(current_value) / hard_limit × 100
status: GREEN (<70%) / YELLOW (70–80%) / ORANGE (80–90%) / RED (90–100%) / BREACH (>100%)
```

### `CSA` — Credit Support Annex

```python
csa_id, counterparty_id, counterparty_name, our_legal_entity,
threshold_usd, mta_usd, independent_amount_usd, mpor_days,
eligible_collateral: list[CollateralAssetType],
haircuts: dict[CollateralAssetType, float],
rehypothecation_allowed: bool, is_cleared: bool
```

---

## 8. Database Schemas

### `meetings.db`

```sql
CREATE TABLE meetings (
    id TEXT PRIMARY KEY,
    title TEXT, topic TEXT,
    status TEXT DEFAULT 'running',   -- running | completed | error
    started_at TEXT, ended_at TEXT,
    agent_names TEXT DEFAULT '[]',   -- JSON array
    turn_count INTEGER DEFAULT 0
);
CREATE TABLE meeting_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id TEXT NOT NULL REFERENCES meetings(id),
    seq INTEGER NOT NULL,
    agent_name TEXT, agent_title TEXT,
    text TEXT, color TEXT, timestamp TEXT
);
CREATE INDEX idx_turns_meeting ON meeting_turns(meeting_id, seq);
```

### `oms_trades.db`

```sql
CREATE TABLE oms_trades (
    trade_id TEXT PRIMARY KEY,
    ticker TEXT, side TEXT, quantity REAL,
    fill_price REAL, notional REAL,
    desk TEXT, book_id TEXT, trader_id TEXT,
    executed_at TEXT, greeks_json TEXT,
    var_before REAL, var_after REAL,
    limit_status TEXT    -- GREEN | YELLOW | ORANGE | RED
);
```

### `events.db`

```sql
CREATE TABLE bank_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    aggregate_type TEXT NOT NULL,  -- "trade" | "position" | "limit" | ...
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,         -- JSON
    sequence_number INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX idx_aggregate ON bank_events(aggregate_type, aggregate_id);
CREATE INDEX idx_event_type ON bank_events(event_type);
```

### `instruments.db`

```sql
CREATE TABLE instruments (
    isin TEXT PRIMARY KEY, cusip TEXT, ticker TEXT NOT NULL,
    name TEXT, product_type TEXT, currency TEXT DEFAULT 'USD',
    exchange TEXT, day_count TEXT DEFAULT 'ACT/360',
    is_active INTEGER DEFAULT 1, created_at TEXT
);
CREATE INDEX idx_ticker ON instruments(ticker);
```

### `position_snapshots.db`

```sql
CREATE TABLE position_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument TEXT NOT NULL,       -- canonical (NOT "ticker")
    book_id TEXT NOT NULL,
    quantity REAL, avg_cost REAL,
    realised_pnl REAL DEFAULT 0,    -- British spelling (matches engine)
    unrealised_pnl REAL DEFAULT 0,  -- British spelling (matches engine)
    snapshot_time TEXT,
    UNIQUE(instrument, book_id)
);
```

### `collateral.db`

```sql
CREATE TABLE csa (csa_id PK, counterparty_id, counterparty_name, our_legal_entity,
                  governing_law, threshold_usd, mta_usd, independent_amount_usd,
                  mpor_days, eligible_collateral JSON, haircuts_json,
                  rehypothecation_allowed, is_cleared);

CREATE TABLE collateral_account (account_id PK, csa_id FK, counterparty_id,
                                  posted_balance_usd, received_balance_usd,
                                  posted_assets JSON, received_assets JSON, updated_at);

CREATE TABLE margin_call (call_id PK, csa_id FK,
                          direction TEXT,  -- OUTBOUND | INBOUND
                          amount_usd REAL, due_date TEXT,
                          status TEXT,     -- PENDING|DELIVERED|DISPUTED|LATE|SETTLED|DEFAULTED
                          initiated_at TEXT, settled_at TEXT);
```

---

## 9. Agent Roster

All 14 agents use `claude-opus-4-6` with adaptive thinking. Each `speak()` call = one API call = real cost.

| Agent | Title | Color | Voice accent | Speed |
|-------|-------|-------|-------------|-------|
| Alexandra Chen | CEO | Gold `#e3b341` | en-US female | 1.00× |
| Dr. Priya Nair | CRO | Red `#f85149` | en-GB female | 0.85× |
| Marcus Rivera | CTO | Blue `#79c0ff` | en-US male | 1.05× |
| Dr. Yuki Tanaka | Head Quant | Blue `#58a6ff` | en-US male | 1.00× |
| James Okafor | Lead Trader | Green `#3fb950` | en-US male | 1.15× |
| Sarah Mitchell | CCO | Purple `#bc8cff` | en-US female | 0.90× |
| Amara Diallo | Head Treasury | Orange `#ffa657` | en-US female | 0.90× |
| Diana Osei | CFO | Gold `#e3b341` | en-US female | 0.95× |
| Dr. Fatima Al-Rashid | CDO | Purple `#b39ddb` | en-US female | 0.95× |
| Jordan Pierce | Head Audit | Dark red `#c62828` | en-US female | 0.88× |
| Margaret Okonkwo | General Counsel | Cyan `#4fc3f7` | en-GB female | 0.90× |
| Dr. Samuel Achebe | Head Model Validation | Pink `#ce93d8` | en-US male | 0.88× |
| The Observer | Independent Narrator | Gray `#8b949e` | en-US male | 0.88× |
| Meridian Consultant | External Advisor | — | — | — |

**Cost model**: Use `Boardroom.call_agent()` for sequential discussion — one API call per turn. Use `round_table()` for parallel opinions. Reserve multi-agent concurrent calls for independent parallel workstreams. Never loop agent calls without a termination condition.

---

## 10. Risk Limit Framework

`LimitManager` ships with 20 pre-configured limits:

| Category | Limit | Hard Limit |
|----------|-------|-----------|
| VaR — firm | VAR_FIRM | $450M |
| VaR — desk | VAR_EQUITY, VAR_RATES, VAR_FX, VAR_CREDIT, VAR_DERIVATIVES | $85M / $60M / $55M / $75M / $95M |
| Sensitivity | DV01_FIRM | $25M/bp |
| Sensitivity | EQUITY_DELTA | $2B |
| Sensitivity | VEGA_FIRM | $15M/%vol |
| Concentration | SINGLE_NAME_EQ_PCT | 20% |
| Concentration | SINGLE_NAME_EQ_NOTIONAL | $500M |
| Concentration | COUNTRY_FX | $800M |
| Stress | STRESS_GFC, STRESS_COVID | $2.1B / $1.8B |
| Leverage | GROSS_LEVERAGE, NET_LEVERAGE | 12× / 8× |

Status thresholds: GREEN < 70% · YELLOW 70–80% · ORANGE 80–90% · RED 90–100% · BREACH > 100%

---

## 11. Configured Greeks by Instrument Type

| Instrument pattern | Delta | Gamma | Vega | DV01 |
|--------------------|-------|-------|------|------|
| Equity (AAPL, MSFT, NVDA) | qty × price | 0 | 0 | 0 |
| US10Y (duration 8.5yr) | 0 | 0 | 0 | face × 8.5 × 0.0001 |
| US2Y (duration 1.9yr) | 0 | 0 | 0 | face × 1.9 × 0.0001 |
| FX (EURUSD, GBPUSD) | qty × rate | 0 | 0 | 0 |
| *_CALL_* / *_PUT_* | BSM Δ × qty × 100 | BSM Γ | BSM ν | 0 |
| USD_IRS_5Y | 0 | 0 | 0 | qty × 0.0004 |

---

## 12. Scenarios System

**Built-in scenarios**:
1. `founding_board_meeting.py` — 7-agent session: Vision → Tech → Trading → Quant → Risk → Compliance → Synthesis (8–15 min)
2. `consulting_review_meeting.py` — Meridian Consulting external review
3. `collateral_mechanics_meeting.py` — CSA/VM/SIMM deep-dive

**API-driven scenario activation** (`POST /api/scenarios/activate`):
- Injects shock dict (`equity_shock`, `vol_spike`, `rates_shock_bps`, etc.) into `ScenarioState` singleton
- Meeting orchestrator reads `scenario_state.snapshot()` before each turn and prepends shock descriptions to the agent's prompt
- Agents respond in-character to market conditions at zero additional API cost

---

## 13. Collateral Module (v0.1.4.0)

Five seeded CSAs:

| Counterparty | Threshold | MTA | MPoR | Type |
|-------------|-----------|-----|------|------|
| Goldman Sachs | $0 (zero-threshold) | $10K | 10 days | Bilateral |
| JPMorgan Chase | $50K | $25K | 10 days | Bilateral |
| Deutsche Bank | $100K | $50K | 10 days | Bilateral |
| Meridian Capital | $200K | $100K | 10 days | Bilateral |
| LCH | $0 | $500 | 5 days | CCP-cleared |

Standard haircuts: USD Cash 0% · UST 2% · Agency 4% · Gilt 4% · Bund 2% · IG Corp 15%

Stress scenarios: COVID Week (equities −35%, rates +200bps) · Lehman Event (equities −45%, credit +800bps) · Gilt Crisis (rates +300bps, GBP −15%)

---

## 14. Dashboard Pages

| Page | URL | Key API calls |
|------|-----|---------------|
| Home | `/` | `/api/health` |
| Boardroom | `/boardroom` | `WS /ws/boardroom`, `POST /api/boardroom/start`, `POST /api/observer/chat` |
| Trading | `/trading` | `WS /ws/trading`, `POST /api/trading/orders`, `GET /api/trading/blotter,greeks,pnl` |
| XVA | `/xva` | `GET /api/xva/summary,pfe,netting-sets` |
| Risk | `/risk` | `GET /api/risk/snapshot,limits`, `GET /api/trading/greeks` |
| Models | `/models` | `GET /api/models/registry`, `POST /api/models/chat` |
| Scenarios | `/scenarios` | `GET /api/scenarios/list`, `POST /api/scenarios/activate` |

All pages share `dashboard/shared_nav.js` for the navigation bar.

---

## 15. Running the Simulator

```bash
pip install -r requirements.txt
cp .env.example .env          # set ANTHROPIC_API_KEY=sk-ant-...

# Start the full dashboard server
uvicorn api.main:app --reload
open http://localhost:8000

# CLI — run founding board meeting (no server needed)
python main.py

# CLI options
python main.py --list-agents
python main.py --scenario founding
```

---

## 16. Critical Invariants

- Every `agent.speak()` = one Anthropic API call. **Never trigger agents in a loop without a termination condition.**
- `BankAgent.history` is trimmed via `max_history` sliding window before each API call.
- `BoardroomBroadcaster._history` is capped at 200 messages. TODO-004 tracks SQLite overflow.
- `PositionManager` is owned by `risk_service`. No second instance is constructed after startup.
- All treasury read paths call `risk_service.position_manager` directly — no detached copies.
- `ANTHROPIC_API_KEY` lives in `.env` only. Never hardcode.
- Dashboard WebSocket binds to `127.0.0.1` only.
- Field names: `instrument` (not `ticker`), `realised_pnl`/`unrealised_pnl` (British spelling) throughout persistence and engine layers.
