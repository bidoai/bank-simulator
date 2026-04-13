"""
Risk Service — unified risk snapshot wiring PositionManager, VaRCalculator, and LimitManager.

Runs Monte Carlo VaR per desk and firm-wide, then pushes results into the limit framework.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from infrastructure.trading.position_manager import PositionManager
from infrastructure.trading.limit_manager import LimitManager
from infrastructure.risk.var_calculator import VaRCalculator

log = structlog.get_logger()

# Default annualised volatilities by desk
_DESK_VOLS: dict[str, float] = {
    "EQUITY":      0.20,
    "RATES":       0.05,
    "FX":          0.08,
    "CREDIT":      0.15,
    "COMMODITIES": 0.18,
    "DERIVATIVES": 0.25,
}

# Map desk name → LimitManager limit name
_DESK_LIMIT: dict[str, str] = {
    "EQUITY":      "VAR_EQUITY",
    "RATES":       "VAR_RATES",
    "FX":          "VAR_FX",
    "CREDIT":      "VAR_CREDIT",
    "DERIVATIVES": "VAR_DERIV",
}


class RiskService:
    def __init__(self):
        self.position_manager = PositionManager()
        self.limit_manager = LimitManager()
        self.add_sample_positions()

    def add_sample_positions(self) -> None:
        # Equity positions
        pm = self.position_manager
        pm.add_trade("EQUITY", "EQ_BOOK_1", "AAPL",            qty=5_000,     price=185.00)
        pm.add_trade("EQUITY", "EQ_BOOK_1", "MSFT",            qty=3_000,     price=420.00)
        pm.add_trade("EQUITY", "EQ_BOOK_1", "NVDA",            qty=2_000,     price=875.00)
        # Rates positions
        pm.add_trade("RATES",  "RATES_BOOK_1", "US10Y",        qty=10_000,    price=98.50)
        pm.add_trade("RATES",  "RATES_BOOK_1", "US2Y",         qty=8_000,     price=99.10)
        # FX positions
        pm.add_trade("FX",     "FX_BOOK_1", "EURUSD",          qty=1_000_000, price=1.085)
        pm.add_trade("FX",     "FX_BOOK_1", "GBPUSD",          qty=500_000,   price=1.265)
        # Credit position
        pm.add_trade("CREDIT", "CREDIT_BOOK_1", "HYEM_ETF",    qty=20_000,    price=78.50)
        # Derivatives position
        pm.add_trade("DERIVATIVES", "DERIV_BOOK_1", "SPX_CALL_5200", qty=500, price=45.50)
        log.info("risk_service.sample_positions_loaded")

    def run_snapshot(self) -> dict[str, Any]:
        calculator = VaRCalculator(confidence=0.99, horizon_days=1)
        all_positions = self.position_manager.get_all_positions()

        # ── Group positions by desk ──────────────────────────────────────────
        desk_positions: dict[str, dict[str, float]] = {}
        desk_vols_map: dict[str, dict[str, float]] = {}
        all_pos_notionals: dict[str, float] = {}
        all_pos_vols: dict[str, float] = {}

        for pos in all_positions:
            desk = pos["desk"]
            instrument = pos["instrument"]
            notional = pos["notional"]
            vol = _DESK_VOLS.get(desk, 0.20)

            if desk not in desk_positions:
                desk_positions[desk] = {}
                desk_vols_map[desk] = {}

            desk_positions[desk][instrument] = notional
            desk_vols_map[desk][instrument] = vol
            all_pos_notionals[instrument] = notional
            all_pos_vols[instrument] = vol

        # ── Run VaR per desk and Firm ────────────────────────────────────────
        var_by_desk: dict[str, Any] = {}
        for desk, positions in desk_positions.items():
            if not positions:
                continue
            result = calculator.monte_carlo_var(
                positions=positions,
                vols=desk_vols_map[desk],
                book_id=desk,
            )
            var_by_desk[desk] = result

            # Update LimitManager if this desk has a VaR limit
            limit_name = _DESK_LIMIT.get(desk)
            if limit_name:
                self.limit_manager.update(limit_name, float(result.var_amount))

        if all_pos_notionals:
            firm_result = calculator.monte_carlo_var(
                positions=all_pos_notionals,
                vols=all_pos_vols,
                book_id="FIRM",
            )
            self.limit_manager.update("VAR_FIRM", float(firm_result.var_amount))
            var_by_desk["FIRM"] = firm_result

        # ── Sensitivity Limits (DV01, Equity Delta, Vega) ─────────────────────
        from infrastructure.trading.greeks import GreeksCalculator
        # We need market prices for Greeks
        # Note: In a real system we'd get this from MarketDataFeed, here we use position last_price
        aggr = GreeksCalculator.aggregate(all_positions)
        
        # Update Firm DV01
        self.limit_manager.update("DV01_FIRM", aggr["portfolio"]["dv01"])
        
        # Update Equity Delta (APEX_EQ_MM)
        # Find all positions for EQUITY desk
        eq_positions = [p for p in all_positions if p["desk"] == "EQUITY"]
        eq_aggr = GreeksCalculator.aggregate(eq_positions)
        self.limit_manager.update("EQUITY_DELTA", eq_aggr["portfolio"]["delta"])
        
        # Update Vega (APEX_DERIV)
        deriv_positions = [p for p in all_positions if p["desk"] == "DERIVATIVES"]
        deriv_aggr = GreeksCalculator.aggregate(deriv_positions)
        self.limit_manager.update("VEGA_FIRM", deriv_aggr["portfolio"]["vega"])

        # ── Concentration Limits ──────────────────────────────────────────────
        from infrastructure.risk.concentration_risk import concentration_monitor
        conc = concentration_monitor.analyze(all_positions)
        
        # SINGLE_NAME_EQ_PCT (Max % for any ticker in EQUITY desk)
        eq_conc = concentration_monitor.analyze(eq_positions)
        if eq_conc["single_name"]:
            max_pct = max(r["pct"] * 100.0 for r in eq_conc["single_name"])
            max_notional = max(r["notional"] for r in eq_conc["single_name"])
            self.limit_manager.update("SINGLE_NAME_EQ_PCT", max_pct)
            self.limit_manager.update("SINGLE_NAME_EQ_NOTIONAL", max_notional)

        limit_summary = self.limit_manager.get_summary()
        limit_report = self.limit_manager.get_report()

        breaches = [
            {"limit": l["name"], "desk": l["desk"], "utilisation_pct": l["utilisation_pct"]}
            for l in limit_report
            if l["status"] in ("RED", "BREACH")
        ]
        warnings = [
            {"limit": l["name"], "desk": l["desk"], "utilisation_pct": l["utilisation_pct"]}
            for l in limit_report
            if l["status"] in ("YELLOW", "ORANGE")
        ]

        log.info("risk_service.snapshot_complete", desks=list(var_by_desk.keys()))

        return {
            "snapshot_time": datetime.now(timezone.utc).isoformat(),
            "var_by_desk": {
                desk: {
                    "book_id": r.book_id,
                    "var_amount": float(r.var_amount),
                    "cvar_amount": float(r.cvar_amount) if r.cvar_amount else None,
                    "method": r.method,
                    "confidence_level": float(r.confidence_level),
                    "horizon_days": r.horizon_days,
                }
                for desk, r in var_by_desk.items()
            },
            "limit_summary": limit_summary,
            "limit_report": limit_report,
            "breaches": breaches,
            "warnings": warnings,
        }

    def get_position_report(self) -> dict:
        return self.position_manager.get_firm_report()


risk_service = RiskService()
