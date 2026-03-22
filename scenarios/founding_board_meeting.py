"""
Founding Board Meeting — the inaugural discussion between all agents.

This scenario walks through the establishment of Apex Global Bank's
AI-native infrastructure. Each agent contributes their perspective,
the Observer explains what's happening for the reader, and the
group discusses which additional agents the bank needs.

Think of this as watching a real founding meeting of a major financial
institution, with a knowledgeable guide explaining every concept.
"""

from __future__ import annotations
import anthropic
from rich.console import Console

from agents.executive.ceo import create_ceo
from agents.executive.cto import create_cto
from agents.executive.cro import create_cro
from agents.markets.lead_trader import create_lead_trader
from agents.markets.trading_desk import create_trading_desk
from agents.markets.quant_researcher import create_quant_researcher
from agents.compliance.compliance_officer import create_compliance_officer
from agents.narrator.observer import create_observer
from orchestrator.boardroom import Boardroom

console = Console(width=120)


def run_founding_meeting(export_path: str = "transcript_founding_meeting.md") -> None:
    """
    Run the full founding board meeting scenario.
    Estimated runtime: 8-15 minutes (depends on API response times).
    """
    client = anthropic.Anthropic()

    # Instantiate all agents
    ceo = create_ceo(client)
    cto = create_cto(client)
    cro = create_cro(client)
    lead_trader = create_lead_trader(client)
    trading_desk = create_trading_desk(client)
    quant = create_quant_researcher(client)
    compliance = create_compliance_officer(client)
    observer = create_observer(client)

    # Build the boardroom
    boardroom = Boardroom(
        agents={
            "CEO":           ceo,
            "CTO":           cto,
            "CRO":           cro,
            "Lead Trader":   lead_trader,
            "Trading Desk":  trading_desk,
            "Quant":         quant,
            "Compliance":    compliance,
        },
        observer=observer,
        session_name="Apex Global Bank — Founding Architecture Session",
    )

    boardroom.open_session()

    # ─── PART 1: CEO SETS THE VISION ─────────────────────────────────────────
    boardroom._render_section_header("PART I: THE VISION")

    ceo_vision = boardroom.call_agent(
        "CEO",
        """We're here to design Apex Global Bank's next-generation infrastructure.
        The goal: build a bank that operates at the scale of JPMorgan, with the
        intelligence of an AI-native technology company, and the risk discipline of
        the Swiss central bank.

        Please open this session by sharing your vision for what we're building,
        why it matters strategically, and what success looks like in 5 years.""",
        show_prompt=True,
        max_tokens=1800,
    )

    boardroom.narrate(
        f"The CEO just opened the session with this vision:\n\n{ceo_vision[:800]}\n\n"
        "Please provide a [DEEP DIVE] on what a global bank like JPMorgan actually does "
        "and why building this kind of institution is so complex. Explain to the reader "
        "the key revenue streams, the scale involved, and what 'AI-native banking' means "
        "in concrete terms."
    )

    # ─── PART 2: CTO LAYS OUT THE TECHNOLOGY ARCHITECTURE ────────────────────
    boardroom._render_section_header("PART II: TECHNOLOGY ARCHITECTURE")

    cto_arch = boardroom.call_agent(
        "CTO",
        f"""The CEO has set an ambitious vision: {ceo_vision[:300]}...

        As CTO, walk us through the technology architecture needed to support this.
        Cover: the trading infrastructure (low latency), the risk platform (real-time),
        the data strategy (AI fuel), and how you'd build the AI layer on top.
        Be specific about technology choices and the engineering challenges.""",
        max_tokens=2000,
    )

    boardroom.narrate(
        f"The CTO just described the technology architecture:\n\n{cto_arch[:800]}\n\n"
        "Please provide a [DEEP DIVE] on the technology stack of a major bank. "
        "Explain what 'low latency' really means in trading (nanoseconds matter!), "
        "why banks still use COBOL mainframes, and how the AI revolution is colliding "
        "with 50-year-old legacy systems. This is one of the great engineering challenges "
        "of our time — help the reader appreciate it."
    )

    # ─── PART 3: TRADING DESK DESCRIBES THE DAILY REALITY ────────────────────
    boardroom._render_section_header("PART III: THE TRADING OPERATION")

    desk_reality = boardroom.call_agent(
        "Trading Desk",
        f"""The CEO and CTO have set the strategic and technical direction.
        Now describe the trading operation from the desk's perspective.
        What does a normal trading day look like? What books are we running?
        How do we make money? What can go wrong and what does the desk do when it does?
        Be specific — walk us through the 07:00 to 18:00 of the trading desk.""",
        max_tokens=1800,
    )

    lead_trader_response = boardroom.call_agent(
        "Lead Trader",
        f"""The Trading Desk described our daily operation:
        {desk_reality[:400]}...

        As Head of Trading, add the strategic layer. What trading businesses
        should Apex prioritize in year one? How should we think about risk capital
        allocation across desks? And what's your view on where AI creates the
        biggest edge in trading today?""",
        max_tokens=1500,
    )

    boardroom.narrate(
        f"The Trading Desk described its daily reality and the Lead Trader added strategic direction.\n"
        f"Desk: {desk_reality[:400]}...\nTrader: {lead_trader_response[:400]}...\n\n"
        "Please provide:\n"
        "1. A [DEEP DIVE] on how banks make money from trading (market-making, prop trading, "
        "flow trading) and why these are fundamentally different\n"
        "2. A [TENSION WATCH] on the relationship between the Trading Desk (execution) and "
        "the Lead Trader (strategy) — what happens when they disagree?\n"
        "3. A [NUMBERS MATTER] section on the scale of daily trading at a major bank"
    )

    # ─── PART 4: QUANT EXPLAINS THE MODELS ───────────────────────────────────
    boardroom._render_section_header("PART IV: THE QUANTITATIVE FOUNDATION")

    quant_models = boardroom.call_agent(
        "Quant",
        f"""You've heard the CEO's vision, the CTO's architecture, and the trading desk's
        reality. Now explain the quantitative foundation that makes all of this work.
        What models does the bank need for pricing, risk, and alpha generation?
        How is AI/ML changing quantitative finance?
        And what's the danger of relying too heavily on models?""",
        max_tokens=1800,
    )

    boardroom.narrate(
        f"The Head of Quant Research explained the mathematical foundation:\n\n{quant_models[:600]}\n\n"
        "Please provide:\n"
        "1. A [DEEP DIVE] on what 'quantitative finance' actually means — explain Black-Scholes, "
        "VaR, and factor models to a non-technical reader using intuitive analogies\n"
        "2. A [HISTORICAL CONTEXT] on famous quant disasters: LTCM (1998), the 'Quant Quake' "
        "of 2007, and what they teach us about model risk\n"
        "3. Your perspective on whether AI is making finance safer or more dangerous"
    )

    # ─── PART 5: CRO SETS THE RISK FRAMEWORK ─────────────────────────────────
    boardroom._render_section_header("PART V: THE RISK FRAMEWORK")

    cro_framework = boardroom.call_agent(
        "CRO",
        f"""We've heard the vision, architecture, trading operations, and quant models.
        Now I need to hear your risk framework.
        What risk infrastructure does this bank need? How do you balance enabling
        the trading business with protecting the franchise?
        Walk us through VaR, stress testing, limit structures, and what keeps you
        up at night about AI-driven trading.""",
        max_tokens=1800,
    )

    # CTO responds to CRO on real-time risk
    cto_risk_response = boardroom.call_agent(
        "CTO",
        f"""The CRO has outlined the risk framework. From a technology perspective,
        how do we build a real-time risk engine that can compute VaR, Greeks, and
        limits on every trade in under 1 millisecond — at scale?
        The CRO needs: {cro_framework[:300]}
        What's the technology blueprint for this?""",
        max_tokens=1200,
    )

    boardroom.narrate(
        f"The CRO set the risk framework and the CTO responded with the technology blueprint.\n"
        f"CRO: {cro_framework[:400]}...\nCTO: {cto_risk_response[:400]}...\n\n"
        "Please provide:\n"
        "1. A [DEEP DIVE] on Value at Risk — explain it simply, explain why it failed in 2008, "
        "and explain what replaced it (Expected Shortfall)\n"
        "2. A [TENSION WATCH] on the fundamental conflict between risk managers and traders "
        "— this is one of the most important tensions in banking\n"
        "3. A [HISTORICAL CONTEXT] on the 2008 Global Financial Crisis from a risk management "
        "perspective — what did banks get wrong?"
    )

    # ─── PART 6: COMPLIANCE COMPLETES THE PICTURE ────────────────────────────
    boardroom._render_section_header("PART VI: COMPLIANCE & REGULATION")

    compliance_view = boardroom.call_agent(
        "Compliance",
        f"""We've designed the strategy, technology, trading operation, quant models, "
        and risk framework. Complete the picture with the compliance and regulatory layer.
        What are the top 5 compliance risks for an AI-native global bank?
        How does compliance infrastructure work — the three lines of defense?
        And specifically: what does the regulators' view of AI in banking look like right now?""",
        max_tokens=1800,
    )

    boardroom.narrate(
        f"The CCO described the compliance framework:\n\n{compliance_view[:600]}\n\n"
        "Please provide:\n"
        "1. A [DEEP DIVE] on AML and KYC — why banks spend billions on this and what happens "
        "when they get it wrong (HSBC $1.9B fine, Wachovia $160M fine)\n"
        "2. A [DEEP DIVE] on Basel III — explain bank capital requirements to someone who "
        "has never heard of it, using the analogy of a house with a down payment\n"
        "3. The big picture: how does regulation shape the entire structure of banking?"
    )

    # ─── PART 7: THE AGENT TEAM DISCUSSION ───────────────────────────────────
    boardroom._render_section_header("PART VII: BUILDING THE AGENT TEAM")

    # CEO kicks off the agent team discussion
    agent_team_prompt = boardroom.call_agent(
        "CEO",
        """We've covered the major functions. Now let's have a frank discussion about
        our AI agent team. We currently have: CEO, CTO, CRO, Head of Trading, Trading Desk,
        Head of Quant Research, and Chief Compliance Officer.

        What critical functions are missing from this team? Think about the full lifecycle
        of a global bank — from client acquisition to settlement, from model development
        to regulatory reporting. Who else needs a seat at this table?""",
        max_tokens=1500,
    )

    # Each executive adds their perspective on missing agents
    cto_agents = boardroom.call_agent(
        "CTO",
        f"""The CEO asked about missing agents: {agent_team_prompt[:300]}...

        From a technology perspective, what functional roles need representation?
        Think about data engineering, cybersecurity, cloud infrastructure, and
        the operational technology that keeps the bank running 24/7.""",
        max_tokens=1000,
    )

    cro_agents = boardroom.call_agent(
        "CRO",
        f"""What agent roles are missing from a risk and control perspective?
        Consider: credit risk (separate from market risk), liquidity risk,
        operational risk, model risk management, and the treasury function.""",
        max_tokens=1000,
    )

    trading_agents = boardroom.call_agent(
        "Lead Trader",
        f"""What's missing from the trading and markets side?
        Think about: sales and client coverage, prime brokerage, treasury,
        structured products, and the back-office/operations function that
        actually settles our trades.""",
        max_tokens=1000,
    )

    boardroom.narrate(
        f"The team discussed what agents are missing. CEO: {agent_team_prompt[:300]}... "
        f"CTO: {cto_agents[:300]}... CRO: {cro_agents[:300]}... Trader: {trading_agents[:300]}...\n\n"
        "Please synthesize this discussion and explain to the reader:\n"
        "1. The full organizational structure of a major bank — draw a conceptual org chart in markdown\n"
        "2. Which roles are most critical and why\n"
        "3. How these different functions interact and depend on each other\n"
        "4. A [DEEP DIVE] on the concept of 'front office, middle office, back office' — "
        "the three-layer structure that most large banks use\n"
        "5. Your recommendation for the next 5 agents to add to complete the team"
    )

    # ─── PART 8: THE TRADING DESK AND RISK CROSS-EXAMINATION ─────────────────
    boardroom._render_section_header("PART VIII: LIVE SCENARIO — MARKET STRESS")

    # Present a market stress scenario
    stress_scenario = """
    MARKET ALERT — 09:47 EST:
    - S&P 500 down 4.2% in 47 minutes (fastest drop since March 2020)
    - VIX spiked from 18 to 38 (volatility doubled)
    - US 10-year Treasury yield dropped 25bps (flight to safety)
    - Oil down 8% on geopolitical headlines
    - EUR/USD down 1.3% (risk-off USD strength)
    - Credit spreads (IG CDX) widened 45bps
    """

    boardroom._render_section_header("⚠️  MARKET STRESS EVENT")
    console.print(stress_scenario)

    desk_stress = boardroom.call_agent(
        "Trading Desk",
        f"""MARKET ALERT:\n{stress_scenario}\n
        You're at your screens. What is happening to our books RIGHT NOW?
        Walk through each major book: what's the P&L impact, what Greeks are
        moving most dangerously, what hedges are you executing immediately?
        Be specific — instruments, sizes, urgency.""",
        max_tokens=1800,
    )

    cro_stress = boardroom.call_agent(
        "CRO",
        f"""The Trading Desk is reporting:\n{desk_stress[:500]}\n
        From risk management: what are your immediate actions?
        Are any limits being breached? What stress scenarios are you running?
        Do you need to restrict trading in any books?
        And what's your communication to the CEO and Board?""",
        max_tokens=1500,
    )

    ceo_stress = boardroom.call_agent(
        "CEO",
        f"""Desk reports: {desk_stress[:300]}\nCRO reports: {cro_stress[:300]}\n
        As CEO, how do you respond? What decisions are yours to make?
        What do you communicate to the Board? To regulators? To clients?
        And what does this scenario reveal about our AI-native infrastructure needs?""",
        max_tokens=1400,
    )

    boardroom.narrate(
        f"The team just managed a simulated market stress event.\n"
        f"Desk: {desk_stress[:400]}...\nCRO: {cro_stress[:400]}...\nCEO: {ceo_stress[:400]}...\n\n"
        "Please provide:\n"
        "1. A [HISTORICAL CONTEXT] — describe what actually happened on March 16, 2020 "
        "(COVID crash) or September 15, 2008 (Lehman collapse) in a trading room\n"
        "2. A [DEEP DIVE] on how banks manage a real crisis: the 'war room,' the communication "
        "chain, the regulatory notifications, the hedging cascade\n"
        "3. A [TENSION WATCH] on the trading desk vs. risk management during a crisis — "
        "this is when their relationship is tested most severely\n"
        "4. What this scenario reveals about why real-time AI infrastructure matters"
    )

    # ─── PART 9: CLOSING SYNTHESIS ───────────────────────────────────────────
    boardroom._render_section_header("PART IX: CLOSING — THE COMPLETE PICTURE")

    ceo_close = boardroom.call_agent(
        "CEO",
        """Close this session with your synthesis.
        What have we decided about the architecture of Apex Global Bank?
        What's the roadmap for the next 12 months?
        What agent team do we need, and what will each contribute?
        And what's the single most important thing we got right in this discussion?""",
        max_tokens=1800,
    )

    # Final observer narration — the big picture for the reader
    boardroom.narrate(
        f"The CEO closed with: {ceo_close[:400]}...\n\n"
        "Please write a comprehensive closing narration for the reader. This should:\n"
        "1. Summarize what we learned about how a global bank works\n"
        "2. Explain the full agent team that's been assembled and what role each plays\n"
        "3. Highlight the 3 most important tensions in banking that came up today\n"
        "4. Give the reader a 'mental model' — a clear framework for understanding banking\n"
        "5. Suggest what to explore next: the concepts, books, and further reading "
        "that would deepen this understanding\n"
        "6. End with your honest assessment: what does it really take to run a bank "
        "at this scale, and why is it one of the most complex human enterprises ever built?",
        max_tokens=2000,
    )

    # Close and export
    boardroom.close_session()
    boardroom.export_transcript(export_path)


if __name__ == "__main__":
    run_founding_meeting()
