"""
Adapter: converts bank-simulator Trade/Position objects to pyxva Agreement/Trade format.

This module bridges the gap between the bank-simulator's internal data models
and the pyxva risk engine's expected input format. It also exposes a sample
pipeline config so the XVA dashboard can render demo data immediately without
needing live trades.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


class XVAAdapter:
    """
    Converts bank-simulator objects to pyxva-compatible dicts and runs
    the XVA pipeline (CVA, DVA, FVA, PFE profiles).
    """

    @staticmethod
    def from_positions(positions: list) -> list:
        """
        Convert a list of bank-simulator position dicts (from PositionManager.get_all_positions())
        to pyxva Trade dicts.

        Equity positions are excluded — their CVA is computed analytically.
        Non-equity positions are mapped by instrument type to a product_type
        with a representative maturity.
        """
        _PRODUCT_MAP: dict[str, str] = {
            "US10Y": "IRS", "US2Y": "IRS",
            "IRS_USD_10Y": "IRS",
            "EURUSD": "FX_FORWARD", "GBPUSD": "FX_FORWARD",
            "IG_CDX": "CDS",
            "CL1": "COMMODITY_FORWARD",
        }
        _MATURITY_MAP: dict[str, float] = {
            "IRS": 7.0,
            "FX_FORWARD": 0.5,
            "CDS": 5.0,
            "COMMODITY_FORWARD": 1.0,
        }
        _EQUITY_INSTRUMENTS = {"AAPL", "MSFT", "GOOGL", "NVDA", "AAPL_CALL_200"}

        trades = []
        for p in positions:
            instrument = p.get("instrument", "")
            if instrument in _EQUITY_INSTRUMENTS:
                continue
            product_type = _PRODUCT_MAP.get(instrument, "IRS")
            notional = abs(float(p.get("quantity", 0)) * float(p.get("avg_cost", 0)))
            if notional < 1.0:
                continue
            trades.append({
                "trade_id": f"{instrument}_{p.get('book_id', 'UNK')}",
                "product_type": product_type,
                "notional": round(notional, 2),
                "currency": p.get("currency", "USD"),
                "maturity_years": _MATURITY_MAP.get(product_type, 1.0),
                "fixed_rate": 0.045,
                "pay_leg": "fixed" if float(p.get("quantity", 0)) > 0 else "float",
            })
        return trades

    @staticmethod
    def from_trade(trade: Any) -> dict:
        """
        Convert a single bank-simulator Trade object to a pyxva Trade dict skeleton.
        """
        return {
            "trade_id": getattr(trade, "trade_id", None),
            "product_type": getattr(trade, "product_type", "IRS"),
            "notional": getattr(trade, "notional", 0.0),
            "currency": getattr(trade, "currency", "USD"),
            "maturity": getattr(trade, "maturity", None),
            "fixed_rate": getattr(trade, "fixed_rate", None),
            "pay_leg": getattr(trade, "pay_leg", "fixed"),
            # TODO: extend with float leg, payment dates, day count conventions
        }

    @staticmethod
    def run_pipeline(config: dict) -> dict:
        """
        Run the pyxva risk pipeline with the given config and return a
        JSON-serialisable results dict.

        Falls back gracefully if pyxva is not installed.
        """
        try:
            from pyxva import RiskEngine, MarketData  # type: ignore

            market_data = MarketData.from_config(config.get("market_data", {}))
            engine = RiskEngine(config=config)
            results = engine.run(market_data=market_data)

            return {
                "status": "ok",
                "cva": float(results.cva),
                "dva": float(results.dva),
                "fva": float(results.fva),
                "pfe_profile": [float(x) for x in results.pfe_profile],
                "pfe_dates": results.pfe_dates,
                "netting_sets": [
                    {
                        "id": ns.id,
                        "ead": float(ns.ead),
                        "collateral": float(ns.collateral),
                        "net_mtm": float(ns.net_mtm),
                    }
                    for ns in (results.netting_sets or [])
                ],
            }

        except ImportError:
            log.warning("pyxva not installed — returning sample XVA results")
            return XVAAdapter._sample_results()

        except Exception as exc:
            log.error("XVA pipeline error", exc_info=exc)
            return {"status": "error", "message": str(exc)}

    @staticmethod
    def sample_config() -> dict:
        """
        Return a hardcoded example pipeline configuration.

        This config describes a plain-vanilla USD IRS trade under a REGVM CSA,
        valued with the Hull-White 1-Factor interest rate model. Use it to demo
        the XVA dashboard without needing live trades or a live pyxva install.
        """
        return {
            "simulation": {
                "n_paths": 2000,
                "n_steps": 40,
                "horizon_years": 10.0,
                "random_seed": 42,
            },
            "model": {
                "type": "HullWhite1F",
                "mean_reversion": 0.05,
                "volatility": 0.015,
            },
            "market_data": {
                "currency": "USD",
                "discount_curve": "OIS",
                "rate": 0.045,
                "credit_spread_counterparty_bps": 120,
                "credit_spread_own_bps": 80,
                "funding_spread_bps": 40,
                "recovery_rate": 0.40,
            },
            "csa": {
                "type": "REGVM",
                "threshold": 0.0,
                "minimum_transfer_amount": 250_000,
                "margin_period_of_risk_days": 10,
                "collateral_currency": "USD",
            },
            "trades": [
                {
                    "trade_id": "IRS-DEMO-001",
                    "product_type": "IRS",
                    "notional": 100_000_000,
                    "currency": "USD",
                    "maturity_years": 10.0,
                    "fixed_rate": 0.0450,
                    "pay_leg": "fixed",
                    "payment_frequency": "semi-annual",
                    "day_count": "ACT/360",
                },
                {
                    "trade_id": "IRS-DEMO-002",
                    "product_type": "IRS",
                    "notional": 50_000_000,
                    "currency": "USD",
                    "maturity_years": 5.0,
                    "fixed_rate": 0.0430,
                    "pay_leg": "float",
                    "payment_frequency": "quarterly",
                    "day_count": "ACT/360",
                },
            ],
        }

    @staticmethod
    def _sample_results() -> dict:
        """
        Return plausible hard-coded XVA results for demo/testing when pyxva
        is not available. Values are representative of a typical USD IRS book.
        """
        import math

        # Simulate a hump-shaped PFE profile (peaks around year 4-5)
        n_steps = 40
        horizon = 10.0
        pfe_dates = [round(i * horizon / n_steps, 2) for i in range(n_steps + 1)]
        pfe_profile = [
            round(
                2_800_000 * math.sin(math.pi * t / horizon) * math.exp(-0.15 * t),
                0,
            )
            for t in pfe_dates
        ]

        return {
            "status": "ok",
            "cva": -485_000.0,
            "dva": 210_000.0,
            "fva": -95_000.0,
            "pfe_profile": pfe_profile,
            "pfe_dates": pfe_dates,
            "netting_sets": [
                {
                    "id": "NS-001",
                    "ead": 2_150_000.0,
                    "collateral": 1_800_000.0,
                    "net_mtm": 350_000.0,
                }
            ],
        }
