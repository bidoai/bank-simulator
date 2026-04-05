"""
RAROC Engine (Risk-Adjusted Return on Capital).

RAROC = (Revenue - Expected Loss - FTP Charge - OpRisk Allocation) / Economic Capital

Desk-level economic capital is internal (not regulatory Basel) and sized
by asset class risk profile. Hurdle rate: 12%.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional


# ── Economic Capital parameters by desk ────────────────────────────────────

EC_PARAMS: dict[str, dict] = {
    "EQUITY": {
        "ec_pct_aum": 0.08,
        "method": "pct_notional",
        "description": "8% of AuM — concentration and gap risk",
    },
    "RATES": {
        "ec_pct_notional": 0.03,
        "method": "pct_notional",
        "description": "3% of DV01-equivalent notional",
    },
    "FX": {
        "ec_pct_notional": 0.06,
        "method": "pct_notional",
        "description": "6% of gross notional",
    },
    "CREDIT": {
        "ec_pct_notional": 0.12,
        "method": "pct_notional",
        "description": "12% of notional — credit risk premium",
    },
    "DERIVATIVES": {
        "ec_pct_notional": 0.10,
        "method": "pct_notional",
        "description": "10% of gross notional",
    },
}

_DEFAULT_EC_PCT = 0.08

# Hurdle rate
HURDLE_RATE = 0.12   # 12% management target RAROC

# Total firm OpRisk capital ($B) — allocated proportionally to desk revenue
TOTAL_OPRISK_CAPITAL = 15e9

# IFRS9 PD by credit rating (annual) — mirrors credit engine assumptions
PD_BY_RATING: dict[str, float] = {
    "AAA": 0.0001,
    "AA":  0.0003,
    "A":   0.0010,
    "BBB": 0.0050,
    "BB":  0.0200,
    "B":   0.0600,
    "CCC": 0.1500,
    "NR":  0.0300,
}

# LGD assumptions by product type
LGD_BY_PRODUCT: dict[str, float] = {
    "equity":      0.55,
    "govt_bond":   0.10,
    "corp_bond":   0.40,
    "fx_spot":     0.05,
    "rates_swap":  0.30,
    "cds":         0.60,
    "default":     0.45,
}

# Representative desk metrics for standalone RAROC when live positions are thin
_DESK_DEFAULTS: dict[str, dict] = {
    "EQUITY": {
        "revenue": 1_200e6,
        "notional": 8_000e6,
        "rating": "A",
        "product": "equity",
        "rwa": 12_000e6,
    },
    "RATES": {
        "revenue": 2_800e6,
        "notional": 15_000e6,
        "rating": "AA",
        "product": "rates_swap",
        "rwa": 15_000e6,
    },
    "FX": {
        "revenue": 1_400e6,
        "notional": 8_000e6,
        "rating": "A",
        "product": "fx_spot",
        "rwa": 8_000e6,
    },
    "CREDIT": {
        "revenue": 2_100e6,
        "notional": 22_000e6,
        "rating": "BBB",
        "product": "corp_bond",
        "rwa": 22_000e6,
    },
    "DERIVATIVES": {
        "revenue": 800e6,
        "notional": 12_000e6,
        "rating": "A",
        "product": "derivatives",
        "rwa": 12_000e6,
    },
}


def _desk_type(desk_name: str) -> str:
    for key in EC_PARAMS:
        if key in desk_name.upper():
            return key
    return "DERIVATIVES"


def _ec_for_desk(desk_type: str, notional: float) -> float:
    params = EC_PARAMS.get(desk_type, {"ec_pct_notional": _DEFAULT_EC_PCT})
    pct = params.get("ec_pct_notional") or params.get("ec_pct_aum") or _DEFAULT_EC_PCT
    return notional * pct


class RAROCEngine:
    """RAROC engine for desk-level and firm-level profitability analysis."""

    def _get_ftp_charge(self, notional: float, desk_type: str) -> float:
        from infrastructure.treasury.ftp_dynamic import dynamic_ftp_engine
        tenor_map = {"EQUITY": 0.25, "RATES": 7.0, "FX": 0.08, "CREDIT": 5.0, "DERIVATIVES": 3.0}
        tenor = tenor_map.get(desk_type, 1.0)
        ftp_rate_bps = dynamic_ftp_engine.get_ftp_rate(tenor, "default")
        return notional * (ftp_rate_bps / 100.0) / 100.0

    def _expected_loss(self, notional: float, rating: str, product: str) -> float:
        pd = PD_BY_RATING.get(rating, PD_BY_RATING["NR"])
        lgd = LGD_BY_PRODUCT.get(product, LGD_BY_PRODUCT["default"])
        ead = notional
        return pd * lgd * ead

    def calculate_desk_raroc(
        self,
        desk_name: str,
        positions: list[dict],
        pnl: float,
    ) -> dict:
        """
        Calculate RAROC components for a single desk.

        Uses live position data if available; falls back to representative defaults.
        """
        dtype = _desk_type(desk_name)
        defaults = _DESK_DEFAULTS.get(dtype, _DESK_DEFAULTS["DERIVATIVES"])

        # Notional from positions
        notional = sum(
            abs(float(p.get("notional") or 0.0))
            or abs(float(p.get("quantity", 0.0))) * abs(float(p.get("avg_cost", 0.0)))
            for p in positions
        ) if positions else defaults["notional"]

        revenue = pnl if abs(pnl) > 1.0 else defaults["revenue"]
        notional = notional if notional > 1.0 else defaults["notional"]

        ec = _ec_for_desk(dtype, notional)
        ftp_charge = self._get_ftp_charge(notional, dtype)
        el = self._expected_loss(notional, defaults["rating"], defaults["product"])

        # OpRisk: proportional share by revenue (simplified)
        total_default_rev = sum(d["revenue"] for d in _DESK_DEFAULTS.values())
        oprisk_alloc = TOTAL_OPRISK_CAPITAL * (abs(revenue) / max(total_default_rev, 1.0)) * 0.12

        net_income = revenue - el - ftp_charge - oprisk_alloc
        raroc = (net_income / ec) if ec > 0 else 0.0

        return {
            "desk": desk_name,
            "desk_type": dtype,
            "revenue_usd": round(revenue, 0),
            "expected_loss_usd": round(el, 0),
            "ftp_charge_usd": round(ftp_charge, 0),
            "oprisk_allocation_usd": round(oprisk_alloc, 0),
            "net_income_usd": round(net_income, 0),
            "economic_capital_usd": round(ec, 0),
            "raroc_pct": round(raroc * 100.0, 2),
            "hurdle_rate_pct": round(HURDLE_RATE * 100.0, 1),
            "above_hurdle": raroc >= HURDLE_RATE,
            "notional_usd": round(notional, 0),
            "rwa_usd": round(defaults.get("rwa", notional), 0),
        }

    def calculate_portfolio_raroc(self) -> dict:
        """Calculate RAROC for all desks and the firm in aggregate."""
        try:
            from infrastructure.risk.risk_service import risk_service
            positions = risk_service.position_manager.get_all_positions()
            firm_report = risk_service.get_position_report()
            desk_pnl = {
                desk: data.get("total_pnl", 0.0)
                for desk, data in firm_report.get("by_desk", {}).items()
                if "error" not in data
            }
        except Exception:
            positions = []
            desk_pnl = {}

        by_desk = []
        total_revenue = total_el = total_ftp = total_oprisk = total_net = total_ec = 0.0

        for desk_name in _DESK_DEFAULTS:
            desk_positions = [p for p in positions if (p.get("desk") or "").upper() == desk_name]
            pnl = desk_pnl.get(desk_name, 0.0)
            result = self.calculate_desk_raroc(desk_name, desk_positions, pnl)
            by_desk.append(result)

            total_revenue += result["revenue_usd"]
            total_el += result["expected_loss_usd"]
            total_ftp += result["ftp_charge_usd"]
            total_oprisk += result["oprisk_allocation_usd"]
            total_net += result["net_income_usd"]
            total_ec += result["economic_capital_usd"]

        firm_raroc = total_net / total_ec if total_ec > 0 else 0.0
        by_desk.sort(key=lambda d: d["raroc_pct"], reverse=True)

        return {
            "by_desk": by_desk,
            "firm": {
                "total_revenue_usd": round(total_revenue, 0),
                "total_expected_loss_usd": round(total_el, 0),
                "total_ftp_charge_usd": round(total_ftp, 0),
                "total_oprisk_allocation_usd": round(total_oprisk, 0),
                "total_net_income_usd": round(total_net, 0),
                "total_economic_capital_usd": round(total_ec, 0),
                "firm_raroc_pct": round(firm_raroc * 100.0, 2),
                "hurdle_rate_pct": round(HURDLE_RATE * 100.0, 1),
                "above_hurdle": firm_raroc >= HURDLE_RATE,
            },
            "as_of": datetime.utcnow().isoformat(),
        }

    def get_rwa_density(self) -> dict:
        """
        RWA density = regulatory RWA / economic capital by business line.

        High density = regulatory capital-intensive relative to internal EC.
        """
        portfolio = self.calculate_portfolio_raroc()
        rows = []
        for desk in portfolio["by_desk"]:
            rwa = desk.get("rwa_usd", desk["notional_usd"])
            ec = desk["economic_capital_usd"]
            density = rwa / ec if ec > 0 else 0.0
            rorwa = desk["raroc_pct"] / density if density > 0 else 0.0
            rows.append({
                "desk": desk["desk"],
                "rwa_usd": round(rwa, 0),
                "economic_capital_usd": round(ec, 0),
                "rwa_density": round(density, 3),
                "raroc_pct": desk["raroc_pct"],
                "rorwa_pct": round(rorwa, 2),
            })
        return {
            "by_desk": sorted(rows, key=lambda d: d["rwa_density"], reverse=True),
            "as_of": datetime.utcnow().isoformat(),
        }

    def get_capital_allocation_summary(self) -> dict:
        """Which desks consume most economic capital and generate best returns."""
        portfolio = self.calculate_portfolio_raroc()
        total_ec = portfolio["firm"]["total_economic_capital_usd"]

        summary = []
        for desk in portfolio["by_desk"]:
            ec = desk["economic_capital_usd"]
            share = (ec / total_ec * 100.0) if total_ec > 0 else 0.0
            summary.append({
                "desk": desk["desk"],
                "economic_capital_usd": round(ec, 0),
                "ec_share_pct": round(share, 1),
                "raroc_pct": desk["raroc_pct"],
                "above_hurdle": desk["above_hurdle"],
                "revenue_per_ec_dollar": round(
                    desk["revenue_usd"] / ec if ec > 0 else 0.0, 4
                ),
            })

        summary.sort(key=lambda d: d["ec_share_pct"], reverse=True)
        return {
            "total_economic_capital_usd": round(total_ec, 0),
            "by_desk": summary,
            "as_of": datetime.utcnow().isoformat(),
        }


raroc_engine = RAROCEngine()
