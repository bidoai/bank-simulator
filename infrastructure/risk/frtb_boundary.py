"""
FRTB Trading/Banking Book Boundary Classifier (Basel MAR12).

Instruments are assigned to trading book (TB) or banking book (BB) based on
presumption criteria. Positions that cross the boundary without regulatory
approval are flagged.
"""
from __future__ import annotations

from typing import Any
import structlog

log = structlog.get_logger()

TRADING_BOOK_INSTRUMENT_TYPES: set[str] = {
    "equity_listed",
    "equity_index",
    "fx_spot",
    "fx_forward",
    "interest_rate_swap",
    "cds_single_name",
    "cds_index",
    "equity_option",
    "ir_option",
    "fx_option",
    "govt_bond",
    "corp_bond",
}

BANKING_BOOK_INSTRUMENT_TYPES: set[str] = {
    "loan_retail",
    "loan_corporate",
    "loan_mortgage",
    "equity_unlisted",
    "real_estate",
    "corp_bond_htm",
}

# Instrument types that are unconditionally TB regardless of other factors
_ALWAYS_TRADING: set[str] = {
    "equity_listed",
    "equity_index",
    "fx_spot",
    "fx_forward",
    "equity_option",
    "ir_option",
    "fx_option",
    "interest_rate_swap",
    "cds_single_name",
    "cds_index",
}

# Instrument types that are unconditionally BB
_ALWAYS_BANKING: set[str] = {
    "loan_retail",
    "loan_corporate",
    "loan_mortgage",
    "equity_unlisted",
    "real_estate",
    "corp_bond_htm",
}


def _classify_type(instrument_type: str, holding_intent: str | None) -> tuple[str, str]:
    """
    Return (book, rationale) based on instrument type and holding intent.
    holding_intent: "trading" | "htm" | "afi" | None (unknown → default to trading presumption)
    """
    t = (instrument_type or "").lower()

    if t in _ALWAYS_BANKING:
        return "BANKING", f"Instrument type '{t}' is unconditionally assigned to banking book (MAR12.10)"

    if t in _ALWAYS_TRADING:
        return "TRADING", f"Instrument type '{t}' is subject to trading book presumption (MAR12.4)"

    # Ambiguous types: corp_bond, govt_bond resolved by holding intent
    if t in ("corp_bond", "govt_bond"):
        intent = (holding_intent or "trading").lower()
        if intent == "htm":
            return "BANKING", f"'{t}' held-to-maturity — banking book (MAR12.10)"
        if intent in ("afi", "afs"):
            return "BANKING", f"'{t}' available-for-investment — banking book (MAR12.10)"
        return "TRADING", f"'{t}' held with trading intent — trading book (MAR12.4)"

    # Unknown instrument type — default to trading book presumption
    return "TRADING", f"Unknown instrument type '{t}' — applying trading book presumption (MAR12.4 default)"


# ---------------------------------------------------------------------------
# Demo positions used as fallback when no live positions are available
# ---------------------------------------------------------------------------

_DEMO_POSITIONS: list[dict[str, Any]] = [
    {"position_id": "POS-001", "instrument_type": "equity_listed",    "desk": "EQUITY",      "notional": 50_000_000,  "holding_intent": "trading",   "book": "EQ_BOOK_1"},
    {"position_id": "POS-002", "instrument_type": "equity_index",     "desk": "EQUITY",      "notional": 30_000_000,  "holding_intent": "trading",   "book": "EQ_BOOK_1"},
    {"position_id": "POS-003", "instrument_type": "interest_rate_swap","desk": "RATES",       "notional": 200_000_000, "holding_intent": "trading",   "book": "RATES_BOOK_1"},
    {"position_id": "POS-004", "instrument_type": "govt_bond",        "desk": "RATES",       "notional": 80_000_000,  "holding_intent": "trading",   "book": "RATES_BOOK_1"},
    {"position_id": "POS-005", "instrument_type": "govt_bond",        "desk": "RATES",       "notional": 40_000_000,  "holding_intent": "htmINVALID","book": "RATES_BOOK_2"},
    {"position_id": "POS-006", "instrument_type": "fx_forward",       "desk": "FX",          "notional": 120_000_000, "holding_intent": "trading",   "book": "FX_BOOK_1"},
    {"position_id": "POS-007", "instrument_type": "cds_single_name",  "desk": "CREDIT",      "notional": 25_000_000,  "holding_intent": "trading",   "book": "CREDIT_BOOK_1"},
    {"position_id": "POS-008", "instrument_type": "loan_corporate",   "desk": "CREDIT",      "notional": 150_000_000, "holding_intent": "htmINVALID","book": "BANKING_BOOK_1"},
    {"position_id": "POS-009", "instrument_type": "loan_retail",      "desk": "RETAIL",      "notional": 500_000_000, "holding_intent": None,        "book": "BANKING_BOOK_2"},
    {"position_id": "POS-010", "instrument_type": "equity_unlisted",  "desk": "EQUITY",      "notional": 8_000_000,   "holding_intent": None,        "book": "BANKING_BOOK_3"},
    {"position_id": "POS-011", "instrument_type": "corp_bond",        "desk": "CREDIT",      "notional": 60_000_000,  "holding_intent": "trading",   "book": "CREDIT_BOOK_2"},
    {"position_id": "POS-012", "instrument_type": "corp_bond_htm",    "desk": "CREDIT",      "notional": 45_000_000,  "holding_intent": "htm",       "book": "BANKING_BOOK_4"},
    {"position_id": "POS-013", "instrument_type": "equity_option",    "desk": "DERIVATIVES", "notional": 15_000_000,  "holding_intent": "trading",   "book": "DERIV_BOOK_1"},
    {"position_id": "POS-014", "instrument_type": "equity_listed",    "desk": "BANKING",     "notional": 5_000_000,   "holding_intent": "afi",       "book": "BANKING_BOOK_5"},
]


class FRTBBoundaryClassifier:
    """
    Classifies positions as TRADING or BANKING per Basel FRTB MAR12.

    All methods work with the demo portfolio if no live positions are provided.
    Flagging logic: a position in the TRADING book desk context but classified
    as BANKING (or vice versa) without regulatory approval is flagged.
    """

    def classify_position(self, position: dict[str, Any]) -> dict[str, Any]:
        """
        Classify a single position.

        Returns the original position dict enriched with:
        - frtb_book: "TRADING" | "BANKING"
        - frtb_rationale: human-readable explanation
        - flagged: bool — True if boundary appears to be crossed without approval
        - flag_reason: str | None
        """
        instrument_type = position.get("instrument_type", "")
        holding_intent  = position.get("holding_intent")
        desk            = (position.get("desk") or "").upper()

        book, rationale = _classify_type(instrument_type, holding_intent)

        # Detect apparent boundary crossings (heuristic: desk name implies a book)
        flagged = False
        flag_reason: str | None = None
        desk_implies_banking = "BANKING" in desk or "RETAIL" in desk
        desk_implies_trading = desk in ("EQUITY", "RATES", "FX", "CREDIT", "DERIVATIVES", "MARKETS", "TRADING")

        if book == "BANKING" and desk_implies_trading:
            flagged = True
            flag_reason = (
                f"Position classified as BANKING but sits on trading desk '{desk}'. "
                "Regulatory approval required for banking book designation on trading desks (MAR12.16)."
            )
        elif book == "TRADING" and desk_implies_banking:
            flagged = True
            flag_reason = (
                f"Position classified as TRADING but desk '{desk}' is a banking book context. "
                "Internal transfer to trading book requires senior risk approval (MAR12.16)."
            )

        result = {
            **position,
            "frtb_book": book,
            "frtb_rationale": rationale,
            "flagged": flagged,
            "flag_reason": flag_reason,
        }
        log.debug(
            "frtb_boundary.classified",
            position_id=position.get("position_id"),
            instrument_type=instrument_type,
            book=book,
            flagged=flagged,
        )
        return result

    def classify_all_positions(
        self, positions: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        """Classify all positions (uses demo portfolio if positions is None)."""
        if positions is None:
            positions = _DEMO_POSITIONS
        return [self.classify_position(p) for p in positions]

    def get_boundary_report(
        self, positions: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """
        Full FRTB boundary report.

        Returns summary stats, per-position classification, and a list of
        flagged boundary issues.
        """
        classified = self.classify_all_positions(positions)

        tb_notional = 0.0
        bb_notional = 0.0
        flagged_positions: list[dict[str, Any]] = []

        for pos in classified:
            notional = float(pos.get("notional", 0) or 0)
            if pos["frtb_book"] == "TRADING":
                tb_notional += notional
            else:
                bb_notional += notional
            if pos["flagged"]:
                flagged_positions.append(pos)

        total = tb_notional + bb_notional
        tb_pct = round(tb_notional / total * 100, 1) if total > 0 else 0.0
        bb_pct = round(bb_notional / total * 100, 1) if total > 0 else 0.0

        log.info(
            "frtb_boundary.report_generated",
            positions_classified=len(classified),
            flagged=len(flagged_positions),
            tb_notional_m=round(tb_notional / 1e6, 1),
            bb_notional_m=round(bb_notional / 1e6, 1),
        )

        return {
            "summary": {
                "total_positions": len(classified),
                "trading_book_positions": sum(1 for p in classified if p["frtb_book"] == "TRADING"),
                "banking_book_positions": sum(1 for p in classified if p["frtb_book"] == "BANKING"),
                "trading_book_notional": tb_notional,
                "banking_book_notional": bb_notional,
                "trading_book_pct": tb_pct,
                "banking_book_pct": bb_pct,
                "flagged_boundary_issues": len(flagged_positions),
            },
            "positions": classified,
            "flagged_issues": flagged_positions,
            "regulatory_note": (
                "Classification per Basel FRTB MAR12. Instruments in TRADING_BOOK_INSTRUMENT_TYPES "
                "are subject to FRTB market risk capital (SA or IMA). Instruments in "
                "BANKING_BOOK_INSTRUMENT_TYPES are subject to credit risk capital. "
                "Reclassification requires Regulatory Affairs approval (MAR12.16)."
            ),
        }


# Module-level singleton
frtb_classifier = FRTBBoundaryClassifier()
