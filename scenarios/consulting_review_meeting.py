"""
Meridian Strategy Group Response Meeting — Executive Leadership Session

Victoria Ashworth (Meridian Strategy Group) delivered a comprehensive platform
assessment. Her findings were direct: the simulator is a well-architected proof
of concept, but there are material gaps in agent coverage, infrastructure, and
control frameworks that would prevent it from credibly simulating a stress event.

This session: the Apex executive team reviews her findings, debates priorities,
assigns ownership, and produces an implementation plan.

Run:
    python scenarios/consulting_review_meeting.py
"""

from __future__ import annotations
import os
import sys
from pathlib import Path

# Load .env from project root
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent.parent))

import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from agents.executive.ceo import create_ceo
from agents.executive.cto import create_cto
from agents.executive.cfo import create_cfo
from agents.executive.cro import create_cro
from agents.executive.cco_credit import create_chief_credit_officer
from agents.executive.head_of_treasury import create_head_of_treasury
from agents.compliance.compliance_officer import create_compliance_officer
from agents.narrator.observer import create_observer
from orchestrator.boardroom import Boardroom

console = Console(width=120)

# ── Victoria Ashworth's key findings, condensed for agent context injection ──

CONSULTING_FINDINGS = """
Victoria Ashworth (Senior Managing Partner, Meridian Strategy Group) has completed
her platform assessment of Apex Global Bank Simulator. Her key findings:

OVERALL RATING: 6.5/10 for a v0.1 platform.

═══ MISSING AGENT ROLES (by severity) ═══

CRITICAL:
• General Counsel / Head of Legal — absent entirely. Legal constraints drive every
  major bank crisis decision. No litigation reserves, no contractual netting model,
  no regulatory enforcement correspondence.
• CDO (Dr. Fatima Al-Rashid) — skeleton only. BCBS 239 compliance requires risk
  data aggregation within 24 hours of a stress event. No functioning CDO = no data
  governance, no lineage, no RDARR framework.
• CISO (Ivan Petrov) — skeleton only. Cyber is a first-order risk category. Post-
  Bangladesh Bank SWIFT heist, no simulation without a CISO models a complete risk
  picture.
• Head of Operations (Chen Wei) — skeleton only. Settlement failures, operational
  resilience, outsourcing risk — absent.

SIGNIFICANT:
• Deputy CRO / Market Risk Officer — CRO currently conflates credit, market,
  liquidity, and model risk. These need separate reporting lines.
• Head of Investor Relations — in a stress event, IR manages the narrative to
  rating agencies. A bank run starts with a downgrade, not a trading loss.
• Tax Director — transfer pricing, FATCA, BEPS, Pillar Two. At JPMorgan scale,
  this is not optional.
• Internal Audit — the third line of defense is completely absent. No audit agent,
  no audit committee, no finding/remediation tracking. SOX perspective: no way to
  model management override risk.
• Model Validation Officer — independent of Quant Researcher. MRM requires
  adversarial validation independence. SR 11-7 compliance theater without it.

═══ MISSING INFRASTRUCTURE ═══

TIER 1 (structural absences):
• Legal Entity / Booking Model — no concept of legal entities. Apex modeled as a
  single entity. XVA netting calculations are fundamentally wrong without entity
  structure. JPMorgan has 2,000+ legal entities.
• General Ledger Integration — P&L calculator runs but there is no accounting layer.
  No chart of accounts, no IFRS 9 ECL staging. Trading P&L and financial statements
  are disconnected.
• Message Bus / Event Streaming — all state is in-memory or SQLite. No Kafka, no
  immutable audit event log. Cannot reconstruct what happened and when.
• Regulatory Reporting Engine — COREP, FINREP, FR Y-9C, CCAR submissions. Entirely
  absent. These are the primary deliverable of risk and finance in a real bank.
• Collateral Management System — VM/IM calls, CSA terms, eligible collateral,
  rehypothecation. In a stress event, collateral calls are the operational trigger
  before credit losses crystallize.

TIER 2 (meaningful gaps):
• Reference Data / Instrument Master — no CUSIP, ISIN, LEI, product type. Cannot
  build a regulatory capital calculator without clean instrument master.
• Limits Hierarchy — flat limits, no desk→business line→firm aggregation, no soft/
  hard limit distinction, no breach escalation workflow.
• Trade Lifecycle Management — no novation, amendment, cancellation, or assignment.
  All trades created, never modified. Event sourcing is absent.
• Fund Transfer Pricing (FTP) — Treasury cannot charge desks for funding cost.
  Trading P&L is economically meaningless without FTP.

═══ MISSING CODEBASES / MODULES ═══

P1 (critical):
• Regulatory Capital Engine — RWA calculation (SA and IMA), CET1/Tier 1/Tier 2,
  leverage ratio. The core output that determines if the bank can operate.
• IFRS 9 / CECL Engine — ECL staging (Stage 1/2/3), forward-looking provisions,
  PD/LGD/EAD over lifetime. CCO references these concepts; no system computes them.
• Collateral & Margin Engine — IM/VM calculation, CSA terms, eligible collateral
  haircuts, rehypothecation tracking.

P2:
• ALM / Interest Rate Risk Engine — NII sensitivity, EVE sensitivity, repricing
  gaps, behavioral assumptions. Head of Treasury operates blind without this.
• AML Transaction Monitoring — rule-based + ML screening, SAR filing, case mgmt.
  Compliance references AML; no system monitors transactions.
• Operational Risk Capital Model — AMA/SMA under Basel III, internal loss data.
• Stress Testing Framework — DFAST/CCAR-style multi-year capital adequacy stress
  projection. CRO runs VaR but cannot run a multi-year stress test.

═══ RISK & CONTROL GAPS ═══

• Three Lines of Defense — partially theater. Second line (CRO, CCO) reads from
  the same data as first line (trading desk). No independent control data layer.
• Model Risk Management — Quant builds models; no independent agent validates them.
• Concentration Risk — no geographic, sector, or single-name concentration limit
  framework despite CCO managing a $1.8T loan portfolio.

═══ ARCHITECTURE GAPS ═══

• In-memory state is a single point of failure — process restart loses all
  simulation state.
• SQLite unsuitable as position/trade persistence layer at scale.
• No authentication or multi-tenancy — WebSocket broadcasts to all clients.
• No metrics instrumentation — no way to detect runaway API spending.

═══ VICTORIA'S BOTTOM LINE ═══

"This platform cannot credibly simulate a stress event at a real bank. The missing
pieces — legal entity structure, regulatory capital, IFRS 9 provisioning, collateral
management, operational risk — are not decorative. They are the systems that
determine whether a bank survives a crisis or does not.

Priority: regulatory capital engine, legal entity model, three-lines-of-defense
independence. The foundation is solid. The distance to a credible enterprise
demonstration is 6–9 months of focused execution."
"""

CONSULTING_FINDINGS_SHORT = """
Victoria Ashworth (Meridian Strategy Group) rated Apex Global Bank Simulator 6.5/10.

Top findings:
1. Missing critical agents: General Counsel, functioning CDO/CISO/Operations heads,
   Internal Audit, Model Validation Officer (independent of Quant)
2. Missing infrastructure: Legal entity model, event sourcing, regulatory capital
   engine, collateral management, IFRS 9/CECL engine, AML transaction monitoring
3. Control gap: Second line (CRO/CCO) reads from first line's data — no independent
   control layer. Three lines of defense are partially theater.
4. Architecture: All position state in-memory (lost on restart), SQLite at scale,
   no metrics/alerting on API spend.
5. Missing codebases: Regulatory reporting engine, stress testing framework (DFAST/
   CCAR), FTP framework, ALM/interest rate risk engine.

Her priority recommendation: regulatory capital engine, legal entity model,
3LoD independence. 6–9 months to a credible enterprise demonstration.
"""


def run_consulting_review_meeting(
    export_path: str = "transcript_consulting_review.md",
) -> None:
    client = anthropic.Anthropic()

    ceo = create_ceo(client)
    cto = create_cto(client)
    cfo = create_cfo(client)
    cro = create_cro(client)
    cco = create_chief_credit_officer(client)
    treasury = create_head_of_treasury(client)
    compliance = create_compliance_officer(client)
    observer = create_observer(client)

    boardroom = Boardroom(
        agents={
            "CEO":        ceo,
            "CTO":        cto,
            "CFO":        cfo,
            "CRO":        cro,
            "CCO":        cco,
            "Treasury":   treasury,
            "Compliance": compliance,
        },
        observer=observer,
        session_name="Apex Global Bank — Meridian Consulting Response & Implementation Plan",
    )

    boardroom.open_session()

    # ── PART 1: CEO FRAMES THE ENGAGEMENT ────────────────────────────────────
    boardroom._render_section_header("PART I: CEO FRAMES THE CONSULTING FINDINGS")

    ceo_open = boardroom.call_agent(
        "CEO",
        f"""We have just received a comprehensive assessment from Victoria Ashworth at
Meridian Strategy Group. She rated us 6.5/10 and identified material gaps that she
says would prevent us from credibly simulating a bank stress event.

Here are her complete findings:

{CONSULTING_FINDINGS}

Open this session. I want your initial reaction — which findings do you agree with
immediately, which do you want to challenge, and how do you want to structure this
discussion to produce an actionable implementation plan by end of day?

Be direct. Victoria charged us $2M for this. Let's make sure we get our money's worth.""",
        show_prompt=False,
        max_tokens=1800,
        use_thinking=True,
    )

    boardroom.narrate(
        f"The CEO just opened the session reacting to the Meridian consulting findings:\n\n"
        f"{ceo_open[:600]}\n\n"
        "For the reader: explain what an external consulting engagement looks like at a major "
        "bank, why boards commission them, and what the typical dynamics are when a management "
        "team receives critical findings from a prestigious firm like McKinsey, BCG, or "
        "(in our case) Meridian. What makes this moment politically charged?"
    )

    # ── PART 2: CTO ON TECHNICAL GAPS ────────────────────────────────────────
    boardroom._render_section_header("PART II: CTO — TECHNICAL INFRASTRUCTURE RESPONSE")

    cto_response = boardroom.call_agent(
        "CTO",
        f"""The CEO has opened the session. Victoria flagged several critical technical gaps:

1. No legal entity / booking model — she says XVA netting calculations are wrong without it
2. No message bus / event streaming — all state in-memory, no audit log
3. No regulatory reporting engine (COREP, FINREP, CCAR)
4. No metrics/alerting infrastructure — no visibility into API spend
5. All position state in-memory — a process restart loses everything
6. SQLite as the only database — unsuitable at scale
7. Missing Greeks pipeline (DV01, vega, CS01 not computed from real positions)

As CTO, respond to each of these. Which are accurate? Which are overstated?
For each you agree with, tell me: what's the build effort, what's the sequencing
dependency, and what should we build first?

Be specific about technology choices. If Victoria says we need Kafka, do we? Or is
there a more pragmatic path for our current stage?""",
        max_tokens=2000,
        use_thinking=True,
    )

    boardroom.narrate(
        f"The CTO responded to the technical infrastructure gaps:\n\n{cto_response[:600]}\n\n"
        "For the reader: explain the concept of event sourcing vs. traditional CRUD databases, "
        "why financial systems increasingly use immutable event logs, and what Apache Kafka "
        "actually does in a bank's technology stack. Make it concrete."
    )

    # ── PART 3: CRO ON RISK & CONTROL GAPS ───────────────────────────────────
    boardroom._render_section_header("PART III: CRO — RISK & CONTROL FRAMEWORK RESPONSE")

    cro_response = boardroom.call_agent(
        "CRO",
        f"""Victoria's most pointed finding was about the Three Lines of Defense:
'The second line reads from the same data as the first line. That is a control failure.'

She also flagged:
- No independent Model Validation (MRM) function — Quant builds models, no one validates
- No stress testing framework (DFAST/CCAR-style multi-year capital projections)
- No Regulatory Capital Engine (RWA calculation, CET1 tracking)
- No Concentration Risk framework despite a $1.8T loan portfolio
- Correlation regime model issue: static Cholesky will catastrophically underestimate
  stress correlations

CTO just said: {cto_response[:300]}...

Now respond to the risk and control gaps. Which of Victoria's risk findings hit hardest?
What does a real 3LoD architecture look like, and what would it take to build it properly
here? What's your honest assessment of the regulatory capital and stress testing gap?
And what is the single risk infrastructure item you'd build first?""",
        max_tokens=1800,
        use_thinking=True,
    )

    cto_cro_exchange = boardroom.call_agent(
        "CTO",
        f"""The CRO raised the 3LoD independence issue:

{cro_response[:500]}

From an architecture perspective — how do we give the second line its own independent
data layer without duplicating the entire position management system? What's the
practical engineering pattern here? Be concrete about the solution.""",
        max_tokens=1200,
    )

    boardroom.narrate(
        f"The CRO and CTO just had a direct exchange about the Three Lines of Defense gap:\n"
        f"CRO: {cro_response[:400]}...\nCTO: {cto_cro_exchange[:400]}...\n\n"
        "For the reader: explain what the Three Lines of Defense model actually means in a bank, "
        "why regulators require it, and what 'independence' specifically means here — why is it "
        "a control failure if the risk department uses the same system as the trading desk?"
    )

    # ── PART 4: CFO ON RESOURCE & SEQUENCING ─────────────────────────────────
    boardroom._render_section_header("PART IV: CFO — BUDGET, SEQUENCING, AND PRIORITIZATION")

    cfo_response = boardroom.call_agent(
        "CFO",
        f"""We've heard from CTO and CRO on the technical and risk gaps. Now I need the
financial lens.

Victoria identified roughly 8 major missing systems and 9 missing agent roles.
Not everything gets built. Every build decision is a capital allocation decision.

CTO said: {cto_response[:300]}...
CRO said: {cro_response[:300]}...

Give me your view on:
1. How do we prioritize — what's the ROI framework for deciding which gaps to close first?
2. The Regulatory Capital Engine and IFRS 9/CECL engine are on Victoria's P1 list —
   from a CFO perspective, agree or disagree, and why?
3. Victoria said "6–9 months to a credible enterprise demonstration." Does that
   timeline hold given resource constraints? What resource allocation makes it true?
4. What are the FINANCIAL consequences of NOT addressing specific gaps — i.e., which
   missing systems create regulatory penalty exposure vs. which are nice-to-have?""",
        max_tokens=1800,
        use_thinking=True,
    )

    boardroom.narrate(
        f"The CFO framed the build vs. defer decision:\n\n{cfo_response[:600]}\n\n"
        "For the reader: explain how major banks do technology investment prioritization — "
        "what frameworks like business value vs. regulatory obligation vs. risk reduction "
        "look like in practice. How does a bank's CFO evaluate a $50M technology build "
        "request vs. a $500M regulatory capital requirement?"
    )

    # ── PART 5: CCO ON CREDIT & COMPLIANCE GAPS ──────────────────────────────
    boardroom._render_section_header("PART V: CCO & COMPLIANCE — REGULATORY OBLIGATION GAPS")

    cco_response = boardroom.call_agent(
        "CCO",
        f"""Victoria identified several gaps that are directly my responsibility:

1. No IFRS 9 / CECL engine — I manage a $1.8T loan portfolio and she says the
   system cannot compute ECL staging (Stage 1/2/3 migration). She is correct.
2. No Concentration Risk framework — no geographic, sector, or single-name limits
3. No AML Transaction Monitoring — I reference AML extensively but no system
   actually monitors transactions
4. BCBS 239 compliance requires risk data aggregation within 24 hours of a stress
   event — our CDO function is a skeleton

CFO just said the ROI framework is: regulatory obligation first, then risk reduction,
then enterprise value. Using that lens: {cfo_response[:200]}...

What is my honest assessment of our regulatory exposure from these gaps?
What is the build sequence that gets us to Basel III / IFRS 9 / BCBS 239 compliance?
And what does a proper IFRS 9 ECL engine actually need to compute?""",
        max_tokens=1600,
        use_thinking=True,
    )

    compliance_response = boardroom.call_agent(
        "Compliance",
        f"""The CCO just outlined the credit and data regulatory gaps.
The CCO said: {cco_response[:400]}...

From the compliance and three-lines perspective, add what I see:
- No Internal Audit agent / function — third line of defense is completely absent
- No AML transaction monitoring workflow (SAR filings, case management)
- No KYC/CDD onboarding workflow
- General Counsel is entirely absent — legal entity governance has no representation
- Victoria specifically said the 3LoD is 'partially theater' — what does that mean
  in terms of actual regulatory risk, and what does a proper compliance remediation
  roadmap look like?""",
        max_tokens=1400,
    )

    boardroom.narrate(
        f"CCO and Compliance just mapped the regulatory obligation gaps:\n"
        f"CCO: {cco_response[:400]}...\nCompliance: {compliance_response[:400]}...\n\n"
        "For the reader: explain IFRS 9 Expected Credit Loss in plain language — what is "
        "Stage 1, Stage 2, Stage 3, and why this accounting standard, introduced in 2018, "
        "fundamentally changed how banks recognize losses. Also explain BCBS 239 and why "
        "regulators care so much about a bank's ability to aggregate risk data quickly."
    )

    # ── PART 6: TREASURY ON ALM GAPS ─────────────────────────────────────────
    boardroom._render_section_header("PART VI: TREASURY — ALM AND FTP GAPS")

    treasury_response = boardroom.call_agent(
        "Treasury",
        f"""Victoria identified two gaps that are central to my function:

1. No ALM / Interest Rate Risk Engine — she says I operate blind without NII
   sensitivity, EVE sensitivity, repricing gap analysis, and behavioral assumptions
   (mortgage prepayment, deposit stickiness). She is right. This is fundamental.

2. No Fund Transfer Pricing (FTP) — trading desk P&L is economically meaningless
   because I cannot charge desks for the cost of their funding positions.

Context from the discussion so far:
- CFO's priority framework: {cfo_response[:200]}...
- CTO's build effort view: {cto_response[:200]}...

Tell the group: what does an ALM engine actually need to compute NII and EVE
sensitivity? What's the dependency chain? And on FTP — how does a real bank
implement internal funding charges, and what's the minimum viable FTP model
that would make our P&L calculations meaningful?""",
        max_tokens=1500,
    )

    boardroom.narrate(
        f"The Head of Treasury described the ALM and FTP gaps:\n\n{treasury_response[:500]}\n\n"
        "For the reader: explain Asset-Liability Management in a bank — why do banks care "
        "about the difference between their assets repricing at fixed rates vs. floating rates? "
        "What happened to Silicon Valley Bank in 2023 and how was it fundamentally an ALM "
        "failure? And explain Fund Transfer Pricing — why does a bank need an internal price "
        "for funding and what happens when it's absent?"
    )

    # ── PART 7: DEBATE — WHAT TO BUILD FIRST ─────────────────────────────────
    boardroom._render_section_header("PART VII: THE DEBATE — SEQUENCING THE BUILD")

    console.print(
        "\n[dim italic]Facilitator: We've heard all perspectives. Now the debate: "
        "what do we build first? CTO and CRO, you have the floor — go directly "
        "at each other's priorities.[/dim italic]\n"
    )

    cto_priority = boardroom.call_agent(
        "CTO",
        f"""The group has surfaced all the gaps. Now we decide sequencing.

Here's where I think we disagree with CRO:

My view: infrastructure first. The Regulatory Capital Engine and IFRS 9 engine are
important, but they sit on top of broken infrastructure. If we don't fix the
in-memory state problem, the event sourcing absence, and the missing instrument
master first — we'll build the capital engine on sand and have to rebuild it.

CRO wants: risk controls and regulatory capital first.
CFO wants: regulatory obligations first, then risk reduction.
I want: foundation first — event sourcing, instrument master, entity model — then
build the risk and regulatory engines on top.

Make the case for the sequencing that gives us the highest-quality outcome.
Specifically: what is the minimum viable technical foundation before we build
any of the regulatory/risk engines Victoria described?""",
        max_tokens=1500,
    )

    cro_counter = boardroom.call_agent(
        "CRO",
        f"""The CTO wants to build infrastructure before risk engines.
CTO's argument: {cto_priority[:400]}...

I disagree — or at least I want to challenge the premise.

The Regulatory Capital Engine is not optional infrastructure. It is the OUTPUT that
regulators demand. The Fed does not give us a grace period because our event bus is
not yet Kafka-native. In 2016, Deutsche Bank's remediation plan under the DOJ and
Fed consent order had to produce credible capital calculations within 90 days —
before any infrastructure modernization was complete.

My counter: we can build the Regulatory Capital Engine as a standalone module that
reads from the current position manager, outputs credible CET1/RWA numbers, and can
be re-plumbed to better infrastructure later. The risk of building infrastructure
first is that we spend 6 months on plumbing and produce nothing demonstrable.

Respond to my counter directly. Where do we actually agree and where do we
genuinely diverge?""",
        max_tokens=1400,
    )

    ceo_arbitrates = boardroom.call_agent(
        "CEO",
        f"""CTO says: build infrastructure first (event sourcing, entity model, instrument master).
CRO says: build regulatory capital engine first, even on current infrastructure.
CFO says: regulatory obligation items first.

CTO position: {cto_priority[:300]}...
CRO counter: {cro_counter[:300]}...

Arbitrate this. We can't build everything in parallel with unlimited resources.
Give me a decision: what is the phased sequencing?

Use this structure:
- Phase 1 (0-60 days): Quick wins and foundation
- Phase 2 (60-180 days): Core regulatory and risk engines
- Phase 3 (180-365 days): Advanced capabilities

For each phase, specify: what gets built, who owns it, what the acceptance criteria
are, and what risk we are explicitly accepting by deferring the rest.""",
        max_tokens=2000,
        use_thinking=True,
    )

    boardroom.narrate(
        f"The CTO and CRO debated sequencing; the CEO arbitrated:\n"
        f"CTO: {cto_priority[:300]}...\nCRO: {cro_counter[:300]}...\n"
        f"CEO: {ceo_arbitrates[:400]}...\n\n"
        "For the reader: this debate — infrastructure vs. deliverables, foundation vs. "
        "output — is one of the most common and consequential arguments in financial "
        "technology. Explain why it matters, what happens when you get the sequencing "
        "wrong, and what Deutsche Bank's 2015-2017 remediation program actually looked "
        "like in practice."
    )

    # ── PART 8: AGENT ROSTER DECISIONS ───────────────────────────────────────
    boardroom._render_section_header("PART VIII: MISSING AGENT ROLES — WHO DO WE HIRE?")

    ceo_agents = boardroom.call_agent(
        "CEO",
        f"""Victoria identified 9 missing agent roles. We can't build all of them immediately.

Critical missing (her assessment):
1. General Counsel — legal entity governance, regulatory enforcement
2. CDO (Dr. Fatima Al-Rashid) — BCBS 239, data governance, risk data aggregation
3. CISO (Ivan Petrov) — cyber risk, first-order risk category
4. Head of Operations (Chen Wei) — settlement, resilience, outsourcing risk

Significant missing:
5. Internal Audit — third line of defense, completely absent
6. Model Validation Officer — independent of Quant, SR 11-7 compliance
7. Head of Investor Relations — manages narrative to rating agencies in stress
8. Deputy CRO / Market Risk Officer — CRO currently conflates 4 risk types
9. Tax Director — FATCA, BEPS, Pillar Two at global scale

We've already spent time on infrastructure. Now the organizational question:
which agent roles do we bring into the boardroom in our next phase, and in what order?

Give me a prioritized hiring plan with rationale for each role's timing.
And for each role: what system dependencies need to exist BEFORE that agent
can function meaningfully (e.g., no point having an Internal Audit agent if
there's nothing to audit)?""",
        max_tokens=1800,
        use_thinking=True,
    )

    boardroom.narrate(
        f"The CEO laid out the agent hiring plan:\n\n{ceo_agents[:600]}\n\n"
        "For the reader: in a real bank, what does an organizational build-out look like "
        "after a major consulting engagement? How do boards respond to findings like "
        "Victoria's? What typically gets built, what gets deferred, and what gets buried? "
        "And explain what the CDO role actually means in a modern bank — this role barely "
        "existed 10 years ago."
    )

    # ── PART 9: FINAL IMPLEMENTATION PLAN ────────────────────────────────────
    boardroom._render_section_header("PART IX: FINAL IMPLEMENTATION PLAN")

    ceo_final = boardroom.call_agent(
        "CEO",
        f"""We've heard from every function. Now synthesize into our formal response
to Victoria Ashworth and our implementation plan.

Context built throughout this session:
- CTO's infrastructure sequencing: {cto_priority[:200]}...
- CRO's risk-first counter: {cro_counter[:200]}...
- CFO's ROI framework: {cfo_response[:200]}...
- CCO's regulatory exposure: {cco_response[:200]}...
- Treasury's ALM/FTP needs: {treasury_response[:200]}...
- Compliance's 3LoD gaps: {compliance_response[:200]}...
- CEO's agent hiring plan: {ceo_agents[:200]}...

Produce the final implementation plan in this format:

## PHASE 1 — Foundation & Quick Wins (0-60 days)
[List each item: what, owner, acceptance criteria, risk if deferred]

## PHASE 2 — Core Regulatory & Risk Engines (60-180 days)
[Same format]

## PHASE 3 — Advanced Capabilities & Full Agent Roster (180-365 days)
[Same format]

## RESPONSE TO VICTORIA ASHWORTH
[One paragraph: what we agree with, what we accept, what we respectfully challenge,
and what we commit to deliver in 12 months]

## WHAT WE WILL NOT BUILD (and why)
[Explicit list of items we are deferring beyond 12 months and the rationale]

Be specific and honest. This is the plan we will execute against.""",
        max_tokens=3000,
        use_thinking=True,
    )

    boardroom.narrate(
        f"The CEO delivered the final implementation plan:\n\n{ceo_final[:800]}\n\n"
        "For the reader — the closing synthesis:\n"
        "1. Summarize what this meeting revealed about how a real bank responds to an "
        "external consulting assessment\n"
        "2. What were the three most important tensions that surfaced in this room?\n"
        "3. What does it mean to build a 'credible' bank simulation — what's the "
        "difference between a demo and something practitioners would actually use?\n"
        "4. What should the reader take away about the complexity of modern bank "
        "technology infrastructure?\n"
        "5. Your honest assessment: did the team produce a plan that will satisfy "
        "Victoria Ashworth when she reviews it in 90 days?",
        max_tokens=1800,
    )

    boardroom.close_session()
    boardroom.export_transcript(export_path)


if __name__ == "__main__":
    run_consulting_review_meeting()
