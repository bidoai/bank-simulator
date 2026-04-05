# Apex Global Bank Simulator — CLAUDE.md

Multi-agent JPMorgan-scale bank simulation. Each agent is a Claude Opus 4.6 instance with a deep domain-specific system prompt. Educational/demo project — not connected to real financial infrastructure.

---

## Architecture

```
agents/          Department agents (20 total — exec, markets, risk, legal, audit, consulting)
api/             FastAPI backend + WebSocket streams (boardroom, trading, xva)
dashboard/       7 single-page HTML dashboards, all share shared_nav.js
infrastructure/  All quantitative engines (see list below)
models/          Pydantic data models
model_docs/      SR 11-7 model cards (registry.json + MDD markdown)
orchestrator/    Boardroom orchestrator + scenario runner
scenarios/       Predefined runnable discussion scenarios (several untested with live API)
scripts/         Entry points
```

## Running

```bash
pip install -r requirements.txt
cp .env.example .env   # add ANTHROPIC_API_KEY
uvicorn api.main:app --reload   # dashboard backend (port 8000)
python main.py                  # founding board meeting (costs API tokens)
```

Full test suite:
```bash
uv run --with fastapi --with pytest-asyncio --with httpx --with structlog --with numpy --with anthropic pytest -q
```

## Infrastructure layers

| Module | Key classes |
|--------|-------------|
| `trading/` | `OMS`, `PositionManager`, `LimitManager`, `PnLCalculator`, `GreeksCalculator`, `OrderBook` |
| `risk/` | `RiskService`, `VaRCalculator`, `CounterpartyRegistry`, `ConcentrationRiskMonitor`, `CorrelationRegimeModel`, `RegulatoryCapitalEngine` |
| `collateral/` | `VMEngine`, `SIMMEngine`, `CollateralStressScenarios` (5 CSAs, SIMM 2.6 IR+CRQ, 3 stress scenarios) |
| `credit/` | `IFRS9ECLEngine` (50-obligor portfolio) |
| `treasury/` | `ALMEngine`, `FTPEngine`, `NMDModel`, `DynamicFTP`, `ALMHedging`, `RAROCEngine`, `BalanceSheetOptimizer` |
| `compliance/` | `AMLTransactionMonitor` |
| `stress/` | `DFASTEngine` (9-quarter CET1 projection, 3 scenarios) |
| `xva/` | `XVAAdapter` wrapping pyxva (local dep `../pyxva`). Now live via `SimulationXVAService` |
| `market_data/` | `MarketDataFeed` (GBM simulation, 11 tickers, 500ms ticks). `LiveSeed` pulls Yahoo Finance prices at startup; `FREDCurve` loads UST/SOFR + BBB OAS; `DFASTScenarios` loads 2025 official Fed parameters. |
| `liquidity/` | `LCREngine`, `NSFREngine`, `IntradayMonitor`, `LiquidityLadder`, `LiquidityStressScenarios` |
| `securities_finance/` | `SecuritiesFinanceService` (repo/stock-borrow desk shell) |
| `securitized_products/` | `SecuritizedProductsService` (agency MBS analytics shell with OAS/duration) |
| `events/` | `EventLog` (append-only SQLite audit trail) |
| `reference/` | `InstrumentMaster` (SQLite, 9 seeded instruments) |
| `persistence/` | `PositionSnapshots` (SQLite, survives restart) |
| `metrics/` | `APIMetrics` (daily token spend, $10 alert threshold) |

## Critical Invariants — Never Break

- Every agent `speak()` call costs real Anthropic API tokens. **Never trigger agents in a loop without a termination condition.**
- `BankAgent.__init__` accepts `max_history` (0 = unlimited). Always set a window. Observer hardcodes 40 messages.
- `BoardroomBroadcaster._history` is capped at 200 messages — never grow unbounded.
- API keys live in `.env` only — never hardcode `ANTHROPIC_API_KEY`.
- `oms_routes` MUST be registered before `trading_routes` in `api/main.py` — it shadows the live endpoints.
- The collateral module sits between PositionManager and XVAAdapter. Do not bypass it when computing CVA.

## Agent Cost Model

- In-character boardroom delivery (Claude playing all roles directly) = zero API cost, often higher quality than multi-agent calls for design/educational sessions.
- Reserve multi-agent API calls for parallel independent work (e.g., 3 agents writing 3 separate docs simultaneously).
- `api_metrics` tracks daily spend — check `GET /api/metrics/api` before running long scenarios.

## XVA / Collateral Integration Path

```
PositionManager → CollateralEngine (CSA terms, MPoR, IM balances)
    → XVAAdapter (collateralised exposure, not gross MTM)
    → CVA/DVA/FVA numbers
```

XVA is now live via `SimulationXVAService` in `infrastructure/xva/`. The collateral module (TODO-025) is in place — next step is wiring `CollateralEngine` balances into the CVA exposure calculation.

## After Any Change

1. Update `TODOS.md` (mark done, add new items)
2. Commit with a concise 1–2 sentence message
3. If API/WebSocket contract changes, update dashboard JS accordingly
4. Run full test suite before pushing
