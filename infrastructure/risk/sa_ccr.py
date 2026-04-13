"""
SA-CCR Engine — Standardised Approach for Counterparty Credit Risk (Basel III CRE52).

EAD = alpha × (RC + PFE_aggregate), alpha = 1.4
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import structlog

from infrastructure.risk.counterparty_registry import counterparty_registry

log = structlog.get_logger(__name__)

ALPHA = 1.4

# Supervisory factors by asset class
SF_IR: dict[str, float] = {
    "<=1Y": 0.005,
    "1Y-5Y": 0.010,
    ">5Y": 0.015,
}

SF_FX: float = 0.04

SF_CREDIT: dict[str, float] = {
    "AAA": 0.0038,
    "AA":  0.0038,
    "A":   0.0042,
    "BBB": 0.0054,
    "BB":  0.0106,
    "B":   0.0160,
    "CCC": 0.0600,
}

SF_EQUITY_SINGLE: float = 0.32
SF_EQUITY_INDEX:  float = 0.20

SF_COMMODITY: dict[str, float] = {
    "energy":  0.18,
    "metals":  0.18,
    "agri":    0.18,
    "other":   0.10,
}

# IR tenor bucket correlation (rho between buckets)
IR_RHO: float = 0.5

# Correlations for FX and equity within hedging sets
FX_RHO:     float = 1.0   # each currency pair is its own hedging set
EQUITY_RHO: float = 0.50  # within-hedging-set correlation (single-name)

# Risk weights for RWA (bank counterparty by rating)
BANK_RISK_WEIGHTS: dict[str, float] = {
    "AAA": 0.20,
    "AA":  0.20,
    "A":   0.50,
    "A+":  0.50,
    "BBB": 0.50,
    "BBB+": 0.50,
    "BB":  1.00,
    "B":   1.50,
    "CCC": 1.50,
}


# ---------------------------------------------------------------------------
# Sample netting sets keyed by counterparty registry ID
# ---------------------------------------------------------------------------

SAMPLE_NETTING_SETS: list[dict[str, Any]] = [
    {
        "netting_set_id": "NS-GS-001",
        "counterparty_id": "Goldman_Sachs",
        "margined": True,
        "threshold_usd": 0.0,
        "mta_usd": 10_000.0,
        "nica_usd": 110_000_000.0,   # net independent collateral amount
        "positions": [
            # IR swap: USD 500M notional, pay-fixed 10Y
            {"type": "IR", "currency": "USD", "notional": 500_000_000, "start_years": 0.0,
             "end_years": 10.0, "delta": -1},
            # IR swap: USD 200M notional, receive-fixed 2Y
            {"type": "IR", "currency": "USD", "notional": 200_000_000, "start_years": 0.0,
             "end_years": 2.0, "delta": 1},
        ],
    },
    {
        "netting_set_id": "NS-JPM-001",
        "counterparty_id": "JPMorgan_Chase",
        "margined": True,
        "threshold_usd": 50_000.0,
        "mta_usd": 25_000.0,
        "nica_usd": 88_000_000.0,
        "positions": [
            # FX forward: EUR/USD 300M
            {"type": "FX", "currency_pair": "EURUSD", "notional": 300_000_000, "delta": 1},
            # FX forward: GBP/USD 150M
            {"type": "FX", "currency_pair": "GBPUSD", "notional": 150_000_000, "delta": -1},
        ],
    },
    {
        "netting_set_id": "NS-DB-001",
        "counterparty_id": "Deutsche_Bank",
        "margined": True,
        "threshold_usd": 100_000.0,
        "mta_usd": 50_000.0,
        "nica_usd": 70_000_000.0,
        "positions": [
            # Single-name CDS: BBB rated ref entity, 100M notional
            {"type": "CREDIT", "rating": "BBB", "notional": 100_000_000, "delta": 1},
            # Single-name CDS: A rated ref entity, 50M notional
            {"type": "CREDIT", "rating": "A", "notional": 50_000_000, "delta": -1},
        ],
    },
    {
        "netting_set_id": "NS-BNP-001",
        "counterparty_id": "BNP_Paribas",
        "margined": True,
        "threshold_usd": 0.0,
        "mta_usd": 20_000.0,
        "nica_usd": 88_000_000.0,
        "positions": [
            # Equity total return swap: single name, 200M
            {"type": "EQUITY", "subtype": "single", "notional": 200_000_000, "delta": 1},
            # Equity index swap: SPX, 100M
            {"type": "EQUITY", "subtype": "index", "notional": 100_000_000, "delta": -1},
        ],
    },
    {
        "netting_set_id": "NS-HSBC-001",
        "counterparty_id": "HSBC",
        "margined": True,
        "threshold_usd": 0.0,
        "mta_usd": 15_000.0,
        "nica_usd": 88_000_000.0,
        "positions": [
            # Commodity energy: crude oil forward, 80M
            {"type": "COMMODITY", "subtype": "energy", "notional": 80_000_000, "delta": 1},
            # IR swap: EUR 300M, 5Y
            {"type": "IR", "currency": "EUR", "notional": 300_000_000, "start_years": 0.0,
             "end_years": 5.0, "delta": 1},
        ],
    },
]


# ---------------------------------------------------------------------------
# SA-CCR Engine
# ---------------------------------------------------------------------------

class SACCREngine:
    """
    Standardised Approach for Counterparty Credit Risk.

    Implements Basel III CRE52 for the five main asset classes:
    IR, FX, Credit, Equity, Commodity.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_ead(
        self,
        counterparty_id: str,
        positions: list[dict[str, Any]],
        collateral_balance: float = 0.0,
        *,
        margined: bool = True,
        threshold_usd: float = 0.0,
        mta_usd: float = 0.0,
        nica_usd: float = 0.0,
    ) -> dict[str, Any]:
        """
        Compute EAD for a single netting set.

        collateral_balance: net collateral held (positive = we hold their collateral).
        """
        # MTM proxy: sum of delta × notional × a small factor (simplified, no live MTM)
        gross_mtm = self._estimate_mtm(positions)
        v = gross_mtm
        c = collateral_balance

        # Replacement Cost
        if margined:
            rc = max(v - c, threshold_usd + mta_usd - nica_usd, 0.0)
        else:
            rc = max(v - c, 0.0)

        # Add-on by asset class
        addon_breakdown = self._calculate_addons(positions)
        addon_aggregate = sum(addon_breakdown.values())

        # PFE multiplier
        multiplier = self._pfe_multiplier(v, c, addon_aggregate)
        pfe = multiplier * addon_aggregate

        ead = ALPHA * (rc + pfe)

        log.info(
            "sa_ccr.ead_calculated",
            counterparty_id=counterparty_id,
            rc=round(rc, 0),
            pfe=round(pfe, 0),
            ead=round(ead, 0),
        )

        return {
            "counterparty_id": counterparty_id,
            "rc_usd": round(rc, 2),
            "pfe_usd": round(pfe, 2),
            "ead_usd": round(ead, 2),
            "pfe_multiplier": round(multiplier, 6),
            "addon_aggregate_usd": round(addon_aggregate, 2),
            "addon_breakdown_usd": {k: round(v2, 2) for k, v2 in addon_breakdown.items()},
            "margined": margined,
            "alpha": ALPHA,
        }

    def calculate_portfolio_ead(
        self,
        all_positions_by_counterparty: dict[str, list[dict[str, Any]]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Compute EAD for all netting sets. Uses SAMPLE_NETTING_SETS if not supplied.
        Returns list of per-netting-set EAD dicts.
        """
        results = []

        netting_sets = SAMPLE_NETTING_SETS

        for ns in netting_sets:
            cp_id = ns["counterparty_id"]
            # Retrieve VM balance from collateral accounts as a proxy for C
            collateral = self._get_collateral_balance(cp_id)
            result = self.calculate_ead(
                counterparty_id=cp_id,
                positions=ns["positions"],
                collateral_balance=collateral,
                margined=ns.get("margined", True),
                threshold_usd=ns.get("threshold_usd", 0.0),
                mta_usd=ns.get("mta_usd", 0.0),
                nica_usd=ns.get("nica_usd", 0.0),
            )
            result["netting_set_id"] = ns["netting_set_id"]
            results.append(result)

        return results

    def get_rwa(self, ead: float, risk_weight: float) -> float:
        """Return credit RWA from EAD and risk weight."""
        return ead * risk_weight

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _estimate_mtm(self, positions: list[dict[str, Any]]) -> float:
        """
        Simplified MTM estimate: delta × notional × asset_class_factor.
        Not a real pricing model — used to seed RC calculation.
        """
        mtm = 0.0
        for p in positions:
            notional = float(p.get("notional", 0.0))
            delta = float(p.get("delta", 1))
            ptype = p.get("type", "")
            if ptype == "IR":
                # ~0.5% for mid-market IRS
                mtm += delta * notional * 0.005
            elif ptype == "FX":
                mtm += delta * notional * 0.01
            elif ptype == "CREDIT":
                mtm += delta * notional * 0.02
            elif ptype == "EQUITY":
                mtm += delta * notional * 0.05
            elif ptype == "COMMODITY":
                mtm += delta * notional * 0.03
        return mtm

    def _get_collateral_balance(self, counterparty_id: str) -> float:
        """
        Retrieve net VM balance for the counterparty from vm_engine accounts.
        Falls back to 0 if unavailable.
        """
        try:
            from infrastructure.collateral.vm_engine import vm_engine
            # Map registry IDs to CSA IDs
            cp_to_csa: dict[str, str] = {
                "Goldman_Sachs":  "CSA-GS-001",
                "JPMorgan_Chase": "CSA-JPM-001",
                "Deutsche_Bank":  "CSA-DB-001",
                "BNP_Paribas":    "CSA-MER-001",
                "HSBC":           "CSA-LCH-001",
            }
            csa_id = cp_to_csa.get(counterparty_id)
            if csa_id:
                account = vm_engine.get_account(csa_id)
                if account:
                    return account.vm_received_usd - account.vm_posted_usd
        except Exception:
            pass
        return 0.0

    # ------------------------------------------------------------------
    # Add-on calculations by asset class
    # ------------------------------------------------------------------

    def _calculate_addons(self, positions: list[dict[str, Any]]) -> dict[str, float]:
        addon: dict[str, float] = {}

        by_type: dict[str, list[dict]] = {}
        for p in positions:
            t = p.get("type", "UNKNOWN")
            by_type.setdefault(t, []).append(p)

        if "IR" in by_type:
            addon["IR"] = self._addon_ir(by_type["IR"])
        if "FX" in by_type:
            addon["FX"] = self._addon_fx(by_type["FX"])
        if "CREDIT" in by_type:
            addon["CREDIT"] = self._addon_credit(by_type["CREDIT"])
        if "EQUITY" in by_type:
            addon["EQUITY"] = self._addon_equity(by_type["EQUITY"])
        if "COMMODITY" in by_type:
            addon["COMMODITY"] = self._addon_commodity(by_type["COMMODITY"])

        return addon

    def _supervisory_duration(self, start_years: float, end_years: float) -> float:
        """SD = (exp(-0.05×S) - exp(-0.05×E)) / 0.05"""
        return (math.exp(-0.05 * start_years) - math.exp(-0.05 * end_years)) / 0.05

    def _ir_tenor_bucket(self, end_years: float) -> str:
        if end_years <= 1.0:
            return "<=1Y"
        elif end_years <= 5.0:
            return "1Y-5Y"
        return ">5Y"

    def _addon_ir(self, positions: list[dict]) -> float:
        """
        IR add-on per Basel CRE52.

        Within each currency hedging set, bucket trades by tenor and aggregate
        with intra-bucket correlation ρ=0.5.
        """
        # Group by currency → bucket → list of (delta × adj_notional)
        hs: dict[str, dict[str, float]] = {}

        for p in positions:
            currency = str(p.get("currency", "USD"))
            notional = float(p.get("notional", 0.0))
            start_y  = float(p.get("start_years", 0.0))
            end_y    = float(p.get("end_years", 1.0))
            delta    = float(p.get("delta", 1))

            sd = self._supervisory_duration(start_y, end_y)
            adj_notional = notional * sd
            bucket = self._ir_tenor_bucket(end_y)
            sf = SF_IR[bucket]
            effective = delta * adj_notional * sf

            hs.setdefault(currency, {})
            hs[currency][bucket] = hs[currency].get(bucket, 0.0) + effective

        total_addon = 0.0
        for buckets in hs.values():
            d = list(buckets.values())
            # ∑ ρ² × (∑dᵢ)² + ∑ dᵢ² × (1-ρ²)
            sum_d = sum(d)
            sum_d2 = sum(x * x for x in d)
            var = IR_RHO ** 2 * sum_d ** 2 + (1 - IR_RHO ** 2) * sum_d2
            total_addon += math.sqrt(max(var, 0.0))

        return abs(total_addon)

    def _addon_fx(self, positions: list[dict]) -> float:
        """FX add-on: SF=4% × adjusted notional per currency pair hedging set."""
        hs: dict[str, float] = {}
        for p in positions:
            pair = str(p.get("currency_pair", "UNKNOWN"))
            notional = float(p.get("notional", 0.0))
            delta    = float(p.get("delta", 1))
            hs[pair] = hs.get(pair, 0.0) + delta * notional * SF_FX

        # Each currency pair is its own hedging set — sum absolute values
        return sum(abs(v) for v in hs.values())

    def _addon_credit(self, positions: list[dict]) -> float:
        """Credit add-on: SF by rating. Full correlation for single-name (ρ=0.5 across names)."""
        d_list = []
        for p in positions:
            rating  = str(p.get("rating", "BBB"))
            notional = float(p.get("notional", 0.0))
            delta    = float(p.get("delta", 1))
            sf = SF_CREDIT.get(rating, SF_CREDIT["BBB"])
            d_list.append(delta * notional * sf)

        if not d_list:
            return 0.0

        rho = 0.50
        sum_d = sum(d_list)
        sum_d2 = sum(x * x for x in d_list)
        var = rho ** 2 * sum_d ** 2 + (1 - rho ** 2) * sum_d2
        return math.sqrt(max(var, 0.0))

    def _addon_equity(self, positions: list[dict]) -> float:
        """Equity add-on: SF=32% single name, 20% index."""
        d_list = []
        for p in positions:
            subtype  = str(p.get("subtype", "single"))
            notional = float(p.get("notional", 0.0))
            delta    = float(p.get("delta", 1))
            sf = SF_EQUITY_SINGLE if subtype == "single" else SF_EQUITY_INDEX
            d_list.append(delta * notional * sf)

        if not d_list:
            return 0.0

        rho = EQUITY_RHO
        sum_d = sum(d_list)
        sum_d2 = sum(x * x for x in d_list)
        var = rho ** 2 * sum_d ** 2 + (1 - rho ** 2) * sum_d2
        return math.sqrt(max(var, 0.0))

    def _addon_commodity(self, positions: list[dict]) -> float:
        """Commodity add-on: SF by commodity type. Same-type hedging."""
        hs: dict[str, float] = {}
        for p in positions:
            subtype  = str(p.get("subtype", "other"))
            notional = float(p.get("notional", 0.0))
            delta    = float(p.get("delta", 1))
            sf = SF_COMMODITY.get(subtype, SF_COMMODITY["other"])
            hs[subtype] = hs.get(subtype, 0.0) + delta * notional * sf

        # Sum abs across commodity types (no cross-type netting)
        return sum(abs(v) for v in hs.values())

    def _pfe_multiplier(
        self, v: float, c: float, addon_aggregate: float
    ) -> float:
        """
        multiplier = min(1, 0.05 + 0.95 × exp((V-C) / (2 × 0.95 × AddOn)))
        """
        if addon_aggregate <= 0.0:
            return 1.0
        exponent = (v - c) / (2.0 * 0.95 * addon_aggregate)
        return min(1.0, 0.05 + 0.95 * math.exp(exponent))


sa_ccr_engine = SACCREngine()
