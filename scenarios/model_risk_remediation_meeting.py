"""
Model Risk Remediation Meeting — Stakeholder Response to Audit Findings

Triggered by the Internal Audit / External Regulator combined review of all
14 MDDs and the model registry. This scenario runs the formal stakeholder
response meeting with the Model Risk Committee + General Counsel.

Participants:
  Jordan Pierce       — Head of Internal Audit (findings presenter)
  Dr. Priya Nair      — CRO (chair, owns most Tier 1 models)
  Dr. Rebecca Chen    — Model Risk Officer (governance)
  Dr. Samuel Achebe   — Model Validation Officer (validation backlog)
  Dr. Yuki Tanaka     — Head of Quant Research (model developer)
  Margaret Okonkwo    — General Counsel (ARRC/legal compliance breach)
  James Okafor        — Head of Global Markets Trading (XVA business owner)
"""

from __future__ import annotations
import anthropic
from rich.console import Console

from agents.audit.internal_audit import create_internal_auditor
from agents.executive.cro import create_cro
from agents.risk_desk.model_risk_officer import create_model_risk_officer
from agents.risk_desk.model_validation_officer import create_model_validation_officer
from agents.markets.quant_researcher import create_quant_researcher
from agents.legal.general_counsel import create_general_counsel
from agents.markets.lead_trader import create_lead_trader
from agents.narrator.observer import create_observer
from orchestrator.boardroom import Boardroom

console = Console(width=120)

# ── Condensed audit findings passed to agents as context ──────────────────────
AUDIT_SUMMARY = """
APEX GLOBAL BANK — MODEL RISK COMBINED AUDIT REVIEW (2026-04-03)
Internal Audit + External Regulator Findings Summary

CRITICAL FINDINGS:
  CRIT-001: 833 of 847 registered models have no MDD (98.3% undocumented).
  CRIT-002: APEX-MDL-0011 (FVA), -0012 (MVA), -0013 (ColVA) — Tier 1, production,
            validator "Pending". SR 11-7 violation.
  CRIT-003: APEX-MDL-0014 (PFE/CCR) is in draft with 2 open major findings yet is
            the foundation for all 4 XVA models above it. Model cascade risk
            undocumented.
  CRIT-004: APEX-MDL-0002 (SVaR) stressed period last certified 2024-01 — 15+ months
            stale. Basel 2.5 requires annual re-identification. Direct capital
            adequacy regulatory breach.

PROGRAM-LEVEL GAPS:
  MAJ-001: No Section 7 (Use Authorization) in any MDD — SR 11-7 non-compliance.
  MAJ-002: No compensating controls register for any open finding.
  MAJ-003: No ongoing monitoring section / KRIs in any MDD.
  S-08:    All 13 Tier 1 models share a single validator (Dr. Achebe) — MRO
           concentration risk; independence concern for regulators.

PER-MODEL HIGHLIGHTS:
  VaR (0001):    SqRt-of-time scaling wrong for fixed income — untracked silent error.
  FRTB-SA(0003): "Draft" but described as primary capital model — cannot be binding floor.
  BSM (0004):    T=0.25 hardcoded in production (pricing defect, not limitation).
                 r=4.5% static, not live OIS.
  HW1F (0005):   DV01 = qty × 0.0004 flat hardcode — completely disconnected from
                 the HW1F model documented in the MDD.
  SOFR (0006):   3 client contracts using Term SOFR without ARRC pre-approval.
                 Legal/compliance breach.
  IFRS9 (0007):  MDD describes 50-obligor demo portfolio, not 850-obligor production.
                 No multi-scenario weighting. SPPI test missing.
  AML (0008):    AML-F2 rated Minor in registry but Major in MDD — register inaccurate.
                 No false-negative rate metric tracked.
  CRM (0009):    Registry shows 1 finding; MDD has 3 — register incomplete.
  CVA (0010):    SA-CVA capital charge not documented. Parameter error (30 vs 200 steps).
  FVA/MVA/ColVA: All show 0 open findings in draft status — implausible, signals
                 no actual review conducted.

MISSING DOCUMENTS (selected critical):
  - Model Risk Management Policy (board-approved)
  - Model Validation Charter
  - DFAST / Stress Testing MDD
  - Collateral / SIMM MDD
  - ALM / FTP MDD
  - Independent Validation Reports (separate from MDDs)
  - Annual Model Performance Reports
  - Compensating Controls Register

ESTIMATED REGULATORY EXPOSURE:
  If examined today: 2 MRAs, 3-4 MATs, targeted review of 833 uninventoried models.
"""


def run_model_risk_remediation_meeting(
    export_path: str = "transcript_model_risk_remediation.md",
) -> None:
    client = anthropic.Anthropic()

    audit        = create_internal_auditor(client)
    cro          = create_cro(client)
    mro          = create_model_risk_officer(client)
    mvo          = create_model_validation_officer(client)
    quant        = create_quant_researcher(client)
    counsel      = create_general_counsel(client)
    trader       = create_lead_trader(client)
    observer     = create_observer(client)

    boardroom = Boardroom(
        agents={
            "Audit":   audit,
            "CRO":     cro,
            "MRO":     mro,
            "MVO":     mvo,
            "Quant":   quant,
            "Counsel": counsel,
            "Trader":  trader,
        },
        observer=observer,
        session_name="Model Risk Remediation — Stakeholder Review",
    )

    boardroom.open_session()

    # ── PART I: AUDIT PRESENTS ────────────────────────────────────────────────
    boardroom._render_section_header("PART I: AUDIT FINDINGS PRESENTATION")

    audit_open = boardroom.call_agent(
        "Audit",
        f"""You have just completed a combined Internal Audit and external regulator
        model risk review of Apex Global Bank's model documentation suite. Here are
        the findings:

        {AUDIT_SUMMARY}

        Open this Model Risk Committee meeting by presenting the top findings to the
        assembled stakeholders. Be direct and specific. Do not soften Critical findings.
        Clarify which findings require immediate escalation to the Audit Committee.
        Identify the two or three items that — if not addressed before the next
        regulatory examination — create the greatest institutional risk.""",
        max_tokens=1800,
        show_prompt=False,
    )

    # ── PART II: CRO IMMEDIATE RESPONSE ──────────────────────────────────────
    boardroom._render_section_header("PART II: CRO IMMEDIATE RESPONSE")

    cro_response = boardroom.call_agent(
        "CRO",
        f"""Jordan Pierce (Head of Internal Audit) has just presented these findings
        to the Model Risk Committee:

        {audit_open}

        You are the CRO and you own most of these models. Respond directly:
        1. Which findings do you accept as presented, and which do you dispute?
        2. Which items do you own personally and must answer for?
        3. What is your immediate commitment to the Audit Committee?
        4. Are there any findings that surprise you, or were these all known risks?
        Be candid — the regulators have likely already seen these.""",
        max_tokens=1600,
    )

    # ── PART III: MRO ON GOVERNANCE FRAMEWORK GAPS ───────────────────────────
    boardroom._render_section_header("PART III: MODEL RISK OFFICER — GOVERNANCE GAPS")

    mro_response = boardroom.call_agent(
        "MRO",
        f"""The CRO has responded to the audit findings:

        {cro_response[:600]}

        You are Dr. Rebecca Chen, Model Risk Officer. You are responsible for the
        SR 11-7 governance framework. The audit found:
        - No Use Authorization section in any MDD
        - No Compensating Controls Register
        - No Monitoring KRIs in any MDD
        - No Model Risk Management Policy (board-approved)
        - No Validation Charter
        - FVA, MVA, ColVA in production without assigned validators

        Address these governance gaps specifically:
        1. Which of these gaps did your office know about and why were they not closed?
        2. What policy and charter documents can be drafted and approved within 60 days?
        3. How do you address the validator concentration risk — you and Dr. Achebe are
           a two-person function validating 14 Tier 1 models plus 833 others?
        4. What is the MRO's remediation commitment?""",
        max_tokens=1600,
    )

    # ── PART IV: MVO ON VALIDATION BACKLOG ───────────────────────────────────
    boardroom._render_section_header("PART IV: MODEL VALIDATION OFFICER — BACKLOG & FINDINGS")

    mvo_response = boardroom.call_agent(
        "MVO",
        f"""The Model Risk Officer has addressed the governance gaps:

        {mro_response[:500]}

        You are Dr. Samuel Achebe, Model Validation Officer. You are the sole validator
        for 13 of the 14 documented Tier 1 models. The audit found:
        - SVaR stressed period stale by 15+ months (CRIT-004)
        - Registry finding counts don't match MDD finding counts (CRM, AML)
        - FVA/MVA/ColVA showing 0 findings in draft — implying no real review occurred
        - CVA contains a factual parameter error (30 vs 200 steps) in a document you reviewed
        - FRTB-SA benchmarked against ISDA SIMM — wrong benchmark (conceptual flaw)

        Respond specifically:
        1. For the SVaR stale period — what process failed and when can it be re-certified?
        2. For the registry vs. MDD discrepancies — is your tracking system reliable?
        3. For FVA/MVA/ColVA with 0 findings — were these actually reviewed or placeholder?
        4. How do you propose to prioritize the validation backlog given your capacity?
        5. Do you need additional validators, and what is your ask of the MRO?""",
        max_tokens=1600,
    )

    # ── PART V: QUANT RESEARCHER ON TECHNICAL FIXES ──────────────────────────
    boardroom._render_section_header("PART V: QUANT RESEARCHER — TECHNICAL REMEDIATION")

    quant_response = boardroom.call_agent(
        "Quant",
        f"""The Model Validation Officer has spoken:

        {mvo_response[:500]}

        You are Dr. Yuki Tanaka, Head of Quantitative Research. You built or own most
        of the models under review. The audit identified these technical defects in YOUR
        models:
        - BSM: T=0.25 hardcoded (production defect), r=4.5% static (not live OIS)
        - HW1F: DV01 = quantity × 0.0004 flat constant — completely detached from
          the HW1F model in the MDD. The MDD misrepresents what's actually running.
        - SOFR LMM: vol calibration still using pre-LIBOR proxy surface (2 years overdue)
        - IFRS9: MDD documents demo portfolio (50 obligors), not production (850)
        - CVA: parameter error in submitted document (30 steps stated, actual 200)
        - CRM: correlation matrices not updated past 2023 (2022 rate shock not incorporated)
        - FRTB-SA: curvature not validated against independent vendor benchmark

        Be direct:
        1. Which of these can be fixed in code within 30 days, and which require model rebuilds?
        2. For HW1F — the MDD says one thing and the code does another. How did this happen?
        3. What is the realistic timeline for BSM dynamic inputs (T from trade date, r from OIS)?
        4. Commit to a specific remediation plan for your models.""",
        max_tokens=1600,
    )

    # ── PART VI: GENERAL COUNSEL ON ARRC BREACH ──────────────────────────────
    boardroom._render_section_header("PART VI: GENERAL COUNSEL — ARRC / LEGAL COMPLIANCE")

    counsel_response = boardroom.call_agent(
        "Counsel",
        f"""The Quant Researcher has responded to the technical findings:

        {quant_response[:400]}

        You are Margaret Okonkwo, General Counsel. The audit has identified a legal
        compliance issue that goes beyond model risk:

        SOFR LMM finding LMM-F2: Three existing client contracts are using Term SOFR
        without ARRC pre-approval. ARRC guidelines explicitly restrict Term SOFR use
        to loan products and interdealer hedges of loans. Use in other financial
        contracts is prohibited without documented ARRC authorization. This has been
        sitting as an open "model finding" rather than being escalated to Legal.

        Address this:
        1. This is a regulatory compliance breach, not a model limitation. What is your
           immediate response?
        2. Should these contracts be re-papered? What is the client relationship exposure?
        3. Was Legal ever informed of this? If not, what failed in the escalation process?
        4. Is there potential regulatory self-reporting obligation to the CFTC or ARRC?
        5. What governance change prevents a model finding from sitting 6+ months without
           Legal review when it has legal/regulatory exposure?""",
        max_tokens=1500,
    )

    # ── PART VII: TRADER ON BUSINESS IMPACT ──────────────────────────────────
    boardroom._render_section_header("PART VII: HEAD OF TRADING — BUSINESS IMPACT ASSESSMENT")

    trader_response = boardroom.call_agent(
        "Trader",
        f"""General Counsel has raised concerns about contract re-papering and ARRC exposure:

        {counsel_response[:400]}

        You are James Okafor, Head of Global Markets Trading and business owner for the
        entire XVA suite (CVA, FVA, MVA, ColVA, PFE). The audit found:
        - PFE (foundation model) is in draft with open major findings
        - FVA/MVA/ColVA have no assigned validators and show 0 findings
        - These models directly feed trade pricing and P&L reporting

        You need to address:
        1. Are you currently pricing client trades using PFE/CVA/FVA models that are
           in draft with open findings? If yes, what is the materiality?
        2. The FRTB-SA is in draft but is the primary capital model — what is the
           capital impact risk if regulators require a capital add-on during the gap?
        3. What is your tolerance for model remediations that may temporarily widen
           bid-ask spreads or cause P&L marks to move?
        4. What resources (budget, headcount) are you prepared to commit to fix this?""",
        max_tokens=1400,
    )

    # ── PART VIII: ROUND TABLE — REMEDIATION PLAN ────────────────────────────
    boardroom._render_section_header("PART VIII: REMEDIATION PLAN — ROUND TABLE")

    boardroom.narrate(
        f"""The meeting has now heard from all six stakeholders. Audit presented critical findings.
        CRO: {cro_response[:200]}...
        MRO: {mro_response[:200]}...
        MVO: {mvo_response[:200]}...
        Quant: {quant_response[:200]}...
        Counsel: {counsel_response[:200]}...
        Trader: {trader_response[:200]}...

        We are now at the synthesis phase. Please narrate what a model risk remediation
        plan at a real bank looks like — who owns it, how it gets tracked, what the
        regulatory engagement strategy is, and what happens if the bank is examined
        before remediation is complete. This is the moment that decides whether the
        bank gets ahead of the regulators or gets caught."""
    )

    # CRO synthesizes the plan
    remediation_plan = boardroom.call_agent(
        "CRO",
        f"""You have heard from all stakeholders. Now synthesize the remediation plan.

        Produce a structured plan with the following format:

        IMMEDIATE (0-30 days):
        - Item, Owner, Deadline, Success Criterion

        SHORT-TERM (31-90 days):
        - Item, Owner, Deadline, Success Criterion

        MEDIUM-TERM (91-180 days):
        - Item, Owner, Deadline, Success Criterion

        REGULATORY ENGAGEMENT:
        - What to proactively disclose vs. wait for examination
        - Who communicates with the Fed/OCC and when

        GOVERNANCE CHANGES:
        - Policy, process, and structural changes to prevent recurrence

        Use the discussion from this meeting. Be specific about owners (name the person,
        not just the title). Acknowledge the SVaR capital breach explicitly in the plan.
        This document will be presented to the Audit Committee.""",
        max_tokens=2400,
    )

    # Audit accepts or challenges
    boardroom._render_section_header("PART IX: AUDIT COMMITTEE RESPONSE")

    boardroom.call_agent(
        "Audit",
        f"""The CRO has presented the following remediation plan to the Audit Committee:

        {remediation_plan}

        You represent the Audit Committee's interests. Respond:
        1. Which commitments are specific enough to track and hold management accountable?
        2. Which are vague or likely to slip — where do you see the management follow-through risk?
        3. The SVaR capital breach: do you agree this can be handled internally or does
           it require proactive regulatory disclosure now?
        4. What conditions do you set before you are prepared to downgrade this from a
           Critical finding to a High finding?
        5. What is your reporting cadence to the Audit Committee on progress?""",
        max_tokens=1500,
    )

    # MRO commits to governance framework delivery
    boardroom.call_agent(
        "MRO",
        f"""Based on the remediation plan and audit response, you need to make a specific,
        binding commitment on governance deliverables. The regulators will ask for:
        1. Model Risk Management Policy — board approved
        2. Model Validation Charter
        3. Use Authorization section added to all 14 MDDs
        4. Compensating Controls Register
        5. Three new MDDs: DFAST, SIMM/Collateral, ALM/FTP

        For each item: confirm your delivery date, who on your team owns drafting,
        and who approves. Be realistic — do not commit to timelines you cannot meet.
        The Audit Committee will track these as open findings.""",
        max_tokens=1200,
    )

    # Final narration
    boardroom._render_section_header("CLOSING NARRATION")

    boardroom.narrate(
        f"""This meeting has produced a remediation plan. The CRO committed to specific
        actions. The MRO committed to governance deliverables. Legal is investigating
        the ARRC contracts. The MVO has acknowledged the validation backlog.

        Please provide a closing narration for the reader:
        1. What does this kind of model risk failure look like at a real bank — is this
           typical, worse than average, or better?
        2. What are the warning signs that a bank's model risk culture is deteriorating?
        3. What does 'good' model risk management look like at JPMorgan or Goldman Sachs?
        4. If the OCC walked in tomorrow with this exact set of findings, what is the
           likely supervisory outcome — MRA, consent order, capital add-on?
        This is educational context for the reader."""
    )

    # ── Close and export ──────────────────────────────────────────────────────
    boardroom.close_session()
    path = boardroom.export_transcript(export_path)
    console.print(f"\n[green]Transcript saved → {path}[/green]")


if __name__ == "__main__":
    run_model_risk_remediation_meeting()
