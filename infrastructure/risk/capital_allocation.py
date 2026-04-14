"""
Capital Allocation Framework — Top-down CET1 allocation to business lines and trading desks.

The CFO allocates the firm's $45B CET1 capital budget top-down:

  Firm CET1 ($45B)
  ├── MARKETS           30%  → $13.5B CET1  → $300B RWA budget
  │   ├── EQUITY        30%  → $4.05B CET1  → $90B  RWA budget
  │   ├── RATES         35%  → $4.725B CET1 → $105B RWA budget
  │   ├── FX            10%  → $1.35B CET1  → $30B  RWA budget
  │   ├── CREDIT        15%  → $2.025B CET1 → $45B  RWA budget
  │   ├── DERIVATIVES   7%   → $0.945B CET1 → $21B  RWA budget
  │   └── COMMODITIES   3%   → $0.405B CET1 → $9B   RWA budget
  ├── SECURITIES_FINANCE 13% → $5.85B CET1  → $130B RWA budget
  ├── TREASURY_ALM      20%  → $9.0B CET1   → $200B RWA budget
  ├── CREDIT_LENDING    25%  → $11.25B CET1 → $250B RWA budget
  └── OPERATIONAL_BUFFER 12% → $5.4B CET1   (non-tradeable buffer)

RWA budget = CET1 allocation / CET1_MIN_RATIO (4.5%).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger(__name__)

FIRM_CET1_USD:  float = 45_000_000_000.0   # $45B — must match RegulatoryCapitalEngine
CET1_MIN_RATIO: float = 0.045              # Basel III 4.5% minimum

# Business line allocations as % of firm CET1
_BUSINESS_LINE_PCTS: dict[str, float] = {
    "MARKETS":             0.30,
    "SECURITIES_FINANCE":  0.13,
    "TREASURY_ALM":        0.20,
    "CREDIT_LENDING":      0.25,
    "OPERATIONAL_BUFFER":  0.12,
}

# Within MARKETS: desk allocations as % of MARKETS CET1
_MARKETS_DESK_PCTS: dict[str, float] = {
    "EQUITY":      0.30,
    "RATES":       0.35,
    "FX":          0.10,
    "CREDIT":      0.15,
    "DERIVATIVES": 0.07,
    "COMMODITIES": 0.03,
}

# Within SECURITIES_FINANCE: desk allocations as % of SECURITIES_FINANCE CET1
_SECFIN_DESK_PCTS: dict[str, float] = {
    "SECURITIES_FINANCE": 0.70,   # Repo, stock lending, prime brokerage
    "SECURITIZED":        0.30,   # Agency MBS, ABS, CMBS, CLO
}

# Desk → business line
DESK_TO_BL: dict[str, str] = {
    "EQUITY":             "MARKETS",
    "RATES":              "MARKETS",
    "FX":                 "MARKETS",
    "CREDIT":             "MARKETS",
    "DERIVATIVES":        "MARKETS",
    "COMMODITIES":        "MARKETS",
    "SECURITIES_FINANCE": "SECURITIES_FINANCE",
    "SECURITIZED":        "SECURITIES_FINANCE",
}


@dataclass
class DeskAllocation:
    desk: str
    business_line: str
    cet1_allocated_usd: float
    rwa_budget_usd: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "desk":               self.desk,
            "business_line":      self.business_line,
            "cet1_allocated_usd": round(self.cet1_allocated_usd, 2),
            "rwa_budget_usd":     round(self.rwa_budget_usd, 2),
        }


@dataclass
class BusinessLineAllocation:
    business_line: str
    cet1_allocated_usd: float
    rwa_budget_usd: float
    desk_allocations: dict[str, DeskAllocation] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "business_line":      self.business_line,
            "cet1_allocated_usd": round(self.cet1_allocated_usd, 2),
            "rwa_budget_usd":     round(self.rwa_budget_usd, 2),
            "desks":              {k: v.to_dict() for k, v in self.desk_allocations.items()},
        }


class CapitalAllocationFramework:
    """
    Top-down capital allocation framework.

    Each trading desk has a CET1 budget (and corresponding RWA budget).
    The OMS checks desk RWA consumption against this budget pre-trade.
    The CFO can reallocate between desks intra-quarter.
    """

    def __init__(self) -> None:
        self._firm_cet1 = FIRM_CET1_USD
        self._bl_allocations: dict[str, BusinessLineAllocation] = {}
        self._desk_allocations: dict[str, DeskAllocation] = {}
        self._rebuild()

    def _rebuild(self) -> None:
        markets_cet1 = self._firm_cet1 * _BUSINESS_LINE_PCTS["MARKETS"]
        secfin_cet1  = self._firm_cet1 * _BUSINESS_LINE_PCTS["SECURITIES_FINANCE"]

        for bl, pct in _BUSINESS_LINE_PCTS.items():
            bl_cet1 = self._firm_cet1 * pct
            bl_rwa  = bl_cet1 / CET1_MIN_RATIO
            desk_allocs: dict[str, DeskAllocation] = {}

            if bl == "MARKETS":
                for desk, desk_pct in _MARKETS_DESK_PCTS.items():
                    desk_cet1 = markets_cet1 * desk_pct
                    desk_rwa  = desk_cet1 / CET1_MIN_RATIO
                    da = DeskAllocation(desk=desk, business_line=bl,
                                        cet1_allocated_usd=desk_cet1, rwa_budget_usd=desk_rwa)
                    desk_allocs[desk] = da
                    self._desk_allocations[desk] = da

            elif bl == "SECURITIES_FINANCE":
                for desk, desk_pct in _SECFIN_DESK_PCTS.items():
                    desk_cet1 = secfin_cet1 * desk_pct
                    desk_rwa  = desk_cet1 / CET1_MIN_RATIO
                    da = DeskAllocation(desk=desk, business_line=bl,
                                        cet1_allocated_usd=desk_cet1, rwa_budget_usd=desk_rwa)
                    desk_allocs[desk] = da
                    self._desk_allocations[desk] = da

            self._bl_allocations[bl] = BusinessLineAllocation(
                business_line=bl,
                cet1_allocated_usd=bl_cet1,
                rwa_budget_usd=bl_rwa,
                desk_allocations=desk_allocs,
            )

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_desk_rwa_budget(self, desk: str) -> float:
        da = self._desk_allocations.get(desk)
        if da:
            return da.rwa_budget_usd
        # Unknown desk — assign a small residual bucket (5% of MARKETS)
        markets_cet1 = self._firm_cet1 * _BUSINESS_LINE_PCTS["MARKETS"]
        return (markets_cet1 * 0.05) / CET1_MIN_RATIO

    def get_desk_cet1_budget(self, desk: str) -> float:
        da = self._desk_allocations.get(desk)
        if da:
            return da.cet1_allocated_usd
        markets_cet1 = self._firm_cet1 * _BUSINESS_LINE_PCTS["MARKETS"]
        return markets_cet1 * 0.05

    def get_full_report(self) -> dict[str, Any]:
        return {
            "firm_cet1_usd":      round(self._firm_cet1, 2),
            "cet1_min_ratio":     CET1_MIN_RATIO,
            "total_rwa_budget":   round(self._firm_cet1 / CET1_MIN_RATIO, 2),
            "business_lines":     {bl: a.to_dict() for bl, a in self._bl_allocations.items()},
            "desk_allocations":   {d: da.to_dict() for d, da in self._desk_allocations.items()},
        }

    # ── Write ─────────────────────────────────────────────────────────────────

    def reallocate(
        self,
        from_desk: str,
        to_desk: str,
        cet1_amount_usd: float,
    ) -> dict[str, Any]:
        """
        Transfer CET1 allocation (and RWA budget) between desks.
        Simulates an intra-quarter CFO reallocation decision.
        """
        from_da = self._desk_allocations.get(from_desk)
        to_da   = self._desk_allocations.get(to_desk)

        if not from_da:
            return {"success": False, "error": f"Unknown desk: {from_desk}"}
        if not to_da:
            return {"success": False, "error": f"Unknown desk: {to_desk}"}
        if cet1_amount_usd <= 0:
            return {"success": False, "error": "Transfer amount must be positive."}
        if cet1_amount_usd > from_da.cet1_allocated_usd:
            return {
                "success": False,
                "error": (
                    f"Cannot transfer ${cet1_amount_usd/1e9:.2f}B from {from_desk} "
                    f"(only ${from_da.cet1_allocated_usd/1e9:.2f}B allocated)."
                ),
            }

        from_da.cet1_allocated_usd -= cet1_amount_usd
        from_da.rwa_budget_usd      = from_da.cet1_allocated_usd / CET1_MIN_RATIO
        to_da.cet1_allocated_usd   += cet1_amount_usd
        to_da.rwa_budget_usd        = to_da.cet1_allocated_usd / CET1_MIN_RATIO

        log.info(
            "capital.reallocated",
            from_desk=from_desk,
            to_desk=to_desk,
            cet1_usd=cet1_amount_usd,
        )
        return {
            "success":   True,
            "from_desk": from_da.to_dict(),
            "to_desk":   to_da.to_dict(),
        }


capital_allocation = CapitalAllocationFramework()
