"""
Meridian Strategy Group — Apex Global Bank Simulator Engagement

Victoria Ashworth conducts a full platform review: architecture, infrastructure,
missing systems, organizational gaps, and a prioritized remediation roadmap.

Run:
    python scripts/consulting_review.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env from project root
from pathlib import Path
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.rule import Rule
from agents.consulting import create_consultant

console = Console(width=120)

ENGAGEMENT_BRIEFING = """
You have been engaged to review the Apex Global Bank Simulator — a multi-agent AI simulation platform
modeled on a JPMorgan-scale institution. The client (the builder/product owner) wants a frank
assessment of: what's working, what's missing, what's dangerous, and what should be built next.

## Platform Overview

Apex Global Bank Simulator is an educational/demo platform demonstrating multi-agent AI coordination
across a JP Morgan-scale bank. Each agent is a Claude Opus 4.6 API call with a distinct persona,
role, and department. The system runs board meetings, stress scenarios, and XVA calculations.

**Version:** v0.1.2.0
**Status:** Active development

---

## What Exists Today

### Agents & Departments (16 total, 10 fully implemented)

**Executive Suite (fully implemented):**
- CEO: Alexandra Chen — strategy, capital allocation, 30-year veteran persona
- CTO: Marcus Rivera — tech architecture, AI platform, latency obsession
- CFO: Diana Osei — balance sheet, P&L, ROTCE, investor relations
- CRO: Dr. Priya Nair — VaR, stress testing, Basel III, limit frameworks
- CCO Credit: Robert Adeyemi — $1.8T loan portfolio, PD/LGD/EAD, ECL reserves
- Head of Treasury: Amara Diallo — LCR/NSFR, funding, NIM, ALM

**Markets (fully implemented):**
- Lead Trader: James Okafor — desk P&L, trading strategy
- Trading Desk — execution, book management, Greeks
- Quant Researcher: Dr. Yuki Tanaka — pricing models, alpha research, ML

**Compliance (fully implemented):**
- Compliance Officer: Sarah Mitchell — AML/KYC, OFAC, Volcker, 3LoD

**Narrator:**
- The Observer — explains the simulation to readers, breaks the fourth wall

**Skeleton-only (not yet functional):**
- Head of Investment Banking (Sophie Laurent)
- Head of Wealth Management (Isabella Rossi)
- Head of Operations (Chen Wei)
- CDO (Dr. Fatima Al-Rashid)
- CISO (Ivan Petrov)
- Risk Desk Officers × 4 (market, credit, model, liquidity risk)

---

### Technology Infrastructure

**API Layer:** FastAPI backend with 13 route modules. Key endpoints:
- `POST /api/boardroom/new` + `/play` — orchestrate multi-agent meetings
- `GET /api/boardroom/list` — list saved meetings from SQLite
- `POST /api/observer/chat` — Q&A with The Observer agent
- `/api/scenarios/*` — activate/deactivate market stress scenarios
- `/api/trading/*` — orders, positions, P&L, limit utilization
- `/api/risk/*` — VaR snapshot, limits, counterparties, on-demand VaR calculation
- `/api/xva/*` — CVA/DVA/FVA numbers (currently mock only)
- `/api/models/*` — SR 11-7 model registry

**WebSocket:** `/ws/boardroom` — real-time agent turn streaming to browser clients

**Persistence:** SQLite (aiosqlite) — meetings and turns stored. No other databases.

**Dashboard:** 6 single-page HTML applications (vanilla JS, Tailwind CSS, no build step):
1. Home/navigation
2. Boardroom — live agent conversation with WebSocket, Browser TTS voice per agent
3. Trading — orders, positions, P&L, limit utilization
4. XVA — CVA/DVA/FVA heatmaps, PFE profile (mock data)
5. Model Registry — SR 11-7 model cards
6. Scenarios — activate market stress scenarios

---

### Risk & Trading Infrastructure

**Position Manager:** Tracks net positions per desk/instrument (Python in-memory)
**Order Book:** Continuous limit order book (CLOB) — in-memory
**P&L Calculator:** Mark-to-market, daily P&L attribution
**Limit Manager:** Risk limits — VAR_EQUITY, VAR_RATES, DV01, vega, CS01 buckets
**VaR Calculator:** Monte Carlo, 1-day 99% confidence, 1000 paths, GBM
**Risk Service:** Unified snapshot across all three systems (completed v0.1.2.0)
**Counterparty Registry:** Ratings, ISDA flags, PFE limits

**What's STUBBED / Mock only:**
- XVA calculations: `from_positions()` returns `[]` — all CVA/DVA/FVA is hardcoded mock
- Greeks pipeline: DV01, vega, CS01 not yet computed from real positions
- Stressed VaR: FRTB/historical stress window not yet built
- Correlation regime model: Static Cholesky (will underestimate stress correlations)
- Market data feed: GBM simulator only, no real data integration

---

### Key Technical Decisions

- Single model (Claude Opus 4.6) for all agents — differentiated by system prompts
- Adaptive thinking enabled — model decides depth of reasoning per query
- Sliding window history — agents use last N messages, prevents context explosion
- Scenario injection — active market shocks injected into every agent's context
- Graceful degradation — pyxva/compliance/data feed all return sensible defaults if missing

---

### Open TODOs (from TODOS.md)

**P2 Backlog:**
- TODO-002: XVA position field mapping — wire real trades to pyxva engine
- TODO-003: Model governance AI — Quant agent Q&A on SR 11-7 model cards
- TODO-004: BoardroomBroadcaster history pagination — cap at 1k messages, serve rest from SQLite
- TODO-005: pyxva live XVA integration end-to-end
- TODO-011: Greeks pipeline (DV01, vega, CS01)
- TODO-012: Stressed VaR + FRTB backtesting (GFC 2007-09, COVID 2020 data)
- TODO-013: Correlation regime model (HMM + Cholesky stress regime)

**Explicitly deferred:**
- Multi-user auth system
- Production cloud deployment
- Real-world market data (Bloomberg/Refinitiv)
- CI/CD pipeline

---

### Codebase Stats
- ~2,600 lines of API code
- 31 agent files
- 6 dashboard HTML SPAs
- 700+ lines of tests (18 boardroom tests passing)
- Dependencies: anthropic SDK, FastAPI, uvicorn, pydantic, numpy/scipy/pandas, aiosqlite, websockets, pyxva (local)

---

## Your Engagement Mandate

The client wants a frank consulting engagement covering:

1. **Missing Agent Roles** — what department heads, desks, or functions are conspicuously absent for a bank this scale? What gaps could cause the simulation to give dangerously incomplete advice?

2. **Missing Infrastructure** — what systems, data stores, message buses, or compute layers are absent? What would a real bank have that this platform entirely lacks?

3. **Missing Codebases / Modules** — what entire subsystems need to be built from scratch?

4. **Risk & Control Gaps** — where are the three lines of defense not actually implemented? What regulatory obligations have no corresponding system?

5. **Architecture & Scalability** — where will this break under load or extended simulation? What architectural choices create technical debt?

6. **Organizational Design Gaps** — what roles or capabilities are single points of failure?

7. **Prioritized Recommendations** — Quick Wins (30 days), Medium-Term (90 days), Strategic (12+ months)

8. **Bottom Line** — is this platform ready to simulate a real stress event credibly, or will it fail the moment something goes wrong?

Be as specific, frank, and actionable as a senior partner at a top-tier strategy firm. This is a paid engagement. The client does not need encouragement — they need the truth.
"""


def run_engagement():
    console.print(Panel.fit(
        "[bold gold1]MERIDIAN STRATEGY GROUP[/bold gold1]\n"
        "[dim]Apex Global Bank Simulator — Platform Assessment Engagement[/dim]\n"
        "[dim]Senior Managing Partner: Victoria Ashworth[/dim]",
        border_style="gold1",
    ))
    console.print()

    consultant = create_consultant()

    console.print("[dim]Transmitting engagement briefing to Victoria Ashworth...[/dim]")
    console.print()

    response = consultant.stream_speak(
        ENGAGEMENT_BRIEFING,
        max_tokens=8000,
        use_thinking=True,
    )

    console.print(Rule("[bold gold1]ENGAGEMENT FINDINGS — Victoria Ashworth, Meridian Strategy Group[/bold gold1]", style="gold1"))
    console.print()
    console.print(Markdown(response))
    console.print()
    console.print(Rule(style="gold1"))

    # Save the report
    report_path = "meridian_consulting_review.md"
    with open(report_path, "w") as f:
        f.write("# Meridian Strategy Group — Apex Global Bank Simulator Assessment\n\n")
        f.write("**Engagement Lead:** Victoria Ashworth, Senior Managing Partner\n\n")
        f.write("---\n\n")
        f.write(response)
    console.print(f"\n[dim]Report saved to {report_path}[/dim]")


if __name__ == "__main__":
    run_engagement()
