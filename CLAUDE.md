# Apex Global Bank Simulator — CLAUDE.md

Multi-agent JP Morgan-scale bank simulation. Each agent is a Claude API call with a distinct persona, role, and department. Educational/demo project — not connected to real financial infrastructure.

---

## Architecture

```
agents/          Department agents (markets, risk_desk, compliance, executive, etc.)
api/             FastAPI backend + WebSocket boardroom broadcaster
dashboard/       Single-page HTML dashboard (boardroom view, XVA, model registry)
infrastructure/  XVA adapter (pyxva integration), SQLite persistence
model_docs/      SR 11-7 model cards (registry.json)
orchestrator/    Simulation orchestrator + scenario runner
scenarios/       Predefined simulation scenarios
scripts/         Entry points
```

## Running

```bash
pip install -r requirements.txt
cp .env.example .env  # add ANTHROPIC_API_KEY
python main.py                        # founding board meeting
python main.py --list-agents          # list all agents
uvicorn api.app:app --reload          # dashboard backend
```

## Critical Invariants — Never Break

- Every agent call costs real Anthropic API tokens. **Never trigger agents in a loop without a termination condition.**
- `BankAgent.history` has no size cap — always use a sliding window (last N messages) before passing to API. See TODO-001.
- `BoardroomBroadcaster._history` must be capped at 1,000 messages (TODO-004) — never grow unbounded.
- API keys live in `.env` only — never hardcode `ANTHROPIC_API_KEY`.
- Dashboard WebSocket binds to `127.0.0.1` only.

## Agent Cost Model

- Each agent `speak()` call = one Anthropic API call = real money.
- Use Claude for **roleplay/single-conversation boardroom meetings** (zero API cost) rather than spawning agent instances for sequential discussion — same quality, free.
- Reserve multi-agent API calls for **parallel independent work** (e.g., 3 agents writing 3 separate docs simultaneously).

## pyxva Integration

- pyxva is a local dependency at `../pyxva` (also on PyPI as `pyxva`).
- XVA pipeline: `XVAAdapter.from_positions()` → `run_pipeline()` → CVA/DVA/FVA numbers.
- `from_positions()` currently returns `[]` (TODO-002) — XVA dashboard shows mock data until fixed.

## Open TODOs (see TODOS.md for full detail)

- **TODO-001 P1**: Context window management for BankAgent (sliding window history)
- **TODO-002 P2**: XVAAdapter.from_positions() — wire real trade positions
- **TODO-003 P2**: Model governance AI — Quant agent Q&A on model cards
- **TODO-004 P2**: BoardroomBroadcaster history pagination (cap at 1k, serve rest from SQLite)
- **TODO-005 P2**: pyxva live XVA integration end-to-end

## After Any Change

1. Update TODOS.md (mark done, add new items)
2. Commit with a concise 1–2 sentence message
3. If API/WebSocket contract changes, update dashboard JS accordingly
