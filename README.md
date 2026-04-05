# Apex Global Bank Simulator

A multi-agent JP Morgan-scale bank simulation. Each agent is a Claude API call with a distinct persona, department, and role. Built for education and demos — not connected to real financial infrastructure.

---

## What it is

A full-stack bank simulator with:
- **13+ AI agents** playing C-suite executives, traders, risk officers, compliance, legal, and audit — all powered by `claude-opus-4-6`
- **Live trading infrastructure** — OMS with FIFO position accounting, pre-trade VaR checks, Greeks, and real-time limit monitoring
- **Risk engine** — Monte Carlo VaR (regime-aware), Basel III capital ratios, concentration risk, counterparty credit
- **Treasury** — Fund Transfer Pricing with tenor-matched swap curve, ALM/NII/EVE sensitivity
- **Securities finance** — Repo, stock borrow-loan, and prime financing operating view
- **Collateral** — CSA/VM lifecycle, SIMM approximation, margin call management
- **Credit & compliance** — IFRS 9 ECL, AML transaction monitoring (6 rule types)
- **Securitized products** — Agency MBS / ABS / CMBS / CLO inventory, OAS, convexity, and stress views
- **XVA** — CVA/DVA/FVA via pyxva integration (partially live)
- **9 dashboard pages** with live WebSocket feeds

---

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env       # set ANTHROPIC_API_KEY=sk-ant-...

# Start the full dashboard
uvicorn api.main:app --reload
open http://localhost:8000

# Or run a boardroom meeting from the CLI (no server needed)
python main.py
```

---

## Dashboard Pages

| Page | URL | Description |
|------|-----|-------------|
| Home | `/` | System overview |
| Boardroom | `/boardroom` | Live multi-agent meeting stream + Observer Q&A |
| Trading | `/trading` | OMS blotter, P&L, Greeks, live positions |
| XVA | `/xva` | CVA/DVA/FVA, PFE profile |
| Risk | `/risk` | VaR by desk, limit heatmap, Greeks heatmap |
| Securities Finance | `/securities-finance` | Repo, stock loan, prime financing, balance-sheet usage |
| Securitized | `/securitized` | MBS / ABS / CMBS / CLO desk analytics and build pipeline |
| Models | `/models` | SR 11-7 model governance registry |
| Scenarios | `/scenarios` | Market stress scenario launcher |

---

## Agent Roster

| Agent | Title |
|-------|-------|
| Alexandra Chen | CEO |
| Dr. Priya Nair | CRO |
| Marcus Rivera | CTO |
| Diana Osei | CFO |
| Dr. Yuki Tanaka | Head Quant Research |
| James Okafor | Lead Trader |
| Sarah Mitchell | CCO / Compliance |
| Amara Diallo | Head of Treasury |
| Jordan Pierce | Head of Internal Audit |
| Margaret Okonkwo | General Counsel |
| Dr. Samuel Achebe | Head of Model Validation |
| Dr. Fatima Al-Rashid | CDO |
| The Observer | Independent Narrator |
| Meridian Consultant | External Advisor |

Each agent has a distinct system prompt, voice profile, and color. The Observer narrates for the reader without a department agenda.

---

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full writeup including:
- Startup sequence
- All 40+ API routes
- WebSocket message shapes
- Data flows: trade execution, boardroom, risk snapshot, market data MTM, treasury FTP, XVA, collateral VM
- Database schemas (6 SQLite databases)
- Singleton ownership map
- Risk limit framework (20 limits)
- Greeks by instrument type

---

## Repository Layout

```
agents/           AI agent implementations (BankAgent base + 14 personas)
api/              FastAPI backend — routes, WebSocket hubs, meeting orchestrator
infrastructure/   Core banking systems (trading, risk, treasury, collateral, credit, compliance, sec-fin, securitized)
models/           Pydantic data models
orchestrator/     Boardroom session conductor
scenarios/        Predefined simulation scenarios
dashboard/        Frontend HTML/JS (7 pages + shared nav)
model_docs/       SR 11-7 model card registry
data/             Runtime SQLite databases (gitignored)
docs/             Architecture and design documentation
```

---

## Cost Model

Every `agent.speak()` call = one `claude-opus-4-6` API call = real money.

- Use sequential boardroom turns for discussion — same quality, one call per turn
- Reserve parallel multi-agent calls for genuinely independent parallel workstreams
- Never loop agent calls without a termination condition
- `ANTHROPIC_API_KEY` lives in `.env` only — never hardcode

---

## Environment Variables

```
ANTHROPIC_API_KEY=sk-ant-...    # required
```

Everything else (ports, DB paths, tick intervals, limits) is configured in code. See `CLAUDE.md` for project-specific conventions.

---

## Open TODOs

| ID | Description |
|----|-------------|
| TODO-004 | BoardroomBroadcaster history pagination (200-msg in-memory → SQLite overflow) |
| TODO-012 | Stressed VaR + FRTB backtesting (2008 GFC / 2020 COVID historical data) |
| TODO-026 | OMS hardening (asyncio.Lock, thread-pool for run_snapshot, pre/post-trade consistency) |

See [`TODOS.md`](TODOS.md) for full detail including completed items and rationale.
