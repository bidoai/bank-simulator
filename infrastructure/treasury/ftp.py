"""
Fund Transfer Pricing (FTP) engine.

Treasury charges each trading desk an internal funding cost based on the
tenor and product type of their positions. Without FTP, desk P&L numbers
are economically meaningless — a desk holding $5B in 10-year bonds looks
profitable without the cost of the funding that supports that position.

FTP rate = tenor-matched USD swap rate + product liquidity premium.
"""
from __future__ import annotations

import numpy as np
from datetime import datetime
from dataclasses import dataclass, field, asdict
import structlog

log = structlog.get_logger()


class SwapCurve:
    """USD swap curve — key tenor points with linear interpolation."""

    # Simulated rates reflecting a normalised post-hiking environment (%)
    TENOR_RATES: dict[float, float] = {
        0.08:  4.90,   # overnight / 1-month
        0.25:  4.85,   # 3-month SOFR
        0.50:  4.80,   # 6-month
        1.00:  4.65,   # 1-year
        2.00:  4.40,   # 2-year
        3.00:  4.30,   # 3-year
        5.00:  4.25,   # 5-year
        7.00:  4.30,   # 7-year
        10.00: 4.40,   # 10-year
        30.00: 4.60,   # 30-year
    }

    # Liquidity premium per product type (bps added to swap rate)
    LIQUIDITY_PREMIUM_BPS: dict[str, float] = {
        "equity":      10.0,
        "govt_bond":    0.0,   # most liquid — no premium
        "corp_bond":   25.0,
        "fx_spot":      5.0,
        "rates_swap":  15.0,
        "cds":         50.0,
        "default":     20.0,
    }

    def get_rate(self, tenor_years: float) -> float:
        """Linearly interpolate swap rate for tenor. Returns rate in %."""
        tenors = sorted(self.TENOR_RATES.keys())
        rates = [self.TENOR_RATES[t] for t in tenors]
        tenor_clamped = max(tenors[0], min(tenors[-1], tenor_years))
        return float(np.interp(tenor_clamped, tenors, rates))

    def get_ftp_rate(self, tenor_years: float, product_type: str = "default") -> float:
        """Swap rate + liquidity premium. Returns rate in %."""
        swap_rate = self.get_rate(tenor_years)
        premium_bps = self.LIQUIDITY_PREMIUM_BPS.get(product_type, self.LIQUIDITY_PREMIUM_BPS["default"])
        return swap_rate + premium_bps / 100.0

    def snapshot(self) -> dict[str, float]:
        """Key tenor rates for dashboard display."""
        key_tenors = [0.25, 0.50, 1.0, 2.0, 5.0, 10.0, 30.0]
        return {f"{t}y": round(self.get_rate(t), 4) for t in key_tenors}


@dataclass
class DeskFTPCharge:
    desk: str
    notional_funded_usd: float
    avg_tenor_years: float
    ftp_rate_pct: float
    daily_charge_usd: float
    annual_charge_usd: float
    as_of: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class FTPEngine:
    """Fund Transfer Pricing engine."""

    # Assumed tenor (years) per product type when no maturity is available
    PRODUCT_TENOR: dict[str, float] = {
        "equity":      0.25,   # equities funded on O/N repo, rolled quarterly
        "govt_bond":   2.00,
        "corp_bond":   5.00,
        "fx_spot":     0.08,   # FX settled/rolled near overnight
        "rates_swap":  7.00,
        "cds":         5.00,
        "default":     1.00,
    }

    # Ticker → product type
    PRODUCT_MAP: dict[str, str] = {
        "AAPL":        "equity",
        "MSFT":        "equity",
        "GOOGL":       "equity",
        "US10Y":       "govt_bond",
        "US2Y":        "govt_bond",
        "EURUSD":      "fx_spot",
        "GBPUSD":      "fx_spot",
        "IG_CDX":      "cds",
        "IRS_USD_10Y": "rates_swap",
    }

    def __init__(self) -> None:
        self.curve = SwapCurve()

    def _product_type(self, ticker: str) -> str:
        return self.PRODUCT_MAP.get(ticker.upper(), "default")

    def calculate_desk_charges(self, positions: list[dict]) -> list[DeskFTPCharge]:
        """Group positions by desk/book_id and compute FTP charge per desk."""
        from collections import defaultdict
        desks: dict[str, dict] = defaultdict(lambda: {"notional": 0.0, "tenor_weighted": 0.0})

        for pos in positions:
            desk = pos.get("desk") or "UNKNOWN"
            notional = abs(float(pos.get("notional") or 0.0))
            if notional == 0.0:
                qty = abs(float(pos.get("quantity", 0.0)))
                price = abs(float(pos.get("avg_cost", 0.0)))
                notional = qty * price
            product_type = self._product_type(pos.get("instrument", ""))
            tenor = self.PRODUCT_TENOR.get(product_type, self.PRODUCT_TENOR["default"])

            desks[desk]["notional"] += notional
            desks[desk]["tenor_weighted"] += notional * tenor

        charges: list[DeskFTPCharge] = []
        now = datetime.utcnow().isoformat()
        for desk, data in desks.items():
            notional = data["notional"]
            if notional == 0.0:
                continue
            avg_tenor = data["tenor_weighted"] / notional
            # Determine blended product type from largest position (approximation)
            ftp_rate = self.curve.get_ftp_rate(avg_tenor, "default")
            daily = notional * (ftp_rate / 100.0) / 365.0
            charges.append(DeskFTPCharge(
                desk=desk,
                notional_funded_usd=round(notional, 2),
                avg_tenor_years=round(avg_tenor, 4),
                ftp_rate_pct=round(ftp_rate, 4),
                daily_charge_usd=round(daily, 2),
                annual_charge_usd=round(notional * ftp_rate / 100.0, 2),
                as_of=now,
            ))
        return sorted(charges, key=lambda c: c.annual_charge_usd, reverse=True)

    def get_ftp_summary(self, positions: list[dict]) -> dict:
        charges = self.calculate_desk_charges(positions)
        total_notional = sum(c.notional_funded_usd for c in charges)
        total_daily = sum(c.daily_charge_usd for c in charges)
        total_annual = sum(c.annual_charge_usd for c in charges)
        blended = (total_annual / total_notional * 100.0) if total_notional > 0 else 0.0
        return {
            "total_funded_notional_usd": round(total_notional, 2),
            "total_daily_charge_usd": round(total_daily, 2),
            "total_annual_charge_usd": round(total_annual, 2),
            "blended_ftp_rate_pct": round(blended, 4),
            "by_desk": [c.to_dict() for c in charges],
            "curve_snapshot": self.curve.snapshot(),
            "as_of": datetime.utcnow().isoformat(),
        }

    def get_adjusted_pnl(self, positions: list[dict], desk_pnl: dict[str, float]) -> dict:
        """Subtract FTP charges from gross desk P&L."""
        charges = {c.desk: c.daily_charge_usd for c in self.calculate_desk_charges(positions)}
        rows = []
        total_gross = total_ftp = total_net = 0.0
        for desk, gross in desk_pnl.items():
            charge = charges.get(desk, 0.0)
            net = gross - charge
            rows.append({"desk": desk, "gross_pnl": round(gross, 2),
                         "ftp_charge": round(charge, 2), "net_pnl": round(net, 2)})
            total_gross += gross
            total_ftp += charge
            total_net += net
        return {
            "by_desk": rows,
            "total_gross_pnl": round(total_gross, 2),
            "total_ftp_charge": round(total_ftp, 2),
            "total_net_pnl": round(total_net, 2),
            "as_of": datetime.utcnow().isoformat(),
        }


ftp_engine = FTPEngine()
