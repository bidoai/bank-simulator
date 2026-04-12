"""FastAPI routes for the Securitized Products dashboard."""
from __future__ import annotations

from fastapi import APIRouter

from infrastructure.securitized_products.service import securitized_products_service

router = APIRouter(prefix="/securitized", tags=["securitized"])


@router.get("/overview")
def overview() -> dict:
    return securitized_products_service.get_overview()


@router.get("/inventory")
def inventory() -> list[dict]:
    return securitized_products_service.get_inventory()


@router.get("/relative-value")
def relative_value() -> dict:
    return securitized_products_service.get_relative_value()


@router.get("/stress")
def stress() -> dict:
    return securitized_products_service.run_stress()


@router.get("/pipeline")
def pipeline() -> dict:
    return securitized_products_service.get_pipeline()


@router.get("/mbs-analytics")
def mbs_analytics(r0: float | None = None) -> list[dict]:
    """Live agency MBS analytics: OAS, effective duration, convexity, PSA cash flows, 7-scenario analysis."""
    return securitized_products_service.get_mbs_analytics(r0)


# ---------------------------------------------------------------------------
# Trade booking — routes to the OMS (P5)
# ---------------------------------------------------------------------------

from pydantic import BaseModel
from fastapi import HTTPException


class SecuritizedOrderRequest(BaseModel):
    book_id: str
    ticker: str    # FNMA_TBA | SPEC_POOL | AUTO_ABS | CMBS_AA | CLO_AAA
    side: str      # "buy" | "sell"
    qty: float     # face value in USD
    counterparty_id: str | None = None
    override_raroc: bool = False


@router.post("/book-trade")
def book_securitized_trade(order: SecuritizedOrderRequest) -> dict:
    """
    Book a Securitized Products trade into the OMS.
    Draws from the SECURITIZED capital pool; enforces notional and RWA limits.
    Tickers: FNMA_TBA, SPEC_POOL, AUTO_ABS, CMBS_AA, CLO_AAA
    """
    from infrastructure.trading.oms import oms
    _TICKER_SUBTYPE = {
        "FNMA_TBA":  "agency_mbs",
        "SPEC_POOL": "agency_mbs",
        "AUTO_ABS":  "abs",
        "CMBS_AA":   "cmbs",
        "CLO_AAA":   "clo",
    }
    try:
        conf = oms.submit_order(
            desk="SECURITIZED",
            book_id=order.book_id,
            ticker=order.ticker.upper(),
            side=order.side.lower(),
            qty=order.qty,
            counterparty_id=order.counterparty_id,
            product_subtype=_TICKER_SUBTYPE.get(order.ticker.upper(), "structured"),
            override_raroc=order.override_raroc,
        )
        return conf.model_dump(mode="json")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
