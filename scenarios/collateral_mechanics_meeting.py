"""
Collateral Mechanics & Simulation Design — Board Session

Relevant stakeholders discuss the full collateral lifecycle:
Variation Margin, Initial Margin, ISDA/CSA framework, SIMM,
rehypothecation, collateral optimization, and the design of a
credible collateral simulation module for Apex Global Bank.

Run:
    python3 scenarios/collateral_mechanics_meeting.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent.parent))

import anthropic
from orchestrator.boardroom import Boardroom
from agents.executive.ceo import create_ceo
from agents.executive.cro import create_cro
from agents.executive.head_of_treasury import create_head_of_treasury
from agents.executive.cfo import create_cfo
from agents.markets.lead_trader import create_lead_trader
from agents.markets.quant_researcher import create_quant_researcher
from agents.legal.general_counsel import create_general_counsel
from agents.narrator.observer import create_observer


def run(export_path: str = "transcript_collateral_mechanics.md") -> None:
    client = anthropic.Anthropic()

    ceo      = create_ceo(client)
    cro      = create_cro(client)
    treasury = create_head_of_treasury(client)
    cfo      = create_cfo(client)
    trader   = create_lead_trader(client)
    quant    = create_quant_researcher(client)
    gc       = create_general_counsel(client)
    observer = create_observer(client)

    boardroom = Boardroom(
        agents={
            "CEO":      ceo,
            "CRO":      cro,
            "Treasury": treasury,
            "CFO":      cfo,
            "Trader":   trader,
            "Quant":    quant,
            "GC":       gc,
        },
        observer=observer,
        session_name="Apex Global Bank — Collateral Mechanics & Simulation Design",
    )

    boardroom.open_session()

    # ── I: CEO SETS THE AGENDA ─────────────────────────────────────────────
    boardroom._render_section_header("PART I: WHY COLLATERAL IS THE HIDDEN ENGINE OF DERIVATIVES")

    ceo_open = boardroom.call_agent(
        "CEO",
        """Open this session on collateral mechanics and simulation design.

We have just received a consulting assessment noting that collateral management
is entirely absent from our simulation platform. Victoria Ashworth called it out
as a Tier 1 structural gap: 'In a stress event, collateral calls are the
operational trigger before credit losses crystallize on paper.'

I want to understand two things:
1. What collateral management actually means mechanically — from ISDA Master
   Agreements to daily margin calls to rehypothecation
2. What it would take to build a credible collateral simulation layer in our platform

Set the agenda for the group. What are the most important things to get right?""",
        max_tokens=1400, use_thinking=True,
    )

    boardroom.narrate(
        f"The CEO opened with: {ceo_open[:500]}...\n\n"
        "For the reader: what is collateral in the derivatives context? "
        "Why do counterparties post collateral to each other? "
        "Explain the 2008 AIG failure as a collateral story — what happened when "
        "AIG couldn't meet its margin calls, and why that nearly broke the global "
        "financial system. Make it visceral."
    )

    # ── II: GC — LEGAL ARCHITECTURE OF COLLATERAL ─────────────────────────
    boardroom._render_section_header("PART II: THE LEGAL ARCHITECTURE — ISDA, CSA, CLOSE-OUT NETTING")

    gc_legal = boardroom.call_agent(
        "GC",
        f"""The CEO has framed the agenda: {ceo_open[:300]}...

As General Counsel, walk the group through the legal architecture underpinning
all collateral arrangements:

1. The ISDA Master Agreement — what it is, what it governs, why it took decades
   to standardise
2. The Credit Support Annex (CSA) — the document that actually governs collateral.
   Walk through its key terms: threshold, minimum transfer amount, independent
   amount, eligible collateral, haircuts, dispute resolution
3. Close-out netting — why this is the single most important legal concept in
   derivatives. What happens when a counterparty defaults and you have 500 trades
   with them across 12 legal entities
4. The enforceability problem — why we need netting opinions in every jurisdiction
   we operate in, and what happens in jurisdictions where netting is not legally
   enforceable

Be specific about the numbers — what do these terms look like in practice?""",
        max_tokens=2000, use_thinking=True,
    )

    boardroom.narrate(
        f"The General Counsel laid out the legal framework:\n\n{gc_legal[:600]}...\n\n"
        "For the reader: what is an ISDA Master Agreement? Why did it take the "
        "derivatives industry 30 years to standardise these documents? "
        "Explain 'close-out netting' using the analogy of a tab at a bar — "
        "why netting 500 positions into one number matters so much. "
        "And explain the Lehman Brothers close-out in 2008: the largest derivatives "
        "close-out in history, $35 trillion notional, how it was actually executed."
    )

    # ── III: TREASURY — THE OPERATIONAL MECHANICS ─────────────────────────
    boardroom._render_section_header("PART III: TREASURY — VARIATION MARGIN, INITIAL MARGIN, THE DAILY GRIND")

    treasury_mech = boardroom.call_agent(
        "Treasury",
        f"""The GC has explained the legal framework. Now the operational mechanics.

Walk through the daily collateral lifecycle from Treasury's perspective:

1. Variation Margin (VM) — what triggers a VM call, how it's calculated,
   the settlement timeline (T+1 for cleared, same-day for bilateral),
   what happens when a counterparty disputes the call
2. Initial Margin (IM) — why IM exists separately from VM, how it's calculated
   (SIMM vs. grid/schedule approach), where it's held (segregated vs. commingled),
   how it interacts with the CSA
3. The Margin Call process — walk through a specific example: we have a $500M
   IRS book with Goldman Sachs, rates move 25bps overnight. Walk the call from
   mark-to-market recalculation through dispute resolution to settlement
4. Rehypothecation — what it means to reuse counterparty collateral, why it's
   operationally critical and systemic risk amplifier at the same time
5. Collateral transformation — using repo to turn illiquid assets into eligible
   collateral

GC said: {gc_legal[:200]}...""",
        max_tokens=2000, use_thinking=True,
    )

    boardroom.narrate(
        f"Treasury described the operational mechanics:\n\n{treasury_mech[:600]}...\n\n"
        "For the reader: explain Variation Margin vs. Initial Margin simply. "
        "VM = marking the trade to market daily (like a brokerage account). "
        "IM = an extra buffer for gap risk. "
        "Explain what happened during the March 2020 COVID crash when everyone "
        "got margin calls simultaneously — the 'dash for cash' and why central "
        "banks had to intervene. Numbers: $500B+ in margin calls in a week."
    )

    # ── IV: QUANT — SIMM AND IM CALCULATION ───────────────────────────────
    boardroom._render_section_header("PART IV: QUANTITATIVE MECHANICS — SIMM, PFE, AND IM MODELS")

    quant_simm = boardroom.call_agent(
        "Quant",
        f"""Treasury has explained the operational flow. Now the quantitative engine.

1. SIMM (ISDA Standard Initial Margin Model) — explain the methodology:
   sensitivity-based, delta/vega/curvature risk classes, risk weights, correlation
   parameters, how it produces an IM number for a given portfolio
2. PFE (Potential Future Exposure) — how it relates to IM, the difference
   between Current Exposure (mark-to-market) and PFE, why the 95th percentile
   over the margin period of risk is the key number
3. The Margin Period of Risk (MPoR) — why it's 10 days for bilateral, 5 days
   for cleared, how it determines both IM requirements and XVA calculations
4. Wrong-Way Risk — when exposure and counterparty default probability are
   positively correlated. Give the classic example: a bank selling protection
   on its own sovereign via CDS
5. For the simulation: what are the minimum mathematical components needed to
   compute a credible SIMM approximation for our derivative positions?

Treasury said: {treasury_mech[:200]}...""",
        max_tokens=1800, use_thinking=True,
    )

    boardroom.narrate(
        f"The Quant explained the SIMM methodology:\n\n{quant_simm[:600]}...\n\n"
        "For the reader: explain the Margin Period of Risk intuitively — "
        "why does it take 10 days to close out a bilateral derivatives position "
        "when a counterparty defaults? Walk through the operational sequence: "
        "default notification, position verification, market impact of unwinding, "
        "basis risk. And explain why SIMM replaced the old Schedule approach: "
        "BCBS-IOSCO uncleared margin rules, the phase-in timeline, why the "
        "industry built SIMM rather than let each firm use its own model."
    )

    # ── V: CRO — COLLATERAL AS RISK MITIGATION ────────────────────────────
    boardroom._render_section_header("PART V: CRO — COLLATERAL IN THE RISK FRAMEWORK")

    cro_risk = boardroom.call_agent(
        "CRO",
        f"""The Quant has walked through SIMM and PFE. From the risk management perspective:

1. How collateral fits into the CCR (Counterparty Credit Risk) framework — the
   difference between uncollateralised and collateralised exposure, how CSA terms
   affect CVA and XVA calculations
2. SA-CCR (Standardised Approach for CCR under Basel III) — how regulators
   require us to calculate EAD for collateralised derivatives, the replacement
   cost + PFE multiplier structure, how CSA thresholds affect the multiplier
3. The wrong-way risk problem in our current simulation — we have counterparty
   exposures but no collateral layer. What is the quantitative error this
   introduces in our CVA numbers?
4. Collateral disputes as a stress signal — in 2008, the first sign of a
   counterparty problem was when they started disputing margin calls. How do we
   model this leading indicator in a stress simulation?
5. Concentration risk in collateral — what happens when everyone posts the same
   collateral (US Treasuries) and you need to liquidate it simultaneously?

Quant said: {quant_simm[:200]}...""",
        max_tokens=1800, use_thinking=True,
    )

    # ── VI: TRADER — DESK PERSPECTIVE ON COLLATERAL ───────────────────────
    boardroom._render_section_header("PART VI: LEAD TRADER — HOW COLLATERAL AFFECTS DESK P&L")

    trader_view = boardroom.call_agent(
        "Trader",
        f"""The CRO has covered the risk framework. From the desk:

1. The funding cost of collateral — when we post cash as VM, that cash has a
   cost (the OIS rate). When we receive cash VM, we earn on it. How does this
   net funding cost affect desk P&L and how does it relate to the CVA/FVA
   adjustment our Quant prices into trades?
2. Collateral optionality in CSAs — some CSAs allow the poster to choose which
   eligible asset to post (cheapest-to-deliver). What is this option worth and
   how do traders monetize it?
3. The operational drag — describe the daily reality of a derivatives desk
   that manages 200+ ISDA relationships. How much of the desk's time is
   consumed by collateral operations vs. actual trading?
4. The cross-product netting benefit — how netting across rates, credit, and
   FX positions with a single counterparty reduces collateral requirements,
   and why this affects our choice of which products to trade with which
   counterparties

CRO said: {cro_risk[:200]}...""",
        max_tokens=1500,
    )

    boardroom.narrate(
        f"The CRO and Trader covered the risk and desk perspectives:\n"
        f"CRO: {cro_risk[:300]}...\nTrader: {trader_view[:300]}...\n\n"
        "For the reader: explain CVA (Credit Valuation Adjustment) and FVA "
        "(Funding Valuation Adjustment) in plain language. CVA = the market "
        "value of counterparty default risk. FVA = the funding cost of posting "
        "collateral. Together these are part of the 'XVA' adjustments that "
        "derivative desks price into every trade. Explain why the 2008 crisis "
        "made these adjustments mainstream — before 2008, most banks priced "
        "derivatives as if their counterparties would never default."
    )

    # ── VII: CFO — BALANCE SHEET IMPACT ───────────────────────────────────
    boardroom._render_section_header("PART VII: CFO — BALANCE SHEET AND CAPITAL TREATMENT")

    cfo_balance = boardroom.call_agent(
        "CFO",
        f"""We've covered the mechanics, risk, and desk perspective.
The balance sheet and capital view:

1. How collateral appears on the balance sheet — gross vs. net presentation,
   why the US GAAP / IFRS difference in netting creates enormous apparent size
   differences between US and European bank balance sheets
2. The capital treatment of collateralised exposures — how SA-CCR affects RWA,
   why a CSA with a zero threshold can dramatically reduce capital requirements
   vs. an uncollateralised trade
3. Liquidity implications — eligible collateral that is posted is not available
   for other uses. How does this show up in the LCR (Liquidity Coverage Ratio)
   calculation? What is the 'liquidity value' of having unencumbered high-quality
   liquid assets (HQLA)?
4. The cost of the new uncleared margin rules (UMR) — the BCBS-IOSCO rules
   requiring bilateral IM posting went live in phases 2016-2022. What was the
   industry-wide liquidity impact? How much collateral was mobilised?

Treasury: {treasury_mech[:200]}...""",
        max_tokens=1500,
    )

    # ── VIII: SIMULATION DESIGN DEBATE ────────────────────────────────────
    boardroom._render_section_header("PART VIII: SIMULATION DESIGN — WHAT DO WE BUILD?")

    quant_design = boardroom.call_agent(
        "Quant",
        f"""We've done the full conceptual walkthrough. Now the engineering question:
what should a collateral simulation module look like for Apex Global Bank Simulator?

Design a minimum viable collateral engine that would make our platform credible.
Structure your answer as:

**Core Data Model:**
What objects do we need? (CSA, CollateralAccount, MarginCall, CollateralPool...)

**VM Calculation:**
Given a portfolio of positions with MTM values, how do we calculate daily VM calls?
What's the algorithm?

**IM Calculation (SIMM approximation):**
A full SIMM implementation is complex. What's a defensible simplification that
preserves the key behaviours — sensitivity to portfolio delta/vega, correlation
offsets across risk classes?

**Collateral Call Simulation:**
How do we model a stress scenario where we issue 50 margin calls simultaneously,
some counterparties dispute, some are late, one defaults?

**Integration Points:**
How does this connect to our existing XVA adapter, position manager,
and counterparty registry?

Be specific about data structures and algorithms, not just concepts.
This is a design spec.""",
        max_tokens=2500, use_thinking=True,
    )

    treasury_design = boardroom.call_agent(
        "Treasury",
        f"""The Quant has proposed a simulation design.

From an operational realism perspective — what is the Quant missing?
The design needs to capture not just the mathematics but the operational failure
modes that actually matter:

1. Dispute workflow — how do we simulate a counterparty disputing a call?
   What's the resolution mechanism?
2. Collateral substitution — modelling when a counterparty wants to substitute
   posted collateral (e.g. swap Treasuries for agency bonds)
3. Intraday margin calls — CCP variation margin is now often intraday. How do
   we model that?
4. Collateral transformation chains — the $20T repo market as the plumbing
   behind collateral flows. Should we model the repo desk?
5. The optimisation problem — given that we have eligible collateral across
   multiple accounts and need to meet 15 margin calls by 10am, how do we
   allocate collateral to minimise cost?

Quant design: {quant_design[:400]}...""",
        max_tokens=1500,
    )

    cro_design = boardroom.call_agent(
        "CRO",
        f"""Quant designed the engine. Treasury added operational realism.

From the risk perspective, what are the stress scenarios the simulation MUST
be able to run to be credible for a risk audience?

Design 3 specific collateral stress scenarios:

1. **The Systemic Margin Call** — a 2020 COVID-style event where volatility
   doubles in 48 hours and we issue/receive $10B+ in margin calls simultaneously
2. **The Counterparty Default** — a Lehman-style single counterparty default
   with $50B notional exposure across 800 trades. Walk through the close-out
   netting waterfall
3. **The Collateral Quality Shock** — government bonds (our main posted
   collateral) fall 15% due to a sovereign debt crisis. How does this affect
   our IM haircuts and trigger additional calls?

For each scenario: what data inputs do we need, what outputs does the simulation
produce, and what decisions does each agent (CEO, CRO, Treasury, Trader) need
to make?

Quant design: {quant_design[:300]}...\nTreasury additions: {treasury_design[:300]}...""",
        max_tokens=1800, use_thinking=True,
    )

    boardroom.narrate(
        f"The team designed the collateral simulation engine:\n"
        f"Quant spec: {quant_design[:300]}...\n"
        f"Treasury additions: {treasury_design[:300]}...\n"
        f"CRO stress scenarios: {cro_design[:300]}...\n\n"
        "For the reader: explain the $20 trillion global repo market. "
        "Why is it called 'the plumbing of the financial system'? "
        "What happened to repo markets in September 2019 when overnight rates "
        "spiked to 10%? And explain the systemic amplification mechanism: "
        "when collateral falls in value, everyone gets margin calls simultaneously, "
        "everyone sells assets to raise cash, asset prices fall further, "
        "generating more margin calls — the doom loop."
    )

    # ── IX: CEO — IMPLEMENTATION DECISION ─────────────────────────────────
    boardroom._render_section_header("PART IX: CEO — IMPLEMENTATION PLAN AND DECISIONS")

    ceo_close = boardroom.call_agent(
        "CEO",
        f"""We've had the full technical discussion. Make the implementation decisions.

Summary of what we've heard:
- GC: ISDA/CSA legal framework, close-out netting as the critical legal concept
- Treasury: VM/IM daily mechanics, MPoR, rehypothecation, collateral optimisation
- Quant: SIMM approximation design, PFE/MPoR, Wrong-Way Risk
- CRO: SA-CCR capital treatment, stress scenarios (systemic call, default, quality shock)
- Trader: Funding cost (FVA), cheapest-to-deliver optionality, desk drag
- CFO: Balance sheet treatment, LCR impact, UMR liquidity costs

Based on this, give me:

**1. Build decision:** Do we build a collateral simulation module? If yes, what's
the MVP scope vs. full scope?

**2. Prioritisation:** Where does this sit relative to our other Phase 2 items
(legal entity model, 3LoD CQRS, DFAST stress testing)?

**3. The design decisions:** From the Quant/Treasury/CRO proposals — what do
we commit to building? What do we explicitly defer?

**4. The integration question:** Our existing XVA adapter computes CVA/DVA/FVA.
Does a collateral module go inside the XVA layer, alongside it, or above it?

**5. The simulation scenario:** What is the single most compelling demonstration
scenario that a collateral module enables — the 'demo that sells the platform'?""",
        max_tokens=2000, use_thinking=True,
    )

    boardroom.narrate(
        f"The CEO delivered the implementation decision:\n\n{ceo_close[:700]}...\n\n"
        "Closing synthesis for the reader:\n"
        "1. What is the most important thing this session revealed about how "
        "collateral actually works in a modern bank?\n"
        "2. Why is collateral management one of the most underappreciated but "
        "systemically critical functions in finance?\n"
        "3. What does the 2008 financial crisis look like through the lens of "
        "collateral failure — specifically the AIG, Lehman, and Bear Stearns stories?\n"
        "4. If we build this collateral simulation module, what becomes possible "
        "that isn't possible today?\n"
        "5. Your honest verdict: after this session, is Apex Global Bank ready "
        "to simulate a collateral-driven stress event credibly?",
        max_tokens=1800,
    )

    boardroom.close_session()
    boardroom.export_transcript(export_path)


if __name__ == "__main__":
    run()
