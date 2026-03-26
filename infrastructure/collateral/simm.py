"""
SIMM — ISDA Standard Initial Margin Model (approximation).

Implements a simplified SIMM calculation for the Interest Rate (IR)
and Credit Qualifying (CRQ) risk classes, which cover the majority
of Apex Global Bank's derivatives portfolio.

Reference: ISDA SIMM Methodology, version 2.6 (published parameters).
This is an educational approximation — not a production SIMM implementation.

Key simplifications:
  - IR: single-currency (USD), delta risk only (no vega/curvature)
  - CRQ: issuer-level delta only (no sector correlation buckets)
  - Cross-risk-class correlation: IR↔CRQ correlation = 0.20
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional
import structlog

log = structlog.get_logger()


# ── SIMM published parameters (IR risk class, USD "Regular" vol) ──────────
# Risk weights in basis points per $1 notional delta (i.e., $RW = sensitivity × RW_bps / 10000)
# Source: ISDA SIMM 2.6 Table 1 — Interest Rate risk weights

IR_RISK_WEIGHTS_BPS: dict[str, float] = {
    "2w":   77.0,
    "1m":   77.0,
    "3m":   77.0,
    "6m":   64.0,
    "1y":   58.0,
    "2y":   49.0,
    "3y":   48.0,
    "5y":   48.0,
    "10y":  44.0,
    "15y":  44.0,
    "20y":  46.0,
    "30y":  45.0,
}

# Intra-bucket IR correlation matrix (USD tenors — 12×12 simplified as off-diagonal ρ)
# Adjacent tenors: high correlation (~0.91); distant tenors: lower (~0.29)
# Approximation: ρ(i,j) = exp(-0.05 * |midpoint_years(i) - midpoint_years(j)|)
_TENOR_YEARS: dict[str, float] = {
    "2w": 0.04, "1m": 0.08, "3m": 0.25, "6m": 0.5, "1y": 1.0,
    "2y": 2.0,  "3y": 3.0,  "5y": 5.0,  "10y": 10.0,
    "15y": 15.0, "20y": 20.0, "30y": 30.0,
}

def _ir_correlation(t1: str, t2: str) -> float:
    y1 = _TENOR_YEARS.get(t1, 1.0)
    y2 = _TENOR_YEARS.get(t2, 1.0)
    return math.exp(-0.05 * abs(y1 - y2))


# ── Credit Qualifying (CRQ) risk weights ──────────────────────────────────
# Risk weight by rating bucket (simplified — SIMM 2.6 Table 5, Bucket 1-3)
CRQ_RISK_WEIGHTS_BPS: dict[str, float] = {
    "AAA":  38.0,
    "AA":   38.0,
    "A":    42.0,
    "BBB":  54.0,
    "BB":  249.0,
    "B":   249.0,
    "CCC": 369.0,
    "NR":  249.0,
}

# Intra-bucket CRQ correlation (same sector): 0.45
# Cross-bucket CRQ correlation: 0.27
CRQ_INTRA_BUCKET_CORR = 0.45
CRQ_CROSS_BUCKET_CORR = 0.27

# Cross-risk-class correlation (IR ↔ CRQ)
CROSS_RISK_CLASS_CORR = 0.20


# ── Data input structures ─────────────────────────────────────────────────

@dataclass
class IRDelta:
    """DV01 sensitivity (USD per basis point) at a given tenor."""
    tenor: str          # "1y", "5y", "10y", etc. — must be a key in IR_RISK_WEIGHTS_BPS
    dv01_usd: float     # positive = long duration (receives fixed or long bond)
    currency: str = "USD"


@dataclass
class CRQDelta:
    """CS01 sensitivity (USD per basis point) for a credit position."""
    issuer_id: str
    cs01_usd: float     # positive = short protection / long credit risk
    rating: str = "BBB"
    sector: str = "CORP"


@dataclass
class SIMMInput:
    """All sensitivities for a netting set / portfolio."""
    ir_deltas:  list[IRDelta]  = field(default_factory=list)
    crq_deltas: list[CRQDelta] = field(default_factory=list)


@dataclass
class SIMMResult:
    ir_im_usd:     float = 0.0
    crq_im_usd:    float = 0.0
    total_im_usd:  float = 0.0
    detail:        dict  = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ir_im_usd":    round(self.ir_im_usd, 0),
            "crq_im_usd":   round(self.crq_im_usd, 0),
            "total_im_usd": round(self.total_im_usd, 0),
            "detail":       self.detail,
        }


class SIMMEngine:
    """
    Simplified SIMM calculator for IR and CRQ risk classes.
    """

    def compute_ir_im(self, ir_deltas: list[IRDelta]) -> float:
        """
        Compute IR IM for a USD rates portfolio.

        Algorithm (SIMM 2.6 Section 4.1):
          1. Weight each sensitivity: WS_k = DV01_k × RW_k
          2. Aggregate with intra-bucket correlation:
             K = sqrt( Σ_k WS_k² + Σ_{k≠l} ρ_{kl} × WS_k × WS_l )
        """
        if not ir_deltas:
            return 0.0

        # Pre-net: aggregate DV01 at the same tenor before weighting
        net_dv01: dict[str, float] = {}
        for d in ir_deltas:
            net_dv01[d.tenor] = net_dv01.get(d.tenor, 0.0) + d.dv01_usd

        tenors = list(net_dv01.keys())
        ws: dict[str, float] = {
            tenor: dv01 * IR_RISK_WEIGHTS_BPS.get(tenor, 50.0) / 10_000.0
            for tenor, dv01 in net_dv01.items()
        }

        sum_sq = sum(v ** 2 for v in ws.values())
        cross = 0.0
        for i, t1 in enumerate(tenors):
            for j, t2 in enumerate(tenors):
                if i < j:
                    rho = _ir_correlation(t1, t2)
                    cross += 2.0 * rho * ws[t1] * ws[t2]

        return math.sqrt(max(0.0, sum_sq + cross))

    def compute_crq_im(self, crq_deltas: list[CRQDelta]) -> float:
        """
        Compute CRQ IM for a credit portfolio.

        Single-bucket approximation (no sector grouping for MVP).
        """
        if not crq_deltas:
            return 0.0

        ws: list[float] = []
        for d in crq_deltas:
            rw = CRQ_RISK_WEIGHTS_BPS.get(d.rating, 249.0) / 10_000.0
            ws.append(d.cs01_usd * rw)

        sum_sq = sum(v ** 2 for v in ws)
        cross = 0.0
        for i in range(len(ws)):
            for j in range(i + 1, len(ws)):
                cross += 2.0 * CRQ_INTRA_BUCKET_CORR * ws[i] * ws[j]

        return math.sqrt(max(0.0, sum_sq + cross))

    def compute(self, inputs: SIMMInput) -> SIMMResult:
        """
        Full SIMM computation across IR and CRQ risk classes.

        Cross-risk-class aggregation:
          Total IM = sqrt( IR_IM² + CRQ_IM² + 2 × ρ_cross × IR_IM × CRQ_IM )
        """
        ir_im  = self.compute_ir_im(inputs.ir_deltas)
        crq_im = self.compute_crq_im(inputs.crq_deltas)

        # Cross-risk-class aggregation
        total = math.sqrt(
            ir_im ** 2
            + crq_im ** 2
            + 2.0 * CROSS_RISK_CLASS_CORR * ir_im * crq_im
        )

        return SIMMResult(
            ir_im_usd=round(ir_im, 0),
            crq_im_usd=round(crq_im, 0),
            total_im_usd=round(total, 0),
            detail={
                "ir_weighted_sensitivities": len(inputs.ir_deltas),
                "crq_positions": len(inputs.crq_deltas),
                "cross_rc_correlation": CROSS_RISK_CLASS_CORR,
            },
        )

    def compute_sample_portfolio(self) -> SIMMResult:
        """
        Compute SIMM IM for the representative Apex rates + credit portfolio.

        Based on approximate DV01 and CS01 sensitivities from the
        current position book (IRS and CDS positions).
        """
        ir_deltas = [
            IRDelta("2y",   dv01_usd=-850_000),    # payer IRS 2y (negative = pay fixed)
            IRDelta("5y",   dv01_usd= 1_200_000),  # receiver IRS 5y
            IRDelta("10y",  dv01_usd=-2_400_000),  # payer IRS 10y (large book)
            IRDelta("10y",  dv01_usd= 1_800_000),  # receiver IRS 10y (partial offset)
            IRDelta("30y",  dv01_usd=-600_000),     # payer IRS 30y
        ]

        crq_deltas = [
            CRQDelta("CDX_IG", cs01_usd=-150_000, rating="BBB", sector="INDEX"),
            CRQDelta("C",      cs01_usd= -80_000,  rating="A",   sector="BANK"),
            CRQDelta("BAC",    cs01_usd= -75_000,  rating="A",   sector="BANK"),
            CRQDelta("HY_IDX", cs01_usd=  90_000,  rating="BB",  sector="INDEX"),
        ]

        return self.compute(SIMMInput(ir_deltas=ir_deltas, crq_deltas=crq_deltas))


simm_engine = SIMMEngine()
