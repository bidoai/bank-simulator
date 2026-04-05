"""
Intraday Liquidity Monitoring — BCBS 248

Tracks hourly cash flows against opening central bank balance and
credit line availability.
"""
from __future__ import annotations

from typing import Any


_OPENING_BALANCE_BN = 45.0
_CREDIT_LINE_BN = 50.0

_HOURLY_FLOWS = [
    {"time": "08:00", "description": "Opening / overnight settlements",       "payments_bn": -2.0,  "receipts_bn":  1.5},
    {"time": "09:00", "description": "FX settlement (CLS cycle)",             "payments_bn": -28.0, "receipts_bn":  3.0},
    {"time": "10:00", "description": "Securities maturity proceeds",          "payments_bn": -3.5,  "receipts_bn": 22.0},
    {"time": "11:00", "description": "Tri-party repo unwinds",                "payments_bn": -5.0,  "receipts_bn":  2.5},
    {"time": "12:00", "description": "Interbank placements",                  "payments_bn": -4.0,  "receipts_bn":  3.0},
    {"time": "13:00", "description": "Commercial paper issuance",             "payments_bn": -3.0,  "receipts_bn":  4.5},
    {"time": "14:00", "description": "Derivatives settlement (DTCC/LCH)",    "payments_bn": -15.0, "receipts_bn":  2.0},
    {"time": "15:00", "description": "Client wire receipts",                  "payments_bn": -2.5,  "receipts_bn":  8.0},
    {"time": "16:00", "description": "End-of-day RTGS settlements",          "payments_bn": -3.0,  "receipts_bn": 12.0},
    {"time": "17:00", "description": "Late settlements / nostro reconcile",  "payments_bn": -1.5,  "receipts_bn":  2.0},
]


class IntradayLiquidityMonitor:
    def __init__(self) -> None:
        self._opening = _OPENING_BALANCE_BN
        self._credit_line = _CREDIT_LINE_BN
        self._flows = _HOURLY_FLOWS

    def get_cashflow_profile(self) -> list[dict[str, Any]]:
        profile = []
        balance = self._opening
        for row in self._flows:
            net = row["payments_bn"] + row["receipts_bn"]
            balance += net
            profile.append({
                "time": row["time"],
                "description": row["description"],
                "payments_bn": row["payments_bn"],
                "receipts_bn": row["receipts_bn"],
                "net_bn": round(net, 2),
                "running_balance_bn": round(balance, 2),
                "credit_line_drawn_bn": round(max(0.0, -balance), 2),
            })
        return profile

    def get_peak_exposure(self) -> dict[str, Any]:
        profile = self.get_cashflow_profile()
        # Peak = most negative running balance (largest credit line draw)
        worst = min(profile, key=lambda r: r["running_balance_bn"])
        peak_draw = max(0.0, -worst["running_balance_bn"])
        return {
            "peak_time": worst["time"],
            "peak_balance_bn": worst["running_balance_bn"],
            "peak_credit_draw_bn": round(peak_draw, 2),
            "description": worst["description"],
        }

    def get_credit_line_utilization(self) -> dict[str, Any]:
        peak = self.get_peak_exposure()
        utilization_pct = (peak["peak_credit_draw_bn"] / self._credit_line * 100) if self._credit_line > 0 else 0.0
        return {
            "credit_line_total_bn": self._credit_line,
            "peak_draw_bn": peak["peak_credit_draw_bn"],
            "peak_time": peak["peak_time"],
            "utilization_pct": round(utilization_pct, 1),
            "headroom_bn": round(self._credit_line - peak["peak_credit_draw_bn"], 2),
        }

    def get_daily_summary(self) -> dict[str, Any]:
        profile = self.get_cashflow_profile()
        peak = self.get_peak_exposure()
        utilization = self.get_credit_line_utilization()
        eod = profile[-1]["running_balance_bn"]
        total_payments = sum(abs(r["payments_bn"]) for r in profile)
        total_receipts = sum(r["receipts_bn"] for r in profile)
        return {
            "opening_balance_bn": self._opening,
            "end_of_day_balance_bn": round(eod, 2),
            "total_payments_bn": round(total_payments, 2),
            "total_receipts_bn": round(total_receipts, 2),
            "net_flow_bn": round(total_receipts - total_payments, 2),
            "peak_exposure": peak,
            "credit_line": utilization,
            "cashflow_profile": profile,
            "credit_line_breached": utilization["peak_draw_bn"] > self._credit_line,
        }
