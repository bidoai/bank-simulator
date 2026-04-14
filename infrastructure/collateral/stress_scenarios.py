"""
Collateral Stress Scenarios.

Three named scenarios designed to exercise the collateral simulation engine:

1. COVID Week — systemic margin call shock (vol doubles, $8.5B gross calls)
2. Lehman Event — single counterparty default with close-out netting
3. Gilt Crisis — collateral quality shock (gov bond prices fall 12%)

Each scenario produces structured output with per-agent decision points,
suitable for boardroom simulation injection via the ScenarioEngine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional
import structlog

from infrastructure.collateral.vm_engine import VMEngine, vm_engine
from infrastructure.collateral.csa import MarginCallStatus

log = structlog.get_logger(__name__)


@dataclass
class AgentDecisionPoint:
    agent: str
    decision_required: str
    context: str
    options: list[str]


@dataclass
class ScenarioResult:
    scenario_name: str
    description: str
    total_outbound_calls_usd: float
    total_inbound_calls_usd: float
    net_liquidity_demand_usd: float
    disputed_calls: int
    late_calls: int
    defaulted_counterparties: list[str]
    close_out_losses_usd: float
    collateral_quality_adjustment_usd: float  # additional calls from haircut changes
    agent_decision_points: list[AgentDecisionPoint]
    call_detail: list[dict]
    risk_flags: list[str]

    def to_dict(self) -> dict:
        return {
            "scenario_name": self.scenario_name,
            "description": self.description,
            "total_outbound_calls_usd": self.total_outbound_calls_usd,
            "total_inbound_calls_usd": self.total_inbound_calls_usd,
            "net_liquidity_demand_usd": self.net_liquidity_demand_usd,
            "disputed_calls": self.disputed_calls,
            "late_calls": self.late_calls,
            "defaulted_counterparties": self.defaulted_counterparties,
            "close_out_losses_usd": self.close_out_losses_usd,
            "collateral_quality_adjustment_usd": self.collateral_quality_adjustment_usd,
            "call_detail": self.call_detail,
            "risk_flags": self.risk_flags,
            "agent_decision_points": [
                {
                    "agent": dp.agent,
                    "decision_required": dp.decision_required,
                    "context": dp.context,
                    "options": dp.options,
                }
                for dp in self.agent_decision_points
            ],
        }


class CollateralStressScenarios:
    """
    Factory for the three named collateral stress scenarios.
    """

    def __init__(self, engine: Optional[VMEngine] = None) -> None:
        self._engine = engine or vm_engine

    # ── Scenario 1: COVID Week ─────────────────────────────────────────────

    def run_covid_week(self, as_of: Optional[date] = None) -> ScenarioResult:
        """
        Systemic margin call shock.

        Assumptions:
          - Equity indices -15% in 48 hours
          - Credit spreads +300bps
          - Implied vol ×2
          - MTM shocks applied per CSA based on position sensitivities
        """
        today = as_of or date.today()

        # Apply MTM shocks: each CSA moves by the sensitivity of its position book
        shocked_mtm = {
            "CSA-GS-001":  -185_000_000,  # large rates payer book losses under vol spike
            "CSA-JPM-001":  -68_000_000,
            "CSA-DB-001":   -95_000_000,
            "CSA-MER-001":  -42_000_000,  # hedge fund: long equities, now deeply ITM for them
            "CSA-LCH-001": -820_000_000,  # cleared IRS book: large MTM swing
        }

        # Counterparty behaviours: 70% normal, 20% late, 10% dispute
        behaviours = {
            "CP001": VMEngine.COUNTERPARTY_BEHAVIOUR_NORMAL,
            "CP002": VMEngine.COUNTERPARTY_BEHAVIOUR_LATE,
            "CP003": VMEngine.COUNTERPARTY_BEHAVIOUR_LATE,
            "CP004": VMEngine.COUNTERPARTY_BEHAVIOUR_DISPUTE,
            "CP_LCH": VMEngine.COUNTERPARTY_BEHAVIOUR_NORMAL,  # CCP always performs
        }

        calls = self._engine.run_daily_margining(shocked_mtm, behaviours, as_of=today)

        outbound = sum(c.amount_usd for c in calls
                       if c.direction == "OUTBOUND")
        inbound  = sum(c.amount_usd for c in calls
                       if c.direction == "INBOUND")
        net_demand = outbound - inbound  # net cash out
        disputed = sum(1 for c in calls if c.status == MarginCallStatus.DISPUTED)
        late     = sum(1 for c in calls if c.status == MarginCallStatus.LATE)

        # Transformation capacity: max $5B/day, cost = OIS + 50bps spread
        transformation_needed = max(0.0, net_demand - 800_000_000)  # $800M unencumbered cash
        transformation_cost   = transformation_needed * 0.0050      # 50bps cost

        risk_flags = [
            "LIQUIDITY_STRESS: Net outbound demand exceeds unencumbered cash",
            "COLLATERAL_TRANSFORMATION: Repo desk activation required",
            f"CCP_INTRADAY: LCH intraday call T+0 — same-day settlement required",
            "DISPUTE_SIGNAL: Meridian Capital disputing calls — monitor for default",
        ] if net_demand > 0 else []

        decision_points = [
            AgentDecisionPoint(
                agent="CEO",
                decision_required="Activate emergency repo facility?",
                context=f"Net liquidity demand: ${net_demand/1e9:.1f}B. "
                        f"Unencumbered cash: $0.8B. Transformation gap: ${transformation_needed/1e9:.1f}B.",
                options=["Activate Fed repo facility ($5B)", "Sell liquid assets", "Defer non-critical VM"],
            ),
            AgentDecisionPoint(
                agent="CRO",
                decision_required="Escalate Meridian Capital to watch list?",
                context="Meridian is disputing their VM call (15%). Pattern consistent with early-stage liquidity stress.",
                options=["Add to watch list + daily monitoring", "Request additional IM immediately", "No action"],
            ),
            AgentDecisionPoint(
                agent="Treasury",
                decision_required="Prioritise which margin calls to settle first?",
                context=f"Total outbound: ${outbound/1e9:.1f}B. CCP intraday call is T+0. "
                        f"Bilateral calls are T+1. Transformation capacity: $5B.",
                options=["CCP first (systemic risk)", "Largest counterparties first", "Cheapest-to-deliver optimisation"],
            ),
            AgentDecisionPoint(
                agent="Trader",
                decision_required="Reduce positions to free up collateral?",
                context="FVA on current book has doubled due to vol spike. Some positions now uneconomic.",
                options=["Reduce by 20% across all books", "Target highest-FVA positions only", "Hold — temporary dislocation"],
            ),
        ]

        return ScenarioResult(
            scenario_name="COVID Week — Systemic Margin Call",
            description=(
                "Global equity markets fall 15% in 48 hours. Credit spreads widen 300bps. "
                "Implied volatility doubles. All derivative books take simultaneous MTM losses. "
                "Net collateral outflow: ~$8.5B over 3 days."
            ),
            total_outbound_calls_usd=round(outbound, 0),
            total_inbound_calls_usd=round(inbound, 0),
            net_liquidity_demand_usd=round(net_demand, 0),
            disputed_calls=disputed,
            late_calls=late,
            defaulted_counterparties=[],
            close_out_losses_usd=0.0,
            collateral_quality_adjustment_usd=0.0,
            agent_decision_points=decision_points,
            call_detail=[c.to_dict() for c in calls],
            risk_flags=risk_flags,
        )

    # ── Scenario 2: Lehman Event ───────────────────────────────────────────

    def run_lehman_event(self, defaulting_counterparty_id: str = "CP004",
                         as_of: Optional[date] = None) -> ScenarioResult:
        """
        Single named counterparty default with close-out netting.

        Default: Meridian Capital Fund LP (CP004) fails to deliver
        morning VM. ISDA Event of Default declared by end of day.
        """
        today = as_of or date.today()

        # Pre-default MTM snapshot
        pre_default_mtm = {"CSA-MER-001": 18_000_000}  # $18M in-the-money to us

        # Generate the VM call that goes undelivered
        calls = self._engine.run_daily_margining(
            pre_default_mtm,
            {defaulting_counterparty_id: VMEngine.COUNTERPARTY_BEHAVIOUR_DEFAULT},
            as_of=today,
        )

        # Execute close-out netting
        # In close-out, slippage is higher (stressed market, forced replacement)
        close_out = self._engine.compute_close_out(
            counterparty_id=defaulting_counterparty_id,
            current_mtm_by_csa=pre_default_mtm,
            replacement_cost_premium_pct=0.025,  # 2.5% slippage in stressed close-out
        )

        close_out_loss = close_out.get("total_close_out_loss_usd", 0.0)
        total_exposure = close_out.get("total_net_mtm_usd", 0.0)

        risk_flags = [
            f"COUNTERPARTY_DEFAULT: {defaulting_counterparty_id} — Event of Default declared",
            "CLOSE_OUT_INITIATED: 800 trades across 1 CSA — 7-day close-out timeline",
            "RWA_JUMP: Collateralised exposure becomes uncollateralised at close-out",
            "IFRS9_STAGE3: Obligor moves to Stage 3 ECL — full LGD×EAD provision required",
        ]

        decision_points = [
            AgentDecisionPoint(
                agent="CEO",
                decision_required="Public disclosure obligation?",
                context=f"Meridian default. Net MTM: ${total_exposure/1e6:.0f}M. "
                        f"Close-out loss estimate: ${close_out_loss/1e6:.0f}M. "
                        "Materiality threshold: $10M.",
                options=["Disclose to regulators (immediate)", "Internal only pending close-out", "Legal advice first"],
            ),
            AgentDecisionPoint(
                agent="CRO",
                decision_required="Activate CCR breach protocol?",
                context=f"Expected close-out loss ${close_out_loss/1e6:.0f}M vs. CCR limit. "
                        "IM held: $0 (Meridian was below UMR threshold). Unsecured claim on estate.",
                options=["Activate breach protocol + board notification", "Monitor — within single-name limit", "Increase reserves immediately"],
            ),
            AgentDecisionPoint(
                agent="Treasury",
                decision_required="Execute close-out trades — timing?",
                context="800 IRS trades need replacement. Market knows we are a forced buyer. "
                        "Each day we wait: more slippage. Each day we rush: more market impact.",
                options=["Execute ASAP (minimise exposure duration)", "Pace over 7 days (minimise market impact)", "Hedge with futures immediately, replace swaps over 2 weeks"],
            ),
            AgentDecisionPoint(
                agent="GC",
                decision_required="File claim in Meridian insolvency?",
                context="Meridian is registered in Delaware. ISDA netting should be enforceable. "
                        "Net claim: outstanding close-out amount after IM offset.",
                options=["File immediately (preserve priority)", "Negotiate direct settlement", "Wait for administrator appointment"],
            ),
        ]

        return ScenarioResult(
            scenario_name="Lehman Event — Single Counterparty Default",
            description=(
                f"Meridian Capital Fund LP ({defaulting_counterparty_id}) fails to deliver "
                "morning VM call. ISDA Event of Default declared at 3pm. "
                "Close-out netting of all positions initiated. 7-day replacement timeline."
            ),
            total_outbound_calls_usd=0.0,
            total_inbound_calls_usd=sum(c.amount_usd for c in calls),
            net_liquidity_demand_usd=0.0,
            disputed_calls=0,
            late_calls=0,
            defaulted_counterparties=[defaulting_counterparty_id],
            close_out_losses_usd=round(close_out_loss, 0),
            collateral_quality_adjustment_usd=0.0,
            agent_decision_points=decision_points,
            call_detail=[c.to_dict() for c in calls] + [close_out],
            risk_flags=risk_flags,
        )

    # ── Scenario 3: Gilt Crisis ────────────────────────────────────────────

    def run_gilt_crisis(self, bond_price_shock_pct: float = -0.12,
                        as_of: Optional[date] = None) -> ScenarioResult:
        """
        Collateral quality shock.

        Government bonds (UST / Gilt) fall 12% in price over 5 days
        due to a sovereign debt / inflation crisis. This does NOT affect
        trade MTM directly — it affects the *value of posted collateral*,
        triggering secondary margin calls to make up the shortfall.
        """
        today = as_of or date.today()

        # Standard haircuts (pre-shock) and new haircuts post-shock
        pre_shock_haircut_ust  = 0.020   # 2%
        post_shock_haircut_ust = 0.060   # rises to 6% as bond vol spikes

        # Calculate additional collateral calls due to collateral devaluation
        # For each CSA where UST is posted:
        # Additional call = posted_ust × abs(price_shock) + posted_ust × (new_haircut - old_haircut)
        additional_calls = {}
        total_quality_adjustment = 0.0

        for account in self._engine.get_all_accounts():
            if account.vm_posted_usd > 0:
                # Approximate: 60% of posted collateral is UST
                posted_ust = account.vm_posted_usd * 0.60
                price_loss = posted_ust * abs(bond_price_shock_pct)
                haircut_increase = posted_ust * (post_shock_haircut_ust - pre_shock_haircut_ust)
                additional = price_loss + haircut_increase
                if additional > 0:
                    additional_calls[account.csa_id] = additional
                    total_quality_adjustment += additional

        risk_flags = [
            f"COLLATERAL_QUALITY_SHOCK: UST prices down {abs(bond_price_shock_pct)*100:.0f}% — haircuts revised",
            "SECONDARY_VM_CALLS: $" + f"{total_quality_adjustment/1e9:.1f}B additional calls from collateral devaluation",
            "TRANSFORMATION_STRESS: Gilt repo spread widened 50bps — transformation cost elevated",
            "CONCENTRATION_RISK: 60%+ of posted collateral in government bonds — concentrated exposure",
            "LCR_IMPACT: HQLA quality deteriorating — potential LCR breach if quality shock persists",
        ]

        decision_points = [
            AgentDecisionPoint(
                agent="Treasury",
                decision_required="Substitute posted UST collateral before further devaluation?",
                context=f"UST collateral down {abs(bond_price_shock_pct)*100:.0f}%. "
                        f"Additional calls: ${total_quality_adjustment/1e9:.1f}B. "
                        "Substitution to USD cash would eliminate reinvestment risk.",
                options=["Substitute UST for USD cash immediately", "Accept additional calls (hold UST)", "Partial substitution on largest CSAs only"],
            ),
            AgentDecisionPoint(
                agent="CRO",
                decision_required="Increase IM haircut requirements for received UST?",
                context="We receive UST as IM from counterparties. If their posted UST falls 12%, "
                        "our credit protection is reduced. Haircut reset clause may be triggered.",
                options=["Invoke haircut reset — call additional IM", "Absorb haircut difference — preserve relationship", "Model-driven: only call if net coverage falls below 105%"],
            ),
            AgentDecisionPoint(
                agent="CFO",
                decision_required="LCR impact assessment required — board disclosure?",
                context="HQLA quality is deteriorating. If UST prices fall further, "
                        "our Level 1 HQLA buffer shrinks. LCR headroom: currently 35%. "
                        "At -20% UST, LCR approaches minimum.",
                options=["File 5-day liquidity risk event report", "Internal monitoring only", "Pre-position — buy shorter-duration HQLA"],
            ),
            AgentDecisionPoint(
                agent="CEO",
                decision_required="Accelerate collateral diversification policy?",
                context="This crisis has exposed 60% concentration in UST as posted collateral. "
                        "Policy change: cap any single collateral type at 40%.",
                options=["Implement immediately — operational disruption accepted", "Implement over 90 days", "Refer to Risk Committee — no unilateral change"],
            ),
        ]

        return ScenarioResult(
            scenario_name="Gilt Crisis — Collateral Quality Shock",
            description=(
                f"Government bond prices fall {abs(bond_price_shock_pct)*100:.0f}% over 5 days. "
                "Collateral haircuts revised upward. Secondary VM calls generated by collateral "
                "devaluation — independent of trade MTM movements."
            ),
            total_outbound_calls_usd=round(total_quality_adjustment, 0),
            total_inbound_calls_usd=round(total_quality_adjustment, 0),  # bilateral — both sides affected
            net_liquidity_demand_usd=round(total_quality_adjustment, 0),
            disputed_calls=0,
            late_calls=0,
            defaulted_counterparties=[],
            close_out_losses_usd=0.0,
            collateral_quality_adjustment_usd=round(total_quality_adjustment, 0),
            agent_decision_points=decision_points,
            call_detail=[{"csa_id": k, "additional_call_usd": round(v, 0)} for k, v in additional_calls.items()],
            risk_flags=risk_flags,
        )

