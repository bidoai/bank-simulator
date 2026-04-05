"""
Variation Margin Engine.

Calculates daily VM calls for each CSA based on the net MTM movement
of the positions in that netting set. Tracks call lifecycle and
applies counterparty behaviour (normal / dispute / late / default).
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Optional
import structlog

from infrastructure.collateral.csa import (
    CSA,
    CollateralAccount,
    MarginCall,
    MarginCallDirection,
    MarginCallStatus,
    CollateralAssetType,
)

log = structlog.get_logger()


def _business_days_ahead(from_date: date, n: int) -> date:
    d = from_date
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:   # Mon-Fri
            added += 1
    return d


# ── Seeded CSA catalogue (Apex Global Bank bilateral relationships) ────────

def _build_default_csas() -> list[CSA]:
    """
    Representative set of bilateral CSA relationships for Apex Global Bank.
    Drawn from the CounterpartyRegistry counterparty IDs.
    """
    return [
        CSA(
            csa_id="CSA-GS-001",
            counterparty_id="CP001",
            counterparty_name="Goldman Sachs International",
            our_legal_entity="Apex Global Bank N.A.",
            governing_law="New York",
            threshold_usd=0.0,
            mta_usd=500_000,
            independent_amount_usd=120_000_000,   # UMR Phase 6 IM
            mpor_days=10,
            eligible_collateral=[CollateralAssetType.USD_CASH, CollateralAssetType.UST],
            rehypothecation_allowed=True,
        ),
        CSA(
            csa_id="CSA-JPM-001",
            counterparty_id="CP002",
            counterparty_name="JPMorgan Chase Bank",
            our_legal_entity="Apex Global Bank N.A.",
            governing_law="New York",
            threshold_usd=0.0,
            mta_usd=500_000,
            independent_amount_usd=95_000_000,
            mpor_days=10,
            eligible_collateral=[CollateralAssetType.USD_CASH, CollateralAssetType.UST, CollateralAssetType.AGENCY],
            rehypothecation_allowed=True,
        ),
        CSA(
            csa_id="CSA-DB-001",
            counterparty_id="CP003",
            counterparty_name="Deutsche Bank AG",
            our_legal_entity="Apex Global Bank Ltd (London)",
            governing_law="English",
            threshold_usd=0.0,
            mta_usd=1_000_000,
            independent_amount_usd=75_000_000,
            mpor_days=10,
            eligible_collateral=[CollateralAssetType.USD_CASH, CollateralAssetType.UST, CollateralAssetType.BUND],
            rehypothecation_allowed=True,
        ),
        CSA(
            csa_id="CSA-MER-001",
            counterparty_id="CP004",
            counterparty_name="Meridian Capital Fund LP",
            our_legal_entity="Apex Global Bank N.A.",
            governing_law="New York",
            threshold_usd=10_000_000,     # $10M threshold (legacy CSA)
            mta_usd=1_000_000,
            independent_amount_usd=0.0,   # below UMR threshold
            mpor_days=10,
            eligible_collateral=[CollateralAssetType.USD_CASH, CollateralAssetType.UST, CollateralAssetType.IG_CORP],
            rehypothecation_allowed=False,
        ),
        CSA(
            csa_id="CSA-LCH-001",
            counterparty_id="CP_LCH",
            counterparty_name="LCH Ltd (CCP — Rates)",
            our_legal_entity="Apex Global Bank N.A.",
            governing_law="English",
            threshold_usd=0.0,
            mta_usd=0.0,           # CCPs have no MTA
            independent_amount_usd=850_000_000,  # CCP initial margin
            mpor_days=5,           # 5-day MPoR for cleared
            eligible_collateral=[CollateralAssetType.USD_CASH, CollateralAssetType.UST],
            rehypothecation_allowed=False,
            is_cleared=True,
        ),
    ]


def _build_default_accounts(csas: list[CSA]) -> dict[str, CollateralAccount]:
    """Seed opening collateral balances for each CSA."""
    seed_balances = {
        "CSA-GS-001":  {"vm_posted": 45_000_000,  "vm_received": 82_000_000,
                        "im_posted": 120_000_000,  "im_received": 110_000_000},
        "CSA-JPM-001": {"vm_posted": 120_000_000, "vm_received": 95_000_000,
                        "im_posted": 95_000_000,   "im_received": 88_000_000},
        "CSA-DB-001":  {"vm_posted": 30_000_000,  "vm_received": 55_000_000,
                        "im_posted": 75_000_000,   "im_received": 70_000_000},
        "CSA-MER-001": {"vm_posted": 0.0,          "vm_received": 18_000_000,
                        "im_posted": 0.0,           "im_received": 0.0},
        "CSA-LCH-001": {"vm_posted": 220_000_000,  "vm_received": 0.0,
                        "im_posted": 850_000_000,   "im_received": 0.0},
    }
    accounts = {}
    for csa in csas:
        b = seed_balances.get(csa.csa_id, {})
        accounts[csa.csa_id] = CollateralAccount(
            account_id=f"ACC-{csa.csa_id}",
            csa_id=csa.csa_id,
            counterparty_id=csa.counterparty_id,
            vm_posted_usd=b.get("vm_posted", 0.0),
            vm_received_usd=b.get("vm_received", 0.0),
            im_posted_usd=b.get("im_posted", 0.0),
            im_received_usd=b.get("im_received", 0.0),
        )
    return accounts


class VMEngine:
    """
    Variation Margin calculation and call management engine.

    Tracks daily MTM per CSA and generates outbound / inbound margin calls.
    Applies counterparty behaviour flags for stress scenario simulation.
    """

    COUNTERPARTY_BEHAVIOUR_NORMAL  = "NORMAL"
    COUNTERPARTY_BEHAVIOUR_DISPUTE = "DISPUTE"   # disputes 15% of call amount
    COUNTERPARTY_BEHAVIOUR_LATE    = "LATE"      # delivers T+3 instead of T+1
    COUNTERPARTY_BEHAVIOUR_DEFAULT = "DEFAULT"   # fails to deliver, triggers close-out

    def __init__(self) -> None:
        self._csas: dict[str, CSA] = {}
        self._accounts: dict[str, CollateralAccount] = {}
        self._calls: list[MarginCall] = []
        self._prev_mtm: dict[str, float] = {}   # csa_id → last known net MTM

        # Load defaults
        default_csas = _build_default_csas()
        for csa in default_csas:
            self._csas[csa.csa_id] = csa
        self._accounts = _build_default_accounts(default_csas)

        # Seed opening MTM estimates per CSA (approximate mid-market)
        self._prev_mtm = {
            "CSA-GS-001":  -37_000_000,   # net MTM against us (we owe them)
            "CSA-JPM-001":  24_000_000,   # net MTM in our favour
            "CSA-DB-001":  -12_000_000,
            "CSA-MER-001":  18_000_000,   # in-the-money to us (above threshold)
            "CSA-LCH-001": -220_000_000,  # paying fixed on large IRS book
        }

    # ── CSA management ────────────────────────────────────────────────────

    def register_csa(self, csa: CSA) -> None:
        self._csas[csa.csa_id] = csa
        if csa.csa_id not in self._accounts:
            self._accounts[csa.csa_id] = CollateralAccount(
                account_id=f"ACC-{csa.csa_id}",
                csa_id=csa.csa_id,
                counterparty_id=csa.counterparty_id,
            )

    def get_csa(self, csa_id: str) -> Optional[CSA]:
        return self._csas.get(csa_id)

    def get_all_csas(self) -> list[CSA]:
        return list(self._csas.values())

    def get_account(self, csa_id: str) -> Optional[CollateralAccount]:
        return self._accounts.get(csa_id)

    def get_all_accounts(self) -> list[CollateralAccount]:
        return list(self._accounts.values())

    # ── VM calculation ────────────────────────────────────────────────────

    def calculate_vm_call(
        self,
        csa_id: str,
        current_mtm: float,      # current net MTM of the netting set (our perspective)
        as_of: Optional[date] = None,
    ) -> Optional[MarginCall]:
        """
        Compute a VM call for the given CSA given the current net MTM.

        Returns a MarginCall if the net movement exceeds MTA, else None.
        Positive current_mtm = trades worth more to us → we should be receiving.
        Negative current_mtm = trades worth less to us → we should be posting.
        """
        csa = self._csas.get(csa_id)
        account = self._accounts.get(csa_id)
        if not csa or account is None:
            return None

        today = as_of or date.today()

        # Net required collateral = MTM minus threshold
        # If MTM > threshold: counterparty owes us (inbound call)
        # If MTM < -threshold: we owe counterparty (outbound call)
        # If |MTM| ≤ threshold: within the free band — no collateral required
        if abs(current_mtm) <= csa.threshold_usd:
            return None
        net_required = current_mtm - math.copysign(csa.threshold_usd, current_mtm)

        # Current net VM balance (positive = we hold their collateral)
        current_balance = account.vm_received_usd - account.vm_posted_usd

        delta = net_required - current_balance

        if abs(delta) < csa.mta_usd:
            return None   # below MTA, no call

        direction = (
            MarginCallDirection.INBOUND if delta > 0
            else MarginCallDirection.OUTBOUND
        )

        # Bilateral: T+1; CCP intraday: same-day
        settlement_days = 0 if csa.is_cleared else 1
        due = _business_days_ahead(today, settlement_days)

        call = MarginCall(
            csa_id=csa_id,
            counterparty_id=csa.counterparty_id,
            call_type="VM",
            direction=direction,
            amount_usd=abs(delta),
            status=MarginCallStatus.PENDING,
            asset_type=csa.eligible_collateral[0],
            call_date=today,
            due_date=due,
        )
        self._calls.append(call)
        self._prev_mtm[csa_id] = current_mtm
        account.last_call_date = today
        log.info("vm.call_generated", csa_id=csa_id, direction=direction, amount_usd=round(abs(delta), 0))
        return call

    def apply_behaviour(
        self,
        call: MarginCall,
        behaviour: str,
        as_of: Optional[date] = None,
    ) -> MarginCall:
        """Apply a counterparty behaviour flag to a pending inbound call."""
        today = as_of or date.today()

        if behaviour == self.COUNTERPARTY_BEHAVIOUR_DISPUTE:
            call.status = MarginCallStatus.DISPUTED
            call.disputed_amount = round(call.amount_usd * 0.15, 0)
            call.notes = "Counterparty disputes 15% of call; reference dealer quotations requested."
        elif behaviour == self.COUNTERPARTY_BEHAVIOUR_LATE:
            call.status = MarginCallStatus.LATE
            call.due_date = _business_days_ahead(today, 3)  # T+3 instead of T+1
            call.notes = "Late delivery indicated; extended due date."
        elif behaviour == self.COUNTERPARTY_BEHAVIOUR_DEFAULT:
            call.status = MarginCallStatus.DEFAULTED
            call.is_close_out = True
            call.notes = "Counterparty has failed to deliver. Event of Default notice issued."
            log.warning("vm.counterparty_default", counterparty_id=call.counterparty_id)
        return call

    def settle_call(self, call_id: str, delivered_amount: Optional[float] = None) -> bool:
        for call in self._calls:
            if call.call_id == call_id and call.status != MarginCallStatus.SETTLED:
                amount = delivered_amount or call.undisputed_amount
                call.delivery_date = date.today()
                call.agreed_amount = amount
                call.status = MarginCallStatus.SETTLED
                # Update account balance
                account = self._accounts.get(call.csa_id)
                if account:
                    if call.direction == MarginCallDirection.OUTBOUND:
                        account.vm_posted_usd += amount
                    else:
                        account.vm_received_usd += amount
                    account.last_delivery_date = date.today()
                return True
        return False

    # ── Bulk scenario call generation ─────────────────────────────────────

    def run_daily_margining(
        self,
        mtm_by_csa: dict[str, float],
        counterparty_behaviours: Optional[dict[str, str]] = None,
        as_of: Optional[date] = None,
    ) -> list[MarginCall]:
        """
        Generate all VM calls for a given day's MTM snapshot.

        mtm_by_csa: {csa_id: net_mtm_usd}
        counterparty_behaviours: {counterparty_id: behaviour_flag}
        """
        behaviours = counterparty_behaviours or {}
        calls = []
        for csa_id, mtm in mtm_by_csa.items():
            call = self.calculate_vm_call(csa_id, mtm, as_of=as_of)
            if call:
                csa = self._csas.get(csa_id)
                if csa:
                    beh = behaviours.get(csa.counterparty_id, self.COUNTERPARTY_BEHAVIOUR_NORMAL)
                    if beh != self.COUNTERPARTY_BEHAVIOUR_NORMAL and call.direction == MarginCallDirection.INBOUND:
                        self.apply_behaviour(call, beh, as_of=as_of)
                calls.append(call)
        return calls

    # ── Close-out netting ─────────────────────────────────────────────────

    def compute_close_out(
        self,
        counterparty_id: str,
        current_mtm_by_csa: dict[str, float],
        replacement_cost_premium_pct: float = 0.02,
    ) -> dict:
        """
        Compute the close-out netting result for a defaulted counterparty.

        replacement_cost_premium_pct: estimated market impact / slippage
        when replacing positions in a stressed market (default 2%).
        """
        cp_csas = [c for c in self._csas.values() if c.counterparty_id == counterparty_id]
        if not cp_csas:
            return {"error": f"No CSAs found for counterparty {counterparty_id}"}

        results = []
        total_net_mtm = 0.0
        total_im_held = 0.0
        total_replacement_cost = 0.0
        total_close_out_loss = 0.0

        for csa in cp_csas:
            mtm = current_mtm_by_csa.get(csa.csa_id, 0.0)
            account = self._accounts.get(csa.csa_id)
            im_held = account.im_received_usd if account else 0.0

            # Replacement cost = MTM + slippage premium (if we're owed money)
            if mtm > 0:
                replacement_cost = mtm * (1.0 + replacement_cost_premium_pct)
            else:
                replacement_cost = mtm  # liability — we owe them, no premium

            close_out_loss = max(0.0, replacement_cost - im_held)
            total_net_mtm += mtm
            total_im_held += im_held
            total_replacement_cost += replacement_cost
            total_close_out_loss += close_out_loss

            results.append({
                "csa_id": csa.csa_id,
                "net_mtm_usd": round(mtm, 0),
                "im_held_usd": round(im_held, 0),
                "replacement_cost_usd": round(replacement_cost, 0),
                "close_out_loss_usd": round(close_out_loss, 0),
            })

        return {
            "counterparty_id": counterparty_id,
            "csa_count": len(cp_csas),
            "total_net_mtm_usd": round(total_net_mtm, 0),
            "total_im_held_usd": round(total_im_held, 0),
            "total_replacement_cost_usd": round(total_replacement_cost, 0),
            "total_close_out_loss_usd": round(total_close_out_loss, 0),
            "netting_benefit_usd": 0.0,  # already computed at netting set level
            "csa_detail": results,
        }

    # ── Reporting ─────────────────────────────────────────────────────────

    def get_open_calls(self) -> list[MarginCall]:
        return [c for c in self._calls if c.status in (
            MarginCallStatus.PENDING, MarginCallStatus.DISPUTED, MarginCallStatus.LATE
        )]

    def get_all_calls(self) -> list[MarginCall]:
        return list(self._calls)

    def get_portfolio_summary(self) -> dict:
        total_vm_posted   = sum(a.vm_posted_usd   for a in self._accounts.values())
        total_vm_received = sum(a.vm_received_usd for a in self._accounts.values())
        total_im_posted   = sum(a.im_posted_usd   for a in self._accounts.values())
        total_im_received = sum(a.im_received_usd for a in self._accounts.values())
        open_calls = self.get_open_calls()
        return {
            "csa_count": len(self._csas),
            "total_vm_posted_usd":   round(total_vm_posted, 0),
            "total_vm_received_usd": round(total_vm_received, 0),
            "net_vm_usd":            round(total_vm_received - total_vm_posted, 0),
            "total_im_posted_usd":   round(total_im_posted, 0),
            "total_im_received_usd": round(total_im_received, 0),
            "net_im_usd":            round(total_im_received - total_im_posted, 0),
            "total_collateral_posted_usd":  round(total_vm_posted + total_im_posted, 0),
            "total_collateral_received_usd": round(total_vm_received + total_im_received, 0),
            "open_call_count": len(open_calls),
            "open_call_outbound_usd": round(
                sum(c.amount_usd for c in open_calls if c.direction == MarginCallDirection.OUTBOUND), 0
            ),
            "open_call_inbound_usd": round(
                sum(c.amount_usd for c in open_calls if c.direction == MarginCallDirection.INBOUND), 0
            ),
        }


vm_engine = VMEngine()
