"""
Volcker Rule Attribution Engine.

Implements Section 619 of the Dodd-Frank Act (Volcker Rule) classification
for each trading position and booking. Distinguishes permitted activities
(market-making, hedging, underwriting, customer facilitation) from
prohibited proprietary trading.

Classification is rule-based using desk, product type, tenor, and
counterparty presence as signals.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class VolckerClass(str, Enum):
    MARKET_MAKING         = "MARKET_MAKING"          # Permitted: inventory to service clients
    PERMITTED_HEDGING     = "PERMITTED_HEDGING"       # Permitted: hedging existing bank exposure
    CUSTOMER_FACILITATION = "CUSTOMER_FACILITATION"  # Permitted: executing client orders
    UNDERWRITING          = "UNDERWRITING"            # Permitted: underwriting securities
    REPO_SECURITIES_FINANCE = "REPO_SECURITIES_FINANCE"  # Permitted: repo/sec lending
    PROHIBITED_PROP       = "PROHIBITED_PROP"         # PROHIBITED: principal risk-taking


# ── Classification rules ──────────────────────────────────────────────────────
# Each rule is a (desk_prefix, product_subtype_prefix) → VolckerClass
# Rules are evaluated in order; first match wins. "" matches any.

_RULES: list[tuple[str, str, VolckerClass]] = [
    # Repo and securities finance — always permitted
    ("SECURITIES_FINANCE", "",         VolckerClass.REPO_SECURITIES_FINANCE),
    ("SECURITIZED",        "",         VolckerClass.REPO_SECURITIES_FINANCE),
    ("",                   "repo",     VolckerClass.REPO_SECURITIES_FINANCE),

    # Underwriting desks
    ("IBD",                "",         VolckerClass.UNDERWRITING),
    ("DCM",                "",         VolckerClass.UNDERWRITING),
    ("ECM",                "",         VolckerClass.UNDERWRITING),

    # Rates desk — IRS/bond trading is market-making
    ("RATES",              "irs",      VolckerClass.MARKET_MAKING),
    ("RATES",              "gov_bond", VolckerClass.MARKET_MAKING),
    ("RATES",              "",         VolckerClass.MARKET_MAKING),

    # Credit desk — market-making by default
    ("CREDIT",             "cds",      VolckerClass.MARKET_MAKING),
    ("CREDIT",             "",         VolckerClass.MARKET_MAKING),

    # FX desk — spot/forward market-making
    ("FX",                 "spot",     VolckerClass.MARKET_MAKING),
    ("FX",                 "fwd",      VolckerClass.MARKET_MAKING),
    ("FX",                 "",         VolckerClass.MARKET_MAKING),

    # Equity derivatives — market-making with a counterparty; prop if no counterparty
    ("EQUITY_DERIVATIVES", "option",   VolckerClass.MARKET_MAKING),
    ("EQUITY_DERIVATIVES", "",         VolckerClass.MARKET_MAKING),

    # Equity cash — market-making for institutional clients
    ("EQUITY",             "",         VolckerClass.MARKET_MAKING),

    # Commodities desk — customer facilitation
    ("COMMODITIES",        "",         VolckerClass.CUSTOMER_FACILITATION),

    # Hedging desks
    ("HEDGING",            "",         VolckerClass.PERMITTED_HEDGING),
    ("ALM",                "",         VolckerClass.PERMITTED_HEDGING),
    ("TREASURY",           "",         VolckerClass.PERMITTED_HEDGING),

    # Fallback: unknown desks booking large directional positions → flag as prop
]

# Desks whose activity is by default customer-facing (not prop)
_CUSTOMER_DESKS = {"PRIME_BROKERAGE", "PRIME_BROK", "EQUITY_DERIVATIVES", "STRUCTURED_PRODUCTS"}

# Short tenor threshold (≤ 60 days) is consistent with market-making inventory
_MM_TENOR_YEARS = 60 / 365.0


def classify_trade(
    desk: str,
    product_subtype: str | None = None,
    tenor_years: float | None = None,
    counterparty_id: str | None = None,
    notional: float | None = None,
) -> VolckerClass:
    """
    Classify a single trade under the Volcker Rule.

    Rules (in order):
    1. Rule table lookup by desk + product_subtype prefix.
    2. If a counterparty_id is present, lean toward customer facilitation.
    3. Short-tenor (<60d) with counterparty → market-making.
    4. Unknown desk + long tenor + no counterparty + large notional → prohibited prop.
    """
    desk_upper = (desk or "").upper()
    subtype = (product_subtype or "").lower()

    # Rule table lookup
    for desk_prefix, sub_prefix, volcker_class in _RULES:
        if desk_upper.startswith(desk_prefix) and subtype.startswith(sub_prefix):
            classification = volcker_class
            break
    else:
        # No rule matched — apply heuristics
        classification = _heuristic_classify(desk_upper, subtype, tenor_years, counterparty_id, notional)

    log.debug(
        "volcker.classified",
        desk=desk, product_subtype=product_subtype,
        tenor_years=tenor_years, classification=classification.value,
    )
    return classification


def _heuristic_classify(
    desk: str,
    subtype: str,
    tenor_years: float | None,
    counterparty_id: str | None,
    notional: float | None,
) -> VolckerClass:
    # Has a named counterparty → customer facilitation
    if counterparty_id:
        return VolckerClass.CUSTOMER_FACILITATION

    # Short-tenor inventory → market-making
    if tenor_years is not None and tenor_years <= _MM_TENOR_YEARS:
        return VolckerClass.MARKET_MAKING

    # Large directional position, no counterparty, long tenor → flag
    if notional and notional > 10_000_000 and not counterparty_id:
        return VolckerClass.PROHIBITED_PROP

    return VolckerClass.MARKET_MAKING


class VolckerAttributionEngine:
    """Portfolio-level Volcker attribution and compliance reporting."""

    def classify_trade(
        self,
        desk: str,
        product_subtype: str | None = None,
        tenor_years: float | None = None,
        counterparty_id: str | None = None,
        notional: float | None = None,
    ) -> str:
        return classify_trade(desk, product_subtype, tenor_years, counterparty_id, notional).value

    def get_portfolio_attribution(self, positions: list[dict]) -> dict[str, Any]:
        """
        Classify all open positions and aggregate notional by Volcker class.

        Each position dict is expected to have: desk, product_subtype (optional),
        notional/quantity, counterparty_id (optional), tenor_years (optional).
        """
        attribution: dict[str, float] = {vc.value: 0.0 for vc in VolckerClass}
        classified: list[dict] = []

        for pos in positions:
            desk         = pos.get("desk") or pos.get("book_id", "UNKNOWN")
            subtype      = pos.get("product_subtype")
            tenor        = pos.get("tenor_years")
            cpty         = pos.get("counterparty_id")
            notional     = abs(pos.get("notional") or (
                (pos.get("quantity") or 0) * (pos.get("price") or pos.get("avg_cost") or 0)
            ))

            vc = classify_trade(desk, subtype, tenor, cpty, notional)
            attribution[vc.value] = round(attribution[vc.value] + notional, 2)

            classified.append({
                "instrument":         pos.get("instrument") or pos.get("ticker"),
                "desk":               desk,
                "product_subtype":    subtype,
                "notional_usd":       round(notional, 2),
                "volcker_class":      vc.value,
                "is_flagged":         vc == VolckerClass.PROHIBITED_PROP,
            })

        total_notional = sum(attribution.values())

        return {
            "attribution_by_class": attribution,
            "pct_by_class": {
                k: round(v / total_notional * 100, 1) if total_notional else 0.0
                for k, v in attribution.items()
            },
            "total_notional_usd":   round(total_notional, 2),
            "position_count":       len(classified),
            "positions":            classified,
        }

    def get_compliance_report(self, positions: list[dict]) -> dict[str, Any]:
        """
        Highlight positions classified as PROHIBITED_PROP with notional > $1M.
        These require compliance review.
        """
        attribution = self.get_portfolio_attribution(positions)
        flags = [
            p for p in attribution["positions"]
            if p["is_flagged"] and p["notional_usd"] >= 1_000_000
        ]

        return {
            "flagged_positions":  flags,
            "flag_count":         len(flags),
            "flagged_notional_usd": round(sum(f["notional_usd"] for f in flags), 2),
            "attribution_summary": attribution["attribution_by_class"],
            "compliant":          len(flags) == 0,
            "status":             "COMPLIANT" if len(flags) == 0 else "REVIEW_REQUIRED",
        }


volcker_engine = VolckerAttributionEngine()
